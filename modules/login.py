from playwright.sync_api import sync_playwright


def manual_login():
    """Open LinkedIn login in a persistent browser and wait for manual auth."""
    p = sync_playwright().start()
    context = p.chromium.launch_persistent_context(
        "user_data",
        headless=False,
    )
    page = context.new_page()
    page.goto("https://www.linkedin.com/login")
    input("Complete login in the opened browser and press Enter here...")
    context.storage_state(path="user_data/state.json")
    return p, context
