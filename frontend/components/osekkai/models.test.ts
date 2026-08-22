import { describe, expect, it } from 'vitest';

import { extractEpisodes, normalizeProfile, reasonLabel } from './models';

describe('Osekkai UI model normalization', () => {
  it('keeps explicit settings separate from inferred memories', () => {
    const profile = normalizeProfile({
      memoryConsent: true,
      pushConsent: false,
      maxSocialIntensity: 2,
      quietHours: { start: '22:00', end: '07:30' },
      explicitPreferences: { demoSeed: { value: true } },
      socialBattery: 24,
      inferredPreferences: {
        preferredTone: {
          value: 'gentle',
          confidence: 0.82,
          evidence: '静かに話してほしい',
        },
      },
    });

    expect(profile.pushConsent).toBe(false);
    expect(profile.socialBattery).toBe(24);
    expect(profile.quietStart).toBe('22:00');
    expect(profile.inferred).toEqual([
      expect.objectContaining({
        key: 'preferredTone',
        value: 'gentle',
        confidence: 0.82,
      }),
    ]);
  });

  it('normalizes PUSH and no-PUSH episodes returned by the Python envelope', () => {
    const episodes = extractEpisodes({
      interventions: [
        {
          id: 'episode-push',
          sequence: 2,
          shouldPush: true,
          decision: 'suggest_solo_place',
          reasonCodes: ['LOW_CONVERSATION_REQUIREMENT'],
          selectedOpportunity: { id: 'event-1', title: '静かな展示' },
        },
        {
          id: 'episode-no-push',
          sequence: 1,
          shouldPush: false,
          decision: 'do_not_push',
          reasonCodes: ['EXPLICIT_NO_ACTION'],
        },
      ],
    });

    expect(episodes).toHaveLength(2);
    expect(episodes[0]).toMatchObject({ shouldPush: true, selectedOpportunity: { title: '静かな展示' } });
    expect(episodes[0].sequence).toBe(2);
    expect(episodes[1]).toMatchObject({ shouldPush: false, reasonCodes: ['EXPLICIT_NO_ACTION'] });
    expect(reasonLabel('EXPLICIT_NO_ACTION')).toContain('何もしない');
  });

  it('orders equal-time episodes by the monotonic sequence', () => {
    const episodes = extractEpisodes({
      interventions: [
        { id: 'first', sequence: 1, createdAt: '2019-02-23T10:00:00+09:00', shouldPush: false },
        { id: 'second', sequence: 2, createdAt: '2019-02-23T10:00:00+09:00', shouldPush: true },
      ],
    });

    expect(episodes.map((episode) => episode.id)).toEqual(['second', 'first']);
  });
});
