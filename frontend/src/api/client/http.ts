import { apiConfig } from "@/config/env";
import { ApiError, type ApiErrorCode, type ApiErrorBody } from "@/types/api";
import { authSession } from "./session";
import { generateRequestId } from "@/lib/requestId";

/** Normalize any thrown error into an ApiError we can render safely. */
function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof TypeError || error instanceof SyntaxError) {
    return new ApiError({
      status: 0,
      code: "UNKNOWN",
      message: "The investigation server is unreachable. Check the connection and retry.",
    });
  }
  return new ApiError({
    status: 0,
    code: "UNKNOWN",
    message: error instanceof Error ? error.message : "Unexpected failure",
  });
}

function codeForStatus(status: number): ApiErrorCode {
  const map: Record<number, ApiErrorCode> = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "BAD_REQUEST",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_ERROR",
    502: "INTERNAL_ERROR",
    503: "INTERNAL_ERROR",
  };
  return map[status] ?? "UNKNOWN";
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  formData?: FormData;
  signal?: AbortSignal;
}

async function parseErrorBody(response: Response, requestId: string): Promise<ApiError> {
  let body: ApiErrorBody | null = null;
  try {
    const json = (await response.json()) as ApiErrorBody;
    if (json?.error?.message && json?.error?.code) body = json;
  } catch {
    /* empty/invalid body */
  }
  const status = response.status;
  const code = body?.error?.code ?? codeForStatus(status);
  const message = body?.error?.message ?? defaultMessage(code, status);
  return new ApiError({ status, code, message, requestId });
}

function defaultMessage(code: ApiErrorCode, status: number): string {
  const messages: Record<string, string> = {
    UNAUTHORIZED: "Your session has expired. Please sign in again.",
    FORBIDDEN: "You do not have access to this case.",
    NOT_FOUND: "The requested investigation was not found.",
    TOO_MANY_REQUESTS: "Too many requests. Please wait before trying again.",
    VALIDATION_ERROR: "The request could not be validated.",
    CONFLICT: "This item already exists.",
    INTERNAL_ERROR: "Unable to load the investigation. Please try again.",
    UNKNOWN: "Unable to reach the investigation server.",
  };
  return messages[code] ?? `Request failed (HTTP ${status}).`;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, formData, headers } = options;
  const token = authSession.getToken();
  const requestId = generateRequestId();

  const url = `${apiConfig.apiUrl}/api/v1${path}`;
  const headersOut = new Headers(headers);
  headersOut.set("X-Request-Id", requestId);
  if (token && !headersOut.has("Authorization")) {
    headersOut.set("Authorization", `Bearer ${token}`);
  }
  if (formData) {
    headersOut.delete("Content-Type");
  } else if (body !== undefined) {
    headersOut.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers: headersOut,
      body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
    });
  } catch (error) {
    throw toApiError(error);
  }

  const echoed = response.headers.get("x-request-id");

  if (response.status === 401 && token) {
    authSession.clear();
    authSession.fireUnauthorized();
    throw await parseErrorBody(response, appliedId(echoed, requestId));
  }

  if (!response.ok) {
    throw await parseErrorBody(response, appliedId(echoed, requestId));
  }

  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      return (await response.json()) as T;
    } catch (error) {
      throw toApiError(error);
    }
  }
  return (await response.text()) as unknown as T;
}

function appliedId(echoed: string | null, requestId: string): string {
  return echoed || requestId;
}