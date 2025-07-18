import yaml
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import datetime
import time
import streamlit as st


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def _client(cfg):
    creds_path = cfg['gsheets']['creds_json']
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        return gspread.authorize(creds)
    except Exception as e:
        raise RuntimeError(
            f"Failed to authenticate with Google Sheets. "
            f"Check gsheets.creds_json at '{creds_path}': {e}"
        )

def get_leads_sheet(cfg):
    client = _client(cfg)
    return client.open_by_key(cfg['gsheets']['spreadsheet_id']).worksheet(cfg['gsheets']['leads_ws'])

def get_metadata_sheet(cfg):
    client = _client(cfg)
    return client.open_by_key(cfg['gsheets']['spreadsheet_id']).worksheet(cfg['gsheets'].get('metadata_ws', 'Metadata'))

def get_company_sheet(cfg):
    client = _client(cfg)
    return client.open_by_key(cfg['gsheets']['spreadsheet_id']).worksheet("CompanyDetails")

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
        'linkedin_id', 'name', 'headline', 'title', 'company', 'company_id',
        'industry', 'profile_url', 'email', 'status', 'connection_level',
        'location', 'extracted_at', 'invited_at', 'connected_at',
        'last_visit_at', 'followup_sent_at'
    ]


    current_header = sheet.row_values(1)

    # Insert header only if the sheet is empty
    if not current_header:
        print("📄 Inserting header into empty sheet.")
        sheet.insert_row(expected_header, index=1)

    elif current_header != expected_header:
        print("⚠️ Header mismatch. Please fix manually to avoid overwriting existing data.")
        raise ValueError("Header mismatch in Google Sheet. Aborting append to avoid data loss.")

    row_data = [lead.get(col, '') for col in expected_header]
    sheet.append_row(row_data, value_input_option='USER_ENTERED')


def update_lead(cfg, updated_lead):
    leads, sheet = get_all_leads(cfg)
    headers = sheet.row_values(1)
    linkedin_id = updated_lead.get('linkedin_id')
    row_index = None

    for lead in leads:
        if lead.get('linkedin_id') == linkedin_id:
            row_index = lead['_row']
            break

    if row_index is None:
        print(f"❌ Lead with ID {linkedin_id} not found.")
        return

    row_data = [updated_lead.get(h, "") for h in headers]
    end_col_letter = chr(65 + len(headers) - 1)
    sheet.update(f"A{row_index}:{end_col_letter}{row_index}", [row_data])
    print(f"🔄 Lead {linkedin_id} updated in row {row_index}.")

def update_metadata(cfg, field):
    sheet = get_metadata_sheet(cfg)
    headers = sheet.row_values(1)
    if field in headers:
        col = headers.index(field) + 1
        sheet.update_cell(2, col, str(datetime.datetime.utcnow()))

def append_company(cfg, company_data):
    sheet = get_company_sheet(cfg)

    expected_header = ['company_id', 'company_name', 'description', 'company_iq', 'industry', 'enriched_at']
    current_header = sheet.row_values(1)
    if current_header != expected_header:
        print("⚠️ Resetting CompanyDetails header.")
        sheet.clear()
        sheet.insert_row(expected_header, index=1)

    row_data = [company_data.get(col, '') for col in expected_header]
    sheet.append_row(row_data, value_input_option='USER_ENTERED')

def get_existing_companies(cfg):
    sheet = get_company_sheet(cfg)
    try:
        rows = sheet.col_values(1)[1:]  # company_id column
        return set(rows)
    except Exception:
        return set()

def update_company(cfg, company_data):
    sheet = get_company_sheet(cfg)
    records = sheet.get_all_records()
    headers = sheet.row_values(1)

    for i, row in enumerate(records, start=2):
        if row.get('company_id') == company_data['company_id']:
            values = [company_data.get(h, '') for h in headers]
            sheet.update(f"A{i}:{chr(65+len(headers)-1)}{i}", [values])
            return

def get_company_row(cfg, company_id):
    sheet = get_company_sheet(cfg)
    records = sheet.get_all_records()
    for idx, row in enumerate(records, start=2):
        if str(row.get('company_id')) == str(company_id):
            row['_row'] = idx
            return row
    return None

def needs_company_update(cfg, company_id):
    row = get_company_row(cfg, company_id)
    if not row:
        return True
    return "Sorry, we’re currently experiencing high demand." in row.get('company_iq', '')

def get_scheduled_sheet(cfg):
    client = _client(cfg)
    return client.open_by_key(cfg['gsheets']['spreadsheet_id']).worksheet("ScheduledMessages")

def get_all_scheduled_messages(cfg):
    sheet = get_scheduled_sheet(cfg)
    records = sheet.get_all_records()
    result = []
    for idx, row in enumerate(records, start=2):
        row['_row'] = idx
        result.append(row)
    return result, sheet

def get_scheduled_messages_worksheet(config):
    return _get_worksheet(config, config["gsheets"]["spreadsheet_id"], "ScheduledMessages")


def append_scheduled_message(config, new_record, existing_keys=None):
    sheet = get_scheduled_sheet(config)
    existing_records = sheet.get_all_records()

    # Skip if already scheduled via keys
    if existing_keys and (new_record["linkedin_id"], new_record["message_id"]) in existing_keys:
        return

    # Skip duplicates based on content
    for row in existing_records:
        if (
                row.get("linkedin_id") == new_record["linkedin_id"] and
                row.get("message_id") == new_record["message_id"]
        ):
            return

    # Determine if it's the first scheduled message for this lead
    lead_id = new_record["linkedin_id"]
    is_first_time = not any(
        row.get("linkedin_id") == lead_id for row in existing_records
    )

    # Determine next rank
    existing_ranks = [
        int(row.get("rank", 0)) for row in existing_records
        if row.get("linkedin_id") == lead_id and str(row.get("rank")).isdigit()
    ]
    next_rank = max(existing_ranks) + 1 if existing_ranks else 1
    new_record["rank"] = next_rank

    # Ensure header is correct
    expected_header = [
        'rank', 'message_id', 'linkedin_id', 'message_text', 'message_type',
        'scheduled_for', 'status', 'industry_bucket', 'created_at',
        'chat_history', 'name', 'title', 'company', 'industry'
    ]
    current_header = sheet.row_values(1)
    if not current_header:
        sheet.insert_row(expected_header, index=1)
    elif current_header != expected_header:
        raise ValueError("⚠️ Header mismatch in ScheduledMessages. Please fix manually.")

    # Append to sheet
    row_data = [new_record.get(col, "") for col in expected_header]
    sheet.append_row(row_data, value_input_option='USER_ENTERED')
    time.sleep(2)

    # Mark lead status as "in_progress" if this is the first scheduled message
    if is_first_time:
        update_lead_status(config, {
            "linkedin_id": lead_id,
            "status": "in_progress"
        })

def update_lead_status(cfg, lead_update):
    leads, sheet = get_all_leads(cfg)
    headers = sheet.row_values(1)
    row_index = None

    for lead in leads:
        if lead.get('linkedin_id') == lead_update['linkedin_id']:
            row_index = lead['_row']
            break

    if row_index is None:
        print(f"❌ Lead with ID {lead_update['linkedin_id']} not found.")
        return

    if "status" not in headers:
        print("⚠️ 'status' column not found in Leads sheet.")
        return

    col_index = headers.index("status") + 1
    sheet.update_cell(row_index, col_index, lead_update["status"])
    print(f"✅ Status updated to {lead_update['status']} for {lead_update['linkedin_id']}")


def update_lead_industry_bucket(cfg, lead):
    sheet = get_leads_sheet(cfg)
    records = sheet.get_all_records()

    for idx, row in enumerate(records, start=2):  # Row 1 is header
        if str(row.get("linkedin_id", "")).strip() == str(lead.get("linkedin_id", "")).strip():
            headers = sheet.row_values(1)
            if "industry_bucket" not in [h.strip().lower() for h in headers]:
                raise ValueError("❌ 'industry_bucket' column not found in Leads sheet.")
            col_index = headers.index("industry_bucket") + 1
            sheet.update_cell(idx, col_index, lead.get("industry_bucket", ""))
            print(f"✅ Updated industry bucket for {lead.get('name')}")
            return

def get_message_library(config):
    sheet = _get_worksheet(config, config["gsheets"]["spreadsheet_id"], "Message_Library")
    return sheet.get_all_records()


def _get_worksheet(config, spreadsheet_id, worksheet_name):
    client = _client(config)  # ✅ Correct
    sheet = client.open_by_key(spreadsheet_id)
    return sheet.worksheet(worksheet_name)

def get_scheduled_messages(config):
    sheet = _get_worksheet(config, config["gsheets"]["spreadsheet_id"], "ScheduledMessages")
    return sheet.get_all_records()


def get_worksheet(config, worksheet_name):
    client = _client(config)
    sheet = client.open_by_key(config['gsheets']['spreadsheet_id'])
    return sheet.worksheet(worksheet_name)

@st.cache_data(show_spinner=False)
def get_cached_message_library(config):
    return get_message_library(config)

@st.cache_data(show_spinner=False)
def get_cached_scheduled_messages(config):
    return get_scheduled_messages(config)

@st.cache_data(show_spinner=False)
def get_cached_leads(config):
    return get_all_leads(config)[0]  # [0] = just the records, not the sheet

@st.cache_data(show_spinner=False)
def get_cached_company_sheet(config):
    return get_company_sheet(config).get_all_records()
