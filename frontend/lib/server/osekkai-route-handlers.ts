import type { JsonObject, JsonValue, OsekkaiSessionView } from './osekkai-contract';
import { randomUUID } from 'crypto';
import { NextResponse } from 'next/server';
import mapEventsSnapshotJson from '@/lib/osekkai/map-events-snapshot.generated.json';
import type { MapEventsResult } from '@/lib/osekkai/types.generated';
import { validateChatResult } from '@/lib/osekkai/validators.generated';
import { ensureOsekkaiDemoSeed } from './osekkai-demo-seed';
import { OsekkaiHttpError } from './osekkai-errors';
import {
  FIXED_START_GREETING,
  generateLlmChatReply,
  isLlmChatAvailable,
  parseLlmChatHistory,
  type LlmChatAction,
} from './osekkai-llm-chat';
import { getOsekkaiMetrics } from './osekkai-metrics';
import {
  assertAllowedFields,
  assertSafeGetRequest,
  isJsonObject,
  optionalBoolean,
  osekkaiSuccess,
  parseMutationRequest,
  requireString,
  requireUuid,
  withOsekkaiErrors,
  withoutTransportFields,
} from './osekkai-request';
import {
  decideOsekkaiIntervention,
  completeGoogleCalendarConnection,
  deleteOsekkaiProfile,
  disconnectGoogleCalendar,
  getOsekkaiFreebusy,
  getOsekkaiEvents,
  getOsekkaiMapEvents,
  getOsekkaiEventRoute,
  getOsekkaiInterventions,
  getOsekkaiOpportunities,
  getOsekkaiProfile,
  getOsekkaiSourceStatus,
  recordOsekkaiFeedback,
  recordOsekkaiIntervention,
  resetOsekkaiDemo,
  runOsekkaiChat,
  startGoogleCalendarConnection,
  syncOsekkaiSources,
  updateOsekkaiProfile,
} from './osekkai-store';
import {
  clearOsekkaiSession,
  getOrCreateOsekkaiSession,
  getOsekkaiDataMode,
  issueOsekkaiCsrfToken,
  requireOsekkaiSession,
} from './osekkai-user';

type CalendarConnectResult = { authorizationUrl: string; state: string; expiresAt: string };

function calendarLanding(request: Request, status: string): URL {
  const target = new URL('/osekkai', request.url);
  target.searchParams.set('calendar', status);
  return target;
}

export function calendarConnectGet(request: Request) {
  return withOsekkaiErrors(async () => {
    assertSafeGetRequest(request);
    const session = await getOrCreateOsekkaiSession();
    const result = await startGoogleCalendarConnection<CalendarConnectResult>(session.userId, randomUUID());
    return NextResponse.redirect(result.data.authorizationUrl, 302);
  });
}

export function calendarCallbackGet(request: Request) {
  return withOsekkaiErrors(async () => {
    assertSafeGetRequest(request);
    const session = await requireOsekkaiSession();
    const query = new URL(request.url).searchParams;
    if (query.get('error')) {
      return NextResponse.redirect(calendarLanding(request, 'denied'), 303);
    }
    const state = query.get('state');
    const code = query.get('code');
    if (!state || !/^[A-Za-z0-9_-]{32,160}$/.test(state) || !code || code.length > 4096) {
      throw new OsekkaiHttpError('OAUTH_CALLBACK_INVALID', 'Google認証の応答を確認できません。', 400);
    }
    await completeGoogleCalendarConnection(
      session.userId,
      { state, code },
      randomUUID(),
    );
    return NextResponse.redirect(calendarLanding(request, 'connected'), 303);
  });
}

export function calendarDisconnectPost(request: Request) {
  return withOsekkaiErrors(async () => {
    const parsed = await parseMutationRequest(request);
    if (Object.keys(mutationPayload(parsed.body)).length > 0) {
      throw new OsekkaiHttpError('VALIDATION_ERROR', 'Calendar切断に入力値は不要です。', 400);
    }
    const result = await disconnectGoogleCalendar(parsed.session.userId, parsed.idempotencyKey);
    return osekkaiSuccess(result.data, result.requestId);
  });
}

function mutationPayload(body: JsonObject): JsonObject {
  return withoutTransportFields(body);
}

function requireEpisodeId(body: JsonObject): string {
  return requireUuid(body, 'episodeId');
}

function profileUpdatePayload(body: JsonObject): JsonObject {
  const withoutTransport = mutationPayload(body);
  const operation = withoutTransport.operation;
  if (operation !== undefined && typeof operation !== 'string') {
    throw new OsekkaiHttpError('VALIDATION_ERROR', 'operation の内容を確認してください。', 400);
  }

  if (operation === 'update_settings') {
    assertAllowedFields(body, ['operation', 'updates']);
    if (!isJsonObject(withoutTransport.updates)) {
      throw new OsekkaiHttpError('VALIDATION_ERROR', 'updates の内容を確認してください。', 400);
    }
    return { patch: withoutTransport.updates };
  }
  if (operation === 'pause_one_week') {
    assertAllowedFields(body, ['operation', 'pauseOneWeek']);
    if (withoutTransport.pauseOneWeek !== true) {
      throw new OsekkaiHttpError('VALIDATION_ERROR', 'pauseOneWeek の内容を確認してください。', 400);
    }
    return { pauseOneWeek: true };
  }
  if (operation === 'remove_inferred_preference') {
    assertAllowedFields(body, ['operation', 'inferredPreferenceKey']);
    if (
      typeof withoutTransport.inferredPreferenceKey !== 'string' ||
      withoutTransport.inferredPreferenceKey.length > 128
    ) {
      throw new OsekkaiHttpError(
        'VALIDATION_ERROR',
        'inferredPreferenceKey の内容を確認してください。',
        400,
      );
    }
    return { removeInferredPreferenceKey: withoutTransport.inferredPreferenceKey };
  }
  if (operation !== undefined) {
    throw new OsekkaiHttpError('VALIDATION_ERROR', '未対応のプロフィール操作です。', 400);
  }

  const patch = withoutTransport.patch;

  assertAllowedFields(body, [
    'patch',
    'removeEvidenceId',
    'pauseOneWeek',
    'memoryConsent',
    'pushConsent',
    'quietHours',
    'maxPushesPerWeek',
    'preferredTone',
    'maxTravelMinutes',
    'maxBudgetYen',
    'maxSocialIntensity',
    'preferredCategories',
    'avoidedCategories',
  ]);

  if (patch !== undefined && !isJsonObject(patch)) {
    throw new OsekkaiHttpError('VALIDATION_ERROR', 'patch の内容を確認してください。', 400);
  }
  if (
    withoutTransport.removeEvidenceId !== undefined &&
    typeof withoutTransport.removeEvidenceId !== 'string'
  ) {
    throw new OsekkaiHttpError(
      'VALIDATION_ERROR',
      'removeEvidenceId の内容を確認してください。',
      400,
    );
  }
  if (
    withoutTransport.pauseOneWeek !== undefined &&
    typeof withoutTransport.pauseOneWeek !== 'boolean'
  ) {
    throw new OsekkaiHttpError(
      'VALIDATION_ERROR',
      'pauseOneWeek の内容を確認してください。',
      400,
    );
  }

  // PUT clients may send profile fields at the top level. Normalize those to
  // the CLI's explicit `patch` field while preserving PATCH control fields.
  if (patch === undefined) {
    const normalizedPatch: JsonObject = {};
    for (const [key, value] of Object.entries(withoutTransport)) {
      if (key !== 'removeEvidenceId' && key !== 'pauseOneWeek') {
        normalizedPatch[key] = value as JsonValue;
      }
    }
    return {
      ...(Object.keys(normalizedPatch).length > 0 ? { patch: normalizedPatch } : {}),
      ...(withoutTransport.removeEvidenceId !== undefined
        ? { removeEvidenceId: withoutTransport.removeEvidenceId }
        : {}),
      ...(withoutTransport.pauseOneWeek !== undefined
        ? { pauseOneWeek: withoutTransport.pauseOneWeek }
        : {}),
    };
  }
  return withoutTransport;
}

export function sessionGet(request: Request) {
  return withOsekkaiErrors(async (requestId) => {
    assertSafeGetRequest(request);
    const session = await getOrCreateOsekkaiSession();
    const csrf = issueOsekkaiCsrfToken(session);
    const data: OsekkaiSessionView = {
      csrfToken: csrf.token,
      dataMode: getOsekkaiDataMode(),
      expiresAt: csrf.expiresAt,
    };
    return osekkaiSuccess(data, requestId);
  });
}

export function profileGet(request: Request) {
  return withOsekkaiErrors(async () => {
    assertSafeGetRequest(request);
    const session = await getOrCreateOsekkaiSession();
    try {
      const result = await getOsekkaiProfile(session.userId);
      return osekkaiSuccess(result.data, result.requestId);
    } catch (error) {
      // Vercel can't spawn the Python-owned profile store. The client
      // validates this response against the full DistanceProfile schema
      // (see components/osekkai/api-client.ts's validatePayload) before it
      // ever reaches normalizeProfile, so an empty object fails validation —
      // it must be a complete, schema-valid synthetic profile instead.
      if (!isPythonUnavailableError(error)) throw error;
      return osekkaiSuccess(buildSyntheticProfile(session.userId), randomUUID());
    }
  });
}

export function profileUpdate(request: Request) {
  return withOsekkaiErrors(async () => {
    const parsed = await parseMutationRequest(request);
    const result = await updateOsekkaiProfile(
      parsed.session.userId,
      profileUpdatePayload(parsed.body),
      parsed.idempotencyKey,
    );
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function profileDelete(request: Request) {
  return withOsekkaiErrors(async () => {
    const parsed = await parseMutationRequest(request);
    assertAllowedFields(parsed.body, ['confirm']);
    if (parsed.body.confirm !== true) {
      throw new OsekkaiHttpError(
        'DELETE_CONFIRMATION_REQUIRED',
        'プロフィール削除の確認が必要です。',
        400,
      );
    }
    const result = await deleteOsekkaiProfile(parsed.session.userId, parsed.idempotencyKey);
    await clearOsekkaiSession();
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function chatGet(request: Request) {
  return withOsekkaiErrors(async (requestId) => {
    assertSafeGetRequest(request);
    const session = await getOrCreateOsekkaiSession();
    const [profile, interventions] = await Promise.all([
      getOsekkaiProfile(session.userId),
      getOsekkaiInterventions(session.userId),
    ]);
    return osekkaiSuccess(
      { messages: [], profile: profile.data, interventions: interventions.data },
      requestId,
    );
  });
}

function buildSyntheticProfile(userId: string): JsonObject {
  const now = new Date().toISOString();
  return {
    schemaVersion: '1.0',
    id: randomUUID(),
    userId,
    memoryConsent: false,
    pushConsent: false,
    quietHours: { start: '21:00', end: '08:00', timezone: 'Asia/Tokyo' },
    maxPushesPerWeek: 2,
    preferredTone: 'gentle',
    maxTravelMinutes: 40,
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
    participationFriction: {},
    currentSignals: {
      interventionHint: 'none',
      currentReceptivity: null,
      safety: { level: 'normal', requiresHumanSupport: false },
      observedAt: null,
    },
    createdAt: now,
    updatedAt: now,
  };
}

function buildSyntheticChatResult(reply: string, userId: string): JsonObject {
  const value: JsonObject = {
    schemaVersion: '1.0',
    reply,
    profileDelta: {},
    frictionDelta: [],
    interventionHint: 'none',
    confidence: 0.5,
    safety: {
      requiresHumanSupport: false,
      level: 'normal',
      message: null,
      supportResourcesVerified: false,
    },
    persisted: false,
    conversationId: null,
    profile: buildSyntheticProfile(userId),
    context: {
      schemaVersion: '1.0',
      episodeId: null,
      state: 'getting_to_know',
      trigger: 'user_initiated',
      quickReplies: [],
      recommendations: [],
      calendarSummary: null,
      selectedOpportunityId: null,
      checkInDueAt: null,
      canSendMessage: true,
      notice: 'いまは簡易モードです。雑談と活動紹介のみ対応し、この会話は保存されません。',
    },
  };
  const validated = validateChatResult(value);
  if (!validated.valid) {
    throw new OsekkaiHttpError('PYTHON_INVALID_RESPONSE', 'おっせかいエンジンの応答形式が正しくありません。', 502);
  }
  return value;
}

export function chatPost(request: Request) {
  return withOsekkaiErrors(async () => {
    const parsed = await parseMutationRequest(request);
    assertAllowedFields(parsed.body, ['action', 'message', 'opportunityId', 'remember', 'history']);
    const action = parsed.body.action ?? 'message';
    if (!['start', 'message', 'select', 'check_in'].includes(String(action))) {
      throw new OsekkaiHttpError('VALIDATION_ERROR', '未対応の会話操作です。', 400);
    }
    const remember = optionalBoolean(parsed.body, 'remember');
    const payload: JsonObject = { action: String(action) };
    if (action === 'message' || action === 'check_in') {
      payload.message = requireString(parsed.body, 'message', { min: 1, max: 2_000 });
    }
    if (action === 'select') {
      payload.opportunityId = requireString(parsed.body, 'opportunityId', { min: 1, max: 200 });
    }
    if (remember !== undefined) {
      payload.remember = remember;
    }
    try {
      const result = await runOsekkaiChat(
        parsed.session.userId,
        payload,
        parsed.idempotencyKey,
      );
      return osekkaiSuccess(result.data, result.requestId);
    } catch (error) {
      // Vercel can't spawn the Python conversation engine at all. If an LLM
      // key is configured, fall back to a stateless, casual-chat-only path
      // that calls OpenAI directly from Node (see osekkai-llm-chat.ts) —
      // no friction/safety classification, no server-side memory.
      if (!isPythonUnavailableError(error) || !isLlmChatAvailable()) throw error;
      const history = parseLlmChatHistory(parsed.body.history);
      // The opening line skips the LLM entirely — a first-visit request is
      // the one most likely to hit a cold Vercel function, and a slow or
      // failed greeting there reads as "she never speaks first."
      const reply = action === 'start'
        ? FIXED_START_GREETING
        : await generateLlmChatReply({
          action: action as LlmChatAction,
          message: typeof payload.message === 'string' ? payload.message : undefined,
          history,
        });
      return osekkaiSuccess(buildSyntheticChatResult(reply, parsed.session.userId), randomUUID());
    }
  });
}

export function freebusyGet(request: Request) {
  return withOsekkaiErrors(async () => {
    assertSafeGetRequest(request);
    const session = await getOrCreateOsekkaiSession();
    const result = await getOsekkaiFreebusy(session.userId);
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function opportunitiesGet(request: Request) {
  return withOsekkaiErrors(async () => {
    assertSafeGetRequest(request);
    const session = await getOrCreateOsekkaiSession();
    const result = await getOsekkaiOpportunities(session.userId);
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function sourcesGet(request: Request) {
  return withOsekkaiErrors(async () => {
    assertSafeGetRequest(request);
    const session = await getOrCreateOsekkaiSession();
    const result = await getOsekkaiSourceStatus(session.userId);
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function sourcesPost(request: Request) {
  return withOsekkaiErrors(async () => {
    const parsed = await parseMutationRequest(request);
    const payload = mutationPayload(parsed.body);
    const result = await syncOsekkaiSources(parsed.session.userId, payload, parsed.idempotencyKey);
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function eventsGet(request: Request) {
  return withOsekkaiErrors(async () => {
    assertSafeGetRequest(request);
    const session = await getOrCreateOsekkaiSession();
    const result = await getOsekkaiEvents(session.userId);
    return osekkaiSuccess(result.data, result.requestId);
  });
}

const mapEventsSnapshot = mapEventsSnapshotJson as unknown as MapEventsResult;

// Vercel serverless functions cannot spawn the Python live-sync process this
// route normally reads through. Rather than 500 there, fall back to the last
// snapshot fetched locally (`lib/osekkai/map-events-snapshot.generated.json`)
// so the map still renders real, already-fetched Events instead of nothing.
function isPythonUnavailableError(error: unknown): boolean {
  return error instanceof OsekkaiHttpError && error.code.startsWith('PYTHON_');
}

function mapEventsFromSnapshot(offset: number, limit: number): MapEventsResult {
  const page = mapEventsSnapshot.events.slice(offset, offset + limit);
  const end = offset + page.length;
  return {
    ...mapEventsSnapshot,
    events: page,
    counts: { ...mapEventsSnapshot.counts, returned: page.length },
    nextOffset: end < mapEventsSnapshot.events.length ? end : null,
  };
}

export function mapEventsGet(request: Request) {
  return withOsekkaiErrors(async () => {
    assertSafeGetRequest(request);
    const params = new URL(request.url).searchParams;
    if (Array.from(params.keys()).some((key) => key !== 'offset' && key !== 'limit')) {
      throw new OsekkaiHttpError('VALIDATION_ERROR', '地図の取得条件を確認してください。', 400);
    }
    const offsetText = params.get('offset') ?? '0';
    const limitText = params.get('limit') ?? '250';
    if (!/^\d{1,5}$/.test(offsetText) || !/^\d{1,3}$/.test(limitText)) {
      throw new OsekkaiHttpError('VALIDATION_ERROR', '地図の取得条件を確認してください。', 400);
    }
    const offset = Number(offsetText);
    const limit = Number(limitText);
    try {
      const session = await getOrCreateOsekkaiSession();
      const result = await getOsekkaiMapEvents(session.userId, {
        scope: 'chiyoda_kojimachi',
        offset,
        limit,
      });
      return osekkaiSuccess(result.data, result.requestId);
    } catch (error) {
      if (!isPythonUnavailableError(error)) throw error;
      return osekkaiSuccess(mapEventsFromSnapshot(offset, limit), randomUUID());
    }
  });
}

export function eventRoutePost(request: Request) {
  return withOsekkaiErrors(async () => {
    const parsed = await parseMutationRequest(request);
    const result = await getOsekkaiEventRoute(parsed.session.userId, mutationPayload(parsed.body));
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function decidePost(request: Request) {
  return withOsekkaiErrors(async () => {
    const parsed = await parseMutationRequest(request);
    const payloadKeys = Object.keys(mutationPayload(parsed.body));
    if (payloadKeys.length > 0) {
      throw new OsekkaiHttpError(
        'SERVER_OWNED_DECISION_INPUT',
        '判断材料はサーバー側の保存データから取得します。',
        400,
      );
    }
    const result = await decideOsekkaiIntervention(
      parsed.session.userId,
      parsed.idempotencyKey,
    );
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function interventionsGet(request: Request) {
  return withOsekkaiErrors(async () => {
    assertSafeGetRequest(request);
    const session = await getOrCreateOsekkaiSession();
    const result = await getOsekkaiInterventions(session.userId);
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function interventionsPost(request: Request) {
  return withOsekkaiErrors(async () => {
    const parsed = await parseMutationRequest(request);
    assertAllowedFields(parsed.body, [
      'episodeId',
      'event',
      'transition',
      'eventType',
      'outcome',
      'status',
    ]);
    requireEpisodeId(parsed.body);
    const payload = mutationPayload(parsed.body);
    const eventAlias = payload.event ?? payload.transition;
    if (payload.eventType === undefined && typeof eventAlias === 'string') {
      payload.eventType = eventAlias;
    }
    delete payload.event;
    delete payload.transition;
    const result = await recordOsekkaiIntervention(
      parsed.session.userId,
      payload,
      parsed.idempotencyKey,
    );
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function feedbackPost(request: Request) {
  return withOsekkaiErrors(async () => {
    const parsed = await parseMutationRequest(request);
    assertAllowedFields(parsed.body, ['episodeId', 'actionResponse', 'distanceFeedback']);
    requireEpisodeId(parsed.body);
    const hasActionResponse = parsed.body.actionResponse !== undefined;
    const hasDistanceFeedback = parsed.body.distanceFeedback !== undefined;
    if (hasActionResponse === hasDistanceFeedback) {
      throw new OsekkaiHttpError(
        'VALIDATION_ERROR',
        'actionResponse または distanceFeedback のどちらか一方を指定してください。',
        400,
      );
    }
    const actionResponse = parsed.body.actionResponse;
    const distanceFeedback = parsed.body.distanceFeedback;
    if (
      actionResponse !== undefined &&
      !['accepted', 'declined', 'show_another', 'pause_one_week'].includes(String(actionResponse))
    ) {
      throw new OsekkaiHttpError('VALIDATION_ERROR', 'actionResponse の内容を確認してください。', 400);
    }
    if (
      distanceFeedback !== undefined &&
      !['too_much', 'just_right', 'push_more'].includes(String(distanceFeedback))
    ) {
      throw new OsekkaiHttpError('VALIDATION_ERROR', 'distanceFeedback の内容を確認してください。', 400);
    }
    const result = await recordOsekkaiFeedback(
      parsed.session.userId,
      mutationPayload(parsed.body),
      parsed.idempotencyKey,
    );
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function metricsGet(request: Request) {
  return withOsekkaiErrors(async () => {
    assertSafeGetRequest(request);
    const session = await getOrCreateOsekkaiSession();
    const result = await getOsekkaiMetrics(session.userId);
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function demoResetPost(request: Request) {
  return withOsekkaiErrors(async () => {
    if (getOsekkaiDataMode() !== 'demo') {
      throw new OsekkaiHttpError('DEMO_MODE_DISABLED', 'ページが見つかりません。', 404);
    }
    const parsed = await parseMutationRequest(request);
    assertAllowedFields(parsed.body, []);
    const result = await resetOsekkaiDemo(parsed.session.userId, parsed.idempotencyKey);
    return osekkaiSuccess(result.data, result.requestId);
  });
}

export function demoSeedPost(request: Request) {
  return withOsekkaiErrors(async () => {
    if (getOsekkaiDataMode() !== 'demo') {
      throw new OsekkaiHttpError('DEMO_MODE_DISABLED', 'ページが見つかりません。', 404);
    }
    const parsed = await parseMutationRequest(request);
    assertAllowedFields(parsed.body, []);
    const result = await ensureOsekkaiDemoSeed(parsed.session.userId);
    return osekkaiSuccess(result.data, result.requestId);
  });
}


export function outcomePost(request: Request, eventType: 'attendance' | 'revisit') {
  return withOsekkaiErrors(async () => {
    const parsed = await parseMutationRequest(request);
    assertAllowedFields(parsed.body, ['episodeId']);
    const episodeId = requireEpisodeId(parsed.body);
    const payload: JsonObject = {
      episodeId,
      eventType,
      status: eventType === 'attendance' ? 'attended' : 'revisited',
    };
    const result = await recordOsekkaiIntervention(
      parsed.session.userId,
      payload,
      parsed.idempotencyKey,
    );
    return osekkaiSuccess(result.data, result.requestId);
  });
}
