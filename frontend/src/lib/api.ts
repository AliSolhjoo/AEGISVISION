import type { Tokens } from './types';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const ACCESS_KEY = 'aegisvision.access';
const REFRESH_KEY = 'aegisvision.refresh';

export function getAccessToken() {
  return sessionStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken() {
  return sessionStorage.getItem(REFRESH_KEY);
}

export function saveTokens(tokens: Pick<Tokens, 'access' | 'refresh'>) {
  sessionStorage.setItem(ACCESS_KEY, tokens.access);
  sessionStorage.setItem(REFRESH_KEY, tokens.refresh);
}

export function clearTokens() {
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
}

function buildUrl(path: string) {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return (await response.json()) as T;
  }
  return (await response.blob()) as T;
}

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(message: string, status: number, data: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export function describeApiError(error: unknown): string {
  if (error instanceof ApiError) {
    if (typeof error.data === 'string') return error.data;
    if (error.data && typeof error.data === 'object') {
      const obj = error.data as Record<string, unknown>;
      if (typeof obj.detail === 'string') return obj.detail;
      if (typeof obj.message === 'string') return obj.message;
      const first = Object.entries(obj)[0];
      if (first) {
        const value = first[1];
        if (Array.isArray(value)) return `${first[0]}: ${value.join(', ')}`;
        if (typeof value === 'string') return `${first[0]}: ${value}`;
      }
    }
    return error.message;
  }
  return error instanceof Error ? error.message : 'An unexpected error occurred.';
}

let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      const response = await fetch(buildUrl('/api/auth/token/refresh/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh }),
      });
      if (!response.ok) return false;
      const data = (await response.json()) as { access: string; refresh?: string };
      if (!data.access) return false;
      sessionStorage.setItem(ACCESS_KEY, data.access);
      if (data.refresh) sessionStorage.setItem(REFRESH_KEY, data.refresh);
      return true;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

interface RequestOptions extends RequestInit {
  auth?: boolean;
  retryAuth?: boolean;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { auth = true, retryAuth = true, headers, ...init } = options;
  const requestHeaders = new Headers(headers || {});
  if (auth) {
    const token = getAccessToken();
    if (token) requestHeaders.set('Authorization', `Bearer ${token}`);
  }
  if (init.body && !(init.body instanceof FormData) && !requestHeaders.has('Content-Type')) {
    requestHeaders.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path), {
      ...init,
      headers: requestHeaders,
    });
  } catch {
    throw new ApiError('Cannot reach the AEGISVISION API. Make sure Django is running.', 0, null);
  }

  if (response.status === 401 && auth && retryAuth && !path.includes('/token/refresh/')) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return apiRequest<T>(path, { ...options, retryAuth: false });
    clearTokens();
    window.dispatchEvent(new CustomEvent('aegis:session-expired'));
  }

  const data = await parseResponse<unknown>(response);
  if (!response.ok) {
    throw new ApiError(`Request failed (${response.status})`, response.status, data);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => apiRequest<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiRequest<T>(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body ?? {}) }),
  publicPost: <T>(path: string, body?: unknown) =>
    apiRequest<T>(path, { method: 'POST', auth: false, body: JSON.stringify(body ?? {}) }),
  patch: <T>(path: string, body: unknown) =>
    apiRequest<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => apiRequest<T>(path, { method: 'DELETE' }),
  blob: (path: string) => apiRequest<Blob>(path),
};

export function authApiUrl(path: string) {
  return buildUrl(path);
}

export function toApiPath(value: string) {
  if (/^https?:\/\//i.test(value)) {
    const parsed = new URL(value);
    return `${parsed.pathname}${parsed.search}`;
  }
  return value;
}
