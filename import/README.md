## Providers Excel to CSV
   
   Utility to load non-normalized providers Excel file into database, aggregate on data and produce a result csv file where
   each provider has a single row and all aggregate fields are joined into single string.
   
   * Uses xlsx2csv to convert from Excel to CSV
   * Uses pgfutter to load csv into database creating table (strucutre corresponds to csv header) if necessary
   * Users Postgres database to hold a temp table and do aggregates.
   
   **NOTE**: Excel/CSV file header should not contain any commas or other symbols (had issue with = as well).  Replace 
   column header like: `State Type - 1=DEA, 2=CDS` -> `State Type`
   
## Usage
Needs xlsx2csv installed: https://github.com/dilshod/xlsx2csv

Needs pgfutter executable file to be placed into this folder: https://github.com/lukasmartinelli/pgfutter/releases/tag/v1.1
 
1. Setup DB access in your local `.env` file in the same folder:
 
```
PGHOST=
PGDATABASE=
PGUSER=
PGPASSWORD=
```

2. Put input providers file as `src-providers.xlsx` in this folder
3. Run `./convert.sh` which should produce `out-providers.csv` on success