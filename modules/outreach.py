import sqlite3, yaml, random, time, os
from playwright.sync_api import sync_playwright
from modules.message_gen import generate_connection, generate_followup

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")
DB_FILE = os.path.join(BASE_DIR, "leads.db")

def send_invites():
    cfg = yaml.safe_load(open(CONFIG_FILE))
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
            if page.query_selector("button:has-text('Connect')"):
                page.click("button:has-text('Connect')")
                if page.query_selector("button:has-text('Add a note')"):
                    page.click("button:has-text('Add a note')")
                    page.fill('textarea', msg)
                    if page.query_selector("button:has-text('Send')"):
                        page.click("button:has-text('Send')")
            cur.execute("UPDATE leads SET status='invited', invited_at=CURRENT_TIMESTAMP WHERE linkedin_id=?", (lid,))
            time.sleep(random.randint(cfg['rate_limits']['min_delay_sec'], cfg['rate_limits']['max_delay_sec']))
        browser.close()
    cur.execute("UPDATE metadata SET last_outreach=CURRENT_TIMESTAMP")
    conn.commit()
    conn.close()

def process_followups():
    cfg = yaml.safe_load(open(CONFIG_FILE))
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT linkedin_id, profile_url, name FROM leads WHERE status='invited'")
    leads = cur.fetchall()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.linkedin.com/login")
        page.fill("input[name='session_key']", cfg['linkedin']['username'])
        page.fill("input[name='session_password']", cfg['linkedin']['password'])
        page.click("button[type='submit']")
        page.wait_for_load_state('networkidle')

        for lid,url,name in leads:
            page.goto(url)
            if page.query_selector("button:has-text('Message')"):
                msg = generate_followup({'name':name})
                page.click("button:has-text('Message')")
                page.fill('textarea', msg)
                if page.query_selector("button:has-text('Send')"):
                    page.click("button:has-text('Send')")
                cur.execute(
                    "UPDATE leads SET status='connected', connected_at=CURRENT_TIMESTAMP, followup_sent_at=CURRENT_TIMESTAMP WHERE linkedin_id=?",
                    (lid,)
                )
        browser.close()
    cur.execute("UPDATE metadata SET last_followup=CURRENT_TIMESTAMP")
    conn.commit()
    conn.close()
