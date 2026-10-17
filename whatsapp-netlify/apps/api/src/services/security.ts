import { createHash, createHmac, randomBytes, scrypt, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";
import { env } from "../config/env.js";
const derive = promisify(scrypt);
export const hash = (value: string) => createHash("sha256").update(value).digest("hex");
export const privateHash = (value: string) => createHmac("sha256", env.SESSION_SECRET).update(value).digest("hex");
export const token = () => randomBytes(32).toString("hex");
export const csrfFor = (sessionHash: string) => privateHash(`csrf:${sessionHash}`);
export function equal(a: string, b: string) { const x = Buffer.from(a); const y = Buffer.from(b); return x.length === y.length && timingSafeEqual(x, y); }
export async function hashPassword(password: string) { const salt = randomBytes(16).toString("hex"); const key = await derive(password, salt, 64) as Buffer; return `scrypt:${salt}:${key.toString("hex")}`; }
export async function checkPassword(password: string, encoded: string) {
  const [type, salt, digest] = encoded.split(":"); if (type !== "scrypt" || !salt || !digest) return false;
  const key = await derive(password, salt, 64) as Buffer; return equal(key.toString("hex"), digest);
}
export function verifySignature(body: Buffer, signature: string, secret: string) {
  if (!secret || !/^sha256=[a-f0-9]{64}$/.test(signature)) return false;
  return equal(signature, `sha256=${createHmac("sha256", secret).update(body).digest("hex")}`);
}
