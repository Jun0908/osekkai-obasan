import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../osekkai-user', () => ({
  OSEKKAI_CSRF_HEADER: 'x-osekkai-csrf',
  OSEKKAI_SESSION_COOKIE: '__Host-osekkai_session',
  clearOsekkaiSession: vi.fn(async () => undefined),
  decodeOsekkaiSession: vi.fn(() => null),
  getOrCreateOsekkaiSession: vi.fn(async () => ({
    userId: '11111111-1111-4111-8111-111111111111',
    issuedAtSeconds: 1_700_000_000,
  })),
  getOsekkaiDataMode: vi.fn(() => 'demo'),
  isValidOsekkaiUserId: vi.fn(
    (value: unknown) => value === '11111111-1111-4111-8111-111111111111',
  ),
  issueOsekkaiCsrfToken: vi.fn(() => ({
    token: 'csrf-token',
    expiresAt: '2026-08-22T10:00:00+09:00',
  })),
  requireOsekkaiSession: vi.fn(async () => ({
    userId: '11111111-1111-4111-8111-111111111111',
    issuedAtSeconds: 1_700_000_000,
  })),
  verifyOsekkaiCsrfToken: vi.fn(() => true),
}));

import { interventionsPost, profileUpdate } from '../osekkai-route-handlers';
import { resetOsekkaiResourceGuardsForTests } from '../osekkai-resource-guards';

const EPISODE_ID = '33333333-3333-4333-8333-333333333333';

function mutationRequest(path: string, body: Record<string, unknown>): Request {
  return new Request(`http://localhost:3000/api/osekkai${path}`, {
    method: 'POST',
    headers: {
      host: 'localhost:3000',
      origin: 'http://localhost:3000',
      'content-type': 'application/json',
      'x-osekkai-csrf': 'csrf-token',
      'x-forwarded-for': '127.0.0.1',
    },
    body: JSON.stringify({ ...body, idempotencyKey: 'http-validator-test-0001' }),
  });
}

async function expectStrictValidationFailure(response: Response): Promise<void> {
  expect(response.status).toBe(400);
  expect(response.headers.get('cache-control')).toContain('no-store');
  const envelope = await response.json();
  expect(Object.keys(envelope).sort()).toEqual(['error', 'requestId']);
  expect(envelope.error).toEqual({
    code: 'VALIDATION_ERROR',
    message: 'リクエスト内容を確認してください。',
  });
  expect(envelope.requestId).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
}

describe('Osekkai HTTP mutation request schemas', () => {
  afterEach(() => {
    resetOsekkaiResourceGuardsForTests();
  });

  it('rejects an invalid normalized profile patch before Python starts', async () => {
    const response = await profileUpdate(
      mutationRequest('/profile', {
        operation: 'update_settings',
        updates: { memoryConsent: 'yes' },
      }),
    );

    await expectStrictValidationFailure(response);
  });

  it('rejects an invalid normalized intervention enum before Python starts', async () => {
    const response = await interventionsPost(
      mutationRequest('/interventions', {
        episodeId: EPISODE_ID,
        event: 'teleport',
      }),
    );

    await expectStrictValidationFailure(response);
  });
});

