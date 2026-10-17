import { Router } from "express";
import { z } from "zod";
import { campaignSchema, variableMappingSchema, segmentFiltersSchema, launchSchema, paginationSchema, idSchema } from "@takolo/shared";
import { db, serial, Prisma } from "../config/db.js";
import { env, requireMeta } from "../config/env.js";
import { asyncRoute, AppError } from "../http/errors.js";
import { identity } from "../middleware/auth.js";
import { loadSegment, segmentWhere } from "../services/segments.js";
import { assertTemplate, mapVariables } from "../services/templates.js";
import { audit } from "../services/audit.js";
export const campaignRoutes = Router();
campaignRoutes.get("/", asyncRoute(async (req, res) => { const q = paginationSchema.parse(req.query); const where = { workspaceId: identity(req).workspaceId, name: { contains: q.search, mode: "insensitive" as const } }; const [total, campaigns] = await db.$transaction([db.campaign.count({ where }), db.campaign.findMany({ where, take: q.pageSize, skip: (q.page - 1) * q.pageSize, orderBy: { createdAt: "desc" }, include: { template: { select: { name: true, language: true } }, segment: { select: { name: true } } } })]); res.json({ campaigns, total, page: q.page, pageSize: q.pageSize }); }));
campaignRoutes.post("/preview", asyncRoute(async (req, res) => {
  const input = campaignSchema.omit({ name: true }).parse(req.body); const workspaceId = identity(req).workspaceId;
  const segment = await loadSegment(workspaceId, input.segmentId); const template = await db.template.findUnique({ where: { workspaceId_id: { workspaceId, id: input.templateId } } });
  if (!template) throw new AppError(404, "No se encontró la plantilla."); assertTemplate(template);
  const where = segmentWhere(workspaceId, segment.filters); const [total, contacts] = await db.$transaction([db.contact.count({ where }), db.contact.findMany({ where, take: 20, orderBy: { id: "asc" } })]);
  res.json({ total, previews: contacts.map(c => ({ contactId: c.id, name: c.name, phone: c.phoneE164, text: mapVariables(template.bodyText, input.variableMapping, c).preview })), requiresOptOut: template.category === "MARKETING" });
}));
campaignRoutes.post("/", asyncRoute(async (req, res) => { const input = campaignSchema.parse(req.body); const actor = identity(req); const campaign = await serial(async tx => { await loadSegment(actor.workspaceId, input.segmentId, tx); const template = await tx.template.findUnique({ where: { workspaceId_id: { workspaceId: actor.workspaceId, id: input.templateId } } }); if (!template) throw new AppError(404, "No se encontró la plantilla."); assertTemplate(template); const created = await tx.campaign.create({ data: { ...input, workspaceId: actor.workspaceId, createdBy: actor.userId } }); await audit(actor, "CAMPAIGN_CREATED", "campaign", created.id, {}, tx); return created; }); res.status(201).json(campaign); }));
campaignRoutes.put("/:id", asyncRoute(async (req, res) => {
  const id = idSchema.parse(req.params.id); const input = campaignSchema.parse(req.body); const actor = identity(req);
  const updated = await serial(async tx => {
    await loadSegment(actor.workspaceId, input.segmentId, tx);
    const template = await tx.template.findUnique({ where: { workspaceId_id: { workspaceId: actor.workspaceId, id: input.templateId } } });
    if (!template) throw new AppError(404, "No se encontró la plantilla."); assertTemplate(template);
    const current = await tx.campaign.findUnique({ where: { workspaceId_id: { workspaceId: actor.workspaceId, id } } });
    if (!current || current.status !== "DRAFT") throw new AppError(409, "Solo se pueden editar campañas en borrador.");
    const result = await tx.campaign.update({ where: { workspaceId_id: { workspaceId: actor.workspaceId, id } }, data: { ...input, version: { increment: 1 } } });
    await audit(actor, "CAMPAIGN_UPDATED", "campaign", id, {}, tx); return result;
  }); res.json(updated);
}));
campaignRoutes.post("/:id/launch", asyncRoute(async (req, res) => {
  const id = idSchema.parse(req.params.id); const input = launchSchema.parse(req.body); const actor = identity(req); const now = new Date();
  const scheduled = input.scheduledAt ? new Date(input.scheduledAt) : now;
  if (input.scheduledAt && (scheduled <= now || scheduled.getTime() > now.getTime() + 90 * 86400000)) throw new AppError(400, "La programación debe ser futura y estar dentro de los próximos 90 días.");
  const result = await serial(async tx => {
    const campaign = await tx.campaign.findUnique({ where: { workspaceId_id: { workspaceId: actor.workspaceId, id } }, include: { template: true, segment: true, workspace: true } });
    if (!campaign) throw new AppError(404, "No se encontró la campaña.");
    if (campaign.status !== "DRAFT") throw new AppError(409, "Esta campaña ya se lanzó. No se duplicarán sus mensajes.");
    if (campaign.workspace.sendingState !== "ACTIVE") throw new AppError(409, "Activa el procesamiento del espacio en Configuración antes de lanzar la campaña.");
    assertTemplate(campaign.template); const dryRun = env.DRY_RUN || campaign.workspace.dryRun;
    if (!dryRun) { requireMeta(); if (!input.confirmLive) throw new AppError(400, "Confirma expresamente el envío real."); if (campaign.workspace.metaPhoneNumberId !== env.META_PHONE_NUMBER_ID) throw new AppError(409, "Verifica el número oficial del espacio."); }
    const filters = segmentFiltersSchema.parse(campaign.segment.filters); const contacts = await tx.contact.findMany({ where: segmentWhere(actor.workspaceId, filters), take: env.CSV_MAX_ROWS + 1, orderBy: { id: "asc" } });
    if (!contacts.length) throw new AppError(400, "El segmento no tiene contactos con consentimiento vigente.");
    if (contacts.length > env.CSV_MAX_ROWS) throw new AppError(400, "Divide este segmento: una campaña admite hasta diez mil contactos.");
    const mapping = variableMappingSchema.parse(campaign.variableMapping);
    const jobs = contacts.map(contact => {
      const rendered = mapVariables(campaign.template.bodyText, mapping, contact);
      const payload = { messaging_product: "whatsapp", recipient_type: "individual", to: contact.phoneE164.slice(1), type: "template", template: { name: campaign.template.name, language: { code: campaign.template.language }, ...(rendered.values.length ? { components: [{ type: "body", parameters: rendered.values.map(text => ({ type: "text", text })) }] } : {}) } };
      return { workspaceId: actor.workspaceId, contactId: contact.id, campaignId: id, idempotencyKey: `campaign:${id}:${contact.id}`, kind: "TEMPLATE" as const, phoneE164: contact.phoneE164, payload, dryRun, nextAttemptAt: scheduled, expiresAt: new Date(scheduled.getTime() + env.MAX_MESSAGE_AGE_HOURS * 3600000) };
    });
    await tx.outboundMessage.createMany({ data: jobs, skipDuplicates: true });
    const updated = await tx.campaign.update({ where: { workspaceId_id: { workspaceId: actor.workspaceId, id } }, data: { status: input.scheduledAt ? "SCHEDULED" : "RUNNING", scheduledAt: scheduled, startedAt: input.scheduledAt ? null : now, dryRun, segmentSnapshot: filters, templateSnapshot: { metaId: campaign.template.metaId, name: campaign.template.name, language: campaign.template.language, body: campaign.template.bodyText, components: campaign.template.components as Prisma.InputJsonValue }, enrollmentCompleted: true, version: { increment: 1 } } });
    await audit(actor, "CAMPAIGN_LAUNCHED", "campaign", id, { recipients: jobs.length, dryRun, scheduledAt: scheduled.toISOString() }, tx); return { campaign: updated, recipients: jobs.length };
  }); res.json(result);
}));
for (const action of ["pause", "resume", "cancel"] as const) campaignRoutes.post(`/:id/${action}`, asyncRoute(async (req, res) => {
  const id = idSchema.parse(req.params.id); const actor = identity(req);
  const result = await serial(async tx => {
    const current = await tx.campaign.findUnique({ where: { workspaceId_id: { workspaceId: actor.workspaceId, id } } }); if (!current) throw new AppError(404, "No se encontró la campaña.");
    if (action === "pause" && !["RUNNING", "SCHEDULED"].includes(current.status) || action === "resume" && current.status !== "PAUSED" || action === "cancel" && ["COMPLETED", "CANCELLED"].includes(current.status)) throw new AppError(409, "La acción no corresponde al estado actual de la campaña.");
    const status = action === "pause" ? "PAUSED" : action === "cancel" ? "CANCELLED" : current.scheduledAt && current.scheduledAt > new Date() ? "SCHEDULED" : "RUNNING";
    const updated = await tx.campaign.update({ where: { workspaceId_id: { workspaceId: actor.workspaceId, id } }, data: { status, pausedAt: action === "pause" ? new Date() : null, cancelledAt: action === "cancel" ? new Date() : current.cancelledAt, version: { increment: 1 } } });
    if (action === "cancel") await tx.outboundMessage.updateMany({ where: { workspaceId: actor.workspaceId, campaignId: id, status: "QUEUED" }, data: { status: "CANCELLED", lastError: "La campaña fue cancelada." } });
    await audit(actor, `CAMPAIGN_${action.toUpperCase()}`, "campaign", id, {}, tx); return updated;
  }); res.json(result);
}));
campaignRoutes.get("/:id", asyncRoute(async (req, res) => {
  const id = idSchema.parse(req.params.id); const workspaceId = identity(req).workspaceId; const campaign = await db.campaign.findUnique({ where: { workspaceId_id: { workspaceId, id } }, include: { template: true, segment: true } }); if (!campaign) throw new AppError(404, "No se encontró la campaña.");
  const q = paginationSchema.parse(req.query); const where = { workspaceId, campaignId: id };
  const [states, total, messages, accepted, delivered, read, errors] = await db.$transaction([db.outboundMessage.groupBy({ by: ["status"], orderBy: { status: "asc" }, where, _count: { _all: true } }), db.outboundMessage.count({ where }), db.outboundMessage.findMany({ where, skip: (q.page - 1) * q.pageSize, take: q.pageSize, orderBy: { createdAt: "desc" }, include: { contact: { select: { name: true } } } }), db.outboundMessage.count({ where: { ...where, acceptedAt: { not: null } } }), db.outboundMessage.count({ where: { ...where, deliveredAt: { not: null } } }), db.outboundMessage.count({ where: { ...where, readAt: { not: null } } }), db.dispatchAttempt.groupBy({ by: ["errorCode"], orderBy: { errorCode: "asc" }, where: { errorCode: { not: null }, message: where }, _count: { _all: true } })]);
  res.json({ campaign, states, messages, total, metrics: { accepted, delivered, read, deliveryRate: accepted ? delivered / accepted : 0, readRate: accepted ? read / accepted : 0, errors }, page: q.page, pageSize: q.pageSize });
}));
