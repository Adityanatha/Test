import os
import yaml
import textwrap
import subprocess
import re

# --- Config ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

# --- Load YAML Config ---
def _load_cfg():
    return yaml.safe_load(open(CONFIG_FILE))

# --- Build Prompt Dynamically ---
def _build_category_prompt(lead, category, cfg):
    category_config = cfg['categories'].get(category, {})
    tone = category_config.get("tone", "Friendly and professional")
    goal = category_config.get("goal", "Build rapport and invite a light response")
    max_chars = category_config.get("max_chars", 200)

    pdf_text = lead.get("pdf_summary", "").strip()
    if pdf_text:
        pdf_text = textwrap.shorten(pdf_text, width=800, placeholder="...")

    return f"""
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
- Chat History: {lead.get("chat_history", "None")}
- LeadIQ Data: {lead.get("leadiq", "None")}

Company Document (optional):
\"\"\"
{pdf_text or 'N/A'}
\"\"\"

Write a short LinkedIn-style message under {max_chars} characters. Make it sound natural, not scripted.
""".strip()

# --- Ollama Local Call with Model from YAML ---
def _call_ollama(prompt, cfg):
    model = cfg.get("ollama", {}).get("model", "deepseek-r1:7b")

    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=60
        )
        output = result.stdout.strip()

        # 🧹 Clean unwanted sections (e.g., <think> blocks or headings)
        output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL)
        output = re.sub(r"(Here[’']?s.*?:\s*)", "", output, flags=re.IGNORECASE)

        return output.strip()

    except Exception as e:
        print("⚠️ Ollama failed:", str(e))
        return prompt

# --- Main Message Generators ---
def generate_connection(lead):
    cfg = _load_cfg()
    category = lead.get("category", "initial_message")
    prompt = _build_category_prompt(lead, category, cfg)
    return _call_ollama(prompt, cfg)

def generate_followup(lead):
    cfg = _load_cfg()
    category = lead.get("category", "follow_up_message")
    prompt = _build_category_prompt(lead, category, cfg)
    return _call_ollama(prompt, cfg)
