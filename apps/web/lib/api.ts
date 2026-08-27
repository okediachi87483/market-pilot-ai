const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ErrorEnvelope {
  error: { code: string; message: string; details?: unknown };
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Thin fetch wrapper — every request the app makes goes through this, not
 * a bare `fetch`, so the base URL and error handling stay in one place.
 * Understands the backend's error envelope (docs/api.md §1):
 * {"error": {"code", "message", "details"}}.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    let message = `Request to ${path} failed with status ${res.status}`;
    let code: string | undefined;
    try {
      const body = (await res.json()) as ErrorEnvelope;
      message = body.error?.message ?? message;
      code = body.error?.code;
    } catch {
      // response wasn't JSON (or had no body) — fall back to the generic message
    }
    throw new ApiError(res.status, message, code);
  }

  return res.json() as Promise<T>;
}
