# Flightbook

A social flight diary where passengers can log their flights, rate and review their experiences, and explore other travellers' journeys.

## Planned features

- Create an account and log in.
- Log flights with details such as airline, route, date, aircraft, and cabin class.
- Edit and delete your own flight entries.
- Optionally rate flights and write reviews.
- Classify flights by cabin class and journey purpose using options stored in the database.
- Browse and search your own and other users' flight entries by airport, airline, or flight number.
- Comment on your own and other users' flights.
- View traveller profiles showing their flight history, total flights, and number of airlines and airports visited.

## Technologies

Python, Flask, SQLite, SQL, HTML, Jinja, and CSS.

## Current status

Registration, login, and logout are available. Usernames preserve capitalization
but are unique and matched without regard to case. Accounts stay signed in until
logout or seven days of inactivity.

Signed-in users can add, edit, and delete their own public flight entries. Everyone
can browse recent entries and flight details. My flights shows personal history
by departure date; both lists show 20 entries per page.

Flights require a departure date (today or earlier) and three-letter departure
and arrival airport codes. Airline name, flight number, aircraft type, seat,
cabin class, and journey purpose are optional. Codes are normalized to uppercase;
flight numbers cannot contain internal spaces. Airport names come from a local
snapshot. Unknown three-letter airport codes can still be saved. Airport lookup accepts one to three letters of an airport code. Press Search airports, then
select a result; partial codes return prefix matches; a full code returns only that airport. Searching preserves unsaved flight details. Names also appear on saved
entries. No external service is contacted during normal use.

Ratings, reviews, search, comments, and profiles are not implemented yet.

Airport reference data is included in
[`data/airports.csv`](data/airports.csv). See [data sources and terms](data/README.md).

## Run locally

Install Python 3.12, then run these commands from the project directory:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Generate a private session key once (this refuses to overwrite an existing `.env`):

```sh
python -c "import secrets; open('.env', 'x').write('FLIGHTBOOK_SECRET_KEY=' + secrets.token_hex(32) + '\n')"
```

Load the key into your terminal, initialize the database, and start the app:

```sh
set -a
source .env
set +a
python -m flask --app app init-db
python -m flask --app app run --debug
```

Open http://127.0.0.1:5000 in your browser. Stop the server with Ctrl+C.
On Windows, create the environment with `py -3.12 -m venv .venv` and activate
it in PowerShell with `.venv\Scripts\Activate.ps1` instead. Replace the three
key-loading lines with:

```powershell
$env:FLIGHTBOOK_SECRET_KEY = (Get-Content .env) -replace '^FLIGHTBOOK_SECRET_KEY=', ''
```

If port 5000 is occupied, append `--port 5001` to the run command and open
http://127.0.0.1:5001 instead. The development server is for local use only.
The database is stored in `flightbook.db`. Initialization preserves existing
accounts and flight entries and imports the bundled airport snapshot and category
choices. After updating an existing checkout, run `python -m flask --app app init-db`
once before using the new flight pages. Both the database and `.env` are excluded
from Git.

Reuse the same key each time you start the app; load it again in each new terminal.
Requests fail with a configuration error if `FLIGHTBOOK_SECRET_KEY` is missing.
Replacing the key signs out existing sessions. For HTTPS hosting, also set
`FLIGHTBOOK_COOKIE_SECURE=1` so browsers only send the session cookie over HTTPS.

## Manual verification

- Add a past flight from `HEL` to `AMS` and confirm both airport names appear.
- Search airports by partial code, select a result, and check that other
  form fields are preserved.
- Try a future date, malformed airport code, and flight number containing spaces.
- Press Enter in a completed flight form and confirm it saves instead of searching airports.
- Edit the flight, then open the delete confirmation and cancel before testing deletion.
- Log out and confirm flights remain public but edit/delete controls disappear.
- Sign in as another user and confirm they cannot edit or delete the first user's flight.

- Create an account and confirm you are signed in with your chosen username spelling.
- Log out, then log in using a different capitalization of the same username.
- Try a duplicate username, mismatched passwords, and incorrect login credentials.
- Confirm errors preserve the username but never fill in password fields.
- Check the layout at narrow and wide browser widths, including text zoom.
- Use Tab to reveal the skip link, then Enter to move to the main content.
- Follow the Flightbook home link and confirm it returns to `/`.
- Visit a nonexistent URL and confirm the server returns HTTP 404.

## Development checks

With the virtual environment active, install and run the development tools:

```sh
python -m pip install -r requirements-dev.txt
python -m pip check
python -m pylint --rcfile=pyproject.toml *.py tests
python -m unittest discover -s tests -v
```

`requirements-dev.txt` includes the application dependencies and adds Pylint.
Tests use temporary databases and a test-only signing key. They cover homepage
rendering, account flows, validation, password storage, CSRF protection, and session
renewal and expiry, flight ownership and validation, airport import, and pagination.

GitHub Actions runs these checks on Python 3.12 for pull requests and pushes to
`main`. The `Quality checks` job must pass before merging, alongside owner approval.
