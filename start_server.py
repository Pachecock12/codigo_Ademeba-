import os
import subprocess
import sys

port = os.environ.get('PORT', '8000')
sys.exit(subprocess.call([
    'gunicorn', 'ademeba_web.wsgi',
    '--bind', f'0.0.0.0:{port}',
    '--workers', '4',
    '--timeout', '120'
]))
