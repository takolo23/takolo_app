import { runQueue } from "./workers/queue.js";
import { db } from "./config/db.js";
try {
  const result = await runQueue();
  console.log(JSON.stringify(result));
} finally {
  await db.$disconnect();
}
