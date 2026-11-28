#!/usr/bin/env python3
"""Generate medo-infra env files deterministically from AppHub/.secrets + service .env passthrough.

Usage: python scripts/gen-env.py --env dev|prod
Outputs (gitignored):
  .env                        shared compose vars (DB passwords; image tags managed by release.sh)
  secrets/<env>/<svc>.env     per-service env_file for compose

Secrets precedence: existing per-service .env passthrough keys first (R2_*, RESEND_API_KEY,
INVITE_TOKEN_SECRET, EMAIL_FROM, VAPID_SUBJECT, PUSH_ENDPOINT_ALLOWLIST,
CHECK_LINK_CACHE_TTL_MS, MATERIALIZATION_HORIZON_DAYS), then .secrets JSONs,
then D:\\medo\\.env.
"""
import argparse
import json
import os
import sys
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1]
APPHUB = INFRA.parent
SECRETS_DIR = APPHUB / ".secrets"
MEDO_ENV = Path(r"D:\medo\.env")

SERVICES = [
    ("identity", 3001, "identity_db", "identity_PASSWORD"),
    ("care", 3002, "care_db", "care_PASSWORD"),
    ("medicine", 3003, "medicine_db", "medicine_PASSWORD"),
    ("schedule-dose", 3004, "schedule_dose_db", "schedule_dose_PASSWORD"),
    ("notification", 3005, "notification_db", "notification_PASSWORD"),
    ("gamification", 3006, "gamification_db", "gamification_PASSWORD"),
]
SVC_KEY = {name: f"medo-{name}" for name, *_ in SERVICES}
DB_ROLE = {name: name.replace("-", "_") for name, *_ in SERVICES}

# internal container URLs (compose network)
SVC_URL = {name: f"http://{name}:{port}" for name, port, *_ in SERVICES}
JWKS_URL = f"{SVC_URL['identity']}/.well-known/jwks.json"

PUBLIC_URLS = {
    "prod": {
        "APP_BASE_URL": "https://app.simmaps.com",
        "INVITE_LINK_BASE": "https://app.simmaps.com/invite/",
        "NODE_ENV": "production",
    },
    "dev": {
        "APP_BASE_URL": "http://localhost:3000",
        "INVITE_LINK_BASE": "http://localhost:3000/invite/",
        "NODE_ENV": "development",
    },
}

# keys carried over verbatim from an existing service .env when present
PASSTHROUGH = {
    "identity": [],
    "care": ["INVITE_TOKEN_SECRET"],
    "medicine": [
        "R2_ENDPOINT",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
        "R2_PUBLIC_BASE_URL",
    ],
    "schedule-dose": ["CHECK_LINK_CACHE_TTL_MS", "MATERIALIZATION_HORIZON_DAYS"],
    "notification": [
        "RESEND_API_KEY",
        "EMAIL_FROM",
        "VAPID_SUBJECT",
        "PUSH_ENDPOINT_ALLOWLIST",
        "DIRECTORY_CACHE_TTL_MS",
    ],
    "gamification": [],
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_env_file(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"')
    return out


def load_dmedo_env() -> dict:
    return parse_env_file(MEDO_ENV)


def compact(obj) -> str:
    return json.dumps(obj, separators=(",", ":"))


def service_public_keys(keys: dict) -> str:
    return compact({name: [svc["pub"]] for name, svc in keys["services"].items()})


def build_service_env(name: str, port: int, db: str, pw_key: str,
                      env_kind: str, db_pw: dict, keys: dict,
                      passthrough: dict, dmedo: dict) -> dict:
    e = {
        "NODE_ENV": PUBLIC_URLS[env_kind]["NODE_ENV"],
        "PORT": str(port),
        "LOG_LEVEL": "info",
        "DATABASE_URL": f"postgres://{DB_ROLE[name]}:{db_pw[pw_key]}@postgres:5432/{db}",
        "BROKER_DATABASE_URL": f"postgres://broker:{db_pw['BROKER_PASSWORD']}@postgres:5432/broker_db",
        "SERVICE_PRIVATE_KEY": compact(keys["services"][SVC_KEY[name]]["priv"]),
        "SERVICE_PUBLIC_KEYS": service_public_keys(keys),
        "SENTRY_DSN": "",
    }
    for k in PASSTHROUGH[name]:
        if k in passthrough:
            e[k] = passthrough[k]
    # vapid for notification comes from keys file
    if name == "notification":
        e["VAPID_PUBLIC_KEY"] = keys["vapid"]["publicKey"]
        e["VAPID_PRIVATE_KEY"] = keys["vapid"]["privateKey"]
        e.setdefault("VAPID_SUBJECT", "mailto:notifications@notify.simmaps.com")
        e.setdefault("EMAIL_FROM", "Medo <notifications@notify.simmaps.com>")
        if "RESEND_API_KEY" not in e:
            e["RESEND_API_KEY"] = dmedo.get("RESEND_API_KEY", "")
    # identity user-JWT keys
    if name == "identity":
        e["JWT_PRIVATE_KEY"] = compact(keys["user"]["priv"])
        e["JWT_PUBLIC_KEYS"] = compact([keys["user"]["pub"]])
        e["APP_BASE_URL"] = PUBLIC_URLS[env_kind]["APP_BASE_URL"]
        e["CARE_SERVICE_URL"] = SVC_URL["care"]
    # per-service peer URLs
    peer_map = {
        "care": {"IDENTITY_SERVICE_URL": SVC_URL["identity"], "IDENTITY_JWKS_URL": JWKS_URL},
        "medicine": {
            "IDENTITY_JWKS_URL": JWKS_URL,
            "CARE_SERVICE_URL": SVC_URL["care"],
            "SCHEDULE_DOSE_SERVICE_URL": SVC_URL["schedule-dose"],
        },
        "schedule-dose": {
            "IDENTITY_JWKS_URL": JWKS_URL,
            "CARE_BASE_URL": SVC_URL["care"],
            "MEDICINE_BASE_URL": SVC_URL["medicine"],
        },
        "notification": {
            "IDENTITY_JWKS_URL": JWKS_URL,
            "CARE_BASE_URL": SVC_URL["care"],
            "MEDICINE_BASE_URL": SVC_URL["medicine"],
            "SCHEDULE_DOSE_BASE_URL": SVC_URL["schedule-dose"],
        },
        "gamification": {
            "IDENTITY_JWKS_URL": JWKS_URL,
            "CARE_BASE_URL": SVC_URL["care"],
            "SCHEDULE_DOSE_BASE_URL": SVC_URL["schedule-dose"],
        },
    }
    e.update(peer_map.get(name, {}))
    if name == "care":
        e["INVITE_LINK_BASE"] = PUBLIC_URLS[env_kind]["INVITE_LINK_BASE"]
    return e


def write_env(path: Path, env: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in env.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["dev", "prod"], required=True)
    args = ap.parse_args()

    db_pw = load_json(SECRETS_DIR / "db-passwords.json")
    keys = load_json(SECRETS_DIR / f"medo-{args.env}-keys.json")
    dmedo = load_dmedo_env()

    out = INFRA / "secrets" / args.env
    for name, port, db, pw_key in SERVICES:
        repo = APPHUB / f"medo-{name}"
        passthrough = parse_env_file(repo / ".env")
        env = build_service_env(name, port, db, pw_key, args.env,
                                db_pw, keys, passthrough, dmedo)
        write_env(out / f"{name}.env", env)

    # shared .env for compose interpolation (DB passwords + placeholders for tags)
    shared = {
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": db_pw["POSTGRES_PASSWORD"],
        "POSTGRES_DB": "postgres",
        "IDENTITY_DB_PASSWORD": db_pw["identity_PASSWORD"],
        "CARE_DB_PASSWORD": db_pw["care_PASSWORD"],
        "MEDICINE_DB_PASSWORD": db_pw["medicine_PASSWORD"],
        "SCHEDULE_DOSE_DB_PASSWORD": db_pw["schedule_dose_PASSWORD"],
        "NOTIFICATION_DB_PASSWORD": db_pw["notification_PASSWORD"],
        "GAMIFICATION_DB_PASSWORD": db_pw["gamification_PASSWORD"],
        "BROKER_DB_PASSWORD": db_pw["BROKER_PASSWORD"],
    }
    # preserve existing MEDO_TAG_* lines if .env already exists (release.sh owns them)
    existing = INFRA / ".env"
    old_tags = {}
    if existing.exists():
        for line in existing.read_text(encoding="utf-8").splitlines():
            if line.startswith("MEDO_TAG_"):
                k, _, v = line.partition("=")
                old_tags[k] = v
    lines = [f"{k}={v}" for k, v in shared.items()]
    for name, *_ in SERVICES:
        key = f"MEDO_TAG_{name.upper().replace('-', '_')}"
        lines.append(f"{key}={old_tags.get(key, 'latest')}")
    existing.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"generated secrets/{args.env}/*.env + .env ({args.env})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
