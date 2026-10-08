import { getToken, setToken, removeToken } from "@/lib/auth-token";
import { API_ROUTES } from "@/lib/constants";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

interface RequestOptions extends RequestInit {
  params?: Record<string, string>;
}

function getAuthHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * How long a token refresh may take before it counts as failed. Every request
 * that gets a 401 waits on the one shared refresh, so a refresh that never
 * answered used to leave the whole page loading forever.
 */
export const REFRESH_TIMEOUT_MS = 10_000;

// Singleton refresh promise — prevents concurrent refresh calls
let refreshPromise: Promise<boolean> | null = null;

/**
 * Exchange the httpOnly refresh cookie for a new access token.
 *
 * Concurrent callers share one request. Resolves `false` - never rejects,
 * never hangs - when the cookie is rejected, the network fails, or no answer
 * comes within ``REFRESH_TIMEOUT_MS``.
 */
export function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REFRESH_TIMEOUT_MS);
    try {
      const response = await fetch(`${API_BASE_URL}${API_ROUTES.authRefresh}`, {
        method: "POST",
        credentials: "include",
        signal: controller.signal,
      });
      if (!response.ok) return false;
      const data = (await response.json()) as { access_token: string };
      setToken(data.access_token);
      return true;
    } catch {
      return false;
    } finally {
      clearTimeout(timer);
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

let sessionExpiredHandler: (() => void) | null = null;

/**
 * Register what happens when the session cannot be recovered: the refresh
 * failed, or a request was still refused after refreshing. ``AuthProvider``
 * clears the user, which sends the browser to the login page instead of
 * leaving it on a page that can never load.
 */
export function setSessionExpiredHandler(handler: (() => void) | null): void {
  sessionExpiredHandler = handler;
}

function expireSession(): void {
  removeToken();
  sessionExpiredHandler?.();
}

/** Paths that should never trigger a 401 refresh retry. */
const NO_RETRY_PATHS = [
  API_ROUTES.authRefresh,
  API_ROUTES.authLogin,
  API_ROUTES.ssoMicrosoftCallback,
];

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private buildUrl(path: string, params?: Record<string, string>): string {
    const fullPath = `${this.baseUrl}${path}`;
    if (!params || Object.keys(params).length === 0) {
      return fullPath;
    }
    const searchParams = new URLSearchParams(params);
    return `${fullPath}?${searchParams.toString()}`;
  }

  private shouldRetry(path: string): boolean {
    return !NO_RETRY_PATHS.some((p) => path === p);
  }

  /**
   * Send a request; on a 401, refresh the token and retry **once**.
   *
   * ``init`` is called for every attempt so the retry carries the new token.
   * A second 401 is final: retrying again would only refresh again, which is
   * how a client used to loop on the refresh endpoint until rate-limited.
   * When the session cannot be recovered the session-expired handler runs.
   */
  private async authorizedFetch(
    path: string,
    params: Record<string, string> | undefined,
    init: () => RequestInit,
  ): Promise<Response> {
    const send = () =>
      fetch(this.buildUrl(path, params), { ...init(), credentials: "include" });
    const response = await send();
    if (response.status !== 401 || !this.shouldRetry(path)) return response;

    if (await refreshAccessToken()) {
      const retried = await send();
      if (retried.status !== 401) return retried;
      expireSession();
      return retried;
    }
    expireSession();
    return response;
  }

  private async throwIfNotOk(response: Response): Promise<void> {
    if (response.ok) return;
    const body = await response.json().catch(() => null);
    const message =
      (body as { detail?: string } | null)?.detail ??
      `API error: ${response.status} ${response.statusText}`;
    throw new ApiError(message, response.status);
  }

  private async json<T>(response: Response): Promise<T> {
    await this.throwIfNotOk(response);
    return response.json() as Promise<T>;
  }

  async get<T>(path: string, options?: RequestOptions): Promise<T> {
    const { params, ...fetchOptions } = options ?? {};
    const response = await this.authorizedFetch(path, params, () => ({
      ...fetchOptions,
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
        ...fetchOptions.headers,
      },
    }));
    return this.json<T>(response);
  }

  async post<T>(
    path: string,
    body?: unknown,
    options?: RequestOptions,
  ): Promise<T> {
    const { params, ...fetchOptions } = options ?? {};
    const response = await this.authorizedFetch(path, params, () => ({
      ...fetchOptions,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
        ...fetchOptions.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    }));
    return this.json<T>(response);
  }

  async put<T>(
    path: string,
    body?: unknown,
    options?: RequestOptions,
  ): Promise<T> {
    const { params, ...fetchOptions } = options ?? {};
    const response = await this.authorizedFetch(path, params, () => ({
      ...fetchOptions,
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
        ...fetchOptions.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    }));
    return this.json<T>(response);
  }

  async patch<T>(
    path: string,
    body?: unknown,
    options?: RequestOptions,
  ): Promise<T> {
    const { params, ...fetchOptions } = options ?? {};
    const response = await this.authorizedFetch(path, params, () => ({
      ...fetchOptions,
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
        ...fetchOptions.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    }));
    return this.json<T>(response);
  }

  async delete(path: string, options?: RequestOptions): Promise<void> {
    const { params, ...fetchOptions } = options ?? {};
    const response = await this.authorizedFetch(path, params, () => ({
      ...fetchOptions,
      method: "DELETE",
      headers: {
        ...getAuthHeaders(),
        ...fetchOptions.headers,
      },
    }));
    await this.throwIfNotOk(response);
  }

  async getBlob(
    path: string,
    options?: RequestOptions,
  ): Promise<{ blob: Blob; filename: string }> {
    const { params, ...fetchOptions } = options ?? {};
    const response = await this.authorizedFetch(path, params, () => ({
      ...fetchOptions,
      method: "GET",
      headers: {
        ...getAuthHeaders(),
        ...fetchOptions.headers,
      },
    }));
    await this.throwIfNotOk(response);
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition");
    const filenameMatch = disposition?.match(/filename="?([^"]+)"?/);
    const filename = filenameMatch?.[1] ?? "download.pdf";
    return { blob, filename };
  }

  async postFormData<T>(
    path: string,
    formData: FormData,
    options?: RequestOptions,
  ): Promise<T> {
    const { params, ...fetchOptions } = options ?? {};
    const response = await this.authorizedFetch(path, params, () => ({
      ...fetchOptions,
      method: "POST",
      headers: {
        ...getAuthHeaders(),
        ...fetchOptions.headers,
      },
      body: formData,
    }));
    return this.json<T>(response);
  }
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const api = new ApiClient(API_BASE_URL);

export function apiFetcher<T>(path: string): Promise<T> {
  return api.get<T>(path);
}
