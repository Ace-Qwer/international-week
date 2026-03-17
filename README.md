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