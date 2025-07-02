# Utility functions for managing Sales Navigator lead lists via Playwright
from playwright.sync_api import sync_playwright
import os
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

def _get_context(context=None):
    """Return a Playwright page and context, optionally using an existing context."""
    if context:
        page = context.new_page()
        return None, context, page, False
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(
        storage_state="user_data/state.json",
        viewport={"width": 1280, "height": 1080},
    )
    page = ctx.new_page()
    return p, ctx, page, True


def add_search_results_to_list(search_url, list_url, limit=100, context=None):
    """Open a Sales Navigator search and save the first `limit` leads to a list."""
    p, ctx, page, close_browser = _get_context(context)

    page.goto(search_url)
    page.wait_for_timeout(5000)

    cards = page.query_selector_all("li.search-result")
    added = 0
    for card in cards:
        if added >= limit:
            break
        try:
            save_btn = card.query_selector("button:has-text('Save')")
            if not save_btn:
                continue
            save_btn.click()
            page.wait_for_selector("div.save-to-list-modal")
            page.fill("input[placeholder='Search for a list']", "")
            page.click(f"a[href='{list_url}']")
            confirm = page.query_selector("button:has-text('Save')")
            if confirm:
                confirm.click()
                added += 1
                time.sleep(1)
        except Exception:
            continue

    if close_browser:
        ctx.close()
        p.stop()

    return added


def move_profile_to_list(page, list_url):
    """On an open profile page, save the lead to the given list."""
    try:
        save_btn = page.query_selector("button:has-text('Save')")
        if save_btn:
            save_btn.click()
            page.wait_for_selector("div.save-to-list-modal")
            page.click(f"a[href='{list_url}']")
            confirm = page.query_selector("button:has-text('Save')")
            if confirm:
                confirm.click()
                page.wait_for_timeout(1000)
                return True
    except Exception:
        pass
    return False
