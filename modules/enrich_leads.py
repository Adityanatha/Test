import yaml
from modules import sheets
from playwright.sync_api import sync_playwright
import datetime
import time
import random
from datetime import timedelta

def enrich_missing_leads(cfg=None, context=None):
    if not cfg:
        cfg = yaml.safe_load(open("config.yaml"))

    leads, sheet = sheets.get_all_leads(cfg)
    print(f"🔍 Found {len(leads)} leads to enrich")

    if not context:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state="user_data/state.json")
        page = context.new_page()
        close_browser = True
    else:
        page = context.new_page()
        close_browser = False

    already_enriched_companies = sheets.get_existing_companies(cfg)
    enriched_this_session = set()
    all_companies_to_check = set()

    for idx, lead in enumerate(leads, 1):
        url = lead.get('profile_url')
        if not url:
            continue

        extracted_at_str = lead.get("extracted_at")
        needs_refresh = True
        if extracted_at_str:
            try:
                extracted_at = datetime.datetime.fromisoformat(extracted_at_str)
                needs_refresh = (datetime.datetime.utcnow() - extracted_at) > timedelta(days=10)
            except Exception:
                needs_refresh = True

        needs_enrichment = (
                needs_refresh or
                not lead.get('title') or
                lead.get('company') in [None, '', 'N/A', 'N/O'] or
                not lead.get('company_id') or
                not lead.get('connection_level')
        )

        if not needs_enrichment:
            if lead.get('company_id'):
                all_companies_to_check.add((lead['company_id'], lead.get('company')))
            continue

        try:
            print(f"\n🔎 [{idx}/{len(leads)}] Visiting {lead['name']} - {url}")
            page.goto(url)
            page.wait_for_timeout(random.randint(3000, 6000))

            title_el = page.query_selector('[data-anonymize="job-title"]')
            company_link_el = page.query_selector('a[data-anonymize="company-name"]')
            headline_el = page.query_selector('[data-anonymize="headline"]')
            location_el = page.query_selector('div.ivgSwkTiadiWAwYWsCzNPlqpMCdTHqLebSXGtk')

            connection_spans = page.query_selector_all('span._name-sublabel--no-pronunciation_sqh8tm span')
            for span in connection_spans:
                text = span.inner_text().strip()
                if text.lower() in ['1st', '2nd', '3rd']:
                    lead['connection_level'] = text
                    break

            if title_el:
                lead['title'] = title_el.inner_text().strip()

            if company_link_el:
                lead['company'] = company_link_el.inner_text().strip()
                company_url = company_link_el.get_attribute('href')
                if company_url and '/sales/company/' in company_url:
                    lead['company_id'] = company_url.split('/sales/company/')[-1].split('?')[0]

            if headline_el:
                lead['headline'] = headline_el.inner_text().strip()

            if location_el:
                loc_text = location_el.inner_text().strip().split('\n')[0]
                lead['location'] = loc_text

            lead['extracted_at'] = datetime.datetime.utcnow().isoformat()

            if lead.get('connection_level', '').lower().startswith("1st"):
                lead['status'] = 'connected'
                lead['connected_at'] = datetime.datetime.utcnow().isoformat()

            sheets.update_lead(cfg, lead)
            print(f"✅ Updated: {lead['name']} – {lead.get('title')} at {lead.get('company')} | ID: {lead.get('company_id')} | {lead.get('connection_level')}")

            company_id = lead.get('company_id')
            company_name = lead.get('company')

            if company_id:
                all_companies_to_check.add((company_id, company_name))

            time.sleep(random.randint(30, 90))

        except Exception as e:
            print(f"❌ Error updating {lead.get('name', 'Unknown')}: {e}")

    for company_id, company_name in all_companies_to_check:
        if company_id in enriched_this_session:
            continue

        enriched_this_session.add(company_id)
        company_row = sheets.get_company_row(cfg, company_id)
        needs_company_refresh = True
        if company_row:
            try:
                last_enriched = datetime.datetime.fromisoformat(company_row.get("enriched_at", ""))
                needs_company_refresh = (datetime.datetime.utcnow() - last_enriched) > timedelta(days=10)
            except Exception:
                needs_company_refresh = True

        if not company_row or needs_company_refresh or not company_row.get('company_iq') or not company_row.get('industry'):
            enrich_company_from_linkedin(page, cfg, company_id, company_name)

    if close_browser:
        context.close()
        browser.close()
        p.stop()

    print("✅ Enrichment done.")

def enrich_company_from_linkedin(page, cfg, company_id, company_name):
    try:
        print(f"\n🏢 Enriching company: {company_name} (ID: {company_id})")
        company_url = f"https://www.linkedin.com/sales/company/{company_id}"
        page.goto(company_url)
        page.wait_for_timeout(random.randint(4000, 7000))

        show_more_button = page.query_selector('//span[text()="Show more"]/ancestor::button')
        if show_more_button:
            try:
                show_more_button.click()
                page.wait_for_timeout(2000)
            except:
                pass

        about_section = page.query_selector("p[data-anonymize='company-blurb']")
        company_description = about_section.inner_text().strip() if about_section else ""

        company_iq_el = page.query_selector("section.org-insights-module__content")
        company_iq_text = company_iq_el.inner_text().strip() if company_iq_el else ""

        if "Sorry, we’re currently experiencing high demand." in company_iq_text:
            company_iq = "Sorry, we’re currently experiencing high demand."
        else:
            company_iq = company_iq_text[:300] if company_iq_text else ""

        industry_el = page.query_selector("span[data-anonymize='industry']")
        industry = industry_el.inner_text().strip() if industry_el else ""

        company_data = {
            'company_id': company_id,
            'company_name': company_name,
            'description': company_description,
            'company_iq': company_iq,
            'industry': industry,
            'enriched_at': datetime.datetime.utcnow().isoformat()
        }

        existing = sheets.get_company_row(cfg, company_id)
        if existing:
            sheets.update_company(cfg, company_data)
            print(f"♻️ Updated company: {company_name}")
        else:
            sheets.append_company(cfg, company_data)
            print(f"✅ Added new company: {company_name}")

    except Exception as e:
        print(f"❌ Error enriching company {company_name}: {e}")
