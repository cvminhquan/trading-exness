"""Tiny privacy helpers — leaf module, no broker/demo imports."""

from __future__ import annotations


def mask_login(login: int | None) -> str | None:
    if login is None:
        return None
    text = str(int(login))
    if len(text) <= 4:
        return "****"
    return f"***{text[-4:]}"
