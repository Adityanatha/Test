from playwright.sync_api import sync_playwright
import sqlite3, random, time, yaml, os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")
DB_FILE = os.path.join(BASE_DIR, "leads.db")

def extract_all_searches():
    cfg = yaml.safe_load(open(CONFIG_FILE))
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
            cards = page.query_selector_all('li.artdeco-list__item')
            for c in cards:
                name = c.query_selector('span[dir="ltr"]')
                if not name:
                    continue
                name = name.inner_text().strip()
                profile = c.query_selector('a.app-aware-link')
                url = profile.get_attribute('href').split('?')[0] if profile else ''
                lid = url.split('/')[-2] if url else ''
                title_el = c.query_selector('.entity-result__primary-subtitle')
                title = title_el.inner_text().strip() if title_el else ''
                company_el = c.query_selector('.entity-result__secondary-subtitle')
                company = company_el.inner_text().strip() if company_el else ''
                cur.execute(
                    "INSERT OR IGNORE INTO leads (linkedin_id, name, title, company, profile_url, extracted_at)"
                    " VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (lid, name, title, company, url)
                )
            time.sleep(random.randint(cfg['rate_limits']['min_delay_sec'], cfg['rate_limits']['max_delay_sec']))
        browser.close()
    cur.execute("UPDATE metadata SET last_extract=CURRENT_TIMESTAMP")
    conn.commit()
    conn.close()
