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
  | "INVALID_CREDENTIALS"
  | "ACCOUNT_PENDING"
  | "ACCOUNT_SUSPENDED"
  | "ACCOUNT_REJECTED"
  | "INSUFFICIENT_PERMISSION"
  | "CASE_ACCESS_DENIED"
  | "DUPLICATE_USERNAME"
  | "DUPLICATE_EMAIL"
  /* Evidence intelligence + integrity (phase 2). */
  | "AI_DISABLED"
  | "ARTIFACT_KIND_UNSUPPORTED"
  | "ARTIFACT_NOT_FOUND"
  | "ARTIFACT_NOT_REVIEWABLE"
  | "CUSTODY_AUDIT_ACTIVE"
  | "CUSTODY_FIELD_REQUIRED"
  | "EMPTY_EVIDENCE"
  | "EVIDENCE_NOT_FOUND"
  | "EVIDENCE_UNAVAILABLE"
  | "EXTRACTION_ACTIVE"
  | "EXTRACTION_FAILED"
  | "EXTRACTION_PARSE_FAILED"
  | "INTEGRITY_MISMATCH"
  | "INTEGRITY_SOURCE_MISSING"
  | "INVALID_FILTER"
  | "INVALID_PAYLOAD"
  | "JOB_NOT_FOUND"
  | "JOB_TERMINAL"
  | "UNSUPPORTED_FORMAT"
  /* Case intelligence (phase 3). */
  | "RESOLUTION_ACTIVE"
  | "RECONSTRUCTION_ACTIVE"
  | "CONTRADICTION_ACTIVE"
  | "CANDIDATE_ENTITY_UNAVAILABLE"
  | "PROPOSAL_NOT_APPROVED"
  | "TIMELINE_TIMESTAMP_MISSING"
  | "CONTRADICTION_STATE_INVALID"
  | "REVIEW_NOTE_REQUIRED"
  /* Financial flow (phase 4, feature A). */
  | "FLOW_ACTIVE"
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