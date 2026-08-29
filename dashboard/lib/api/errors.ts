import { apiErrorEnvelopeSchema } from "@/domain/api/envelope";

export type ApiErrorDetails = Record<string, unknown> | unknown[] | string | null;

export type ApiErrorBody = {
  code: string;
  message: string;
  details?: ApiErrorDetails;
};

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: ApiErrorDetails;

  constructor(params: {
    code: string;
    message: string;
    status: number;
    details?: ApiErrorDetails;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.code = params.code;
    this.status = params.status;
    this.details = params.details;
  }
}

const HTTP_FALLBACK_MESSAGES: Record<number, ApiErrorBody> = {
  400: { code: "BAD_REQUEST", message: "Yêu cầu không hợp lệ." },
  401: { code: "UNAUTHORIZED", message: "Không có quyền truy cập." },
  403: { code: "FORBIDDEN", message: "Bạn không có quyền thực hiện thao tác này." },
  404: { code: "NOT_FOUND", message: "Không tìm thấy tài nguyên yêu cầu." },
  409: { code: "CONFLICT", message: "Dữ liệu xung đột với trạng thái hiện tại." },
  429: { code: "RATE_LIMITED", message: "Quá nhiều yêu cầu. Vui lòng thử lại sau." },
  500: { code: "INTERNAL_ERROR", message: "Lỗi máy chủ nội bộ." },
  503: { code: "SERVICE_UNAVAILABLE", message: "Dịch vụ tạm thời không khả dụng." },
};

export const KNOWN_API_ERROR_CODES: Record<string, string> = {
  BOT_NOT_CONNECTED: "Bot hiện chưa kết nối.",
  VALIDATION_FAILED: "Dữ liệu phản hồi không hợp lệ.",
  NETWORK_ERROR: "Không thể kết nối tới API.",
  TIMEOUT: "Yêu cầu API quá thời gian chờ.",
  PARSE_ERROR: "Không thể đọc phản hồi từ API.",
  LIVE_ACCOUNT_NOT_CONFIGURED:
    "Chưa cấu hình tài khoản thật. Thêm MT5_LIVE_LOGIN, MT5_LIVE_PASSWORD và MT5_LIVE_SERVER vào .env của trading-engine.",
  DEMO_ACCOUNT_NOT_CONFIGURED: "Chưa cấu hình tài khoản demo.",
  ACCOUNT_SWITCH_FAILED: "Không thể chuyển tài khoản MT5.",
};

export const resolveApiErrorMessage = (code: string, fallback: string): string =>
  KNOWN_API_ERROR_CODES[code] ?? fallback;

export const normalizeHttpError = (status: number, body?: unknown): ApiError => {
  const fallback = HTTP_FALLBACK_MESSAGES[status] ?? {
    code: "HTTP_ERROR",
    message: `Đã xảy ra lỗi HTTP ${status}.`,
  };

  const parsedEnvelope = apiErrorEnvelopeSchema.safeParse(body);
  if (parsedEnvelope.success) {
    const err = parsedEnvelope.data.error;
    return new ApiError({
      code: err.code,
      message: resolveApiErrorMessage(err.code, err.message),
      status,
      details: err.details as ApiErrorDetails | undefined,
    });
  }

  if (body && typeof body === "object" && "error" in body) {
    const err = (body as { error?: ApiErrorBody }).error;
    if (err && typeof err.code === "string" && typeof err.message === "string") {
      return new ApiError({
        code: err.code,
        message: resolveApiErrorMessage(err.code, err.message),
        status,
        details: err.details as ApiErrorDetails | undefined,
      });
    }
  }

  return new ApiError({
    code: fallback.code,
    message: fallback.message,
    status,
  });
};

export const createValidationError = (details?: ApiErrorDetails): ApiError =>
  new ApiError({
    code: "VALIDATION_FAILED",
    message: KNOWN_API_ERROR_CODES.VALIDATION_FAILED,
    status: 502,
    details,
  });

export const createNetworkError = (cause?: unknown): ApiError =>
  new ApiError({
    code: "NETWORK_ERROR",
    message: KNOWN_API_ERROR_CODES.NETWORK_ERROR,
    status: 0,
    details: cause instanceof Error ? cause.message : undefined,
  });

export const createTimeoutError = (): ApiError =>
  new ApiError({
    code: "TIMEOUT",
    message: KNOWN_API_ERROR_CODES.TIMEOUT,
    status: 408,
  });
