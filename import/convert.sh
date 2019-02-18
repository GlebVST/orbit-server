#!/usr/bin/env bash

set -e
export $(grep -v '^#' .env | xargs)

echo "Using Postgres host $PGHOST"

#cleanup
rm -f ./src-providers.csv
rm -rf ./sheets

# fail fast if sooething wrong with db credentials
psql -h $PGHOST -d $PGDATABASE -U $PGUSER -c "SELECT 'OK' as \"Access\";"

echo "Converting Excel file"
# export all sheets from the excel file
xlsx2csv -a -i -d ';' -e src-providers.xlsx sheets

#combine all sheets into one csv file
cat ./sheets/*.csv > ./src-providers.csv

echo "Importing temp table"
# load csv file with structure into postgresql table
psql -h $PGHOST -d $PGDATABASE -U $PGUSER -c "DROP TABLE IF EXISTS _tmp_src_providers;" > /dev/null
./pgfutter --ignore-errors --host $PGHOST --db $PGDATABASE --user $PGUSER --pw $PGPASSWORD --schema public  --table _tmp_src_providers csv -d $';' src-providers.csv

echo "Exporting aggregated data"
# export data in decided structure specified by sql
rm -f out-providers.csv
#echo "Doing data cleanup"
psql -h $PGHOST -d $PGDATABASE -U $PGUSER -F $';' --no-align -f rp_clean.sql
psql -h $PGHOST -d $PGDATABASE -U $PGUSER -F $';' --no-align -f rp_convert.sql > out-providers.csv