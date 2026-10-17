import { Router } from "express";
import { z } from "zod";
import { botSchema, settingsSchema, userSchema } from "@takolo/shared";
import { db, serial } from "../config/db.js";
import { env, requireMeta } from "../config/env.js";
import { identity, admin } from "../middleware/auth.js";
import { asyncRoute, AppError } from "../http/errors.js";
import { hashPassword } from "../services/security.js";
import { verifyMeta, MetaError, failurePolicy } from "../services/meta.js";
import { syncTemplates } from "../services/templates.js";
import { audit } from "../services/audit.js";
export const settingsRoutes = Router();
settingsRoutes.get("/", asyncRoute(async (req, res) => {
  const actor = identity(req); const workspace = await db.workspace.findUniqueOrThrow({ where: { id: actor.workspaceId }, include: { botConfig: true } });
  res.json({ workspace, globalDryRun: env.DRY_RUN, maximumPerMinute: env.MESSAGES_PER_MINUTE, webhookUrl: `${new URL(env.APP_URL).origin}/api/webhooks/whatsapp`, meta: { tokenConfigured: Boolean(env.META_ACCESS_TOKEN), appSecretConfigured: Boolean(env.META_APP_SECRET), verifyTokenConfigured: Boolean(env.META_VERIFY_TOKEN), phoneIdConfigured: Boolean(env.META_PHONE_NUMBER_ID), businessIdConfigured: Boolean(env.META_BUSINESS_ACCOUNT_ID), graphVersion: env.META_GRAPH_VERSION } });
}));
settingsRoutes.put("/", admin, asyncRoute(async (req, res) => {
  const input = settingsSchema.parse(req.body); const actor = identity(req);
  if (input.messagesPerMinute > env.MESSAGES_PER_MINUTE) throw new AppError(400, `El límite del servidor es ${env.MESSAGES_PER_MINUTE} mensajes por minuto.`);
  if (!input.dryRun) { requireMeta(); if (env.DRY_RUN) throw new AppError(409, "Primero desactiva DRY_RUN en las variables privadas del alojamiento. Las simulaciones existentes seguirán siendo pruebas."); await verifyMeta(actor.workspaceId); }
  const workspace = await serial(async tx => { const updated = await tx.workspace.update({ where: { id: actor.workspaceId }, data: { ...input, version: { increment: 1 } } }); await audit(actor, "SETTINGS_UPDATED", "workspace", actor.workspaceId, { dryRun: input.dryRun, messagesPerMinute: input.messagesPerMinute }, tx); return updated; }); res.json(workspace);
}));
settingsRoutes.put("/bot", admin, asyncRoute(async (req, res) => { const input = botSchema.parse(req.body); const actor = identity(req); const config = await serial(async tx => { const updated = await tx.botConfig.upsert({ where: { workspaceId: actor.workspaceId }, create: { workspaceId: actor.workspaceId, ...input }, update: input }); await audit(actor, "BOT_UPDATED", "bot", actor.workspaceId, { enabled: input.enabled }, tx); return updated; }); res.json(config); }));
settingsRoutes.post("/verify-meta", admin, asyncRoute(async (req, res) => { const actor = identity(req); try { const result = await verifyMeta(actor.workspaceId); await audit(actor, "META_VERIFIED", "workspace", actor.workspaceId); res.json(result); } catch (error) { if (error instanceof MetaError) { const policy = failurePolicy(error); if (policy.pause) await db.workspace.update({ where: { id: actor.workspaceId }, data: { sendingState: policy.pause, pauseReason: error.message, pausedAt: new Date() } }); throw new AppError(502, `No se pudo verificar Meta. Código ${error.metaCode || error.httpStatus}. Revisa las credenciales y permisos.`); } throw error; } }));
for (const action of ["pause", "resume"] as const) settingsRoutes.post(`/${action}`, admin, asyncRoute(async (req, res) => {
  z.object({}).strict().parse(req.body); const actor = identity(req); const current = await db.workspace.findUniqueOrThrow({ where: { id: actor.workspaceId } });
  if (action === "resume" && !env.DRY_RUN && !current.dryRun) { await verifyMeta(actor.workspaceId); await syncTemplates(actor.workspaceId); }
  const updated = await serial(async tx => { const result = await tx.workspace.update({ where: { id: actor.workspaceId }, data: { sendingState: action === "resume" ? "ACTIVE" : "PAUSED", pauseReason: action === "pause" ? "Pausado por la administración." : null, pausedAt: action === "pause" ? new Date() : null, version: { increment: 1 } } }); await audit(actor, `WORKSPACE_${action.toUpperCase()}`, "workspace", actor.workspaceId, {}, tx); return result; }); res.json(updated);
}));
settingsRoutes.get("/users", admin, asyncRoute(async (req, res) => { const members = await db.membership.findMany({ where: { workspaceId: identity(req).workspaceId }, include: { user: { select: { id: true, name: true, email: true, active: true } } } }); res.json(members); }));
settingsRoutes.post("/users", admin, asyncRoute(async (req, res) => { const input = userSchema.parse(req.body); const actor = identity(req); const passwordHash = await hashPassword(input.password); const user = await serial(async tx => { const created = await tx.user.create({ data: { email: input.email, name: input.name, passwordHash, memberships: { create: { workspaceId: actor.workspaceId, role: input.role } } }, select: { id: true, name: true, email: true } }); await audit(actor, "USER_CREATED", "user", created.id, { role: input.role }, tx); return created; }); res.status(201).json(user); }));
