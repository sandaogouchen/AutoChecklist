from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "tiktok_cookie_injector.command"


def test_cookie_injector_script_exists() -> None:
    assert SCRIPT_PATH.exists()


def test_cookie_injector_script_contains_required_cookies_and_flags() -> None:
    contents = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "--user-data-dir=" in contents
    assert "--load-extension=" in contents
    assert "sid_tt_ads" in contents
    assert "fd8fc3d9edff27b7fa5732e2a0ec10e4" in contents
    assert "ads.tiktok.com" in contents
    assert "chrome.cookies.set" in contents
    assert "https://ads.tiktok.com/i18n/manage/campaign?aadvid=1636212376671237" in contents
