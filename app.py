import yaml
import os
import uuid
import time
import streamlit as st
from datetime import datetime
from collections import defaultdict
from modules import sheets
from modules.login import manual_login
from modules.salesnav_extract import extract_all_searches
from modules.hubspot_sync import sync_hubspot
from modules.message_gen import generate_connection, generate_followup, generate_dynamic_message
from modules.outreach import send_invites, process_followups
from modules.salesnav_lists import add_search_results_to_list
from modules.reporting import push_daily_metrics
from modules.enrich_leads import enrich_missing_leads
from modules.industry_mapper import load_bucket_mapping, get_industry_bucket

from modules.scheduler import MessageScheduler
import pandas as pd
from modules.scheduler import MessageScheduler


CONFIG_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), "config.yaml")
COLLATERAL_DIR = "collateral"
COLLATERAL_CONFIG = "config/collaterals.yaml"

@st.cache_data
def load_config():
    if os.path.exists(CONFIG_FILE):
        return yaml.safe_load(open(CONFIG_FILE)) or {}
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(cfg, f)


@st.cache_data(ttl=60)  # cache for 60 seconds
def get_cached_message_library(config):
    return sheets.get_cached_message_library(config)

@st.cache_data(ttl=60)  # cache for 60 seconds
def get_cached_leads(config):
    leads = sheets.get_cached_leads(config)
    return leads

@st.cache_data(ttl=60)
def get_cached_company_sheet(config):
    return sheets.get_company_sheet(config).get_all_records()


@st.cache_data(ttl=60)  # cache for 60 seconds
def get_cached_scheduled_messages(config):
    return sheets.get_cached_scheduled_messages(config)


def save_collateral_entry(entry):
    os.makedirs(os.path.dirname(COLLATERAL_CONFIG), exist_ok=True)
    if os.path.exists(COLLATERAL_CONFIG):
        with open(COLLATERAL_CONFIG, "r") as f:
            data = yaml.safe_load(f) or []
    else:
        data = []

    for existing in data:
        if existing.get('name', '').strip().lower() == entry['name'].strip().lower():
            st.warning(f"⚠️ A collateral named '{entry['name']}' already exists.")
            return

    data.append(entry)
    with open(COLLATERAL_CONFIG, "w") as f:
        yaml.dump(data, f)

def handle_collateral_upload(name, description, industry, asset_type, file=None, url=None):
    code = uuid.uuid4().hex[:8]
    os.makedirs(COLLATERAL_DIR, exist_ok=True)
    if file:
        filename = f"{code}_{file.name}"
        save_path = os.path.join(COLLATERAL_DIR, filename)
        with open(save_path, "wb") as f:
            f.write(file.read())
        entry = {
            "code": code,
            "name": name,
            "type": "pdf",
            "path": save_path,
            "industry": industry,
            "asset_type": asset_type,
            "description": description
        }
    else:
        entry = {
            "code": code,
            "name": name,
            "type": "link",
            "url": url,
            "industry": industry,
            "asset_type": asset_type,
            "description": description
        }
    save_collateral_entry(entry)
    return entry

def get_collaterals():
    if not os.path.exists(COLLATERAL_CONFIG):
        return []
    with open(COLLATERAL_CONFIG, "r") as f:
        collaterals = yaml.safe_load(f) or []
        st.markdown("#### 🔍 Debug: Loaded Collateral Config")
        st.code(yaml.dump(collaterals), language="yaml")
        return collaterals

config = load_config()
today = datetime.today().date()
st.success(today)



st.title("📈 Automated BDR Pipeline")

with st.expander("📁 Files in collateral/ folder", expanded=False):
    try:
        if not os.path.exists(COLLATERAL_DIR):
            st.info("📭 No files found. The collateral/ folder is empty.")
        else:
            files = os.listdir(COLLATERAL_DIR)
            if not files:
                st.info("📭 No files found in collateral/")
            else:
                for f in sorted(files):
                    file_path = os.path.join(COLLATERAL_DIR, f)
                    file_size_kb = os.path.getsize(file_path) / 1024
                    st.markdown(f"📎 `{f}` — `{file_size_kb:.1f} KB`")
    except Exception as e:
        st.error(f"❌ Error reading folder: {e}")

with st.expander("📎 Upload New Collateral"):
    col_type = st.selectbox("Type", ["PDF", "Smart Link"])
    name = st.text_input("Title")
    description = st.text_area("Short description for prompt/context")

    industry = st.selectbox("Industry or Theme", [
        "general",
        "automotive_retail",
        "healthcare",
        "financial_services",
        "manufacturing",
        "education",
        "telecommunications",
        "logistics_supply_chain",
        "legal_compliance",
        "cybersecurity",
        "cross_industry"
    ])

    asset_type = st.selectbox("Asset Type", [
        "case_study", "whitepaper", "video_demo", "one_pager", "deck", "benchmark"
    ])

    file = url = None
    if col_type == "PDF":
        file = st.file_uploader("Upload PDF", type="pdf")
    else:
        url = st.text_input("Paste Smart Link URL")

    if st.button("💾 Save Collateral"):
        if (file or url) and name and description:
            entry = handle_collateral_upload(name, description, industry, asset_type, file, url)
            st.success(f"✅ Collateral saved: {entry['name']}")
        else:
            st.warning("⚠️ Please fill all required fields.")

# -------------------------
# ⚙️ Configuration Section
# -------------------------
with st.expander("⚙️ Configuration"):
    linkedin_user = st.text_input("LinkedIn Username", value=config.get("linkedin", {}).get("username", ""))
    linkedin_pass = st.text_input("LinkedIn Password", type="password")

    searches_raw = st.text_area("SalesNav Searches (name|url per line)", value="\n".join([f"{s['name']}|{s['url']}" for s in config.get("linkedin", {}).get("searches", [])]))

    new_list_url = st.text_input('Lead List URL (from SalesNav)', value=config.get('linkedin', {}).get('lists', {}).get('new_leads_url', ''))
    new_list_name = st.text_input('Lead List Name (optional if URL is provided)', value=config.get('linkedin', {}).get('lists', {}).get('new_leads', ''))
    invited_list = st.text_input('Invited List Name', value=config.get('linkedin', {}).get('lists', {}).get('invited', ''))
    connected_list = st.text_input('Connected List Name', value=config.get('linkedin', {}).get('lists', {}).get('connected', ''))
    bulk_search_url = st.text_input('SalesNav Search URL to Add 100 Leads', '')

    hub_key = st.text_input("HubSpot API Key", type="password", value=config.get("hubspot", {}).get("api_key", ""))
    hf_token = st.text_input("HuggingFace Token", type="password", value=config.get("huggingface", {}).get("token", ""))
    hf_model = st.text_input("HF Model", value=config.get("huggingface", {}).get("model", "meta-llama/Llama-2-7b-chat-hf"))

    # Load Ollama models from config
    ollama_models_config = config.get("ollama", {}).get("models", [])
    if not ollama_models_config:
        st.warning("⚠️ No Ollama models found in config.yaml → ollama.models. Please check the config file.")
        ollama_models_config = ["mistral", "llama3", "deepseek"]

    default_model = config.get("ollama", {}).get("model", ollama_models_config[0] if ollama_models_config else "mistral")
    model_selection = st.selectbox("LLM Model (Ollama)", ollama_models_config, index=ollama_models_config.index(default_model) if default_model in ollama_models_config else 0)

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
                    'new_leads': new_list_name,
                    'new_leads_url': new_list_url,
                    'invited': invited_list,
                    'connected': connected_list
                }
            },
            'hubspot': {'api_key': hub_key},
            'huggingface': {'token': hf_token, 'model': hf_model},
            'ollama': {
                'model': model_selection,
                'models': ollama_models_config
            },
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
        load_config.clear()
        config = load_config()
        st.success("✅ Configuration saved.")



# -------------------------
# 🚀 Action Buttons
# -------------------------
st.markdown("---")
if st.button("🔐 Manual Login to LinkedIn"):
    try:
        pw, ctx = manual_login()
        st.session_state["pw"] = pw
        st.session_state["context"] = ctx
        st.success("✅ Logged in. Browser context saved.")
    except Exception as e:
        st.error(f"❌ Login failed: {e}")

if st.button('📅 Add Search to Lead List'):
    try:
        if not bulk_search_url or (not new_list_url and not new_list_name):
            st.warning("Please provide the search URL and either a list name or URL.")
        else:
            added = add_search_results_to_list(
                search_url=bulk_search_url,
                list_url=new_list_url,
                list_name=new_list_name,
                context=st.session_state.get('context')
            )
            st.success(f"✅ Added {added} leads to list: {new_list_name or new_list_url}")
    except Exception as e:
        st.error(f'❌ Failed to add leads: {e}')

cols = st.columns(5)
if cols[0].button("1. Extract Leads"):
    try:
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

if cols[4].button("5. Enrich Existing Leads"):
    try:
        enrich_missing_leads(config, st.session_state.get("context"))
        st.success("✅ Lead enrichment complete.")
    except Exception as e:
        st.error(f"❌ Enrichment failed: {e}")

if st.button("6. Push Reporting Metrics"):
    try:
        push_daily_metrics()
        st.success("✅ Metrics pushed.")
    except Exception as e:
        st.error(f"❌ Reporting failed: {e}")

# -------------------------
# 📊 Status Dashboard
# -------------------------
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

# -------------------------
# 🧠 Industry Bucket Mapping Section
# -------------------------
with st.expander("🧠 Enrich Leads with Industry Buckets (Live Preview Only)"):
    cfg = load_config()

# Button to trigger live preview of enriched leads
    if st.button("🔁 Enrich All Leads with Industry Buckets (Preview Only)"):
        try:
            leads, _ = sheets.get_all_leads(cfg)
            company_sheet = sheets.get_cached_company_sheet(cfg)
            company_map = {c["company_id"]: c for c in company_sheet.get_all_records()}

            reverse_map, default_bucket = load_bucket_mapping()
            enriched_preview = []

            for lead in leads:
                # Try lead.industry first, then fallback to company.industry
                industry = lead.get("industry", "")
                if not industry:
                    company = company_map.get(lead.get("company_id"))
                    industry = company.get("industry", "") if company else ""

                # Bucket mapping
                bucket = get_industry_bucket(industry.strip(), reverse_map, default_bucket)
                enriched_preview.append({
                    "name": lead.get("name"),
                    "company": lead.get("company"),
                    "industry": industry,
                    "industry_bucket": bucket
                })

            # Show enriched preview
            st.success(f"✅ Previewed {len(enriched_preview)} leads with their mapped buckets.")
            st.dataframe(enriched_preview)

        except Exception as e:
            st.error(f"❌ Enrichment failed: {e}")

    # Show the actual industry → bucket mapping from config
    try:
        reverse_map, default_bucket = load_bucket_mapping()
        bucket_list = defaultdict(list)
        for industry, bucket in reverse_map.items():
            bucket_list[bucket].append(industry)

        st.markdown("### 📘 Current Industry to Bucket Mapping")
        st.code(yaml.dump(dict(bucket_list), sort_keys=False), language="yaml")

    except Exception as e:
        st.error(f"❌ Failed to load bucket mapping: {e}")

# -------------------------
# 📬 Auto-Schedule Messages
# -------------------------
st.title("📬 Auto-Schedule Messages")

# Preview mode toggle
preview_mode = st.checkbox("🕵️ Preview Only (No Messages Will Be Saved)", value=True)

# Button state flag
if "schedule_clicked" not in st.session_state:
    st.session_state.schedule_clicked = False

with st.expander("⚙️ Message Sequence Configuration", expanded=True):

    try:
        message_library = get_cached_message_library(config)
        approved_msgs = [m for m in message_library if m.get("status") == "approved"]
        all_stages = sorted(set([m["stage"] for m in approved_msgs]))
    except Exception as e:
        st.error(f"❌ Failed to load message library: {e}")
        all_stages = ["intro", "value", "collateral", "nurture", "news", "knowledge", "friday_touch", "cta"]

    # Message stage selection
    st.subheader("🧩 Message Types")
    default_stages = [s for s in ["intro", "value", "collateral", "nurture", "news", "knowledge", "friday_touch", "cta"] if s in all_stages]
    selected_stages = st.multiselect(
        "Select message stages to include", options=all_stages, default=default_stages,
        help="Only these message stages will be considered for scheduling."
    )

    # Day gaps between stages
    st.subheader("⏱️ Time Gaps")
    day_gaps = {}
    for stage in selected_stages:
        day_gaps[stage] = st.number_input(
            f"Gap after {stage}", min_value=0, value=4,
            help=f"Number of days to wait after a {stage} message before sending the next one."
        )

    # Message limits
    st.subheader("🔢 Limits")
    max_per_lead = st.slider("Max messages per lead", 1, 10, 10)
    max_per_stage = {}
    for stage in selected_stages:
        default_value = 2 if stage == "collateral" else 1
        max_per_stage[stage] = st.number_input(
            f"Max {stage} messages", min_value=0, value=default_value, key=f"max_{stage}"
        )

    # Industry targeting
    st.subheader("🏭 Industry Filter")
    industry_buckets = [
        "general", "financial_services", "education", "manufacturing",
        "healthcare", "telecommunications", "automotive_retail",
        "logistics_supply_chain", "cybersecurity", "legal_compliance", "cross_industry"
    ]
    selected_industries = st.multiselect(
        "Restrict to these industries", options=industry_buckets,
        help="Leave empty to include all industries."
    )

    # Message ID exclusion
    st.subheader("🛑 Exclude Specific Messages")
    excluded_ids_input = st.text_input("Excluded message IDs (comma-separated)")
    excluded_ids = [x.strip() for x in excluded_ids_input.split(",") if x.strip()]

    # Filter config
    filters = {
        "include_stages": selected_stages,
        "day_gaps": day_gaps,
        "max_messages_per_lead": max_per_lead,
        "max_per_stage": max_per_stage,
        "industries": selected_industries,
        "excluded_ids": excluded_ids
    }

    # Initialize scheduler
    scheduled_messages = get_cached_scheduled_messages(config)
    lead_data = get_cached_leads(config)
    company_sheet = get_cached_company_sheet(config)
    scheduler = MessageScheduler(
        config,
        filters,
        scheduled_messages=scheduled_messages,
        leads=lead_data,
        company_sheet=company_sheet
    )

# Layout: preview and schedule buttons
col1, col2 = st.columns(2)

# Preview action
if col1.button("🔍 Preview Auto-Scheduled Messages"):
    try:
        preview_data = scheduler.auto_schedule(preview=True)
        if preview_data:
            st.session_state["preview_messages"] = preview_data
            st.success(f"✅ Previewed {len(preview_data)} messages.")
            st.dataframe(pd.DataFrame(preview_data))
        else:
            st.session_state["preview_messages"] = []
            st.info("📭 No messages to schedule.")
    except Exception as e:
        st.error(f"❌ Preview failed: {e}")

# Final scheduling action
if not preview_mode:
    if col2.button("📬 Schedule Messages (Save to Sheet)", disabled=st.session_state.schedule_clicked):
        try:
            st.session_state.schedule_clicked = True
            scheduler.auto_schedule(preview=False)
            st.success("✅ Messages scheduled and saved.")
        except Exception as e:
            st.error(f"❌ Scheduling failed: {e}")
        finally:
            st.session_state.schedule_clicked = False

#---------------------
# Schedule Message UI
#---------------------
st.title("📡 Outreach Message Scheduler")

# ===========================
# 📬 SCHEDULED MESSAGES RUNNER
# ===========================
with st.expander("📬 Run Scheduled Messages", expanded=True):
    st.markdown("Send all messages scheduled up to a selected date (including missed ones if needed).")

    col1, col2 = st.columns(2)
    with col1:
        run_date = st.date_input("📅 Schedule For", value=today)
    with col2:
        max_messages = st.number_input("🔢 Max Messages Per Day", min_value=1, max_value=200, value=100)

    backdate = st.checkbox("⏪ Include Missed (Older) Messages")

    if st.button("🚀 Run Scheduler Now"):
        scheduler = MessageScheduler(
            config=config,
            filters={
                "max_messages_per_day": max_messages,
                "backdate": backdate
            },
            mode="send_only"  # skip company sheet
        )
    with st.spinner("Running message scheduler..."):
        results = scheduler.run_scheduler(for_date=run_date)

    st.success("✅ Scheduler complete!")
    st.markdown("### Results")
    for lid, mid, status in results:
        st.write(f"• `{lid}` | `{mid}` → {status}")


# ===========================
# 🔥 FORCE SEND MESSAGES
# ===========================
with st.expander("🔥 Force Send Messages"):
    st.markdown("Manually send messages based on filters and a selected message template.")

    # --- Filter Section ---
    industry = st.text_input("🏭 Filter by Industry (optional)")
    company = st.text_input("🏢 Filter by Company (optional)")
    location = st.text_input("📍 Filter by Location (optional)")

    # --- Template Selection ---
    st.divider()
    st.markdown("### ✉️ Select Message Template")
    message_library = get_cached_message_library(config)
    filtered_templates = [m for m in message_library if m.get("status") == "approved"]

    if not filtered_templates:
        st.warning("No approved message templates found.")
    else:
        template_options = [f"{m['message_id']} - {m['template_text'][:50]}..." for m in filtered_templates]
        selected_index = st.selectbox("Choose a Template", range(len(template_options)), format_func=lambda i: template_options[i])
        selected_template = filtered_templates[selected_index]

        scheduled_date = st.date_input("📅 Schedule Date", value=today)

        if st.button("⚠️ Force Send"):
            st.info("🚧 Force send logic not wired yet — next step: implement `force_send()` using selected filters and template.")



# -------------------------
# ✉️ NEW LEAD MESSAGING UI (Enhanced)
# -------------------------
st.markdown("### ✉️ Generate Message for Selected Lead")

if st.button("🔄 Search Leads & Companies"):
    leads, _ = sheets.get_all_leads(config)
    company_sheet = sheets.get_company_sheet(config)
    company_records = company_sheet.get_all_records()
    company_details = [dict(row) for row in company_records if row]
    st.session_state["leads"] = leads
    st.session_state["company_details"] = company_details

if "leads" in st.session_state and "company_details" in st.session_state:
    leads = st.session_state["leads"]
    company_details = st.session_state["company_details"]

    # Filters
    with st.expander("🔍 Filter Leads"):
        unique_industries = sorted(set([c.get("industry") for c in company_details if c.get("industry")]))
        selected_industries = st.multiselect("Industry", options=unique_industries, key="industry_filter")

        if selected_industries:
            filtered_company_ids = {c.get("company_id") for c in company_details if c.get("industry") in selected_industries}
            company_details = [c for c in company_details if c.get("company_id") in filtered_company_ids]
            leads = [l for l in leads if l.get("company_id") in filtered_company_ids]

        unique_companies = sorted(set([c.get("company_name") for c in company_details if c.get("company_name")]))
        company_filter = st.multiselect("Company (from industry filter above)", options=unique_companies, key="company_filter")
        connection_filter = st.selectbox("Connection Level", ["All", "1st", "2nd", "3rd+"], index=0)

    filtered_leads = leads[:]
    if company_filter:
        filtered_leads = [l for l in filtered_leads if l.get("company") in company_filter or l.get("company_name") in company_filter]
    if selected_industries:
        valid_company_ids = {c.get("company_id") for c in company_details if c.get("industry") in selected_industries}
        filtered_leads = [l for l in filtered_leads if l.get("company_id") in valid_company_ids]
    if connection_filter != "All":
        connection_lookup = {"1st": ["1st"], "2nd": ["2nd"], "3rd+": ["3rd", "3rd+", "3rd degree"]}
        accepted = connection_lookup.get(connection_filter, [])
        filtered_leads = [l for l in filtered_leads if l.get("connection", "").strip().lower() in [v.lower() for v in accepted]]

    if filtered_leads:
        page_size = 20
        start = st.number_input("Start Index", min_value=0, max_value=max(len(filtered_leads)-1, 0), value=0, step=page_size, key="start_index")
        lead_names = [f"{l['name']} – {l['title']} @ {l.get('company') or l.get('company_name', '')}" for l in filtered_leads[start:start+page_size]]
        selected = st.selectbox("Select a lead", options=lead_names)
        selected_index = lead_names.index(selected)
        selected_lead = filtered_leads[start + selected_index]

        st.markdown("---")
        st.markdown(f"#### {selected_lead['name']} — {selected_lead['title']} @ {selected_lead['company']}")
        fallback_industry = next((c.get("industry") for c in company_details if c.get("company_id") == selected_lead.get("company_id")), "N/A")
        st.caption(f"Industry: {fallback_industry} | Connection: {selected_lead.get('connection_level', 'N/A')} | Last message: {selected_lead.get('last_message_date', 'N/A')}")

        name = st.text_input("Name", selected_lead.get("name", ""), key="name_input")
        title = st.text_input("Title", selected_lead.get("title", ""), key="title_input")
        company = st.text_input("Company", selected_lead.get("company", ""), key="company_input")
        fallback_industry = next((c.get("industry") for c in company_details if c.get("company_id") == selected_lead.get("company_id")), "")
        selected_lead["industry"] = selected_lead.get("industry") or fallback_industry
        industry = st.text_input("Industry", selected_lead["industry"], key="industry_input")
        chat = st.text_area("Chat History", selected_lead.get("chat_history", ""))
        signals = st.text_area("LeadIQ Signals", selected_lead.get("leadiq", ""))

        company_id = selected_lead.get("company_id")
        company_info = next((c.get("description") for c in company_details if c.get("company_id") == company_id), "")
        pdf = st.text_area("Company Details", company_info)
        category = st.selectbox("Message Category", list(config.get("categories", {}).keys()), key="message_category")
        use_dynamic = st.checkbox("Use AI-Powered Dynamic Prompting", value=True)

        if st.button("Generate Message"):
            test_lead = {
                "name": name, "title": title, "company": company, "industry": industry,
                "chat_history": chat, "leadiq": signals, "pdf_summary": pdf,
                "category": category
            }
            if use_dynamic:
                message = generate_dynamic_message(test_lead, model_selection, config)
            else:
                message = generate_connection(test_lead, model_selection, config)
            st.session_state["generated_message"] = message

    if "generated_message" in st.session_state:
        st.text_area("Generated Message", st.session_state["generated_message"], height=140)

        if st.button("Send Message"):
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            selected_lead["last_message_date"] = now
            sheets.update_lead_message_date(config, selected_lead, now)
            st.success(f"✅ Message sent to {name} (Last messaged on {now})")

        if st.button("🕒 Schedule Message"):
            scheduled_data = {
                "linkedin_id": selected_lead.get("linkedin_id", ""),
                "name": name,
                "title": title,
                "company": company,
                "industry": industry,
                "message": st.session_state["generated_message"],
                "category": category,
                "scheduled_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "scheduled"
            }
            try:
                sheets.append_scheduled_message(config, scheduled_data)
                st.success("✅ Message scheduled successfully.")
            except Exception as e:
                st.error(f"❌ Failed to schedule message: {e}")
    else:
        st.warning("⚠️ No leads match your current filters. Try adjusting filters or reload.")
else:
    st.info("Click '🔄 Load Leads & Company Details' to begin.")

# -------------------------
# 🗓️ View & Manage Scheduled Messages
# -------------------------
st.markdown("### 🗓️ Scheduled Messages Queue")

try:
    sheet = sheets._client(config).open_by_key(config['gsheets']['spreadsheet_id']).worksheet("ScheduledMessages")
    records = sheet.get_all_records()

    if not records:
        st.info("📭 No scheduled messages yet.")
    else:
        df = pd.DataFrame(records)

        # 1. Stats Summary
        col1, col2, col3 = st.columns(3)
        col1.metric("📬 Total", len(df))
        col2.metric("✅ Sent", (df["status"] == "sent").sum())
        col3.metric("📅 Upcoming", (df["status"] == "scheduled").sum())

        # 2. Filters
        with st.expander("🔍 Filter Options", expanded=False):
            status_filter = st.selectbox("Status", ["All", "scheduled", "sent"])
            search_term = st.text_input("Search by Name or Company")
            page_size = st.selectbox("Messages per page", [10, 20, 50, 100], index=1)

        # 3. Filtering
        filtered_df = df.copy()
        if status_filter != "All":
            filtered_df = filtered_df[filtered_df["status"] == status_filter]
        if search_term:
            filtered_df = filtered_df[
                filtered_df["name"].str.lower().str.contains(search_term.lower()) |
                filtered_df["company"].str.lower().str.contains(search_term.lower())
                ]

        # 4. Pagination
        total_records = len(filtered_df)
        total_pages = max(1, (total_records - 1) // page_size + 1)
        page = st.number_input("Page", min_value=1, max_value=total_pages, step=1)
        start, end = (page - 1) * page_size, page * page_size
        paged_df = filtered_df.iloc[start:end]

        # 5. Display Table
        st.dataframe(
            paged_df[[
                "rank", "name", "company", "scheduled_for",
                "message_type", "status", "industry_bucket"
            ]].reset_index(drop=True),
            use_container_width=True,
            height=400
        )

        # 6. Action Buttons for each record
        for _, row in paged_df.iterrows():
            with st.expander(f"📨 Message: {row['name']} — {row['company']}"):
                st.code(row["message_text"], language="text")

                row_index = int(row.get("rank", 0)) + 1
                msg_id = row.get("message_id", "")
                lid = row.get("linkedin_id", "")
                col1, col2 = st.columns(2)

                if col1.button("✅ Mark as Sent", key=f"sent_{lid}_{msg_id}_{row_index}"):
                    sheet.update_cell(row_index, 7, "sent")
                    st.success(f"✅ Marked sent: {row['name']}")

                if col2.button("🗑️ Delete", key=f"del_{lid}_{msg_id}_{row_index}"):
                    sheet.delete_rows(row_index)
                    st.warning(f"🗑️ Deleted message for {row['name']}")

except Exception as e:
    st.error(f"❌ Failed to load scheduled messages: {e}")
