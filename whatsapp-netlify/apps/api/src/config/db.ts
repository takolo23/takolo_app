import { Pool } from "pg";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient, Prisma } from "../generated/prisma/client.js";
import { env } from "./env.js";
const url = new URL(env.DATABASE_URL);
if (!["postgres:", "postgresql:"].includes(url.protocol)) throw new Error("DATABASE_URL debe ser una conexión PostgreSQL.");
const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
for (const key of [...url.searchParams.keys()]) if (key.startsWith("ssl") || key === "connection_limit") url.searchParams.delete(key);
const globalDb = globalThis as typeof globalThis & { takoloDb?: PrismaClient };
export const db = globalDb.takoloDb ?? new PrismaClient({ adapter: new PrismaPg(new Pool({ connectionString: url.toString(), max: 2, connectionTimeoutMillis: 6000, idleTimeoutMillis: 10000, statement_timeout: 10000, ssl: local ? false : { rejectUnauthorized: true } })) });
globalDb.takoloDb = db;
export type Tx = Prisma.TransactionClient;
export { Prisma };
export async function serial<T>(fn: (tx: Tx) => Promise<T>): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try { return await db.$transaction(fn, { isolationLevel: "Serializable", maxWait: 3000, timeout: 15000 }); }
    catch (error) {
      if (attempt >= 3 || !(error instanceof Prisma.PrismaClientKnownRequestError) || !["P2034", "P2002"].includes(error.code)) throw error;
      await new Promise(resolve => setTimeout(resolve, 20 + Math.random() * 60));
    }
  }
}
