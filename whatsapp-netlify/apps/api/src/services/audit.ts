import { db, type Tx, type Prisma } from "../config/db.js";
import type { Identity } from "../middleware/auth.js";
export async function audit(actor: Pick<Identity, "workspaceId" | "userId">, action: string, entityType: string, entityId?: string, details: Prisma.InputJsonValue = {}, client: Tx = db) {
  await client.auditEvent.create({ data: { workspaceId: actor.workspaceId, actorId: actor.userId, action, entityType, entityId: entityId ?? null, details } });
}
