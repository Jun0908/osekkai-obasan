import type { OsekkaiCommand } from './osekkai-commands';

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };

export type OsekkaiDataMode = 'demo' | 'live';

export type OsekkaiCliRequest = {
  schemaVersion: '1.0';
  requestId: string;
  command: OsekkaiCommand;
  userId: string;
  idempotencyKey: string | null;
  payload: JsonObject;
};

export type OsekkaiCliSuccess<T> = {
  ok: true;
  requestId: string;
  data: T;
};

export type OsekkaiCliFailure = {
  ok: false;
  requestId: string;
  error: {
    code: string;
    message: string;
  };
};

export type OsekkaiCliResponse<T> = OsekkaiCliSuccess<T> | OsekkaiCliFailure;

export type OsekkaiApiSuccess<T> = {
  data: T;
  requestId: string;
};

export type OsekkaiApiFailure = {
  error: {
    code: string;
    message: string;
  };
  requestId: string;
};

export type OsekkaiCommandResult<T> = {
  data: T;
  requestId: string;
};

export type OsekkaiSessionView = {
  csrfToken: string;
  dataMode: OsekkaiDataMode;
  expiresAt: string;
};
