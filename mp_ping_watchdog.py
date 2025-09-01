#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, argparse, smtplib, socket
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from pathlib import Path

DEF_STATUS_PATH = "/opt/mp_ping/status.json"
# DEF_STATE_PATH = "/var/lib/mp_ping/watchdog_state.json"

def parse_args():
    ap = argparse.ArgumentParser(
        description="Watchdog per mp_ping: verifica freschezza di status.json e che non siano tutti DOWN."
    )
    ap.add_argument("--status", default=os.getenv("MP_STATUS_PATH", DEF_STATUS_PATH),
                    help=f"Percorso status.json (default: %(default)s)")
    ap.add_argument("--max-age-seconds", type=int, default=int(os.getenv("MP_MAX_AGE_SEC", "3600")),
                    help="Età massima consentita dello snapshot in secondi (default: 3600)")
    ap.add_argument("--suppress-minutes", type=int, default=int(os.getenv("MP_SUPPRESS_MIN", "120")),
                    help="Minuti di soppressione per evitare email duplicate (default: 120)")
#     ap.add_argument("--state-file", default=os.getenv("MP_STATE_FILE", DEF_STATE_PATH),
#                     help=f"Percorso file di stato per la soppressione (default: %(default)s)")
    ap.add_argument("--require-some-up", action="store_true",
                    default=os.getenv("MP_REQUIRE_SOME_UP", "1") not in ("0", "false", "False"),
                    help="Alza allarme se nessun host è UP (default: attivo)")
    return ap.parse_args()

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        raise RuntimeError(f"Errore lettura JSON {path}: {e}")

def parse_timestamp(ts):
    # Prova ISO 8601 varianti comuni
    if not ts:
        return None
    try:
        # Gestisce sia 'Z' sia offset
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return datetime.fromisoformat(ts)
    except Exception:
        # Fallback permissivo: prova senza microsecondi
        try:
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

def seconds_age(dt):
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        # Assume UTC se naive
        dt = dt.replace(tzinfo=timezone.utc)
    return int((now - dt).total_seconds())

def send_email_alert(subject, body):
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    mail_from = os.getenv("SMTP_FROM", "")
    mail_to = [x.strip() for x in os.getenv("SMTP_TO", "").split(",") if x.strip()]
    sender_name = os.environ.get('EMAIL_NAME', 'Multipedia Ping')

    if not all([smtp_host, mail_from, mail_to, smtp_user, smtp_pass]):
        raise RuntimeError("SMTP non configurato: servono SMTP_HOST, SMTP_FROM, SMTP_TO (e se necessario SMTP_USER/SMTP_PASS).")

    msg = MIMEMultipart()
    msg['From'] = f"{sender_name} <{mail_from}>"
    msg['To'] = ", ".join(mail_to)
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(mail_from, mail_to, msg.as_string())
        print(f'Email inviata a {mail_to}')
    except Exception as e:
        raise RuntimeError(f'Errore invio email: {e}')

# def ensure_parent(path: Path):
#     path.parent.mkdir(parents=True, exist_ok=True)

# def load_state(path: Path):
#     try:
#         with open(path, "r", encoding="utf-8") as f:
#             return json.load(f)
#     except Exception:
#         return {}

# def save_state(path: Path, data: dict):
#     ensure_parent(path)
#     tmp = path.with_suffix(".tmp")
#     with open(tmp, "w", encoding="utf-8") as f:
#         json.dump(data, f, ensure_ascii=False, indent=2)
#     os.replace(tmp, path)

def main():
    args = parse_args()
    status_path = Path(args.status)
    # state_path = Path(args.state_file)

    data = load_json(status_path)
    issues = []
    details = []

    if data is None:
        issues.append("status_missing")
        details.append(f"File assente: {status_path}")
    else:
        ts_raw = data.get("timestamp")
        dt = parse_timestamp(ts_raw)
        age = seconds_age(dt)
        last = data.get("last_status", {}) or {}
        host_count = len(last)
        up_count = sum(1 for v in last.values() if (isinstance(v, str) and v.upper() == "UP"))
        down_count = sum(1 for v in last.values() if (isinstance(v, str) and v.upper() == "DOWN"))

        details.append(f"timestamp: {ts_raw}")
        details.append(f"host_count: {host_count}, up: {up_count}, down: {down_count}")
        details.append(f"age_seconds: {age}")

        if age is None:
            issues.append("timestamp_unparsable")
        elif age > args.max_age_seconds:
            issues.append("stale_status")

        if args.require_some_up and up_count == 0 and host_count > 0:
            issues.append("all_down")

    # Soppressione email duplicate
    # state = load_state(state_path)
    # last_sig = state.get("last_signature")
    # last_sent = state.get("last_sent_epoch", 0)
    # now_epoch = int(datetime.now(timezone.utc).timestamp())

    signature = "|".join(sorted(issues)) if issues else "OK"

    # Report & invio
    subject_base = f"[mp_ping watchdog]"

    # if not issues:
    #     # Se rientra OK dopo errore, invia un RECOVERY (una sola volta)
    #     if last_sig and last_sig != "OK":
    #         body = "\n".join([
    #             f"Watchdog OK (recovery).",
    #             f"File: {status_path}",
    #             *details
    #         ])
    #         try:
    #             send_email_alert(subject=f"{subject_base} RECOVERY", body=body)
    #         except Exception as e:
    #             print(f"Errore invio email (recovery): {e}", file=sys.stderr)
    #             return 2
    #     # Aggiorna stato
    #     save_state(state_path, {"last_signature": "OK", "last_sent_epoch": now_epoch})
    #     print("Watchdog OK.")
    #     return 0

    # Ci sono problemi → valuta soppressione
    # suppress_sec = args.suppress_minutes * 60
    # should_suppress = (signature == last_sig) and (now_epoch - int(last_sent)) < suppress_sec

    body = "\n".join([
        f"Issues: {', '.join(issues)}",
        f"File: {status_path}",
        *details
    ])

    # if should_suppress:
    #     print(f"Problemi rilevati ma email soppressa (signature={signature}).")
    #     return 1

    if len(issues) > 0:
        try:
            send_email_alert(subject=f"{subject_base} ALERT: {','.join(issues)}", body=body)
        except Exception as e:
            print(f"Errore invio email: {e}", file=sys.stderr)
            return 2

        # save_state(state_path, {"last_signature": signature, "last_sent_epoch": now_epoch})
        print(f"Inviata email di ALERT (signature={signature}).")

    return 0

if __name__ == "__main__":
    sys.exit(main())
