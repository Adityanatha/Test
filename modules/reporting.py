import sqlite3, datetime, gspread, yaml, os
from oauth2client.service_account import ServiceAccountCredentials

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")
DB_FILE = os.path.join(BASE_DIR, "leads.db")

def push_daily_metrics():
    cfg = yaml.safe_load(open(CONFIG_FILE))
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

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(cfg['reporting']['creds_json'], scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(cfg['reporting']['spreadsheet_id']).worksheet(cfg['reporting']['worksheet'])
    sheet.append_row([metrics['date'], metrics['new_leads'], metrics['invites'], metrics['accepted'], metrics['followups']])
    cur.execute("UPDATE metadata SET last_report=CURRENT_TIMESTAMP")
    conn.commit()
    conn.close()
