COPY (
select p."First Name", p."Last Name", p."NPI Number", p."Birth Date", p."Email Address", p."Alternate Email", p."Practice Division", p."Degree",
  rg.schools as "Residency Training Program", rg.graduation_dates as "Residency Graduation Date",
  lg.state_licenses as "State Licenses", lg.state_license_numbers as "State License Numbers", lg.state_license_expiration_dates as "State License Expiry Dates",
  dg.dea_states as "DEA Certificate States", dg.state_dea_numbers as "DEA Certificate Numbers", dg.state_dea_expiration_dates as "DEA Certificate Expiry Dates",
  coalesce(bg.specialty, 'Radiology') as "Specialty", sg.services as "Subspecialty scope of practice"
from (select p.full_name, trim(p.first_name) as "First Name", trim(p.last_name) as "Last Name", trim(p.npi_number) as "NPI Number",
                          p.birth_date as "Birth Date", coalesce(p.email_address, p.alternate_email) as "Email Address",
                          case when p.email_address is not null and p.alternate_email is not null and p.alternate_email != p.email_address then p.alternate_email else null end as "Alternate Email",
                          replace(trim(replace(p.rp_team, '\r\n', '')), 'Matrix;RP Houston','RP Houston') as "Practice Division", trim(replace(p.degree, ', PhD', '')) as "Degree"
      from _tmp_src_providers p
      where p.full_name is not null
      GROUP BY 1,2,3,4,5,6,7,8, 9
     ) p
  left outer join (
                    -- State Licenses
                    select l.full_name, string_agg(l.license_number, ',') as state_license_numbers, string_agg(l.state_license, ',') as state_licenses, string_agg(l.state_license_expiration_date, ',') as state_license_expiration_dates
                    from (
                           select p.full_name, p.state_license, p.license_type, p.license_number, p.state_license_expiration_date
                           from _tmp_src_providers p
                           WHERE p.full_name is not NULL and lower(trim(p.lic__status)) in ('active', 'active physician', 'clear/active', 'license is current (active)')
                           GROUP BY 1,2,3,4,5
                         ) l
                    GROUP BY 1
                  ) lg ON (p.full_name=lg.full_name)
  left outer join (
                    -- Residency Training programs
                    select l.full_name, string_agg(l.education_type, ',') as education_types, string_agg(l.school, ',') as schools, string_agg(to_char(l.graduation_date, 'MM/DD/YYYY'), ',') as graduation_dates
                    from (
                           select p.full_name, p.education_type, pnm.orbit_program_names as school, to_date(p.graduation_date, 'MM/DD/YYYY') as graduation_date
                           from _tmp_src_providers p left outer join _tmp_rp_program_names pnm on (trim(p.school)=trim(pnm.rp_program_names))
                           WHERE p.full_name is not NULL and p.education_type='Residency'
                           GROUP BY 1,2,3,4
                           ORDER BY 4 desc
                         ) l
                    GROUP BY 1
                  ) rg ON (p.full_name=rg.full_name)
  left outer join (
                    -- DEA Certificates
                    select l.full_name, string_agg(l.state_type, ',') as dea_state_types, string_agg(l.state_dea_certificates, ',') as dea_states, string_agg(l.dea_number, ',') as state_dea_numbers, string_agg(l.state_dea_expiration_date, ',') as state_dea_expiration_dates
                    from (
                           select p.full_name, p.state_dea_certificates, p.dea_number, p.state_dea_expiration_date , p.state_type
                           from _tmp_src_providers p
                           WHERE p.full_name is not NULL and p.state_type = '1' and trim(p.state_dea_certificates) not in ('')
                           GROUP BY 1,2,3,4,5
                           ORDER BY 1 asc, (case when p.state_dea_expiration_date != '' then to_date(p.state_dea_expiration_date, 'MM/DD/YYYY') else null end) desc
                         ) l
                    GROUP BY 1
                  ) dg ON (p.full_name=dg.full_name)
  left outer join (
                    -- Boards
                    select l.full_name, string_agg(l.specialty, ',') as specialty
                    from (
                           select p.full_name,
                             case trim(p.board_name)
                             when trim('American Board of Radiology') then 'Radiology'
                             when trim('ABR') then 'Radiology'
                             when trim('American Board of Nuclear Medicine') then 'Nuclear Medicine'
                             when trim('ABNM') then 'Nuclear Medicine'
                             when trim('American Board of Family Medicine') then 'Family Medicine'
                             when trim('American Board of Internal Medicine') then 'Internal Medicine'
                             when trim('ABIM') then 'Internal Medicine'
                             when trim('American Osteopathic Board of Radiology') then 'Osteopathic Radiology'
                             when 'Certification Board of Nuclear Cadrdiology' then 'Nuclear Cardiology'
                             else p.board_name
                             end as specialty
                           from _tmp_src_providers p
                           WHERE p.full_name is not NULL and p.board_name != ''
                           GROUP BY 1,2
                         ) l
                    GROUP BY 1
                  ) bg ON (p.full_name=bg.full_name)
  left outer join (
                    -- Subspecialties
                    select g.full_name, string_agg(g.service, ',') as services
                    from (
                           SELECT
                             p.full_name,
                             NULLIF(snm.orbit_service, '') as service
                           FROM _tmp_src_providers p left outer join _tmp_rp_service_names snm on (trim(p.service)=trim(snm.rp_service))
                           WHERE p.full_name IS NOT NULL
                           GROUP BY 1, 2
                         ) g
                    GROUP BY 1
                  ) sg ON (p.full_name=sg.full_name)
WHERE p.full_name != 'Full Name'
order by p.full_name
) TO STDOUT WITH CSV HEADER DELIMITER ';'