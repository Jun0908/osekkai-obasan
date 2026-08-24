import { loadCommunityDirectorySummary } from '@/lib/osekkai/community-directory';

/**
 * Vercel-only fallback for /api/osekkai/chat when the Python bridge can't be
 * spawned. Calls OpenAI directly from Node (no Python), grounded in the same
 * community-directory CSV the map uses. Deliberately lightweight: no memory
 * is persisted server-side (the client resends recent turns each request),
 * and none of the Python-side friction/safety classification is replicated —
 * this is casual chat and activity introductions only, not a substitute for
 * the full conversation engine.
 */

export type LlmChatTurn = { speaker: 'you' | 'osekkai'; text: string };
export type LlmChatAction = 'start' | 'message' | 'check_in' | 'select';

const DEFAULT_MODEL = 'gpt-5.4-mini';
const DEFAULT_BASE_URL = 'https://api.openai.com/v1';
const GROUNDING_WARD = '千代田区';
const MAX_HISTORY_TURNS = 20;
const MAX_TURN_TEXT_LENGTH = 2000;

export function isLlmChatAvailable(): boolean {
  const key = (process.env.OPENAI_API_KEY ?? '').trim();
  if (!key) return false;
  const enabledRaw = (process.env.OSEKKAI_LLM_ENABLED ?? '').trim().toLowerCase();
  return !['0', 'false', 'no', 'off', 'disabled'].includes(enabledRaw);
}

export function parseLlmChatHistory(value: unknown): LlmChatTurn[] {
  if (!Array.isArray(value)) return [];
  const turns: LlmChatTurn[] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') continue;
    const record = item as Record<string, unknown>;
    const speaker = record.speaker;
    const text = record.text;
    if ((speaker === 'you' || speaker === 'osekkai') && typeof text === 'string' && text.trim()) {
      turns.push({ speaker, text: text.slice(0, MAX_TURN_TEXT_LENGTH) });
    }
  }
  return turns.slice(-MAX_HISTORY_TURNS);
}

async function buildGroundingNote(): Promise<string> {
  try {
    const summary = await loadCommunityDirectorySummary();
    const nearby = summary.facilities
      .filter((facility) => facility.ward === GROUNDING_WARD)
      .sort((left, right) => right.count - left.count)
      .slice(0, 6)
      .map((facility) => `- ${facility.name}（${facility.ward}、関連コミュニティ${facility.count}件）`)
      .join('\n');
    return nearby || '（付近の地域コミュニティ情報は現在取得できません）';
  } catch {
    return '（付近の地域コミュニティ情報は現在取得できません）';
  }
}

function systemInstructions(groundingNote: string): string {
  return [
    'あなたは「おっせかいおばさん」という、東京の地域コミュニティ活動を紹介する、世話好きだけど押しつけがましくない案内役です。',
    '一人称は「わたし」。やわらかく丁寧な話し言葉で、2〜4文程度の短い返信を心がけてください。',
    '相手の話をまず受け止め、質問は一度に一つだけにしてください。',
    'これは簡易デモモードで、深刻な相談・自傷や危険に関する話には対応できません。そうした話が出たら、地域の相談窓口や身近な信頼できる人へつながるよう促し、それ以上の提案は控えてください。',
    '以下は実在する地域コミュニティ拠点の参考情報です。関連する話題のときだけ自然に触れてください。存在しない日時・料金・定員などを断定的に作り話ししないでください。',
    groundingNote,
  ].join('\n');
}

function extractOutputText(body: unknown): string {
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>;
    if (typeof record.output_text === 'string' && record.output_text.trim()) {
      return record.output_text.trim();
    }
    const output = Array.isArray(record.output) ? record.output : [];
    const chunks: string[] = [];
    for (const item of output) {
      if (!item || typeof item !== 'object') continue;
      const content = (item as Record<string, unknown>).content;
      for (const part of Array.isArray(content) ? content : []) {
        if (!part || typeof part !== 'object') continue;
        const partRecord = part as Record<string, unknown>;
        if (partRecord.type === 'output_text' && typeof partRecord.text === 'string') {
          chunks.push(partRecord.text);
        }
      }
    }
    const joined = chunks.join('').trim();
    if (joined) return joined;
  }
  throw new Error('LLM_EMPTY_OUTPUT');
}

async function callOpenAiResponses(instructions: string, input: string): Promise<string> {
  const apiKey = (process.env.OPENAI_API_KEY ?? '').trim();
  const model = (process.env.OSEKKAI_LLM_MODEL ?? DEFAULT_MODEL).trim() || DEFAULT_MODEL;
  const baseUrl = (process.env.OPENAI_BASE_URL ?? DEFAULT_BASE_URL).trim().replace(/\/+$/, '') || DEFAULT_BASE_URL;
  const timeoutSecondsRaw = Number(process.env.OSEKKAI_LLM_TIMEOUT_SECONDS ?? '7');
  const timeoutMs = Math.min(20, Math.max(1, Number.isFinite(timeoutSecondsRaw) ? timeoutSecondsRaw : 7)) * 1000;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl}/responses`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, store: false, instructions, input, max_output_tokens: 500 }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`LLM_HTTP_${response.status}`);
    const body: unknown = await response.json();
    return extractOutputText(body);
  } finally {
    clearTimeout(timer);
  }
}

export async function generateLlmChatReply(options: {
  action: LlmChatAction;
  message?: string;
  history: LlmChatTurn[];
}): Promise<string> {
  const instructions = systemInstructions(await buildGroundingNote());
  const historyText = options.history
    .map((turn) => `${turn.speaker === 'you' ? 'ユーザー' : 'おっせかいおばさん'}: ${turn.text}`)
    .join('\n');
  const latest = options.action === 'start'
    ? '（会話開始。まず一言、気さくに挨拶して、どんなことに興味があるか聞いてください）'
    : (options.message ?? '');
  const input = historyText ? `${historyText}\nユーザー: ${latest}` : `ユーザー: ${latest}`;
  return callOpenAiResponses(instructions, input);
}
