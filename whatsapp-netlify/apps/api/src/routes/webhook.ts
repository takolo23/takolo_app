import { Router, raw } from "express";
import { z } from "zod";
import { env } from "../config/env.js";
import { asyncRoute, AppError } from "../http/errors.js";
import { verifySignature, equal } from "../services/security.js";
import { storeWebhook } from "../services/webhook.js";
export const webhookRoutes = Router();
webhookRoutes.get("/", (req, res, next) => {
  const query = z.object({ "hub.mode": z.literal("subscribe"), "hub.verify_token": z.string().max(500), "hub.challenge": z.string().regex(/^\d{1,100}$/) }).safeParse(req.query);
  if (!env.META_VERIFY_TOKEN || !query.success || !equal(query.data["hub.verify_token"], env.META_VERIFY_TOKEN)) { next(new AppError(403, "No se pudo verificar el webhook.")); return; }
  res.type("text/plain").send(query.data["hub.challenge"]);
});
webhookRoutes.post("/", raw({ type: "application/json", limit: "1mb" }), asyncRoute(async (req, res) => {
  if (!Buffer.isBuffer(req.body) || !verifySignature(req.body, req.get("x-hub-signature-256") ?? "", env.META_APP_SECRET)) throw new AppError(401, "La firma del webhook no es válida.", "BAD_SIGNATURE");
  const result = await storeWebhook(JSON.parse(req.body.toString("utf8")) as unknown); res.json({ ok: true, ...result });
}));
