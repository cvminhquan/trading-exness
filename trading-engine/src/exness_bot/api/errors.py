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
    "LIVE_ACCOUNT_NOT_CONFIGURED": (
        "Chưa cấu hình tài khoản thật. Thêm MT5_LIVE_LOGIN, "
        "MT5_LIVE_PASSWORD và MT5_LIVE_SERVER vào .env."
    ),
    "DEMO_ACCOUNT_NOT_CONFIGURED": "Chưa cấu hình tài khoản demo.",
    "ACCOUNT_SWITCH_FAILED": "Không thể chuyển tài khoản MT5.",
    "ANALYST_CHAT_RATE_LIMITED": "Bạn gửi quá nhanh. Vui lòng thử lại sau.",
    "ANALYST_CHAT_MESSAGE_TOO_LONG": "Tin nhắn quá dài.",
    "ANALYST_CHAT_MESSAGE_REQUIRED": "Tin nhắn không được để trống.",
    "CLOSE_DISABLED": "Đóng vị thế từ dashboard đang tắt.",
    "CLOSE_CONFIRM_REQUIRED": "Cần nhập đúng cụm xác nhận để đóng vị thế.",
    "LIVE_CLOSE_BLOCKED": "Không được đóng vị thế trên tài khoản thật với cấu hình hiện tại.",
    "POSITION_NOT_FOUND": "Không tìm thấy vị thế.",
}
