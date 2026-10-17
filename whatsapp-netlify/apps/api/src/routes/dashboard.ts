import { Router } from "express";
import { paginationSchema } from "@takolo/shared";
import { db } from "../config/db.js";
import { identity } from "../middleware/auth.js";
import { asyncRoute } from "../http/errors.js";
export const dashboardRoutes = Router();
dashboardRoutes.get("/", asyncRoute(async (req, res) => {
  const workspaceId = identity(req).workspaceId; const where = { workspaceId };
  const [contacts, eligible, campaigns, states, errors, accepted, delivered, read] = await db.$transaction([
    db.contact.count({ where }), db.contact.count({ where: { ...where, consentGranted: true, optedOutAt: null } }), db.campaign.groupBy({ by: ["status"], orderBy: { status: "asc" }, where, _count: { _all: true } }),
    db.outboundMessage.groupBy({ by: ["status"], orderBy: { status: "asc" }, where, _count: { _all: true } }), db.dispatchAttempt.groupBy({ by: ["errorCode"], orderBy: { errorCode: "asc" }, where: { message: { workspaceId }, errorCode: { not: null } }, _count: { _all: true } }),
    db.outboundMessage.count({ where: { ...where, acceptedAt: { not: null } } }), db.outboundMessage.count({ where: { ...where, deliveredAt: { not: null } } }), db.outboundMessage.count({ where: { ...where, readAt: { not: null } } }),
  ]);
  res.json({ contacts, eligible, campaigns, states, errors, accepted, delivered, read, deliveryRate: accepted ? delivered / accepted : 0, readRate: accepted ? read / accepted : 0 });
}));
dashboardRoutes.get("/audit", asyncRoute(async (req, res) => { const q = paginationSchema.parse(req.query); const where = { workspaceId: identity(req).workspaceId }; const [total, events] = await db.$transaction([db.auditEvent.count({ where }), db.auditEvent.findMany({ where, skip: (q.page - 1) * q.pageSize, take: q.pageSize, orderBy: [{ createdAt: "desc" }, { id: "desc" }] })]); res.json({ total, events, page: q.page, pageSize: q.pageSize }); }));
