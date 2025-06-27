import sqlite3, requests, yaml, os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")
DB_FILE = os.path.join(BASE_DIR, "leads.db")

def sync_hubspot():
    cfg = yaml.safe_load(open(CONFIG_FILE))
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT linkedin_id, name, profile_url, email FROM leads WHERE status='new'")
    for lid,name,url,email in cur.fetchall():
        data = {"properties": {"firstname": name.split()[0], "linkedin_url": url}}
        headers = {"Authorization": f"Bearer {cfg['hubspot']['api_key']}"}
        r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts", json=data, headers=headers)
        if r.ok:
            cur.execute("UPDATE leads SET status='synced' WHERE linkedin_id=?", (lid,))
    cur.execute("UPDATE metadata SET last_sync=CURRENT_TIMESTAMP")
    conn.commit()
    conn.close()
