"""Database demo tách riêng, không đọc/ghi db.sqlite3 của nhóm."""
import tempfile
from pathlib import Path
from .settings import *  # noqa: F403

III_IV_DEMO = True
DEMO_DIR = Path(tempfile.gettempdir()) / 'danaford_iii_iv_demo'
DEMO_DIR.mkdir(parents=True, exist_ok=True)
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': DEMO_DIR / 'demo.sqlite3'}}
