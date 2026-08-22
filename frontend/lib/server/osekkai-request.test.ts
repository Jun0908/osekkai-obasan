import { describe, expect, it } from "vitest";

import { assertSafeGetRequest, readJsonObject } from "./osekkai-request";

describe("Osekkai request validation", () => {
  it("rejects userId anywhere in a JSON mutation body", async () => {
    const request = new Request("http://localhost/api/osekkai/profile", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patch: { nested: { user_id: "forged" } } })
    });
    await expect(readJsonObject(request)).rejects.toMatchObject({ code: "USER_ID_FORBIDDEN" });
  });

  it("rejects oversized streamed bodies", async () => {
    const request = new Request("http://localhost/api/osekkai/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "x".repeat(256) })
    });
    await expect(readJsonObject(request, 64)).rejects.toMatchObject({ code: "BODY_TOO_LARGE" });
  });

  it("rejects a forged user id in query parameters", () => {
    const request = new Request("http://localhost/api/osekkai/profile?userId=forged");
    expect(() => assertSafeGetRequest(request)).toThrowError(/ユーザー識別子/);
  });
});
