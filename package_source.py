"""Build an allowlisted deployment bundle; no credentials, databases, or backups."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent
files = [
    'README.md', 'requirements.txt', 'requirements-dev.txt', 'requirements.lock.txt',
    '.env.example', '.gitignore', '.dockerignore', 'Dockerfile', 'compose.yaml',
    'render.yaml', 'alembic.ini', '.streamlit/config.toml', 'streamlit_app.py',
    'manage.py', 'start_server.py', 'launch_web.py', 'backup_database.py',
    'pokreni_pregled.ps1', 'Magacin.py', 'Magacin_Aplikacija_requirements.txt',
    'legacy/Magacin_Aplikacija_magacin_app.py.txt', 'package_source.py',
]
for directory in ('magacin_backend', 'migrations', 'tests'):
    files.extend(str(p.relative_to(root)).replace('\\', '/') for p in (root / directory).rglob('*.py'))
destination = root / 'dist' / 'magacin-central-source.zip'
destination.parent.mkdir(exist_ok=True)
with ZipFile(destination, 'w', ZIP_DEFLATED) as bundle:
    for name in sorted(set(files)):
        bundle.write(root / name, name)
print('Deployment source bundle:', destination)

