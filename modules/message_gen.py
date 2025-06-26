import yaml, requests
cfg = yaml.safe_load(open("config.yaml"))

def generate_connection(lead):
    prompt = f"{cfg['seeds']['connection']} Person: {lead['name']}, {lead['title']} at {lead['company']}."
    # TODO: call HF Inference API to get generated message
    return prompt + " (LLM generated)"

def generate_followup(lead):
    prompt = f"{cfg['seeds']['followup']} Person: {lead['name']}."
    # TODO: call HF Inference API to get generated message
    return prompt + " (LLM generated)"
