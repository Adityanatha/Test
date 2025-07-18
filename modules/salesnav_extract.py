from playwright.sync_api import sync_playwright
import random, time, yaml, os
from modules import sheets
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
RATE_LIMIT_PER_MIN = 20

def process_cards(cards, existing_ids, cfg):
    writes = 0
    start_time = time.time()
    for i, c in enumerate(cards):
        if writes >= RATE_LIMIT_PER_MIN:
            elapsed = time.time() - start_time
            sleep_for = max(60 - elapsed, 0)
            print(f"⏱️ Rate limit reached. Sleeping for {sleep_for:.2f} seconds")
            time.sleep(sleep_for)
            writes = 0
            start_time = time.time()

        try:
            name_el = c.query_selector('a.lists-detail__view-profile-name-link')
            lead_name = name_el.inner_text().strip() if name_el else "N/A"

            profile_url = name_el.get_attribute('href') if name_el else ''
            if profile_url and not profile_url.startswith("http"):
                profile_url = f"https://www.linkedin.com{profile_url}"

            lid = profile_url.split("/")[-1].split(",")[0] if profile_url else ''
            if lid in existing_ids:
                print(f"⏩ Skipping existing lead: {lead_name} ({lid})")
                continue

            title_el = c.query_selector('div[data-anonymize="job-title"]')
            title = title_el.inner_text().strip() if title_el else "N/A"

            company_el = c.query_selector('div[class="list-lead-detail__account"]')
            company = company_el.inner_text().strip() if company_el else "N/O"

            sheets.append_lead(cfg, {
                'linkedin_id': lid,
                'name': lead_name,
                'title': title,
                'company': company,
                'company_id': '',
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
            writes += 1
            print(f"➕ Saved: {lead_name} | {title} | {company}")
            time.sleep(random.uniform(3.5, 6.0))  # Slow down every append_row

        except Exception as e:
            print(f"❌ Error parsing card #{i+1}: {e}")

def scroll_and_collect_cards(page, existing_ids, cfg):
    all_cards = []
    visited_leads = set()
    page_num = 1

    while True:
        page.wait_for_timeout(3000)
        cards = page.query_selector_all('td.list-people-detail-header__entity')
        print(f"📄 Page {page_num}: Found {len(cards)} cards")

        process_cards(cards, existing_ids, cfg)

        new_lids = set()
        for card in cards:
            name_el = card.query_selector('a.lists-detail__view-profile-name-link')
            profile_url = name_el.get_attribute('href') if name_el else ''
            if profile_url and not profile_url.startswith("http"):
                profile_url = f"https://www.linkedin.com{profile_url}"
            lid = profile_url.split("/")[-1].split(",")[0] if profile_url else ''
            if lid and lid not in visited_leads:
                visited_leads.add(lid)
                new_lids.add(lid)

        if not new_lids:
            print("🛑 No new cards found, assuming last page.")
            break

        try:
            next_button = page.query_selector('//button[.//span[normalize-space()="Next"]]')
            if next_button and next_button.is_enabled():
                next_button.scroll_into_view_if_needed()
                next_button.click()
                print("➡️ Clicked next page")
                page.wait_for_timeout(5000)
                time.sleep(random.uniform(4.5, 7.5))  # Extra buffer between page scrolls
                page_num += 1
            else:
                print("⛔ 'Next' button not found or not enabled. Stopping.")
                break
        except Exception as e:
            print(f"❌ Pagination error: {e}")
            break

def extract_all_searches(context=None):
    cfg = yaml.safe_load(open(CONFIG_FILE))
    print("🔧 Loaded config")
    leads, _ = sheets.get_all_leads(cfg)
    existing_ids = {l['linkedin_id'] for l in leads if l.get('linkedin_id')}
    print(f"📄 Existing lead count: {len(existing_ids)}")

    if context:
        print("🌐 Using existing browser context")
        page = context.new_page()
        close_browser = False
        p = None
    else:
        print("🚀 Launching new browser session")
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state="user_data/state.json", viewport={"width": 1280, "height": 1080})
        page = context.new_page()
        close_browser = True

    searches = cfg.get('linkedin', {}).get('searches', [])
    print(f"🔍 Found {len(searches)} searches to process")
    for entry in searches:
        name, url = '', ''
        if isinstance(entry, dict):
            name = entry.get('name', '').strip()
            url = entry.get('url', '').strip()
        elif isinstance(entry, str) and '|' in entry:
            parts = entry.split('|', 1)
            if len(parts) == 2:
                name, url = parts[0].strip(), parts[1].strip()

        if not name or not url.startswith("http"):
            print(f"⚠️ Skipping invalid search: name='{name}', url='{url}'")
            continue

        print(f"\n🔍 Processing search: {name} -> {url}")
        try:
            page.goto(url)
            print(f"🌐 Navigated to: {page.url}")
        except Exception as e:
            print(f"❌ Failed to navigate to {url}: {e}")
            continue

        if "login" in page.url:
            print("⚠️  Redirected to login — session may have expired.")
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"{name}_login_redirect.png"), full_page=True)
            continue

        try:
            page.wait_for_selector('td.list-people-detail-header__entity', timeout=10000)
        except Exception as e:
            print(f"❌ Cards not found: {e}")
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"{name}_no_cards.png"), full_page=True)
            continue

        scroll_and_collect_cards(page, existing_ids, cfg)
        time.sleep(random.randint(cfg['rate_limits']['min_delay_sec'], cfg['rate_limits']['max_delay_sec']))

    if close_browser:
        print("🛑 Closing browser")
        context.close()
        browser.close()
        p.stop()

    sheets.update_metadata(cfg, 'last_extract')
    print("\n✅ Done extracting and saving to Google Sheet.")
