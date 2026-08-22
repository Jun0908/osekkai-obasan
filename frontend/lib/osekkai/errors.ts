export class OsekkaiApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId?: string;

  constructor(code: string, message: string, status: number, requestId?: string) {
    super(message);
    this.name = "OsekkaiApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}
