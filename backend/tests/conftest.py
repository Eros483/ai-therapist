"""Test bootstrap.

Required settings fields (no defaults) must exist for `app.config.settings`
to import during test collection. Dummy values are set here; individual tests
override via monkeypatch or construct Settings() with explicit kwargs.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("MAIN_MODEL", "test/main-model")
os.environ.setdefault("EXTRACTION_MODEL", "test/extraction-model")
os.environ.setdefault("SAFETY_MODEL", "test/safety-model")
