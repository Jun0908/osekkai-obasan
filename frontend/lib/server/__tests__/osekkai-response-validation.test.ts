import { describe, expect, it } from 'vitest';

import profileFixture from '../../../../agents-OpenClaw/fixtures/osekkai/profile.json';

import { OSEKKAI_COMMANDS } from '../osekkai-commands';
import { buildOsekkaiChildEnv } from '../osekkai-openclaw-bridge';
import { validateOsekkaiCommandData } from '../osekkai-response-validation';

const EXPECTED_USER_ID = '11111111-1111-4111-8111-111111111111';
const WRONG_USER_ID = '22222222-2222-4222-8222-222222222222';
const NOW = '2019-02-23T10:00:00+09:00';

function minimalEpisode(userId: string) {
  return {
    schemaVersion: '1.0',
    id: '33333333-3333-4333-8333-333333333333',
    userId,
    sequence: 1,
    policyVersion: 'osekkai-p0-v1',
    decision: 'do_not_push',
    shouldPush: false,
    reasonCodes: ['EXPLICIT_NO_ACTION'],
    score: null,
    profileSnapshot: null,
    freeWindowSnapshot: null,
    candidateIdsBeforeFilter: [],
    candidateIdsAfterFilter: [],
    excludedCandidates: [],
    selectedOpportunity: null,
    notification: null,
    dataMode: 'demo',
    metricClassification: 'demo',
    minimalRecord: true,
    pushedAt: null,
    noPushAt: NOW,
    actionResponse: null,
    actionResponseAt: null,
    distanceFeedback: null,
    distanceFeedbackAt: null,
    attendedAt: null,
    revisitedAt: null,
    selfInitiatedAt: null,
    createdAt: NOW,
    updatedAt: NOW,
  };
}

describe('Python response validation boundary', () => {
  it('accepts a schema-valid profile owned by the authenticated user', () => {
    expect(
      validateOsekkaiCommandData(
        OSEKKAI_COMMANDS.profileGet,
        {},
        profileFixture,
        EXPECTED_USER_ID,
      ),
    ).toEqual(profileFixture);
  });

  it('rejects an invalid command response with a fixed 502 error', () => {
    expect(() =>
      validateOsekkaiCommandData(
        OSEKKAI_COMMANDS.profileGet,
        {},
        { ...profileFixture, memoryConsent: 'yes' },
        EXPECTED_USER_ID,
      ),
    ).toThrowError(
      expect.objectContaining({
        code: 'PYTHON_INVALID_RESPONSE',
        status: 502,
        message: 'おっせかいエンジンの応答形式が正しくありません。',
      }),
    );
  });

  it('rejects a valid Profile owned by another user', () => {
    expect(() =>
      validateOsekkaiCommandData(
        OSEKKAI_COMMANDS.profileGet,
        {},
        { ...profileFixture, userId: WRONG_USER_ID },
        EXPECTED_USER_ID,
      ),
    ).toThrowError(
      expect.objectContaining({ code: 'PYTHON_OWNER_MISMATCH', status: 502 }),
    );
  });

  it('finds a wrong-owner Episode nested inside an array', () => {
    expect(() =>
      validateOsekkaiCommandData(
        OSEKKAI_COMMANDS.interventions,
        { action: 'list' },
        { schemaVersion: '1.0', interventions: [minimalEpisode(WRONG_USER_ID)] },
        EXPECTED_USER_ID,
      ),
    ).toThrowError(
      expect.objectContaining({ code: 'PYTHON_OWNER_MISMATCH', status: 502 }),
    );
  });

  it('validates the exact atomic demo seed result and its Profile owner', () => {
    const result = {
      schemaVersion: '1.0',
      dataMode: 'demo',
      seeded: true,
      profile: profileFixture,
    };
    expect(
      validateOsekkaiCommandData(
        OSEKKAI_COMMANDS.demoSeed,
        {},
        result,
        EXPECTED_USER_ID,
      ),
    ).toEqual(result);
    expect(() =>
      validateOsekkaiCommandData(
        OSEKKAI_COMMANDS.demoSeed,
        {},
        { ...result, unexpected: true },
        EXPECTED_USER_ID,
      ),
    ).toThrowError(expect.objectContaining({ code: 'PYTHON_INVALID_RESPONSE', status: 502 }));
    expect(() =>
      validateOsekkaiCommandData(
        OSEKKAI_COMMANDS.demoSeed,
        {},
        { ...result, profile: { ...profileFixture, userId: WRONG_USER_ID } },
        EXPECTED_USER_ID,
      ),
    ).toThrowError(expect.objectContaining({ code: 'PYTHON_OWNER_MISMATCH', status: 502 }));
  });
});

describe('Python child environment allowlist', () => {
  it('keeps required runtime values without leaking application secrets', () => {
    const env = buildOsekkaiChildEnv({
      Path: 'C:\\safe-bin',
      SystemRoot: 'C:\\Windows',
      TEMP: 'C:\\Temp',
      NODE_ENV: 'test',
      OSEKKAI_DEMO_MODE: 'true',
      OSEKKAI_SESSION_SECRET: 'must-not-leak',
      OSEKKAI_SESSION_SECRET_PREVIOUS: 'must-not-leak-either',
      OPENAI_API_KEY: 'must-not-leak',
      DATABASE_URL: 'must-not-leak',
    });

    expect(env.PATH).toBe('C:\\safe-bin');
    expect(env.SystemRoot).toBe('C:\\Windows');
    expect(env.OSEKKAI_DEMO_MODE).toBe('true');
    expect(env.PYTHONIOENCODING).toBe('utf-8');
    expect(env.OSEKKAI_DATA_ROOT).toBeTruthy();
    expect(env.OSEKKAI_SESSION_SECRET).toBeUndefined();
    expect(env.OSEKKAI_SESSION_SECRET_PREVIOUS).toBeUndefined();
    expect(env.OPENAI_API_KEY).toBeUndefined();
    expect(env.DATABASE_URL).toBeUndefined();
  });
});
