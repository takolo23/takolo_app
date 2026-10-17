import { segmentFiltersSchema, type SegmentFilters } from "@takolo/shared";
import { Prisma, type Tx, db } from "../config/db.js";
import { AppError } from "../http/errors.js";
export function segmentWhere(workspaceId: string, filters: SegmentFilters, eligible = true): Prisma.ContactWhereInput {
  const conditions: Prisma.ContactWhereInput[] = [];
  if (filters.tagIds.length) {
    if (filters.tagMode === "all") for (const tagId of filters.tagIds) conditions.push({ tags: { some: { tagId, workspaceId } } });
    else conditions.push({ tags: { some: { workspaceId, tagId: { in: filters.tagIds } } } });
  }
  for (const field of filters.fields) {
    if (field.key === "name") conditions.push({ name: field.operator === "exists" ? { not: "" } : field.operator === "equals" ? { equals: field.value, mode: "insensitive" } : { contains: field.value, mode: "insensitive" } });
    else conditions.push({ customFields: { path: [field.key], ...(field.operator === "equals" ? { equals: field.value } : field.operator === "contains" ? { string_contains: field.value } : { not: Prisma.DbNull }) } });
  }
  return { workspaceId, ...(eligible ? { consentGranted: true, optedOutAt: null } : {}), AND: conditions };
}
export async function checkSegmentTags(workspaceId: string, filters: SegmentFilters, tx: Tx = db) {
  const unique = [...new Set(filters.tagIds)];
  if (await tx.tag.count({ where: { workspaceId, id: { in: unique } } }) !== unique.length) throw new AppError(400, "Hay etiquetas que no pertenecen a este espacio.");
}
export async function loadSegment(workspaceId: string, id: string, tx: Tx = db) {
  const segment = await tx.segment.findUnique({ where: { workspaceId_id: { workspaceId, id } } });
  if (!segment) throw new AppError(404, "No se encontró el segmento.");
  return { ...segment, filters: segmentFiltersSchema.parse(segment.filters) };
}
