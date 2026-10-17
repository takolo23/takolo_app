import { schedule } from "@netlify/functions";
import { runQueue } from "../../apps/api/src/workers/queue.js";
// Netlify excludes scheduled functions from public HTTP invocation.
export const handler = schedule("* * * * *", async () => {
  const result = await runQueue();
  return { statusCode: 200, body: JSON.stringify(result) };
});
