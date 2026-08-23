import { describe, expect, it } from 'vitest';

import {
  validateChatRequest,
  validateDecideRequest,
  validateDemoResetRequest,
  validateFeedbackRequest,
  validateInterventionRecordRequest,
  validateMapEventsQuery,
  validateProfileDeleteRequest,
  validateProfileUpdateRequest,
} from '@/lib/osekkai/validators.generated';

import { OSEKKAI_COMMANDS } from '../osekkai-commands';
import { validateOsekkaiCommandPayload } from '../osekkai-request-validation';

const EPISODE_ID = '33333333-3333-4333-8333-333333333333';

describe('generated Osekkai mutation request validators', () => {
  it('accepts only the closed chat request shape', () => {
    expect(validateChatRequest({ message: 'hello', remember: false }).valid).toBe(true);
    expect(validateChatRequest({ action: 'start', remember: false }).valid).toBe(true);
    expect(validateChatRequest({ action: 'select', opportunityId: 'event-1' }).valid).toBe(true);
    expect(validateChatRequest({ action: 'check_in', message: 'また行きたい' }).valid).toBe(true);
    expect(validateChatRequest({ action: 'select', message: 'event-1' }).valid).toBe(false);
    expect(validateChatRequest({ message: '   ' }).valid).toBe(false);
    expect(validateChatRequest({ message: 'hello', remember: 'yes' }).valid).toBe(false);
    expect(validateChatRequest({ message: 'hello', unknown: true }).valid).toBe(false);
    expect(validateChatRequest({ message: 'hello', idempotencyKey: 'transport-only' }).valid).toBe(
      false,
    );
  });

  it('validates canonical profile operations and rejects wrong field types', () => {
    expect(
      validateProfileUpdateRequest({
        patch: {
          memoryConsent: true,
          quietHours: { start: '21:00', end: '08:00', timezone: 'Asia/Tokyo' },
        },
      }).valid,
    ).toBe(true);
    expect(validateProfileUpdateRequest({ pauseOneWeek: true }).valid).toBe(true);
    expect(
      validateProfileUpdateRequest({ removeEvidenceId: '33333333-3333-4333-8333-333333333333' })
        .valid,
    ).toBe(true);
    expect(validateProfileUpdateRequest({ patch: { memoryConsent: 'yes' } }).valid).toBe(false);
    expect(validateProfileUpdateRequest({ patch: { socialBattery: 80 } }).valid).toBe(false);
    expect(validateProfileUpdateRequest({}).valid).toBe(false);
  });

  it('requires exactly one canonical feedback value', () => {
    expect(
      validateFeedbackRequest({ episodeId: EPISODE_ID, actionResponse: 'accepted' }).valid,
    ).toBe(true);
    expect(
      validateFeedbackRequest({ episodeId: EPISODE_ID, distanceFeedback: 'just_right' }).valid,
    ).toBe(true);
    expect(validateFeedbackRequest({ episodeId: EPISODE_ID }).valid).toBe(false);
    expect(
      validateFeedbackRequest({
        episodeId: EPISODE_ID,
        actionResponse: 'accepted',
        distanceFeedback: 'just_right',
      }).valid,
    ).toBe(false);
    expect(
      validateFeedbackRequest({ episodeId: EPISODE_ID, actionResponse: 'maybe' }).valid,
    ).toBe(false);
  });

  it('validates intervention record action, enum, and exact event source', () => {
    expect(
      validateInterventionRecordRequest({
        action: 'record',
        episodeId: EPISODE_ID,
        eventType: 'attendance',
        status: 'attended',
      }).valid,
    ).toBe(true);
    expect(
      validateInterventionRecordRequest({
        action: 'record',
        episodeId: EPISODE_ID,
        outcome: 'self_initiated',
      }).valid,
    ).toBe(true);
    expect(
      validateInterventionRecordRequest({
        action: 'record',
        episodeId: EPISODE_ID,
        eventType: 'attendance',
        outcome: 'attended',
      }).valid,
    ).toBe(false);
    expect(
      validateInterventionRecordRequest({
        action: 'record',
        episodeId: EPISODE_ID,
        eventType: 'unknown',
      }).valid,
    ).toBe(false);
  });

  it('keeps decide and demo reset empty and delete explicitly confirmed', () => {
    expect(validateDecideRequest({}).valid).toBe(true);
    expect(validateDemoResetRequest({}).valid).toBe(true);
    expect(validateProfileDeleteRequest({ confirm: true }).valid).toBe(true);
    expect(validateDecideRequest({ score: 1 }).valid).toBe(false);
    expect(validateDemoResetRequest({ seeded: true }).valid).toBe(false);
    expect(validateProfileDeleteRequest({ confirm: false }).valid).toBe(false);
    expect(validateProfileDeleteRequest({ confirm: true, userId: EPISODE_ID }).valid).toBe(false);
  });
});

describe('Node/Python request validation boundary', () => {
  it('applies generated validation after transport fields are separated', () => {
    expect(
      validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.chat, { message: 'hello' }),
    ).toEqual({ message: 'hello' });
    expect(() =>
      validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.chat, {
        message: 'hello',
        idempotencyKey: 'must-not-enter-python-payload',
      }),
    ).toThrowError(expect.objectContaining({ code: 'VALIDATION_ERROR', status: 400 }));
  });

  it('closes intervention list and maintenance payloads too', () => {
    expect(
      validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.interventions, { action: 'list' }),
    ).toEqual({ action: 'list' });
    expect(() =>
      validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.interventions, {
        action: 'list',
        unknown: true,
      }),
    ).toThrowError(expect.objectContaining({ code: 'VALIDATION_ERROR', status: 400 }));
    expect(
      validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.cleanup, { retentionDays: 30 }),
    ).toEqual({ retentionDays: 30 });
    expect(() =>
      validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.cleanup, { retentionDays: 0 }),
    ).toThrowError(expect.objectContaining({ code: 'VALIDATION_ERROR', status: 400 }));
  });

  it('keeps the private atomic demo seed payload empty', () => {
    expect(
      validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.demoSeed, {}),
    ).toEqual({});
    expect(() =>
      validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.demoSeed, { seeded: true }),
    ).toThrowError(expect.objectContaining({ code: 'VALIDATION_ERROR', status: 400 }));
  });

  it('bounds the Chiyoda map feed before it reaches Python', () => {
    const query = { scope: 'chiyoda_kojimachi', offset: 0, limit: 250 };
    expect(validateMapEventsQuery(query).valid).toBe(true);
    expect(validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.mapEvents, query)).toEqual(query);
    expect(validateMapEventsQuery({ ...query, limit: 251 }).valid).toBe(false);
    expect(validateMapEventsQuery({ ...query, scope: 'tokyo_all' }).valid).toBe(false);
    expect(() => validateOsekkaiCommandPayload(OSEKKAI_COMMANDS.mapEvents, {
      ...query,
      unknown: true,
    })).toThrowError(expect.objectContaining({ code: 'VALIDATION_ERROR', status: 400 }));
  });
});
