let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}

// getRandomValues works on internal HTTP LAN origins as well as HTTPS.
export function requestToken() {
  return Array.from(crypto.getRandomValues(new Uint8Array(24)), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (csrf) headers.set("X-CSRF-Token", csrf);
  const response = await fetch("/api" + path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    const detail = data.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map(
                (e: { loc: string[]; msg: string }) =>
                  `${e.loc.join(".")}: ${e.msg}`,
              )
              .join("; ")
          : JSON.stringify(detail);
    if (response.status === 401 && path !== "/auth/login")
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(message, response.status);
  }
  return response.status === 204 ? (undefined as T) : await response.json();
}

export function post<T>(path: string, data?: unknown) {
  return api<T>(path, {
    method: "POST",
    body: data === undefined ? undefined : JSON.stringify(data),
  });
}
export function put<T>(path: string, data: unknown) {
  return api<T>(path, { method: "PUT", body: JSON.stringify(data) });
}

export async function all<T>(path: string): Promise<T[]> {
  let result: T[] = [],
    offset = 0;
  while (true) {
    const rows = await api<T[]>(
      `${path}${path.includes("?") ? "&" : "?"}limit=200&offset=${offset}`,
    );
    result = [...result, ...rows];
    if (rows.length < 200) return result;
    offset += 200;
  }
}
