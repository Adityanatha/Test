import os
import time
import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(BASE_DIR, "user_data/state.json")
COLLATERAL_DIR = os.path.join(BASE_DIR, "collateral")
SCREENSHOT_DIR = os.path.join(BASE_DIR, "_debug_screens")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def _get_context(context=None):
    if context:
        return None, context, context.new_page(), False
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=False, slow_mo=50)
    ctx = browser.new_context(
        storage_state=STATE_PATH,
        viewport={"width": 1400, "height": 1000},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.5993.90 Safari/537.36"
        ),
    )
    page = ctx.new_page()
    return p, ctx, page, True


class LinkedInSender:
    def __init__(self, day_gap=3, actually_click_send=True):
        self.day_gap = day_gap
        self.actually_click_send = actually_click_send
        self.p = None
        self.context = None
        self.page = None
        self.close_browser = False

    # -------------- browser lifecycle --------------
    def start_browser(self, context=None):
        print("⚙️ start_browser() called")
        self.p, self.context, self.page, self.close_browser = _get_context(context)
        print("🚀 Browser launched")

    def close_browser_if_needed(self):
        if self.close_browser:
            if self.context:
                self.context.close()
            if self.p:
                self.p.stop()
            print("🛑 Browser closed")

    # -------------- helpers --------------
    def _wait_ready(self):
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeout:
            pass

    def _debug_shot(self, tag):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCREENSHOT_DIR, f"{ts}_{tag}.png")
        try:
            self.page.screenshot(path=path, full_page=True)
            print(f"📸 Saved screenshot: {path}")
        except Exception as e:
            print(f"(screenshot fail) {e}")
    def _dump_buttons(self, tag="buttons_dump"):
        try:
            btns = self.page.locator("button").all()
            print(f"[dump] found {len(btns)} buttons")
            for i, b in enumerate(btns[:80]):
                try:
                    txt = (b.inner_text() or "").strip().replace("\n", " ")
                except Exception:
                    txt = "<no inner_text>"
                try:
                    cls = b.get_attribute("class") or ""
                except Exception:
                    cls = ""
                try:
                    aria = b.get_attribute("aria-label") or ""
                except Exception:
                    aria = ""
                print(f"[btn {i:02d}] text='{txt}' | class='{cls}' | aria-label='{aria}'")
        except Exception as e:
            print(f"[dump] failed: {e}")


    def _open_message_box(self, name):
        """Try multiple selectors/flows to open the message composer in Sales Navigator/LinkedIn."""
        page = self.page

        # PRIORITIZE your real-world button attributes first
        direct_selectors = [
            "xpath=(//section//span[text()='Message'])[1]",

        ]



        def _click_first_visible(selectors, click_desc):
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    print(f"[open_box] check visible: {sel}")
                    try:
                        loc.wait_for(state="visible", timeout=10000)
                    except Exception:
                        print(f"[open_box] not visible (wait timeout): {sel}")
                        continue

                    if loc.is_visible():
                        print(f"➡️ [open_box] clicking: {sel} ({click_desc})")
                        loc.click(timeout=10000)
                        self._wait_ready()
                        if self._composer_visible(name):
                            print("✅ [open_box] composer visible")
                            return True
                    else:
                        print(f"[open_box] not visible: {sel}")
                except Exception as e:
                    print(f"[open_box] selector failed {sel}: {e}")
            return False

        # pass 1: direct buttons
        if _click_first_visible(direct_selectors, "direct"):
            return True



        # Last resort: try to focus any contenteditable field to trigger composer
        try:

            editor_probe = page.locator("xpath=(//div[@id='message-overlay']//header//..//section)[1]")
            if editor_probe and editor_probe.wait_for(state="visible", timeout=2000):
                editor_probe.click()
                self._wait_ready()
                if self._composer_visible(name):
                    print("✅ [open_box] composer via editor probe")
                    return True
        except Exception as e:
            print(f"[open_box] editor probe failed: {e}")

        self._debug_shot("no_message_button")
        return False

    def _composer_visible(self, name):
        page = self.page
        selectors_to_try = [
            "xpath=//div[@id='message-overlay']//header//span[text()='" + name + "' or text()='New message']"

        ]

        for sel in selectors_to_try:
            try:
                locator = page.locator(sel)
                self._wait_ready()
                if locator:
                    print(f"[composer] visible: {sel}")
                    return True
            except Exception as e:
                print(f"[composera] selector failed: {sel} — {e}")
        return False

    def _type_message(self, text):
        """Type directly in the message composer without extra checks."""
        page = self.page

        # Assuming composer was already found and ready in prior steps
        editor = page.locator("xpath=//textarea[contains(@aria-label, 'Type your message here')]").first

        # Click and type directly
        editor.click()
        editor.fill("")  # Clear it quickly without keyboard controls
        editor.type(text, delay=10)  # Type the message


    # -------------- main API --------------
    def send_message(self, profile_url, message_text, name , scheduled_for_date=None, attachment_name=None):
        if not self.page:
            return False, "❌ Browser not started"

        # Build full URL from linkedin_id; also accept full URLs safely
        if str(profile_url).startswith("http"):
            complete_profile_url = profile_url
        else:
            complete_profile_url = f"https://www.linkedin.com/sales/lead/{profile_url}"

        try:
            print(f"➡️ goto: {complete_profile_url}")
            self.page.goto(complete_profile_url, timeout=60000)
            self._dump_buttons()
            self._debug_shot("after_goto")
            self._wait_ready()
        except Exception as e:
            self._debug_shot("goto_fail")
            return False, f"❌ Failed to open profile: {e}"

        # Try to open message composer
        if not self._open_message_box(name):
            return False, "❌ Could not open message box"

        # duplicate guard (best-effort)
        try:
            bubbles = self.page.locator("div.msg-s-message-list__event").all()
            history = [b.inner_text().strip() for b in bubbles][-9:]
            print("This history" + history[0])
        except Exception:
            history = []
        if any(message_text.strip() in (h or "") for h in history):
            return False, "⛔ Already sent"

        # day gap guard (best-effort)
        try:
            ts_nodes = self.page.locator("time.msg-s-message-group__timestamp").all()
            if ts_nodes:
                last_str = ts_nodes[-1].get_attribute("datetime")
                last_sent_date = datetime.datetime.fromisoformat(last_str).date() if last_str else None
            else:
                last_sent_date = None
        except Exception:
            last_sent_date = None
        if scheduled_for_date and last_sent_date:
            delta_days = (scheduled_for_date - last_sent_date).days
            if delta_days < self.day_gap:
                return False, f"⏳ Last message was {delta_days}d ago (< {self.day_gap}d gap)"

        # Type message
        try:
            self._type_message(message_text)
            time.sleep(0.5)

            # attachment (optional)
            if attachment_name:
                file_path = os.path.join(COLLATERAL_DIR, attachment_name)
                if os.path.exists(file_path):
                    try:
                        self.page.set_input_files("input[type='file']", file_path)
                        time.sleep(1.5)
                    except Exception:
                        pass

            # Send
            if self.actually_click_send:
                try:
                    # Primary send buttons
                    for sel in [
                        "xpath=//textarea[contains(@aria-label, 'Type your message here')]",
                        "xpath= //span[(text())='Send']",

                    ]:
                        btn = self.page.locator(sel)
                        time.sleep(2.5)
                        btn.click(timeout=3000)

                        if btn and btn.wait_for(state="visible", timeout=2000):
                            print("Buttons is visible")
                            btn.click(timeout=3000)
                            time.sleep(10)
                            break
                    else:
                        # keyboard fallback
                        print("Buttons is not visible")
                        self.page.keyboard.press("Enter")
                except Exception as e:
                    self._debug_shot("send_click_fail")
                    return False, f"❌ Failed to click Send: {e}"

            self._wait_ready()
            return True, "Sent"
        except Exception as e:
            self._debug_shot("type_or_send_fail")
            return False, f"❌ Failed to compose/send: {e}"
