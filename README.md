# Flightbook

Flightbook is a social flight diary for the University of Helsinki’s *Tietokannat ja web-ohjelmointi* course.
Anyone can browse and search flight entries. Sign in to log a flight. Only you can edit or delete your own entries.

## Features

- Log, edit, and delete flights with their route, departure date, and optional details like airline, flight number, and cabin class.
- Browse recent public entries or view your own flight history by departure date.
- Search either list by departure airport, arrival airport, airline, or flight number.

**Planned:** flight ratings and reviews, comments, and traveller profiles with flight histories and statistics.

Built with Python 3.12, Flask, SQLite, raw SQL, Jinja, HTML, and CSS. Airport names come from a [bundled snapshot](data/README.md), so airport lookup works offline.

## Run locally

### First-time setup

Install Git and Python 3.12, then clone the repository:

```sh
git clone https://github.com/kuosmark/flightbook.git
cd flightbook
```

Create and activate the virtual environment:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell, use `py -3.12 -m venv .venv` and `.venv\Scripts\Activate.ps1` instead.

Install the dependencies and initialize Flightbook:

```sh
python -m pip install -r requirements.txt
python -m flask --app app init-db
```

This creates the database, imports airport and category data, and generates a private
session key in `instance/session.key`. You can run `init-db` again without replacing
the key or losing accounts and flights.

### Start the app

From the project directory with the virtual environment active, run:

```sh
python -m flask --app app run --debug
```

Open [localhost:5000](http://127.0.0.1:5000). The diary starts empty. Create an account and add your first flight.

If the port is busy, append `--port 5001` to the run command and open [localhost:5001](http://127.0.0.1:5001). Stop the local server with Ctrl+C.

On later starts, activate the environment and run the same Flask command.
If you already set `FLIGHTBOOK_SECRET_KEY`, Flightbook uses it instead of the local key.

## Development checks

With the virtual environment active, install and run the development tools:

```sh
python -m pip install -r requirements-dev.txt
python -m pip check
python -m pylint --rcfile=pyproject.toml *.py tests
python -m unittest discover -s tests -v
```

Tests use a temporary database and won’t change your diary.
