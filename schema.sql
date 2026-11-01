CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS airports (
    id INTEGER PRIMARY KEY,
    iata_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    municipality TEXT NOT NULL,
    iso_country TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('cabin', 'purpose')),
    name TEXT NOT NULL,
    UNIQUE (kind, name)
);

INSERT OR IGNORE INTO categories (id, kind, name) VALUES
    (1, 'cabin', 'Economy'),
    (2, 'cabin', 'Premium economy'),
    (3, 'cabin', 'Business'),
    (4, 'cabin', 'First'),
    (5, 'purpose', 'Leisure'),
    (6, 'purpose', 'Business'),
    (7, 'purpose', 'Other');

CREATE TABLE IF NOT EXISTS flights (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users,
    departure_date TEXT NOT NULL,
    departure_code TEXT NOT NULL CHECK (length(departure_code) = 3),
    arrival_code TEXT NOT NULL CHECK (length(arrival_code) = 3),
    airline TEXT,
    flight_number TEXT,
    aircraft TEXT,
    seat TEXT,
    cabin_id INTEGER REFERENCES categories,
    purpose_id INTEGER REFERENCES categories
);

CREATE INDEX IF NOT EXISTS flights_user_date ON flights (user_id, departure_date DESC, id DESC);
