import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  decodeOsekkaiSession,
  encodeOsekkaiSession,
  getOsekkaiDataMode,
  issueOsekkaiCsrfToken,
  verifyOsekkaiCsrfToken,
  type OsekkaiSession,
} from '../osekkai-user';

const session: OsekkaiSession = {
  userId: '00000000-0000-4000-8000-000000000001',
  issuedAtSeconds: 1_700_000_000,
};

describe('signed Osekkai session', () => {
  beforeEach(() => {
    vi.stubEnv('NODE_ENV', 'test');
    vi.stubEnv('OSEKKAI_SESSION_SECRET', 'a'.repeat(64));
    vi.stubEnv('OSEKKAI_SESSION_SECRET_PREVIOUS', '');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('round-trips a valid signed session and rejects tampering', () => {
    const encoded = encodeOsekkaiSession(session);
    expect(decodeOsekkaiSession(encoded, session.issuedAtSeconds + 60)).toEqual(session);
    expect(decodeOsekkaiSession(`${encoded.slice(0, -1)}x`, session.issuedAtSeconds + 60)).toBeNull();
  });

  it('rejects sessions beyond the 30 day lifetime', () => {
    const encoded = encodeOsekkaiSession(session);
    expect(decodeOsekkaiSession(encoded, session.issuedAtSeconds + 31 * 24 * 60 * 60)).toBeNull();
  });

  it('binds the short-lived CSRF token to one session', () => {
    const csrf = issueOsekkaiCsrfToken(session, session.issuedAtSeconds);
    expect(verifyOsekkaiCsrfToken(session, csrf.token, session.issuedAtSeconds + 599)).toBe(true);
    expect(verifyOsekkaiCsrfToken(session, csrf.token, session.issuedAtSeconds + 601)).toBe(false);
    expect(
      verifyOsekkaiCsrfToken(
        { ...session, userId: '00000000-0000-4000-8000-000000000002' },
        csrf.token,
        session.issuedAtSeconds + 1,
      ),
    ).toBe(false);
  });

  it('defaults to the offline demo mode', () => {
    vi.stubEnv('OSEKKAI_DEMO_MODE', '');
    expect(getOsekkaiDataMode()).toBe('demo');
    vi.stubEnv('OSEKKAI_DEMO_MODE', 'false');
    expect(getOsekkaiDataMode()).toBe('live');
    vi.stubEnv('OSEKKAI_DEMO_MODE', 'no');
    expect(getOsekkaiDataMode()).toBe('live');
  });

  it('fails closed to live mode in production even when demo is requested', () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('OSEKKAI_DEMO_MODE', 'true');
    expect(getOsekkaiDataMode()).toBe('live');
    vi.stubEnv('OSEKKAI_DEMO_MODE', '');
    expect(getOsekkaiDataMode()).toBe('live');
  });

  it('rejects a weak previous signing key in production', () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('OSEKKAI_SESSION_SECRET', '0123456789abcdef'.repeat(4));
    vi.stubEnv('OSEKKAI_SESSION_SECRET_PREVIOUS', 'weak-old-key');
    expect(() => encodeOsekkaiSession(session)).toThrow('セッション設定が完了していません。');
  });

  it('rejects the public .env.example value as the current production key', () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('OSEKKAI_SESSION_SECRET', 'replace-with-at-least-32-random-characters');
    vi.stubEnv('OSEKKAI_SESSION_SECRET_PREVIOUS', '');
    expect(() => encodeOsekkaiSession(session)).toThrow('セッション設定が完了していません。');
  });

  it('rejects a replace-with placeholder as the previous production key', () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('OSEKKAI_SESSION_SECRET', '0123456789abcdef'.repeat(4));
    vi.stubEnv('OSEKKAI_SESSION_SECRET_PREVIOUS', 'replace-with-a-previous-random-secret-value');
    expect(() => encodeOsekkaiSession(session)).toThrow('セッション設定が完了していません。');
  });
});
