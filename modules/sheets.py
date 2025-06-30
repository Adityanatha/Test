import yaml
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def _client(cfg):
    creds = ServiceAccountCredentials.from_json_keyfile_name(cfg['gsheets']['creds_json'], scope)
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

    expected_header = [
        'linkedin_id',
        'name',
        'title',
        'company',
        'profile_url',
        'email',
        'status',
        'extracted_at',
        'invited_at',
        'connected_at',
        'last_visit_at',
        'followup_sent_at'
    ]

    current_header = sheet.row_values(1)
    if current_header != expected_header:
        print("⚠️ Header missing or incorrect. Resetting header row.")
        sheet.clear()
        sheet.insert_row(expected_header, index=1)

    row_data = [lead.get(col, '') for col in expected_header]
    sheet.append_row(row_data, value_input_option='USER_ENTERED')

def update_lead(sheet, row, col, value):
    sheet.update_cell(row, col, value)

def update_metadata(cfg, field):
    sheet = get_metadata_sheet(cfg)
    headers = sheet.row_values(1)
    if field in headers:
        col = headers.index(field) + 1
        sheet.update_cell(2, col, str(datetime.datetime.utcnow()))
