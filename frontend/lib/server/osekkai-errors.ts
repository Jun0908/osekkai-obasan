import { randomUUID } from 'crypto';

export class OsekkaiHttpError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId?: string;

  constructor(code: string, message: string, status: number, requestId?: string) {
    super(message);
    this.name = 'OsekkaiHttpError';
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

export function createRequestId(): string {
  return randomUUID();
}

export function statusForCliError(code: string): number {
  switch (code) {
    case 'NOT_FOUND':
    case 'EPISODE_NOT_FOUND':
    case 'EVENT_NOT_FOUND':
      return 404;
    case 'CONFLICT':
    case 'INVALID_STATE_TRANSITION':
    case 'FEEDBACK_ALREADY_RECORDED':
    case 'IDEMPOTENCY_CONFLICT':
    case 'CALENDAR_NOT_CONNECTED':
      return 409;
    case 'VALIDATION_ERROR':
    case 'INVALID_REQUEST':
      return 400;
    case 'DEMO_MODE_DISABLED':
      return 404;
    case 'PROVIDER_ERROR':
    case 'PROVIDER_UNAVAILABLE':
      return 502;
    case 'STORAGE_ERROR':
    case 'LOCK_TIMEOUT':
    case 'ROUTES_CREDENTIAL_MISSING':
    case 'ROUTES_QUOTA_EXCEEDED':
    case 'ROUTES_TIMEOUT':
    case 'ROUTES_UNAVAILABLE':
      return 503;
    default:
      return 422;
  }
}

export function publicCliError(code: string, requestId: string): OsekkaiHttpError {
  const messages: Record<string, string> = {
    VALIDATION_ERROR: 'リクエスト内容を確認してください。',
    DEMO_MODE_DISABLED: 'ページが見つかりません。',
    EPISODE_NOT_FOUND: '介入エピソードが見つかりません。',
    FEEDBACK_ALREADY_RECORDED: 'この反応はすでに記録されています。',
    IDEMPOTENCY_CONFLICT: '同じ操作キーを別の内容には使えません。',
    STORAGE_UNAVAILABLE: '保存領域を利用できません。時間をおいてお試しください。',
    PROVIDER_UNAVAILABLE: '候補または空き時間を取得できません。',
    CALENDAR_NOT_CONNECTED: 'Google Calendarを接続してください。予定の中身ではなく、空き時間だけを使います。',
    CALENDAR_CONNECTION_FAILED: 'Google Calendarを接続できませんでした。設定を確認してください。',
    ROUTES_CREDENTIAL_MISSING: 'Google RoutesのAPI keyが未設定です。',
    ROUTES_QUOTA_EXCEEDED: 'Google Routesの利用上限に達しました。時間をおいてお試しください。',
    ROUTES_TIMEOUT: 'Google Routesが応答しませんでした。もう一度お試しください。',
    ROUTES_UNAVAILABLE: 'Google Routesを一時的に利用できません。',
    ROUTES_ZERO_RESULTS: 'このEventまでの実移動経路を確認できませんでした。',
    ROUTES_AUTH_FAILED: 'Google Routesの接続設定を確認できませんでした。',
    ROUTES_REQUEST_FAILED: 'Google Routesから実移動時間を取得できませんでした。',
    ROUTES_LOCATION_MISSING: 'このEventの場所を確認できませんでした。',
    ROUTES_LOCATION_INVALID: '現在地またはEventの場所を確認できませんでした。',
    ROUTES_RESPONSE_INVALID: 'Google Routesの応答を確認できませんでした。',
    EVENT_NOT_FOUND: 'このEventは更新後の一覧にありません。',
    INTERNAL_ERROR: 'おっせかいエンジンを実行できませんでした。',
  };
  const message = messages[code];
  if (!message) {
    return new OsekkaiHttpError(
      'PYTHON_INVALID_RESPONSE',
      'おっせかいエンジンの応答形式が正しくありません。',
      502,
      requestId,
    );
  }
  return new OsekkaiHttpError(code, message, statusForCliError(code), requestId);
}

export function asOsekkaiHttpError(error: unknown, fallbackRequestId: string): OsekkaiHttpError {
  if (error instanceof OsekkaiHttpError) {
    return error;
  }

  // Do not leak filesystem paths, subprocess output, or stack traces.
  return new OsekkaiHttpError(
    'INTERNAL_ERROR',
    '処理を完了できませんでした。時間をおいてもう一度お試しください。',
    500,
    fallbackRequestId,
  );
}
