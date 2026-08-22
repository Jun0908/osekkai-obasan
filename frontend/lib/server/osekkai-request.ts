import { NextResponse } from 'next/server';

import type {
  JsonObject,
  JsonValue,
  OsekkaiApiFailure,
  OsekkaiApiSuccess,
} from './osekkai-contract';
import { asOsekkaiHttpError, createRequestId, OsekkaiHttpError } from './osekkai-errors';
import {
  enforceOsekkaiRequestRateLimit,
  osekkaiRetryAfterSeconds,
} from './osekkai-resource-guards';
import {
  decodeOsekkaiSession,
  OSEKKAI_CSRF_HEADER,
  OSEKKAI_SESSION_COOKIE,
  requireOsekkaiSession,
  verifyOsekkaiCsrfToken,
  type OsekkaiSession,
} from './osekkai-user';

const DEFAULT_MAX_BODY_BYTES = 64 * 1024;
const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export type ParsedMutation = {
  body: JsonObject;
  idempotencyKey: string;
  session: OsekkaiSession;
};

export function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function hasUserIdKey(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.some(hasUserIdKey);
  }
  if (!value || typeof value !== 'object') {
    return false;
  }

  return Object.entries(value).some(([key, child]) => {
    const normalized = key.replace(/[-_]/g, '').toLowerCase();
    return normalized === 'userid' || hasUserIdKey(child);
  });
}

function rejectUserIdQuery(request: Request): void {
  let containsUserId = false;
  new URL(request.url).searchParams.forEach((_value, key) => {
    if (key.replace(/[-_]/g, '').toLowerCase() === 'userid') {
      containsUserId = true;
    }
  });
  if (containsUserId) {
    throw new OsekkaiHttpError(
      'USER_ID_FORBIDDEN',
      'ユーザー識別子をリクエストから指定することはできません。',
      400,
    );
  }
}

function requestCookie(request: Request, name: string): string | undefined {
  const cookieHeader = request.headers.get('cookie');
  if (!cookieHeader) {
    return undefined;
  }
  for (const part of cookieHeader.split(';')) {
    const separator = part.indexOf('=');
    if (separator < 0 || part.slice(0, separator).trim() !== name) {
      continue;
    }
    const value = part.slice(separator + 1).trim();
    try {
      return decodeURIComponent(value);
    } catch {
      return undefined;
    }
  }
  return undefined;
}

function requestSessionUserId(request: Request): string | null {
  try {
    return decodeOsekkaiSession(requestCookie(request, OSEKKAI_SESSION_COOKIE))?.userId || null;
  } catch {
    // Session configuration is still checked by the session boundary. For rate
    // limiting, an undecodable cookie is deliberately treated as anonymous.
    return null;
  }
}

function enforceRequestRateLimit(request: Request, mayIssueSession: boolean): void {
  const userId = requestSessionUserId(request);
  enforceOsekkaiRequestRateLimit(request, {
    userId,
    issuesSession: mayIssueSession && !userId,
  });
}

function assertJsonContentType(request: Request): void {
  const contentType = request.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase();
  if (contentType !== 'application/json') {
    throw new OsekkaiHttpError(
      'UNSUPPORTED_MEDIA_TYPE',
      'Content-Type は application/json を指定してください。',
      415,
    );
  }
}

function assertSameOrigin(request: Request): void {
  const origin = request.headers.get('origin');
  const host = request.headers.get('host');
  const requestUrl = new URL(request.url);

  if (!origin || !host) {
    throw new OsekkaiHttpError('ORIGIN_REQUIRED', '同一オリジンのリクエストが必要です。', 403);
  }

  let originUrl: URL;
  try {
    originUrl = new URL(origin);
  } catch {
    throw new OsekkaiHttpError('ORIGIN_MISMATCH', 'リクエスト元を確認できません。', 403);
  }

  const expectedProtocol = requestUrl.protocol;
  if (
    originUrl.host.toLowerCase() !== host.toLowerCase() ||
    originUrl.protocol.toLowerCase() !== expectedProtocol.toLowerCase()
  ) {
    throw new OsekkaiHttpError('ORIGIN_MISMATCH', '別のサイトからの変更は受け付けられません。', 403);
  }

  const fetchSite = request.headers.get('sec-fetch-site');
  if (fetchSite && fetchSite !== 'same-origin' && fetchSite !== 'none') {
    throw new OsekkaiHttpError('ORIGIN_MISMATCH', '別のサイトからの変更は受け付けられません。', 403);
  }
}

function contentLength(request: Request): number | null {
  const raw = request.headers.get('content-length');
  if (!raw) {
    return null;
  }
  const value = Number(raw);
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

export async function readJsonObject(
  request: Request,
  maxBodyBytes = DEFAULT_MAX_BODY_BYTES,
): Promise<JsonObject> {
  const declaredLength = contentLength(request);
  if (declaredLength !== null && declaredLength > maxBodyBytes) {
    throw new OsekkaiHttpError('BODY_TOO_LARGE', 'リクエスト本文が大きすぎます。', 413);
  }

  const reader = request.body?.getReader();
  const chunks: Uint8Array[] = [];
  let receivedBytes = 0;
  if (reader) {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      receivedBytes += value.byteLength;
      if (receivedBytes > maxBodyBytes) {
        await reader.cancel();
        throw new OsekkaiHttpError('BODY_TOO_LARGE', 'リクエスト本文が大きすぎます。', 413);
      }
      chunks.push(value);
    }
  }
  const raw = Buffer.concat(chunks.map((chunk) => Buffer.from(chunk)), receivedBytes).toString('utf8');

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new OsekkaiHttpError('INVALID_JSON', 'JSON形式を確認してください。', 400);
  }

  if (!isJsonObject(parsed)) {
    throw new OsekkaiHttpError('INVALID_REQUEST', 'JSONオブジェクトを送信してください。', 400);
  }
  if (hasUserIdKey(parsed)) {
    throw new OsekkaiHttpError(
      'USER_ID_FORBIDDEN',
      'ユーザー識別子をリクエストから指定することはできません。',
      400,
    );
  }
  return parsed;
}

function readIdempotencyKey(request: Request, body: JsonObject): string {
  if (
    Object.prototype.hasOwnProperty.call(body, 'idempotencyKey') &&
    typeof body.idempotencyKey !== 'string'
  ) {
    throw new OsekkaiHttpError(
      'IDEMPOTENCY_KEY_REQUIRED',
      '有効な冪等キーを指定してください。',
      400,
    );
  }
  const bodyKey = typeof body.idempotencyKey === 'string' ? body.idempotencyKey : null;
  const headerKey = request.headers.get('idempotency-key');

  if (bodyKey && headerKey && bodyKey !== headerKey) {
    throw new OsekkaiHttpError(
      'IDEMPOTENCY_KEY_MISMATCH',
      '冪等キーが一致しません。',
      400,
    );
  }

  const value = bodyKey || headerKey;
  if (!value || !IDEMPOTENCY_KEY_PATTERN.test(value)) {
    throw new OsekkaiHttpError(
      'IDEMPOTENCY_KEY_REQUIRED',
      '有効な冪等キーを指定してください。',
      400,
    );
  }
  return value;
}

export function assertSafeGetRequest(request: Request): void {
  enforceRequestRateLimit(request, true);
  rejectUserIdQuery(request);
}

export async function parseMutationRequest(request: Request): Promise<ParsedMutation> {
  enforceRequestRateLimit(request, false);
  rejectUserIdQuery(request);
  assertSameOrigin(request);
  assertJsonContentType(request);

  const session = await requireOsekkaiSession();
  if (!verifyOsekkaiCsrfToken(session, request.headers.get(OSEKKAI_CSRF_HEADER))) {
    throw new OsekkaiHttpError(
      'CSRF_TOKEN_INVALID',
      '操作用トークンの有効期限が切れました。画面を更新してください。',
      403,
    );
  }

  const body = await readJsonObject(request);
  return {
    session,
    body,
    idempotencyKey: readIdempotencyKey(request, body),
  };
}

export function withoutTransportFields(body: JsonObject): JsonObject {
  const result: JsonObject = {};
  for (const [key, value] of Object.entries(body)) {
    if (key !== 'idempotencyKey') {
      result[key] = value as JsonValue;
    }
  }
  return result;
}

const NO_STORE_HEADERS = {
  'Cache-Control': 'no-store, max-age=0',
  Pragma: 'no-cache',
  'X-Content-Type-Options': 'nosniff',
};

export function osekkaiSuccess<T>(
  data: T,
  requestId: string,
  status = 200,
): NextResponse<OsekkaiApiSuccess<T>> {
  return NextResponse.json(
    { data, requestId },
    { status, headers: NO_STORE_HEADERS },
  );
}

export function osekkaiFailure(
  error: unknown,
  fallbackRequestId = createRequestId(),
): NextResponse<OsekkaiApiFailure> {
  const normalized = asOsekkaiHttpError(error, fallbackRequestId);
  const retryAfterSeconds = osekkaiRetryAfterSeconds(normalized);
  return NextResponse.json(
    {
      error: { code: normalized.code, message: normalized.message },
      requestId: normalized.requestId || fallbackRequestId,
    },
    {
      status: normalized.status,
      headers: retryAfterSeconds
        ? { ...NO_STORE_HEADERS, 'Retry-After': String(retryAfterSeconds) }
        : NO_STORE_HEADERS,
    },
  );
}

export async function withOsekkaiErrors(
  handler: (requestId: string) => Promise<NextResponse>,
): Promise<NextResponse> {
  const requestId = createRequestId();
  try {
    return await handler(requestId);
  } catch (error) {
    return osekkaiFailure(error, requestId);
  }
}

export function requireString(
  body: JsonObject,
  field: string,
  options: { min?: number; max?: number } = {},
): string {
  const value = body[field];
  const min = options.min ?? 1;
  const max = options.max ?? 4_000;
  if (typeof value !== 'string' || value.trim().length < min || value.length > max) {
    throw new OsekkaiHttpError('VALIDATION_ERROR', `${field} の内容を確認してください。`, 400);
  }
  return value.trim();
}

export function optionalBoolean(body: JsonObject, field: string): boolean | undefined {
  const value = body[field];
  if (value === undefined) {
    return undefined;
  }
  if (typeof value !== 'boolean') {
    throw new OsekkaiHttpError('VALIDATION_ERROR', `${field} の内容を確認してください。`, 400);
  }
  return value;
}

export function requireUuid(body: JsonObject, field: string): string {
  const value = requireString(body, field, { min: 36, max: 36 });
  if (!UUID_PATTERN.test(value)) {
    throw new OsekkaiHttpError('VALIDATION_ERROR', `${field} の内容を確認してください。`, 400);
  }
  return value.toLowerCase();
}

export function assertAllowedFields(body: JsonObject, allowed: readonly string[]): void {
  const allowlist = new Set([...allowed, 'idempotencyKey']);
  const unknown = Object.keys(body).filter((key) => !allowlist.has(key));
  if (unknown.length > 0) {
    throw new OsekkaiHttpError(
      'VALIDATION_ERROR',
      `未対応の入力項目があります: ${unknown.sort().join(', ')}`,
      400,
    );
  }
}
