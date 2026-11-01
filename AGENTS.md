# Flightbook

A social flight diary developed for the University of Helsinki's *Tietokannat ja web-ohjelmointi* course.

## Project constraints

- Follow the [course requirements](https://hy-tikawe.github.io/materiaali/), including the grade-5 criteria and technical checklist.
- Use Python 3.12, Flask, SQLite, raw SQL, Jinja, HTML, and custom CSS.
- Do not use JavaScript, ORMs, frontend or CSS frameworks, external icon/font libraries, or additional application dependencies beyond those permitted by the course.
- Use English for code, identifiers, comments, and commit messages.
- Follow the simple, server-rendered architecture demonstrated in the course.

## Development principles

- Keep changes focused and implementations as simple as possible.
- Agree on requirements and acceptance criteria before substantial work. Make routine implementation decisions independently.
- Inspect relevant code before editing and preserve unrelated or uncommitted changes.
- Prefer readable code, clear naming, small functions, and existing patterns. Avoid unnecessary dependencies and abstractions.
- Use SQL for database operations and aggregations. Select columns explicitly, define appropriate constraints, and avoid unnecessary queries.

## Quality and verification

- Validate input server-side and enforce authentication and authorization.
- Use parameterized SQL, password hashing, template escaping, and CSRF protection.
- Test relevant behavior and failure cases. Run applicable checks before committing and report verification limitations.
- Check UI changes for responsiveness, accessibility, and error states.
- Measure performance before and after performance-related changes using representative data.
- Never commit secrets, local application databases, virtual environments, or temporary files.

## Git and documentation

- The owner-approved initial bootstrap commit, `docs: initialize Flightbook project`, may be made directly on `main` before branch protection is enabled.
- For every subsequent change, create a short-lived branch and pull request. Never push directly to `main` after bootstrap.
- Make small, focused commits with descriptive English messages.
- Review and verify each pull request before merging. Obtain explicit owner approval before merging.
- Squash-merge approved pull requests and delete merged branches.
- Keep the README accurate, including setup instructions and application features.
- Record required Pylint results and performance measurements.
- Avoid unnecessary infrastructure or deployment workflows.

## Development commands

- Create the environment: `python3.12 -m venv .venv`.
- Activate it on macOS/Linux: `source .venv/bin/activate`.
- Install dependencies: `python -m pip install -r requirements.txt`.
- Run locally: `python -m flask --app app run --debug`.
- If port 5000 is occupied, add `--port 5001`.
- Check dependencies: `python -m pip check`.
- Inspect routes: `python -m flask --app app routes`.
- Follow the README's manual verification steps for the homepage.
- No database initialization is needed for the current foundation.
