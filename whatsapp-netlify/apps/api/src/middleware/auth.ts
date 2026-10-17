import type { RequestHandler, Request } from "express";
import type { Role } from "../generated/prisma/client.js";
import { db } from "../config/db.js";
import { env } from "../config/env.js";
import { AppError, asyncRoute } from "../http/errors.js";
import { csrfFor, equal, hash, privateHash } from "../services/security.js";
export const cookieName = env.NODE_ENV === "production" ? "__Host-takolo" : "takolo_session";
export const cookieOptions = { httpOnly: true, secure: env.NODE_ENV === "production", sameSite: "strict" as const, path: "/" };
export interface Identity { userId: string; workspaceId: string; role: Role; sessionId: string; csrfToken: string; }
export const identity = (req: Request) => (req as Request & { identity: Identity }).identity;
export const requireOrigin: RequestHandler = (req, _res, next) => {
  if (["GET", "HEAD", "OPTIONS"].includes(req.method)) { next(); return; }
  if (req.get("origin") !== new URL(env.APP_URL).origin) { next(new AppError(403, "La solicitud debe venir de la aplicación.", "ORIGIN")); return; }
  next();
};
export const authenticate = asyncRoute(async (req, _res, next) => {
  const raw = typeof req.cookies?.[cookieName] === "string" ? req.cookies[cookieName] as string : "";
  if (!/^[a-f0-9]{64}$/.test(raw)) throw new AppError(401, "Inicia sesión para continuar.", "UNAUTHENTICATED");
  const session = await db.session.findUnique({ where: { tokenHash: privateHash(raw) }, include: { user: { include: { memberships: { orderBy: { workspaceId: "asc" } } } } } });
  if (!session || session.expiresAt <= new Date() || !session.user.active) throw new AppError(401, "Tu sesión terminó. Vuelve a iniciar sesión.", "UNAUTHENTICATED");
  const requested = req.get("x-workspace-id");
  const membership = requested ? session.user.memberships.find(m => m.workspaceId === requested) : session.user.memberships[0];
  if (!membership) throw new AppError(403, "No tienes acceso a este espacio.");
  const csrf = csrfFor(session.tokenHash);
  if (!["GET", "HEAD", "OPTIONS"].includes(req.method) && (!equal(req.get("x-csrf-token") ?? "", csrf) || !equal(hash(csrf), session.csrfHash))) throw new AppError(403, "Actualiza la página antes de guardar.", "CSRF");
  (req as Request & { identity: Identity }).identity = { userId: session.userId, workspaceId: membership.workspaceId, role: membership.role, sessionId: session.id, csrfToken: csrf };
  next();
});
export const admin: RequestHandler = (req, _res, next) => identity(req).role === "ADMIN" ? next() : next(new AppError(403, "Esta acción requiere una cuenta administradora."));
