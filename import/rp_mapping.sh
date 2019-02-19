#!/usr/bin/env bash

set -e
export $(grep -v '^#' .env | xargs)

echo "Using Postgres host $PGHOST"

# fail fast if sooething wrong with db credentials
psql -h $PGHOST -d $PGDATABASE -U $PGUSER -c "SELECT 'OK' as \"Access\";"

psql -h $PGHOST -d $PGDATABASE -U $PGUSER -c "DROP TABLE IF EXISTS _tmp_rp_program_names;" > /dev/null
./pgfutter --ignore-errors --host $PGHOST --db $PGDATABASE --user $PGUSER --pw $PGPASSWORD --schema public  --table _tmp_rp_program_names csv -d $';' rp-program-names.csv

psql -h $PGHOST -d $PGDATABASE -U $PGUSER -c "DROP TABLE IF EXISTS _tmp_rp_service_names;" > /dev/null
./pgfutter --ignore-errors --host $PGHOST --db $PGDATABASE --user $PGUSER --pw $PGPASSWORD --schema public  --table _tmp_rp_service_names csv -d $';' rp-service-names.csv
