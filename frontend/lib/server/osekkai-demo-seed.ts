import { createHash } from 'crypto';

import type { OsekkaiCommandResult } from './osekkai-contract';
import { seedOsekkaiDemo } from './osekkai-store';

export type OsekkaiDemoSeedResult = {
  schemaVersion: '1.0';
  dataMode: 'demo';
  seeded: boolean;
  profile: unknown;
};

const seedFlights = new Map<
  string,
  Promise<OsekkaiCommandResult<OsekkaiDemoSeedResult>>
>();

function automaticSeedIdempotencyKey(userId: string): string {
  const digest = createHash('sha256')
    .update(`osekkai:auto-demo-seed:${userId}`, 'utf8')
    .digest('hex')
    .slice(0, 40);
  return `demo-seed-${digest}`;
}

/**
 * Coalesces duplicate browser/StrictMode initialization attempts. The actual
 * untouched-state check and seed write are one atomic operation inside the
 * Python store's per-user lock; Node never performs a check-then-patch.
 */
export function ensureOsekkaiDemoSeed(
  userId: string,
): Promise<OsekkaiCommandResult<OsekkaiDemoSeedResult>> {
  const existing = seedFlights.get(userId);
  if (existing) return existing;

  const pending = seedOsekkaiDemo<OsekkaiDemoSeedResult>(
    userId,
    automaticSeedIdempotencyKey(userId),
  );

  seedFlights.set(userId, pending);
  const clearFlight = () => {
    if (seedFlights.get(userId) === pending) {
      seedFlights.delete(userId);
    }
  };
  void pending.then(clearFlight, clearFlight);
  return pending;
}

export function resetOsekkaiDemoSeedFlightsForTests(): void {
  seedFlights.clear();
}
