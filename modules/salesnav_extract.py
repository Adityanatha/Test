from playwright.sync_api import sync_playwright
import random, time, yaml, os
from modules import sheets
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

def extract_all_searches(context=None):
    cfg = yaml.safe_load(open(CONFIG_FILE))
    leads, sheet = sheets.get_all_leads(cfg)
    existing_ids = {l['linkedin_id'] for l in leads if l['linkedin_id']}

    if context:
        page = context.new_page()
        close_browser = False
    else:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # LinkedIn login
        page.goto("https://www.linkedin.com/login")
        page.fill("input[name='session_key']", cfg['linkedin']['username'])
        page.fill("input[name='session_password']", cfg['linkedin']['password'])
        page.click("button[type='submit']")
        page.wait_for_load_state('networkidle')
        close_browser = True

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
            if lid in existing_ids:
                continue
            title_el = c.query_selector('.entity-result__primary-subtitle')
            title = title_el.inner_text().strip() if title_el else ''
            company_el = c.query_selector('.entity-result__secondary-subtitle')
            company = company_el.inner_text().strip() if company_el else ''
            sheets.append_lead(cfg, {
                'linkedin_id': lid,
                'name': name,
                'title': title,
                'company': company,
                'profile_url': url,
                'status': 'new',
                'extracted_at': datetime.datetime.utcnow().isoformat()
            })
            existing_ids.add(lid)
        time.sleep(random.randint(cfg['rate_limits']['min_delay_sec'], cfg['rate_limits']['max_delay_sec']))

    if close_browser:
        browser.close()
        p.stop()
    sheets.update_metadata(cfg, 'last_extract')
