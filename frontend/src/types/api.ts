/**
 * API error envelope (matches backend app/schemas/error.py).
 * { "error": { "code": "NOT_FOUND", "message": "..." } }
 */

export type ApiErrorCode =
  | "BAD_REQUEST"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "METHOD_NOT_ALLOWED"
  | "CONFLICT"
  | "VALIDATION_ERROR"
  | "TOO_MANY_REQUESTS"
  | "INTERNAL_ERROR"
  | "UNKNOWN";

export interface ApiErrorBody {
  error: {
    code: ApiErrorCode;
    message: string;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  readonly requestId?: string;
  readonly retryable: boolean;

  constructor(options: {
    status: number;
    code: ApiErrorCode;
    message: string;
    requestId?: string;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.requestId = options.requestId;
    this.retryable =
      options.status === 429 ||
      options.status >= 500 ||
      options.code === "UNKNOWN";
  }

  get userMessage(): string {
    return this.message.trim();
  }
}