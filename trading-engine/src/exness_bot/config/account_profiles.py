"""Demo / live MT5 account profiles for read-only viewing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class AccountProfile(StrEnum):
    """Which MT5 login the read-only API should use."""

    DEMO = "demo"
    LIVE = "live"


PROFILE_LABELS: dict[AccountProfile, str] = {
    AccountProfile.DEMO: "Tài khoản demo",
    AccountProfile.LIVE: "Tài khoản thật",
}


@dataclass(frozen=True)
class Mt5AccountCredentials:
    """Resolved MT5 login details — never persist password to disk."""

    login: int | None
    password: str
    server: str

    @property
    def configured(self) -> bool:
        return self.login is not None and bool(self.password) and bool(self.server)


class AccountProfileStore:
    """Persist the active profile id only (no secrets)."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        default: AccountProfile = AccountProfile.DEMO,
    ) -> None:
        self._path = path
        self._memory = default
        self._default = default

    def load(self) -> AccountProfile:
        raw = self._memory.value
        if self._path is not None and self._path.exists():
            raw = self._path.read_text(encoding="utf-8").strip().lower()
        try:
            return AccountProfile(raw)
        except ValueError:
            return self._default

    def save(self, profile: AccountProfile) -> None:
        self._memory = profile
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(f"{profile.value}\n", encoding="utf-8")
