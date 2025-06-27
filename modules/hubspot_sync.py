import requests, yaml, os
from modules import sheets
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

def sync_hubspot():
    cfg = yaml.safe_load(open(CONFIG_FILE))
    leads, sheet = sheets.get_all_leads(cfg)
    leads = [l for l in leads if l.get('status') == 'new']
    for l in leads:
        lid = l['linkedin_id']; name = l['name']; url = l['profile_url']; email = l.get('email')
        data = {"properties": {"firstname": name.split()[0], "linkedin_url": url}}
        headers = {"Authorization": f"Bearer {cfg['hubspot']['api_key']}"}
        r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts", json=data, headers=headers)
        if r.ok:
            sheets.update_lead(sheet, l['_row'], 7, 'synced')
            sheets.update_lead(sheet, l['_row'], 8, l.get('extracted_at') or datetime.datetime.utcnow().isoformat())
    sheets.update_metadata(cfg, 'last_sync')
