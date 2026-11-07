"""Flight entries, airport lookups, and form validation."""

from datetime import date
import re

import db

PAGE_SIZE = 20
AIRPORT_RESULT_LIMIT = 20
FLIGHT_NUMBER = re.compile(r"(?=[A-Z0-9]{0,1}[A-Z])[A-Z0-9]{2}[0-9]{1,4}[A-Z]?")
ROUTE_FIELDS = ("departure_date", "departure_code", "arrival_code")
DETAIL_FIELDS = ("airline", "flight_number", "aircraft", "seat", "cabin_id", "purpose_id")
FIELDS = ROUTE_FIELDS + DETAIL_FIELDS


def choices(kind):
    """Return the database-defined options for one classification."""
    return db.query("SELECT id, name FROM categories WHERE kind = ? ORDER BY id", [kind])


def find_airports(query):
    """Find named places locally, with literal matching and bounded results."""
    term = query.strip().casefold()
    return db.query("""SELECT iata_code, name, municipality, iso_country FROM airports
        WHERE instr(casefold(name), ?) OR instr(casefold(coalesce(municipality, '')), ?)
        ORDER BY (casefold(coalesce(municipality, '')) = ?) DESC, name, iata_code
        LIMIT ?""", [term, term, term, AIRPORT_RESULT_LIMIT + 1])


def airport_names(codes):
    """Resolve the two endpoints from their current codes in one query."""
    rows = db.query("SELECT iata_code, name FROM airports WHERE iata_code IN (?, ?)", codes)
    return {row["iata_code"]: row["name"] for row in rows}


def form_values(form):
    """Trim submitted fields and normalize codes without removing internal spaces."""
    values = {field: form.get(field, "").strip() for field in FIELDS}
    for field in ("departure_code", "arrival_code", "flight_number", "seat"):
        if values[field].isascii():
            values[field] = values[field].upper()
    return values


def airport_code_error(code):
    """Validate a supplied code after normalization, including unlisted airports."""
    return None if re.fullmatch(r"[A-Z]{3}", code) else "Enter a three-letter airport code."


def route_errors(values):
    """Identify the individual route fields that need correcting."""
    errors = {}
    try:
        departure = date.fromisoformat(values["departure_date"])
    except ValueError:
        departure = None
    if (not departure or departure.isoformat() != values["departure_date"]
            or departure > date.today()):
        errors["departure_date"] = "Enter a valid departure date on or before today."
    for field in ("departure_code", "arrival_code"):
        if error := airport_code_error(values[field]):
            errors[field] = error
    return errors


def detail_errors(values, cabins, purposes):
    """Validate optional details against the same category options shown in the form."""
    errors = {}
    for field in ("airline", "aircraft"):
        if len(values[field]) > 100:
            errors[field] = "Use 100 characters or fewer."
    if values["flight_number"] and not FLIGHT_NUMBER.fullmatch(values["flight_number"]):
        errors["flight_number"] = "Use a full flight number without spaces."
    if values["seat"] and not re.fullmatch(r"[1-9][0-9]{0,2}[A-Z]", values["seat"]):
        errors["seat"] = "Enter a row from 1 to 999 followed by one letter."
    for field, options in (("cabin_id", cabins), ("purpose_id", purposes)):
        if values[field] and values[field] not in {str(row["id"]) for row in options}:
            errors[field] = "Select one of the listed options."
    return errors


def save(values, user_id, flight_id=None):
    """Insert a flight or update only an entry belonging to its owner."""
    parameters = [values[field] or None for field in FIELDS]
    if flight_id is None:
        return db.execute("""INSERT INTO flights
            (departure_date, departure_code, arrival_code, airline, flight_number,
             aircraft, seat, cabin_id, purpose_id, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", parameters + [user_id])
    db.execute("""UPDATE flights SET departure_date = ?, departure_code = ?, arrival_code = ?,
        airline = ?, flight_number = ?, aircraft = ?, seat = ?, cabin_id = ?, purpose_id = ?
        WHERE id = ? AND user_id = ?""", parameters + [flight_id, user_id])
    return flight_id


FLIGHT_SELECT = """SELECT f.id, f.user_id, f.departure_date, f.departure_code, f.arrival_code,
    f.airline, f.flight_number, f.aircraft, f.seat, f.cabin_id, f.purpose_id, u.username,
    d.name AS departure_name, a.name AS arrival_name,
    c.name AS cabin_name, p.name AS purpose_name
    FROM flights f JOIN users u ON u.id = f.user_id
    LEFT JOIN airports d ON d.iata_code = f.departure_code
    LEFT JOIN airports a ON a.iata_code = f.arrival_code
    LEFT JOIN categories c ON c.id = f.cabin_id
    LEFT JOIN categories p ON p.id = f.purpose_id"""


def get_flight(flight_id):
    """Find a public flight and its optional reference names."""
    rows = db.query(FLIGHT_SELECT + " WHERE f.id = ?", [flight_id])
    return rows[0] if rows else None


def search_filters(args):
    """Read only supported, nonempty filters and report errors next to their fields."""
    filters = {}
    errors = {}
    for key in ("from", "to", "airline", "flight_number"):
        value = args.get(key, "").strip()
        if not value:
            continue
        if key != "airline" and value.isascii():
            value = value.upper()
        filters[key] = value
        if key in ("from", "to"):
            if error := airport_code_error(value):
                errors[key] = error
        elif key == "flight_number" and not FLIGHT_NUMBER.fullmatch(value):
            errors[key] = "Enter a full flight number, such as AY123."
        elif key == "airline" and len(value) > 100:
            errors[key] = "Use 100 characters or fewer."
    return filters, errors


def list_flights(page, filters, user_id=None):
    """Apply all filters within the list's scope before ordering and paging."""
    conditions = []
    parameters = []
    if user_id is not None:
        conditions.append("f.user_id = ?")
        parameters.append(user_id)
    for key, column in (("from", "departure_code"), ("to", "arrival_code"),
                        ("flight_number", "flight_number")):
        if key in filters:
            conditions.append(f"f.{column} = ?")
            parameters.append(filters[key])
    if "airline" in filters:
        conditions.append("instr(casefold(coalesce(f.airline, '')), ?) > 0")
        parameters.append(filters["airline"].casefold())
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    order = (" ORDER BY f.departure_date DESC, f.id DESC"
             if user_id is not None else " ORDER BY f.id DESC")
    return db.query(FLIGHT_SELECT + where + order + " LIMIT ? OFFSET ?",
                    parameters + [PAGE_SIZE + 1, (page - 1) * PAGE_SIZE])


def delete(flight_id, user_id):
    """Delete only the owner's entry."""
    db.execute("DELETE FROM flights WHERE id = ? AND user_id = ?", [flight_id, user_id])
