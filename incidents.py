import json
import os
import uuid
from datetime import datetime


INCIDENTS_FILE = os.path.join(os.path.dirname(__file__), "incidents.json")


class IncidentStore:
    STATUSES = ("open", "acknowledged", "assigned", "resolved")

    def __init__(self, filename=INCIDENTS_FILE):
        self.filename = filename

    def _read(self):
        if not os.path.exists(self.filename):
            return []
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                payload = json.load(f)
                if isinstance(payload, list):
                    return payload
        except Exception:
            pass
        return []

    def _write(self, rows):
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=True, indent=2)

    def list_incidents(self):
        rows = self._read()
        return sorted(rows, key=lambda x: x.get("updated_at", ""), reverse=True)

    def create_incident(self, city, event, risk_score, notes="", created_by="system"):
        rows = self._read()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inc = {
            "id": uuid.uuid4().hex[:8],
            "city": city,
            "event": event,
            "risk_score": int(risk_score),
            "status": "open",
            "assigned_to": "",
            "notes": notes,
            "resolution_note": "",
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        rows.append(inc)
        self._write(rows)
        return inc

    def update_incident(self, incident_id, status=None, assigned_to=None, notes=None, resolution_note=None):
        rows = self._read()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updated = None
        for row in rows:
            if row.get("id") != incident_id:
                continue
            if status:
                row["status"] = status
            if assigned_to is not None:
                row["assigned_to"] = assigned_to
            if notes is not None:
                row["notes"] = notes
            if resolution_note is not None:
                row["resolution_note"] = resolution_note
            row["updated_at"] = now
            updated = row
            break
        if updated:
            self._write(rows)
        return updated
