This is a weather-driven farmer alert system with a Tkinter admin dashboard, risk scoring, and audited operations.

Quick setup
- Set API key before running:
	- PowerShell: `$env:WEATHER_API_KEY="your_key_here"`
- Install dependency:
	- `py -m pip install requests`
- Run:
	- `py main.py`

Default users
- `admin / admin123` (full control)
- `farmer / farm2026` (analyst: no global send-all)
- `viewer / viewer123` (read-only + export)

New capabilities
- Passwords are stored as PBKDF2 hashes in `users.json`.
- Security tab supports status/query filtering and CSV export.
- Security logs include user role, session ID, source host/process.
- Region cards and smart panel show risk scores (0-100) with top factors.
- Weather fetch uses local fallback cache when API/network is unavailable.
- Incident workflow tab supports `open -> acknowledged -> assigned -> resolved` with notes.
- Interactive risk map uses GeoJSON points in `regions.geojson` with color overlays.
- Delivery tracking writes provider statuses to `delivery_status.json`.

Provider configuration (optional)
- Twilio SMS:
	- `TWILIO_ACCOUNT_SID`
	- `TWILIO_AUTH_TOKEN`
	- `TWILIO_FROM_NUMBER`
	- `TWILIO_TO_NUMBERS` (comma-separated)
- SendGrid email:
	- `SENDGRID_API_KEY`
	- `SENDGRID_FROM_EMAIL`
	- `SENDGRID_TO_EMAILS` (comma-separated)

If provider env vars are missing, dispatch is skipped and recorded as `SKIPPED` in delivery tracking.

SendGrid is disabled by default. To enable later, set `ENABLE_SENDGRID=true`.