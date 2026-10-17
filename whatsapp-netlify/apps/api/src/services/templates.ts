import { z } from "zod";
import { type VariableMapping, variableMappingSchema } from "@takolo/shared";
import { db, type Prisma } from "../config/db.js";
import { env } from "../config/env.js";
import { AppError } from "../http/errors.js";
import { metaRequest } from "./meta.js";
const componentSchema = z.object({ type: z.string(), format: z.string().optional(), text: z.string().optional(), buttons: z.array(z.object({ type: z.string(), url: z.string().optional(), text: z.string().optional() }).passthrough()).optional() }).passthrough();
const metaTemplateSchema = z.object({ id: z.string().max(64), name: z.string().max(512), language: z.string().max(20), status: z.string(), category: z.enum(["MARKETING", "UTILITY", "AUTHENTICATION"]), components: z.array(componentSchema).max(20), rejected_reason: z.string().max(500).optional() }).passthrough();
export function templateVariables(body: string) { return [...new Set([...body.matchAll(/\{\{\s*([1-9]\d*)\s*\}\}/g)].map(m => m[1]!))].sort((a, b) => Number(a) - Number(b)); }
export function analyzeTemplate(components: z.infer<typeof componentSchema>[], category: string) {
  const body = components.find(c => c.type === "BODY")?.text ?? ""; const variables = templateVariables(body);
  const bad = components.some(c => !["BODY", "HEADER", "FOOTER", "BUTTONS"].includes(c.type) || (c.type === "HEADER" && (c.format !== "TEXT" || /\{\{/.test(c.text ?? ""))) || (c.type === "FOOTER" && /\{\{/.test(c.text ?? "")) || (c.type === "BUTTONS" && (c.buttons ?? []).some(b => !["URL", "PHONE_NUMBER", "QUICK_REPLY"].includes(b.type) || /\{\{/.test(b.url ?? ""))));
  const stripped = body.replace(/\{\{\s*[1-9]\d*\s*\}\}/g, "");
  const sequential = variables.every((v, i) => Number(v) === i + 1);
  const optOutIncluded = /\b(?:BAJA|STOP)\b/i.test(components.map(c => c.text ?? "").join(" "));
  return { body, variables, optOutIncluded, supported: Boolean(body) && !bad && !/[{}]/.test(stripped) && sequential && variables.length <= 30 && category !== "AUTHENTICATION" };
}
export async function refreshTemplate(workspaceId: string, id: string) {
  const stored = await db.template.findUniqueOrThrow({ where: { workspaceId_id: { workspaceId, id } } });
  const item = metaTemplateSchema.parse(await metaRequest(`${stored.metaId}?fields=id,name,language,status,category,components`));
  if (item.id !== stored.metaId) throw new AppError(502, "Meta devolvió una plantilla diferente.");
  const info = analyzeTemplate(item.components, item.category);
  const status = (["APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED"].includes(item.status) ? item.status : "UNKNOWN") as "APPROVED" | "PENDING" | "REJECTED" | "PAUSED" | "DISABLED" | "UNKNOWN";
  await db.template.update({ where: { workspaceId_id: { workspaceId, id } }, data: { name: item.name, language: item.language, category: item.category, status, components: item.components as Prisma.InputJsonValue, variables: info.variables, bodyText: info.body, optOutIncluded: info.optOutIncluded, supported: info.supported, syncedAt: new Date() } });
}
export async function syncTemplates(workspaceId: string) {
  const workspace = await db.workspace.findUniqueOrThrow({ where: { id: workspaceId } });
  if (workspace.metaBusinessAccountId !== env.META_BUSINESS_ACCOUNT_ID || workspace.metaPhoneNumberId !== env.META_PHONE_NUMBER_ID) throw new AppError(409, "Verifica primero la conexión oficial del espacio.");
  const seen: string[] = []; let after = "";
  for (let page = 0; page < 30; page++) {
    const result = z.object({ data: z.array(metaTemplateSchema).max(100), paging: z.object({ cursors: z.object({ after: z.string().max(2048).optional() }).optional(), next: z.string().optional() }).optional() }).parse(await metaRequest(`${env.META_BUSINESS_ACCOUNT_ID}/message_templates?limit=100${after ? `&after=${encodeURIComponent(after)}` : ""}`));
    for (const item of result.data) {
      const info = analyzeTemplate(item.components, item.category); const status = (["APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED"].includes(item.status) ? item.status : "UNKNOWN") as "APPROVED" | "PENDING" | "REJECTED" | "PAUSED" | "DISABLED" | "UNKNOWN";
      const data = { name: item.name, language: item.language, category: item.category, status, components: item.components as Prisma.InputJsonValue, variables: info.variables, bodyText: info.body, optOutIncluded: info.optOutIncluded, supported: info.supported, rejectionReason: item.rejected_reason ?? null, syncedAt: new Date() };
      await db.template.upsert({ where: { workspaceId_metaId: { workspaceId, metaId: item.id } }, create: { workspaceId, metaId: item.id, ...data }, update: data }); seen.push(item.id);
    }
    if (!result.paging?.next) { await db.template.updateMany({ where: { workspaceId, metaId: { notIn: seen } }, data: { status: "DISABLED" } }); return { synced: seen.length }; }
    const next = result.paging.cursors?.after; if (!next || next === after) throw new AppError(502, "Meta devolvió una paginación de plantillas inválida."); after = next;
  }
  throw new AppError(502, "Hay demasiadas plantillas para una sincronización. No se desactivaron plantillas existentes.");
}
export function mapVariables(body: string, mapping: VariableMapping, contact: { name: string; phoneE164: string; customFields: unknown }) {
  const variables = templateVariables(body); const validated = variableMappingSchema.parse(mapping);
  if (Object.keys(validated).some(key => !variables.includes(key))) throw new AppError(400, "Hay variables asignadas que no existen en la plantilla.");
  const fields = z.record(z.string()).safeParse(contact.customFields); const values: string[] = [];
  for (const variable of variables) {
    const rule = validated[variable]; if (!rule) throw new AppError(400, `Falta asignar la variable {{${variable}}}.`);
    const value = rule.source === "name" ? contact.name : rule.source === "phone" ? contact.phoneE164 : rule.source === "literal" ? rule.value : fields.success ? fields.data[rule.value] : undefined;
    if (!value?.trim() || value.length > 1024 || /[\r\n\t]/.test(value)) throw new AppError(400, `La variable {{${variable}}} está vacía o no es válida para ${contact.name}.`);
    values.push(value);
  }
  return { values, preview: body.replace(/\{\{\s*([1-9]\d*)\s*\}\}/g, (_all, id: string) => values[Number(id) - 1] ?? "") };
}
export function assertTemplate(template: { status: string; supported: boolean; category: string; optOutIncluded: boolean }) {
  if (template.status !== "APPROVED" || !template.supported) throw new AppError(409, "Selecciona una plantilla aprobada y compatible de Meta.");
  if (template.category === "MARKETING" && !template.optOutIncluded) throw new AppError(409, "La plantilla de marketing debe incluir instrucciones para responder BAJA o STOP.");
}
