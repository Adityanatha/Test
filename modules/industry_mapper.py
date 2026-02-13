import os
import yaml

# Locate the config.yaml relative to this file
CONFIG_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "config.yaml")

def load_bucket_mapping():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"⚠️ config.yaml not found at {CONFIG_PATH}")

    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f) or {}

    # Reserved keys to ignore
    reserved_keys = {
        "gsheets", "hubspot", "huggingface", "linkedin", "rate_limits",
        "seeds", "ollama", "categories", "default_bucket"
    }

    reverse_map = {}
    default_bucket = config.get("default_bucket", "general")

    for key, val in config.items():
        if key in reserved_keys:
            continue
        if isinstance(val, list):
            for industry in val:
                reverse_map[industry.lower()] = key

    return reverse_map, default_bucket

def get_industry_bucket(industry, reverse_map, default_bucket):
    return reverse_map.get(industry.lower().strip(), default_bucket)

def assign_industry_bucket(lead):
    industry = lead.get("industry", "").strip()
    reverse_map, default_bucket = load_bucket_mapping()
    bucket = get_industry_bucket(industry, reverse_map, default_bucket)
    lead["industry_bucket"] = bucket
    return lead
