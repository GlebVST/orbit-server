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
rm out-providers.csv
psql -h $PGHOST -d $PGDATABASE -U $PGUSER -F $';' --no-align -c "COPY (select p.*,
  rg.schools as \"Residency Training Program\", rg.graduation_dates as \"Residency Graduation Date\",
  lg.state_licenses as \"State Licenses\", lg.state_license_expiration_dates as \"State License Expiry Dates\",
  dg.dea_states as \"DEA Certificate States\", dg.state_dea_expiration_dates as \"DEA Certificate Expiry Dates\",
  bg.boards as \"ABMS Active Board Certifications\", sg.services as \"Subspecialty scope of practice\"
from (select p.full_name, p.first_name as \"First Name\", p.last_name as \"Last Name\", p.npi_number as \"NPI Number\",
        p.birth_date as \"Birth Date\", coalesce(p.email_address, p.alternate_email) as \"Email Address\",
        p.rp_team as \"Practice Division\", p.degree as \"Degree\"
      from _tmp_src_providers p
      where p.full_name is not null
      GROUP BY 1,2,3,4,5,6,7,8
     ) p
  left outer join (
               -- State Licenses
               select l.full_name, string_agg(l.license_type, ',') as state_license_types, string_agg(l.state_license, ',') as state_licenses, string_agg(l.state_license_expiration_date, ',') as state_license_expiration_dates
               from (
                      select p.full_name, p.state_license, p.license_type, p.license_number, p.state_license_expiration_date
                      from _tmp_src_providers p
                      WHERE p.full_name is not NULL
                      GROUP BY 1,2,3,4,5
                    ) l
               GROUP BY 1
             ) lg ON (p.full_name=lg.full_name)
  left outer join (
               -- Residency Training programs
               select l.full_name, string_agg(l.education_type, ',') as education_types, string_agg(l.school, ',') as schools, string_agg(l.graduation_date, ',') as graduation_dates
               from (
                      select p.full_name, p.education_type, p.school, p.graduation_date
                      from _tmp_src_providers p
                      WHERE p.full_name is not NULL and p.education_type='Residency'
                      GROUP BY 1,2,3,4
                    ) l
               GROUP BY 1
             ) rg ON (p.full_name=rg.full_name)
  left outer join (
               -- DEA Certificates
               select l.full_name, string_agg(l.state_type, ',') as dea_state_types, string_agg(l.state_dea_certificates, ',') as dea_states, string_agg(l.dea_number, ',') as state_dea_numbers, string_agg(l.state_dea_expiration_date, ',') as state_dea_expiration_dates
               from (
                      select p.full_name, p.state_dea_certificates, p.dea_number, p.state_dea_expiration_date, p.state_type
                      from _tmp_src_providers p
                      WHERE p.full_name is not NULL and p.state_type = 'DEA'
                      GROUP BY 1,2,3,4,5
                    ) l
               GROUP BY 1
             ) dg ON (p.full_name=dg.full_name)
  left outer join (
               -- ABMS
               select l.full_name, string_agg(l.board_name, ',') as boards
               from (
                      select p.full_name, p.board_name
                      from _tmp_src_providers p
                      WHERE p.full_name is not NULL
                      GROUP BY 1,2
                    ) l
               GROUP BY 1
             ) bg ON (p.full_name=bg.full_name)
  left outer join (
               -- Subspecialties
               select g.full_name, string_agg(g.service, ',') as services from (
                                                                                 SELECT
                                                                                   p.full_name,
                                                                                   p.service
                                                                                 from _tmp_src_providers p
                                                                                 WHERE p.full_name IS NOT NULL
                                                                                 GROUP BY 1, 2
                                                                               ) g
               GROUP BY 1
             ) sg ON (p.full_name=sg.full_name)
order by p.full_name
) TO STDOUT WITH CSV HEADER DELIMITER ';' " > out-providers.csv