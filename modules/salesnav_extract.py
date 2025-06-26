from playwright.sync_api import sync_playwright
import sqlite3, random, time, yaml, os

CONFIG_FILE = "config.yaml"
DB_FILE = "leads.db"
cfg = yaml.safe_load(open(CONFIG_FILE))

def extract_all_searches():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # LinkedIn login
        page.goto("https://www.linkedin.com/login")
        page.fill("input[name='session_key']", cfg['linkedin']['username'])
        page.fill("input[name='session_password']", cfg['linkedin']['password'])
        page.click("button[type='submit']")
        page.wait_for_load_state('networkidle')

        for search in cfg['linkedin']['searches']:
            page.goto(search['url'])
            # TODO: scrape profiles and insert into leads table
            time.sleep(random.randint(cfg['rate_limits']['min_delay_sec'], cfg['rate_limits']['max_delay_sec']))
        browser.close()
    conn.commit()
    conn.close()
