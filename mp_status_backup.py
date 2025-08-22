#!/usr/bin/env python3
"""
/usr/local/bin/mp_status_backup.py
Esegue snapshot atomico di status.json e rimuove backup più vecchi di RETENTION giorni.
Usare l'interprete del venv nel systemd ExecStart per avere portalocker disponibile.
Config possibile via /etc/default/mp_status_backup env vars:
  MP_STATUS_FILE (default /opt/mp_ping/status.json)
  MP_BACKUP_DIR (default /var/backups/mp_ping)
  MP_BACKUP_RETENTION_DAYS (default 30)
  MP_OWNER (default multipedia)
  MP_GROUP (default mp_users)
"""
import os
import json
import time
import tempfile
import shutil
import stat
from datetime import datetime, timezone, timedelta

# try to import portalocker; if not available, fall back to naive copy with warning
try:
    import portalocker
    HAVE_PORTALOCKER = True
except Exception:
    HAVE_PORTALOCKER = False

MP_STATUS_FILE = os.environ.get("MP_STATUS_FILE", "/opt/mp_ping/status.json")
MP_BACKUP_DIR = os.environ.get("MP_BACKUP_DIR", "/var/backups/mp_ping")
MP_BACKUP_RETENTION_DAYS = int(os.environ.get("MP_BACKUP_RETENTION_DAYS", "30"))
MP_OWNER = os.environ.get("MP_OWNER", "multipedia")
MP_GROUP = os.environ.get("MP_GROUP", "mp_users")
MODE = 0o640

def uid_gid(owner, group):
    import pwd, grp
    try:
        uid = pwd.getpwnam(owner).pw_uid
    except Exception:
        uid = None
    try:
        gid = grp.getgrnam(group).gr_gid
    except Exception:
        gid = None
    return uid, gid

def atomic_write(path, data):
    # data is a python object -> write JSON atomically
    dirn = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=dirn)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

def backup_and_prune():
    if not os.path.exists(MP_STATUS_FILE):
        print(f"Status file not found: {MP_STATUS_FILE}")
        return 1

    os.makedirs(MP_BACKUP_DIR, exist_ok=True)

    # read status with portalocker shared lock (if available)
    data = None
    if HAVE_PORTALOCKER:
        try:
            with open(MP_STATUS_FILE, "r", encoding="utf-8") as f:
                portalocker.lock(f, portalocker.LOCK_SH)
                try:
                    data = json.load(f)
                finally:
                    try:
                        portalocker.unlock(f)
                    except Exception:
                        pass
        except Exception as e:
            print(f"Errore leggendo {MP_STATUS_FILE} con portalocker: {e}")
            return 2
    else:
        # fallback senza lock: meno sicuro
        try:
            with open(MP_STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            print("Warning: portalocker non disponibile, snapshot senza lock (potrebbe essere inconsistente).")
        except Exception as e:
            print(f"Errore leggendo {MP_STATUS_FILE}: {e}")
            return 3

    # filename con timestamp (UTC) -- evita ":" per compatibilità
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    filename = f"status_{ts}.json"
    dest = os.path.join(MP_BACKUP_DIR, filename)

    try:
        atomic_write(dest, data)
    except Exception as e:
        print(f"Errore scrivendo snapshot {dest}: {e}")
        return 4

    # set ownership and mode if possible
    uid, gid = uid_gid(MP_OWNER, MP_GROUP)
    try:
        if uid is not None or gid is not None:
            os.chown(dest, uid if uid is not None else -1, gid if gid is not None else -1)
        os.chmod(dest, MODE)
    except Exception as e:
        print(f"Warning: non ho potuto impostare owner/perm per {dest}: {e}")

    # prune old files
    try:
        cutoff = time.time() - (MP_BACKUP_RETENTION_DAYS * 86400)
        removed = 0
        for fname in os.listdir(MP_BACKUP_DIR):
            if not fname.startswith("status_") or not fname.endswith(".json"):
                continue
            path = os.path.join(MP_BACKUP_DIR, fname)
            try:
                st = os.stat(path)
                if st.st_mtime < cutoff:
                    os.remove(path)
                    removed += 1
            except FileNotFoundError:
                pass
        print(f"Snapshot scritto: {dest}. Rimosse {removed} vecchie snapshot.")
    except Exception as e:
        print(f"Warning: errore durante prune: {e}")

    return 0

if __name__ == "__main__":
    rc = backup_and_prune()
    exit(rc)
