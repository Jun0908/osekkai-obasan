import { createHash, createHmac, randomBytes, randomUUID, timingSafeEqual } from 'crypto';
import { cookies } from 'next/headers';

import type { OsekkaiDataMode } from './osekkai-contract';
import { OsekkaiHttpError } from './osekkai-errors';

export const OSEKKAI_SESSION_COOKIE = 'osekkai_session';
export const OSEKKAI_CSRF_HEADER = 'x-osekkai-csrf';

const SESSION_VERSION = 'v1';
const SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;
const CSRF_TTL_SECONDS = 10 * 60;
const USER_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export type OsekkaiSession = {
  userId: string;
  issuedAtSeconds: number;
};

function developmentSecret(): string {
  return createHash('sha256')
    .update(`osekkai-local-development:${process.cwd()}`)
    .digest('hex');
}

export function isWeakProductionSecret(value: string): boolean {
  const normalized = value.toLowerCase();
  return (
    Buffer.byteLength(value) < 32 ||
    new Set(value).size < 8 ||
    [
      'change-me',
      'replace-me',
      'replace-with-',
      'your-secret',
      'example-secret',
      'development-secret',
      'test-secret',
    ]
      .some((placeholder) => normalized.includes(placeholder))
  );
}

function sessionSecrets(): { current: string; previous?: string } {
  const configured = process.env.OSEKKAI_SESSION_SECRET?.trim();
  const previous = process.env.OSEKKAI_SESSION_SECRET_PREVIOUS?.trim() || undefined;

  if (!configured && process.env.NODE_ENV === 'production') {
    throw new OsekkaiHttpError(
      'SESSION_CONFIG_ERROR',
      'セッション設定が完了していません。',
      503,
    );
  }

  if (
    process.env.NODE_ENV === 'production' &&
    ((configured && isWeakProductionSecret(configured)) || (previous && isWeakProductionSecret(previous)))
  ) {
    throw new OsekkaiHttpError(
      'SESSION_CONFIG_ERROR',
      'セッション設定が完了していません。',
      503,
    );
  }

  return {
    current: configured || developmentSecret(),
    previous,
  };
}

function hmac(value: string, secret: string): string {
  return createHmac('sha256', secret).update(value).digest('base64url');
}

function signaturesEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);

  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

function validSignature(payload: string, signature: string): boolean {
  const { current, previous } = sessionSecrets();
  return (
    signaturesEqual(signature, hmac(payload, current)) ||
    Boolean(previous && signaturesEqual(signature, hmac(payload, previous)))
  );
}

export function isValidOsekkaiUserId(value: string): boolean {
  return USER_ID_PATTERN.test(value);
}

export function encodeOsekkaiSession(session: OsekkaiSession): string {
  const payload = `${SESSION_VERSION}.${session.userId}.${session.issuedAtSeconds}`;
  return `${payload}.${hmac(payload, sessionSecrets().current)}`;
}

export function decodeOsekkaiSession(
  value: string | undefined,
  nowSeconds = Math.floor(Date.now() / 1000),
): OsekkaiSession | null {
  if (!value) {
    return null;
  }

  const parts = value.split('.');
  if (parts.length !== 4) {
    return null;
  }

  const [version, userId, issuedAtRaw, signature] = parts;
  const issuedAtSeconds = Number(issuedAtRaw);
  const payload = `${version}.${userId}.${issuedAtRaw}`;

  if (
    version !== SESSION_VERSION ||
    !isValidOsekkaiUserId(userId) ||
    !Number.isSafeInteger(issuedAtSeconds) ||
    issuedAtSeconds > nowSeconds + 60 ||
    nowSeconds - issuedAtSeconds > SESSION_MAX_AGE_SECONDS ||
    !validSignature(payload, signature)
  ) {
    return null;
  }

  return { userId: userId.toLowerCase(), issuedAtSeconds };
}

type OsekkaiCookieStore = Awaited<Awaited<ReturnType<typeof cookies>>>;

function setSessionCookie(cookieStore: OsekkaiCookieStore, session: OsekkaiSession): void {
  cookieStore.set(OSEKKAI_SESSION_COOKIE, encodeOsekkaiSession(session), {
    httpOnly: true,
    // OAuth callbacks are top-level cross-site navigations. Lax sends this
    // signed anonymous-session cookie for that GET; every state-changing API
    // still requires same-origin plus the separate CSRF token.
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/api/osekkai',
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
}

export async function getOrCreateOsekkaiSession(): Promise<OsekkaiSession> {
  const cookieStore = await cookies();
  const current = decodeOsekkaiSession(cookieStore.get(OSEKKAI_SESSION_COOKIE)?.value);
  if (current) {
    return current;
  }

  const created = {
    userId: randomUUID(),
    issuedAtSeconds: Math.floor(Date.now() / 1000),
  };
  setSessionCookie(cookieStore, created);
  return created;
}

export async function requireOsekkaiSession(): Promise<OsekkaiSession> {
  const cookieStore = await cookies();
  const session = decodeOsekkaiSession(cookieStore.get(OSEKKAI_SESSION_COOKIE)?.value);
  if (!session) {
    throw new OsekkaiHttpError(
      'SESSION_REQUIRED',
      'セッションを初期化してから、もう一度お試しください。',
      401,
    );
  }
  return session;
}

export async function clearOsekkaiSession(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set(OSEKKAI_SESSION_COOKIE, '', {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/api/osekkai',
    maxAge: 0,
    expires: new Date(0),
  });
}

export function issueOsekkaiCsrfToken(
  session: OsekkaiSession,
  nowSeconds = Math.floor(Date.now() / 1000),
): { token: string; expiresAt: string } {
  const expiresAtSeconds = nowSeconds + CSRF_TTL_SECONDS;
  const nonce = randomBytes(18).toString('base64url');
  const payload = `${SESSION_VERSION}.${session.userId}.${expiresAtSeconds}.${nonce}`;
  const signature = hmac(payload, sessionSecrets().current);

  return {
    token: `${SESSION_VERSION}.${expiresAtSeconds}.${nonce}.${signature}`,
    expiresAt: new Date(expiresAtSeconds * 1000).toISOString(),
  };
}

export function verifyOsekkaiCsrfToken(
  session: OsekkaiSession,
  token: string | null,
  nowSeconds = Math.floor(Date.now() / 1000),
): boolean {
  if (!token) {
    return false;
  }

  const parts = token.split('.');
  if (parts.length !== 4) {
    return false;
  }

  const [version, expiresAtRaw, nonce, signature] = parts;
  const expiresAtSeconds = Number(expiresAtRaw);
  if (
    version !== SESSION_VERSION ||
    !Number.isSafeInteger(expiresAtSeconds) ||
    expiresAtSeconds < nowSeconds ||
    expiresAtSeconds > nowSeconds + CSRF_TTL_SECONDS + 60 ||
    !/^[A-Za-z0-9_-]{20,64}$/.test(nonce)
  ) {
    return false;
  }

  const payload = `${version}.${session.userId}.${expiresAtRaw}.${nonce}`;
  return validSignature(payload, signature);
}

export function getOsekkaiDataMode(): OsekkaiDataMode {
  if (process.env.NODE_ENV === 'production') {
    return 'live';
  }
  const value = process.env.OSEKKAI_DEMO_MODE?.trim().toLowerCase();
  return value === 'false' || value === '0' || value === 'no' ? 'live' : 'demo';
}
