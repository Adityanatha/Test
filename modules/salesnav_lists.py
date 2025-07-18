from playwright.sync_api import sync_playwright
import os
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_STATE = os.path.join(BASE_DIR, "user_data/state.json")


def _get_context(context=None):
    if context:
        return None, context, context.new_page(), False
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True, slow_mo=50)
    ctx = browser.new_context(
        storage_state=STORAGE_STATE,
        viewport={"width": 1280, "height": 1080},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.90 Safari/537.36"
    )
    page = ctx.new_page()
    return p, ctx, page, True



def add_search_results_to_list(search_url, list_url=None, list_name=None, context=None, limit=4):
    if not list_name:
        raise ValueError("❌ You must provide list_name (visible name of the list).")

    p, ctx, page, close_browser = _get_context(context)
    try:
        page.goto(search_url, wait_until="domcontentloaded")
        page.wait_for_selector("input[type='checkbox']", timeout=20000)
    except Exception as e:
        print(f"❌ Page.goto failed or selector not found: {e}")
        if close_browser:
            ctx.close()
            p.stop()
        return 0

    pages_processed = 0

    while pages_processed < limit:
        try:
            print(f"➡️ Processing page {pages_processed + 1}")

            first_checkbox = page.query_selector("xpath=//label[contains(@for, 'multi-selector-checkbox-ember')]")
            if first_checkbox:
                first_checkbox.click()
                time.sleep(1)
            else:
                print("⚠️ No selectable checkbox found.")
                break

            bulk_btn = page.query_selector("button:has-text('Save to list')")
            if not bulk_btn:
                print("⚠️ Bulk 'Save to list' button not found.")
                break
            bulk_btn.click()


            page.wait_for_selector(f"xpath=//ul[contains(@class, '_menu-container_aii1oi')]//button[.//span[text()='{list_name}']]", timeout=5000)
            list_option = page.query_selector(f"xpath=//ul[contains(@class, '_menu-container_aii1oi')]//button[.//span[text()='{list_name}']]")
            if not list_option:
                print(f"[!] List '{list_name}' not found.")
                break
            list_option.click()
            print(f"[!] Added to '{list_name}'.")

            print(f"[+] Leads added to list '{list_name}' on page {pages_processed + 1}")
            time.sleep(20)

            next_btn = page.query_selector("button[aria-label='Next']") or page.query_selector("button:has-text('Next')")
            if next_btn and not next_btn.is_disabled():
                next_btn.click()
                page.wait_for_selector("li[class*='artdeco-list__item']", timeout=10000)
                pages_processed += 1
            else:
                print("🚫 No next page or end of results.")
                break

        except Exception as e:
            print(f"[x] Error on page: {e}")
            break

    if close_browser:
        ctx.close()
        p.stop()

    print(f"✅ Done. Total pages processed: {pages_processed}")
    return pages_processed



def move_profile_to_list(page, list_name):
    try:
        save_btn = page.query_selector("button:has-text('Save')")
        if save_btn:
            save_btn.click()
            page.wait_for_selector("div.save-to-list-modal", timeout=5000)
            page.fill("input[placeholder='Search for a list']", list_name)
            page.wait_for_timeout(1000)
            list_option = page.query_selector(f"div.save-to-list-modal div:has-text('{list_name}')")
            if list_option:
                list_option.click()
                confirm = page.query_selector("div.save-to-list-modal button:has-text('Save')")
                if confirm:
                    confirm.click()
                    print(f"[+] Profile added to list '{list_name}'.")
                    return True
    except Exception as e:
        print(f"[x] Error saving profile to list: {e}")
    return False
