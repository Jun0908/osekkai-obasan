import { afterEach, describe, expect, it, vi } from 'vitest';

const storeMocks = vi.hoisted(() => ({
  seedOsekkaiDemo: vi.fn(),
}));

vi.mock('../osekkai-store', () => storeMocks);

import {
  ensureOsekkaiDemoSeed,
  resetOsekkaiDemoSeedFlightsForTests,
} from '../osekkai-demo-seed';

const USER_ID = '11111111-1111-4111-8111-111111111111';
const REQUEST_ID = '22222222-2222-4222-8222-222222222222';

afterEach(() => {
  resetOsekkaiDemoSeedFlightsForTests();
  vi.clearAllMocks();
});

describe('atomic demo seed boundary', () => {
  it('coalesces duplicate initialization into one atomic Python command', async () => {
    let resolveSeed!: (value: {
      data: { schemaVersion: '1.0'; dataMode: 'demo'; seeded: boolean; profile: object };
      requestId: string;
    }) => void;
    const seedPromise = new Promise<{
      data: { schemaVersion: '1.0'; dataMode: 'demo'; seeded: boolean; profile: object };
      requestId: string;
    }>((resolve) => {
      resolveSeed = resolve;
    });
    storeMocks.seedOsekkaiDemo.mockReturnValue(seedPromise);

    const first = ensureOsekkaiDemoSeed(USER_ID);
    const duplicate = ensureOsekkaiDemoSeed(USER_ID);
    resolveSeed({
      data: {
        schemaVersion: '1.0',
        dataMode: 'demo',
        seeded: true,
        profile: { userId: USER_ID },
      },
      requestId: REQUEST_ID,
    });

    const [firstResult, duplicateResult] = await Promise.all([first, duplicate]);
    expect(firstResult).toEqual(duplicateResult);
    expect(firstResult.data.seeded).toBe(true);
    expect(storeMocks.seedOsekkaiDemo).toHaveBeenCalledTimes(1);
    expect(storeMocks.seedOsekkaiDemo).toHaveBeenCalledWith(
      USER_ID,
      expect.stringMatching(/^demo-seed-[0-9a-f]{40}$/),
    );
  });

  it('passes through seeded=false for existing progress without a Node-side patch', async () => {
    storeMocks.seedOsekkaiDemo.mockResolvedValue({
      data: {
        schemaVersion: '1.0',
        dataMode: 'demo',
        seeded: false,
        profile: { userId: USER_ID, pushConsent: false },
      },
      requestId: REQUEST_ID,
    });

    const result = await ensureOsekkaiDemoSeed(USER_ID);

    expect(result.data.seeded).toBe(false);
    expect(result.data.profile).toMatchObject({
      userId: USER_ID,
      pushConsent: false,
    });
    expect(storeMocks.seedOsekkaiDemo).toHaveBeenCalledTimes(1);
  });
});
