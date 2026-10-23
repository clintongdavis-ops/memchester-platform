"""Create a consistent SQLite backup without stopping the app."""
import os
from pathlib import Path
import sqlite3
import sys

source = Path(os.environ.get('MEMCHESTER_DATA', str(Path(__file__).parent / 'data'))) / 'finance.sqlite3'
if len(sys.argv) != 2:
    raise SystemExit('Usage: python backup.py /private/path/backup.sqlite3')
target = Path(sys.argv[1])
if not source.is_file():
    raise SystemExit('No finance database found. Start the app first.')
fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
os.close(fd)
try:
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
except Exception:
    target.unlink(missing_ok=True)
    raise
print('Backup complete. Store it securely; it contains financial records and account hashes.')
