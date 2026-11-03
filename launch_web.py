"""Compatibility launcher for previous desktop shortcuts."""
from pathlib import Path
import os
import subprocess
import sys
import threading
import urllib.request
import webbrowser

root = Path(__file__).resolve().parent
remote = os.environ.get('MAGACIN_WEB_URL')
if remote:
    if not remote.startswith('https://'):
        raise SystemExit('Internet adresa aplikacije mora koristiti HTTPS.')
    webbrowser.open(remote)
    raise SystemExit(0)
url = 'http://127.0.0.1:8501'
try:
    with urllib.request.urlopen(url + '/_stcore/health', timeout=2) as response:
        available = response.status == 200
except (OSError, TimeoutError):
    available = False
if available:
    webbrowser.open(url)
    raise SystemExit(0)
python = root / '.venv' / 'Scripts' / 'python.exe' if os.name == 'nt' else root / '.venv' / 'bin' / 'python'
if not python.exists():
    raise SystemExit('Prvo instalirajte serversko okruženje prema README.md ili otvorite zajedničku HTTPS adresu.')
pg_ctl = root / '.local' / 'pgsql' / 'bin' / 'pg_ctl.exe'
if pg_ctl.exists():
    data = str(root / '.local' / 'pgdata')
    if subprocess.run([str(pg_ctl), '-D', data, 'status'], capture_output=True).returncode:
        subprocess.run([str(pg_ctl), '-D', data, '-l', str(root / '.local' / 'postgres.log'),
                        '-o', '-h 127.0.0.1 -p 55432', 'start'], check=True)
threading.Timer(2, lambda: webbrowser.open(url)).start()
raise SystemExit(subprocess.call([str(python), '-m', 'streamlit', 'run', str(root / 'streamlit_app.py'),
                                 '--server.address=127.0.0.1', '--server.port=8501'], cwd=root))

