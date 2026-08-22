import { createHash } from 'crypto';

import { OsekkaiHttpError } from './osekkai-errors';

const DEFAULT_BRIDGE_CONCURRENCY = 4;
const MAX_BRIDGE_CONCURRENCY = 16;
const DEFAULT_BRIDGE_QUEUE_SIZE = 16;
const MAX_BRIDGE_QUEUE_SIZE = 256;
const DEFAULT_BRIDGE_QUEUE_TIMEOUT_MS = 2_000;
const DEFAULT_RATE_LIMIT_WINDOW_MS = 60_000;
const DEFAULT_REQUESTS_PER_WINDOW = 120;
const DEFAULT_SESSION_ISSUES_PER_WINDOW = 60;
const DEFAULT_RATE_LIMIT_MAX_KEYS = 10_000;

const RETRY_AFTER_SECONDS = Symbol('osekkaiRetryAfterSeconds');

type RetryableError = OsekkaiHttpError & {
  [RETRY_AFTER_SECONDS]?: number;
};

function integerInRange(
  raw: string | undefined,
  fallback: number,
  minimum: number,
  maximum: number,
): number {
  if (raw === undefined || raw.trim() === '') {
    return fallback;
  }
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed < minimum) {
    return fallback;
  }
  return Math.min(parsed, maximum);
}

function retryableError(
  code: string,
  message: string,
  status: number,
  retryAfterSeconds: number,
  requestId?: string,
): OsekkaiHttpError {
  const error = new OsekkaiHttpError(code, message, status, requestId) as RetryableError;
  error[RETRY_AFTER_SECONDS] = Math.max(1, Math.ceil(retryAfterSeconds));
  return error;
}

/** Returns a validated Retry-After value without trusting arbitrary thrown objects. */
export function osekkaiRetryAfterSeconds(error: unknown): number | undefined {
  if (!(error instanceof OsekkaiHttpError)) {
    return undefined;
  }
  const value = (error as RetryableError)[RETRY_AFTER_SECONDS];
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 1 && value <= 300
    ? value
    : undefined;
}

type QueuedPermit = {
  done: boolean;
  requestId?: string;
  resolve: (release: () => void) => void;
  reject: (error: unknown) => void;
  timer: ReturnType<typeof setTimeout>;
};

export type BoundedPermitPoolOptions = {
  concurrency: number;
  maxQueue: number;
  waitTimeoutMs: number;
};

/**
 * A small FIFO semaphore with a bounded wait queue. A permit is represented by
 * an idempotent release callback so child-process failures cannot leak capacity.
 */
export class BoundedPermitPool {
  private readonly concurrency: number;
  private readonly maxQueue: number;
  private readonly waitTimeoutMs: number;
  private active = 0;
  private readonly queue: QueuedPermit[] = [];

  constructor(options: BoundedPermitPoolOptions) {
    if (!Number.isSafeInteger(options.concurrency) || options.concurrency < 1) {
      throw new TypeError('concurrency must be a positive integer');
    }
    if (!Number.isSafeInteger(options.maxQueue) || options.maxQueue < 0) {
      throw new TypeError('maxQueue must be a non-negative integer');
    }
    if (!Number.isSafeInteger(options.waitTimeoutMs) || options.waitTimeoutMs < 1) {
      throw new TypeError('waitTimeoutMs must be a positive integer');
    }
    this.concurrency = options.concurrency;
    this.maxQueue = options.maxQueue;
    this.waitTimeoutMs = options.waitTimeoutMs;
  }

  get activeCount(): number {
    return this.active;
  }

  get pendingCount(): number {
    return this.queue.length;
  }

  private releaseCallback(): () => void {
    let released = false;
    return () => {
      if (released) {
        return;
      }
      released = true;
      this.active -= 1;
      this.grantQueuedPermits();
    };
  }

  private grantQueuedPermits(): void {
    while (this.active < this.concurrency) {
      const queued = this.queue.shift();
      if (!queued) {
        return;
      }
      if (queued.done) {
        continue;
      }
      queued.done = true;
      clearTimeout(queued.timer);
      this.active += 1;
      queued.resolve(this.releaseCallback());
    }
  }

  async acquire(requestId?: string): Promise<() => void> {
    if (this.active < this.concurrency) {
      this.active += 1;
      return this.releaseCallback();
    }

    if (this.queue.length >= this.maxQueue) {
      throw retryableError(
        'PYTHON_QUEUE_FULL',
        'The Osekkai engine is busy. Please retry shortly.',
        429,
        1,
        requestId,
      );
    }

    return new Promise<() => void>((resolve, reject) => {
      const queued = {} as QueuedPermit;
      queued.done = false;
      queued.requestId = requestId;
      queued.resolve = resolve;
      queued.reject = reject;
      queued.timer = setTimeout(() => {
        if (queued.done) {
          return;
        }
        queued.done = true;
        const index = this.queue.indexOf(queued);
        if (index >= 0) {
          this.queue.splice(index, 1);
        }
        reject(
          retryableError(
            'PYTHON_QUEUE_TIMEOUT',
            'The Osekkai engine remained busy. Please retry shortly.',
            503,
            1,
            requestId,
          ),
        );
      }, this.waitTimeoutMs);
      this.queue.push(queued);
    });
  }

  async run<T>(task: () => Promise<T> | T, requestId?: string): Promise<T> {
    const release = await this.acquire(requestId);
    try {
      return await task();
    } finally {
      release();
    }
  }
}

type RateLimitRecord = {
  count: number;
  resetAtMs: number;
};

export type FixedWindowRateLimiterOptions = {
  windowMs: number;
  maxKeys: number;
  now?: () => number;
};

export type RateLimitItem = {
  key: string;
  limit: number;
};

/** Instance-local fixed-window limiter with atomic multi-key consumption. */
export class FixedWindowRateLimiter {
  private readonly windowMs: number;
  private readonly maxKeys: number;
  private readonly now: () => number;
  private readonly records = new Map<string, RateLimitRecord>();
  private nextPruneAtMs = 0;

  constructor(options: FixedWindowRateLimiterOptions) {
    if (!Number.isSafeInteger(options.windowMs) || options.windowMs < 1) {
      throw new TypeError('windowMs must be a positive integer');
    }
    if (!Number.isSafeInteger(options.maxKeys) || options.maxKeys < 1) {
      throw new TypeError('maxKeys must be a positive integer');
    }
    this.windowMs = options.windowMs;
    this.maxKeys = options.maxKeys;
    this.now = options.now || Date.now;
  }

  get size(): number {
    return this.records.size;
  }

  private pruneExpired(nowMs: number): void {
    for (const [key, record] of Array.from(this.records.entries())) {
      if (record.resetAtMs <= nowMs) {
        this.records.delete(key);
      }
    }
    this.nextPruneAtMs = nowMs + Math.min(this.windowMs, 5_000);
  }

  consume(items: readonly RateLimitItem[], requestId?: string): void {
    const nowMs = this.now();
    if (nowMs >= this.nextPruneAtMs || this.records.size >= this.maxKeys) {
      this.pruneExpired(nowMs);
    }

    const uniqueItems = new Map<string, number>();
    for (const item of items) {
      if (!item.key || !Number.isSafeInteger(item.limit) || item.limit < 1) {
        throw new TypeError('rate limit items require a key and positive integer limit');
      }
      const previous = uniqueItems.get(item.key);
      uniqueItems.set(item.key, previous === undefined ? item.limit : Math.min(previous, item.limit));
    }

    for (const key of Array.from(uniqueItems.keys())) {
      const record = this.records.get(key);
      if (record && record.resetAtMs <= nowMs) {
        this.records.delete(key);
      }
    }

    let newKeys = 0;
    for (const key of Array.from(uniqueItems.keys())) {
      if (!this.records.has(key)) {
        newKeys += 1;
      }
    }
    if (this.records.size + newKeys > this.maxKeys) {
      let earliestResetAt = nowMs + this.windowMs;
      for (const record of Array.from(this.records.values())) {
        earliestResetAt = Math.min(earliestResetAt, record.resetAtMs);
      }
      throw retryableError(
        'RATE_LIMIT_CAPACITY_EXCEEDED',
        'Request protection is temporarily at capacity. Please retry shortly.',
        503,
        (earliestResetAt - nowMs) / 1_000,
        requestId,
      );
    }

    for (const [key, limit] of Array.from(uniqueItems.entries())) {
      const record = this.records.get(key);
      if (record && record.count >= limit) {
        throw retryableError(
          'RATE_LIMITED',
          'Too many requests. Please wait before trying again.',
          429,
          (record.resetAtMs - nowMs) / 1_000,
          requestId,
        );
      }
    }

    for (const key of Array.from(uniqueItems.keys())) {
      const record = this.records.get(key);
      if (record) {
        record.count += 1;
      } else {
        this.records.set(key, { count: 1, resetAtMs: nowMs + this.windowMs });
      }
    }
  }
}

type RequestRateGuardOptions = {
  requestsPerWindow: number;
  sessionIssuesPerWindow: number;
  windowMs: number;
  maxKeys: number;
  now?: () => number;
};

export type OsekkaiRateLimitIdentity = {
  ipFingerprint: string;
  userId?: string | null;
  issuesSession?: boolean;
  requestId?: string;
};

export class OsekkaiRequestRateGuard {
  private readonly requestsPerWindow: number;
  private readonly sessionIssuesPerWindow: number;
  private readonly limiter: FixedWindowRateLimiter;

  constructor(options: RequestRateGuardOptions) {
    this.requestsPerWindow = options.requestsPerWindow;
    this.sessionIssuesPerWindow = options.sessionIssuesPerWindow;
    this.limiter = new FixedWindowRateLimiter(options);
  }

  check(identity: OsekkaiRateLimitIdentity): void {
    const items: RateLimitItem[] = [
      { key: `request:ip:${identity.ipFingerprint}`, limit: this.requestsPerWindow },
    ];
    if (identity.userId) {
      items.push({ key: `request:user:${identity.userId}`, limit: this.requestsPerWindow });
    }
    if (identity.issuesSession) {
      items.push({
        key: `session-issue:ip:${identity.ipFingerprint}`,
        limit: this.sessionIssuesPerWindow,
      });
    }
    this.limiter.consume(items, identity.requestId);
  }
}

function trustedClientAddress(request: Request): string {
  const trustForwardedHeaders =
    process.env.NODE_ENV !== 'production' ||
    Boolean(process.env.VERCEL) ||
    process.env.OSEKKAI_TRUST_PROXY_IP_HEADERS?.trim().toLowerCase() === 'true';
  if (!trustForwardedHeaders) {
    // A shared key is intentionally fail-safe when a production proxy has not
    // been declared trusted; caller-supplied forwarding headers are ignored.
    return 'unknown';
  }

  const forwarded = request.headers.get('x-forwarded-for')?.split(',', 1)[0]?.trim();
  const candidate =
    forwarded ||
    request.headers.get('x-real-ip')?.trim() ||
    request.headers.get('cf-connecting-ip')?.trim() ||
    'unknown';
  return candidate.slice(0, 256);
}

export function osekkaiClientIpFingerprint(request: Request): string {
  return createHash('sha256').update(trustedClientAddress(request)).digest('hex').slice(0, 32);
}

let bridgePermitPool: BoundedPermitPool | undefined;
let requestRateGuard: OsekkaiRequestRateGuard | undefined;

function getBridgePermitPool(): BoundedPermitPool {
  if (!bridgePermitPool) {
    bridgePermitPool = new BoundedPermitPool({
      concurrency: integerInRange(
        process.env.OSEKKAI_BRIDGE_MAX_CONCURRENCY,
        DEFAULT_BRIDGE_CONCURRENCY,
        1,
        MAX_BRIDGE_CONCURRENCY,
      ),
      maxQueue: integerInRange(
        process.env.OSEKKAI_BRIDGE_MAX_QUEUE,
        DEFAULT_BRIDGE_QUEUE_SIZE,
        0,
        MAX_BRIDGE_QUEUE_SIZE,
      ),
      waitTimeoutMs: integerInRange(
        process.env.OSEKKAI_BRIDGE_QUEUE_TIMEOUT_MS,
        DEFAULT_BRIDGE_QUEUE_TIMEOUT_MS,
        50,
        30_000,
      ),
    });
  }
  return bridgePermitPool;
}

function getRequestRateGuard(): OsekkaiRequestRateGuard {
  if (!requestRateGuard) {
    requestRateGuard = new OsekkaiRequestRateGuard({
      requestsPerWindow: integerInRange(
        process.env.OSEKKAI_RATE_LIMIT_REQUESTS,
        DEFAULT_REQUESTS_PER_WINDOW,
        1,
        2_000,
      ),
      sessionIssuesPerWindow: integerInRange(
        process.env.OSEKKAI_SESSION_ISSUE_RATE_LIMIT,
        DEFAULT_SESSION_ISSUES_PER_WINDOW,
        1,
        500,
      ),
      windowMs: integerInRange(
        process.env.OSEKKAI_RATE_LIMIT_WINDOW_MS,
        DEFAULT_RATE_LIMIT_WINDOW_MS,
        1_000,
        300_000,
      ),
      maxKeys: integerInRange(
        process.env.OSEKKAI_RATE_LIMIT_MAX_KEYS,
        DEFAULT_RATE_LIMIT_MAX_KEYS,
        128,
        50_000,
      ),
    });
  }
  return requestRateGuard;
}

export async function withOsekkaiBridgePermit<T>(
  requestId: string,
  task: () => Promise<T> | T,
): Promise<T> {
  return getBridgePermitPool().run(task, requestId);
}

export function enforceOsekkaiRequestRateLimit(
  request: Request,
  options: { userId?: string | null; issuesSession?: boolean; requestId?: string } = {},
): void {
  getRequestRateGuard().check({
    ipFingerprint: osekkaiClientIpFingerprint(request),
    ...options,
  });
}

/** Test-only reset for environment-based singleton configuration. */
export function resetOsekkaiResourceGuardsForTests(): void {
  bridgePermitPool = undefined;
  requestRateGuard = undefined;
}
