import { Router } from "express";
import { loginSchema } from "@takolo/shared";
import { db, serial } from "../config/db.js";
import { env } from "../config/env.js";
import { asyncRoute, AppError } from "../http/errors.js";
import { authenticate, cookieName, cookieOptions, identity } from "../middleware/auth.js";
import { checkPassword, hash, privateHash, token, csrfFor, hashPassword } from "../services/security.js";
import { bootstrap } from "../services/bootstrap.js";
export const authRoutes = Router();
let dummyHash: Promise<string> | undefined;
authRoutes.post("/login", asyncRoute(async (req, res) => {
  const input = loginSchema.parse(req.body); await bootstrap();
  const key = privateHash(`login:${input.email}`); const now = new Date();
  await serial(async tx => {
    const throttle = await tx.loginThrottle.findUnique({ where: { key } });
    if (throttle?.blockedUntil && throttle.blockedUntil > now) throw new AppError(429, "Demasiados intentos. Espera quince minutos.", "LOGIN_LIMIT");
    const reset = !throttle || throttle.windowEndsAt <= now;
    const attempts = reset ? 1 : throttle.attempts + 1;
    await tx.loginThrottle.upsert({ where: { key }, create: { key, attempts, windowEndsAt: new Date(now.getTime() + 900000) }, update: { attempts, windowEndsAt: reset ? new Date(now.getTime() + 900000) : throttle.windowEndsAt, blockedUntil: attempts >= 6 ? new Date(now.getTime() + 900000) : null } });
    if (attempts > 6) throw new AppError(429, "Demasiados intentos. Espera quince minutos.");
  });
  const user = await db.user.findUnique({ where: { email: input.email }, include: { memberships: true } });
  dummyHash ??= hashPassword(token());
  const valid = await checkPassword(input.password, user?.passwordHash ?? await dummyHash);
  if (!user || !user.active || !valid || !user.memberships.length) throw new AppError(401, "El correo o la contraseña no son correctos.", "BAD_LOGIN");
  const raw = token(); const tokenHash = privateHash(raw); const csrfToken = csrfFor(tokenHash);
  await db.session.create({ data: { userId: user.id, tokenHash, csrfHash: hash(csrfToken), expiresAt: new Date(Date.now() + env.SESSION_TTL_HOURS * 3600000) } });
  await db.loginThrottle.deleteMany({ where: { key } });
  res.cookie(cookieName, raw, { ...cookieOptions, maxAge: env.SESSION_TTL_HOURS * 3600000 }).json({ user: { id: user.id, email: user.email, name: user.name }, memberships: user.memberships, csrfToken });
}));
authRoutes.get("/me", authenticate, asyncRoute(async (req, res) => {
  const actor = identity(req); const user = await db.user.findUniqueOrThrow({ where: { id: actor.userId }, select: { id: true, name: true, email: true, memberships: { include: { workspace: { select: { id: true, name: true } } } } } });
  res.json({ user, workspaceId: actor.workspaceId, role: actor.role, csrfToken: actor.csrfToken });
}));
authRoutes.post("/logout", authenticate, asyncRoute(async (req, res) => { await db.session.deleteMany({ where: { id: identity(req).sessionId } }); res.clearCookie(cookieName, cookieOptions).json({ ok: true }); }));
