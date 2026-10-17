import { app } from "./http/app.js";
import { env } from "./config/env.js";
import { bootstrap } from "./services/bootstrap.js";
import { db } from "./config/db.js";
await bootstrap();
const server = app.listen(env.PORT, "127.0.0.1", () => console.log(`API local iniciada en el puerto ${env.PORT}. Modo: ${env.DRY_RUN ? "simulación" : "real"}.`));
for (const signal of ["SIGINT", "SIGTERM"] as const) process.once(signal, () => { server.close(() => { void db.$disconnect().finally(() => process.exit(0)); }); });
