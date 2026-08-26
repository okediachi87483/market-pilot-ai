const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Thin fetch wrapper — no business endpoints exist yet (see docs/api.md),
 * this only proves the frontend can reach the backend. Every request the
 * app makes should go through this, not a bare `fetch`, so the base URL
 * and error handling stay in one place.
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
    throw new ApiError(res.status, `Request to ${path} failed with status ${res.status}`);
  }

  return res.json() as Promise<T>;
}
