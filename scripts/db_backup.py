"""Database backup / restore helper.
  SQLite:      python scripts/db_backup.py backup  backups/app-YYYYMMDD.db        (online, consistent: uses SQLite's backup API)
               python scripts/db_backup.py restore backups/app-YYYYMMDD.db        (STOP the API first; the current database is moved aside)
  PostgreSQL:  use the server's own tools, e.g.  pg_dump --format=custom --file=backup.dump "$DATABASE_URL_WITHOUT_DRIVER_SUFFIX"
               and  pg_restore --clean --if-exists --dbname=... backup.dump   (this script prints the exact commands and does not run them).
Backups contain clinical text and password hashes: encrypt them and restrict access."""
import os
import shutil
import sqlite3
import sys
import time

sys.path.insert(0, ".")
from src.db.session import database_url, is_sqlite, safe_url  # noqa: E402


def sqlite_path():
    return database_url().split("///", 1)[-1]


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("backup", "restore"):
        sys.exit(__doc__)
    cmd, target = sys.argv[1], sys.argv[2]
    if not is_sqlite():
        print("PostgreSQL database:", safe_url())
        print('  backup : pg_dump --format=custom --file="%s" "<connection string>"' % target)
        print('  restore: pg_restore --clean --if-exists --dbname="<connection string>" "%s"' % target)
        return
    src = sqlite_path()
    if cmd == "backup":
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        with sqlite3.connect(src) as a, sqlite3.connect(target) as b:
            a.backup(b)
        print("backup written:", target, os.path.getsize(target), "bytes")
    else:
        if not os.path.exists(target):
            sys.exit("backup file not found")
        if os.path.exists(src):
            moved = f"{src}.before-restore-{int(time.time())}"
            shutil.move(src, moved)
            for ext in ("-wal", "-shm"):
                if os.path.exists(src + ext):
                    os.remove(src + ext)
            print("previous database moved to", moved)
        shutil.copyfile(target, src)
        print("restored", target, "->", src)


main()
