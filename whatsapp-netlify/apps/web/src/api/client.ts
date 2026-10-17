let csrfToken = "";
let workspaceId = "";
export function setCredentials(csrf: string, space = "") {
  csrfToken = csrf;
  workspaceId = space;
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public details: { field?: string; row?: number; message: string }[] = [],
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  csv = false,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      ...(workspaceId ? { "X-Workspace-ID": workspaceId } : {}),
      ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      ...(body === undefined
        ? {}
        : { "Content-Type": csv ? "text/csv" : "application/json" }),
    },
    ...(body === undefined
      ? {}
      : { body: csv ? String(body) : JSON.stringify(body) }),
  });
  const data = (await response
    .json()
    .catch(() => ({
      error: "El servidor no devolvió una respuesta válida.",
    }))) as {
    error?: string;
    details?: { field?: string; row?: number; message: string }[];
  };
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login")
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(
      data.error ?? "No se pudo completar la operación.",
      response.status,
      data.details ?? [],
    );
  }
  if (method !== "GET" && path.startsWith("/settings"))
    window.dispatchEvent(new Event("workspace-updated"));
  return data as T;
}
export const date = (value: string | null | undefined) =>
  value
    ? new Intl.DateTimeFormat("es-MX", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "Sin fecha";
export const localInput = (value = new Date()) =>
  new Date(value.getTime() - value.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
