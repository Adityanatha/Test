import datetime
import re
import random
import time
import os
import streamlit as st
from modules.sheets import (
    get_all_leads,
    get_message_library,
    append_scheduled_message,
    get_scheduled_messages,
    get_company_sheet,
    update_lead_status
)
from modules.industry_mapper import assign_industry_bucket
from modules.send import LinkedInSender  # ensure this exists


class MessageScheduler:
    """Schedules and sends LinkedIn messages.

    Key decisions in this version:
    - We **do not** persist `profile_url`. We only use `linkedin_id` and build the URL in the sender.
    - We read message body from `message_text` (fallback to `message`).
    - Robust logging + guards for missing fields.
    - Backoff on append. Cleaned UI feedback.
    """

    def __init__(self, config, filters=None, leads=None, scheduled_messages=None, company_sheet=None, mode="full"):
        self.config = config
        self.filters = filters or {}
        self.mode = mode
        self.today = datetime.date.today()

        # Load data
        self.scheduled_messages = scheduled_messages or get_scheduled_messages(config)
        self.message_library = get_message_library(config)

        # Cache
        self.cached_leads = leads
        self.scheduled_by_lead = self._index_scheduled_messages()

        # Company data (optional)
        self.company_data = {}
        if self.mode == "full":
            sheet_data = company_sheet or get_company_sheet(config)
            self.company_data = self._index_company_data(sheet_data)

    # =====================
    # Sending (runner)
    # =====================
    def run_scheduler(self, for_date):
        count = 0
        results = []

        sender = LinkedInSender(day_gap=self.filters.get("day_gap", 1))
        sender.start_browser()

        try:
            for msg in self.scheduled_messages:
                try:
                    lid = msg.get("linkedin_id")
                    uname = msg.get("name")
                    mid = msg.get("message_id")
                    status = msg.get("status")
                    print(f"\n---\nProcessing message: {lid} | {mid} | status: {status}")

                    # Must be scheduled
                    if status != "scheduled":
                        print(f"Skipping {lid} because status is not scheduled")
                        continue

                    # Must be due by run date
                    msg_date = datetime.datetime.strptime(msg["scheduled_for"], "%Y-%m-%d").date()
                    print(f"Scheduled for: {msg_date}, Running up to: {for_date}")
                    if msg_date > for_date:
                        print(f"Skipping {lid} because msg_date > run_date")
                        continue

                    # Must have linkedin_id
                    if not lid:
                        print(f"❌ 'linkedin_id' missing for message_id={mid}, skipping!")
                        results.append((lid, mid, "❌ 'linkedin_id' missing"))
                        continue

                    # Extract message text
                    text = msg.get("message_text") or msg.get("message")
                    if not text or not str(text).strip():
                        print(f"❌ message text missing for message_id={mid}")
                        results.append((lid, mid, "❌ message text missing"))
                        continue

                    # Send if backdate on OR due today
                    if self.filters.get("backdate") or msg_date == for_date:
                        print(f"Calling send_message for {lid}")
                        success, info = sender.send_message(
                            profile_url=lid,  # sender builds full URL
                            message_text=text,
                            name = uname,
                            scheduled_for_date=msg_date,
                            attachment_name=msg.get("attachment_name")
                        )
                        print(f"send_message result: {success}, {info}")
                        results.append((lid, mid, info))
                        count += 1

                    # Daily cap
                    if count >= self.filters.get("max_messages_per_day", 100):
                        print("Reached max_messages_per_day limit.")
                        break

                except Exception as e:
                    print(f"Exception for {msg.get('linkedin_id')}: {e}")
                    results.append((msg.get("linkedin_id"), msg.get("message_id"), f"❌ {str(e)}"))
        finally:
            sender.close_browser_if_needed()

        return results

    # =====================
    # Indexing helpers
    # =====================
    def _index_company_data(self, sheet_data):
        if not sheet_data:
            sheet_data = get_company_sheet(self.config)
        return {c["company_id"]: c for c in sheet_data if c.get("company_id")}

    def _index_scheduled_messages(self):
        index = {}
        for msg in self.scheduled_messages:
            lid = msg.get("linkedin_id")
            if lid:
                index.setdefault(lid, []).append(msg)
        return index

    def already_scheduled(self, lead, message_id):
        lid = lead.get("linkedin_id")
        return any(m.get("message_id") == message_id for m in self.scheduled_by_lead.get(lid, []))

    # =====================
    # Message templating
    # =====================
    def _extract_first_name(self, full_name):
        if not full_name:
            return ""
        return full_name.split()[0].replace(',', '').strip()

    def _fill_placeholders(self, text, lead):
        first_name = self._extract_first_name(lead.get("name", ""))
        try:
            timeslot = self.clean_location_and_generate_timeslot(lead.get("location", "") or "")
        except Exception:
            timeslot = "your timezone"

        replacements = {
            "{{first_name}}": first_name,
            "{{company}}": lead.get("company", ""),
            "{{timeslot}}": timeslot
        }
        for ph, val in replacements.items():
            text = text.replace(ph, val)

        known = set(replacements.keys())
        unresolved = [ph for ph in re.findall(r"\{\{.*?\}\}", text) if ph not in known]
        return text, unresolved

    # =====================
    # Library filtering
    # =====================
    def get_approved_messages(self, lead):
        bucket = lead.get("industry_bucket", "general")
        include_stages = self.filters.get("include_stages", [])
        excluded_ids = self.filters.get("excluded_ids", [])
        return [
            m for m in self.message_library
            if m.get('status') == 'approved'
               and (not include_stages or m.get('stage') in include_stages)
               and m.get('industry_bucket') in [bucket, 'general']
               and m.get('message_id') not in excluded_ids
        ]

    # =====================
    # Persistence with backoff
    # =====================
    def _safe_append_with_backoff(self, record, max_retries=3):
        for attempt in range(max_retries):
            try:
                append_scheduled_message(self.config, record)
                time.sleep(2)  # small delay
                return
            except Exception as e:
                if "429" in str(e) or "Quota exceeded" in str(e):
                    wait_time = 10 * (attempt + 1)
                    st.warning(f"⏳ Quota hit. Waiting {wait_time}s before retrying... (attempt {attempt + 1})")
                    time.sleep(wait_time)
                else:
                    st.error(f"❌ Failed to append message: {e}")
                    raise

    # =====================
    # Auto-scheduling
    # =====================
    def auto_schedule(self, preview=False):
        leads = self.cached_leads or get_all_leads(self.config)[0]
        scheduled_preview = []
        scheduled_count = 0
        skipped_due_to_placeholder = 0

        # Existing combos to avoid dupes
        existing_keys = {(m.get("linkedin_id"), m.get("message_id")) for m in self.scheduled_messages}

        for lead in leads:
            # Eligibility
            if not lead.get("linkedin_id") or lead.get("status") != "connected" or str(lead.get("connection_level")).strip() != "test":
                continue

            company_id = lead.get("company_id")
            if not lead.get("industry") and company_id in self.company_data:
                lead["industry"] = self.company_data[company_id].get("industry")

            if lead.get("industry") in ["IT Services", "IT Consulting", "IT Services and IT Consulting"]:
                continue

            lead = assign_industry_bucket(lead)
            bucket = lead.get("industry_bucket", "general")
            if self.filters.get("industries") and bucket not in self.filters["industries"]:
                continue

            chat_history = (lead.get("chat_history", "").strip().lower())
            lid = lead['linkedin_id']
            scheduled = self.scheduled_by_lead.get(lid, [])
            already_scheduled_combos = {(m.get("message_id"), m.get("linkedin_id")) for m in scheduled}

            max_total = self.filters.get("max_messages_per_lead", 10)
            messages_scheduled_count = 0
            missed_stages = []

            def _safe_schedule(msg, days_from_today):
                nonlocal scheduled_count, skipped_due_to_placeholder, messages_scheduled_count
                scheduled_date = self.today + datetime.timedelta(days=days_from_today)

                if messages_scheduled_count >= max_total or (msg['message_id'], lid) in already_scheduled_combos or (lid, msg['message_id']) in existing_keys:
                    return False

                message_text, unresolved = self._fill_placeholders(msg['template_text'], lead)
                if unresolved:
                    skipped_due_to_placeholder += 1
                    return False

                attachment_name = ""
                if msg.get("type") == "attachment" and msg.get("asset_link"):
                    attachment_name = os.path.basename(msg["asset_link"])

                record = {
                    "rank": messages_scheduled_count + 1,
                    "message_id": msg['message_id'],
                    "linkedin_id": lid,
                    "message_text": message_text,
                    "message_type": msg['type'],
                    "scheduled_for": scheduled_date.isoformat(),
                    "status": "scheduled",
                    "industry_bucket": bucket,
                    "created_at": datetime.datetime.now().isoformat(),
                    "chat_history": chat_history,
                    "name": lead.get("name", ""),
                    "title": lead.get("title", ""),
                    "company": lead.get("company", ""),
                    "industry": lead.get("industry", ""),
                    "attachment_name": attachment_name
                }

                scheduled_preview.append(record)
                if not preview:
                    self._safe_append_with_backoff(record)
                    time.sleep(1)
                scheduled_count += 1
                messages_scheduled_count += 1
                return True

            all_messages = self.get_approved_messages(lead)
            max_messages = self.filters.get("max_per_stage", {}).copy()
            stage_order = self.filters.get("include_stages", [
                "intro", "value", "collateral", "nurture",
                "news", "knowledge", "friday_touch", "cta", "follow_up"
            ])
            start_day = 0
            used_message_ids = set()

            for stage in stage_order:
                if messages_scheduled_count >= max_total:
                    break

                stage_messages = [m for m in all_messages if m.get("stage") == stage and m.get("message_id") not in used_message_ids]
                random.shuffle(stage_messages)

                if not stage_messages or max_messages.get(stage, 0) <= 0:
                    missed_stages.append(stage)
                    continue

                for m in stage_messages:
                    if messages_scheduled_count >= max_total:
                        break
                    if self.already_scheduled(lead, m['message_id']):
                        continue
                    if max_messages.get(stage, 0) <= 0:
                        continue

                    day_gap = int(self.filters.get("day_gaps", {}).get(stage, 5))

                    if stage == "friday_touch":
                        target_date = self.today + datetime.timedelta(days=start_day)
                        days_to_friday = (4 - target_date.weekday()) % 7
                        scheduled_day = target_date + datetime.timedelta(days=days_to_friday)
                        days_from_today = (scheduled_day - self.today).days
                        was_scheduled = _safe_schedule(m, days_from_today)
                        if was_scheduled:
                            start_day = days_from_today + day_gap
                            max_messages[stage] -= 1
                            used_message_ids.add(m['message_id'])
                    else:
                        was_scheduled = _safe_schedule(m, start_day)
                        if was_scheduled:
                            start_day += day_gap
                            max_messages[stage] -= 1
                            used_message_ids.add(m['message_id'])

            if preview and missed_stages:
                st.info(f"{lead.get('name')} missed stages: {missed_stages}")

            if not preview and messages_scheduled_count > 0:
                update_lead_status(self.config, {"linkedin_id": lid, "status": "in_progress"})

        if preview:
            return scheduled_preview
        else:
            st.toast(f"✅ Scheduled {scheduled_count} messages.")
            if skipped_due_to_placeholder:
                st.warning(f"⚠️ Skipped {skipped_due_to_placeholder} messages with unresolved placeholders.")

    # =====================
    # Misc helper
    # =====================
    def clean_location_and_generate_timeslot(self, raw_location: str) -> str:
        if not raw_location:
            return "your timezone"
        junk_words = ["Greater", "County", "Metropolitan Area", "Area", "Region", "Republic"]
        parts = [p.strip() for p in raw_location.replace("/", ",").split(",") if p.strip()]
        cleaned = [part for part in parts if not any(junk.lower() in part.lower() for junk in junk_words)]
        location = cleaned[0] if cleaned else "your timezone"
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        hour = random.randint(10, 16)
        suffix = "AM" if hour < 12 else "PM"
        display_hour = hour if hour <= 12 else hour - 12
        weekday = random.choice(weekdays)
        return f"{weekday} at {display_hour} {suffix} in {location}"