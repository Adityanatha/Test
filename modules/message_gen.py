import os
import yaml
import textwrap
import subprocess
import re
import streamlit as st
from modules.industry_mapper import load_bucket_mapping, get_industry_bucket

# --- Config ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")
COLLATERAL_CONFIG = os.path.join(BASE_DIR, "config", "collaterals.yaml")

# --- Load YAML Config ---
def _load_cfg():
    return yaml.safe_load(open(CONFIG_FILE))

# --- Load Collaterals ---
def get_collaterals():
    if not os.path.exists(COLLATERAL_CONFIG):
        return []
    with open(COLLATERAL_CONFIG, "r") as f:
        data = yaml.safe_load(f) or []
        if not isinstance(data, list):
            st.warning("⚠️ Collateral config is malformed. Expected a list.")
            return []
        return data

# --- Assign Industry Bucket ---
def assign_industry_bucket(lead):
    industry = lead.get("industry", "").strip()
    reverse_map, default_bucket = load_bucket_mapping()
    bucket = get_industry_bucket(industry, reverse_map, default_bucket)
    lead["industry_bucket"] = bucket
    return lead

# --- Build Prompt for Static Category ---
def _build_category_prompt(lead, category, cfg, collateral_snippet=None):
    category_config = cfg['categories'].get(category, {})
    tone = category_config.get("tone", "Friendly and professional")
    goal = category_config.get("goal", "Build rapport and invite a light response")
    max_chars = category_config.get("max_chars", 200)

    pdf_text = lead.get("pdf_summary", "").strip()
    if pdf_text:
        pdf_text = textwrap.shorten(pdf_text, width=800, placeholder="...")

    collateral_text = f"\nRelevant Collateral:\n{collateral_snippet}\n" if collateral_snippet else ""

    prompt = f"""
You are a Director at InfoObjects — not in sales, but here to build trust and spark meaningful conversations with enterprise leaders.

Message category: {category}
Tone: {tone}
Goal: {goal}
Maximum Length: {max_chars} characters

Lead context:
- Name: {lead.get("name")}
- Title: {lead.get("title")}
- Company: {lead.get("company")}
- Industry: {lead.get("industry")}
- Industry Bucket: {lead.get("industry_bucket")}
- Chat History: {lead.get("chat_history", "None")}
- LeadIQ Data: {lead.get("leadiq", "None")}

Company Document (optional):
\"\"\"{pdf_text or 'N/A'}\"\"\"

{collateral_text}
Write a short LinkedIn-style message under {max_chars} characters. Make it sound natural, not scripted.
Do not invent past interactions or events. Only use the provided context. Do not refer to meetings or conversations unless explicitly mentioned.
""".strip()

    return prompt

# --- Dynamic Message Builder ---
def generate_dynamic_message(lead, model_name, cfg=None):
    cfg = cfg or _load_cfg()
    lead = assign_industry_bucket(lead)

    collaterals = get_collaterals()

    bdr_collateral = next((c for c in collaterals if c["asset_type"] == "benchmark" and "BDR" in c["name"]), None)

    formatted_collaterals = [
        f"- {c['name']} ({c['type']}, {c['industry']}, {c['asset_type']}): {c['description']}"
        for c in collaterals
        if c.get("name") and c.get("description")
    ]

    if bdr_collateral:
        formatted_collaterals.insert(0, f"- {bdr_collateral['name']} (Internal Benchmark): {bdr_collateral['description']}")

    pdf_text = lead.get("pdf_summary", "").strip()
    if pdf_text:
        pdf_text = textwrap.shorten(pdf_text, width=800, placeholder="...")

    prompt = f"""
You are helping a GenAI strategist at InfoObjects write a high-impact message to a prospect.

## Lead Information:
- Name: {lead.get("name")}
- Title: {lead.get("title")}
- Company: {lead.get("company")}
- Industry: {lead.get("industry")}
- Industry Bucket: {lead.get("industry_bucket")}
- Chat History: {lead.get("chat_history", "None")}
- LeadIQ: {lead.get("leadiq", "None")}

## Company Summary:
\"\"\"{pdf_text}\"\"\"

## Internal Messaging Reference (for style):
Start by referencing our internal BDR Messaging Benchmark document.

## Available Collateral:
{chr(10).join(formatted_collaterals)}

## Your Task:
1. Choose a relevant message type (initial, follow-up, nurture, demo invite).
2. If useful, include one supporting collateral from above.
3. Write a LinkedIn message that:
   - Has a clear hook relevant to the lead’s role or company
   - Avoids vague compliments, fake familiarity, or fluff
   - Suggests a conversation or async resource
   - Keeps it concise and natural (under 300 characters)

Return only the message text.
""".strip()

    st.markdown("#### 🧠 Prompt Sent to LLM")
    st.code(prompt)

    return _call_ollama(prompt, cfg, model_name)

# --- Ollama Run ---
def _call_ollama(prompt, cfg, model_name):
    print("\n\n🧠 DEBUG — Prompt Sent to Ollama:\n", prompt, "\n\n")
    try:
        result = subprocess.run(
            ["ollama", "run", model_name],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=60
        )
        output = result.stdout.strip()
        output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL)
        output = re.sub(r"(Here[’']?s.*?:\s*)", "", output, flags=re.IGNORECASE)
        return output.strip()
    except Exception as e:
        print("⚠️ Ollama failed:", str(e))
        return prompt

# --- Standard Message Generators ---
def generate_connection(lead, model_name, cfg=None, collateral_snippet=None):
    cfg = cfg or _load_cfg()
    lead = assign_industry_bucket(lead)
    category = lead.get("category", "initial_message")
    prompt = _build_category_prompt(lead, category, cfg, collateral_snippet)
    return _call_ollama(prompt, cfg, model_name)

def generate_followup(lead, model_name, cfg=None, collateral_snippet=None):
    cfg = cfg or _load_cfg()
    lead = assign_industry_bucket(lead)
    category = lead.get("category", "follow_up_message")
    prompt = _build_category_prompt(lead, category, cfg, collateral_snippet)
    return _call_ollama(prompt, cfg, model_name)
