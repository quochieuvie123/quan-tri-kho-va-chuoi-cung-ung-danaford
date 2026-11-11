"""Run focused tests with schema_editor on SQLite :memory:; never opens project SQLite or runs migrations."""
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.conf import settings
settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
import django
django.setup()
from django.apps import apps
from django.db import connection
from django.test.utils import setup_test_environment
setup_test_environment()
assert connection.settings_dict['NAME'] == ':memory:'
with connection.schema_editor() as editor:
    for model in apps.get_models():
        editor.create_model(model)
names = sys.argv[1:] or ['contracts.tests', 'warehouse.test_receipt_ui', 'warehouse.test_integration', 'warehouse.tests']
suite = unittest.defaultTestLoader.loadTestsFromNames(names)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
