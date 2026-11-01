# Airport reference data

`airports.csv` is a reduced snapshot of [OurAirports](https://ourairports.com/data/),
retrieved on 2026-11-01 from its [CSV download](https://davidmegginson.github.io/ourairports-data/airports.csv).

## Terms of use

OurAirports releases its data into the public domain. Attribution is appreciated
but not required. The data comes with no guarantee of accuracy or fitness for use.
See the [source terms](https://ourairports.com/data/#terms-of-use).

## Contents

The snapshot contains 9,052 records with an IATA code matching three uppercase
ASCII letters. It retains these original source columns:

- `id`: stable OurAirports record ID.
- `iata_code`: three-letter IATA code.
- `name`: airport name.
- `municipality`: municipality served, when provided.
- `iso_country`: two-character country code used by OurAirports.

Rows are sorted by IATA code, then numeric source ID. Other columns are omitted;
field values are unchanged. Closed facilities and facilities without scheduled
service are retained when they have an IATA code, to support past flight entries.
This snapshot is not a complete historical record of code assignments.

To refresh it, download the source CSV, apply the same filtering and column
selection, and save as UTF-8 CSV with LF line endings. Check source IDs and IATA
codes for duplicates, and update the retrieval date and record count here.

The `flask --app app init-db` command imports this snapshot into SQLite.
Initialization preserves existing user accounts and flight entries.
