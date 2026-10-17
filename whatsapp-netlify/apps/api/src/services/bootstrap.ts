import { db, serial } from "../config/db.js";
import { env } from "../config/env.js";
import { hashPassword } from "./security.js";
import { userSchema } from "@takolo/shared";
let boot: Promise<void> | undefined;
export function bootstrap() { return boot ??= run().catch(error => { boot = undefined; throw error; }); }
async function run() {
  if (await db.user.count()) return;
  if (!env.BOOTSTRAP_ADMIN_EMAIL || !env.BOOTSTRAP_ADMIN_PASSWORD) return;
  const user = userSchema.parse({ email: env.BOOTSTRAP_ADMIN_EMAIL, password: env.BOOTSTRAP_ADMIN_PASSWORD, name: "Administrador", role: "ADMIN" });
  const passwordHash = await hashPassword(user.password);
  await serial(async tx => {
    if (await tx.user.count()) return;
    const created = await tx.user.create({ data: { email: user.email, name: user.name, passwordHash } });
    const space = await tx.workspace.create({ data: { name: env.WORKSPACE_NAME, messagesPerMinute: env.MESSAGES_PER_MINUTE, metaPhoneNumberId: env.META_PHONE_NUMBER_ID || null, metaBusinessAccountId: env.META_BUSINESS_ACCOUNT_ID || null, memberships: { create: { userId: created.id, role: "ADMIN" } }, botConfig: { create: {} } } });
    await tx.auditEvent.create({ data: { workspaceId: space.id, actorId: created.id, action: "ADMIN_BOOTSTRAPPED", entityType: "workspace", entityId: space.id } });
  });
}
