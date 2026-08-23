'use client';

import {
  type ValidationResult,
  validateChatResult,
  validateDecideResponse,
  validateDemoResetResponse,
  validateDistanceProfile,
  validateEventRouteResult,
  validateLiveEvent,
  validateFeedbackResponse,
  validateFreeBusyResult,
  validateInterventionsResult,
  validateMetricsResult,
  validateMapEventsResult,
  validateOpportunitiesResult,
  validateProfileDeleteResponse,
  validateRecordOutcomeResponse,
  validateSessionResult,
} from '@/lib/osekkai/validators.generated';

export type JsonObject = Record<string, unknown>;

export type SessionInfo = {
  csrfToken: string;
  dataMode: 'demo' | 'live';
  expiresAt: string;
};

export class OsekkaiApiError extends Error {
  code: string;
  status: number;
  requestId?: string;

  constructor(message: string, options: { code?: string; status?: number; requestId?: string } = {}) {
    super(message);
    this.name = 'OsekkaiApiError';
    this.code = options.code ?? 'UNKNOWN_ERROR';
    this.status = options.status ?? 500;
    this.requestId = options.requestId;
  }
}

let sessionPromise: Promise<SessionInfo> | null = null;

function isObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

const REQUEST_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function hasExactKeys(value: JsonObject, keys: readonly string[]): boolean {
  const actual = Object.keys(value);
  return actual.length === keys.length && keys.every((key) => actual.includes(key));
}

function isRequestId(value: unknown): value is string {
  return typeof value === 'string' && REQUEST_ID_PATTERN.test(value);
}

function invalidResponse(): OsekkaiApiError {
  return new OsekkaiApiError('サーバー応答の形式を確認できませんでした。', {
    code: 'INVALID_RESPONSE',
    status: 502,
  });
}

async function parseEnvelope<T>(response: Response): Promise<T> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw invalidResponse();
  }

  if (!isObject(payload)) {
    throw invalidResponse();
  }

  if (response.ok) {
    if (!hasExactKeys(payload, ['data', 'requestId']) || !isRequestId(payload.requestId)) {
      throw invalidResponse();
    }
    return payload.data as T;
  }

  const error = payload.error;
  if (
    !hasExactKeys(payload, ['error', 'requestId']) ||
    !isRequestId(payload.requestId) ||
    !isObject(error) ||
    !hasExactKeys(error, ['code', 'message']) ||
    typeof error.code !== 'string' ||
    error.code.length === 0 ||
    typeof error.message !== 'string' ||
    error.message.length === 0
  ) {
    throw invalidResponse();
  }

  throw new OsekkaiApiError(error.message, {
    code: error.code,
    status: response.status,
    requestId: payload.requestId,
  });
}

function assertValid<T>(result: ValidationResult<T>): T {
  if (result.valid) return result.value;
  throw new OsekkaiApiError('サーバー応答の形式を確認できませんでした。', {
    code: 'INVALID_RESPONSE',
    status: 502,
  });
}

function validatePayload<T>(path: string, method: string, value: unknown): T {
  const routePath = path.split('?', 1)[0];
  let result: ValidationResult<unknown> | undefined;
  if (routePath === '/profile') {
    result = method === 'DELETE' ? validateProfileDeleteResponse(value) : validateDistanceProfile(value);
  } else if (routePath === '/chat' && method === 'POST') {
    result = validateChatResult(value);
  } else if (routePath === '/freebusy') {
    result = validateFreeBusyResult(value);
  } else if (routePath === '/opportunities') {
    result = validateOpportunitiesResult(value);
  } else if (routePath === '/decide') {
    result = validateDecideResponse(value);
  } else if (routePath === '/interventions') {
    result = method === 'GET' ? validateInterventionsResult(value) : validateRecordOutcomeResponse(value);
  } else if (routePath === '/feedback') {
    result = validateFeedbackResponse(value);
  } else if (routePath === '/metrics') {
    result = validateMetricsResult(value);
  } else if (routePath === '/demo/reset') {
    result = validateDemoResetResponse(value);
  } else if (routePath === '/sources') {
    const valid = isObject(value) && value.schemaVersion === '1.0' && value.dataMode === 'live' &&
      typeof value.generatedAt === 'string' && Array.isArray(value.sources) && isObject(value.counts);
    if (!valid) throw invalidResponse();
  } else if (routePath === '/events') {
    const valid = isObject(value) && value.schemaVersion === '1.0' && value.dataMode === 'live' &&
      typeof value.generatedAt === 'string' && Array.isArray(value.events) &&
      value.events.every((event) => validateLiveEvent(event).valid);
    if (!valid) throw invalidResponse();
  } else if (routePath === '/map-events') {
    result = validateMapEventsResult(value);
  } else if (routePath === '/routes') {
    result = validateEventRouteResult(value);
  }
  return result ? (assertValid(result) as T) : (value as T);
}

export function clearOsekkaiSession() {
  sessionPromise = null;
}

export async function getOsekkaiSession(force = false): Promise<SessionInfo> {
  if (force) {
    clearOsekkaiSession();
  }
  if (!sessionPromise) {
    sessionPromise = fetch('/api/osekkai/session', {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    })
      .then(parseEnvelope<SessionInfo>)
      .then((value) => assertValid(validateSessionResult(value)))
      .catch((error) => {
        sessionPromise = null;
        throw error;
      });
  }
  return sessionPromise;
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: JsonObject;
  mutation?: boolean;
  retryCsrf?: boolean;
};

export async function osekkaiRequest<T = JsonObject>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const method = options.method ?? 'GET';
  const mutation = options.mutation ?? method !== 'GET';
  const headers: Record<string, string> = { Accept: 'application/json' };
  const session = await getOsekkaiSession();
  let requestBody = options.body;

  if (mutation) {
    const key =
      typeof options.body?.idempotencyKey === 'string'
        ? options.body.idempotencyKey
        : newIdempotencyKey('osekkai');
    requestBody = { ...(options.body ?? {}), idempotencyKey: key };
    headers['idempotency-key'] = key;
  }

  if (requestBody) {
    headers['Content-Type'] = 'application/json';
  }
  if (mutation) {
    headers['x-osekkai-csrf'] = session.csrfToken;
  }

  const response = await fetch(`/api/osekkai${path}`, {
    method,
    credentials: 'same-origin',
    cache: 'no-store',
    headers,
    body: requestBody ? JSON.stringify(requestBody) : undefined,
  });

  try {
    const value = await parseEnvelope<unknown>(response);
    return validatePayload<T>(path, method, value);
  } catch (error) {
    if (
      mutation &&
      options.retryCsrf !== false &&
      error instanceof OsekkaiApiError &&
      (error.status === 401 || error.status === 403)
    ) {
      await getOsekkaiSession(true);
      return osekkaiRequest<T>(path, {
        ...options,
        body: requestBody,
        retryCsrf: false,
      });
    }
    throw error;
  }
}

export function newIdempotencyKey(prefix: string) {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${random}`;
}

export function friendlyApiError(error: unknown) {
  if (error instanceof OsekkaiApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return '処理を完了できませんでした。もう一度お試しください。';
}
