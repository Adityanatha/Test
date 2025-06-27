try:
    import streamlit as st
except ModuleNotFoundError:
    import sys
    sys.exit("Error: 'streamlit' module not found. Install via 'pip install streamlit'.")

import yaml, os
from modules import sheets
from modules.login import manual_login
from datetime import datetime
from modules.salesnav_extract import extract_all_searches
from modules.hubspot_sync import sync_hubspot
from modules.message_gen import generate_connection, generate_followup
from modules.outreach import send_invites, process_followups
from modules.reporting import push_daily_metrics

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

@st.cache_data
def load_config():
    if os.path.exists(CONFIG_FILE):
        return yaml.safe_load(open(CONFIG_FILE)) or {}
    return {}


def save_config(cfg):
    yaml.dump(cfg, open(CONFIG_FILE, "w"))

config = load_config()
st.title("Free BDR Pipeline Dashboard")

with st.expander("⚙️ Configuration"):
    linkedin_user = st.text_input(
        "LinkedIn Username",
        value=config.get("linkedin", {}).get("username", ""),
        help="Optional. Only needed for automated login",
    )
    linkedin_pass = st.text_input(
        "LinkedIn Password",
        type="password",
        help="Optional. Only needed for automated login",
    )
    searches_raw   = st.text_area(
        "SalesNav Searches (name|url per line)",
        value="\n".join([f"{s['name']}|{s['url']}" for s in config.get("linkedin", {}).get("searches", [])])
    )
    hub_key        = st.text_input("HubSpot API Key", type="password", value=config.get("hubspot", {}).get("api_key", ""))
    hf_token       = st.text_input("HuggingFace Token", type="password", value=config.get("huggingface", {}).get("token", ""))
    hf_model       = st.text_input("HF Model", value=config.get("huggingface", {}).get("model", "meta-llama/Llama-2-7b-chat-hf"))
    min_delay      = st.number_input("Min Delay (sec)", value=config.get("rate_limits", {}).get("min_delay_sec", 30))
    max_delay      = st.number_input("Max Delay (sec)", value=config.get("rate_limits", {}).get("max_delay_sec", 90))
    conn_seed      = st.text_area("Connection Prompt", value=config.get("seeds", {}).get("connection", ""))
    follow_seed    = st.text_area("Follow-Up Prompt", value=config.get("seeds", {}).get("followup", ""))
    gs_creds       = st.text_input("Google Creds JSON", value=config.get("gsheets", {}).get("creds_json", ""))
    gs_sheet       = st.text_input("Spreadsheet ID", value=config.get("gsheets", {}).get("spreadsheet_id", ""))
    gs_leads_ws    = st.text_input("Leads Worksheet", value=config.get("gsheets", {}).get("leads_ws", "Leads"))
    gs_report_ws   = st.text_input("Report Worksheet", value=config.get("gsheets", {}).get("report_ws", "Report"))

    if st.button("Save Configuration"):
        searches = []
        for line in searches_raw.splitlines():
            if '|' in line:
                name, url = line.split('|',1)
                searches.append({'name': name.strip(), 'url': url.strip()})
        new_cfg = {
            'linkedin': {'username': linkedin_user, 'password': linkedin_pass, 'searches': searches},
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
        st.success("Configuration saved.")

st.markdown("---")
if st.button("Login to LinkedIn"):
    pw, ctx = manual_login()
    st.session_state["pw"] = pw
    st.session_state["context"] = ctx
    st.success("Logged in. Browser context saved.")

cols = st.columns(4)
if cols[0].button("1. Extract Leads"):
    extract_all_searches(st.session_state.get("context"))
    st.success("Extraction complete.")
if cols[1].button("2. Sync to HubSpot"):
    sync_hubspot()
    st.success("Sync complete.")
if cols[2].button("3. Send Invites"):
    send_invites(st.session_state.get("context"))
    st.success("Invites sent.")
if cols[3].button("4. Process Follow-Ups"):
    process_followups(st.session_state.get("context"))
    st.success("Follow-ups processed.")
if st.button("5. Push Reporting Metrics"):
    push_daily_metrics()
    st.success("Metrics pushed.")

st.markdown("### Pipeline Status & Lead Counts")
cfg = load_config()
leads, _ = sheets.get_all_leads(cfg)
meta_sheet = sheets.get_metadata_sheet(cfg)
headers = meta_sheet.row_values(1)
values = meta_sheet.row_values(2)
meta = dict(zip(headers, values))
st.write({
    'Last Extract':   meta.get('last_extract'),
    'Last Sync':      meta.get('last_sync'),
    'Last Outreach':  meta.get('last_outreach'),
    'Last Follow-up': meta.get('last_followup'),
    'Last Report':    meta.get('last_report')
})
status_counts = {}
for l in leads:
    status_counts[l.get('status','unknown')] = status_counts.get(l.get('status','unknown'),0) + 1
st.table(status_counts)
