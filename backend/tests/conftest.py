from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture()
def site():
    from tests.support import FakeSite

    return FakeSite()


@pytest.fixture()
def rt(tmp_path, site):
    from nzstats.config import load_settings
    from nzstats.runtime import build_runtime
    from tests.support import BASE

    settings = load_settings({"NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_BASE_URL": BASE})
    return build_runtime(settings, fetcher=site.fetcher())
