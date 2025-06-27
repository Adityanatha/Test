import datetime, yaml, os
from modules import sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

def push_daily_metrics():
    cfg = yaml.safe_load(open(CONFIG_FILE))
    leads, _ = sheets.get_all_leads(cfg)
    today = datetime.date.today().isoformat()
    metrics = {
        'date': today,
        'new_leads': sum(1 for l in leads if l.get('extracted_at','').split('T')[0] == today),
        'invites': sum(1 for l in leads if l.get('invited_at','').split('T')[0] == today),
        'accepted': sum(1 for l in leads if l.get('connected_at','').split('T')[0] == today),
        'followups': sum(1 for l in leads if l.get('followup_sent_at','').split('T')[0] == today)
    }

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(cfg['gsheets']['creds_json'], scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(cfg['gsheets']['spreadsheet_id']).worksheet(cfg['gsheets']['report_ws'])
    sheet.append_row([metrics['date'], metrics['new_leads'], metrics['invites'], metrics['accepted'], metrics['followups']])
    sheets.update_metadata(cfg, 'last_report')
