import {
  type ValidationResult,
  validateChatRequest,
  validateCalendarCallbackRequest,
  validateDecideRequest,
  validateEventRouteRequest,
  validateMapEventsQuery,
  validateDemoResetRequest,
  validateFeedbackRequest,
  validateInterventionRecordRequest,
  validateProfileDeleteRequest,
  validateProfileUpdateRequest,
} from '@/lib/osekkai/validators.generated';

import { OSEKKAI_COMMANDS, type OsekkaiCommand } from './osekkai-commands';
import type { JsonObject } from './osekkai-contract';
import { OsekkaiHttpError } from './osekkai-errors';

const INVALID_REQUEST_MESSAGE = 'リクエスト内容を確認してください。';

function rejectRequest(requestId?: string): never {
  throw new OsekkaiHttpError(
    'VALIDATION_ERROR',
    INVALID_REQUEST_MESSAGE,
    400,
    requestId,
  );
}

function acceptGenerated<T>(
  result: ValidationResult<T>,
  payload: JsonObject,
  requestId?: string,
): JsonObject {
  if (!result.valid) {
    rejectRequest(requestId);
  }
  return payload;
}

function hasExactKeys(payload: JsonObject, keys: readonly string[]): boolean {
  const actual = Object.keys(payload);
  return actual.length === keys.length && keys.every((key) => actual.includes(key));
}

function validateReadPayload(
  command: OsekkaiCommand,
  payload: JsonObject,
  requestId?: string,
): JsonObject {
  if (command === OSEKKAI_COMMANDS.interventions) {
    return hasExactKeys(payload, ['action']) && payload.action === 'list'
      ? payload
      : rejectRequest(requestId);
  }
  if (command === OSEKKAI_COMMANDS.cleanup) {
    const keys = Object.keys(payload);
    const days = payload.retentionDays;
    const valid =
      keys.length <= 1 &&
      (days === undefined ||
        (typeof days === 'number' &&
          Number.isInteger(days) &&
          days >= 1 &&
          days <= 365));
    return valid ? payload : rejectRequest(requestId);
  }
  return Object.keys(payload).length === 0 ? payload : rejectRequest(requestId);
}

/**
 * Validates the canonical, transport-free CLI payload at the final Node/Python
 * trust boundary. Generated validators are mandatory for every public
 * mutation command; read-only and maintenance payloads are also closed here.
 */
export function validateOsekkaiCommandPayload(
  command: OsekkaiCommand,
  payload: JsonObject,
  requestId?: string,
): JsonObject {
  switch (command) {
    case OSEKKAI_COMMANDS.chat:
      return acceptGenerated(validateChatRequest(payload), payload, requestId);
    case OSEKKAI_COMMANDS.profileUpdate:
      return acceptGenerated(validateProfileUpdateRequest(payload), payload, requestId);
    case OSEKKAI_COMMANDS.profileDelete:
      return acceptGenerated(validateProfileDeleteRequest(payload), payload, requestId);
    case OSEKKAI_COMMANDS.feedback:
      return acceptGenerated(validateFeedbackRequest(payload), payload, requestId);
    case OSEKKAI_COMMANDS.decide:
      return acceptGenerated(validateDecideRequest(payload), payload, requestId);
    case OSEKKAI_COMMANDS.demoReset:
    case OSEKKAI_COMMANDS.demoSeed:
      return acceptGenerated(validateDemoResetRequest(payload), payload, requestId);
    case OSEKKAI_COMMANDS.interventions:
      return payload.action === 'record'
        ? acceptGenerated(validateInterventionRecordRequest(payload), payload, requestId)
          : validateReadPayload(command, payload, requestId);
    case OSEKKAI_COMMANDS.calendarCallback:
      return acceptGenerated(validateCalendarCallbackRequest(payload), payload, requestId);
    case OSEKKAI_COMMANDS.eventRoute:
      return acceptGenerated(validateEventRouteRequest(payload), payload, requestId);
    case OSEKKAI_COMMANDS.mapEvents:
      return acceptGenerated(validateMapEventsQuery(payload), payload, requestId);
    case OSEKKAI_COMMANDS.sourcesSync: {
      const keys = Object.keys(payload);
      const validKeys = keys.every((key) => key === 'force' || key === 'sourceIds');
      const validForce = payload.force === undefined || typeof payload.force === 'boolean';
      const validSources = payload.sourceIds === undefined || (
        Array.isArray(payload.sourceIds) &&
        payload.sourceIds.every((value) => typeof value === 'string' && value.length >= 1 && value.length <= 80)
      );
      return validKeys && validForce && validSources ? payload : rejectRequest(requestId);
    }
    default:
      return validateReadPayload(command, payload, requestId);
  }
}
