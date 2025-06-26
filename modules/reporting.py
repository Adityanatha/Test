import sqlite3, datetime, gspread
from oauth2client.service_account import ServiceAccountCredentials

DB_FILE = "leads.db"

def push_daily_metrics():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    today = datetime.date.today().isoformat()
    metrics = {
        'date': today,
        'new_leads': cur.execute("SELECT COUNT(*) FROM leads WHERE DATE(extracted_at)=?", (today,)).fetchone()[0],
        'invites': cur.execute("SELECT COUNT(*) FROM leads WHERE DATE(invited_at)=?", (today,)).fetchone()[0],
        'accepted': cur.execute("SELECT COUNT(*) FROM leads WHERE DATE(connected_at)=?", (today,)).fetchone()[0],
        'followups': cur.execute("SELECT COUNT(*) FROM leads WHERE DATE(followup_sent_at)=?", (today,)).fetchone()[0]
    }
    # TODO: authenticate with Google Sheets and append metrics
    conn.close()
