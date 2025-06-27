import yaml, random, time, os
from playwright.sync_api import sync_playwright
from modules.message_gen import generate_connection, generate_followup
from modules import sheets
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

def send_invites(context=None):
    cfg = yaml.safe_load(open(CONFIG_FILE))
    leads, sheet = sheets.get_all_leads(cfg)
    leads = [l for l in leads if l.get('status') == 'synced']

    if context:
        page = context.new_page()
        close_browser = False
    else:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.linkedin.com/login")
        page.fill("input[name='session_key']", cfg['linkedin']['username'])
        page.fill("input[name='session_password']", cfg['linkedin']['password'])
        page.click("button[type='submit']")
        page.wait_for_load_state('networkidle')
        close_browser = True

    for l in leads:
        msg = generate_connection({'name': l['name'], 'title': l['title'], 'company': l['company']})
        page.goto(l['profile_url'])
        if page.query_selector("button:has-text('Connect')"):
            page.click("button:has-text('Connect')")
            if page.query_selector("button:has-text('Add a note')"):
                page.click("button:has-text('Add a note')")
                page.fill('textarea', msg)
                if page.query_selector("button:has-text('Send')"):
                    page.click("button:has-text('Send')")
        sheets.update_lead(sheet, l['_row'], 7, 'invited')
        sheets.update_lead(sheet, l['_row'], 9, datetime.datetime.utcnow().isoformat())
        time.sleep(random.randint(cfg['rate_limits']['min_delay_sec'], cfg['rate_limits']['max_delay_sec']))

    if close_browser:
        browser.close()
        p.stop()
    sheets.update_metadata(cfg, 'last_outreach')

def process_followups(context=None):
    cfg = yaml.safe_load(open(CONFIG_FILE))
    leads, sheet = sheets.get_all_leads(cfg)
    leads = [l for l in leads if l.get('status') == 'invited']
    if context:
        page = context.new_page()
        close_browser = False
    else:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.linkedin.com/login")
        page.fill("input[name='session_key']", cfg['linkedin']['username'])
        page.fill("input[name='session_password']", cfg['linkedin']['password'])
        page.click("button[type='submit']")
        page.wait_for_load_state('networkidle')
        close_browser = True

    for l in leads:
        page.goto(l['profile_url'])
        if page.query_selector("button:has-text('Message')"):
            msg = generate_followup({'name': l['name']})
            page.click("button:has-text('Message')")
            page.fill('textarea', msg)
            if page.query_selector("button:has-text('Send')"):
                page.click("button:has-text('Send')")
            sheets.update_lead(sheet, l['_row'], 7, 'connected')
            sheets.update_lead(sheet, l['_row'], 10, datetime.datetime.utcnow().isoformat())
            sheets.update_lead(sheet, l['_row'], 12, datetime.datetime.utcnow().isoformat())

    if close_browser:
        browser.close()
        p.stop()
    sheets.update_metadata(cfg, 'last_followup')
