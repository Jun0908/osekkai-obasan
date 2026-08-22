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
      return 404;
    case 'CONFLICT':
    case 'INVALID_STATE_TRANSITION':
    case 'FEEDBACK_ALREADY_RECORDED':
    case 'IDEMPOTENCY_CONFLICT':
      return 409;
    case 'VALIDATION_ERROR':
    case 'INVALID_REQUEST':
      return 400;
    case 'DEMO_MODE_DISABLED':
      return 404;
    case 'PROVIDER_ERROR':
      return 502;
    case 'STORAGE_ERROR':
    case 'LOCK_TIMEOUT':
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
