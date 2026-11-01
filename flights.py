"""Flight entries, airport lookups, and form validation."""

from datetime import date
import re

import db

PAGE_SIZE = 20
FIELDS = ("departure_date", "departure_code", "arrival_code", "airline", "flight_number",
          "aircraft", "seat", "cabin_id", "purpose_id")


def choices(kind):
    """Return the database-defined options for one classification."""
    return db.query("SELECT id, name FROM categories WHERE kind = ? ORDER BY id", [kind])


def airports():
    """Return airport suggestions in code order."""
    return db.query("""SELECT iata_code, name, municipality, iso_country
        FROM airports ORDER BY iata_code""")


def form_values(form):
    """Trim submitted fields and normalize codes without removing internal spaces."""
    values = {field: form.get(field, "").strip() for field in FIELDS}
    for field in ("departure_code", "arrival_code", "flight_number", "seat"):
        values[field] = values[field].upper()
    return values


def validation_error(values):
    """Check dates, bounded text, code formats, and classification membership."""
    try:
        departure = date.fromisoformat(values["departure_date"])
    except ValueError:
        return "Enter a valid departure date."
    if departure.isoformat() != values["departure_date"] or departure > date.today():
        return "Enter a departure date on or before today."
    for field in ("departure_code", "arrival_code"):
        if not re.fullmatch(r"[A-Z]{3}", values[field]):
            return "Use a three-letter airport code for departure and arrival."
    return detail_error(values)


def detail_error(values):
    """Validate optional flight details and category choices."""
    for field in ("airline", "aircraft"):
        if len(values[field]) > 100:
            return "Keep airline and aircraft names within 100 characters."
    number = values["flight_number"]
    if number and not re.fullmatch(r"(?=[A-Z0-9]{0,1}[A-Z])[A-Z0-9]{2}[0-9]{1,4}[A-Z]?", number):
        return "Use a flight number such as AY123, without spaces."
    if values["seat"] and not re.fullmatch(r"[1-9][0-9]{0,2}[A-Z]", values["seat"]):
        return "Use a seat number such as 12A (row 1–999 and one letter)."
    for kind in ("cabin", "purpose"):
        value = values[f"{kind}_id"]
        if value and value not in {str(row["id"]) for row in choices(kind)}:
            return "Select a valid cabin class and journey purpose."
    return None


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


def list_flights(page, user_id=None):
    """Fetch a bounded page plus one row to determine whether more exist."""
    where = " WHERE f.user_id = ?" if user_id is not None else ""
    order = (" ORDER BY f.departure_date DESC, f.id DESC"
             if user_id is not None else " ORDER BY f.id DESC")
    parameters = [user_id] if user_id is not None else []
    return db.query(FLIGHT_SELECT + where + order + " LIMIT ? OFFSET ?",
                    parameters + [PAGE_SIZE + 1, (page - 1) * PAGE_SIZE])


def delete(flight_id, user_id):
    """Delete only the owner's entry."""
    db.execute("DELETE FROM flights WHERE id = ? AND user_id = ?", [flight_id, user_id])
