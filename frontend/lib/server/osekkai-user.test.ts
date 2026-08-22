import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { decodeOsekkaiSession, encodeOsekkaiSession } from "./osekkai-user";

const originalSecret = process.env.OSEKKAI_SESSION_SECRET;
const originalPrevious = process.env.OSEKKAI_SESSION_SECRET_PREVIOUS;

beforeEach(() => {
  process.env.OSEKKAI_SESSION_SECRET = "current-secret-that-is-at-least-thirty-two-bytes";
  delete process.env.OSEKKAI_SESSION_SECRET_PREVIOUS;
});

afterEach(() => {
  if (originalSecret === undefined) delete process.env.OSEKKAI_SESSION_SECRET;
  else process.env.OSEKKAI_SESSION_SECRET = originalSecret;
  if (originalPrevious === undefined) delete process.env.OSEKKAI_SESSION_SECRET_PREVIOUS;
  else process.env.OSEKKAI_SESSION_SECRET_PREVIOUS = originalPrevious;
});

describe("signed Osekkai sessions", () => {
  it("accepts an untampered current signature", () => {
    const session = {
      userId: "20000000-0000-4000-8000-000000000002",
      issuedAtSeconds: 1_700_000_000
    };
    const encoded = encodeOsekkaiSession(session);
    expect(decodeOsekkaiSession(encoded, 1_700_000_100)).toEqual(session);
  });

  it("rejects tampering and expiration", () => {
    const session = {
      userId: "20000000-0000-4000-8000-000000000002",
      issuedAtSeconds: 1_700_000_000
    };
    const encoded = encodeOsekkaiSession(session);
    expect(decodeOsekkaiSession(`${encoded.slice(0, -1)}x`, 1_700_000_100)).toBeNull();
    expect(decodeOsekkaiSession(encoded, 1_700_000_000 + 31 * 24 * 60 * 60)).toBeNull();
  });

  it("accepts the previous secret only for verification during rotation", () => {
    const session = {
      userId: "20000000-0000-4000-8000-000000000002",
      issuedAtSeconds: 1_700_000_000
    };
    const encodedWithOldKey = encodeOsekkaiSession(session);
    process.env.OSEKKAI_SESSION_SECRET_PREVIOUS = process.env.OSEKKAI_SESSION_SECRET;
    process.env.OSEKKAI_SESSION_SECRET = "replacement-secret-that-is-at-least-thirty-two-bytes";
    expect(decodeOsekkaiSession(encodedWithOldKey, 1_700_000_100)).toEqual(session);
  });
});
