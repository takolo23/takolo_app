import { Router } from "express";
import { z } from "zod";
import { idSchema, paginationSchema } from "@takolo/shared";
import { db, serial, type Prisma } from "../config/db.js";
import { identity } from "../middleware/auth.js";
import { AppError, asyncRoute } from "../http/errors.js";
import { audit } from "../services/audit.js";
export const messageRoutes = Router();
messageRoutes.get("/", asyncRoute(async (req, res) => {
  const q = paginationSchema.extend({ campaignId: idSchema.optional(), status: z.enum(["QUEUED", "PROCESSING", "SIMULATED", "ACCEPTED", "SENT", "DELIVERED", "READ", "FAILED", "CANCELLED", "UNKNOWN"]).optional() }).parse(req.query);
  const where: Prisma.OutboundMessageWhereInput = { workspaceId: identity(req).workspaceId, ...(q.campaignId ? { campaignId: q.campaignId } : {}), ...(q.status ? { status: q.status } : {}), ...(q.search ? { contact: { name: { contains: q.search, mode: "insensitive" } } } : {}) };
  const [total, messages] = await db.$transaction([db.outboundMessage.count({ where }), db.outboundMessage.findMany({ where, take: q.pageSize, skip: (q.page - 1) * q.pageSize, orderBy: [{ createdAt: "desc" }, { id: "desc" }], include: { contact: { select: { name: true } }, campaign: { select: { id: true, name: true } } } })]);
  res.json({ total, messages, page: q.page, pageSize: q.pageSize });
}));
messageRoutes.get("/inbox", asyncRoute(async (req, res) => {
  const q = paginationSchema.extend({ contactId: idSchema.optional() }).parse(req.query);
  const where: Prisma.InboundMessageWhereInput = { workspaceId: identity(req).workspaceId, ...(q.contactId ? { contactId: q.contactId } : {}), ...(q.search ? { contact: { name: { contains: q.search, mode: "insensitive" } } } : {}) };
  const [total, messages] = await db.$transaction([db.inboundMessage.count({ where }), db.inboundMessage.findMany({ where, take: q.pageSize, skip: (q.page - 1) * q.pageSize, orderBy: [{ occurredAt: "desc" }, { id: "desc" }], include: { contact: { select: { id: true, name: true, phoneE164: true } } } })]);
  res.json({ total, messages, page: q.page, pageSize: q.pageSize });
}));
messageRoutes.get("/:id", asyncRoute(async (req, res) => {
  const id = idSchema.parse(req.params.id); const message = await db.outboundMessage.findFirst({ where: { workspaceId: identity(req).workspaceId, id }, include: { dispatchAttempts: { orderBy: { number: "asc" } }, contact: { select: { id: true, name: true } }, campaign: { select: { id: true, name: true } } } });
  if (!message) throw new AppError(404, "No se encontró el mensaje."); res.json(message);
}));
messageRoutes.post("/:id/cancel", asyncRoute(async (req, res) => {
  z.object({}).strict().parse(req.body); const id = idSchema.parse(req.params.id); const actor = identity(req);
  await serial(async tx => { const changed = await tx.outboundMessage.updateMany({ where: { workspaceId: actor.workspaceId, id, status: "QUEUED" }, data: { status: "CANCELLED", lastError: "Cancelado por un operador." } }); if (!changed.count) throw new AppError(409, "Solo se pueden cancelar mensajes que aún están en cola."); await audit(actor, "MESSAGE_CANCELLED", "message", id, {}, tx); }); res.json({ ok: true });
}));
