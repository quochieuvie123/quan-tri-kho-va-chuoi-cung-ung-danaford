"""Read-only template syntax audit after resolving the integration merge."""
from pathlib import Path
from django.apps import apps
from django.template.loader import get_template

roots = [Path('templates')] + [Path(app.path) / 'templates' for app in apps.get_app_configs()]
errors = []
count = 0
for root in roots:
    if not root.exists():
        continue
    for path in root.rglob('*.html'):
        count += 1
        try:
            get_template(path.relative_to(root).as_posix())
        except Exception as error:
            errors.append((str(path), str(error)))
print(f'Checked {count} templates; errors: {len(errors)}')
for path, error in errors:
    print(path, error)
if errors:
    raise RuntimeError('Template compilation failed')
