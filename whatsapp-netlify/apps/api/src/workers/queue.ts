import { randomUUID } from "node:crypto";
import { z } from "zod";
import { db, serial, Prisma, type Tx } from "../config/db.js";
import { env, requireMeta } from "../config/env.js";
import { sendMeta, verifyMeta, MetaError, failurePolicy, retryDelay } from "../services/meta.js";
import { refreshTemplate, assertTemplate } from "../services/templates.js";
import { processPendingWebhooks } from "../services/webhook.js";
const include = { contact: true, workspace: true, campaign: { include: { template: true } } } satisfies Prisma.OutboundMessageInclude;
type Job = Prisma.OutboundMessageGetPayload<{ include: typeof include }>;
function invalidReason(job: Job) {
  if (!job.contact.consentGranted || job.contact.optedOutAt) return "El contacto no tiene consentimiento vigente.";
  if (job.contact.phoneE164 !== job.phoneE164) return "El teléfono cambió después de programar el mensaje.";
  if (job.expiresAt <= new Date()) return "El mensaje superó su plazo de envío.";
  if (job.campaign && ["CANCELLED", "COMPLETED"].includes(job.campaign.status)) return "La campaña ya no admite envíos.";
  if (job.kind === "BOT_REPLY" && (!job.contact.lastInboundAt || job.contact.lastInboundAt.getTime() + 86400000 <= Date.now())) return "La ventana de respuesta de 24 horas está cerrada.";
  if (job.campaign) {
    try { assertTemplate(job.campaign.template); } catch { return "La plantilla ya no está aprobada o no incluye la baja requerida."; }
    const snapshot = z.object({ metaId: z.string(), body: z.string(), name: z.string(), language: z.string() }).safeParse(job.campaign.templateSnapshot);
    if (!snapshot.success || snapshot.data.metaId !== job.campaign.template.metaId || snapshot.data.body !== job.campaign.template.bodyText || snapshot.data.name !== job.campaign.template.name || snapshot.data.language !== job.campaign.template.language) return "La plantilla cambió. Crea una campaña con la nueva versión.";
  }
  return null;
}
async function lease(token: string) {
  return serial(async tx => {
    await tx.workerLease.createMany({ data: [{ name: "queue", token: "", expiresAt: new Date(0) }], skipDuplicates: true });
    return (await tx.workerLease.updateMany({ where: { name: "queue", expiresAt: { lte: new Date() } }, data: { token, expiresAt: new Date(Date.now() + env.CLAIM_LEASE_SECONDS * 1000) } })).count === 1;
  });
}
async function claim(allowed: string[]) {
  return serial(async tx => {
    const job = await tx.outboundMessage.findFirst({ where: { workspaceId: { in: allowed }, status: "QUEUED", nextAttemptAt: { lte: new Date() }, workspace: { sendingState: "ACTIVE" }, OR: [{ campaignId: null }, { campaign: { status: { in: ["RUNNING", "SCHEDULED"] } } }], ...(env.DRY_RUN ? {} : { AND: [{ OR: [{ dryRun: true }, { workspace: { dryRun: true } }, { kind: "BOT_REPLY" }, { campaign: { template: { syncedAt: { gte: new Date(Date.now() - 600000) } } } }] }] }) }, include, orderBy: [{ nextAttemptAt: "asc" }, { id: "asc" }] });
    if (!job) return null;
    const reason = invalidReason(job);
    if (reason) { await tx.outboundMessage.update({ where: { id: job.id }, data: { status: "CANCELLED", lastError: reason } }); return { skipped: true as const }; }
    const now = new Date(); const minute = new Date(Math.floor(now.getTime() / 60000) * 60000);
    await tx.rateBucket.upsert({ where: { workspaceId_minute: { workspaceId: job.workspaceId, minute } }, create: { workspaceId: job.workspaceId, minute, expiresAt: new Date(minute.getTime() + 3600000) }, update: {} });
    const count = await tx.rateBucket.updateMany({ where: { workspaceId: job.workspaceId, minute, reserved: { lt: Math.min(env.MESSAGES_PER_MINUTE, job.workspace.messagesPerMinute) } }, data: { reserved: { increment: 1 } } });
    if (!count.count) { await tx.outboundMessage.update({ where: { id: job.id }, data: { nextAttemptAt: new Date(minute.getTime() + 60000) } }); return { skipped: true as const }; }
    const claimToken = randomUUID();
    const changed = await tx.outboundMessage.updateMany({ where: { id: job.id, status: "QUEUED" }, data: { status: "PROCESSING", claimToken, leaseExpiresAt: new Date(now.getTime() + env.CLAIM_LEASE_SECONDS * 1000) } });
    if (!changed.count) return { skipped: true as const };
    if (job.campaign?.status === "SCHEDULED") await tx.campaign.updateMany({ where: { id: job.campaign.id, status: "SCHEDULED" }, data: { status: "RUNNING", startedAt: now } });
    return { skipped: false as const, id: job.id, claimToken };
  });
}
async function begin(id: string, claimToken: string) {
  return serial(async tx => {
    const job = await tx.outboundMessage.findUnique({ where: { id }, include });
    if (!job || job.status !== "PROCESSING" || job.claimToken !== claimToken) return null;
    const paused = job.workspace.sendingState !== "ACTIVE" || job.campaign?.status === "PAUSED";
    if (paused) { await tx.outboundMessage.update({ where: { id }, data: { status: "QUEUED", claimToken: null, leaseExpiresAt: null } }); return null; }
    const reason = invalidReason(job);
    if (reason) { await tx.outboundMessage.update({ where: { id }, data: { status: "CANCELLED", lastError: reason, leaseExpiresAt: null } }); return null; }
    const number = job.attempts + 1;
    await tx.outboundMessage.update({ where: { id }, data: { attempts: number } });
    await tx.dispatchAttempt.create({ data: { messageId: id, number } });
    return { ...job, attempts: number, effectiveDryRun: job.dryRun || job.workspace.dryRun || env.DRY_RUN };
  });
}
async function processJob(id: string, claimToken: string) {
  const job = await begin(id, claimToken); if (!job) return;
  if (job.effectiveDryRun) {
    await serial(async tx => {
      await tx.outboundMessage.updateMany({ where: { id, claimToken, status: "PROCESSING" }, data: { status: "SIMULATED", leaseExpiresAt: null, lastError: null } });
      await tx.dispatchAttempt.update({ where: { messageId_number: { messageId: id, number: job.attempts } }, data: { outcome: "SIMULATED", finishedAt: new Date() } });
    }); return;
  }
  try {
    requireMeta();
    if (job.workspace.metaPhoneNumberId !== env.META_PHONE_NUMBER_ID) throw new MetaError(403, 200, null, false);
    const providerId = await sendMeta(job.payload);
    await serial(async tx => {
      // A receipt may already have arrived; it will also be replayed from durable events.
      await tx.outboundMessage.updateMany({ where: { id, claimToken, status: { in: ["PROCESSING", "UNKNOWN"] } }, data: { status: "ACCEPTED", providerMessageId: providerId, acceptedAt: new Date(), leaseExpiresAt: null, lastError: null, lastErrorCode: null } });
      await tx.dispatchAttempt.update({ where: { messageId_number: { messageId: id, number: job.attempts } }, data: { outcome: "ACCEPTED", providerId, httpStatus: 200, finishedAt: new Date() } });
    });
  } catch (error) {
    const meta = error instanceof MetaError ? error : new MetaError(0, 0, null, true);
    const policy = failurePolicy(meta); const retry = policy.retry && job.attempts < env.MAX_ATTEMPTS;
    const status = meta.uncertain ? "UNKNOWN" as const : retry ? "QUEUED" as const : "FAILED" as const;
    await serial(async tx => {
      await tx.outboundMessage.updateMany({ where: { id, claimToken, status: { in: ["PROCESSING", "UNKNOWN"] } }, data: { status, leaseExpiresAt: null, lastErrorCode: String(meta.metaCode || meta.httpStatus || "NETWORK"), lastError: meta.uncertain ? "Resultado incierto. Revisa Meta antes de crear otro envío; no se reintentará automáticamente." : `Meta rechazó el intento con código ${meta.metaCode || meta.httpStatus}.`, ...(retry ? { nextAttemptAt: new Date(Date.now() + retryDelay(job.attempts) * 1000) } : {}), ...(status === "FAILED" ? { failedAt: new Date() } : {}) } });
      await tx.dispatchAttempt.update({ where: { messageId_number: { messageId: id, number: job.attempts } }, data: { outcome: meta.uncertain ? "UNKNOWN" : retry ? "RETRYABLE" : "FAILED", httpStatus: meta.httpStatus || null, errorCode: String(meta.metaCode || "NETWORK"), errorSubcode: meta.subcode === null ? null : String(meta.subcode), errorMessage: meta.message, finishedAt: new Date() } });
      if (policy.pause) { await tx.workspace.update({ where: { id: job.workspaceId }, data: { sendingState: policy.pause, pausedAt: new Date(), pauseReason: meta.message } }); await tx.auditEvent.create({ data: { workspaceId: job.workspaceId, action: "SENDING_AUTO_PAUSED", entityType: "workspace", entityId: job.workspaceId, details: { reason: policy.pause, code: meta.metaCode } } }); }
    });
  }
}
export async function runQueue() {
  const started = Date.now(); const token = randomUUID(); if (!await lease(token)) return { skipped: true, processed: 0 };
  let processed = 0;
  try {
    await db.outboundMessage.updateMany({ where: { status: "PROCESSING", leaseExpiresAt: { lte: new Date() }, attempts: 0 }, data: { status: "QUEUED", claimToken: null, leaseExpiresAt: null } });
    await db.outboundMessage.updateMany({ where: { status: "PROCESSING", leaseExpiresAt: { lte: new Date() }, attempts: { gt: 0 } }, data: { status: "UNKNOWN", lastError: "La ejecución se interrumpió. No se reintentará un envío sin confirmar.", leaseExpiresAt: null } });
    await processPendingWebhooks(10);
    const spaces = await db.workspace.findMany({ where: { sendingState: "ACTIVE", messages: { some: { status: "QUEUED", nextAttemptAt: { lte: new Date() } } } }, take: 50 }); const allowed: string[] = [];
    for (const space of spaces) {
      const hasReal = !env.DRY_RUN && !space.dryRun && await db.outboundMessage.count({ where: { workspaceId: space.id, dryRun: false, status: "QUEUED", nextAttemptAt: { lte: new Date() } } }) > 0;
      if (!hasReal) { allowed.push(space.id); continue; }
      if (Date.now() - started > env.QUEUE_BUDGET_MS - 14000) break;
      try {
        await verifyMeta(space.id);
        const stale = await db.template.findMany({ where: { workspaceId: space.id, syncedAt: { lt: new Date(Date.now() - 600000) }, campaigns: { some: { messages: { some: { status: "QUEUED", dryRun: false, nextAttemptAt: { lte: new Date() } } } } } }, select: { id: true }, take: env.QUEUE_BATCH_SIZE });
        for (const template of stale) {
          if (Date.now() - started > env.QUEUE_BUDGET_MS - 14000) break;
          await refreshTemplate(space.id, template.id);
        }
        allowed.push(space.id);
      } catch (error) {
        const policy = error instanceof MetaError ? failurePolicy(error) : null;
        if (policy?.pause) await db.workspace.update({ where: { id: space.id }, data: { sendingState: policy.pause, pauseReason: error instanceof MetaError ? error.message : "No se pudo verificar Meta.", pausedAt: new Date() } });
      }
    }
    for (let i = 0; i < env.QUEUE_BATCH_SIZE && Date.now() - started < env.QUEUE_BUDGET_MS - 7500; i++) {
      const job = await claim(allowed); if (!job) break;
      if (!job.skipped) { await processJob(job.id, job.claimToken); processed++; }
    }
    await processPendingWebhooks(10);
    const campaigns = await db.campaign.findMany({ where: { status: "RUNNING", enrollmentCompleted: true, messages: { none: { status: { in: ["QUEUED", "PROCESSING"] } } } }, select: { id: true }, take: 100 });
    if (campaigns.length) await db.campaign.updateMany({ where: { id: { in: campaigns.map(c => c.id) }, status: "RUNNING" }, data: { status: "COMPLETED", completedAt: new Date() } });
    await db.session.deleteMany({ where: { expiresAt: { lt: new Date() } } });
    await db.rateBucket.deleteMany({ where: { expiresAt: { lt: new Date() } } });
    return { skipped: false, processed };
  } finally { await db.workerLease.updateMany({ where: { name: "queue", token }, data: { expiresAt: new Date() } }); }
}
