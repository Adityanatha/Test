try:
    import streamlit as st
except ModuleNotFoundError:
    import sys
    sys.exit("Error: 'streamlit' module not found. Install via 'pip install streamlit'.")

import yaml, sqlite3, os
from datetime import datetime
from modules.salesnav_extract import extract_all_searches
from modules.hubspot_sync import sync_hubspot
from modules.message_gen import generate_connection, generate_followup
from modules.outreach import send_invites, process_followups
from modules.reporting import push_daily_metrics

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")
DB_FILE = os.path.join(BASE_DIR, "leads.db")

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
    linkedin_user = st.text_input("LinkedIn Username", value=config.get("linkedin", {}).get("username", ""))
    linkedin_pass = st.text_input("LinkedIn Password", type="password")
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
            'seeds': {'connection': conn_seed, 'followup': follow_seed}
        }
        save_config(new_cfg)
        load_config.cache_clear()
        config = load_config()
        st.success("Configuration saved.")

st.markdown("---")
cols = st.columns(4)
if cols[0].button("1. Extract Leads"): extract_all_searches(); st.success("Extraction complete.")
if cols[1].button("2. Sync to HubSpot"): sync_hubspot(); st.success("Sync complete.")
if cols[2].button("3. Send Invites"): send_invites(); st.success("Invites sent.")
if cols[3].button("4. Process Follow-Ups"): process_followups(); st.success("Follow-ups processed.")
if st.button("5. Push Reporting Metrics"): push_daily_metrics(); st.success("Metrics pushed.")

st.markdown("### Pipeline Status & Lead Counts")
conn = sqlite3.connect(DB_FILE)
meta = conn.execute("SELECT * FROM metadata").fetchone()
st.write({
    'Last Extract':   meta[0],
    'Last Sync':      meta[1],
    'Last Outreach':  meta[2],
    'Last Follow-up': meta[3],
    'Last Report':    meta[4]
})
status_counts = dict(conn.execute("SELECT status, COUNT(*) FROM leads GROUP BY status").fetchall())
st.table(status_counts)
conn.close()
