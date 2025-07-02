import yaml, os
import random, time
from datetime import datetime

try:
    import streamlit as st
except ModuleNotFoundError:
    import sys
    sys.exit("Error: 'streamlit' module not found. Install via 'pip install streamlit'.")

from modules import sheets
from modules.login import manual_login
from modules.salesnav_extract import extract_all_searches, extract_list
from modules.hubspot_sync import sync_hubspot
from modules.message_gen import generate_connection, generate_followup
from modules.outreach import send_invites, process_followups
from modules.salesnav_lists import add_search_results_to_list
from modules.reporting import push_daily_metrics

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

@st.cache_data
def load_config():
    if os.path.exists(CONFIG_FILE):
        return yaml.safe_load(open(CONFIG_FILE)) or {}
    return {}

def save_config(cfg):
    yaml.dump(cfg, open(CONFIG_FILE, "w"))

config = load_config()
st.title("BDR Pipeline Dashboard")

# CONFIG SECTION
with st.expander("⚙️ Configuration"):
    linkedin_user = st.text_input("LinkedIn Username", value=config.get("linkedin", {}).get("username", ""))
    linkedin_pass = st.text_input("LinkedIn Password", type="password")
    searches_raw = st.text_area("SalesNav Searches (name|url per line)", value="\n".join(
        [f"{s['name']}|{s['url']}" for s in config.get("linkedin", {}).get("searches", [])]))
    new_list = st.text_input('New Leads List URL', value=config.get('linkedin', {}).get('lists', {}).get('new_leads', ''))
    invited_list = st.text_input('Invited List URL', value=config.get('linkedin', {}).get('lists', {}).get('invited', ''))
    connected_list = st.text_input('Connected List URL', value=config.get('linkedin', {}).get('lists', {}).get('connected', ''))
    bulk_search_url = st.text_input('Search URL to add 100 leads', '')

    hub_key = st.text_input("HubSpot API Key", type="password", value=config.get("hubspot", {}).get("api_key", ""))
    hf_token = st.text_input("HuggingFace Token", type="password", value=config.get("huggingface", {}).get("token", ""))
    hf_model = st.text_input("HF Model", value=config.get("huggingface", {}).get("model", "meta-llama/Llama-2-7b-chat-hf"))
    min_delay = st.number_input("Min Delay (sec)", value=config.get("rate_limits", {}).get("min_delay_sec", 30))
    max_delay = st.number_input("Max Delay (sec)", value=config.get("rate_limits", {}).get("max_delay_sec", 90))
    conn_seed = st.text_area("Connection Prompt", value=config.get("seeds", {}).get("connection", ""))
    follow_seed = st.text_area("Follow-Up Prompt", value=config.get("seeds", {}).get("followup", ""))
    gs_creds = st.text_input("Google Creds JSON", value=config.get("gsheets", {}).get("creds_json", ""))
    gs_sheet = st.text_input("Spreadsheet ID", value=config.get("gsheets", {}).get("spreadsheet_id", ""))
    gs_leads_ws = st.text_input("Leads Worksheet", value=config.get("gsheets", {}).get("leads_ws", "Leads"))
    gs_report_ws = st.text_input("Report Worksheet", value=config.get("gsheets", {}).get("report_ws", "Report"))

    if st.button("Save Configuration"):
        searches = []
        for line in searches_raw.splitlines():
            if '|' in line:
                name, url = line.split('|', 1)
                searches.append({'name': name.strip(), 'url': url.strip()})
        new_cfg = {
            'linkedin': {
                'username': linkedin_user,
                'password': linkedin_pass,
                'searches': searches,
                'lists': {
                    'new_leads': new_list,
                    'invited': invited_list,
                    'connected': connected_list
                }
            },
            'hubspot': {'api_key': hub_key},
            'huggingface': {'token': hf_token, 'model': hf_model},
            'rate_limits': {'min_delay_sec': int(min_delay), 'max_delay_sec': int(max_delay)},
            'seeds': {'connection': conn_seed, 'followup': follow_seed},
            'gsheets': {
                'creds_json': gs_creds,
                'spreadsheet_id': gs_sheet,
                'leads_ws': gs_leads_ws,
                'report_ws': gs_report_ws
            }
        }
        save_config(new_cfg)
        load_config.cache_clear()
        config = load_config()
        st.success("✅ Configuration saved.")

# MAIN ACTIONS
st.markdown("---")
if st.button("Login to LinkedIn"):
    try:
        pw, ctx = manual_login()
        st.session_state["pw"] = pw
        st.session_state["context"] = ctx
        st.success("✅ Logged in. Browser context saved.")
    except Exception as e:
        st.error(f"❌ Login failed: {e}")

if st.button('Add Search to New Leads'):
    try:
        add_search_results_to_list(bulk_search_url, new_list, st.session_state.get('context'))
        st.success('✅ Added leads to list.')
    except Exception as e:
        st.error(f'❌ Failed to add leads: {e}')

cols = st.columns(4)
if cols[0].button("1. Extract Leads"):
    try:
        if new_list:
            extract_list(new_list, st.session_state.get("context"))
        else:
            extract_all_searches(st.session_state.get("context"))
        st.success("✅ Extraction complete.")
    except Exception as e:
        st.error(f"❌ Extraction failed: {e}")

if cols[1].button("2. Sync to HubSpot"):
    try:
        sync_hubspot()
        st.success("✅ Sync complete.")
    except Exception as e:
        st.error(f"❌ Sync failed: {e}")

if cols[2].button("3. Send Invites"):
    try:
        send_invites(st.session_state.get("context"))
        st.success("✅ Invites sent.")
    except Exception as e:
        st.error(f"❌ Invite sending failed: {e}")

if cols[3].button("4. Process Follow-Ups"):
    try:
        process_followups(st.session_state.get("context"))
        st.success("✅ Follow-ups processed.")
    except Exception as e:
        st.error(f"❌ Follow-up failed: {e}")

if st.button("5. Push Reporting Metrics"):
    try:
        push_daily_metrics()
        st.success("✅ Metrics pushed.")
    except Exception as e:
        st.error(f"❌ Reporting failed: {e}")

# DASHBOARD STATUS
st.markdown("### 📊 Pipeline Status & Lead Counts")
try:
    cfg = load_config()
    leads, _ = sheets.get_all_leads(cfg)
    meta_sheet = sheets.get_metadata_sheet(cfg)
    headers = meta_sheet.row_values(1)
    values = meta_sheet.row_values(2)
    meta = dict(zip(headers, values))

    st.write({
        'Last Extract': meta.get('last_extract'),
        'Last Sync': meta.get('last_sync'),
        'Last Outreach': meta.get('last_outreach'),
        'Last Follow-up': meta.get('last_followup'),
        'Last Report': meta.get('last_report')
    })

    status_counts = {}
    for l in leads:
        status = l.get('status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1

    st.table(status_counts)

except Exception as e:
    st.error(f"❌ Failed to load dashboard: {e}")

# -------------------------------
# 🧪 TEST MESSAGE GENERATOR PANEL
# -------------------------------
st.markdown("### 🧪 Test Message Generator")

test_col1, test_col2 = st.columns(2)
lead_name = test_col1.text_input("Name", "Ravi Mehra")
lead_title = test_col2.text_input("Title", "VP of Engineering")
lead_company = test_col1.text_input("Company", "Finovate")
lead_industry = test_col2.text_input("Industry", "Fintech")

category = st.selectbox("Message Category", [
    "initial_message", "nurture_message", "follow_up_message",
    "informative_message", "collateral_message", "meeting_message", "contextual_pitch"
])

chat_history = st.text_area("Chat History", "Connected, no reply yet.")
leadiq_data = st.text_area("LeadIQ Signals", "Hiring ML engineers, posted about GenAI.")
pdf_summary = st.text_area("Company PDF Summary", "Finovate is building AI-driven personalization tools.")

if st.button("Generate Test Message"):
    test_lead = {
        "name": lead_name,
        "title": lead_title,
        "company": lead_company,
        "industry": lead_industry,
        "chat_history": chat_history,
        "leadiq": leadiq_data,
        "pdf_summary": pdf_summary,
        "category": category
    }

    try:
        message = generate_connection(test_lead)
        st.success("✅ Message Generated:")
        st.code(message, language="markdown")
    except Exception as e:
        st.error(f"❌ Failed to generate message: {e}")
