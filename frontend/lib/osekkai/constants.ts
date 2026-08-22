export const OSEKKAI_SCHEMA_VERSION = "1.0" as const;
export const OSEKKAI_CSRF_HEADER = "x-osekkai-csrf" as const;
export const OSEKKAI_IDEMPOTENCY_HEADER = "idempotency-key" as const;

export const OSEKKAI_COPY = {
  title: "おっせかいおばさん",
  lead: [
    "近づきすぎず、離れすぎず。",
    "あなたが一歩動ける瞬間だけ、",
    "東京がおっせかいする。"
  ],
  snapshotNotice:
    "公開データの過去スナップショットを使ったデモです。現在の開催情報ではありません。",
  syntheticNotice:
    "空き時間と移動時間は、個人の予定を含まない合成デモデータです。"
} as const;

export const CLASSIFICATION_LABELS = {
  measured: "実測",
  reference_estimate: "参考推計",
  demo: "デモシナリオ",
  unverified: "未検証"
} as const;

export const REASON_LABELS: Record<string, string> = {
  NO_PUSH_CONSENT: "提案の受け取りがオフです",
  QUIET_HOURS: "静かに過ごす時間です",
  COOLDOWN_ACTIVE: "いまは少し間をあけています",
  WEEKLY_LIMIT_REACHED: "今週の提案上限に達しています",
  EXPLICIT_PAUSE: "今週は休む設定です",
  EXPLICIT_NO_ACTION: "いまは何もしたくない気持ちを優先しました",
  HUMAN_SUPPORT_REQUIRED: "イベント提案より人の支えを優先しました",
  NO_FREE_WINDOW: "十分な空き時間がありません",
  NO_VERIFIED_OPPORTUNITY: "条件と出典を確認できる候補がありません",
  OUTSIDE_FREE_WINDOW: "空き時間に収まりません",
  TRAVEL_LIMIT: "移動時間の上限を超えます",
  OVER_BUDGET: "予算の上限を超えます",
  SOCIAL_INTENSITY_LIMIT: "人との関わりの強さが上限を超えます",
  INVALID_SOURCE: "出典を確認できません",
  SCORE_BELOW_THRESHOLD: "今は提案するタイミングではありません",
  FREE_WINDOW_AVAILABLE: "ゆとりのある空き時間があります",
  LOW_SOCIAL_BATTERY: "人と関わる余力が少ない状態に合わせました",
  LOW_CONVERSATION_REQUIREMENT: "会話をほとんど必要としません",
  WITHIN_TRAVEL_LIMIT: "希望する移動時間の範囲内です",
  UNDER_BUDGET: "希望する予算の範囲内です"
};
