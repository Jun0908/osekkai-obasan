import { afterEach, describe, expect, it, vi } from 'vitest';

import { assertSafeGetRequest, osekkaiFailure } from '../osekkai-request';
import {
  BoundedPermitPool,
  FixedWindowRateLimiter,
  OsekkaiRequestRateGuard,
  osekkaiClientIpFingerprint,
  resetOsekkaiResourceGuardsForTests,
  withOsekkaiBridgePermit,
} from '../osekkai-resource-guards';
import { encodeOsekkaiSession, OSEKKAI_SESSION_COOKIE } from '../osekkai-user';

describe('Osekkai fixed-window request protection', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    resetOsekkaiResourceGuardsForTests();
  });

  it('enforces the limit, emits Retry-After, and reopens after the time window', async () => {
    let nowMs = 1_000;
    const limiter = new FixedWindowRateLimiter({
      windowMs: 60_000,
      maxKeys: 8,
      now: () => nowMs,
    });
    const items = [
      { key: 'request:ip:one', limit: 2 },
      { key: 'request:user:one', limit: 2 },
    ];

    limiter.consume(items);
    limiter.consume(items);

    let error: unknown;
    try {
      limiter.consume(items, 'request-id');
    } catch (caught) {
      error = caught;
    }
    expect(error).toMatchObject({ code: 'RATE_LIMITED', status: 429 });
    const response = osekkaiFailure(error, 'fallback-id');
    expect(response.status).toBe(429);
    expect(response.headers.get('retry-after')).toBe('60');

    nowMs += 60_001;
    expect(() => limiter.consume(items)).not.toThrow();
  });

  it('bounds the key map and removes expired keys before admitting replacements', () => {
    let nowMs = 0;
    const limiter = new FixedWindowRateLimiter({
      windowMs: 1_000,
      maxKeys: 1,
      now: () => nowMs,
    });

    limiter.consume([{ key: 'first', limit: 10 }]);
    expect(() => limiter.consume([{ key: 'second', limit: 10 }])).toThrow(
      expect.objectContaining({ code: 'RATE_LIMIT_CAPACITY_EXCEEDED', status: 503 }),
    );
    expect(limiter.size).toBe(1);

    nowMs = 1_001;
    expect(() => limiter.consume([{ key: 'second', limit: 10 }])).not.toThrow();
    expect(limiter.size).toBe(1);
  });

  it('limits session issuance by IP and API use by both IP and user', () => {
    let nowMs = 0;
    const sessionGuard = new OsekkaiRequestRateGuard({
      requestsPerWindow: 3,
      sessionIssuesPerWindow: 1,
      windowMs: 60_000,
      maxKeys: 32,
      now: () => nowMs,
    });
    sessionGuard.check({ ipFingerprint: 'ip-one', issuesSession: true });
    expect(() =>
      sessionGuard.check({ ipFingerprint: 'ip-one', issuesSession: true }),
    ).toThrow(expect.objectContaining({ code: 'RATE_LIMITED', status: 429 }));

    const apiGuard = new OsekkaiRequestRateGuard({
      requestsPerWindow: 2,
      sessionIssuesPerWindow: 10,
      windowMs: 60_000,
      maxKeys: 32,
      now: () => nowMs,
    });
    apiGuard.check({ ipFingerprint: 'ip-a', userId: 'user-one' });
    apiGuard.check({ ipFingerprint: 'ip-b', userId: 'user-one' });
    expect(() =>
      apiGuard.check({ ipFingerprint: 'ip-c', userId: 'user-one' }),
    ).toThrow(expect.objectContaining({ code: 'RATE_LIMITED' }));

    const ipGuard = new OsekkaiRequestRateGuard({
      requestsPerWindow: 2,
      sessionIssuesPerWindow: 10,
      windowMs: 60_000,
      maxKeys: 32,
      now: () => nowMs,
    });
    ipGuard.check({ ipFingerprint: 'shared-ip', userId: 'user-a' });
    ipGuard.check({ ipFingerprint: 'shared-ip', userId: 'user-b' });
    expect(() =>
      ipGuard.check({ ipFingerprint: 'shared-ip', userId: 'user-c' }),
    ).toThrow(expect.objectContaining({ code: 'RATE_LIMITED' }));

    nowMs += 60_001;
    expect(() =>
      sessionGuard.check({ ipFingerprint: 'ip-one', issuesSession: true }),
    ).not.toThrow();
  });

  it('ignores spoofable forwarding headers by default in production', () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('VERCEL', '');
    vi.stubEnv('OSEKKAI_TRUST_PROXY_IP_HEADERS', '');
    const first = new Request('https://example.test/api/osekkai/session', {
      headers: { 'x-forwarded-for': '192.0.2.1' },
    });
    const second = new Request('https://example.test/api/osekkai/session', {
      headers: { 'x-forwarded-for': '198.51.100.2' },
    });
    expect(osekkaiClientIpFingerprint(first)).toBe(osekkaiClientIpFingerprint(second));
  });

  it('connects anonymous issuance and signed-user limits to the shared GET boundary', () => {
    vi.stubEnv('NODE_ENV', 'test');
    vi.stubEnv('OSEKKAI_SESSION_SECRET', '0123456789abcdef'.repeat(4));
    vi.stubEnv('OSEKKAI_RATE_LIMIT_REQUESTS', '10');
    vi.stubEnv('OSEKKAI_SESSION_ISSUE_RATE_LIMIT', '1');
    resetOsekkaiResourceGuardsForTests();
    const anonymous = () =>
      new Request('http://localhost:3000/api/osekkai/session', {
        headers: { 'x-forwarded-for': '192.0.2.10' },
      });
    expect(() => assertSafeGetRequest(anonymous())).not.toThrow();
    expect(() => assertSafeGetRequest(anonymous())).toThrow(
      expect.objectContaining({ code: 'RATE_LIMITED', status: 429 }),
    );

    vi.stubEnv('OSEKKAI_RATE_LIMIT_REQUESTS', '1');
    vi.stubEnv('OSEKKAI_SESSION_ISSUE_RATE_LIMIT', '10');
    resetOsekkaiResourceGuardsForTests();
    const encoded = encodeOsekkaiSession({
      userId: '00000000-0000-4000-8000-000000000001',
      issuedAtSeconds: Math.floor(Date.now() / 1_000),
    });
    const signed = (ip: string) =>
      new Request('http://localhost:3000/api/osekkai/profile', {
        headers: {
          cookie: `${OSEKKAI_SESSION_COOKIE}=${encoded}`,
          'x-forwarded-for': ip,
        },
      });
    expect(() => assertSafeGetRequest(signed('192.0.2.11'))).not.toThrow();
    expect(() => assertSafeGetRequest(signed('192.0.2.12'))).toThrow(
      expect.objectContaining({ code: 'RATE_LIMITED', status: 429 }),
    );
  });
});

describe('Osekkai Python bridge permit pool', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    resetOsekkaiResourceGuardsForTests();
  });

  async function configuredConcurrency(rawValue: string, taskCount: number): Promise<number> {
    vi.stubEnv('OSEKKAI_BRIDGE_MAX_CONCURRENCY', rawValue);
    vi.stubEnv('OSEKKAI_BRIDGE_MAX_QUEUE', '32');
    resetOsekkaiResourceGuardsForTests();
    let releaseGate: () => void = () => void 0;
    const gate = new Promise<void>((resolve) => {
      releaseGate = resolve;
    });
    let started = 0;
    const tasks = Array.from({ length: taskCount }, (_, index) =>
      withOsekkaiBridgePermit(`request-${index}`, async () => {
        started += 1;
        await gate;
      }),
    );
    const expected = rawValue === '' ? Math.min(4, taskCount) : Math.min(16, taskCount);
    await vi.waitFor(() => expect(started).toBe(expected));
    const observed = started;
    releaseGate();
    await Promise.all(tasks);
    return observed;
  }

  it('uses a safe default of four and clamps environment concurrency to sixteen', async () => {
    await expect(configuredConcurrency('', 5)).resolves.toBe(4);
    await expect(configuredConcurrency('999', 17)).resolves.toBe(16);
  });

  it('bounds active work and its FIFO queue', async () => {
    const pool = new BoundedPermitPool({ concurrency: 1, maxQueue: 1, waitTimeoutMs: 5_000 });
    let finishFirst: (() => void) | undefined;
    const first = pool.run(
      () =>
        new Promise<void>((resolve) => {
          finishFirst = resolve;
        }),
    );
    await Promise.resolve();

    const second = pool.run(async () => 'second');
    await Promise.resolve();
    expect(pool.activeCount).toBe(1);
    expect(pool.pendingCount).toBe(1);
    await expect(pool.run(async () => 'third')).rejects.toMatchObject({
      code: 'PYTHON_QUEUE_FULL',
      status: 429,
    });

    finishFirst?.();
    await first;
    await expect(second).resolves.toBe('second');
    expect(pool.activeCount).toBe(0);
    expect(pool.pendingCount).toBe(0);
  });

  it('does not leak a permit when the protected task throws', async () => {
    const pool = new BoundedPermitPool({ concurrency: 1, maxQueue: 1, waitTimeoutMs: 1_000 });
    await expect(
      pool.run(async () => {
        throw new Error('child failed');
      }),
    ).rejects.toThrow('child failed');

    expect(pool.activeCount).toBe(0);
    await expect(pool.run(async () => 42)).resolves.toBe(42);
    expect(pool.activeCount).toBe(0);
  });

  it('removes timed-out waiters without leaking queue or active capacity', async () => {
    vi.useFakeTimers();
    const pool = new BoundedPermitPool({ concurrency: 1, maxQueue: 1, waitTimeoutMs: 100 });
    const release = await pool.acquire();
    const waiting = pool.acquire('queued-request');
    const waitingRejection = expect(waiting).rejects.toMatchObject({
      code: 'PYTHON_QUEUE_TIMEOUT',
      status: 503,
    });
    expect(pool.pendingCount).toBe(1);

    await vi.advanceTimersByTimeAsync(101);
    await waitingRejection;
    expect(pool.pendingCount).toBe(0);

    release();
    expect(pool.activeCount).toBe(0);
    const releaseAgain = await pool.acquire();
    releaseAgain();
    expect(pool.activeCount).toBe(0);
  });
});
