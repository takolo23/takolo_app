import type { Config } from "@netlify/functions";
import { runQueue } from "../../apps/api/src/workers/queue.js";

// Netlify does not expose a published scheduled function as a public HTTP endpoint.
export default async function queue(): Promise<Response> {
  return Response.json(await runQueue());
}
export const config: Config = { schedule: "* * * * *" };
