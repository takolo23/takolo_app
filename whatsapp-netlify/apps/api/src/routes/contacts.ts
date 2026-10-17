import { Router, text } from "express";
import { parse } from "csv-parse/sync";
import { z } from "zod";
import { contactSchema, consentSchema, paginationSchema, idSchema, customFieldsSchema } from "@takolo/shared";
import { db, serial, Prisma } from "../config/db.js";
import { env } from "../config/env.js";
import { asyncRoute, AppError } from "../http/errors.js";
import { identity } from "../middleware/auth.js";
import { normalizePhone } from "../services/phones.js";
import { audit } from "../services/audit.js";
export const contactRoutes = Router();
contactRoutes.get("/", asyncRoute(async (req, res) => {
  const q = paginationSchema.extend({ tagId: idSchema.optional() }).parse(req.query); const workspaceId = identity(req).workspaceId;
  const where: Prisma.ContactWhereInput = { workspaceId, ...(q.tagId ? { tags: { some: { tagId: q.tagId, workspaceId } } } : {}), ...(q.search ? { OR: [{ name: { contains: q.search, mode: "insensitive" } }, { phoneE164: { contains: q.search } }] } : {}) };
  const [total, contacts] = await db.$transaction([db.contact.count({ where }), db.contact.findMany({ where, orderBy: [{ name: "asc" }, { id: "asc" }], skip: (q.page - 1) * q.pageSize, take: q.pageSize, include: { tags: { include: { tag: true } } } })]);
  res.json({ contacts, total, page: q.page, pageSize: q.pageSize });
}));
contactRoutes.post("/", asyncRoute(async (req, res) => {
  const input = contactSchema.parse(req.body); const actor = identity(req); const phoneE164 = normalizePhone(input.phone);
  const contact = await serial(async tx => {
    const created = await tx.contact.create({ data: { workspaceId: actor.workspaceId, name: input.name, phoneE164, consentGranted: input.consent, consentGrantedAt: input.consentAt ? new Date(input.consentAt) : null, consentSource: input.consentSource ?? null, customFields: input.customFields } });
    for (const name of [...new Set(input.tags)]) {
      const tag = await tx.tag.upsert({ where: { workspaceId_name: { workspaceId: actor.workspaceId, name } }, create: { workspaceId: actor.workspaceId, name }, update: {} });
      await tx.contactTag.create({ data: { workspaceId: actor.workspaceId, contactId: created.id, tagId: tag.id } });
    }
    if (input.consent) await tx.consentEvent.create({ data: { workspaceId: actor.workspaceId, contactId: created.id, action: "GRANTED", occurredAt: new Date(input.consentAt!), source: input.consentSource!, actorId: actor.userId } });
    await audit(actor, "CONTACT_CREATED", "contact", created.id, {}, tx); return created;
  }); res.status(201).json(contact);
}));
contactRoutes.post("/import", text({ type: ["text/csv", "text/plain", "application/csv"], limit: env.CSV_MAX_BYTES }), asyncRoute(async (req, res) => {
  if (typeof req.body !== "string") throw new AppError(415, "Envía el contenido del archivo con tipo text/csv.");
  let raw: Record<string, string>[];
  try {
    const rows: unknown[] = parse(req.body, { bom: true, skip_empty_lines: true, trim: true, max_record_size: 65536, on_record: (record, context) => { if (context.records > env.CSV_MAX_ROWS) throw new Error("rows"); return record; }, columns: (headers: string[]) => { const normalized = headers.map(h => h.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim()); if (new Set(normalized).size !== normalized.length || normalized.length > 50 || !["nombre", "telefono", "consentimiento", "fecha"].every(h => normalized.includes(h))) throw new Error("headers"); return normalized; } });
    raw = z.array(z.record(z.string(), z.string())).max(env.CSV_MAX_ROWS).min(1).parse(rows);
  } catch { throw new AppError(400, "CSV inválido. Usa las columnas nombre, telefono, consentimiento y fecha; máximo diez mil filas y cincuenta columnas.", "INVALID_CSV"); }
  const records: { name: string; phoneE164: string; consentGranted: boolean; consentGrantedAt: Date | null; consentSource: string | null; customFields: Record<string, string>; tags: string[] }[] = [];
  const errors: { row: number; message: string }[] = []; const seen = new Map<string, boolean>(); let duplicatesInFile = 0;
  for (const [index, row] of raw.entries()) {
    try {
      const yes = ["si", "sí", "true", "1"].includes((row.consentimiento ?? "").toLowerCase());
      if (!["si", "sí", "true", "1", "no", "false", "0", ""].includes((row.consentimiento ?? "").toLowerCase())) throw new Error("Consentimiento inválido: usa sí o no.");
      const date = row.fecha ? new Date(row.fecha) : null;
      if (date && !Number.isFinite(date.getTime())) throw new Error("La fecha no es válida; usa ISO 8601 con zona horaria.");
      if (row.fecha && !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(row.fecha)) throw new Error("La fecha debe incluir hora y zona, por ejemplo 2026-10-17T09:00:00-06:00.");
      const fields = Object.fromEntries(Object.entries(row).filter(([key]) => key.startsWith("campo_")).map(([key, value]) => [key.slice(6), value]));
      const item = contactSchema.parse({ name: row.nombre, phone: row.telefono, consent: yes, ...(date ? { consentAt: date.toISOString() } : {}), ...(row.fuente ? { consentSource: row.fuente } : {}), tags: (row.etiquetas ?? "").split("|").filter(Boolean), customFields: fields });
      const phoneE164 = normalizePhone(item.phone);
      if (seen.has(phoneE164)) { if (seen.get(phoneE164) !== yes) throw new Error("Hay permisos contradictorios para el mismo teléfono."); duplicatesInFile++; continue; } seen.set(phoneE164, yes);
      records.push({ name: item.name, phoneE164, consentGranted: yes, consentGrantedAt: date, consentSource: item.consentSource ?? null, customFields: item.customFields, tags: item.tags });
    } catch (error) { errors.push({ row: index + 2, message: error instanceof z.ZodError ? error.issues.map(i => i.message).join(" ") : error instanceof Error ? error.message : "Fila inválida." }); }
  }
  if (errors.length) { res.status(400).json({ error: "No se importó ningún contacto. Corrige las filas indicadas.", details: errors.slice(0, 100), invalidRows: errors.length }); return; }
  const actor = identity(req);
  const result = await serial(async tx => {
    const created = await tx.contact.createManyAndReturn({ data: records.map(({ tags: _tags, ...row }) => ({ ...row, workspaceId: actor.workspaceId })), skipDuplicates: true, select: { id: true, phoneE164: true, consentGranted: true, consentGrantedAt: true, consentSource: true } });
    const byPhone = new Map(records.map(row => [row.phoneE164, row]));
    const names = [...new Set(created.flatMap(c => byPhone.get(c.phoneE164)?.tags ?? []))];
    if (names.length) await tx.tag.createMany({ data: names.map(name => ({ workspaceId: actor.workspaceId, name })), skipDuplicates: true });
    const tags = await tx.tag.findMany({ where: { workspaceId: actor.workspaceId, name: { in: names } } }); const tagIds = new Map(tags.map(t => [t.name, t.id]));
    const links = created.flatMap(c => [...new Set(byPhone.get(c.phoneE164)?.tags ?? [])].map(name => ({ workspaceId: actor.workspaceId, contactId: c.id, tagId: tagIds.get(name)! })));
    if (links.length) await tx.contactTag.createMany({ data: links, skipDuplicates: true });
    const consent = created.filter(c => c.consentGranted).map(c => ({ workspaceId: actor.workspaceId, contactId: c.id, action: "GRANTED" as const, occurredAt: c.consentGrantedAt!, source: c.consentSource!, actorId: actor.userId }));
    if (consent.length) await tx.consentEvent.createMany({ data: consent });
    const summary = { created: created.length, skipped: records.length - created.length + duplicatesInFile, total: raw.length };
    await audit(actor, "CONTACTS_IMPORTED", "contact", undefined, summary, tx); return summary;
  }); res.status(201).json(result);
}));
contactRoutes.get("/:id", asyncRoute(async (req, res) => {
  const id = idSchema.parse(req.params.id); const workspaceId = identity(req).workspaceId;
  const contact = await db.contact.findUnique({ where: { workspaceId_id: { workspaceId, id } }, include: { tags: { include: { tag: true } }, consentEvents: { take: 50, orderBy: { occurredAt: "desc" } }, inboundMessages: { take: 50, orderBy: { occurredAt: "desc" } }, messages: { take: 50, orderBy: { createdAt: "desc" } } } });
  if (!contact) throw new AppError(404, "No se encontró el contacto."); res.json(contact);
}));
contactRoutes.patch("/:id", asyncRoute(async (req, res) => {
  const id = idSchema.parse(req.params.id); const actor = identity(req);
  const input = z.object({ name: z.string().trim().min(1).max(200), customFields: customFieldsSchema, tags: z.array(z.string().trim().min(1).max(80)).max(20) }).strict().parse(req.body);
  const contact = await serial(async tx => {
    const current = await tx.contact.findUnique({ where: { workspaceId_id: { workspaceId: actor.workspaceId, id } } }); if (!current) throw new AppError(404, "No se encontró el contacto.");
    const updated = await tx.contact.update({ where: { workspaceId_id: { workspaceId: actor.workspaceId, id } }, data: { name: input.name, customFields: input.customFields } });
    await tx.contactTag.deleteMany({ where: { workspaceId: actor.workspaceId, contactId: id } });
    for (const name of [...new Set(input.tags)]) { const tag = await tx.tag.upsert({ where: { workspaceId_name: { workspaceId: actor.workspaceId, name } }, create: { workspaceId: actor.workspaceId, name }, update: {} }); await tx.contactTag.create({ data: { workspaceId: actor.workspaceId, contactId: id, tagId: tag.id } }); }
    await audit(actor, "CONTACT_UPDATED", "contact", id, {}, tx); return updated;
  }); res.json(contact);
}));
contactRoutes.post("/:id/consent", asyncRoute(async (req, res) => {
  const id = idSchema.parse(req.params.id); const input = consentSchema.parse(req.body); const actor = identity(req);
  const contact = await serial(async tx => {
    const current = await tx.contact.findUnique({ where: { workspaceId_id: { workspaceId: actor.workspaceId, id } } }); if (!current) throw new AppError(404, "No se encontró el contacto.");
    const occurredAt = new Date(input.occurredAt);
    if (input.granted && current.optedOutAt && occurredAt <= current.optedOutAt) throw new AppError(400, "La nueva autorización debe ser posterior a la baja.");
    const updated = await tx.contact.update({ where: { workspaceId_id: { workspaceId: actor.workspaceId, id } }, data: { consentGranted: input.granted, consentGrantedAt: input.granted ? occurredAt : current.consentGrantedAt, consentSource: input.source, optedOutAt: input.granted ? null : new Date() } });
    await tx.consentEvent.create({ data: { workspaceId: actor.workspaceId, contactId: id, action: input.granted ? "GRANTED" : "WITHDRAWN", occurredAt, source: input.source, actorId: actor.userId } });
    if (!input.granted) await tx.outboundMessage.updateMany({ where: { workspaceId: actor.workspaceId, contactId: id, status: "QUEUED" }, data: { status: "CANCELLED", lastError: "El contacto retiró su consentimiento." } });
    await audit(actor, input.granted ? "CONSENT_GRANTED" : "CONSENT_WITHDRAWN", "contact", id, {}, tx); return updated;
  }); res.json(contact);
}));
