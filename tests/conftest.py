import hashlib
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
DUMMY_URL = "https://example.com/fixture"


def _load(filename: str) -> tuple[bytes, str, str]:
    data = (FIXTURES / filename).read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    url = DUMMY_URL + "/" + filename
    return data, url, md5


@pytest.fixture(scope="session")
def inflancka_fixture():
    return _load("inflancka.pdf")


@pytest.fixture(scope="session")
def foka_fixture():
    return _load("foka.pdf")


@pytest.fixture(scope="session")
def potocka_fixture():
    return _load("potocka.pdf")


@pytest.fixture(scope="session")
def delfin_fixture():
    return _load("delfin.xlsx")
