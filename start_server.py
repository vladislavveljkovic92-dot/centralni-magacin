"""Single-server entrypoint; database failure prevents startup."""
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
subprocess.run([sys.executable, str(root / 'manage.py'), 'migrate'], check=True, cwd=root)
subprocess.run([sys.executable, str(root / 'manage.py'), 'bootstrap'], check=True, cwd=root)
os.execv(sys.executable, [sys.executable, '-m', 'streamlit', 'run', str(root / 'streamlit_app.py'),
    '--server.address=0.0.0.0', '--server.port=' + os.getenv('PORT', '8501')])

