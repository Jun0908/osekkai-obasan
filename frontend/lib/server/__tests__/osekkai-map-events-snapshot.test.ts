import { afterEach, describe, expect, it, vi } from 'vitest';

import { OsekkaiHttpError } from '../osekkai-errors';
import mapEventsSnapshot from '@/lib/osekkai/map-events-snapshot.generated.json';

const storeMocks = vi.hoisted(() => ({
  getOsekkaiMapEvents: vi.fn(),
}));

vi.mock('../osekkai-store', () => storeMocks);

vi.mock('../osekkai-user', () => ({
  getOrCreateOsekkaiSession: vi.fn(async () => ({
    userId: '11111111-1111-4111-8111-111111111111',
    issuedAtSeconds: 1_700_000_000,
  })),
}));

import { mapEventsGet } from '../osekkai-route-handlers';

function getRequest(query = ''): Request {
  return new Request(`http://localhost:3000/api/osekkai/map-events${query}`, {
    headers: { host: 'localhost:3000', 'x-forwarded-for': '127.0.0.1' },
  });
}

describe('mapEventsGet Vercel fallback', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('serves the live Python result untouched when the bridge succeeds', async () => {
    storeMocks.getOsekkaiMapEvents.mockResolvedValue({
      data: { schemaVersion: '1.0', events: [], counts: { returned: 0 }, nextOffset: null },
      requestId: 'req-live',
    });

    const response = await mapEventsGet(getRequest());
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.data.events).toEqual([]);
    expect(body.requestId).toBe('req-live');
  });

  it('falls back to the bundled snapshot when Python is unavailable (e.g. on Vercel)', async () => {
    storeMocks.getOsekkaiMapEvents.mockRejectedValue(
      new OsekkaiHttpError('PYTHON_CLI_NOT_FOUND', 'python not found', 502),
    );

    const response = await mapEventsGet(getRequest('?offset=0&limit=5'));
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.data.events).toEqual(mapEventsSnapshot.events.slice(0, 5));
    expect(body.data.events.length).toBeGreaterThan(0);
    expect(body.data.counts.returned).toBe(body.data.events.length);
  });

  it('re-throws non-Python errors instead of masking them with the snapshot', async () => {
    storeMocks.getOsekkaiMapEvents.mockRejectedValue(
      new OsekkaiHttpError('VALIDATION_ERROR', 'bad request', 400),
    );

    const response = await mapEventsGet(getRequest());

    expect(response.status).toBe(400);
  });
});
