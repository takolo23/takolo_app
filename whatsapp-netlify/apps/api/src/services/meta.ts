import { z } from "zod";
import { env, requireMeta } from "../config/env.js";
import { db } from "../config/db.js";
import { AppError } from "../http/errors.js";
export class MetaError extends Error {
  constructor(public httpStatus: number, public metaCode: number, public subcode: number | null, public uncertain: boolean) { super(`Meta respondió con el código ${metaCode || httpStatus}.`); }
}
export function failurePolicy(error: MetaError) {
  if (error.metaCode === 190 || error.httpStatus === 401) return { pause: "TOKEN_INVALID" as const, retry: false };
  if ([200, 368, 131031, 131042].includes(error.metaCode) || error.httpStatus === 403) return { pause: "ACCOUNT_RESTRICTED" as const, retry: false };
  if (error.metaCode === 131048) return { pause: "LOW_QUALITY" as const, retry: false };
  return { pause: null, retry: !error.uncertain && (error.httpStatus === 429 || [4, 17, 32, 613, 80007, 130429, 131056].includes(error.metaCode)) };
}
export function retryDelay(attempt: number, random = Math.random) { return Math.min(env.RETRY_MAX_SECONDS, env.RETRY_BASE_SECONDS * 2 ** Math.min(20, Math.max(0, attempt - 1))) * (0.75 + random() * 0.25); }
export async function metaRequest(path: string, method = "GET", body?: unknown): Promise<unknown> {
  try { requireMeta(); } catch { throw new AppError(503, "Falta configurar la conexión oficial de Meta en las variables privadas del servidor.", "META_NOT_CONFIGURED"); }
  if (!/^[0-9]+(?:\/[a-z_]+)?(?:\?[a-zA-Z0-9_%,=&.-]+)?$/.test(path)) throw new AppError(400, "La ruta de Meta no es válida.");
  let response: Response;
  try { response = await fetch(`https://graph.facebook.com/${env.META_GRAPH_VERSION}/${path}`, { method, headers: { Authorization: `Bearer ${env.META_ACCESS_TOKEN}`, "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(6500), redirect: "error" }); }
  catch { throw new MetaError(0, 0, null, method === "POST"); }
  let data: unknown;
  try { data = await response.json(); } catch { throw new MetaError(response.status, 0, null, method === "POST"); }
  if (!response.ok) {
    const error = z.object({ error: z.object({ code: z.number().optional(), error_subcode: z.number().optional() }).passthrough() }).safeParse(data);
    throw new MetaError(response.status, error.success ? error.data.error.code ?? 0 : 0, error.success ? error.data.error.error_subcode ?? null : null, method === "POST" && (response.status >= 500 || response.status === 408));
  }
  return data;
}
export async function sendMeta(payload: unknown) {
  const response = await metaRequest(`${env.META_PHONE_NUMBER_ID}/messages`, "POST", payload);
  const parsed = z.object({ messages: z.array(z.object({ id: z.string().min(1).max(256) })).min(1) }).safeParse(response);
  if (!parsed.success) throw new MetaError(200, 0, null, true);
  return parsed.data.messages[0]!.id;
}
export async function verifyMeta(workspaceId: string) {
  requireMeta();
  const current = await db.workspace.findUniqueOrThrow({ where: { id: workspaceId } });
  if (current.metaPhoneNumberId && current.metaPhoneNumberId !== env.META_PHONE_NUMBER_ID) throw new AppError(409, "Este espacio está asociado a otro número de Meta.");
  const number = z.object({ id: z.string(), display_phone_number: z.string().optional(), quality_rating: z.string().optional() }).parse(await metaRequest(`${env.META_PHONE_NUMBER_ID}?fields=id,display_phone_number,quality_rating`));
  if (number.id !== env.META_PHONE_NUMBER_ID) throw new AppError(409, "Meta devolvió un número diferente al configurado.");
  if (["RED", "LOW"].includes(number.quality_rating ?? "")) { await db.workspace.update({ where: { id: workspaceId }, data: { sendingState: "LOW_QUALITY", pauseReason: "Meta informa calidad baja.", pausedAt: new Date() } }); throw new AppError(409, "Meta informa calidad baja. Los envíos permanecen pausados."); }
  await db.workspace.update({ where: { id: workspaceId }, data: { metaPhoneNumberId: env.META_PHONE_NUMBER_ID, metaBusinessAccountId: env.META_BUSINESS_ACCOUNT_ID } });
  return { phoneNumberId: number.id, displayPhone: number.display_phone_number ?? "", quality: number.quality_rating ?? "UNKNOWN" };
}
