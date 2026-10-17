import { z } from "zod";
z.setErrorMap(() => ({ message: "El dato no tiene el formato o valor permitido." }));

export const paginationSchema = z.object({
  page: z.coerce.number().int().min(1).max(100000).default(1),
  pageSize: z.coerce.number().int().min(1).max(100).default(25),
  search: z.string().trim().max(200).default(""),
});
export const idSchema = z.string().cuid();
export const customFieldsSchema = z.record(z.string().regex(/^[a-zA-Z][a-zA-Z0-9_]{0,49}$/), z.string().max(1000)).refine(v => Object.keys(v).length <= 30, "Máximo 30 campos personalizados.");
export const contactSchema = z.object({
  name: z.string().trim().min(1).max(200), phone: z.string().trim().min(7).max(30),
  consent: z.boolean().default(false), consentAt: z.string().datetime({ offset: true }).optional(),
  consentSource: z.string().trim().min(3).max(500).optional(),
  tags: z.array(z.string().trim().min(1).max(80)).max(20).default([]),
  customFields: customFieldsSchema.default({}),
}).strict().superRefine((v, ctx) => {
  if (v.consent && (!v.consentAt || !v.consentSource)) ctx.addIssue({ code: "custom", message: "El consentimiento necesita fecha y fuente." });
  if (v.consentAt && Date.parse(v.consentAt) > Date.now() + 60000) ctx.addIssue({ code: "custom", message: "La fecha de consentimiento no puede ser futura." });
});
export const consentSchema = z.object({ granted: z.boolean(), source: z.string().trim().min(10).max(500), occurredAt: z.string().datetime({ offset: true }) }).strict().refine(v => Date.parse(v.occurredAt) <= Date.now() + 60000, "La fecha no puede ser futura.");
export const segmentFiltersSchema = z.object({
  tagIds: z.array(idSchema).max(20).default([]), tagMode: z.enum(["any", "all"]).default("any"),
  fields: z.array(z.object({ key: z.string().regex(/^[a-zA-Z][a-zA-Z0-9_]{0,49}$/), operator: z.enum(["equals", "contains", "exists"]), value: z.string().max(1000).default("") }).strict()).max(10).default([]),
}).strict();
export const segmentSchema = z.object({ name: z.string().trim().min(1).max(120), filters: segmentFiltersSchema }).strict();
export const variableMappingSchema = z.record(z.string().regex(/^[1-9]\d{0,2}$/), z.object({ source: z.enum(["name", "phone", "field", "literal"]), value: z.string().max(1024).default("") }).strict()).refine(v => Object.keys(v).length <= 30, "Máximo 30 variables.");
export const campaignSchema = z.object({ name: z.string().trim().min(1).max(150), segmentId: idSchema, templateId: idSchema, variableMapping: variableMappingSchema }).strict();
export const launchSchema = z.object({ scheduledAt: z.string().datetime({ offset: true }).optional(), confirmLive: z.boolean().default(false) }).strict();
export const botSchema = z.object({ enabled: z.boolean(), greetingText: z.string().trim().min(1).max(4096), cooldownSecs: z.number().int().min(60).max(86400) }).strict();
export const settingsSchema = z.object({ name: z.string().trim().min(1).max(100), dryRun: z.boolean(), messagesPerMinute: z.number().int().min(1).max(1000) }).strict();
export const loginSchema = z.object({ email: z.string().trim().email().max(254).transform(v => v.toLowerCase()), password: z.string().min(1).max(200) }).strict();
export const userSchema = z.object({ email: z.string().trim().email().max(254).transform(v => v.toLowerCase()), name: z.string().trim().min(1).max(100), password: z.string().min(14).max(200), role: z.enum(["ADMIN", "OPERATOR"]).default("OPERATOR") }).strict();
export const campaignLabels = { DRAFT: "Borrador", SCHEDULED: "Programada", RUNNING: "En curso", PAUSED: "Pausada", COMPLETED: "Terminada", CANCELLED: "Cancelada" } as const;
export const messageLabels = { QUEUED: "En cola", PROCESSING: "Procesando", SIMULATED: "Simulado", ACCEPTED: "Aceptado", SENT: "Enviado", DELIVERED: "Entregado", READ: "Leído", FAILED: "Fallido", CANCELLED: "Cancelado", UNKNOWN: "Por confirmar" } as const;
export type SegmentFilters = z.infer<typeof segmentFiltersSchema>;
export type VariableMapping = z.infer<typeof variableMappingSchema>;
export type ContactInput = z.infer<typeof contactSchema>;
