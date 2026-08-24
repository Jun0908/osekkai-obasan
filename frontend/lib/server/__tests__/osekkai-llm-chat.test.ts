import { afterEach, describe, expect, it } from 'vitest';

import { isLlmChatAvailable, parseLlmChatHistory } from '../osekkai-llm-chat';

const ORIGINAL_KEY = process.env.OPENAI_API_KEY;
const ORIGINAL_ENABLED = process.env.OSEKKAI_LLM_ENABLED;

afterEach(() => {
  if (ORIGINAL_KEY === undefined) delete process.env.OPENAI_API_KEY;
  else process.env.OPENAI_API_KEY = ORIGINAL_KEY;
  if (ORIGINAL_ENABLED === undefined) delete process.env.OSEKKAI_LLM_ENABLED;
  else process.env.OSEKKAI_LLM_ENABLED = ORIGINAL_ENABLED;
});

describe('isLlmChatAvailable', () => {
  it('is false when no API key is configured', () => {
    delete process.env.OPENAI_API_KEY;
    expect(isLlmChatAvailable()).toBe(false);
  });

  it('is true when a key is present and the flag is unset', () => {
    process.env.OPENAI_API_KEY = 'sk-test';
    delete process.env.OSEKKAI_LLM_ENABLED;
    expect(isLlmChatAvailable()).toBe(true);
  });

  it('is false when explicitly disabled despite a key being present', () => {
    process.env.OPENAI_API_KEY = 'sk-test';
    process.env.OSEKKAI_LLM_ENABLED = 'false';
    expect(isLlmChatAvailable()).toBe(false);
  });
});

describe('parseLlmChatHistory', () => {
  it('keeps only well-formed turns', () => {
    const result = parseLlmChatHistory([
      { speaker: 'you', text: 'ヨガに興味あります' },
      { speaker: 'osekkai', text: 'ええですね！' },
      { speaker: 'someone-else', text: 'invalid speaker' },
      { speaker: 'you', text: '' },
      { speaker: 'you' },
      'not an object',
      null,
    ]);
    expect(result).toEqual([
      { speaker: 'you', text: 'ヨガに興味あります' },
      { speaker: 'osekkai', text: 'ええですね！' },
    ]);
  });

  it('returns an empty array for non-array input', () => {
    expect(parseLlmChatHistory(undefined)).toEqual([]);
    expect(parseLlmChatHistory('not an array')).toEqual([]);
  });

  it('caps the number of retained turns to the most recent 20', () => {
    const many = Array.from({ length: 30 }, (_, index) => ({ speaker: 'you', text: `turn-${index}` }));
    const result = parseLlmChatHistory(many);
    expect(result).toHaveLength(20);
    expect(result[0].text).toBe('turn-10');
    expect(result[19].text).toBe('turn-29');
  });

  it('truncates overly long turn text', () => {
    const result = parseLlmChatHistory([{ speaker: 'you', text: 'a'.repeat(3000) }]);
    expect(result[0].text).toHaveLength(2000);
  });
});
