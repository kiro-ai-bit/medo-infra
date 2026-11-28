#!/usr/bin/env python3
"""Seed the Kiroween showcase dataset against a running Medo stack.

Creates two demo accounts (patient + caregiver), four catalog medicines with
realistic photos, adopted patient medicines, daily/weekly schedules, a linked
care relationship, a rich 7-day dose-outcome history (via SQL — the API only
marks live windows), and one on-time demo dose marked through the real API.

Idempotent: re-running skips/reuses existing rows (409-tolerant, dedup by
lookup, INSERT ... ON CONFLICT DO NOTHING for dose history).

Prereqs:
  - Stack reachable at BASE (default https://api.simmaps.com).
  - --psql CMD: shell prefix that runs psql inside postgres, e.g.
      local dev:  docker exec -i medo-postgres-1 psql -U postgres
      prod EC2:   ssh -i D:/medo/AppHub/.secrets/medo-prod-key.pem ubuntu@52.63.127.50 docker exec -i medo-postgres-1 psql -U postgres
    (space-free; the script appends -tA -d <db> -c <sql>)
  - scripts/seed-assets/*.png present (run gen-seed-assets.py once).

Usage:
  python scripts/seed-showcase.py [BASE] --psql "CMD" [--assets DIR] [--history-days N]
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, time as dtime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

UA = {"User-Agent": "medo-seed/1.0", "Content-Type": "application/json"}
TZ_NAME = "Asia/Karachi"
PKT = ZoneInfo(TZ_NAME)

PATIENT = {"name": "Ayesha Khan", "email": "demo.patient@simmaps.com",
           "password": "MedoDemo!2026", "role": "Patient"}
CAREGIVER = {"name": "Bilal Ahmed", "email": "demo.caregiver@simmaps.com",
             "password": "MedoDemo!2026", "role": "Caregiver"}

MEDS = [
    # slug, brand, ingredients, form, packQty, pharmacy, doctor, dosage,
    # dosesRemaining, refillThreshold, price, doseTimes, recurrence
    ("panadol-extra", "Panadol Extra", ["paracetamol", "caffeine"], "tablet", 24,
     "Sehat Pharmacy", "Dr. Sana Iqbal", "1 tablet", 18, 6, 2.5,
     ["08:00", "20:00"], {"kind": "rrule", "rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR,SA,SU"}),
    ("augmentin-625", "Augmentin 625", ["amoxicillin", "clavulanic acid"], "tablet", 20,
     "Aga Khan Pharmacy", "Dr. Imran Sheikh", "1 tablet", 9, 5, 4.0,
     ["08:00", "14:00", "20:00"], {"kind": "rrule", "rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR,SA,SU"}),
    ("vitamin-d3", "Vitamin D3 200,000 IU", ["cholecalciferol"], "capsule", 4,
     "Sehat Pharmacy", "Dr. Sana Iqbal", "1 capsule weekly", 1, 1, 3.5,
     ["09:00"], {"kind": "rrule", "rrule": "FREQ=WEEKLY;BYDAY=SU"}),
    ("cetirizine-10", "Cetirizine 10mg", ["cetirizine hydrochloride"], "tablet", 30,
     "Aga Khan Pharmacy", "Dr. Nadia Raza", "1 tablet at night", 22, 7, 1.0,
     ["22:00"], {"kind": "rrule", "rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR,SA,SU"}),
]

SLOTS = ["A", "B", "C"]


def req(method, url, body=None, token=None):
    headers = dict(UA)
    data = json.dumps(body).encode() if body is not None else None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {"_raw": raw[:200].decode("utf-8", "replace")}
        except json.JSONDecodeError:
            return e.code, {"_raw": raw[:200].decode("utf-8", "replace")}


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    return bool(cond)


def info(name, detail=""):
    print(f"[INFO] {name} {detail}")


def psql(psql_cmd, db, sql, tuples=False):
    args = psql_cmd.split()
    if tuples:
        args += ["-tA"]
    args += ["-d", db, "-c", sql]
    r = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"psql failed: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def ensure_account(base, psql_cmd, spec):
    """Signup (tolerate 409) -> verify via psql -> login. Returns (userId, token)."""
    st, body = req("POST", f"{base}/v1/auth/signup",
                   {"name": spec["name"], "email": spec["email"],
                    "password": spec["password"], "role": spec["role"]})
    if st == 201:
        info(f"signup {spec['email']}", f"({body.get('userId')})")
    elif st in (400, 409):
        info(f"signup {spec['email']} exists, reusing")
    else:
        check(f"signup {spec['email']}", False, f"({st} {body})")
        return None, None
    psql(psql_cmd, "identity_db",
         f"UPDATE users SET email_verified=true WHERE email='{spec['email']}';")
    st, body = req("POST", f"{base}/v1/auth/login",
                   {"email": spec["email"], "password": spec["password"]})
    if st != 200:
        check(f"login {spec['email']}", False, f"({st} {body})")
        return None, None
    return body["userId"], body["accessToken"]


def upload_photos(base, token, catalog_id, slug, assets):
    global _last_key
    ok = True
    for slot in SLOTS:
        path = os.path.join(assets, f"{slug}-{slot}.png")
        if not os.path.exists(path):
            info(f"skip photo {slug}-{slot} (missing {path})")
            continue
        st, body = req("POST", f"{base}/v1/medicine-catalog/{catalog_id}/photos",
                       {"slot": slot}, token=token)
        if st != 200 or not body.get("uploadUrl"):
            ok &= check(f"photo issue {slug}-{slot}", False, f"({st} {body})")
            continue
        key = body["photoKey"]
        with open(path, "rb") as f:
            png = f.read()
        up = urllib.request.Request(body["uploadUrl"], data=png, method="PUT",
                                    headers={"Content-Type": "image/png"})
        try:
            with urllib.request.urlopen(up, timeout=20) as resp:
                up_st = resp.status
        except urllib.error.HTTPError as e:
            up_st = e.code
        ok &= check(f"photo PUT {slug}-{slot}", up_st in (200, 201), f"({up_st})")
        if up_st not in (200, 201):
            continue
        st, body = req("PUT", f"{base}/v1/medicine-catalog/{catalog_id}/photos/{slot}",
                       {"photoKey": key}, token=token)
        ok &= check(f"photo confirm {slug}-{slot}", st == 200, f"({st} {body})")
    return ok


def ensure_catalog(base, token, spec, assets):
    slug, brand, ings, form, pack = spec[:5]
    st, body = req("GET", f"{base}/v1/medicine-catalog?q={quote(brand)}", token=token)
    entries = body.get("entries", []) if st == 200 else []
    for e in entries:
        if e.get("brandName") == brand:
            info(f"catalog '{brand}' exists ({e['id']})")
            cid = e["id"]
            photos = e.get("photos") or {}
            have = sum(1 for s in SLOTS if (photos.get(s) or {}).get("url"))
            if have < len(SLOTS):
                upload_photos(base, token, cid, slug, assets)
            return cid
    st, body = req("POST", f"{base}/v1/medicine-catalog",
                   {"brandName": brand, "ingredientNames": ings, "form": form,
                    "packagingQuantity": pack}, token=token)
    if st not in (200, 201):
        check(f"catalog '{brand}'", False, f"({st} {body})")
        return None
    cid = body["id"]
    info(f"catalog '{brand}' created ({cid})")
    upload_photos(base, token, cid, slug, assets)
    return cid


def ensure_medicine(base, token, patient_id, spec, catalog_id):
    (slug, brand, ings, form, pack, pharmacy, doctor, dosage,
     doses_rem, refill, price, dose_times, recurrence) = spec
    st, body = req("GET", f"{base}/v1/medicines?patientId={patient_id}", token=token)
    meds = body.get("medicines", []) if st == 200 else []
    for m in meds:
        if m.get("catalogEntryId") == catalog_id and m.get("status") != "archived":
            info(f"medicine '{brand}' exists ({m['id']})")
            return m["id"]
    st, body = req("POST", f"{base}/v1/medicines",
                   {"patientId": patient_id, "catalogEntryId": catalog_id,
                    "prescribingDoctor": doctor, "dosage": dosage,
                    "dosesRemaining": doses_rem, "refillThreshold": refill,
                    "price": price, "pharmacyName": pharmacy}, token=token)
    if st not in (200, 201):
        check(f"medicine '{brand}'", False, f"({st} {body})")
        return None
    info(f"medicine '{brand}' adopted ({body['id']})")
    return body["id"]


def ensure_schedule(base, token, patient_id, medicine_id, spec, start_date):
    (slug, brand, ings, form, pack, pharmacy, doctor, dosage,
     doses_rem, refill, price, dose_times, recurrence) = spec
    st, body = req("GET", f"{base}/v1/patients/{patient_id}/schedules", token=token)
    schedules = body.get("schedules", []) if st == 200 else []
    for s in schedules:
        if s.get("medicineId") == medicine_id:
            info(f"schedule for '{brand}' exists ({s['id']})")
            return s["id"], s
    payload = {"medicineId": medicine_id, "recurrence": recurrence,
               "doseTimes": dose_times, "timezone": TZ_NAME,
               "startDate": start_date.isoformat()}
    st, body = req("POST", f"{base}/v1/patients/{patient_id}/schedules",
                   payload, token=token)
    if st not in (200, 201):
        check(f"schedule '{brand}'", False, f"({st} {body})")
        return None, None
    info(f"schedule for '{brand}' created ({body['id']})")
    return body["id"], body


def pkt_now():
    return datetime.now(PKT)


def sched_utc(local_date: date, hhmm: str) -> datetime:
    h, m = int(hhmm[:2]), int(hhmm[3:])
    return datetime.combine(local_date, dtime(h, m), tzinfo=PKT).astimezone(timezone.utc)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


WEEKDAY_ABBR = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def occurs_on(recurrence, local: date, start: date) -> bool:
    """Approximate the service's recurrence expansion for history seeding.
    Supports the kinds used here: date-list + FREQ=WEEKLY[;BYDAY=..]."""
    if recurrence["kind"] == "date-list":
        return local.isoformat() in recurrence["dates"]
    rrule = recurrence.get("rrule", "")
    parts = dict(p.split("=", 1) for p in rrule.split(";") if "=" in p)
    freq = parts.get("FREQ", "")
    if freq == "WEEKLY":
        byday = parts.get("BYDAY")
        if byday:
            return WEEKDAY_ABBR[local.weekday()] in byday.split(",")
        return local.weekday() == start.weekday()
    # MONTHLY/YEARLY unused by the seed set — include the date rather than drop
    return True


def build_history(psql_cmd, patient_id, caregiver_id, items, history_days):
    """items: list of dicts {schedule_id, medicine_id, dose_times, recurrence}."""
    today_pkt = pkt_now().date()
    tuples = []
    for it in items:
        sid, mid = it["schedule_id"], it["medicine_id"]
        times = it["dose_times"]
        for d in range(1, history_days + 1):
            local = today_pkt - timedelta(days=d)
            if not occurs_on(it["recurrence"], local, it.get("start_date", today_pkt)):
                continue
            for slot, tt in enumerate(times):
                outcome, mark_min, actor, skipped = "taken-on-time", 12 + slot * 7, patient_id, False
                # deterministic variety keyed on (days_ago, slot)
                if d == 3 and slot == 0:
                    outcome, mark_min = "taken-late", 95
                if d == 5 and slot == len(times) - 1:
                    outcome, mark_min, skipped = "skipped", 20, True
                if d == 2 and slot == 0 and it.get("caregiver_mark"):
                    actor = caregiver_id
                if d == 4 and slot == len(times) - 1:
                    outcome, mark_min, actor = "missed", None, None
                sat = sched_utc(local, tt)
                if mark_min is None:
                    # missed: locked next local midnight + a few minutes
                    nxt = datetime.combine(local + timedelta(days=1), dtime(0, 8), tzinfo=PKT)
                    marked = nxt.astimezone(timezone.utc)
                else:
                    marked = sat + timedelta(minutes=mark_min)
                tuples.append(
                    f"('{sid}','{patient_id}','{mid}','{local.isoformat()}','{tt}',{slot},"
                    f"'{iso_z(sat)}','{outcome}',{'true' if skipped else 'false'},"
                    f"{('NULL' if actor is None else repr(actor))},'{iso_z(marked)}')"
                )
    return tuples


def insert_history(psql_cmd, tuples):
    if not tuples:
        return 0
    cols = ("schedule_id, patient_id, medicine_id, local_date, dose_time, dose_slot,"
            " scheduled_at, outcome, skipped_by_user, actor_id, marked_at")
    # chunk to keep each -c statement reasonable
    n = 0
    for i in range(0, len(tuples), 40):
        chunk = tuples[i:i + 40]
        sql = (f"INSERT INTO dose_occurrences ({cols}) VALUES {','.join(chunk)} "
               f"ON CONFLICT (schedule_id, local_date, dose_slot) DO NOTHING;")
        psql(psql_cmd, "schedule_dose_db", sql)
        n += len(chunk)
    return n


def mark_today_doses(base, token, patient_id, demo_dose_time_pkt):
    """Mark today's already-due doses via the real API (window-respecting),
    then the demo dose once it enters its on-time window."""
    now_pkt = pkt_now()
    day = now_pkt.date()
    frm = datetime.combine(day, dtime(0, 0), tzinfo=PKT).astimezone(timezone.utc)
    to = frm + timedelta(days=1)
    st, body = req("GET",
                   f"{base}/v1/patients/{patient_id}/doses"
                   f"?from={quote(iso_z(frm))}&to={quote(iso_z(to))}", token=token)
    if st != 200:
        check("GET today doses", False, f"({st} {body})")
        return
    doses = body.get("doses", [])
    info(f"today doses materialized: {len(doses)}")
    now_utc = datetime.now(timezone.utc)
    marked = 0
    for d in sorted(doses, key=lambda x: x["scheduledAt"]):
        if d.get("outcome") != "unmarked":
            continue
        sat = datetime.fromisoformat(d["scheduledAt"].replace("Z", "+00:00"))
        if sat > now_utc:
            continue  # upcoming — leave for the live demo
        for outcome in ("taken-on-time", "taken-late", "skipped"):
            st, body = req("POST", f"{base}/v1/doses/{d['id']}/outcome",
                           {"outcome": outcome}, token=token)
            if st == 200:
                marked += 1
                info(f"marked {d['doseTime']} -> {outcome}")
                break
    # demo dose: created ~3min ahead; wait for its on-time window then mark
    if demo_dose_time_pkt:
        target = datetime.combine(day, demo_dose_time_pkt, tzinfo=PKT).astimezone(timezone.utc)
        info(f"waiting for demo dose window at {target.isoformat()}")
        while datetime.now(timezone.utc) < target + timedelta(seconds=20):
            time.sleep(10)
        st, body = req("GET",
                       f"{base}/v1/patients/{patient_id}/doses"
                       f"?from={quote(iso_z(frm))}&to={quote(iso_z(to))}", token=token)
        for d in body.get("doses", []):
            sat = datetime.fromisoformat(d["scheduledAt"].replace("Z", "+00:00"))
            if abs((sat - target).total_seconds()) < 90 and d.get("outcome") == "unmarked":
                st, body = req("POST", f"{base}/v1/doses/{d['id']}/outcome",
                               {"outcome": "taken-on-time"}, token=token)
                check("demo dose taken-on-time", st == 200, f"({st} {body})")
                return
        check("demo dose found+marked", False, "(dose not found in window)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="https://api.simmaps.com")
    ap.add_argument("--psql", required=True)
    ap.add_argument("--assets", default=os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "seed-assets"))
    ap.add_argument("--history-days", type=int, default=7)
    ap.add_argument("--no-demo-wait", action="store_true",
                    help="skip the ~4min wait for the live demo dose")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    ok = True
    p_user, p_tok = ensure_account(base, args.psql, PATIENT)
    c_user, c_tok = ensure_account(base, args.psql, CAREGIVER)
    if not (p_user and p_tok and c_user and c_tok):
        return 1

    # care link (direct insert — invite tokens are hashed, unrecoverable)
    psql(args.psql, "care_db",
         f"INSERT INTO care_links (patient_id, caregiver_id, caregiver_email) "
         f"SELECT '{p_user}', '{c_user}', '{CAREGIVER['email']}' "
         f"WHERE NOT EXISTS (SELECT 1 FROM care_links WHERE patient_id='{p_user}' "
         f"AND caregiver_id='{c_user}' AND status='active');")
    info("care link ensured", f"{PATIENT['email']} <- {CAREGIVER['email']}")

    med_items = []
    sched_start = pkt_now().date() - timedelta(days=args.history_days)
    for spec in MEDS:
        cid = ensure_catalog(base, p_tok, spec, args.assets)
        if not cid:
            ok = False
            continue
        mid = ensure_medicine(base, p_tok, p_user, spec, cid)
        if not mid:
            ok = False
            continue
        sid, _ = ensure_schedule(base, p_tok, p_user, mid, spec, sched_start)
        if sid:
            med_items.append({"slug": spec[0], "schedule_id": sid, "medicine_id": mid,
                              "dose_times": spec[10], "recurrence": spec[11],
                              "start_date": sched_start,
                              "caregiver_mark": spec[0] == "augmentin-625"})

    # demo dose: one-off schedule ~3 min ahead on Panadol -> marked on-time live
    demo_time = None
    if med_items and not args.no_demo_wait:
        pan = next((m for m in med_items if m["slug"] == "panadol-extra"), None)
        if pan:
            now = pkt_now()
            today = now.date()
            st, body = req("GET", f"{base}/v1/patients/{p_user}/schedules", token=p_tok)
            existing = body.get("schedules", []) if st == 200 else []
            dup = any(s.get("medicineId") == pan["medicine_id"]
                      and (s.get("recurrence") or {}).get("kind") == "date-list"
                      for s in existing)
            if dup:
                info("demo dose schedule already exists — skipping")
                demo_time = None
            else:
                demo_time = (now + timedelta(minutes=4)).time().replace(second=0, microsecond=0)
                st, body = req("POST", f"{base}/v1/patients/{p_user}/schedules",
                               {"medicineId": pan["medicine_id"],
                                "recurrence": {"kind": "date-list",
                                               "dates": [today.isoformat()]},
                                "doseTimes": [demo_time.strftime("%H:%M")],
                                "timezone": TZ_NAME}, token=p_tok)
                if st in (200, 201):
                    info(f"demo dose schedule created at {demo_time.strftime('%H:%M')} PKT")
                else:
                    info(f"demo dose schedule failed ({st} {body}) — skipping live mark")
                    demo_time = None

    if med_items:
        tuples = build_history(args.psql, p_user, c_user, med_items, args.history_days)
        n = insert_history(args.psql, tuples)
        info(f"dose history rows attempted: {n} "
             f"(pre-existing skipped via ON CONFLICT)")

    mark_today_doses(base, p_tok, p_user, demo_time)

    print()
    print("SEED", "PASS" if ok else "FAIL")
    print(f"  patient    {PATIENT['email']} / {PATIENT['password']}")
    print(f"  caregiver  {CAREGIVER['email']} / {CAREGIVER['password']}")
    print(f"  timezone   {TZ_NAME}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
