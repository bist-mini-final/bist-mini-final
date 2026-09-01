import ky, { type Options } from 'ky';

interface ApiErrorDetail {
  readonly code?: unknown;
  readonly message?: unknown;
  readonly retryable?: unknown;
  readonly context?: unknown;
}

export class ApiError extends Error {
  readonly name = 'ApiError';

  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly retryable?: boolean,
    readonly context?: Record<string, unknown>,
  ) {
    super(message);
  }
}

export const API_V1_PREFIX = '/api/v1';

/**
 * Migrate legacy feature-local `/api/*` paths at the single transport boundary.
 * Non-API URLs and already-versioned URLs are left untouched.
 */
export function versionedApiEndpoint(endpoint: string): string {
  if (endpoint === '/api') return API_V1_PREFIX;
  if (endpoint === API_V1_PREFIX || endpoint.startsWith(`${API_V1_PREFIX}/`)) {
    return endpoint;
  }
  if (endpoint.startsWith('/api/')) {
    return `${API_V1_PREFIX}${endpoint.slice('/api'.length)}`;
  }
  return endpoint;
}

export const httpClient = ky.create({
  credentials: 'same-origin',
  retry: 0,
  timeout: 15_000,
  throwHttpErrors: false,
});

export async function apiErrorFromResponse(
  response: Response,
  fallback = `요청을 처리하지 못했습니다. (${response.status})`,
): Promise<ApiError> {
  try {
    const body = await response.clone().json() as { detail?: unknown };
    if (body.detail && typeof body.detail === 'object') {
      const detail = body.detail as ApiErrorDetail;
      return new ApiError(
        typeof detail.message === 'string' ? detail.message : fallback,
        response.status,
        typeof detail.code === 'string' ? detail.code : undefined,
        typeof detail.retryable === 'boolean' ? detail.retryable : undefined,
        detail.context && typeof detail.context === 'object'
          ? detail.context as Record<string, unknown>
          : undefined,
      );
    }
  } catch {
    // Non-JSON failures retain the endpoint-specific fallback.
  }
  return new ApiError(fallback, response.status);
}

export async function requestResponse(
  endpoint: string,
  options: Options = {},
  fallback?: string,
): Promise<Response> {
  const response = await httpClient(versionedApiEndpoint(endpoint), options);
  if (!response.ok) {
    throw await apiErrorFromResponse(response, fallback);
  }
  return response;
}

export async function requestJson<T>(
  endpoint: string,
  options: Options = {},
  fallback?: string,
): Promise<T> {
  const response = await requestResponse(endpoint, options, fallback);
  return await response.json() as T;
}
