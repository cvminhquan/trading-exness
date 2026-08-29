"""Normalized API errors with Vietnamese operator messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApiAppError(Exception):
    """Application error mapped to HTTP response envelope."""

    code: str
    message: str
    status_code: int
    details: Any | None = None


ERROR_MESSAGES: dict[str, str] = {
    "BROKER_DISCONNECTED": "Broker chưa kết nối. Dữ liệu live không khả dụng.",
    "BROKER_UNAVAILABLE": "Không thể kết nối với MT5.",
    "BOT_NOT_CONNECTED": "Bot hiện chưa kết nối.",
    "DATA_UNAVAILABLE": "Dữ liệu hiện không khả dụng.",
    "BACKTEST_NOT_FOUND": "Không tìm thấy báo cáo Backtest.",
    "INVALID_PARAMETER": "Tham số yêu cầu không hợp lệ.",
    "INTERNAL_ERROR": "Đã xảy ra lỗi nội bộ.",
}
