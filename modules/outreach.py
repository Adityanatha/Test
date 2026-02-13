import yaml
import random
import time
import os
import datetime
import traceback
from playwright.sync_api import sync_playwright
from modules.salesnav_lists import move_profile_to_list
from modules.message_gen import generate_connection, generate_followup
from modules import sheets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

def send_invites(context=None):
    print("\n▶️ Starting invite process...")
    cfg = yaml.safe_load(open(CONFIG_FILE))
    leads, _ = sheets.get_all_leads(cfg)
    leads = [l for l in leads if l.get('status') == 'new']
    print(f"🔍 Found {len(leads)} leads marked as 'new'.")

    if not leads:
        print("❌ No leads to process. Exiting early.")
        return

    if context:
        print("🔐 Using existing login context")
        page = context.new_page()
        close_browser = False
        p = None
    else:
        print("🚀 Launching new browser session...")
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            storage_state="user_data/state.json",
            viewport={"width": 1280, "height": 1080}
        )
        page = context.new_page()
        close_browser = True

    for i, l in enumerate(leads):
        print(f"\n🔁 [{i+1}/{len(leads)}] Visiting: {l['name']} ({l['title']} at {l['company']})")

        try:
            page.goto(l['profile_url'], timeout=30000)
            page.wait_for_selector('button[aria-label="Open actions overflow menu"]', timeout=10000)
            page.wait_for_timeout(2000)

            connection_label_el = page.query_selector('._name-sublabel--no-pronunciation_sqh8tm span:nth-child(2)')
            connection_degree = connection_label_el.text_content().strip() if connection_label_el else "N/A"
            print(f"🔗 Connection degree: {connection_degree}")

            if connection_degree == "1st":
                print("⚡️ Skipping invite: Already a 1st-degree connection.")
                l['status'] = 'connected'
                sheets.update_lead(cfg, l)
                continue

            # Check if "Connect — Pending" button is visible
            pending_btn = page.query_selector('//button[@disabled][div/div[text()="Connect — Pending"]]')
            if pending_btn:
                print(f"⏳ Connect already pending for {l['name']}. Marking as invited.")
                l['status'] = 'invited'
                l['invited_at'] = datetime.datetime.utcnow().isoformat()
                sheets.update_lead(cfg, l)
                continue

            print("📌 Not a 1st-degree — opening More menu to find Connect.")
            dropdown_btn = page.query_selector('button[aria-label="Open actions overflow menu"]')
            if dropdown_btn:
                dropdown_btn.click()
                page.wait_for_timeout(1000)

            connect_btn = page.query_selector("button:has-text('Connect')")
            if not connect_btn:
                print("❌ Connect button not found. Skipping.")
                continue

            if not connect_btn.is_enabled():
                print(f"⚠️ Connect button for {l['name']} is disabled. Marking as invited.")
                l['status'] = 'invited'
                l['invited_at'] = datetime.datetime.utcnow().isoformat()
                sheets.update_lead(cfg, l)
                continue

            connect_btn.click()
            page.wait_for_timeout(1500)

            # Check if email input is shown — means invite can't be sent
            email_input = page.query_selector("input#connect-cta-form__email")
            if email_input:
                print(f"📩 Email required to connect with {l['name']}. Marking as email_needed.")
                l['status'] = 'email_needed'
                l['invited_at'] = datetime.datetime.utcnow().isoformat()
                sheets.update_lead(cfg, l)
                continue


            note_btn = page.query_selector("button:has-text('Add a note')")
            if note_btn:
                note_btn.click()
                msg = generate_connection({'name': l['name'], 'title': l['title'], 'company': l['company']}, cfg)
                page.fill("textarea", msg)
                send_btn = page.query_selector("button:has-text('Send')")
                if send_btn:
                    send_btn.click()
                    print(f"✅ Invite with note sent to {l['name']}")
                else:
                    print("❌ Send button not found after adding note.")
                    continue
            else:
                fallback_send = page.query_selector("button:has-text('Send')")
                if fallback_send:
                    fallback_send.click()
                    print(f"✅ Sent default invite to {l['name']}")
                else:
                    print("❌ Couldn't send invite. Skipping.")
                    continue

            l['status'] = 'invited'
            l['invited_at'] = datetime.datetime.utcnow().isoformat()
            sheets.update_lead(cfg, l)

            invited_list = cfg.get('linkedin', {}).get('lists', {}).get('invited')
            if invited_list:
                move_profile_to_list(page, invited_list)

        except Exception as e:
            print(f"❌ Error inviting {l['name']}: {e}")
            traceback.print_exc()

        wait_time = random.randint(cfg['rate_limits']['min_delay_sec'], cfg['rate_limits']['max_delay_sec'])
        print(f"⏳ Waiting {wait_time} seconds before next...")
        time.sleep(wait_time)

    if close_browser:
        browser.close()
        p.stop()

    sheets.update_metadata(cfg, 'last_outreach')
    print("\n✅ Finished sending invites.")


def process_followups(context=None):
    print("\n🔁 Starting follow-up process...")
    cfg = yaml.safe_load(open(CONFIG_FILE))
    leads, _ = sheets.get_all_leads(cfg)
    leads = [l for l in leads if l.get('status') == 'connected' and not l.get('followup_sent_at')]
    print(f"🔍 Found {len(leads)} leads eligible for follow-up.")

    if not leads:
        print("❌ No connections to follow up with. Exiting.")
        return

    if context:
        print("🔐 Using existing login context")
        page = context.new_page()
        close_browser = False
        p = None
    else:
        print("🚀 Launching new browser session...")
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            storage_state="user_data/state.json",
            viewport={"width": 1280, "height": 1080}
        )
        page = context.new_page()
        close_browser = True

    for i, l in enumerate(leads):
        print(f"\n💬 [{i+1}/{len(leads)}] Sending follow-up to: {l['name']}")

        try:
            page.goto(l['profile_url'], timeout=30000)
            page.wait_for_timeout(3000)

            msg_btn = page.query_selector("button:has-text('Message')")
            if not msg_btn:
                print("❌ Message button not found. Skipping.")
                continue

            msg = generate_followup({'name': l['name']})
            msg_btn.click()
            page.wait_for_timeout(1000)
            page.fill("textarea", msg)

            send_btn = page.query_selector("button:has-text('Send')")
            if send_btn:
                send_btn.click()
                print(f"📨 Follow-up sent to: {l['name']}")
                l['followup_sent_at'] = datetime.datetime.utcnow().isoformat()
                sheets.update_lead(cfg, l)
            else:
                print("❌ Send button not found after typing message.")

        except Exception as e:
            print(f"❌ Error sending follow-up to {l['name']}: {e}")
            traceback.print_exc()

        wait_time = random.randint(cfg['rate_limits']['min_delay_sec'], cfg['rate_limits']['max_delay_sec'])
        print(f"⏳ Waiting {wait_time} seconds before next...")
        time.sleep(wait_time)

    if close_browser:
        browser.close()
        p.stop()

    sheets.update_metadata(cfg, 'last_followup')
    print("\n✅ Finished processing follow-ups.")
