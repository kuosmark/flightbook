# Flightbook

A social flight diary where passengers can log their flights, rate and review their experiences, and explore other travellers' journeys.

## Planned features

- Create an account and log in.
- Log flights with details such as airline, route, date, aircraft, and cabin class.
- Edit and delete your own flight entries.
- Optionally rate flights and write reviews.
- Classify flights by cabin class and journey purpose using options stored in the database.
- Browse and search your own and other users' flight entries.
- Comment on your own and other users' flights.
- View traveller profiles with flight histories and statistics.

## Technologies

Python, Flask, SQLite, SQL, HTML, Jinja, and CSS.

## Current status

The application currently serves an introductory homepage. Accounts, flight
logging, search, comments, and the database are not implemented yet.

## Run locally

Install Python 3.12, then run these commands from the project directory:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m flask --app app run --debug
```

Open http://127.0.0.1:5000 in your browser. Stop the server with Ctrl+C.
On Windows, create the environment with `py -3.12 -m venv .venv` and activate
it in PowerShell with `.venv\Scripts\Activate.ps1` instead.

If port 5000 is occupied, append `--port 5001` to the run command and open
http://127.0.0.1:5001 instead. The development server is for local use only.
No database initialization or secret configuration is needed at this stage.

## Verify the foundation

- Open `/` and confirm the Flightbook introduction and empty state appear.
- Check the layout at narrow and wide browser widths, including text zoom.
- Use Tab to reveal the skip link, then Enter to move to the main content.
- Follow the Flightbook home link and confirm it returns to `/`.
- Visit a nonexistent URL and confirm the server returns HTTP 404.

With the virtual environment active, check dependency compatibility with
`python -m pip check` and list routes with `python -m flask --app app routes`.
