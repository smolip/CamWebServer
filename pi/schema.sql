CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    triggered_at   DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    ended_at       DATETIME,
    duration_s     INTEGER,
    source         TEXT NOT NULL DEFAULT 'pir',  -- 'pir' nebo 'manual'
    recording_path TEXT
);

CREATE TABLE IF NOT EXISTS recordings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL UNIQUE,     -- rel. cesta pod RECS_DIR: cam/20250518_143022-000.mp4
    recorded_at DATETIME NOT NULL,        -- parsováno z názvu souboru
    size_bytes  INTEGER,
    event_id    INTEGER REFERENCES events(id) ON DELETE SET NULL
);
