import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../osekkai-user', () => ({
  OSEKKAI_CSRF_HEADER: 'x-osekkai-csrf',
  requireOsekkaiSession: vi.fn(async () => ({
    userId: '00000000-0000-4000-8000-000000000001',
    issuedAtSeconds: 1_700_000_000,
  })),
  verifyOsekkaiCsrfToken: vi.fn(() => true),
}));

import { OsekkaiHttpError } from '../osekkai-errors';
import {
  assertSafeGetRequest,
  parseMutationRequest,
  readJsonObject,
} from '../osekkai-request';
import { verifyOsekkaiCsrfToken } from '../osekkai-user';

function mutationRequest(body: string, headers: Record<string, string> = {}): Request {
  return new Request('http://localhost:3000/api/osekkai/chat', {
    method: 'POST',
    headers: {
      host: 'localhost:3000',
      origin: 'http://localhost:3000',
      'content-type': 'application/json',
      'x-osekkai-csrf': 'csrf-token',
      ...headers,
    },
    body,
  });
}

async function expectCode(promise: Promise<unknown>, code: string) {
  await expect(promise).rejects.toMatchObject({ code } satisfies Partial<OsekkaiHttpError>);
}

describe('Osekkai request boundary', () => {
  beforeEach(() => {
    vi.mocked(verifyOsekkaiCsrfToken).mockReturnValue(true);
  });

  it('accepts same-origin JSON with a valid idempotency key', async () => {
    const parsed = await parseMutationRequest(
      mutationRequest('{"message":"hello","idempotencyKey":"chat-12345678"}'),
    );
    expect(parsed.body.message).toBe('hello');
    expect(parsed.idempotencyKey).toBe('chat-12345678');
  });

  it('rejects a foreign origin before invoking the domain', async () => {
    await expectCode(
      parseMutationRequest(
        mutationRequest('{"idempotencyKey":"chat-12345678"}', {
          origin: 'https://evil.example',
        }),
      ),
      'ORIGIN_MISMATCH',
    );
  });

  it('rejects invalid content type and CSRF', async () => {
    await expectCode(
      parseMutationRequest(
        mutationRequest('{"idempotencyKey":"chat-12345678"}', {
          'content-type': 'text/plain',
        }),
      ),
      'UNSUPPORTED_MEDIA_TYPE',
    );

    vi.mocked(verifyOsekkaiCsrfToken).mockReturnValue(false);
    await expectCode(
      parseMutationRequest(mutationRequest('{"idempotencyKey":"chat-12345678"}')),
      'CSRF_TOKEN_INVALID',
    );
  });

  it('rejects user identity in body or query', async () => {
    await expectCode(
      parseMutationRequest(
        mutationRequest(
          '{"nested":{"user_id":"00000000-0000-4000-8000-000000000001"},"idempotencyKey":"chat-12345678"}',
        ),
      ),
      'USER_ID_FORBIDDEN',
    );

    expect(() =>
      assertSafeGetRequest(
        new Request('http://localhost:3000/api/osekkai/profile?userId=attacker'),
      ),
    ).toThrowError(expect.objectContaining({ code: 'USER_ID_FORBIDDEN' }));
  });

  it('enforces the streamed body limit', async () => {
    await expectCode(
      readJsonObject(mutationRequest(JSON.stringify({ value: 'x'.repeat(70_000) }))),
      'BODY_TOO_LARGE',
    );
  });

  it('rejects missing or conflicting idempotency keys', async () => {
    await expectCode(parseMutationRequest(mutationRequest('{"message":"hello"}')), 'IDEMPOTENCY_KEY_REQUIRED');
    await expectCode(
      parseMutationRequest(
        mutationRequest('{"idempotencyKey":42}', {
          'idempotency-key': 'header-12345678',
        }),
      ),
      'IDEMPOTENCY_KEY_REQUIRED',
    );
    await expectCode(
      parseMutationRequest(
        mutationRequest('{"idempotencyKey":"body-12345678"}', {
          'idempotency-key': 'header-12345678',
        }),
      ),
      'IDEMPOTENCY_KEY_MISMATCH',
    );
  });
});
