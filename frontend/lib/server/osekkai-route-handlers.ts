import type { JsonObject, JsonValue, OsekkaiSessionView } from './osekkai-contract';
import { randomUUID } from 'crypto';
import { NextResponse } from 'next/server';
import { ensureOsekkaiDemoSeed } from './osekkai-demo-seed';
import { OsekkaiHttpError } from './osekkai-errors';
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
    const result = await getOsekkaiProfile(session.userId);
    return osekkaiSuccess(result.data, result.requestId);
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

export function chatPost(request: Request) {
  return withOsekkaiErrors(async () => {
    const parsed = await parseMutationRequest(request);
    assertAllowedFields(parsed.body, ['message', 'remember']);
    const message = requireString(parsed.body, 'message', { min: 1, max: 2_000 });
    const remember = optionalBoolean(parsed.body, 'remember');
    const payload: JsonObject = { message };
    if (remember !== undefined) {
      payload.remember = remember;
    }
    const result = await runOsekkaiChat(
      parsed.session.userId,
      payload,
      parsed.idempotencyKey,
    );
    return osekkaiSuccess(result.data, result.requestId);
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
