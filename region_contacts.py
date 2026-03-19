import json
import os
import re
import uuid
from datetime import datetime


CONTACTS_FILE = os.path.join(os.path.dirname(__file__), "region_contacts.json")


class RegionContactStore:
    """Persist and manage per-region SMS recipients."""

    def __init__(self, filename=CONTACTS_FILE, regions=None):
        self.filename = filename
        self.regions = list(regions or [])

    def _read(self):
        if not os.path.exists(self.filename):
            return {"regions": {}}
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict) and isinstance(payload.get("regions"), dict):
                return payload
        except Exception:
            pass
        return {"regions": {}}

    def _write(self, payload):
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)

    @staticmethod
    def normalize_number(raw):
        if raw is None:
            raise ValueError("Phone number is required.")

        n = str(raw).strip()
        n = re.sub(r"[\s\-()]+", "", n)
        if n.startswith("00"):
            n = "+" + n[2:]

        if not n.startswith("+"):
            raise ValueError("Phone number must be in E.164 format, e.g. +18392167702")
        if not re.fullmatch(r"\+[1-9]\d{7,14}", n):
            raise ValueError("Invalid phone number format. Use E.164 like +18392167702")
        return n

    def _ensure_region(self, payload, region):
        payload["regions"].setdefault(region, [])

    def list_regions(self):
        payload = self._read()
        known = set(self.regions)
        known.update(payload.get("regions", {}).keys())
        return sorted(known)

    def list_contacts(self, region):
        payload = self._read()
        rows = payload.get("regions", {}).get(region, [])
        rows = [r for r in rows if isinstance(r, dict)]
        return sorted(rows, key=lambda x: (x.get("name", ""), x.get("number", "")))

    def get_numbers(self, region):
        return [r.get("number") for r in self.list_contacts(region) if r.get("number")]

    def add_contact(self, region, name, number):
        if not region:
            raise ValueError("Region is required.")
        number = self.normalize_number(number)
        name = (name or "").strip() or "Farmer"

        payload = self._read()
        self._ensure_region(payload, region)

        if any(str(r.get("number")) == number for r in payload["regions"][region]):
            raise ValueError("This number already exists in the selected region.")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "number": number,
            "created_at": now,
            "updated_at": now,
        }
        payload["regions"][region].append(row)
        self._write(payload)
        return row

    def update_contact(self, region, contact_id, name=None, number=None):
        if not region or not contact_id:
            return None

        payload = self._read()
        rows = payload.get("regions", {}).get(region, [])
        updated = None

        new_name = (name or "").strip() if name is not None else None
        new_number = self.normalize_number(number) if number is not None else None

        if new_number:
            for row in rows:
                if row.get("id") != contact_id and row.get("number") == new_number:
                    raise ValueError("This number already exists in the selected region.")

        for row in rows:
            if row.get("id") != contact_id:
                continue
            if new_name is not None:
                row["name"] = new_name or "Farmer"
            if new_number is not None:
                row["number"] = new_number
            row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updated = row
            break

        if updated:
            self._write(payload)
        return updated

    def delete_contact(self, region, contact_id):
        if not region or not contact_id:
            return False

        payload = self._read()
        rows = payload.get("regions", {}).get(region, [])
        before = len(rows)
        rows = [r for r in rows if r.get("id") != contact_id]
        payload.setdefault("regions", {})[region] = rows
        changed = len(rows) != before

        if changed:
            self._write(payload)
        return changed
