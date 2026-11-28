#!/usr/bin/env python3
"""Medo full-stack smoke: signup -> verify -> login -> catalog -> medicine ->
schedule -> dose mark, plus Caddy public-route-table assertions.

Usage:
  python scripts/smoke.py [BASE_URL] [--psql "CMD"]

  BASE_URL   default https://api.simmaps.com (dev: http://localhost:8080)
  --psql     shell command that runs psql inside the stack's postgres
             container, e.g. --psql "docker exec medo-postgres-1 psql -U postgres -d identity_db"
             Used to flip email_verified (verification email is not receivable in smoke).
             Without it, login is still attempted and the script reports the 403.

Exit 0 = all checks pass.
"""
import argparse
import base64
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "medo-smoke/1.0", "Content-Type": "application/json"}


def req(method, url, body=None, token=None, cookie=None):
    headers = dict(UA)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cookie:
        headers["Cookie"] = cookie
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}, dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {}, dict(e.headers)
        except json.JSONDecodeError:
            return e.code, {"_raw": raw[:200].decode("utf-8", "replace")}, dict(e.headers)


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name} {detail}")
    return cond


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="https://api.simmaps.com")
    ap.add_argument("--psql", default="")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    ok = True

    # --- Caddy public-route table assertions ---
    st, _, _ = req("GET", f"{base}/health")
    ok &= check("GET /health public", st == 200, f"({st})")
    for path in ["/v1/doses/due", "/v1/care/check-link", "/v1/users/00000000-0000-0000-0000-000000000000",
                 "/metrics", "/ready", "/.well-known/jwks.json", "/v1/patients/00000000-0000-0000-0000-000000000000/has-dose-records"]:
        st, _, _ = req("GET", f"{base}{path}")
        ok &= check(f"GET {path} -> 404", st == 404, f"({st})")

    # --- signup ---
    ts = int(datetime.now(timezone.utc).timestamp())
    email = f"smoke-{ts}@medo.test"
    password = f"Smoke-{ts}-Passw0rd!"
    st, body, _ = req("POST", f"{base}/v1/auth/signup",
                      {"name": "Smoke Test", "email": email, "password": password, "role": "Patient"})
    ok &= check("POST /v1/auth/signup", st == 201, f"({st} {body})")
    if st != 201:
        return 1
    patient_id = body["userId"]

    # --- verify email via DB (no mailbox in smoke) ---
    if args.psql:
        sql = f"UPDATE users SET email_verified=true WHERE email='{email}';"
        r = subprocess.run(args.psql.split() + ["-c", sql], capture_output=True, text=True)
        ok &= check("email_verified flip", r.returncode == 0, r.stderr.strip()[:120])
    else:
        print("[INFO] no --psql: skipping email verify; login expected to 403")

    # --- login ---
    st, body, headers = req("POST", f"{base}/v1/auth/login", {"email": email, "password": password})
    if st == 200:
        token = body["accessToken"]
        ok &= check("POST /v1/auth/login", True, f"({st})")
    else:
        ok &= check("POST /v1/auth/login", False, f"({st} {body}) — pass --psql to verify email")
        return 1

    # --- catalog entry ---
    st, body, _ = req("POST", f"{base}/v1/medicine-catalog",
                      {"brandName": f"SmokeTab-{ts}", "ingredientNames": ["smoke-inet"],
                       "form": "tablet", "packagingQuantity": 10}, token=token)
    ok &= check("POST /v1/medicine-catalog", st in (200, 201), f"({st} {body})")
    catalog_id = body.get("id") or body.get("catalogEntryId") or (body.get("entry") or {}).get("id")
    if not catalog_id:
        print("[FAIL] no catalog id in response")
        return 1

    # --- catalog photo: adopt requires >=1 confirmed photo ---
    # issue presigned PUT -> upload bytes to R2 -> confirm key
    st, body, _ = req("POST", f"{base}/v1/medicine-catalog/{catalog_id}/photos",
                      {"slot": "A"}, token=token)
    ok &= check("POST catalog photo issue", st == 200, f"({st} {body})")
    photo_key, upload_url = body.get("photoKey"), body.get("uploadUrl")
    if not (photo_key and upload_url):
        print("[FAIL] no photoKey/uploadUrl in response")
        return 1
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    up = urllib.request.Request(upload_url, data=png, method="PUT",
                                headers={"Content-Type": "image/png"})
    try:
        with urllib.request.urlopen(up, timeout=15) as resp:
            up_st = resp.status
    except urllib.error.HTTPError as e:
        up_st = e.code
    ok &= check("PUT presigned photo -> R2", up_st in (200, 201), f"({up_st})")
    st, body, _ = req("PUT", f"{base}/v1/medicine-catalog/{catalog_id}/photos/A",
                      {"photoKey": photo_key}, token=token)
    photo_ok = check("PUT catalog photo confirm", st == 200, f"({st} {body})")
    ok &= photo_ok
    if not photo_ok:
        return 1

    # --- adopt medicine ---
    st, body, _ = req("POST", f"{base}/v1/medicines",
                      {"patientId": patient_id, "catalogEntryId": catalog_id,
                       "prescribingDoctor": "Dr Smoke", "dosage": "1 tablet",
                       "dosesRemaining": 30, "price": 1.5, "pharmacyName": "SmokePharmacy"},
                      token=token)
    ok &= check("POST /v1/medicines", st in (200, 201), f"({st} {body})")
    medicine_id = body.get("id") or body.get("medicineId")
    if not medicine_id:
        print("[FAIL] no medicine id in response")
        return 1

    # --- schedule (date-list, dose time 10 min ago UTC -> inside on-time window) ---
    anchor = datetime.now(timezone.utc) - timedelta(minutes=10)
    dose_time = anchor.strftime("%H:%M")
    today = anchor.strftime("%Y-%m-%d")
    st, body, _ = req("POST", f"{base}/v1/patients/{patient_id}/schedules",
                      {"medicineId": medicine_id,
                       "recurrence": {"kind": "date-list", "dates": [today]},
                       "doseTimes": [dose_time], "timezone": "UTC"}, token=token)
    ok &= check("POST /v1/patients/{id}/schedules", st in (200, 201), f"({st} {body})")

    # --- find the dose and mark it (from/to are ISO datetimes) ---
    day = anchor.date()
    frm = f"{day}T00:00:00Z"
    to = f"{day + timedelta(days=1)}T00:00:00Z"
    from urllib.parse import quote
    st, body, _ = req("GET",
                      f"{base}/v1/patients/{patient_id}/doses?from={quote(frm)}&to={quote(to)}",
                      token=token)
    doses = body.get("doses") or body.get("items") or []
    dose_id = doses[0]["id"] if doses else None
    ok &= check("GET doses window", st == 200 and dose_id is not None, f"({st}, doses={len(doses)})")
    if dose_id:
        st, body, _ = req("POST", f"{base}/v1/doses/{dose_id}/outcome",
                          {"outcome": "taken-on-time"}, token=token)
        ok &= check("POST /v1/doses/{id}/outcome", st in (200, 204), f"({st} {body})")

    print("SMOKE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
