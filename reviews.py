"""Optional ratings and written experiences belonging to a flight entry."""

RATING_FIELDS = ("overall_rating", "seat_rating", "service_rating", "food_rating",
                 "entertainment_rating", "wifi_rating")
FIELDS = RATING_FIELDS + ("review",)


def errors(values):
    """Accept only whole stars or an unrated value and bound the review text."""
    problems = {}
    for field in RATING_FIELDS:
        if values[field] not in ("", "1", "2", "3", "4", "5"):
            problems[field] = "Select a rating from 1 to 5, or Not rated."
    if len(values["review"]) > 5000:
        problems["review"] = "Use 5,000 characters or fewer."
    return problems


def save(connection, flight_id, values):
    """Write the optional review inside the caller's flight transaction."""
    if not any(values[field] for field in FIELDS):
        connection.execute("DELETE FROM flight_reviews WHERE flight_id = ?", [flight_id])
        return
    ratings = [int(values[field]) if values[field] else None for field in RATING_FIELDS]
    connection.execute("""INSERT INTO flight_reviews
        (flight_id, overall_rating, seat_rating, service_rating, food_rating,
         entertainment_rating, wifi_rating, review) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(flight_id) DO UPDATE SET overall_rating = excluded.overall_rating,
        seat_rating = excluded.seat_rating, service_rating = excluded.service_rating,
        food_rating = excluded.food_rating, entertainment_rating = excluded.entertainment_rating,
        wifi_rating = excluded.wifi_rating, review = excluded.review""",
                       [flight_id] + ratings + [values["review"] or None])
