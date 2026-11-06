import pytest

import app as app_module


@pytest.fixture(autouse=True)
def process_keyless_jobs(monkeypatch):
    """Most tests exercise the worker path; sample-data (demo) tests turn this back on themselves."""
    monkeypatch.setattr(app_module, "DEMO_WITHOUT_KEY", False)
