import {
  type ValidationResult,
  validateChatResult,
  validateDecideResponse,
  validateDemoResetResponse,
  validateDistanceProfile,
  validateEventRouteResult,
  validateLiveEvent,
  validateFeedbackResponse,
  validateFreeBusyResult,
  validateInterventionEpisode,
  validateInterventionsResult,
  validateMetricsResult,
  validateOpportunitiesResult,
  validateProfileDeleteResponse,
  validateRecordOutcomeResponse,
} from '@/lib/osekkai/validators.generated';

import { OSEKKAI_COMMANDS, type OsekkaiCommand } from './osekkai-commands';
import type { JsonObject } from './osekkai-contract';
import { OsekkaiHttpError } from './osekkai-errors';

const INVALID_RESPONSE_MESSAGE = 'おっせかいエンジンの応答形式が正しくありません。';
const OWNER_MISMATCH_MESSAGE = 'おっせかいエンジンの応答を認証できませんでした。';

function invalidResponse(requestId?: string): never {
  throw new OsekkaiHttpError(
    'PYTHON_INVALID_RESPONSE',
    INVALID_RESPONSE_MESSAGE,
    502,
    requestId,
  );
}

function ownerMismatch(requestId?: string): never {
  throw new OsekkaiHttpError(
    'PYTHON_OWNER_MISMATCH',
    OWNER_MISMATCH_MESSAGE,
    502,
    requestId,
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function validateCleanupResult(value: unknown): ValidationResult<unknown> {
  const valid =
    isRecord(value) &&
    value.schemaVersion === '1.0' &&
    Number.isInteger(value.retentionDays) &&
    Number(value.retentionDays) >= 1 &&
    Number(value.retentionDays) <= 365 &&
    isRecord(value.removed) &&
    Object.values(value.removed).every((item) => Number.isInteger(item) && Number(item) >= 0);
  return valid
    ? { valid: true, value }
    : { valid: false, errors: ['CleanupResult is invalid'] };
}

function validateDemoSeedResult(value: unknown): ValidationResult<unknown> {
  if (!isRecord(value) || !hasExactKeys(value, [
    'schemaVersion',
    'dataMode',
    'seeded',
    'profile',
  ])) {
    return { valid: false, errors: ['DemoSeedResult is invalid'] };
  }
  const profile = validateDistanceProfile(value.profile);
  return value.schemaVersion === '1.0' &&
    value.dataMode === 'demo' &&
    typeof value.seeded === 'boolean' &&
    profile.valid
    ? { valid: true, value }
    : { valid: false, errors: ['DemoSeedResult is invalid'] };
}

function validateCalendarConnectResult(value: unknown): ValidationResult<unknown> {
  const valid = isRecord(value) && hasExactKeys(value, ['authorizationUrl', 'state', 'expiresAt']) &&
    typeof value.authorizationUrl === 'string' && value.authorizationUrl.startsWith('https://accounts.google.com/') &&
    typeof value.state === 'string' && /^[A-Za-z0-9_-]{32,160}$/.test(value.state) &&
    typeof value.expiresAt === 'string' && Number.isFinite(Date.parse(value.expiresAt));
  return valid ? { valid: true, value } : { valid: false, errors: ['CalendarConnectResult is invalid'] };
}

function validateCalendarCallbackResult(value: unknown): ValidationResult<unknown> {
  const valid = isRecord(value) && hasExactKeys(value, ['connected', 'scope', 'expiresAt']) &&
    value.connected === true && value.scope === 'https://www.googleapis.com/auth/calendar.freebusy' &&
    typeof value.expiresAt === 'string' && Number.isFinite(Date.parse(value.expiresAt));
  return valid ? { valid: true, value } : { valid: false, errors: ['CalendarCallbackResult is invalid'] };
}

function validateCalendarDisconnectResult(value: unknown): ValidationResult<unknown> {
  const valid = isRecord(value) && hasExactKeys(value, ['disconnected']) && value.disconnected === true;
  return valid ? { valid: true, value } : { valid: false, errors: ['CalendarDisconnectResult is invalid'] };
}

function validateSourceStatusResult(value: unknown): ValidationResult<unknown> {
  const valid = isRecord(value) && value.schemaVersion === '1.0' && value.dataMode === 'live' &&
    typeof value.generatedAt === 'string' && Number.isFinite(Date.parse(value.generatedAt)) &&
    Array.isArray(value.sources) && value.sources.every((source) =>
      isRecord(source) && typeof source.id === 'string' && typeof source.displayName === 'string' &&
      typeof source.readiness === 'string' && typeof source.health === 'string' &&
      typeof source.eventCount === 'number' && typeof source.stale === 'boolean'
    ) && isRecord(value.counts);
  return valid ? { valid: true, value } : { valid: false, errors: ['SourceStatusResult is invalid'] };
}

function validateEventMeshResult(value: unknown): ValidationResult<unknown> {
  const valid = isRecord(value) && value.schemaVersion === '1.0' && value.dataMode === 'live' &&
    typeof value.generatedAt === 'string' && Number.isFinite(Date.parse(value.generatedAt)) &&
    Array.isArray(value.events) && value.events.every((event) => validateLiveEvent(event).valid) &&
    Array.isArray(value.eligibleEvents) && Array.isArray(value.excludedEvents) &&
    Array.isArray(value.series) && Array.isArray(value.communities) && Array.isArray(value.providerErrors);
  return valid ? { valid: true, value } : { valid: false, errors: ['EventMeshResult is invalid'] };
}

function hasExactKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
): boolean {
  const actual = Object.keys(value);
  return actual.length === keys.length && keys.every((key) => actual.includes(key));
}

function resultForCommand(
  command: OsekkaiCommand,
  payload: Readonly<JsonObject>,
  value: unknown,
): ValidationResult<unknown> {
  switch (command) {
    case OSEKKAI_COMMANDS.chat:
      return validateChatResult(value);
    case OSEKKAI_COMMANDS.profileGet:
    case OSEKKAI_COMMANDS.profileUpdate:
      return validateDistanceProfile(value);
    case OSEKKAI_COMMANDS.profileDelete:
      return validateProfileDeleteResponse(value);
    case OSEKKAI_COMMANDS.freebusy:
      return validateFreeBusyResult(value);
    case OSEKKAI_COMMANDS.opportunities:
      return validateOpportunitiesResult(value);
    case OSEKKAI_COMMANDS.decide:
      return validateDecideResponse(value);
    case OSEKKAI_COMMANDS.interventions:
      return payload.action === 'list'
        ? validateInterventionsResult(value)
        : payload.action === 'record'
          ? validateRecordOutcomeResponse(value)
          : { valid: false, errors: ['Intervention action is invalid'] };
    case OSEKKAI_COMMANDS.feedback:
      return validateFeedbackResponse(value);
    case OSEKKAI_COMMANDS.metrics:
      return validateMetricsResult(value);
    case OSEKKAI_COMMANDS.demoSeed:
      return validateDemoSeedResult(value);
    case OSEKKAI_COMMANDS.demoReset:
      return validateDemoResetResponse(value);
    case OSEKKAI_COMMANDS.cleanup:
      // cleanup is a maintenance-only CLI command and has no public JSON Schema.
      return validateCleanupResult(value);
    case OSEKKAI_COMMANDS.calendarConnect:
      return validateCalendarConnectResult(value);
    case OSEKKAI_COMMANDS.calendarCallback:
      return validateCalendarCallbackResult(value);
    case OSEKKAI_COMMANDS.calendarDisconnect:
      return validateCalendarDisconnectResult(value);
    case OSEKKAI_COMMANDS.sourcesSync:
    case OSEKKAI_COMMANDS.sourcesStatus:
      return validateSourceStatusResult(value);
    case OSEKKAI_COMMANDS.events:
      return validateEventMeshResult(value);
    case OSEKKAI_COMMANDS.eventRoute:
      return validateEventRouteResult(value);
  }
}

function assertReturnedOwners(
  value: unknown,
  expectedUserId: string,
  requestId: string | undefined,
  seen = new WeakSet<object>(),
): void {
  if (!value || typeof value !== 'object') {
    return;
  }
  if (seen.has(value)) {
    return;
  }
  seen.add(value);

  if (isRecord(value)) {
    const profile = validateDistanceProfile(value);
    const episode = validateInterventionEpisode(value);
    if (
      (profile.valid && profile.value.userId !== expectedUserId) ||
      (episode.valid && episode.value.userId !== expectedUserId)
    ) {
      ownerMismatch(requestId);
    }
    Object.values(value).forEach((child) =>
      assertReturnedOwners(child, expectedUserId, requestId, seen),
    );
    return;
  }

  if (Array.isArray(value)) {
    value.forEach((child) => assertReturnedOwners(child, expectedUserId, requestId, seen));
  }
}

/**
 * Validates Python data for the exact command/action and enforces that every
 * returned Profile or Episode belongs to the authenticated cookie user.
 */
export function validateOsekkaiCommandData<T = unknown>(
  command: OsekkaiCommand,
  payload: Readonly<JsonObject>,
  value: unknown,
  expectedUserId: string,
  requestId?: string,
): T {
  const result = resultForCommand(command, payload, value);
  if (!result.valid) {
    invalidResponse(requestId);
  }
  assertReturnedOwners(result.value, expectedUserId, requestId);
  return result.value as T;
}
