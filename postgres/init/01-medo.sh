#!/bin/sh
# Medo Postgres init — runs once on first boot of an empty data dir.
# Creates per-service roles + logical DBs + broker_db. Passwords arrive via
# container env (see compose *.env interpolation), never committed.
set -e

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres <<-SQL
	CREATE ROLE identity LOGIN PASSWORD '${IDENTITY_DB_PASSWORD}';
	CREATE ROLE care LOGIN PASSWORD '${CARE_DB_PASSWORD}';
	CREATE ROLE medicine LOGIN PASSWORD '${MEDICINE_DB_PASSWORD}';
	CREATE ROLE schedule_dose LOGIN PASSWORD '${SCHEDULE_DOSE_DB_PASSWORD}';
	CREATE ROLE notification LOGIN PASSWORD '${NOTIFICATION_DB_PASSWORD}';
	CREATE ROLE gamification LOGIN PASSWORD '${GAMIFICATION_DB_PASSWORD}';
	CREATE ROLE broker LOGIN PASSWORD '${BROKER_DB_PASSWORD}';
SQL

for pair in \
	"identity identity_db" \
	"care care_db" \
	"medicine medicine_db" \
	"schedule_dose schedule_dose_db" \
	"notification notification_db" \
	"gamification gamification_db" \
	"broker broker_db"; do
	set -- $pair
	psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
		-c "CREATE DATABASE $2 OWNER $1;"
done

echo "medo init: 7 databases + 7 roles created"
