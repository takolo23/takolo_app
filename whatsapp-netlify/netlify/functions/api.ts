import type { Context } from "@netlify/functions";
import serverless from "serverless-http";
import { app } from "../../apps/api/src/http/app.js";
import { bootstrap } from "../../apps/api/src/services/bootstrap.js";

const wrapped = serverless(app);
interface LambdaResponse {
  statusCode: number;
  body?: string;
  isBase64Encoded?: boolean;
  headers?: Record<string, string | number | boolean>;
  multiValueHeaders?: Record<string, string[]>;
}
export default async function api(
  request: Request,
  context: Context,
): Promise<Response> {
  await bootstrap();
  const url = new URL(request.url);
  const path = url.pathname.replace(
    /^\/\.netlify\/functions\/api(?=\/|$)/,
    "/api",
  );
  const raw = ["GET", "HEAD"].includes(request.method)
    ? Buffer.alloc(0)
    : Buffer.from(await request.arrayBuffer());
  const requestHeaders: Record<string, string> = {};
  request.headers.forEach((value, key) => {
    requestHeaders[key] = value;
  });
  const result = (await wrapped(
    {
      httpMethod: request.method,
      path,
      headers: requestHeaders,
      queryStringParameters: Object.fromEntries(url.searchParams),
      multiValueQueryStringParameters: Object.fromEntries(
        [...new Set(url.searchParams.keys())].map((key) => [
          key,
          url.searchParams.getAll(key),
        ]),
      ),
      body: raw.length ? raw.toString("base64") : null,
      isBase64Encoded: raw.length > 0,
      requestContext: {
        requestId: context.requestId,
        identity: { sourceIp: context.ip },
      },
    },
    {},
  )) as LambdaResponse;
  const headers = new Headers();
  const multiKeys = new Set(
    Object.keys(result.multiValueHeaders ?? {}).map((key) => key.toLowerCase()),
  );
  for (const [key, value] of Object.entries(result.headers ?? {}))
    if (!multiKeys.has(key.toLowerCase())) headers.set(key, String(value));
  for (const [key, values] of Object.entries(result.multiValueHeaders ?? {}))
    for (const value of values) headers.append(key, value);
  const noBody =
    request.method === "HEAD" || [204, 205, 304].includes(result.statusCode);
  return new Response(
    noBody
      ? null
      : result.isBase64Encoded
        ? Buffer.from(result.body ?? "", "base64")
        : (result.body ?? ""),
    { status: result.statusCode, headers },
  );
}
