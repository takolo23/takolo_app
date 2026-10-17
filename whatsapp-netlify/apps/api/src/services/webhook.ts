import { z } from "zod";
import { db, serial, Prisma, type Tx } from "../config/db.js";
import { env } from "../config/env.js";
import { hash } from "./security.js";
import { normalizePhone } from "./phones.js";
import { failurePolicy, MetaError } from "./meta.js";
const timestampSchema = z.string().regex(/^\d{9,13}$/).transform(v => new Date(Number(v) * 1000)).refine(v => Number.isFinite(v.getTime()) && v.getTime() <= Date.now() + 300000 && v.getTime() >= 1262304000000, "La fecha del evento no es válida.");
const incomingSchema = z.object({ id: z.string().min(1).max(256), from: z.string().regex(/^\d{7,15}$/), timestamp: timestampSchema, type: z.string().max(30), text: z.object({ body: z.string().max(65536) }).optional() }).passthrough();
const statusSchema = z.object({ id: z.string().min(1).max(256), status: z.enum(["sent", "delivered", "read", "failed"]), timestamp: timestampSchema, recipient_id: z.string().optional(), errors: z.array(z.object({ code: z.number().int(), title: z.string().optional() }).passthrough()).max(10).optional() }).passthrough();
const payloadSchema = z.object({ object: z.literal("whatsapp_business_account"), entry: z.array(z.object({ id: z.string().max(64), changes: z.array(z.object({ field: z.string().max(100), value: z.record(z.unknown()) })).max(20) })).max(20) });
export const normalizedCommand = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().toUpperCase().replace(/[.!?]+$/g, "");
export async function storeWebhook(payload: unknown) {
  const parsed = payloadSchema.parse(payload);
  const events: { workspaceId: string; deduplicationKey: string; providerMessageId: string | null; type: string; payload: Prisma.InputJsonValue }[] = [];
  for (const entry of parsed.entry) for (const change of entry.changes) {
    const metadata = z.object({ phone_number_id: z.string() }).safeParse(change.value.metadata);
    if (change.field === "messages" && metadata.success) {
      const workspace = await db.workspace.findFirst({ where: { metaPhoneNumberId: metadata.data.phone_number_id, metaBusinessAccountId: entry.id } });
      if (!workspace) continue;
      const messages = z.array(z.unknown()).max(100).parse(change.value.messages ?? []); const statuses = z.array(z.unknown()).max(100).parse(change.value.statuses ?? []);
      for (const item of messages) { const data = incomingSchema.parse(item); events.push({ workspaceId: workspace.id, deduplicationKey: hash(`${workspace.id}:inbound:${data.id}`), providerMessageId: data.id, type: "inbound", payload: item as Prisma.InputJsonValue }); }
      for (const item of statuses) { const data = statusSchema.parse(item); events.push({ workspaceId: workspace.id, deduplicationKey: hash(`${workspace.id}:status:${data.id}:${data.status}:${data.timestamp.toISOString()}`), providerMessageId: data.id, type: "status", payload: item as Prisma.InputJsonValue }); }
    } else if (["phone_number_quality_update", "message_template_status_update"].includes(change.field)) {
      const spaces = await db.workspace.findMany({ where: { metaBusinessAccountId: entry.id }, take: 100 });
      for (const space of spaces) events.push({ workspaceId: space.id, deduplicationKey: hash(`${space.id}:${change.field}:${JSON.stringify(change.value)}`), providerMessageId: null, type: change.field, payload: change.value as Prisma.InputJsonValue });
    }
  }
  if (events.length > 100) throw new Error("El webhook contiene demasiados eventos.");
  if (events.length) await db.webhookEvent.createMany({ data: events, skipDuplicates: true });
  // Consent withdrawals are committed before acknowledging the webhook. No network sends here.
  for (const event of events.filter(e => e.type === "inbound")) {
    const stored = await db.webhookEvent.findUniqueOrThrow({ where: { deduplicationKey: event.deduplicationKey } });
    if (!stored.processedAt) await processEvent(stored.id);
  }
  return { stored: events.length };
}
async function incoming(tx: Tx, workspaceId: string, payload: unknown) {
  const message = incomingSchema.parse(payload); const phoneE164 = normalizePhone(`+${message.from}`);
  let contact = await tx.contact.upsert({ where: { workspaceId_phoneE164: { workspaceId, phoneE164 } }, create: { workspaceId, phoneE164, name: phoneE164 }, update: {} });
  await tx.contact.updateMany({ where: { id: contact.id, workspaceId, OR: [{ lastInboundAt: null }, { lastInboundAt: { lt: message.timestamp } }] }, data: { lastInboundAt: message.timestamp } });
  const text = message.type === "text" ? message.text?.body ?? "" : "";
  const inbound = await tx.inboundMessage.upsert({ where: { providerMessageId: message.id }, create: { workspaceId, contactId: contact.id, providerMessageId: message.id, type: message.type, text: text || null, occurredAt: message.timestamp }, update: {} });
  if (inbound.workspaceId !== workspaceId || inbound.contactId !== contact.id) throw new Error("El identificador entrante pertenece a otro contacto.");
  const command = normalizedCommand(text);
  if (["BAJA", "STOP"].includes(command)) {
    contact = await tx.contact.update({ where: { id: contact.id }, data: { consentGranted: false, optedOutAt: new Date() } });
    await tx.consentEvent.create({ data: { workspaceId, contactId: contact.id, action: "WITHDRAWN", occurredAt: message.timestamp, source: `WhatsApp: ${command}` } });
    await tx.outboundMessage.updateMany({ where: { workspaceId, contactId: contact.id, status: "QUEUED" }, data: { status: "CANCELLED", lastError: "Baja recibida por WhatsApp." } });
    await tx.auditEvent.create({ data: { workspaceId, action: "CONTACT_OPTED_OUT", entityType: "contact", entityId: contact.id } }); return;
  }
  if (!["HOLA", "MENU"].includes(command) || !contact.consentGranted || contact.optedOutAt || message.timestamp.getTime() + 86400000 <= Date.now()) return;
  const config = await tx.botConfig.findUnique({ where: { workspaceId } }); if (!config?.enabled) return;
  const previous = await tx.outboundMessage.findFirst({ where: { workspaceId, contactId: contact.id, kind: "BOT_REPLY", createdAt: { gt: new Date(Date.now() - config.cooldownSecs * 1000) }, status: { notIn: ["CANCELLED", "FAILED"] } } }); if (previous) return;
  const workspace = await tx.workspace.findUniqueOrThrow({ where: { id: workspaceId } });
  await tx.outboundMessage.createMany({ skipDuplicates: true, data: [{ workspaceId, contactId: contact.id, sourceInboundMessageId: inbound.id, idempotencyKey: `reply:${inbound.id}`, kind: "BOT_REPLY", phoneE164, dryRun: env.DRY_RUN || workspace.dryRun, expiresAt: new Date(message.timestamp.getTime() + 86400000), payload: { messaging_product: "whatsapp", recipient_type: "individual", to: phoneE164.slice(1), type: "text", text: { body: config.greetingText } } }] });
}
const ranks: Record<string, number> = { ACCEPTED: 0, SENT: 1, DELIVERED: 2, READ: 3 };
async function receipt(tx: Tx, workspaceId: string, payload: unknown) {
  const status = statusSchema.parse(payload); const message = await tx.outboundMessage.findFirst({ where: { workspaceId, providerMessageId: status.id } });
  if (!message) return false;
  if (status.recipient_id && normalizePhone(`+${status.recipient_id}`) !== message.phoneE164) return true;
  const next = status.status.toUpperCase() as "SENT" | "DELIVERED" | "READ" | "FAILED";
  const errorCode = status.errors?.[0]?.code;
  if (next === "FAILED" && (ranks[message.status] ?? -1) >= 2) return true;
  if (next !== "FAILED" && (ranks[message.status] ?? -1) > (ranks[next] ?? -1)) return true;
  if (next === "SENT" && message.status === "FAILED" && message.failedAt && status.timestamp <= message.failedAt) return true;
  await tx.outboundMessage.update({ where: { id: message.id }, data: { status: next, ...(next === "SENT" ? { sentAt: status.timestamp } : next === "DELIVERED" ? { deliveredAt: status.timestamp } : next === "READ" ? { readAt: status.timestamp, deliveredAt: message.deliveredAt ?? status.timestamp } : { failedAt: status.timestamp, lastErrorCode: String(errorCode ?? "DELIVERY_FAILED"), lastError: "Meta notificó que el mensaje no se entregó." }) } });
  if (errorCode) {
    const policy = failurePolicy(new MetaError(400, errorCode, null, false));
    if (policy.pause) await tx.workspace.update({ where: { id: workspaceId }, data: { sendingState: policy.pause, pauseReason: `Meta notificó el código ${errorCode}.`, pausedAt: new Date() } });
  }
  return true;
}
export async function processEvent(id: string) {
  return serial(async tx => {
    const event = await tx.webhookEvent.findUnique({ where: { id } }); if (!event || event.processedAt) return;
    if (event.type === "inbound") await incoming(tx, event.workspaceId, event.payload);
    else if (event.type === "status") { if (!await receipt(tx, event.workspaceId, event.payload)) { await tx.webhookEvent.update({ where: { id }, data: { attempts: { increment: 1 }, nextAttemptAt: new Date(Date.now() + 60000) } }); return; } }
    else if (event.type === "phone_number_quality_update") {
      const value = z.object({ phone_number_id: z.string().optional(), quality_rating: z.string().optional(), event: z.string().optional() }).passthrough().parse(event.payload);
      const space = await tx.workspace.findUniqueOrThrow({ where: { id: event.workspaceId } });
      if (value.phone_number_id === space.metaPhoneNumberId && ["RED", "LOW", "FLAGGED"].includes(value.quality_rating ?? value.event ?? "")) await tx.workspace.update({ where: { id: space.id }, data: { sendingState: "LOW_QUALITY", pauseReason: "Meta notificó calidad baja.", pausedAt: new Date() } });
    } else if (event.type === "message_template_status_update") {
      const value = z.object({ message_template_id: z.union([z.string(), z.number()]), event: z.string() }).passthrough().parse(event.payload);
      const status = ["APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED"].includes(value.event) ? value.event as "APPROVED" | "PENDING" | "REJECTED" | "PAUSED" | "DISABLED" : "UNKNOWN";
      await tx.template.updateMany({ where: { workspaceId: event.workspaceId, metaId: String(value.message_template_id) }, data: { status } });
    }
    await tx.webhookEvent.update({ where: { id }, data: { processedAt: new Date(), lastError: null } });
  });
}
export async function processPendingWebhooks(limit = 20) {
  const events = await db.webhookEvent.findMany({ where: { processedAt: null, nextAttemptAt: { lte: new Date() }, attempts: { lt: 20 } }, take: limit, orderBy: { receivedAt: "asc" } });
  for (const event of events) try { await processEvent(event.id); } catch { await db.webhookEvent.update({ where: { id: event.id }, data: { attempts: { increment: 1 }, nextAttemptAt: new Date(Date.now() + 300000), lastError: "No se pudo procesar el evento; se volverá a intentar." } }); }
}
