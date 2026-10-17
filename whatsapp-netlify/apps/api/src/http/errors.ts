import type { ErrorRequestHandler, RequestHandler } from "express";
import { ZodError } from "zod";
import { Prisma } from "../config/db.js";
import { ConfigurationError } from "../config/env.js";
export class AppError extends Error { constructor(public status: number, message: string, public code = "REQUEST_ERROR") { super(message); } }
export const asyncRoute = (fn: RequestHandler): RequestHandler => (req, res, next) => { Promise.resolve(fn(req, res, next)).catch(next); };
export const errorHandler: ErrorRequestHandler = (error: unknown, req, res, _next) => {
  if (error instanceof ZodError) { res.status(400).json({ error: "Revisa los datos enviados.", code: "VALIDATION", details: error.issues.map(i => ({ field: i.path.join("."), message: i.message })) }); return; }
  if (error instanceof AppError) { res.status(error.status).json({ error: error.message, code: error.code }); return; }
  if (error instanceof ConfigurationError) { res.status(503).json({ error: error.message, code: "NOT_CONFIGURED" }); return; }
  if (error instanceof Prisma.PrismaClientKnownRequestError && ["P2002", "P2025", "P2003"].includes(error.code)) { res.status(409).json({ error: "El registro ya existe, cambió o tiene datos relacionados. Actualiza la pantalla.", code: "CONFLICT" }); return; }
  if (typeof error === "object" && error !== null && "type" in error && error.type === "entity.too.large") { res.status(413).json({ error: "El archivo o solicitud supera el tamaño permitido.", code: "TOO_LARGE" }); return; }
  if (error instanceof SyntaxError) { res.status(400).json({ error: "El contenido JSON no es válido.", code: "INVALID_JSON" }); return; }
  console.error(JSON.stringify({ level: "error", requestId: res.locals.requestId, path: req.path, type: error instanceof Error ? error.name : "UnknownError" }));
  res.status(500).json({ error: "No se pudo completar la operación. Inténtalo de nuevo o consulta la configuración del servidor.", code: "INTERNAL", requestId: res.locals.requestId });
};
