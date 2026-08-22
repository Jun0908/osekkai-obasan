import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  clearOsekkaiSession,
  getOsekkaiSession,
  OsekkaiApiError,
} from './api-client';

const REQUEST_ID = '11111111-1111-4111-8111-111111111111';

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify({ data, requestId: REQUEST_ID }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

const validSession = {
  csrfToken: 'v1.valid-token',
  dataMode: 'demo' as const,
  expiresAt: '2026-08-22T10:00:00+09:00',
};

describe('Osekkai session client', () => {
  afterEach(() => {
    clearOsekkaiSession();
    vi.unstubAllGlobals();
  });

  it('clears a cached promise when session validation fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ csrfToken: '', dataMode: 'demo', expiresAt: 'not-a-date' }),
      )
      .mockResolvedValueOnce(
        jsonResponse(validSession),
      );
    vi.stubGlobal('fetch', fetchMock);

    await expect(getOsekkaiSession()).rejects.toBeInstanceOf(OsekkaiApiError);
    await expect(getOsekkaiSession()).resolves.toMatchObject({
      csrfToken: 'v1.valid-token',
      dataMode: 'demo',
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it.each([
    { data: validSession },
    { data: validSession, requestId: 'not-a-uuid' },
    { data: validSession, requestId: REQUEST_ID, extra: true },
    validSession,
  ])('rejects a non-exact success envelope: %j', async (payload) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    await expect(getOsekkaiSession()).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
      status: 502,
    });
  });

  it('preserves a strict failure envelope classification', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: 'CSRF_INVALID', message: 'CSRF token is invalid.' },
            requestId: REQUEST_ID,
          }),
          { status: 403, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    );

    await expect(getOsekkaiSession()).rejects.toMatchObject({
      code: 'CSRF_INVALID',
      status: 403,
      requestId: REQUEST_ID,
    });
  });

  it.each([
    { error: { code: 'FAILED' }, requestId: REQUEST_ID },
    { error: { code: 'FAILED', message: 'failed', detail: 'leak' }, requestId: REQUEST_ID },
    { error: { code: 'FAILED', message: 'failed' }, requestId: 'not-a-uuid' },
    { data: null, requestId: REQUEST_ID },
  ])('rejects a malformed failure envelope: %j', async (payload) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(payload), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    await expect(getOsekkaiSession()).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
      status: 502,
    });
  });
});
