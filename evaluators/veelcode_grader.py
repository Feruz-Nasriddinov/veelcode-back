import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

APP_NOT_READY_EXIT_CODE = 90


def _app_is_up(url):
    request = urllib.request.Request(url, headers={'Host': 'localhost'})
    try:
        urllib.request.urlopen(request, timeout=2)
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False
    return True


def pytest_sessionstart(session):
    url = os.environ.get('APP_URL')
    if not url:
        return
    deadline = time.monotonic() + float(os.environ.get('APP_READY_TIMEOUT', '60'))
    while time.monotonic() < deadline:
        if _app_is_up(url):
            return
        time.sleep(0.5)
    pytest.exit('App did not start', returncode=APP_NOT_READY_EXIT_CODE)


@pytest.fixture
def app_url():
    return os.environ['APP_URL']


@pytest.fixture
def client(app_url):
    import requests

    class Client(requests.Session):
        def request(self, method, url, *args, **kwargs):
            if url.startswith('/'):
                url = app_url + url
            kwargs.setdefault('timeout', 10)
            return super().request(method, url, *args, **kwargs)

    with Client() as session:
        session.headers['Host'] = 'localhost'
        yield session


@pytest.fixture
def submission_dir():
    return Path(os.environ['SUBMISSION_DIR'])
