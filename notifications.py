import json
import os
import base64
from datetime import datetime, timezone
from urllib import parse, request


DELIVERY_STATUS_FILE = os.path.join(os.path.dirname(__file__), "delivery_status.json")


class NotificationDispatcher:
    """Send alerts to SMS/email providers and persist delivery outcomes."""

    def __init__(self, status_file=DELIVERY_STATUS_FILE):
        self.status_file = status_file

    def _append_status(self, row):
        payload = []
        if os.path.exists(self.status_file):
            try:
                with open(self.status_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception:
                payload = []
        payload.append(row)
        with open(self.status_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)

    def _status(self, provider, status, city, event, detail="", message_id=""):
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "status": status,
            "city": city,
            "event": event,
            "message_id": message_id,
            "detail": detail,
        }
        self._append_status(row)
        return row

    def send_twilio_sms(self, city, event, text):
        sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        sender = os.getenv("TWILIO_FROM_NUMBER", "").strip()
        targets = [x.strip() for x in os.getenv("TWILIO_TO_NUMBERS", "").split(",") if x.strip()]

        if not (sid and token and sender and targets):
            return [self._status("twilio", "SKIPPED", city, event, "twilio_not_configured")]

        out = []
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        for number in targets:
            try:
                data = parse.urlencode({"From": sender, "To": number, "Body": text}).encode("utf-8")
                req = request.Request(url, data=data, method="POST")
                basic = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
                req.add_header("Authorization", f"Basic {basic}")
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
                with request.urlopen(req, timeout=15) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    code = getattr(resp, "status", 200)
                if code in (200, 201):
                    out.append(self._status("twilio", "SENT", city, event, f"to={number}", body.get("sid", "")))
                else:
                    out.append(self._status("twilio", "FAILED", city, event, f"to={number};http={code}"))
            except Exception as exc:
                out.append(self._status("twilio", "FAILED", city, event, f"to={number};err={exc}"))
        return out

    def send_sendgrid_email(self, city, event, subject, body):
        api_key = os.getenv("SENDGRID_API_KEY", "").strip()
        sender = os.getenv("SENDGRID_FROM_EMAIL", "").strip()
        targets = [x.strip() for x in os.getenv("SENDGRID_TO_EMAILS", "").split(",") if x.strip()]

        if not (api_key and sender and targets):
            return [self._status("sendgrid", "SKIPPED", city, event, "sendgrid_not_configured")]

        out = []
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        for email in targets:
            payload = {
                "personalizations": [{"to": [{"email": email}]}],
                "from": {"email": sender},
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            }
            try:
                req = request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    method="POST",
                    headers=headers,
                )
                with request.urlopen(req, timeout=15) as resp:
                    code = getattr(resp, "status", 200)
                    msg_id = resp.headers.get("X-Message-Id", "")
                if code in (200, 202):
                    out.append(self._status("sendgrid", "SENT", city, event, f"to={email}", msg_id))
                else:
                    out.append(self._status("sendgrid", "FAILED", city, event, f"to={email};http={code}"))
            except Exception as exc:
                out.append(self._status("sendgrid", "FAILED", city, event, f"to={email};err={exc}"))
        return out

    def send_alert(self, city, event, text):
        subject = f"Farmer Alert: {event.upper()} in {city}"
        rows = []
        rows.extend(self.send_twilio_sms(city, event, text))
        if os.getenv("ENABLE_SENDGRID", "").strip().lower() in {"1", "true", "yes", "on"}:
            rows.extend(self.send_sendgrid_email(city, event, subject, text))
        return rows
