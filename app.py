
import os
import uuid
import yaml
import time
import streamlit as st
import pandas as pd

from datetime import datetime
from collections import defaultdict

from modules import sheets
from modules.login import manual_login
from modules.salesnav_extract import extract_all_searches
from modules.hubspot_sync import sync_hubspot
from modules.message_gen import (
    generate_connection,
    generate_followup,
    generate_dynamic_message,
)
from modules.outreach import send_invites, process_followups
from modules.salesnav_lists import add_search_results_to_list
from modules.reporting import push_daily_metrics
from modules.enrich_leads import enrich_missing_leads
from modules.industry_mapper import load_bucket_mapping, get_industry_bucket
from modules.scheduler import MessageScheduler


# =========================================================
# Page + Theme
# =========================================================

st.set_page_config(
    page_title="Growth Agent",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
:root{
  --ga-black:#000000;
  --ga-white:#ffffff;
  --ga-pewter:#fea34f;
  --ga-silver:#fea14f;

  --ga-sapphire:#2fb36d;
  --ga-impact:#2cd1cc;
  --ga-kiosk:#2fb36d;
  --ga-violet:#9381fb;
  --ga-iris:#33b32f;

  --ga-border:rgba(0,0,0,0.08);
  --ga-soft:rgba(0,0,0,0.03);
}

.stApp{background:var(--ga-white);} 
.block-container{padding-top:1.5rem; padding-bottom:2rem; max-width: 1400px;}

/* Headings */
h1,h2,h3,h4{color:var(--ga-black);} 

/* Buttons */
.stButton>button{
  border-radius: 10px;
  border: 1px solid var(--ga-border);
  background: var(--ga-sapphire);
  color: var(--ga-white);
  font-weight: 650;
  padding: 0.55rem 1rem;
  transition: 0.15s ease-in-out;
}
.stButton>button:hover{
  background: var(--ga-iris);
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(32,81,159,0.22);
}

/* Inputs */
[data-baseweb="input"] > div,
[data-baseweb="textarea"] > div,
[data-baseweb="select"] > div{
  border-radius: 12px !important;
}

/* Expanders */
details{
  border-radius: 14px;
  background: rgba(255,255,255,0.9);
  border: 1px solid var(--ga-border);
}

/* Metrics */
[data-testid="stMetric"]{
  border: 1px solid var(--ga-border);
  border-radius: 14px;
  padding: 0.85rem;
  background: var(--ga-silver);
}

/* Tables */
[data-testid="stDataFrame"]{
  border: 1px solid var(--ga-border);
  border-radius: 14px;
}

/* Divider */
hr{margin: 1.25rem 0;}

/* Hero */
.ga-hero{
  padding: 1.15rem 1.25rem;
  border-radius: 18px;
  background: var(--ga-white);
  border: 1px solid var(--ga-border);
  box-shadow: 0 8px 26px rgba(0,0,0,0.05);
  margin-bottom: 1.25rem;
}
.ga-title{font-size: 2.05rem; font-weight: 800; letter-spacing:-0.02em; margin:0;}
.ga-sub{color: var(--ga-pewter); margin: 0.2rem 0 0 0;}
.ga-chip{
  display:inline-flex;
  align-items:center;
  gap:0.4rem;
  padding: 0.25rem 0.6rem;
  border-radius: 999px;
  border: 1px solid var(--ga-border);
  background: rgba(0,0,0,0.03);
  color: var(--ga-pewter);
  font-size: 0.86rem;
}
</style>
""",
    unsafe_allow_html=True,
)


def hero(title: str, subtitle: str, chip: str | None = None):
    chip_html = f'<span class="ga-chip">{chip}</span>' if chip else ''
    st.markdown(
        f"""
<div class="ga-hero">
  <div style="display:flex; align-items:center; justify-content:space-between; gap:0.75rem;">
    <div>
      <div class="ga-title">{title}</div>
      <p class="ga-sub">{subtitle}</p>
    </div>
    <div>{chip_html}</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


# =========================================================
# Constants / Cache / Collateral
# =========================================================

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


@st.cache_data(ttl=60)
def get_cached_message_library(config):
    return sheets.get_cached_message_library(config)


@st.cache_data(ttl=60)
def get_cached_leads(config):
    return sheets.get_cached_leads(config)


@st.cache_data(ttl=60)
def get_cached_company_sheet(config):
    return sheets.get_company_sheet(config).get_all_records()


@st.cache_data(ttl=60)
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
        if existing.get("name", "").strip().lower() == entry["name"].strip().lower():
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
            "description": description,
        }
    else:
        entry = {
            "code": code,
            "name": name,
            "type": "link",
            "url": url,
            "industry": industry,
            "asset_type": asset_type,
            "description": description,
        }

    save_collateral_entry(entry)
    return entry


def get_collaterals():
    if not os.path.exists(COLLATERAL_CONFIG):
        return []
    with open(COLLATERAL_CONFIG, "r") as f:
        collaterals = yaml.safe_load(f) or []
        return collaterals


# =========================================================
# App State
# =========================================================

config = load_config()
today = datetime.today().date()

hero(
    title="Growth Agent",
    subtitle=f"Relationship-led Revenue Engine • Executive White UI • {today}",
    chip="Hybrid",
)


# =========================================================
# Navigation
# =========================================================

tabs = st.tabs(
    [
        "🛰️ Command Center",
        "⚡ Execution",
        "📎 Assets",
        "🧬 Campaign Studio",
        "🚦 Scheduler",
        "✉️ Message Lab",
        "🗂️ Queue",
        "⚙️ Settings",
    ]
)


# =========================================================
# 🛰️ Command Center
# =========================================================

with tabs[0]:

    st.markdown("## Command Center")

    try:
        cfg = load_config()
        leads, _ = sheets.get_all_leads(cfg)
        meta_sheet = sheets.get_metadata_sheet(cfg)

        headers = meta_sheet.row_values(1)
        values = meta_sheet.row_values(2)
        meta = dict(zip(headers, values))

        # -------------------------
        # Aggregate
        # -------------------------
        status_counts = {}
        for l in leads:
            status = l.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        invited = status_counts.get("invited", 0)
        connected = status_counts.get("connected", 0)
        in_progress = status_counts.get("in_progress", 0)
        new = status_counts.get("new", 0)

        total_pipeline = invited + connected + in_progress + new
        connect_rate = round((connected / invited) * 100, 1) if invited else 0

        # =====================================================
        # 🎯 North Star KPI (Dominant)
        # =====================================================

        st.markdown("### Pipeline Strength")

        k1, k2 = st.columns([2, 1])

        with k1:
            st.markdown(
                f"""
                <div style="
                    padding:2rem;
                    border-radius:18px;
                    border:1px solid rgba(0,0,0,0.08);
                    background:--ga-iris">
                    <div style="font-size:0.9rem;color:#6b7280;">Active Pipeline</div>
                    <div style="font-size:3rem;font-weight:800;margin-top:0.5rem;">
                        {total_pipeline}
                    </div>
                    <div style="color:#6b7280;margin-top:0.4rem;">
                        {connected} connections • {in_progress} active conversations
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

        with k2:
            st.metric("Connect Rate", f"{connect_rate}%")
            st.metric("Invites Sent", invited)
            st.metric("New Leads", new)

        # =====================================================
        # 📊 Funnel
        # =====================================================

        st.markdown("### Pipeline Visualization")
        funnel_df = pd.DataFrame({
            "Stage": ["Invited", "Connected", "In Progress"],
            "Count": [invited, connected, in_progress]
        })

        # -------------------------
        # Visualization Controls
        # -------------------------

        col1, col2, col3 = st.columns(3)

        with col1:
            chart_type = st.selectbox(
                "Chart Type",
                ["Bar", "Line", "Area", "Table"],
                key="viz_chart_type"
            )

        with col2:
            sort_option = st.selectbox(
                "Sort By",
                ["Default Order", "Highest to Lowest", "Lowest to Highest"],
                key="viz_sort"
            )

        with col3:
            compact_view = st.checkbox("Compact View", key="viz_compact")

        # -------------------------
        # Sorting Logic
        # -------------------------

        if sort_option == "Highest to Lowest":
            funnel_df = funnel_df.sort_values("Count", ascending=False)
        elif sort_option == "Lowest to Highest":
            funnel_df = funnel_df.sort_values("Count", ascending=True)

        # -------------------------
        # Rendering Logic
        # -------------------------

        if chart_type == "Bar":
            st.bar_chart(funnel_df.set_index("Stage"))
        elif chart_type == "Line":
            st.line_chart(funnel_df.set_index("Stage"))
        elif chart_type == "Area":
            st.area_chart(funnel_df.set_index("Stage"))
        elif chart_type == "Table":
            st.dataframe(funnel_df, use_container_width=True)

        # -------------------------
        # Compact Mode (Optional Insight)
        # -------------------------

        if not compact_view:
            total = invited if invited else 1
            conv_rate = round((connected / total) * 100, 1)

            st.markdown("---")
            st.markdown(
                f"""
                <div style="padding:1rem;border-radius:12px;border:1px solid rgba(0,0,0,0.06);">
                <strong>Conversion Insight:</strong><br>
                {connected} of {invited} invites converted → <strong>{conv_rate}%</strong>
                </div>
                """,
                unsafe_allow_html=True
            )


    # =====================================================
        # 🧠 Intelligence Summary
        # =====================================================

        st.markdown("### Insight")

        if connect_rate < 10:
            message = "Connection efficiency is below benchmark. Consider refining ICP targeting or messaging precision."
        elif connect_rate > 20:
            message = "Strong connection performance. Increasing invite volume could accelerate pipeline growth."
        else:
            message = "Pipeline performance is stable with room for incremental optimization."

        st.markdown(
            f"""
            <div style="
                padding:1.5rem;
                border-radius:14px;
                border:1px solid rgba(0,0,0,0.06);
                background:#ffffff;">
                <div style="font-weight:600;margin-bottom:0.4rem;">Operational Intelligence</div>
                <div style="color:#4b5563;">
                    {message}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # =====================================================
        # 🕒 Operational Activity
        # =====================================================

        st.markdown("### System Activity")

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Last Extract", meta.get("last_extract") or "—")
        m2.metric("Last Sync", meta.get("last_sync") or "—")
        m3.metric("Last Outreach", meta.get("last_outreach") or "—")
        m4.metric("Last Follow-up", meta.get("last_followup") or "—")
        m5.metric("Last Report", meta.get("last_report") or "—")

    except Exception as e:
        st.error(f"Failed to load Command Center: {e}")

# =========================================================
# ⚡ Execution
# =========================================================

with tabs[1]:
    st.subheader("⚡ Execution")

    colA, colB = st.columns([1, 2])
    with colA:
        if st.button("🔐 Manual Login to LinkedIn", key="exec_login"):
            try:
                pw, ctx = manual_login()
                st.session_state["pw"] = pw
                st.session_state["context"] = ctx
                st.success("✅ Logged in. Browser context saved.")
            except Exception as e:
                st.error(f"❌ Login failed: {e}")

    with colB:
        st.caption("Run these daily actions to keep pipeline moving.")

    st.markdown("---")

    g1 = st.columns(3)
    g2 = st.columns(3)

    if g1[0].button("1) Extract Leads", key="exec_extract"):
        try:
            extract_all_searches(st.session_state.get("context"))
            st.success("✅ Extraction complete.")
        except Exception as e:
            st.error(f"❌ Extraction failed: {e}")

    if g1[1].button("2) Sync to HubSpot", key="exec_sync"):
        try:
            sync_hubspot()
            st.success("✅ Sync complete.")
        except Exception as e:
            st.error(f"❌ Sync failed: {e}")

    if g1[2].button("3) Send Invites", key="exec_invites"):
        try:
            send_invites(st.session_state.get("context"))
            st.success("✅ Invites sent.")
        except Exception as e:
            st.error(f"❌ Invite sending failed: {e}")

    if g2[0].button("4) Process Follow-Ups", key="exec_followups"):
        try:
            process_followups(st.session_state.get("context"))
            st.success("✅ Follow-ups processed.")
        except Exception as e:
            st.error(f"❌ Follow-up failed: {e}")

    if g2[1].button("5) Enrich Existing Leads", key="exec_enrich"):
        try:
            enrich_missing_leads(config, st.session_state.get("context"))
            st.success("✅ Lead enrichment complete.")
        except Exception as e:
            st.error(f"❌ Enrichment failed: {e}")

    if g2[2].button("6) Push Reporting Metrics", key="exec_metrics"):
        try:
            push_daily_metrics()
            st.success("✅ Metrics pushed.")
        except Exception as e:
            st.error(f"❌ Reporting failed: {e}")


# =========================================================
# 📎 Assets
# =========================================================

with tabs[2]:
    st.subheader("📎 Assets")

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

    with st.expander("📎 Upload New Collateral", expanded=True):
        col_type = st.selectbox("Type", ["PDF", "Smart Link"], key="asset_type")
        name = st.text_input("Title", key="asset_title")
        description = st.text_area("Short description for prompt/context", key="asset_desc")

        industry = st.selectbox(
            "Industry or Theme",
            [
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
                "cross_industry",
            ],
            key="asset_industry",
        )

        asset_type = st.selectbox(
            "Asset Type",
            ["case_study", "whitepaper", "video_demo", "one_pager", "deck", "benchmark"],
            key="asset_kind",
        )

        file = url = None
        if col_type == "PDF":
            file = st.file_uploader("Upload PDF", type="pdf", key="asset_pdf")
        else:
            url = st.text_input("Paste Smart Link URL", key="asset_url")

        if st.button("💾 Save Collateral", key="asset_save"):
            if (file or url) and name and description:
                entry = handle_collateral_upload(name, description, industry, asset_type, file, url)
                st.success(f"✅ Collateral saved: {entry['name']}")
            else:
                st.warning("⚠️ Please fill all required fields.")


# =========================================================
# 🧬 Campaign Studio (Auto-Schedule + Industry Preview)
# =========================================================

with tabs[3]:
    st.subheader("🧬 Campaign Studio")

    preview_mode = st.checkbox("🕵️ Preview Only (No Messages Will Be Saved)", value=True, key="cs_preview")

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

        st.subheader("🧩 Message Types")
        default_stages = [
            s
            for s in ["intro", "value", "collateral", "nurture", "news", "knowledge", "friday_touch", "cta"]
            if s in all_stages
        ]
        selected_stages = st.multiselect(
            "Select message stages to include",
            options=all_stages,
            default=default_stages,
            help="Only these message stages will be considered for scheduling.",
            key="cs_stages",
        )

        st.subheader("⏱️ Time Gaps")
        day_gaps = {}
        for stage in selected_stages:
            day_gaps[stage] = st.number_input(
                f"Gap after {stage}",
                min_value=0,
                value=4,
                help=f"Days to wait after a {stage} message before next one.",
                key=f"cs_gap_{stage}",
            )

        st.subheader("🔢 Limits")
        max_per_lead = st.slider("Max messages per lead", 1, 10, 10, key="cs_max_per_lead")
        max_per_stage = {}
        for stage in selected_stages:
            default_value = 2 if stage == "collateral" else 1
            max_per_stage[stage] = st.number_input(
                f"Max {stage} messages",
                min_value=0,
                value=default_value,
                key=f"cs_max_{stage}",
            )

        st.subheader("🏭 Industry Filter")
        industry_buckets = [
            "general",
            "financial_services",
            "education",
            "manufacturing",
            "healthcare",
            "telecommunications",
            "automotive_retail",
            "logistics_supply_chain",
            "cybersecurity",
            "legal_compliance",
            "cross_industry",
        ]
        selected_industries = st.multiselect(
            "Restrict to these industries",
            options=industry_buckets,
            help="Leave empty to include all industries.",
            key="cs_industry",
        )

        st.subheader("🛑 Exclude Specific Messages")
        excluded_ids_input = st.text_input("Excluded message IDs (comma-separated)", key="cs_excluded")
        excluded_ids = [x.strip() for x in excluded_ids_input.split(",") if x.strip()]

        filters = {
            "include_stages": selected_stages,
            "day_gaps": day_gaps,
            "max_messages_per_lead": max_per_lead,
            "max_per_stage": max_per_stage,
            "industries": selected_industries,
            "excluded_ids": excluded_ids,
        }

        scheduled_messages = get_cached_scheduled_messages(config)
        lead_data = get_cached_leads(config)
        company_sheet = get_cached_company_sheet(config)
        scheduler = MessageScheduler(
            config,
            filters,
            scheduled_messages=scheduled_messages,
            leads=lead_data,
            company_sheet=company_sheet,
        )

    c1, c2 = st.columns(2)

    if c1.button("🔍 Preview Auto-Scheduled Messages", key="cs_preview_btn"):
        try:
            preview_data = scheduler.auto_schedule(preview=True)
            st.session_state["preview_messages"] = preview_data or []
            if preview_data:
                st.success(f"✅ Previewed {len(preview_data)} messages.")
                st.dataframe(pd.DataFrame(preview_data), use_container_width=True)
            else:
                st.info("📭 No messages to schedule.")
        except Exception as e:
            st.error(f"❌ Preview failed: {e}")

    if not preview_mode:
        if c2.button("📬 Schedule Messages (Save to Sheet)", disabled=st.session_state.schedule_clicked, key="cs_save"):
            try:
                st.session_state.schedule_clicked = True
                scheduler.auto_schedule(preview=False)
                st.success("✅ Messages scheduled and saved.")
            except Exception as e:
                st.error(f"❌ Scheduling failed: {e}")
            finally:
                st.session_state.schedule_clicked = False

    st.markdown("---")

    with st.expander("🧠 Enrich Leads with Industry Buckets (Live Preview Only)", expanded=False):
        if st.button("🔁 Enrich All Leads with Industry Buckets (Preview Only)", key="cs_bucket_preview"):
            try:
                cfg = load_config()
                leads, _ = sheets.get_all_leads(cfg)
                company_sheet_obj = sheets.get_company_sheet(cfg)
                company_records = company_sheet_obj.get_all_records()
                company_map = {c.get("company_id"): c for c in company_records if c and c.get("company_id")}

                reverse_map, default_bucket = load_bucket_mapping()
                enriched_preview = []

                for lead in leads:
                    industry = lead.get("industry", "")
                    if not industry:
                        company = company_map.get(lead.get("company_id"))
                        industry = company.get("industry", "") if company else ""

                    bucket = get_industry_bucket(industry.strip(), reverse_map, default_bucket)
                    enriched_preview.append(
                        {
                            "name": lead.get("name"),
                            "company": lead.get("company"),
                            "industry": industry,
                            "industry_bucket": bucket,
                        }
                    )

                st.success(f"✅ Previewed {len(enriched_preview)} leads with their mapped buckets.")
                st.dataframe(pd.DataFrame(enriched_preview), use_container_width=True)

            except Exception as e:
                st.error(f"❌ Enrichment failed: {e}")

        try:
            reverse_map, default_bucket = load_bucket_mapping()
            bucket_list = defaultdict(list)
            for industry, bucket in reverse_map.items():
                bucket_list[bucket].append(industry)

            st.markdown("### 📘 Current Industry → Bucket Mapping")
            st.code(yaml.dump(dict(bucket_list), sort_keys=False), language="yaml")

        except Exception as e:
            st.error(f"❌ Failed to load bucket mapping: {e}")


# =========================================================
# 🚦 Scheduler (Runner + Force Send)
# =========================================================

with tabs[4]:
    st.subheader("🚦 Scheduler")

    with st.expander("📬 Run Scheduled Messages", expanded=True):
        st.markdown("Send messages scheduled up to a selected date (optionally include missed ones).")

        r1, r2 = st.columns(2)
        with r1:
            run_date = st.date_input("📅 Run for date", value=today, key="run_date")
        with r2:
            max_messages = st.number_input("🔢 Max Messages Per Day", min_value=1, max_value=200, value=100, key="run_max")

        backdate = st.checkbox("⏪ Include Missed (Older) Messages", key="run_backdate")

        if st.button("🚀 Run Scheduler Now", key="run_now"):
            try:
                runner = MessageScheduler(
                    config=config,
                    filters={"max_messages_per_day": max_messages, "backdate": backdate},
                    mode="send_only",
                )
                with st.spinner("Running message scheduler..."):
                    results = runner.run_scheduler(for_date=run_date)

                st.success("✅ Scheduler complete!")
                st.markdown("### Results")
                for lid, mid, status in results:
                    st.write(f"• `{lid}` | `{mid}` → {status}")

            except Exception as e:
                st.error(f"❌ Scheduler run failed: {e}")

    with st.expander("🔥 Force Send Messages", expanded=False):
        st.markdown("Manually send messages based on filters and a selected template.")

        industry = st.text_input("🏭 Filter by Industry (optional)", key="force_industry")
        company = st.text_input("🏢 Filter by Company (optional)", key="force_company")
        location = st.text_input("📍 Filter by Location (optional)", key="force_location")

        st.divider()
        st.markdown("### ✉️ Select Message Template")

        try:
            message_library = get_cached_message_library(config)
            filtered_templates = [m for m in message_library if m.get("status") == "approved"]
        except Exception as e:
            filtered_templates = []
            st.error(f"❌ Failed to load message library: {e}")

        if not filtered_templates:
            st.warning("No approved message templates found.")
        else:
            template_options = [f"{m.get('message_id','')} - {str(m.get('template_text',''))[:50]}..." for m in filtered_templates]
            selected_index = st.selectbox(
                "Choose a Template",
                range(len(template_options)),
                format_func=lambda i: template_options[i],
                key="force_template",
            )
            _ = filtered_templates[selected_index]

            _ = st.date_input("📅 Schedule Date", value=today, key="force_date")

            if st.button("⚠️ Force Send", key="force_send"):
                st.info(
                    "🚧 Force send logic not wired yet — next step: implement `force_send()` using selected filters + template."
                )


# =========================================================
# ✉️ Message Lab
# =========================================================

with tabs[5]:
    st.subheader("✉️ Message Lab")

    if st.button("🔄 Search Leads & Companies", key="ml_load"):
        try:
            leads, _ = sheets.get_all_leads(config)
            company_sheet_obj = sheets.get_company_sheet(config)
            company_records = company_sheet_obj.get_all_records()
            company_details = [dict(row) for row in company_records if row]
            st.session_state["leads"] = leads
            st.session_state["company_details"] = company_details
            st.success(f"✅ Loaded {len(leads)} leads.")
        except Exception as e:
            st.error(f"❌ Failed to load leads/companies: {e}")

    if "leads" in st.session_state and "company_details" in st.session_state:
        leads = st.session_state["leads"]
        company_details = st.session_state["company_details"]

        with st.expander("🔍 Filter Leads", expanded=False):
            unique_industries = sorted(
                set([c.get("industry") for c in company_details if c.get("industry")])
            )
            selected_industries = st.multiselect(
                "Industry",
                options=unique_industries,
                key="ml_industry_filter",
            )

            filtered_company_ids = None
            if selected_industries:
                filtered_company_ids = {
                    c.get("company_id")
                    for c in company_details
                    if c.get("industry") in selected_industries
                }

            unique_companies = sorted(
                set([c.get("company_name") for c in company_details if c.get("company_name")])
            )
            company_filter = st.multiselect(
                "Company",
                options=unique_companies,
                key="ml_company_filter",
            )
            connection_filter = st.selectbox(
                "Connection Level",
                ["All", "1st", "2nd", "3rd+"],
                index=0,
                key="ml_conn_filter",
            )

        filtered_leads = leads[:]

        if filtered_company_ids is not None:
            filtered_leads = [l for l in filtered_leads if l.get("company_id") in filtered_company_ids]

        if company_filter:
            filtered_leads = [
                l
                for l in filtered_leads
                if (l.get("company") in company_filter) or (l.get("company_name") in company_filter)
            ]

        if connection_filter != "All":
            connection_lookup = {"1st": ["1st"], "2nd": ["2nd"], "3rd+": ["3rd", "3rd+", "3rd degree"]}
            accepted = [v.lower() for v in connection_lookup.get(connection_filter, [])]
            filtered_leads = [
                l
                for l in filtered_leads
                if l.get("connection", "").strip().lower() in accepted
            ]

        if filtered_leads:
            page_size = 20
            start = st.number_input(
                "Start Index",
                min_value=0,
                max_value=max(len(filtered_leads) - 1, 0),
                value=0,
                step=page_size,
                key="ml_start",
            )

            page_slice = filtered_leads[start : start + page_size]
            lead_names = [
                f"{l.get('name','')} – {l.get('title','')} @ {l.get('company') or l.get('company_name','')}"
                for l in page_slice
            ]

            selected = st.selectbox("Select a lead", options=lead_names, key="ml_select")
            selected_index = lead_names.index(selected)
            selected_lead = page_slice[selected_index]

            st.markdown("---")
            st.markdown(
                f"#### {selected_lead.get('name','')} — {selected_lead.get('title','')} @ {selected_lead.get('company','')}"
            )

            company_id = selected_lead.get("company_id")
            fallback_industry = next(
                (c.get("industry") for c in company_details if c.get("company_id") == company_id),
                "N/A",
            )

            st.caption(
                f"Industry: {fallback_industry} | Connection: {selected_lead.get('connection_level','N/A')} | Last message: {selected_lead.get('last_message_date','N/A')}"
            )

            name = st.text_input("Name", selected_lead.get("name", ""), key="ml_name")
            title = st.text_input("Title", selected_lead.get("title", ""), key="ml_title")
            company = st.text_input("Company", selected_lead.get("company", ""), key="ml_company")

            selected_lead["industry"] = selected_lead.get("industry") or fallback_industry
            industry = st.text_input("Industry", selected_lead.get("industry", ""), key="ml_industry")

            chat = st.text_area("Chat History", selected_lead.get("chat_history", ""), key="ml_chat")
            signals = st.text_area("LeadIQ Signals", selected_lead.get("leadiq", ""), key="ml_signals")

            company_info = next(
                (c.get("description") for c in company_details if c.get("company_id") == company_id),
                "",
            )
            pdf = st.text_area("Company Details", company_info, key="ml_company_details")

            categories = list(config.get("categories", {}).keys())
            if not categories:
                categories = ["default"]
            category = st.selectbox("Message Category", categories, key="ml_category")
            use_dynamic = st.checkbox("Use AI-Powered Dynamic Prompting", value=True, key="ml_dynamic")

            if st.button("Generate Message", key="ml_generate"):
                test_lead = {
                    "name": name,
                    "title": title,
                    "company": company,
                    "industry": industry,
                    "chat_history": chat,
                    "leadiq": signals,
                    "pdf_summary": pdf,
                    "category": category,
                }

                try:
                    if use_dynamic:
                        message = generate_dynamic_message(test_lead, st.session_state.get("model_selection"), config)
                    else:
                        message = generate_connection(test_lead, st.session_state.get("model_selection"), config)
                    st.session_state["generated_message"] = message
                except Exception as e:
                    st.error(f"❌ Message generation failed: {e}")

            if "generated_message" in st.session_state:
                st.text_area("Generated Message", st.session_state["generated_message"], height=140, key="ml_out")

                if st.button("Send Message", key="ml_send"):
                    try:
                        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                        selected_lead["last_message_date"] = now
                        sheets.update_lead_message_date(config, selected_lead, now)
                        st.success(f"✅ Message sent to {name} (Last messaged on {now})")
                    except Exception as e:
                        st.error(f"❌ Send failed: {e}")

                if st.button("🕒 Schedule Message", key="ml_schedule"):
                    scheduled_data = {
                        "linkedin_id": selected_lead.get("linkedin_id", ""),
                        "name": name,
                        "title": title,
                        "company": company,
                        "industry": industry,
                        "message": st.session_state["generated_message"],
                        "category": category,
                        "scheduled_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "scheduled",
                    }
                    try:
                        sheets.append_scheduled_message(config, scheduled_data)
                        st.success("✅ Message scheduled successfully.")
                    except Exception as e:
                        st.error(f"❌ Failed to schedule message: {e}")
        else:
            st.warning("⚠️ No leads match your current filters.")
    else:
        st.info("Load leads to begin.")


# =========================================================
# 🗂️ Queue
# =========================================================

with tabs[6]:
    st.subheader("🗂️ Queue")

    try:
        sheet = sheets._client(config).open_by_key(
            config["gsheets"]["spreadsheet_id"]
        ).worksheet("ScheduledMessages")

        records = sheet.get_all_records()

        if not records:
            st.info("📭 No scheduled messages yet.")
        else:
            df = pd.DataFrame(records)

            s1, s2, s3 = st.columns(3)
            s1.metric("📬 Total", len(df))
            s2.metric(
                "✅ Sent",
                (df["status"] == "sent").sum() if "status" in df.columns else 0,
            )
            s3.metric(
                "📅 Upcoming",
                (df["status"] == "scheduled").sum() if "status" in df.columns else 0,
            )

            with st.expander("🔍 Filter Options", expanded=False):
                status_filter = st.selectbox(
                    "Status",
                    ["All", "scheduled", "sent"],
                    key="q_status",
                )
                search_term = st.text_input(
                    "Search by Name or Company",
                    key="q_search",
                )
                page_size = st.selectbox(
                    "Messages per page",
                    [10, 20, 50, 100],
                    index=1,
                    key="q_pagesize",
                )

            filtered_df = df.copy()

            if status_filter != "All" and "status" in filtered_df.columns:
                filtered_df = filtered_df[
                    filtered_df["status"] == status_filter
                    ]

            if (
                    search_term
                    and "name" in filtered_df.columns
                    and "company" in filtered_df.columns
            ):
                term = search_term.lower()
                filtered_df = filtered_df[
                    filtered_df["name"].astype(str).str.lower().str.contains(term)
                    | filtered_df["company"].astype(str).str.lower().str.contains(term)
                    ]

            total_records = len(filtered_df)
            total_pages = max(1, (total_records - 1) // page_size + 1)

            page = st.number_input(
                "Page",
                min_value=1,
                max_value=total_pages,
                step=1,
                key="q_page",
            )

            start = (page - 1) * page_size
            end = page * page_size
            paged_df = filtered_df.iloc[start:end]

            cols_to_show = [
                c
                for c in [
                    "rank",
                    "name",
                    "company",
                    "scheduled_for",
                    "message_type",
                    "status",
                    "industry_bucket",
                ]
                if c in paged_df.columns
            ]

            st.dataframe(
                paged_df[cols_to_show].reset_index(drop=True)
                if cols_to_show
                else paged_df.reset_index(drop=True),
                use_container_width=True,
                height=420,
            )

            for idx, row in paged_df.iterrows():
                display_name = f"📨 {row.get('name','')} — {row.get('company','')}"
                with st.expander(display_name):

                    if "message_text" in row and pd.notna(row["message_text"]):
                        st.code(str(row["message_text"]), language="text")
                    elif "message" in row and pd.notna(row["message"]):
                        st.code(str(row["message"]), language="text")

                    row_index = idx + 2  # assumes header row at index 1
                    lid = row.get("linkedin_id", "")
                    msg_id = row.get("message_id", "")

                    b1, b2 = st.columns(2)

                    if b1.button(
                            "✅ Mark as Sent",
                            key=f"q_sent_{lid}_{msg_id}_{idx}",
                    ):
                        try:
                            if "status" in df.columns:
                                col_index = df.columns.get_loc("status") + 1
                                sheet.update_cell(row_index, col_index, "sent")
                            st.success(f"Marked as sent: {row.get('name','')}")
                        except Exception as e:
                            st.error(f"❌ Failed to mark sent: {e}")

                    if b2.button(
                            "🗑️ Delete",
                            key=f"q_del_{lid}_{msg_id}_{idx}",
                    ):
                        try:
                            sheet.delete_rows(row_index)
                            st.warning(
                                f"Deleted message for {row.get('name','')}"
                            )
                        except Exception as e:
                            st.error(f"❌ Failed to delete row: {e}")

    except Exception as e:
        st.error(f"❌ Failed to load scheduled messages: {e}")


# =========================================================
# ⚙️ Settings (Configuration) — FIXED + COMPLETE TAB BLOCK
# Drop-in replacement for your Settings tab
# =========================================================

with tabs[7]:
    st.subheader("⚙️ Settings")

    # Load config fresh inside Settings tab
    cfg = load_config()

    # ---- LinkedIn ----
    linkedin_user = st.text_input(
        "LinkedIn Username",
        value=cfg.get("linkedin", {}).get("username", ""),
        key="set_li_user",
    )
    linkedin_pass = st.text_input(
        "LinkedIn Password",
        type="password",
        value=cfg.get("linkedin", {}).get("password", ""),
        key="set_li_pass",
    )

    # ✅ FIX: join + string literal (no broken quotes)
    searches_raw = st.text_area(
        "SalesNav Searches (name|url per line)",
        value="\n".join(
            [
                f"{s.get('name','')}|{s.get('url','')}"
                for s in cfg.get("linkedin", {}).get("searches", [])
            ]
        ),
        key="set_searches",
    )

    # ---- SalesNav Lists ----
    new_list_url = st.text_input(
        "Lead List URL (from SalesNav)",
        value=cfg.get("linkedin", {}).get("lists", {}).get("new_leads_url", ""),
        key="set_new_list_url",
    )
    new_list_name = st.text_input(
        "Lead List Name (optional if URL is provided)",
        value=cfg.get("linkedin", {}).get("lists", {}).get("new_leads", ""),
        key="set_new_list_name",
    )
    invited_list = st.text_input(
        "Invited List Name",
        value=cfg.get("linkedin", {}).get("lists", {}).get("invited", ""),
        key="set_invited_list",
    )
    connected_list = st.text_input(
        "Connected List Name",
        value=cfg.get("linkedin", {}).get("lists", {}).get("connected", ""),
        key="set_connected_list",
    )
    bulk_search_url = st.text_input(
        "SalesNav Search URL to Add 100 Leads",
        value="",
        key="set_bulk_url",
    )

    # ---- HubSpot / HF ----
    hub_key = st.text_input(
        "HubSpot API Key",
        type="password",
        value=cfg.get("hubspot", {}).get("api_key", ""),
        key="set_hub_key",
    )
    hf_token = st.text_input(
        "HuggingFace Token",
        type="password",
        value=cfg.get("huggingface", {}).get("token", ""),
        key="set_hf_token",
    )
    hf_model = st.text_input(
        "HF Model",
        value=cfg.get("huggingface", {}).get("model", "meta-llama/Llama-2-7b-chat-hf"),
        key="set_hf_model",
    )

    # ---- Ollama ----
    ollama_models_config = cfg.get("ollama", {}).get("models", [])
    if not ollama_models_config:
        st.warning("⚠️ No Ollama models found in config.yaml → ollama.models.")
        ollama_models_config = ["mistral", "llama3", "deepseek"]

    default_model = cfg.get("ollama", {}).get("model", ollama_models_config[0])
    model_selection = st.selectbox(
        "LLM Model (Ollama)",
        ollama_models_config,
        index=ollama_models_config.index(default_model) if default_model in ollama_models_config else 0,
        key="set_model",
    )
    st.session_state["model_selection"] = model_selection

    # ---- Rate limits ----
    min_delay = st.number_input(
        "Min Delay (sec)",
        value=int(cfg.get("rate_limits", {}).get("min_delay_sec", 30)),
        key="set_min_delay",
    )
    max_delay = st.number_input(
        "Max Delay (sec)",
        value=int(cfg.get("rate_limits", {}).get("max_delay_sec", 90)),
        key="set_max_delay",
    )

    # ---- Prompts ----
    conn_seed = st.text_area(
        "Connection Prompt",
        value=cfg.get("seeds", {}).get("connection", ""),
        key="set_conn_seed",
    )
    follow_seed = st.text_area(
        "Follow-Up Prompt",
        value=cfg.get("seeds", {}).get("followup", ""),
        key="set_follow_seed",
    )

    # ---- Google Sheets ----
    gs_creds = st.text_input(
        "Google Creds JSON",
        value=cfg.get("gsheets", {}).get("creds_json", ""),
        key="set_gs_creds",
    )
    gs_sheet = st.text_input(
        "Spreadsheet ID",
        value=cfg.get("gsheets", {}).get("spreadsheet_id", ""),
        key="set_gs_sheet",
    )
    gs_leads_ws = st.text_input(
        "Leads Worksheet",
        value=cfg.get("gsheets", {}).get("leads_ws", "Leads"),
        key="set_gs_leads",
    )
    gs_report_ws = st.text_input(
        "Report Worksheet",
        value=cfg.get("gsheets", {}).get("report_ws", "Report"),
        key="set_gs_report",
    )

    st.markdown("---")

    # ---- Utility action: Add search results to list ----
    if st.button("📅 Add Search to Lead List", key="set_add_search"):
        try:
            if not bulk_search_url or (not new_list_url and not new_list_name):
                st.warning("Please provide the search URL and either a list name or URL.")
            else:
                added = add_search_results_to_list(
                    search_url=bulk_search_url,
                    list_url=new_list_url,
                    list_name=new_list_name,
                    context=st.session_state.get("context"),
                )
                st.success(f"✅ Added {added} leads to list: {new_list_name or new_list_url}")
        except Exception as e:
            st.error(f"❌ Failed to add leads: {e}")

    # ---- Save config ----
    if st.button("Save Configuration", key="set_save"):
        searches = []
        for line in searches_raw.splitlines():
            if "|" in line:
                n, u = line.split("|", 1)
                searches.append({"name": n.strip(), "url": u.strip()})

        new_cfg = {
            "linkedin": {
                "username": linkedin_user,
                "password": linkedin_pass,
                "searches": searches,
                "lists": {
                    "new_leads": new_list_name,
                    "new_leads_url": new_list_url,
                    "invited": invited_list,
                    "connected": connected_list,
                },
            },
            "hubspot": {"api_key": hub_key},
            "huggingface": {"token": hf_token, "model": hf_model},
            "ollama": {"model": model_selection, "models": ollama_models_config},
            "rate_limits": {"min_delay_sec": int(min_delay), "max_delay_sec": int(max_delay)},
            "seeds": {"connection": conn_seed, "followup": follow_seed},
            "gsheets": {
                "creds_json": gs_creds,
                "spreadsheet_id": gs_sheet,
                "leads_ws": gs_leads_ws,
                "report_ws": gs_report_ws,
            },
        }

        try:
            save_config(new_cfg)
            load_config.clear()

            # refresh in-memory config for rest of app
            config = load_config()
            st.session_state["config"] = config

            st.success("✅ Configuration saved.")
        except Exception as e:
            st.error(f"❌ Failed to save config: {e}")
