import yaml, requests, os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

def _call_hf(prompt, cfg):
    headers = {"Authorization": f"Bearer {cfg['huggingface']['token']}"}
    resp = requests.post(
        f"https://api-inference.huggingface.co/models/{cfg['huggingface']['model']}",
        headers=headers,
        json={"inputs": prompt},
        timeout=30,
    )
    if resp.ok:
        try:
            return resp.json()[0]["generated_text"].strip()
        except Exception:
            pass
    return prompt


def generate_connection(lead):
    cfg = yaml.safe_load(open(CONFIG_FILE))
    prompt = f"{cfg['seeds']['connection']} Person: {lead['name']}, {lead['title']} at {lead['company']}."
    return _call_hf(prompt, cfg)

def generate_followup(lead):
    cfg = yaml.safe_load(open(CONFIG_FILE))
    prompt = f"{cfg['seeds']['followup']} Person: {lead['name']}."
    return _call_hf(prompt, cfg)
