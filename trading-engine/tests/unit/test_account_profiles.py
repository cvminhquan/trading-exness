"""Tests for demo/live account profile resolution and persistence."""

from pathlib import Path

from exness_bot.config.account_profiles import AccountProfile, AccountProfileStore
from exness_bot.config.settings import Settings


class TestAccountCredentials:
    def test_demo_falls_back_to_mt5_login(self) -> None:
        settings = Settings(
            MT5_LOGIN=463864158,
            MT5_PASSWORD="demo-pass",
            MT5_SERVER="Exness-MT5Trial17",
        )
        creds = settings.demo_credentials()
        assert creds.configured is True
        assert creds.login == 463864158
        assert creds.server == "Exness-MT5Trial17"
        assert settings.has_live_credentials is False

    def test_live_requires_dedicated_fields(self) -> None:
        settings = Settings(
            MT5_LOGIN=111,
            MT5_PASSWORD="demo-pass",
            MT5_SERVER="Exness-MT5Trial",
            MT5_LIVE_LOGIN=222,
            MT5_LIVE_PASSWORD="live-pass",
            MT5_LIVE_SERVER="Exness-MT5Real",
        )
        live = settings.live_credentials()
        assert live.configured is True
        assert live.login == 222
        assert settings.credentials_for(AccountProfile.LIVE).login == 222
        assert settings.credentials_for(AccountProfile.DEMO).login == 111

    def test_invalid_active_account_coerced_to_demo(self) -> None:
        settings = Settings(MT5_ACTIVE_ACCOUNT="paper")
        assert settings.mt5_active_account == AccountProfile.DEMO


class TestAccountProfileStore:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / ".mt5_active_account"
        store = AccountProfileStore(path)
        assert store.load() == AccountProfile.DEMO
        store.save(AccountProfile.LIVE)
        assert path.read_text(encoding="utf-8").strip() == "live"
        assert AccountProfileStore(path).load() == AccountProfile.LIVE
        assert "password" not in path.read_text(encoding="utf-8").lower()

    def test_invalid_file_falls_back(self, tmp_path: Path) -> None:
        path = tmp_path / ".mt5_active_account"
        path.write_text("nope\n", encoding="utf-8")
        store = AccountProfileStore(path)
        assert store.load() == AccountProfile.DEMO
