import { describe, expect, it } from 'vitest';

import { isCliResponse } from '../osekkai-openclaw-bridge';

const REQUEST_ID = '00000000-0000-4000-8000-000000000001';

describe('Python bridge envelope', () => {
  it('accepts only the documented success keys and replay marker', () => {
    expect(isCliResponse({ ok: true, requestId: REQUEST_ID, data: {} }, REQUEST_ID)).toBe(true);
    expect(
      isCliResponse(
        { ok: true, requestId: REQUEST_ID, data: {}, idempotentReplay: true },
        REQUEST_ID,
      ),
    ).toBe(true);
    expect(
      isCliResponse({ ok: true, requestId: REQUEST_ID, data: {}, debug: 'secret' }, REQUEST_ID),
    ).toBe(false);
    expect(
      isCliResponse(
        { ok: true, requestId: REQUEST_ID, data: {}, idempotentReplay: false },
        REQUEST_ID,
      ),
    ).toBe(false);
  });

  it('accepts only an exact public error object', () => {
    expect(
      isCliResponse(
        { ok: false, requestId: REQUEST_ID, error: { code: 'INVALID', message: 'invalid' } },
        REQUEST_ID,
      ),
    ).toBe(true);
    expect(
      isCliResponse(
        {
          ok: false,
          requestId: REQUEST_ID,
          error: { code: 'INVALID', message: 'invalid', traceback: 'private' },
        },
        REQUEST_ID,
      ),
    ).toBe(false);
  });
});
