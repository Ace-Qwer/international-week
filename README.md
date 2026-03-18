This is a weather-driven farmer alert system with a Tkinter admin dashboard, risk scoring, and audited operations.

Getting Started (For Team Members)

**Clone and setup in 3 steps:**

```bash
# 1. Clone the repo
git clone https://github.com/Ace-Qwer/international-week.git
cd international-week

# 2. Install dependencies and setup .env
pip install requests python-dotenv
cp .env.example .env

# 3. Add credentials to .env (use editor or command below)
# Edit .env and add:
# - WEATHER_API_KEY=6471d6b96a0646ab81f90409261703
# - TWILIO credentials (if you want SMS alerts)

# 4. Run!
python main.py
```

**Login with:**
- Username: `admin` / Password: `admin123`

---

Quick setup (Detailed)

1. **Install dependencies:**
   ```bash
   pip install requests python-dotenv
   ```

2. **Create `.env` file:**
   ```bash
   cp .env.example .env
   ```

3. **Edit `.env` with required credentials:**
   ```
   # REQUIRED - Weather alerts won't work without this
   WEATHER_API_KEY=6471d6b96a0646ab81f90409261703
   
   # OPTIONAL - For SMS alerts to farmers
   TWILIO_ACCOUNT_SID=your_account_sid
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_FROM_NUMBER=+1234567890
   ```

4. **Run the app:**
   ```bash
   python main.py
   ```
   Login as `admin` / `admin123`

Default users
- `admin / admin123` (full control)
- `farmer / farm2026` (analyst: no global send-all)
- `viewer / viewer123` (read-only + export)

SMS Contact Manager (NEW)
- **CONTACTS button** in dashboard header launches dedicated contact manager window
- **Region-wise recipient lists** — manage farmer phone numbers per region
- **Bulk add** — paste multiple phone numbers at once
- **CSV import/export** — import from spreadsheet, export region contacts
- **Test alerts** — send test SMS to all numbers in a region
- **Region counts** — see how many farmers are registered per region
- Phone numbers stored in `region_contacts.json` (not committed to repo)

Adding Farmers to Alert Zone
1. Click **CONTACTS** button
2. Select a region from the left list
3. Click **"Add Contact"** and enter farmer name + phone number (E.164 format: +[country code][number])
4. Click **"Send Test Alert"** to verify SMS sending works
5. Once setup, all region alerts automatically send SMS to saved numbers

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