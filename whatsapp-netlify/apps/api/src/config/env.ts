import dotenv from "dotenv";
import { fileURLToPath } from "node:url";
import { z } from "zod";
if (process.env.NODE_ENV !== "production") dotenv.config({ path: fileURLToPath(new URL("../../../../.env", import.meta.url)), quiet: true });
const bool = z.enum(["true", "false"]).transform(v => v === "true");
const optionalSecret = z.string().default("");
const schema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  DATABASE_URL: z.string().url(), APP_URL: z.string().url(), PORT: z.coerce.number().int().min(1).max(65535).default(3001),
  SESSION_SECRET: z.string().min(32), SESSION_TTL_HOURS: z.coerce.number().int().min(1).max(72).default(12),
  BOOTSTRAP_ADMIN_EMAIL: optionalSecret, BOOTSTRAP_ADMIN_PASSWORD: optionalSecret, WORKSPACE_NAME: z.string().min(1).max(100).default("Mi espacio"),
  META_ACCESS_TOKEN: optionalSecret, META_APP_SECRET: optionalSecret, META_VERIFY_TOKEN: optionalSecret,
  META_PHONE_NUMBER_ID: optionalSecret, META_BUSINESS_ACCOUNT_ID: optionalSecret, META_GRAPH_VERSION: optionalSecret,
  DRY_RUN: bool.default("true"), MESSAGES_PER_MINUTE: z.coerce.number().int().min(1).max(1000).default(3),
  MAX_ATTEMPTS: z.coerce.number().int().min(1).max(10).default(5), RETRY_BASE_SECONDS: z.coerce.number().int().min(1).max(3600).default(60),
  RETRY_MAX_SECONDS: z.coerce.number().int().min(60).max(86400).default(3600), QUEUE_BATCH_SIZE: z.coerce.number().int().min(1).max(100).default(10),
  QUEUE_BUDGET_MS: z.coerce.number().int().min(1000).max(23000).default(20000), CLAIM_LEASE_SECONDS: z.coerce.number().int().min(60).max(600).default(120),
  MAX_MESSAGE_AGE_HOURS: z.coerce.number().int().min(1).max(168).default(24), CSV_MAX_BYTES: z.coerce.number().int().min(1024).max(4194304).default(2097152),
  CSV_MAX_ROWS: z.coerce.number().int().min(1).max(10000).default(10000), DEFAULT_PHONE_COUNTRY: z.string().length(2).default("MX"),
});
const parsed = schema.safeParse(process.env);
if (!parsed.success) throw new Error(`Configuración inválida: ${parsed.error.issues.map(i => `${i.path.join(".")}: ${i.message}`).join("; ")}`);
export const env = parsed.data;
if (env.NODE_ENV === "production" && new URL(env.APP_URL).protocol !== "https:") throw new Error("APP_URL debe usar HTTPS en producción.");
export class ConfigurationError extends Error {}
export function requireMeta() {
  if (![env.META_ACCESS_TOKEN, env.META_APP_SECRET, env.META_VERIFY_TOKEN, env.META_PHONE_NUMBER_ID, env.META_BUSINESS_ACCOUNT_ID].every(Boolean) || !/^v\d+\.\d+$/.test(env.META_GRAPH_VERSION) || !/^\d+$/.test(env.META_PHONE_NUMBER_ID) || !/^\d+$/.test(env.META_BUSINESS_ACCOUNT_ID)) throw new ConfigurationError("Falta configurar la conexión oficial de Meta en las variables privadas del servidor.");
}
