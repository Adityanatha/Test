import sqlite3, requests, yaml

cfg = yaml.safe_load(open("config.yaml"))
DB_FILE = "leads.db"

def sync_hubspot():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT linkedin_id, name, profile_url, email FROM leads WHERE status='new'")
    for lid,name,url,email in cur.fetchall():
        data = {"properties": {"firstname": name.split()[0], "linkedin_url": url}}
        headers = {"Authorization": f"Bearer {cfg['hubspot']['api_key']}"}
        r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts", json=data, headers=headers)
        if r.ok:
            cur.execute("UPDATE leads SET status='synced' WHERE linkedin_id=?", (lid,))
    conn.commit()
    conn.close()
