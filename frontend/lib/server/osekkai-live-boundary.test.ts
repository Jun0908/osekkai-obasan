import { describe, expect, it } from 'vitest';

import { OSEKKAI_COMMANDS } from './osekkai-commands';
import { validateOsekkaiCommandPayload } from './osekkai-request-validation';
import { validateOsekkaiCommandData } from './osekkai-response-validation';

const USER_ID = '11111111-1111-4111-8111-111111111111';

describe('live Python boundary', () => {
  it('accepts only bounded ephemeral coordinates for one Event route', () => {
    expect(validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.eventRoute, {
      eventId: 'event-1', origin: { latitude: 35.6812, longitude: 139.7671 },
    })).toEqual({ eventId: 'event-1', origin: { latitude: 35.6812, longitude: 139.7671 } });
    expect(() => validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.eventRoute, {
      eventId: 'event-1', origin: { latitude: 999, longitude: 139.7671 }, persist: true,
    })).toThrow();
  });

  it('validates source sync controls and rejects browser provider data', () => {
    expect(validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.sourcesSync, { force: true })).toEqual({ force: true });
    expect(() => validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.sourcesSync, {
      force: true, events: [{ title: 'browser supplied' }],
    })).toThrow();
  });

  it('rejects malformed Event Mesh data returned by Python', () => {
    expect(() => validateOsekkaiCommandData(
      OSEKKAI_COMMANDS.events,
      {},
      {
        schemaVersion: '1.0', dataMode: 'live', generatedAt: '2026-08-23T09:00:00+09:00',
        events: [{ title: 'not canonical' }], eligibleEvents: [], excludedEvents: [],
        series: [], communities: [], providerErrors: [],
      },
      USER_ID,
    )).toThrow();
  });

  it('accepts only the exact FreeBusy Calendar callback shape', () => {
    const state = `g${'a'.repeat(40)}`;
    expect(validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.calendarCallback, { state, code: 'oauth-code' })).toEqual({ state, code: 'oauth-code' });
    expect(() => validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.calendarCallback, { state, code: 'oauth-code', scope: 'calendar.readonly' })).toThrow();
  });
});
