from playwright.sync_api import sync_playwright
import random, time, yaml, os
from modules import sheets
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def extract_all_searches(context=None):
    cfg = yaml.safe_load(open(CONFIG_FILE))
    leads, sheet = sheets.get_all_leads(cfg)
    existing_ids = {l['linkedin_id'] for l in leads if l.get('linkedin_id')}

    if context:
        page = context.new_page()
        close_browser = False
        p = None
    else:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state="user_data/state.json", viewport={"width": 1280, "height": 1080})
        page = context.new_page()
        close_browser = True

    for search in cfg['linkedin']['searches']:
        print(f"\n🔍 Processing search: {search['name']}")
        page.goto(search['url'])
        page.wait_for_timeout(5000)

        if "login" in page.url:
            print("⚠️  Redirected to login — session may have expired.")
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"{search['name']}_login_redirect.png"), full_page=True)
            continue

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)

        cards = page.query_selector_all('td.list-people-detail-header__entity')
        print(f"✅ Found {len(cards)} cards")

        for i, c in enumerate(cards):
            try:
                # Name & Profile URL
                name_el = c.query_selector('a.lists-detail__view-profile-name-link')
                name = name_el.inner_text().strip() if name_el else "N/A"

                profile_url = name_el.get_attribute('href') if name_el else ''
                if profile_url and not profile_url.startswith("http"):
                    profile_url = f"https://www.linkedin.com{profile_url}"

                lid = profile_url.split("/")[-1].split(",")[0] if profile_url else ''
                if lid in existing_ids:
                    continue

                # Title
                title_el = c.query_selector('div[data-anonymize="job-title"]')
                title = title_el.inner_text().strip() if title_el else "N/A"

                # Company
                company_el = c.query_selector('*[data-anonymize="company-name"]')
                company = company_el.text_content().strip() if company_el else "N/A"

                # Upload to sheet
                sheets.append_lead(cfg, {
                    'linkedin_id': lid,
                    'name': name,
                    'title': title,
                    'company': company,
                    'profile_url': profile_url,
                    'email': '',
                    'status': 'new',
                    'extracted_at': datetime.datetime.utcnow().isoformat(),
                    'invited_at': '',
                    'connected_at': '',
                    'last_visit_at': '',
                    'followup_sent_at': ''
                })


                existing_ids.add(lid)
                page.wait_for_timeout(2000)
                print(f"➕ Saved: {name} | {title} | {company}")

            except Exception as e:
                print(f"❌ Error parsing card #{i+1}: {e}")

        time.sleep(random.randint(cfg['rate_limits']['min_delay_sec'], cfg['rate_limits']['max_delay_sec']))

    if close_browser:
        context.close()
        browser.close()
        p.stop()

    sheets.update_metadata(cfg, 'last_extract')
    print("\n✅ Done extracting and saving to Google Sheet.")

def extract_list(list_url, context=None):
    """Extract leads from a specific Sales Navigator list URL."""
    cfg = yaml.safe_load(open(CONFIG_FILE))
    leads, sheet = sheets.get_all_leads(cfg)
    existing_ids = {l['linkedin_id'] for l in leads if l.get('linkedin_id')}

    if context:
        page = context.new_page()
        close_browser = False
        p = None
    else:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state="user_data/state.json", viewport={"width": 1280, "height": 1080})
        page = context.new_page()
        close_browser = True

    page.goto(list_url)
    page.wait_for_timeout(5000)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(3000)

    cards = page.query_selector_all('td.list-people-detail-header__entity')
    for c in cards:
        try:
            name_el = c.query_selector('a.lists-detail__view-profile-name-link')
            name = name_el.inner_text().strip() if name_el else "N/A"

            profile_url = name_el.get_attribute('href') if name_el else ''
            if profile_url and not profile_url.startswith("http"):
                profile_url = f"https://www.linkedin.com{profile_url}"
            lid = profile_url.split("/")[-1].split(",")[0] if profile_url else ''
            if lid in existing_ids:
                continue

            title_el = c.query_selector('div[data-anonymize="job-title"]')
            title = title_el.inner_text().strip() if title_el else "N/A"
            company_el = c.query_selector('*[data-anonymize="company-name"]')
            company = company_el.text_content().strip() if company_el else "N/A"

            sheets.append_lead(cfg, {
                'linkedin_id': lid,
                'name': name,
                'title': title,
                'company': company,
                'profile_url': profile_url,
                'email': '',
                'status': 'new',
                'extracted_at': datetime.datetime.utcnow().isoformat(),
                'invited_at': '',
                'connected_at': '',
                'last_visit_at': '',
                'followup_sent_at': ''
            })
            existing_ids.add(lid)
            page.wait_for_timeout(1000)
        except Exception:
            continue

    if close_browser:
        context.close()
        browser.close()
        p.stop()

    sheets.update_metadata(cfg, 'last_extract')
    return len(cards)
