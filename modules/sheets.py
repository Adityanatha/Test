import yaml
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]


def _client(cfg):
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        cfg['gsheets']['creds_json'], scope
    )
    return gspread.authorize(creds)


def get_leads_sheet(cfg):
    client = _client(cfg)
    return client.open_by_key(cfg['gsheets']['spreadsheet_id']).worksheet(cfg['gsheets']['leads_ws'])


def get_metadata_sheet(cfg):
    client = _client(cfg)
    return client.open_by_key(cfg['gsheets']['spreadsheet_id']).worksheet(cfg['gsheets'].get('metadata_ws', 'Metadata'))


def get_all_leads(cfg):
    sheet = get_leads_sheet(cfg)
    records = sheet.get_all_records()
    result = []
    for idx, row in enumerate(records, start=2):
        row['_row'] = idx
        result.append(row)
    return result, sheet


def append_lead(cfg, lead):
    sheet = get_leads_sheet(cfg)
    sheet.append_row([
        lead.get('linkedin_id', ''),
        lead.get('name', ''),
        lead.get('title', ''),
        lead.get('company', ''),
        lead.get('profile_url', ''),
        lead.get('email', ''),
        lead.get('status', 'new'),
        lead.get('extracted_at', ''),
        lead.get('invited_at', ''),
        lead.get('connected_at', ''),
        lead.get('last_visit_at', ''),
        lead.get('followup_sent_at', '')
    ])


def update_lead(sheet, row, col, value):
    sheet.update_cell(row, col, value)


def update_metadata(cfg, field):
    sheet = get_metadata_sheet(cfg)
    headers = sheet.row_values(1)
    if field in headers:
        col = headers.index(field) + 1
        sheet.update_cell(2, col, str(datetime.datetime.utcnow()))

