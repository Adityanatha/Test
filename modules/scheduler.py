import datetime
import re
import random
import time
import streamlit as st
from modules.sheets import (
    get_all_leads,
    get_message_library,
    append_scheduled_message,
    get_scheduled_messages,
    get_company_sheet
)
from modules.sheets import update_lead_status
from modules.industry_mapper import assign_industry_bucket

class MessageScheduler:
    def __init__(self, config, filters=None, scheduled_messages=None, leads=None, company_sheet=None):
        self.config = config
        self.today = datetime.date.today()
        self.filters = filters or {}
        self.scheduled_messages = scheduled_messages or get_scheduled_messages(config)
        self.message_library = get_message_library(config)
        self.company_data = self._index_company_data(company_sheet)
        self.scheduled_by_lead = self._index_scheduled_messages()
        self.cached_leads = leads

    def _get_company_data(self):
        sheet = get_company_sheet(self.config)
        return {c["company_id"]: c for c in sheet.get_all_records() if c.get("company_id")}


    def _index_scheduled_messages(self):
        index = {}
        for msg in self.scheduled_messages:
            lead_id = msg.get("linkedin_id")
            if lead_id:
                index.setdefault(lead_id, []).append(msg)
        return index

    def _index_company_data(self, sheet_data):
        if not sheet_data:
            sheet_data = get_company_sheet(self.config)
        return {c["company_id"]: c for c in sheet_data if c.get("company_id")}

    def already_scheduled(self, lead, message_id):
        lead_id = lead.get("linkedin_id")
        return any(msg.get("message_id") == message_id for msg in self.scheduled_by_lead.get(lead_id, []))

    def get_approved_messages(self, lead):
        bucket = lead.get("industry_bucket", "general")
        include_stages = self.filters.get("include_stages", [])
        excluded_ids = self.filters.get("excluded_ids", [])

        return [
            m for m in self.message_library
            if m['status'] == 'approved'
               and (not include_stages or m['stage'] in include_stages)
               and m['industry_bucket'] in [bucket, 'general']
               and m['message_id'] not in excluded_ids
        ]

    def _extract_first_name(self, full_name):
        if not full_name:
            return ""
        return full_name.split()[0].replace(',', '').strip()

    def get_sent_stages(self, lead_id):
        return {msg.get("message_type") for msg in self.scheduled_by_lead.get(lead_id, [])}



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
        for placeholder, value in replacements.items():
            text = text.replace(placeholder, value)

        known_placeholders = set(replacements.keys())
        unresolved = [ph for ph in re.findall(r"\{\{.*?\}\}", text) if ph not in known_placeholders]
        return text, unresolved


    def auto_schedule(self, preview=False):
        existing_keys = {
            (msg["linkedin_id"], msg["message_id"])
            for msg in self.scheduled_messages
        }
        leads = self.cached_leads or get_all_leads(self.config)[0]
        scheduled_preview = []
        scheduled_count = 0
        skipped_due_to_placeholder = 0

        for lead in leads:
            if not lead.get("linkedin_id"):
                continue
            if str(lead.get("connection_level")).strip() != "1st":
                continue
            if lead.get("status") not in ["connected"]:
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

            chat_history = lead.get("chat_history", "").strip().lower()
            lead_id = lead['linkedin_id']
            scheduled = self.scheduled_by_lead.get(lead_id, [])
            already_scheduled_combinations = {
                (msg["message_id"], msg["linkedin_id"]) for msg in scheduled
            }

            max_total = self.filters.get("max_messages_per_lead", 10)
            messages_scheduled_count = 0
            missed_stages = []

            def _safe_schedule(msg, days_from_today):
                nonlocal scheduled_count, skipped_due_to_placeholder, messages_scheduled_count
                scheduled_date = self.today + datetime.timedelta(days=days_from_today)

                if messages_scheduled_count >= max_total:
                    return False
                if (msg['message_id'], lead['linkedin_id']) in already_scheduled_combinations:
                    return False

                message_text, unresolved = self._fill_placeholders(msg['template_text'], lead)
                if unresolved:
                    skipped_due_to_placeholder += 1
                    return False

                record = {
                    "rank": messages_scheduled_count + 1,
                    "message_id": msg['message_id'],
                    "linkedin_id": lead['linkedin_id'],
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
                    "industry": lead.get("industry", "")
                }

                scheduled_preview.append(record)
                if not preview:
                    append_scheduled_message(self.config, record, existing_keys=existing_keys)
                    time.sleep(3)
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

                stage_messages = [
                    msg for msg in all_messages
                    if msg.get("stage") == stage and msg.get("message_id") not in used_message_ids
                ]
                random.shuffle(stage_messages)

                if not stage_messages or max_messages.get(stage, 0) <= 0:
                    missed_stages.append(stage)
                    continue

                for msg in stage_messages:
                    if messages_scheduled_count >= max_total:
                        break
                    if self.already_scheduled(lead, msg['message_id']):
                        continue
                    if max_messages.get(stage, 0) <= 0:
                        continue

                    day_gap = int(self.filters.get("day_gaps", {}).get(stage, 5))

                    if stage == "friday_touch":
                        target_date = self.today + datetime.timedelta(days=start_day)
                        days_to_friday = (4 - target_date.weekday()) % 7
                        scheduled_day = target_date + datetime.timedelta(days=days_to_friday)
                        days_from_today = (scheduled_day - self.today).days
                        was_scheduled = _safe_schedule(msg, days_from_today)
                        if was_scheduled:
                            start_day = days_from_today + day_gap
                            max_messages[stage] -= 1
                            used_message_ids.add(msg['message_id'])
                    else:
                        was_scheduled = _safe_schedule(msg, start_day)
                        if was_scheduled:
                            start_day += day_gap
                            max_messages[stage] -= 1
                            used_message_ids.add(msg['message_id'])

            if preview and missed_stages:
                st.info(f"{lead.get('name')} missed stages: {missed_stages}")

            if not preview and messages_scheduled_count > 0:
                update_lead_status(lead_id, "in_progress")

        if preview:
            return scheduled_preview
        else:
            st.toast(f"✅ Scheduled {scheduled_count} messages.")
            if skipped_due_to_placeholder:
                st.warning(f"⚠️ Skipped {skipped_due_to_placeholder} messages with unresolved placeholders.")


    def clean_location_and_generate_timeslot(self, raw_location: str) -> str:
        if not raw_location:
            return "your timezone"

        junk_words = ["Greater", "County", "Metropolitan Area", "Area", "Region", "Republic"]
        parts = [p.strip() for p in raw_location.replace("/", ",").split(",") if p.strip()]
        cleaned = []

        for part in parts:
            if not any(junk.lower() in part.lower() for junk in junk_words):
                cleaned.append(part)

        location = cleaned[0] if cleaned else "your timezone"
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        hour = random.randint(10, 16)
        suffix = "AM" if hour < 12 else "PM"
        display_hour = hour if hour <= 12 else hour - 12
        weekday = random.choice(weekdays)
        return f"{weekday} at {display_hour} {suffix} in {location}"
