import serverless from "serverless-http";
import { app } from "../../apps/api/src/http/app.js";
import { bootstrap } from "../../apps/api/src/services/bootstrap.js";
const wrapped = serverless(app);
export const handler: typeof wrapped = async (event, context) => {
  await bootstrap();
  const request = event as { path?: string; rawPath?: string; requestContext?: { http?: { path?: string } } };
  const normalize = (path: string) => path.replace(/^\/\.netlify\/functions\/api(?=\/|$)/, "/api");
  const path = request.path ? normalize(request.path) : undefined;
  const rawPath = request.rawPath ? normalize(request.rawPath) : undefined;
  return wrapped({ ...event, ...(path ? { path } : {}), ...(rawPath ? { rawPath } : {}), ...(request.requestContext?.http?.path ? { requestContext: { ...request.requestContext, http: { ...request.requestContext.http, path: normalize(request.requestContext.http.path) } } } : {}) }, context);
};
