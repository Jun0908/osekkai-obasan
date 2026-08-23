import type { JsonObject } from './api-client';

export type PreferenceMemory = {
  key: string;
  label: string;
  value: string;
  confidence?: number;
  evidence: Array<{ id: string; text: string; createdAt?: string }>;
};

export type ProfileView = {
  memoryConsent: boolean;
  pushConsent: boolean;
  quietStart: string;
  quietEnd: string;
  maxPushesPerWeek: number;
  preferredTone: string;
  maxTravelMinutes: number;
  maxBudgetYen: number;
  maxSocialIntensity: number;
  socialBattery: number | null;
  pauseUntil?: string;
  rejectionStreak: number;
  inferred: PreferenceMemory[];
};

export type OpportunityView = {
  id: string;
  title: string;
  startsAt?: string;
  endsAt?: string;
  address?: string;
  provider?: string;
  priceYen?: number;
  socialIntensity?: number;
  travelMinutes?: number;
  sourceUrl?: string;
  dataset?: string;
  verificationStatus?: string;
};

export type EpisodeView = {
  id: string;
  sequence?: number;
  decidedAt?: string;
  decision: string;
  shouldPush: boolean;
  reasonCodes: string[];
  message?: string;
  actionResponse?: string;
  distanceFeedback?: string;
  attendedAt?: string;
  revisitedAt?: string;
  selectedOpportunity?: OpportunityView;
  classification?: string;
};

export function isRecord(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function firstRecord(...values: unknown[]): JsonObject {
  for (const value of values) {
    if (isRecord(value)) return value;
  }
  return {};
}

export function readString(record: JsonObject, ...keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return undefined;
}

export function readNumber(record: JsonObject, ...keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return undefined;
}

export function readBoolean(record: JsonObject, fallback: boolean, ...keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'boolean') return value;
  }
  return fallback;
}

export function objectArray(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

const preferenceLabels: Record<string, string> = {
  preferredTone: '話し方',
  maxSocialIntensity: '人との関わりの強さ',
  socialBattery: 'Social Battery',
  preferredCategories: '好きかもしれないこと',
  avoidedCategories: '避けたいこと',
  conversationRequirement: '会話の少なさ',
  conversationPreference: '会話の少なさ',
  pushCadenceDelta: '声かけの頻度',
  'friction:search_fatigue': 'Eventを探す負担',
  'friction:first_time_anxiety': '初参加への不安',
  'friction:stranger_anxiety': '知らない人への不安',
  'friction:group_size': '人の多さ',
  'friction:conversation_load': '会話の多さ',
  'friction:travel_effort': '移動の負担',
  'friction:time_commitment': '拘束時間',
  'friction:cost': '料金の負担',
  'friction:low_social_energy': '人に会う余力',
  'friction:push_aversion': '誘い方の強さ',
  'friction:not_today': '今日ではない',
};

function printableValue(value: unknown): string {
  if (value === null || value === undefined) return '未設定';
  if (Array.isArray(value)) return value.map(printableValue).join('、');
  if (typeof value === 'boolean') return value ? 'はい' : 'いいえ';
  if (typeof value === 'object') return '学習済み';
  return String(value);
}

function normalizeMemories(value: unknown): PreferenceMemory[] {
  if (Array.isArray(value)) {
    return value.filter(isRecord).map((item, index) => {
      const key = readString(item, 'key', 'name', 'field') ?? `memory-${index}`;
      return {
        key,
        label: readString(item, 'label') ?? preferenceLabels[key] ?? key,
        value: printableValue(item.value),
        confidence: readNumber(item, 'confidence'),
        evidence: objectArray(item.evidence).flatMap((evidence) => {
          const id = readString(evidence, 'id');
          const text = readString(evidence, 'text');
          return id && text ? [{ id, text, createdAt: readString(evidence, 'createdAt') }] : [];
        }),
      };
    });
  }
  if (!isRecord(value)) return [];
  return Object.entries(value).map(([key, raw]) => {
    const detail = isRecord(raw) ? raw : {};
    const evidenceItems = objectArray(detail.evidence);
    return {
      key,
      label: preferenceLabels[key] ?? key,
      value: printableValue(isRecord(raw) && 'value' in raw ? raw.value : raw),
      confidence: readNumber(detail, 'confidence'),
      evidence: evidenceItems.flatMap((evidence) => {
        const id = readString(evidence, 'id');
        const text = readString(evidence, 'text');
        return id && text ? [{ id, text, createdAt: readString(evidence, 'createdAt') }] : [];
      }),
    };
  });
}

function normalizeParticipationFriction(value: unknown): PreferenceMemory[] {
  if (!isRecord(value)) return [];
  return Object.entries(value).flatMap(([name, raw]) => {
    if (!isRecord(raw)) return [];
    const key = `friction:${name}`;
    const evidence = objectArray(raw.evidence).flatMap((item) => {
      const id = readString(item, 'id');
      const text = readString(item, 'text');
      return id && text
        ? [{ id, text, createdAt: readString(item, 'lastConfirmedAt', 'observedAt') }]
        : [];
    });
    return [{
      key,
      label: preferenceLabels[key] ?? name,
      value: readString(raw, 'origin') === 'explicit' ? '本人が回答' : '会話から推定',
      confidence: readNumber(raw, 'confidence'),
      evidence,
    }];
  });
}

export function normalizeProfile(raw: unknown): ProfileView {
  const root = firstRecord(raw);
  const profile = firstRecord(root.profile, root.distanceProfile, raw);
  // Canonical P0 settings live at the profile top level. Older fixtures may
  // nest them, so merge those aliases while letting canonical fields win.
  const explicit: JsonObject = {
    ...firstRecord(profile.explicitPreferences),
    ...firstRecord(profile.explicit),
    ...firstRecord(profile.settings),
    ...profile,
  };
  const quiet = firstRecord(explicit.quietHours, profile.quietHours);
  const inferred = profile.inferredPreferences ?? profile.inferred ?? root.inferredPreferences;
  const batteryRaw = profile.socialBattery ?? firstRecord(inferred).socialBattery;
  const batteryDetail = firstRecord(batteryRaw);
  const socialBattery = typeof batteryRaw === 'number'
    ? batteryRaw
    : readNumber(batteryDetail, 'value', 'score') ?? null;

  return {
    memoryConsent: readBoolean(explicit, false, 'memoryConsent'),
    pushConsent: readBoolean(explicit, false, 'pushConsent'),
    quietStart: readString(quiet, 'start') ?? '21:00',
    quietEnd: readString(quiet, 'end') ?? '08:00',
    maxPushesPerWeek: readNumber(explicit, 'maxPushesPerWeek') ?? 2,
    preferredTone: readString(explicit, 'preferredTone') ?? 'gentle',
    maxTravelMinutes: readNumber(explicit, 'maxTravelMinutes') ?? 40,
    maxBudgetYen: readNumber(explicit, 'maxBudgetYen') ?? 2000,
    maxSocialIntensity: readNumber(explicit, 'maxSocialIntensity') ?? 2,
    socialBattery,
    pauseUntil: readString(profile, 'pauseUntil', 'cooldownUntil'),
    rejectionStreak: readNumber(profile, 'rejectionStreak') ?? 0,
    inferred: [
      ...normalizeMemories(inferred),
      ...normalizeParticipationFriction(profile.participationFriction),
    ],
  };
}

export function normalizeOpportunity(raw: unknown): OpportunityView | undefined {
  if (!isRecord(raw)) return undefined;
  const travel = firstRecord(raw.travelEstimate, raw.travel);
  return {
    id: readString(raw, 'id', 'opportunityId') ?? 'unknown-opportunity',
    title: readString(raw, 'title', 'name') ?? '名称未設定の候補',
    startsAt: readString(raw, 'startsAt', 'start'),
    endsAt: readString(raw, 'endsAt', 'end'),
    address: readString(raw, 'address', 'location'),
    provider: readString(raw, 'provider', 'organizer'),
    priceYen: readNumber(raw, 'priceYen', 'price'),
    socialIntensity: readNumber(raw, 'socialIntensity'),
    travelMinutes: readNumber(travel, 'minutes', 'durationMinutes') ?? readNumber(raw, 'travelMinutes'),
    sourceUrl: readString(raw, 'sourceUrl'),
    dataset: readString(raw, 'sourceDataset', 'dataset'),
    verificationStatus: readString(raw, 'verificationStatus'),
  };
}

export function normalizeEpisode(raw: unknown): EpisodeView | undefined {
  if (!isRecord(raw)) return undefined;
  const nested = firstRecord(raw.episode, raw.interventionEpisode);
  const source = Object.keys(nested).length ? nested : raw;
  const reasonCodes = Array.isArray(source.reasonCodes)
    ? source.reasonCodes.filter((value): value is string => typeof value === 'string')
    : [];
  return {
    id: readString(source, 'id', 'episodeId') ?? readString(raw, 'episodeId') ?? 'unknown-episode',
    sequence: readNumber(source, 'sequence'),
    decidedAt: readString(source, 'decidedAt', 'createdAt'),
    decision: readString(source, 'decision') ?? 'do_not_push',
    shouldPush: readBoolean(source, false, 'shouldPush'),
    reasonCodes,
    message: readString(source, 'message', 'notificationMessage'),
    actionResponse: readString(source, 'actionResponse'),
    distanceFeedback: readString(source, 'distanceFeedback'),
    attendedAt: readString(source, 'attendedAt'),
    revisitedAt: readString(source, 'revisitedAt'),
    selectedOpportunity: normalizeOpportunity(source.selectedOpportunity),
    classification: readString(source, 'metricClassification', 'classification'),
  };
}

export function extractEpisodes(raw: unknown): EpisodeView[] {
  const root = firstRecord(raw);
  const candidates = Array.isArray(raw)
    ? raw
    : root.interventions ?? root.episodes ?? root.items ?? [];
  if (!Array.isArray(candidates)) return [];
  return candidates
    .map(normalizeEpisode)
    .filter((item): item is EpisodeView => Boolean(item))
    .sort((left, right) => {
      if (left.sequence !== undefined || right.sequence !== undefined) {
        return (right.sequence ?? 0) - (left.sequence ?? 0);
      }
      const leftTime = left.decidedAt ? Date.parse(left.decidedAt) : Number.NaN;
      const rightTime = right.decidedAt ? Date.parse(right.decidedAt) : Number.NaN;
      return Number.isFinite(leftTime) && Number.isFinite(rightTime) ? rightTime - leftTime : 0;
    });
}

export function extractOpportunities(raw: unknown): OpportunityView[] {
  const root = firstRecord(raw);
  const candidates = Array.isArray(raw) ? raw : root.opportunities ?? root.items ?? root.candidates ?? [];
  return Array.isArray(candidates)
    ? candidates.map(normalizeOpportunity).filter((item): item is OpportunityView => Boolean(item))
    : [];
}

export function reasonLabel(code: string) {
  const labels: Record<string, string> = {
    NO_PUSH_CONSENT: '通知への同意がオフ',
    QUIET_HOURS: '静かにしてほしい時間帯',
    COOLDOWN_ACTIVE: 'いまは声をかけない期間',
    WEEKLY_LIMIT_REACHED: '今週の声かけ上限に到達',
    EXPLICIT_PAUSE: '本人が今週の休止を希望',
    EXPLICIT_NO_ACTION: '今日は何もしない希望を尊重',
    HUMAN_SUPPORT_REQUIRED: '人の支援を優先',
    NO_FREE_WINDOW: '十分な空き時間がない',
    NO_VERIFIED_OPPORTUNITY: '根拠を確認できる候補がない',
    OUTSIDE_FREE_WINDOW: '空き時間に収まらない',
    TRAVEL_LIMIT: '移動時間の上限を超える',
    OVER_BUDGET: '予算の上限を超える',
    SOCIAL_INTENSITY_LIMIT: '人との関わりが強すぎる',
    INVALID_SOURCE: '情報源を確認できない',
    SCORE_BELOW_THRESHOLD: '今は提案しない方がよい',
    FREE_WINDOW_AVAILABLE: '無理のない空き時間がある',
    LOW_SOCIAL_BATTERY: 'Social Batteryが低め',
    LOW_CONVERSATION_REQUIREMENT: '会話が少なくて済む',
    WITHIN_TRAVEL_LIMIT: '設定した移動時間内',
    UNDER_BUDGET: '設定した予算内',
  };
  return labels[code] ?? code.replaceAll('_', ' ').toLowerCase();
}

export function formatDateTime(value?: string) {
  if (!value) return '記録なし';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ja-JP', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function batteryBand(value: number | null) {
  if (value === null) return { label: 'まだわかりません', tone: 'unknown' };
  if (value <= 30) return { label: '低め。そっとしておく寄り', tone: 'low' };
  if (value <= 60) return { label: 'ほどほど', tone: 'medium' };
  return { label: '余力がありそう', tone: 'high' };
}
