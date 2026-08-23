import { afterEach, describe, expect, it, vi } from "vitest";

import freebusyFixture from "../../../agents-OpenClaw/fixtures/osekkai/freebusy.json";
import liveContractsFixture from "../../../agents-OpenClaw/fixtures/osekkai/live-contracts.json";
import opportunitiesFixture from "../../../agents-OpenClaw/fixtures/osekkai/opportunities.normalized.json";
import profileFixture from "../../../agents-OpenClaw/fixtures/osekkai/profile.json";
import { osekkaiApi, resetOsekkaiClientSessionForTests } from "./api";
import {
  validateDecideResponse,
  validateCommunity,
  validateConnectionEvidence,
  validateDecisionResult,
  validateDistanceProfile,
  validateFreeBusyResult,
  validateEventSeries,
  validateLiveEvent,
  validateMetricsResult,
  validateOpportunity,
  validateSessionResult,
  validateSourceRegistry
} from "./validators.generated";

const profile = {
  schemaVersion: "1.0",
  id: "10000000-0000-4000-8000-000000000001",
  userId: "20000000-0000-4000-8000-000000000002",
  memoryConsent: false,
  pushConsent: false,
  quietHours: { start: "21:00", end: "08:00", timezone: "Asia/Tokyo" },
  maxPushesPerWeek: 2,
  preferredTone: "gentle",
  maxTravelMinutes: 30,
  maxBudgetYen: 2000,
  socialBattery: null,
  maxSocialIntensity: 2,
  preferredCategories: [],
  avoidedCategories: [],
  rejectionStreak: 0,
  cooldownUntil: null,
  pauseUntil: null,
  lastPushAt: null,
  explicitPreferences: {},
  inferredPreferences: {},
  currentSignals: {
    interventionHint: "none",
    currentReceptivity: null,
    safety: { level: "normal", requiresHumanSupport: false },
    observedAt: null
  },
  createdAt: "2025-02-20T09:00:00+09:00",
  updatedAt: "2025-02-20T09:00:00+09:00"
} as const;

function withoutKey(value: Record<string, unknown>, key: string) {
  return Object.fromEntries(Object.entries(value).filter(([entryKey]) => entryKey !== key));
}

afterEach(() => {
  resetOsekkaiClientSessionForTests();
  vi.unstubAllGlobals();
});

describe("Osekkai generated validators", () => {
  it("rejects extra session fields so userId can never be exposed", () => {
    const session = {
      csrfToken: "csrf-token",
      expiresAt: "2025-02-20T09:10:00+09:00",
      dataMode: "demo"
    };
    expect(validateSessionResult(session).valid).toBe(true);
    expect(validateSessionResult({ ...session, userId: profile.userId }).valid).toBe(false);
  });

  it("accepts canonical generated and fixture profiles and rejects a missing consent field", () => {
    expect(validateDistanceProfile(profile).valid).toBe(true);
    expect(validateDistanceProfile(profileFixture).valid).toBe(true);
    const invalid = withoutKey(profile, "memoryConsent");
    expect(validateDistanceProfile(invalid).valid).toBe(false);
  });

  it("accepts the Python FreeBusy and Opportunity fixture shapes", () => {
    expect(validateFreeBusyResult(freebusyFixture).valid).toBe(true);
    const opportunity = opportunitiesFixture.opportunities[0];
    expect(validateOpportunity(opportunity).valid).toBe(true);
    expect(
      validateOpportunity({
        ...opportunity,
        license: undefined,
        sourceLicense: opportunity.license,
        checksum: `sha256:${opportunity.checksum}`
      }).valid
    ).toBe(false);
  });

  it("accepts the same live Event, Series, Community, Source, Evidence and ranked decision fixture as Python", () => {
    expect(validateSourceRegistry(liveContractsFixture.sourceRegistry).valid).toBe(true);
    expect(liveContractsFixture.events.every((value) => validateLiveEvent(value).valid)).toBe(true);
    expect(liveContractsFixture.series.every((value) => validateEventSeries(value).valid)).toBe(true);
    expect(liveContractsFixture.communities.every((value) => validateCommunity(value).valid)).toBe(true);
    expect(liveContractsFixture.connectionEvidence.every((value) => validateConnectionEvidence(value).valid)).toBe(true);
    expect(liveContractsFixture.opportunities.every((value) => validateOpportunity(value).valid)).toBe(true);
    expect(validateDecisionResult(liveContractsFixture.decision).valid).toBe(true);
    expect(validateDecisionResult({
      ...liveContractsFixture.decision,
      rankedOpportunities: liveContractsFixture.decision.rankedOpportunities.map((item, index) => ({
        ...item,
        rank: index + 2
      }))
    }).valid).toBe(false);
  });

  it("rejects live opportunities without freshness or connection evidence", () => {
    const opportunity = liveContractsFixture.opportunities[0] as Record<string, unknown>;
    expect(validateOpportunity(withoutKey(opportunity, "revalidatedAt")).valid).toBe(false);
    expect(validateOpportunity(withoutKey(opportunity, "connectionEvidence")).valid).toBe(false);
    expect(validateOpportunity(withoutKey(opportunity, "status")).valid).toBe(false);
  });

  it("validates decide as a decision-plus-episode API response", () => {
    const opportunity = opportunitiesFixture.opportunities[0];
    const episodeId = "30000000-0000-4000-8000-000000000003";
    const episode = {
      schemaVersion: "1.0",
      id: episodeId,
      userId: profile.userId,
      sequence: 2,
      policyVersion: "osekkai-p0-v1",
      decision: "suggest_solo_place",
      shouldPush: true,
      reasonCodes: [
        "FREE_WINDOW_AVAILABLE",
        "LOW_CONVERSATION_REQUIREMENT",
        "WITHIN_TRAVEL_LIMIT",
        "UNDER_BUDGET"
      ],
      score: 0.78,
      profileSnapshot: profileFixture,
      freeWindowSnapshot: {
        ...freebusyFixture.freeWindows[0],
        suggestedVisitStart: "2019-02-23T13:08:00+09:00",
        suggestedVisitEnd: "2019-02-23T13:38:00+09:00"
      },
      candidateIdsBeforeFilter: [opportunity.id],
      candidateIdsAfterFilter: [opportunity.id],
      excludedCandidates: [],
      selectedOpportunity: opportunity,
      notification: { text: "静かに見られる場所です。", tone: "gentle", shownOpportunityIds: [opportunity.id] },
      pushedAt: "2019-02-23T10:00:00+09:00",
      noPushAt: null,
      actionResponse: null,
      actionResponseAt: null,
      distanceFeedback: null,
      distanceFeedbackAt: null,
      attendedAt: null,
      revisitedAt: null,
      selfInitiatedAt: null,
      dataMode: "demo",
      metricClassification: "demo",
      minimalRecord: false,
      createdAt: "2019-02-23T10:00:00+09:00",
      updatedAt: "2019-02-23T10:00:00+09:00"
    };
    const decision = {
      schemaVersion: "1.0",
      episodeId,
      policyVersion: "osekkai-p0-v1",
      decision: "suggest_solo_place",
      shouldPush: true,
      reasonCodes: episode.reasonCodes,
      score: episode.score,
      selectedOpportunity: opportunity,
      excludedCandidates: [],
      notification: { text: "静かに見られる場所です。", tone: "gentle" },
      dataMode: "demo",
      createdAt: "2019-02-23T10:00:00+09:00"
    };

    expect(validateDecisionResult(decision).valid).toBe(true);
    expect(validateDecideResponse({ decision, episode }).valid).toBe(true);
    const legacyEpisode = { ...episode } as Record<string, unknown>;
    delete legacyEpisode.sequence;
    expect(validateDecideResponse({ decision, episode: legacyEpisode }).valid).toBe(false);
    expect(validateDecisionResult({ decision, episode }).valid).toBe(false);
  });

  it("requires generatedAt and separate measured and unverified metric lists", () => {
    const metrics = {
      schemaVersion: "1.0",
      generatedAt: "2019-02-23T10:00:00+09:00",
      dataMode: "demo",
      metrics: [
        {
          key: "just_right_push_rate",
          label: "Just-Right Push Rate",
          value: 1,
          numerator: 1,
          denominator: 1,
          classification: "demo",
          note: "Episodeから再計算しています。"
        }
      ],
      unverifiedMetrics: [
        {
          key: "ucla3_baseline",
          label: "UCLA-3 baseline",
          value: null,
          classification: "unverified",
          note: "P0では収集しません。"
        }
      ]
    };
    expect(validateMetricsResult(metrics).valid).toBe(true);
    const invalid = withoutKey(metrics, "generatedAt");
    expect(validateMetricsResult(invalid).valid).toBe(false);
  });
});

describe("Osekkai API client", () => {
  it("binds a mutation to the session CSRF token without exposing a user id", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            data: {
              csrfToken: "csrf-token",
              expiresAt: new Date(Date.now() + 60_000).toISOString(),
              dataMode: "demo"
            },
            requestId: "11111111-1111-4111-8111-111111111111"
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            data: {
              schemaVersion: "1.0",
              reply: "今日は休んで大丈夫です。",
              profileDelta: {},
              interventionHint: "do_not_push",
              confidence: 1,
              safety: {
                requiresHumanSupport: false,
                level: "normal",
                message: null,
                supportResourcesVerified: false
              },
              persisted: false,
              conversationId: null,
              profile
            },
            requestId: "22222222-2222-4222-8222-222222222222"
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    vi.stubGlobal("fetch", fetchMock);

    await osekkaiApi.chat("これは覚えないで", false);

    const [, mutationOptions] = fetchMock.mock.calls[1];
    const headers = new Headers(mutationOptions?.headers);
    const body = JSON.parse(String(mutationOptions?.body));
    expect(headers.get("x-osekkai-csrf")).toBe("csrf-token");
    expect(headers.get("idempotency-key")).toBe(body.idempotencyKey);
    expect(body).toMatchObject({ message: "これは覚えないで", remember: false });
    expect(JSON.stringify(body).toLowerCase()).not.toContain("userid");
  });
});
