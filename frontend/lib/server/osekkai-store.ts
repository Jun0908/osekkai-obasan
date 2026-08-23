import { OSEKKAI_COMMANDS } from './osekkai-commands';
import type { JsonObject, OsekkaiCommandResult } from './osekkai-contract';
import { invokeOsekkaiCommand } from './osekkai-openclaw-bridge';

// These functions are intentionally thin. Python remains the only owner of
// Osekkai persistence, provider data, policy, and aggregate calculations.
export function getOsekkaiProfile<T = unknown>(userId: string): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({ command: OSEKKAI_COMMANDS.profileGet, userId });
}

export function updateOsekkaiProfile<T = unknown>(
  userId: string,
  payload: JsonObject,
  idempotencyKey: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.profileUpdate,
    userId,
    payload,
    idempotencyKey,
  });
}

export function deleteOsekkaiProfile<T = unknown>(
  userId: string,
  idempotencyKey: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.profileDelete,
    userId,
    payload: { confirm: true },
    idempotencyKey,
  });
}

export function runOsekkaiChat<T = unknown>(
  userId: string,
  payload: JsonObject,
  idempotencyKey: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.chat,
    userId,
    payload,
    idempotencyKey,
  });
}

export function getOsekkaiFreebusy<T = unknown>(userId: string): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({ command: OSEKKAI_COMMANDS.freebusy, userId });
}

export function startGoogleCalendarConnection<T = unknown>(
  userId: string,
  idempotencyKey: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.calendarConnect,
    userId,
    payload: {},
    idempotencyKey,
  });
}

export function completeGoogleCalendarConnection<T = unknown>(
  userId: string,
  payload: JsonObject,
  idempotencyKey: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.calendarCallback,
    userId,
    payload,
    idempotencyKey,
  });
}

export function disconnectGoogleCalendar<T = unknown>(
  userId: string,
  idempotencyKey: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.calendarDisconnect,
    userId,
    payload: {},
    idempotencyKey,
  });
}

export function getOsekkaiOpportunities<T = unknown>(
  userId: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({ command: OSEKKAI_COMMANDS.opportunities, userId });
}

export function getOsekkaiSourceStatus<T = unknown>(userId: string): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({ command: OSEKKAI_COMMANDS.sourcesStatus, userId });
}

export function syncOsekkaiSources<T = unknown>(
  userId: string,
  payload: JsonObject,
  idempotencyKey: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.sourcesSync,
    userId,
    payload,
    idempotencyKey,
  });
}

export function getOsekkaiEvents<T = unknown>(userId: string): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({ command: OSEKKAI_COMMANDS.events, userId });
}

export function getOsekkaiEventRoute<T = unknown>(
  userId: string,
  payload: JsonObject,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({ command: OSEKKAI_COMMANDS.eventRoute, userId, payload });
}

export function decideOsekkaiIntervention<T = unknown>(
  userId: string,
  idempotencyKey: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.decide,
    userId,
    payload: {},
    idempotencyKey,
  });
}

export function getOsekkaiInterventions<T = unknown>(
  userId: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.interventions,
    userId,
    payload: { action: 'list' },
  });
}

export function recordOsekkaiIntervention<T = unknown>(
  userId: string,
  payload: JsonObject,
  idempotencyKey: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.interventions,
    userId,
    payload: { ...payload, action: 'record' },
    idempotencyKey,
  });
}

export function recordOsekkaiFeedback<T = unknown>(
  userId: string,
  payload: JsonObject,
  idempotencyKey: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.feedback,
    userId,
    payload,
    idempotencyKey,
  });
}

export function resetOsekkaiDemo<T = unknown>(
  userId: string,
  idempotencyKey: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.demoReset,
    userId,
    payload: {},
    idempotencyKey,
  });
}

export function seedOsekkaiDemo<T = unknown>(
  userId: string,
  idempotencyKey: string,
): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({
    command: OSEKKAI_COMMANDS.demoSeed,
    userId,
    idempotencyKey,
  });
}
