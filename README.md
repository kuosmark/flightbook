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

## Development checks

With the virtual environment active, install and run the development tools:

```sh
python -m pip install -r requirements-dev.txt
python -m pip check
python -m pylint --rcfile=pyproject.toml *.py tests
python -m unittest discover -s tests -v
```

`requirements.txt` lists application dependencies. `requirements-dev.txt` includes
that file and adds Pylint for development; it is not needed to run the app.
The smoke test uses Python's built-in `unittest` and Flask's test client to render
the homepage and load its referenced local stylesheets, without starting a server.

Pylint uses its default checks, targeting Python 3.12 with a 100-character Python
line limit. Fix findings rather than disabling whole categories; explain any
necessary, narrowly scoped exception. The course's final Pylint report will be
prepared from the completed application, including explanations for remaining findings.

`.editorconfig` provides whitespace and indentation defaults for supporting editors.
It does not install a formatter or replace linting and review.

GitHub Actions runs dependency checks, Pylint, and the smoke test on Python 3.12
for pull requests and pushes to `main`. The `Quality checks` job must pass on the
latest revision before merging, alongside owner approval. Continue to perform
the manual UI checks above; automated checks do not verify visual usability.
