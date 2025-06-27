import sqlite3, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "leads.db")
conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

# Create leads table
cur.execute("""
CREATE TABLE IF NOT EXISTS leads (
    linkedin_id      TEXT PRIMARY KEY,
    name             TEXT,
    title            TEXT,
    company          TEXT,
    profile_url      TEXT,
    email            TEXT,
    status           TEXT DEFAULT 'new',
    extracted_at     DATETIME,
    invited_at       DATETIME,
    connected_at     DATETIME,
    last_visit_at    DATETIME,
    followup_sent_at DATETIME
)
""")

# Create metadata table for audit
cur.execute("""
CREATE TABLE IF NOT EXISTS metadata (
    last_extract   DATETIME,
    last_sync      DATETIME,
    last_outreach  DATETIME,
    last_followup  DATETIME,
    last_report    DATETIME
)
""")
# Ensure one row exists for metadata
cur.execute("INSERT INTO metadata (rowid) SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM metadata)")

conn.commit()
conn.close()
print("Initialized leads.db schema.")
