import sqlite3, yaml, random, time
from playwright.sync_api import sync_playwright
from modules.message_gen import generate_connection, generate_followup

cfg = yaml.safe_load(open("config.yaml"))
DB_FILE = "leads.db"

def send_invites():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT linkedin_id, profile_url, name, title, company FROM leads WHERE status='synced'")
    leads = cur.fetchall()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # LinkedIn login
        page.goto("https://www.linkedin.com/login")
        page.fill("input[name='session_key']", cfg['linkedin']['username'])
        page.fill("input[name='session_password']", cfg['linkedin']['password'])
        page.click("button[type='submit']")
        page.wait_for_load_state('networkidle')

        for lid,url,name,title,company in leads:
            msg = generate_connection({'name':name,'title':title,'company':company})
            page.goto(url)
            # TODO: click Connect, fill message, send
            cur.execute("UPDATE leads SET status='invited', invited_at=CURRENT_TIMESTAMP WHERE linkedin_id=?", (lid,))
            time.sleep(random.randint(cfg['rate_limits']['min_delay_sec'], cfg['rate_limits']['max_delay_sec']))
        browser.close()
    conn.commit()
    conn.close()

def process_followups():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # TODO: detect accepted invitations and send follow-up messages
    conn.commit()
    conn.close()
