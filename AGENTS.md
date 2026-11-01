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
- Follow the [Google HTML/CSS Style Guide](https://google.github.io/styleguide/htmlcssguide.html) when writing HTML and CSS, while respecting the course requirements.
- Use SQL for database operations and aggregations. Select columns explicitly, define appropriate constraints, and avoid unnecessary queries.

## Quality and verification

- Validate input server-side and enforce authentication and authorization.
- Use parameterized SQL, password hashing, template escaping, and CSRF protection.
- Test relevant behavior and failure cases. Run applicable checks before committing and report verification limitations.
- Use Pylint's default checks with the repository's Python 3.12 and 100-character line settings. Fix findings; narrowly scope and explain any necessary suppression.
- Check UI changes for responsiveness, accessibility, and error states.
- Measure performance before and after performance-related changes using representative data.
- Never commit secrets, local application databases, virtual environments, or temporary files.

## Git and documentation

- For every change, create a short-lived branch and pull request. Never push directly to `main`.
- Obtain explicit owner approval before opening a pull request.
- Make small, focused commits with descriptive English messages.
- Keep PR descriptions brief: what changed, why, and how it was verified. Include extra detail only when it affects review or merging.
- For visible UI changes, attach a representative screenshot to the PR description. Keep screenshots out of the repository.
- Review and verify each pull request before merging. Obtain explicit owner approval before merging.
- Require the `Quality checks` CI job to pass for the latest revision before merging.
- Squash-merge approved pull requests and delete merged branches.
- Keep the README accurate, including setup instructions and application features.
- Record required Pylint results and performance measurements.
- Avoid unnecessary infrastructure or deployment workflows.

## Development commands

See [README.md](README.md) for setup, run commands, and automated and manual checks.
