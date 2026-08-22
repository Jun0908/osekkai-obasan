import { describe, expect, it } from 'vitest';

import { isOsekkaiMutation, OSEKKAI_COMMANDS } from '../osekkai-commands';

describe('Osekkai command allowlist', () => {
  it('distinguishes intervention reads from writes', () => {
    expect(isOsekkaiMutation(OSEKKAI_COMMANDS.interventions, { action: 'list' })).toBe(false);
    expect(isOsekkaiMutation(OSEKKAI_COMMANDS.interventions, { action: 'record' })).toBe(true);
  });

  it('classifies state-changing commands', () => {
    expect(isOsekkaiMutation(OSEKKAI_COMMANDS.chat, {})).toBe(true);
    expect(isOsekkaiMutation(OSEKKAI_COMMANDS.decide, {})).toBe(true);
    expect(isOsekkaiMutation(OSEKKAI_COMMANDS.demoSeed, {})).toBe(true);
    expect(isOsekkaiMutation(OSEKKAI_COMMANDS.profileGet, {})).toBe(false);
  });
});
