import { pickCommunityExamples, type CommunityExample, type CommunityGenreFilter } from '@/lib/osekkai/community-directory';

/**
 * Vercel-only fallback for /api/osekkai/chat when the Python bridge can't be
 * spawned. Calls OpenAI directly from Node (no Python), grounded in the same
 * community-directory CSV the map uses. Deliberately lightweight: no memory
 * is persisted server-side (the client resends recent turns each request),
 * and none of the Python-side friction/safety classification is replicated —
 * this is casual chat and activity introductions only, not a substitute for
 * the full conversation engine.
 *
 * The opening line is a fixed string (see FIXED_START_GREETING), not an LLM
 * call — a first-visit request is the most likely to hit a cold Vercel
 * function, and a slow/failed greeting reads as "she never speaks first."
 * From the first real user message onward, every reply is required (via the
 * system prompt) to name up to three real communities pulled from the CSV —
 * there is no real user profile to narrow candidates by relevance the way
 * the Python engine does, so this narrows by data quality (a resolvable
 * venue over a generic ward-office catch-all) and freshness instead, and is
 * framed to the model as "here are some examples," never as a personalized
 * pick.
 */

export type LlmChatTurn = { speaker: 'you' | 'osekkai'; text: string };
export type LlmChatAction = 'start' | 'message' | 'check_in' | 'select';

export const FIXED_START_GREETING = 'まず、最近ちょっと気になってることを一つ聞かせて。';

const DEFAULT_MODEL = 'gpt-5.4-mini';
const DEFAULT_BASE_URL = 'https://api.openai.com/v1';
const MAX_HISTORY_TURNS = 20;
const MAX_TURN_TEXT_LENGTH = 2000;
const EXAMPLE_COUNT = 3;

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

const GENRE_KEYWORDS: Record<CommunityGenreFilter, string[]> = {
  sports: ['スポーツ', '運動', '体操', 'ヨガ', 'ウォーキング', 'ジョギング', '卓球', 'テニス', 'バスケ', 'バレー', 'サッカー', '野球', 'ダンス', '武道', '空手', '柔道', '筋トレ', 'ストレッチ', '球技', '水泳'],
  music_culture: ['音楽', '文化', '美術', '絵', '書道', '茶道', '華道', '楽器', '歌', '合唱', '工芸', '写真', '演劇', 'アート'],
  learning: ['学習', '勉強', '語学', '英語', '読書', '歴史', '講座', '教室', 'パソコン', '資格'],
  social: ['交流', 'ボランティア', '貢献', '地域活動', '子育て', '福祉'],
};

function detectGenre(text: string): CommunityGenreFilter | null {
  for (const genre of Object.keys(GENRE_KEYWORDS) as CommunityGenreFilter[]) {
    if (GENRE_KEYWORDS[genre].some((keyword) => text.includes(keyword))) return genre;
  }
  return null;
}

const WARD_NAMES = [
  '千代田区', '中央区', '港区', '新宿区', '文京区', '台東区', '墨田区', '江東区', '品川区', '目黒区',
  '大田区', '世田谷区', '渋谷区', '中野区', '杉並区', '豊島区', '北区', '荒川区', '板橋区', '練馬区',
  '足立区', '葛飾区', '江戸川区',
];

function detectWard(text: string): string | null {
  return WARD_NAMES.find((ward) => text.includes(ward)) ?? null;
}

// Always returns up to EXAMPLE_COUNT real communities: narrows by genre and
// ward when detected, but broadens step by step (drop ward, drop genre)
// rather than ever coming back empty — "must always show 3" beats "must
// match exactly what was asked."
async function pickActivities(genre: CommunityGenreFilter | null, ward: string | null): Promise<CommunityExample[]> {
  const attempts: Array<{ genre?: CommunityGenreFilter; ward?: string }> = [];
  if (genre && ward) attempts.push({ genre, ward });
  if (genre) attempts.push({ genre });
  if (ward) attempts.push({ ward });
  attempts.push({});
  for (const attempt of attempts) {
    const found = await pickCommunityExamples({ ...attempt, limit: EXAMPLE_COUNT });
    if (found.length >= EXAMPLE_COUNT) return found;
  }
  return pickCommunityExamples({ limit: EXAMPLE_COUNT });
}

function activitiesNote(activities: CommunityExample[]): string {
  if (activities.length === 0) {
    return '（実例を取得できませんでした。一般的な案内にとどめ、存在しない団体名を作り話ししないでください）';
  }
  return activities
    .map((item) => `- ${item.name}（${item.ward}${item.description ? `、${item.description}` : ''}）`)
    .join('\n');
}

function systemInstructions(activitiesText: string): string {
  return [
    'あなたは「おっせかいおばさん」という、東京の地域コミュニティ活動を紹介する、世話好きだけど押しつけがましくない案内役です。',
    '一人称は「わたし」。二人称は「あんた」も使ってよい、砕けた親しみやすい話し言葉で、2〜4文程度の短い返信にしてください。',
    '相手の話をまず一言だけ受け止めてください。',
    '質問を重ねて絞り込もうとしないでください。次の返信では、必ず下記の実例（最大3件）をそのまま短く紹介してください。3件に満たない場合はある分だけ紹介し、存在しない団体名・日時・料金・定員を作り話ししないでください。',
    '「あなたに一番合う」のような、個人の好みに合わせて選んだかのような言い方はせず、「こういうのがあるよ」という紹介の言い方にしてください。',
    'これは簡易デモモードで、深刻な相談・自傷や危険に関する話には対応できません。そうした話が出たら、地域の相談窓口や身近な信頼できる人へつながるよう促し、それ以上の提案は控えてください。',
    '実在する地域コミュニティの参考情報（この中から選んで紹介してください）:',
    activitiesText,
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
  const combinedText = [...options.history.map((turn) => turn.text), options.message ?? ''].join(' ');
  const genre = detectGenre(combinedText);
  const ward = detectWard(combinedText);
  const activities = await pickActivities(genre, ward);
  const instructions = systemInstructions(activitiesNote(activities));
  const historyText = options.history
    .map((turn) => `${turn.speaker === 'you' ? 'ユーザー' : 'おっせかいおばさん'}: ${turn.text}`)
    .join('\n');
  const latest = options.message ?? '';
  const input = historyText ? `${historyText}\nユーザー: ${latest}` : `ユーザー: ${latest}`;
  return callOpenAiResponses(instructions, input);
}
