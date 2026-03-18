"""
Farmer Alert — Admin Platform
Login-protected admin dashboard.  Visual style based on MAIN_STYLE.py.
"""
import math
import os
import csv
import hashlib
import hmac
import json
import platform
import secrets
import threading
import time
import uuid
from datetime import datetime

import pyotp
import qrcode
from PIL import Image, ImageTk

import tkinter as tk
from tkinter import messagebox, ttk

from alerts import WeatherAlertSystemXML
from incidents import IncidentStore
from notifications import NotificationDispatcher
from weather import fetch_forecast, locations

# ── Auth ──────────────────────────────────────────────────────────────────────
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 30
SECURITY_LOG_FILE = os.path.join(
    os.path.dirname(__file__), "security_audit.log")
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")
MAP_GEOJSON_FILE = os.path.join(os.path.dirname(__file__), "regions.geojson")

# ── Palette (deep-blue dark with sharp colors) ──────────────────────────────
C = {
    "bg":       "#070d1a",
    "bg2":      "#0f1419",
    "bg3":      "#192230",
    "card":     "#0f1b2e",
    "border":   "#2a475f",
    "accent":   "#00d4ff",    # Sharp cyan
    "accent2":  "#00f0ff",    # Bright cyan
    "warn":     "#ffaa00",    # Sharp orange
    "danger":   "#ff3333",    # Sharp red
    "ok":       "#00ff66",    # Bright green
    "text":     "#f0f4f8",
    "muted":    "#7a8898",
    "selected": "#1a3a5f",
}

WEATHER_ICONS = {
    "sunny": "☀", "partly cloudy": "⛅", "overcast": "☁",
    "rain": "🌧", "drizzle": "🌦", "thunderstorm": "⛈",
    "snow": "❄", "fog": "🌫", "clear": "✨", "windy": "💨",
}

DANGER_EVENTS = {"storm", "flood", "heatwave"}
POSSIBLE_EVENTS = {"cold_snap", "drought", "rain"}

# Simplified country outline for a visible basemap behind risk points.
TANZANIA_OUTLINE = [
    (29.34, -1.00),
    (30.50, -1.55),
    (31.55, -1.20),
    (32.65, -1.55),
    (33.90, -1.00),
    (35.10, -1.45),
    (36.70, -1.10),
    (38.20, -2.30),
    (39.10, -4.50),
    (40.15, -5.80),
    (40.40, -8.70),
    (39.60, -10.20),
    (38.40, -11.00),
    (36.50, -11.65),
    (34.20, -11.75),
    (32.00, -11.45),
    (30.90, -10.40),
    (29.95, -8.40),
    (29.20, -6.80),
    (29.05, -4.30),
    (29.34, -1.00),
]


def _hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000
    )
    return {"salt": salt, "hash": hashed.hex()}


def _verify_password(password, record):
    if not isinstance(record, dict) or "salt" not in record or "hash" not in record:
        return False
    calc = _hash_password(password, salt=record["salt"])["hash"]
    return hmac.compare_digest(calc, record.get("hash", ""))


def _generate_totp_secret():
    """Generate a new TOTP secret for a user."""
    return pyotp.random_base32()


def _get_totp_uri(username, secret):
    """Generate TOTP URI for QR code."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="Farmer Alert")


def _verify_totp_code(secret, code):
    """Verify a TOTP code against the secret."""
    if not secret:
        return True  # No 2FA setup, allow login
    totp = pyotp.TOTP(secret)
    return totp.verify(code)


def _ensure_user_store():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict) and isinstance(payload.get("users"), list):
                # Migrate existing users to include totp_secret if missing
                for user in payload["users"]:
                    if "totp_secret" not in user:
                        user["totp_secret"] = None
                with open(USERS_FILE, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=True, indent=2)
                return
        except Exception:
            pass

    seed_users = [
        {"username": "admin", "password": "admin123", "role": "admin"},
        {"username": "farmer", "password": "farm2026", "role": "analyst"},
        {"username": "viewer", "password": "viewer123", "role": "viewer"},
    ]
    users = []
    for user in seed_users:
        users.append(
            {
                "username": user["username"],
                "role": user["role"],
                "password": _hash_password(user["password"]),
                "totp_secret": None,  # No 2FA initially
            }
        )
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, ensure_ascii=True, indent=2)


def _authenticate_user(username, password):
    _ensure_user_store()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None

    for user in payload.get("users", []):
        if user.get("username") != username:
            continue
        if _verify_password(password, user.get("password")):
            return {
                "username": username,
                "role": user.get("role", "viewer"),
                "totp_secret": user.get("totp_secret"),
                "requires_2fa": user.get("totp_secret") is not None
            }
        return None
    return None


def _setup_user_2fa(username, secret):
    """Set up 2FA for a user."""
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return False

    for user in payload.get("users", []):
        if user.get("username") == username:
            user["totp_secret"] = secret
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=True, indent=2)
            return True
    return False


def _verify_user_2fa(username, code):
    """Verify 2FA code for a user."""
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return False

    for user in payload.get("users", []):
        if user.get("username") == username:
            secret = user.get("totp_secret")
            return _verify_totp_code(secret, code)
    return False


def _disable_user_2fa(username):
    """Disable 2FA for a user."""
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return False

    for user in payload.get("users", []):
        if user.get("username") == username:
            user["totp_secret"] = None
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=True, indent=2)
            return True
    return False


def _parse_audit_line(line):
    parts = [p.strip() for p in line.split("|")]
    entry = {"raw": line}
    if parts:
        entry["timestamp"] = parts[0]
    for part in parts[1:]:
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        entry[k.strip()] = v.strip()
    return entry


def _ensure_geojson_file():
    if os.path.exists(MAP_GEOJSON_FILE):
        return
    features = []
    for city, lat, lon in locations:
        features.append(
            {
                "type": "Feature",
                "properties": {"name": city},
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        )
    payload = {"type": "FeatureCollection", "features": features}
    with open(MAP_GEOJSON_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def _wx_icon(text):
    t = text.lower()
    for k, v in WEATHER_ICONS.items():
        if k in t:
            return v
    return "🌡"


def _lighten(hex_color):
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return f"#{min(r+30,255):02x}{min(g+30,255):02x}{min(b+30,255):02x}"


def _event_level(event):
    if event in DANGER_EVENTS:
        return "danger"
    if event in POSSIBLE_EVENTS:
        return "possible"
    return "safe"


def audit_log(
    user,
    action,
    status="INFO",
    city="-",
    event="-",
    detail="",
    role="-",
    session_id="-",
):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source = f"{platform.node()}:{os.getpid()}"
    line = (
        f"{ts} | user={user or '-'} | status={status} | action={action} "
        f"| role={role} | session={session_id} | city={city} "
        f"| event={event} | source={source} | detail={detail}\n"
    )
    try:
        with open(SECURITY_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # Security log should never crash the app.
        pass
    return line.rstrip("\n")


def read_audit_tail(limit=250):
    if not os.path.exists(SECURITY_LOG_FILE):
        return []
    try:
        with open(SECURITY_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [ln.rstrip("\n") for ln in lines[-limit:]]
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
#  Animated radar widget
# ══════════════════════════════════════════════════════════════════════════════
class RadarWidget(tk.Canvas):
    def __init__(self, parent, size=44, **kw):
        super().__init__(parent, width=size, height=size,
                         bg=C["bg2"], highlightthickness=0, **kw)
        self.size = size
        self.cx = size // 2
        self.cy = size // 2
        self.angle = 0
        self._draw()

    def _draw(self):
        self.delete("all")
        s, cx, cy = self.size, self.cx, self.cy
        for r in (s * 0.45, s * 0.32, s * 0.18):
            self.create_oval(cx - r, cy - r, cx + r, cy + r,
                             outline=C["border"], width=1)
        rad = math.radians(self.angle)
        ex = cx + s * 0.45 * math.cos(rad)
        ey = cy - s * 0.45 * math.sin(rad)
        self.create_line(cx, cy, ex, ey, fill=C["accent"], width=2)
        self.create_oval(cx - 3, cy - 3, cx + 3, cy + 3,
                         fill=C["accent"], outline="")
        self.angle = (self.angle + 3) % 360
        self.after(30, self._draw)


# ══════════════════════════════════════════════════════════════════════════════
#  Stat card
# ══════════════════════════════════════════════════════════════════════════════
class StatCard(tk.Frame):
    def __init__(self, parent, label, value="0", color=None, **kw):
        super().__init__(parent, bg=C["bg2"], padx=16, pady=14, **kw)
        self._var = tk.StringVar(value=str(value))
        tk.Label(self, textvariable=self._var,
                 font=("Courier New", 26, "bold"),
                 bg=C["bg2"], fg=color or C["text"]).pack(anchor="w")
        tk.Label(self, text=label.upper(),
                 font=("Courier New", 9),
                 bg=C["bg2"], fg=C["muted"]).pack(anchor="w")

    def set(self, v):
        self._var.set(str(v))


# ══════════════════════════════════════════════════════════════════════════════
#  Region card
# ══════════════════════════════════════════════════════════════════════════════
class RegionCard(tk.Frame):
    def __init__(self, parent, region_name, on_click, **kw):
        super().__init__(parent, bg=C["card"], bd=0,
                         highlightthickness=2, highlightbackground=C["border"],
                         relief="flat", padx=16, pady=14, **kw)
        self.region_name = region_name
        self.on_click = on_click
        self._selected = False

        hdr = tk.Frame(self, bg=C["card"])
        hdr.pack(fill="x", pady=(0, 10))
        self._icon = tk.Label(hdr, text="🌡", font=("TkDefaultFont", 24),
                              bg=C["card"], fg=C["accent2"])
        self._icon.pack(side="right", padx=4)
        left = tk.Frame(hdr, bg=C["card"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=region_name, font=("Helvetica", 14, "bold"),
                 bg=C["card"], fg=C["text"]).pack(anchor="w")
        tk.Label(left, text=f"Tanzania Regional Center",
                 font=("Courier New", 7), bg=C["card"], fg=C["muted"]).pack(anchor="w", pady=(2, 0))

        self._temp = tk.Label(self, text="—°C",
                              font=("Courier New", 32, "bold"),
                              bg=C["card"], fg=C["accent"])
        self._temp.pack(anchor="w", pady=(4, 2))
        self._cond = tk.Label(self, text="Fetching…",
                              font=("Helvetica", 9),
                              bg=C["card"], fg=C["muted"])
        self._cond.pack(anchor="w", pady=(0, 12))

        meta = tk.Frame(self, bg=C["card"])
        meta.pack(fill="x", pady=(0, 10))
        self._meta = {}
        for i, (k, unit) in enumerate([("Humidity", "%"), ("Wind", " km/h"),
                                        ("UV", ""), ("Pressure", " hPa")]):
            cell = tk.Frame(meta, bg=C["bg3"], padx=10, pady=8,
                            highlightthickness=0, relief="flat")
            cell.grid(row=i // 2, column=i % 2, padx=4, pady=4, sticky="nsew")
            meta.columnconfigure(i % 2, weight=1)
            meta.rowconfigure(i // 2, weight=1)
            tk.Label(cell, text=k.upper(), font=("Courier New", 7),
                     bg=C["bg3"], fg=C["muted"], justify="left").pack(anchor="w", side="top")
            v = tk.StringVar(value="—")
            self._meta[k] = (v, unit)
            tk.Label(cell, textvariable=v, font=("Courier New", 12, "bold"),
                     bg=C["bg3"], fg=C["accent2"], justify="left").pack(anchor="w", side="top", pady=(2, 0))

        self._badge = tk.Label(self, text="✓  All clear",
                               font=("Helvetica", 10, "bold"),
                               bg=C["bg3"], fg=C["ok"],
                               padx=12, pady=7, anchor="w",
                               relief="flat")
        self._badge.pack(fill="x")

        self._bind_all(self)

    def _bind_all(self, w):
        w.bind("<Button-1>", lambda _: self.on_click(self.region_name))
        w.bind("<Enter>", self._hover_on)
        w.bind("<Leave>", self._hover_off)
        for child in w.winfo_children():
            self._bind_all(child)

    def _hover_on(self, _=None):
        if not self._selected:
            self.configure(highlightbackground=C["accent"])

    def _hover_off(self, _=None):
        if not self._selected:
            self.configure(highlightbackground=C["border"])

    def set_selected(self, sel):
        self._selected = sel
        self.configure(
            highlightbackground=C["accent"] if sel else C["border"],
            bg=C["selected"] if sel else C["card"],
        )

    def update_weather(self, weather, event, risk_score=0):
        if not weather:
            return
        temp  = weather.get("temp_c", "—")
        feels = weather.get("feelslike_c", "—")
        cond  = weather.get("condition", {}).get("text", "N/A")
        cached = bool(weather.get("_cached"))
        hum   = weather.get("humidity", "—")
        wind  = weather.get("wind_kph", "—")
        uv    = weather.get("uv", "—")
        pres  = weather.get("pressure_mb", "—")

        self._icon.config(text=_wx_icon(cond))
        self._temp.config(text=f"{temp}°C")
        cache_note = "  ·  Cached" if cached else ""
        self._cond.config(text=f"{cond}  ·  Feels {feels}°C{cache_note}")

        for k, (var, unit) in self._meta.items():
            val = {"Humidity": hum, "Wind": wind, "UV": uv, "Pressure": pres}[k]
            var.set(f"{val}{unit}")

        level = _event_level(event)
        risk_txt = f"Risk {int(risk_score):02d}/100"
        if level == "danger":
            self._badge.config(text=f"⛔  DANGER • {event.upper()} • {risk_txt}",
                               fg=C["danger"], bg="#2a1a1a")
            if not self._selected:
                self.configure(highlightbackground=C["danger"])
        elif level == "possible":
            self._badge.config(text=f"⚠  POSSIBLE DANGER • {event.upper()} • {risk_txt}",
                               fg=C["warn"], bg="#2a2000")
            if not self._selected:
                self.configure(highlightbackground=C["warn"])
        else:
            self._badge.config(text=f"✓  SAFE • {risk_txt}", fg=C["ok"], bg=C["bg3"])
            if not self._selected:
                self.configure(highlightbackground=C["border"])


# ══════════════════════════════════════════════════════════════════════════════
#  Login screen
# ══════════════════════════════════════════════════════════════════════════════
class LoginScreen(tk.Frame):
    def __init__(self, master, on_success):
        super().__init__(master, bg=C["bg"])
        self._on_success = on_success
        self._failed_attempts = 0
        self._lock_until = 0
        master.title("Farmer Alert — Sign In")
        master.geometry("440x600")
        master.resizable(False, False)
        self._build()

    def _build(self):
        # Top accent bar
        tk.Frame(self, bg=C["accent"], height=3).pack(fill="x")

        # Hero section
        hero = tk.Frame(self, bg=C["bg"], pady=40)
        hero.pack(fill="x")
        row = tk.Frame(hero, bg=C["bg"])
        row.pack()
        RadarWidget(row, size=56).pack(side="left", padx=(0, 18))
        titl = tk.Frame(row, bg=C["bg"])
        titl.pack(side="left")
        tk.Label(titl, text="FARMER ALERT",
                 font=("Courier New", 24, "bold"),
                 bg=C["bg"], fg=C["accent"]).pack(anchor="w")
        tk.Label(titl, text="Admin Control Platform",
                 font=("Courier New", 9),
                 bg=C["bg"], fg=C["muted"]).pack(anchor="w", pady=(4, 0))

        # Card container
        card = tk.Frame(self, bg=C["bg2"], padx=40, pady=36,
                        highlightthickness=1, highlightbackground=C["border"],
                        relief="flat")
        card.pack(fill="x", padx=42, pady=(12, 0))

        # Username
        tk.Label(card, text="USERNAME", font=("Courier New", 8, "bold"),
                 bg=C["bg2"], fg=C["muted"]).pack(anchor="w")
        self._user = tk.Entry(card, font=("Courier New", 11),
                               bg=C["bg3"], fg=C["text"],
                               insertbackground=C["accent2"], relief="flat", bd=0)
        self._user.pack(fill="x", ipady=10, pady=(4, 18))
        self._user.insert(0, "admin")

        # Password
        tk.Label(card, text="PASSWORD", font=("Courier New", 8, "bold"),
                 bg=C["bg2"], fg=C["muted"]).pack(anchor="w")
        self._pwd = tk.Entry(card, font=("Courier New", 11),
                              bg=C["bg3"], fg=C["text"],
                              insertbackground=C["accent2"], relief="flat", bd=0,
                              show="•")
        self._pwd.pack(fill="x", ipady=10, pady=(4, 16))

        # Error label
        self._err = tk.Label(card, text="", font=("Courier New", 9),
                             bg=C["bg2"], fg=C["danger"])
        self._err.pack(anchor="w", pady=(0, 12))

        # Sign in button
        btn = tk.Button(card, text="SIGN  IN  →",
                        font=("Courier New", 11, "bold"),
                        bg=C["accent"], fg="#000", relief="flat", bd=0,
                        pady=10, cursor="hand2",
                        activebackground=C["accent2"],
                        activeforeground="#000",
                        command=self._try_login)
        btn.pack(fill="x")

        # Footer
        tk.Label(self, text="© 2026 Tanzania Agricultural Intelligence",
                 font=("Courier New", 7), bg=C["bg"], fg=C["border"]).pack(
            side="bottom", pady=14)

        # Focus & keyboard — bind directly on widgets, NOT on master
        self._pwd.bind("<Return>", lambda _: self._try_login())
        self._user.bind("<Return>", lambda _: self._pwd.focus())
        self._pwd.focus()

    def _try_login(self):
        user = self._user.get().strip()
        pwd  = self._pwd.get().strip()
        now = time.time()

        if now < self._lock_until:
            left = int(self._lock_until - now)
            self._err.configure(
                text=f"⛔  Too many attempts. Try again in {left}s")
            audit_log(user=user, action="LOGIN_BLOCKED", status="WARN",
                      detail=f"lockout_active={left}s")
            return

        auth = _authenticate_user(user, pwd)
        if auth:
            self._failed_attempts = 0
            if auth.get("requires_2fa"):
                # Show 2FA dialog
                TwoFADialog(self.master, auth, self._on_success)
                audit_log(user=user, action="LOGIN_2FA_REQUIRED", status="OK",
                          role=auth["role"], detail="2fa_verification_pending")
            else:
                audit_log(user=user, action="LOGIN_SUCCESS", status="OK",
                          role=auth["role"], detail="dashboard_access_granted")
                self._on_success(auth)
        else:
            self._failed_attempts += 1
            left = MAX_LOGIN_ATTEMPTS - self._failed_attempts
            if self._failed_attempts >= MAX_LOGIN_ATTEMPTS:
                self._lock_until = now + LOCKOUT_SECONDS
                self._failed_attempts = 0
                self._err.configure(
                    text=f"⛔  Locked for {LOCKOUT_SECONDS}s after too many failures")
                audit_log(user=user or "-", action="LOGIN_LOCKOUT",
                          status="ALERT",
                          detail=f"locked_for={LOCKOUT_SECONDS}s")
                self._pwd.delete(0, "end")
                self._pwd.focus()
                return
            self._err.configure(text="⚠  Invalid username or password")
            audit_log(user=user or "-", action="LOGIN_FAILED", status="WARN",
                      detail=f"remaining_before_lockout={left}")
            self._pwd.delete(0, "end")
            self._pwd.focus()


class TwoFADialog(tk.Toplevel):
    def __init__(self, master, auth_data, on_success):
        super().__init__(master)
        self.auth_data = auth_data
        self.on_success = on_success
        self.title("Two-Factor Authentication")
        self.geometry("400x300")
        self.resizable(False, False)
        self.configure(bg=C["bg"])
        self.transient(master)
        self.grab_set()
        self._build()

    def _build(self):
        # Title
        tk.Label(self, text="Enter 2FA Code",
                 font=("Courier New", 16, "bold"),
                 bg=C["bg"], fg=C["accent"]).pack(pady=20)

        tk.Label(self, text=f"Hello, {self.auth_data['username']}!",
                 font=("Courier New", 10),
                 bg=C["bg"], fg=C["text"]).pack(pady=(0, 10))

        tk.Label(self, text="Enter the 6-digit code from your\n authenticator app:",
                 font=("Courier New", 9),
                 bg=C["bg"], fg=C["muted"]).pack(pady=(0, 20))

        # Code entry
        self.code_entry = tk.Entry(self, font=("Courier New", 14),
                                   bg=C["bg3"], fg=C["text"],
                                   insertbackground=C["accent2"],
                                   relief="flat", bd=0, justify="center")
        self.code_entry.pack(ipady=10, padx=50)
        self.code_entry.focus()

        # Error label
        self.error_label = tk.Label(self, text="", font=("Courier New", 9),
                                    bg=C["bg"], fg=C["danger"])
        self.error_label.pack(pady=(10, 0))

        # Verify button
        btn = tk.Button(self, text="VERIFY",
                        font=("Courier New", 11, "bold"),
                        bg=C["accent"], fg="#000", relief="flat", bd=0,
                        pady=8, cursor="hand2",
                        activebackground=C["accent2"],
                        activeforeground="#000",
                        command=self._verify_code)
        btn.pack(pady=20)

        # Bind Enter key
        self.code_entry.bind("<Return>", lambda _: self._verify_code())

    def _verify_code(self):
        code = self.code_entry.get().strip()
        if not code:
            self.error_label.config(text="Please enter the 2FA code")
            return

        if len(code) != 6 or not code.isdigit():
            self.error_label.config(text="Code must be 6 digits")
            return

        if _verify_user_2fa(self.auth_data["username"], code):
            audit_log(user=self.auth_data["username"], action="LOGIN_2FA_SUCCESS",
                      status="OK", role=self.auth_data["role"],
                      detail="dashboard_access_granted")
            self.destroy()
            self.on_success(self.auth_data)
        else:
            self.error_label.config(text="Invalid 2FA code")
            audit_log(user=self.auth_data["username"], action="LOGIN_2FA_FAILED",
                      status="WARN", detail="invalid_2fa_code")


class TwoFAManagementDialog(tk.Toplevel):
    def __init__(self, master, username):
        super().__init__(master)
        self.username = username
        self.title("Two-Factor Authentication")
        self.geometry("400x250")
        self.resizable(False, False)
        self.configure(bg=C["bg"])
        self.transient(master)
        self.grab_set()

        # Check current 2FA status
        self.is_enabled = self._check_2fa_status()
        self._build()

    def _check_2fa_status(self):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return False

        for user in payload.get("users", []):
            if user.get("username") == self.username:
                return user.get("totp_secret") is not None
        return False

    def _build(self):
        # Title
        tk.Label(self, text="Two-Factor Authentication",
                 font=("Courier New", 16, "bold"),
                 bg=C["bg"], fg=C["accent"]).pack(pady=20)

        if self.is_enabled:
            # 2FA is enabled - show disable option
            tk.Label(self, text="2FA is currently ENABLED",
                     font=("Courier New", 12),
                     bg=C["bg"], fg=C["ok"]).pack(pady=(0, 10))

            tk.Label(self, text="Your account is protected with\n two-factor authentication.",
                     font=("Courier New", 9),
                     bg=C["bg"], fg=C["text"]).pack(pady=(0, 20))

            # Disable button
            disable_btn = tk.Button(self, text="DISABLE 2FA",
                                    font=("Courier New", 11, "bold"),
                                    bg=C["danger"], fg="white", relief="flat", bd=0,
                                    padx=20, pady=8, cursor="hand2",
                                    command=self._disable_2fa)
            disable_btn.pack(pady=10)
        else:
            # 2FA is disabled - show enable option
            tk.Label(self, text="2FA is currently DISABLED",
                     font=("Courier New", 12),
                     bg=C["bg"], fg=C["warn"]).pack(pady=(0, 10))

            tk.Label(self, text="Enable 2FA to add an extra\n layer of security to your account.",
                     font=("Courier New", 9),
                     bg=C["bg"], fg=C["text"]).pack(pady=(0, 20))

            # Enable button
            enable_btn = tk.Button(self, text="ENABLE 2FA",
                                   font=("Courier New", 11, "bold"),
                                   bg=C["ok"], fg="#000", relief="flat", bd=0,
                                   padx=20, pady=8, cursor="hand2",
                                   command=self._enable_2fa)
            enable_btn.pack(pady=10)

        # Cancel button
        cancel_btn = tk.Button(self, text="CANCEL",
                               font=("Courier New", 10),
                               bg=C["bg3"], fg=C["text"], relief="flat", bd=0,
                               padx=20, pady=5, cursor="hand2",
                               command=self.destroy)
        cancel_btn.pack(pady=(10, 0))

    def _enable_2fa(self):
        self.destroy()
        TwoFASetupDialog(self.master, self.username)

    def _disable_2fa(self):
        if messagebox.askyesno("Disable 2FA",
                               "Are you sure you want to disable two-factor authentication?\n\n"
                               "This will make your account less secure.",
                               icon="warning"):
            if _disable_user_2fa(self.username):
                messagebox.showinfo("Success", "Two-factor authentication has been disabled for your account.")
                audit_log(user=self.username, action="2FA_DISABLED",
                          status="OK", detail="2fa_disabled_by_user")
                self.destroy()
            else:
                messagebox.showerror("Error", "Failed to disable 2FA. Please try again.")


class TwoFASetupDialog(tk.Toplevel):
    def __init__(self, master, username):
        super().__init__(master)
        self.username = username
        self.secret = _generate_totp_secret()
        self.title("Setup Two-Factor Authentication")
        self.geometry("500x600")
        self.resizable(False, False)
        self.configure(bg=C["bg"])
        self.transient(master)
        self.grab_set()
        self._build()

    def _build(self):
        # Title
        tk.Label(self, text="Setup 2FA",
                 font=("Courier New", 16, "bold"),
                 bg=C["bg"], fg=C["accent"]).pack(pady=20)

        tk.Label(self, text="Scan the QR code with your\n authenticator app:",
                 font=("Courier New", 10),
                 bg=C["bg"], fg=C["text"]).pack(pady=(0, 20))

        # QR Code
        uri = _get_totp_uri(self.username, self.secret)
        qr = qrcode.QRCode(version=1, box_size=5, border=2)
        qr.add_data(uri)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")

        # Convert PIL to Tkinter
        self.qr_photo = ImageTk.PhotoImage(qr_img)
        qr_label = tk.Label(self, image=self.qr_photo, bg=C["bg"])
        qr_label.pack(pady=(0, 20))

        # Manual entry
        tk.Label(self, text="Or enter this code manually:",
                 font=("Courier New", 9),
                 bg=C["bg"], fg=C["muted"]).pack()

        code_frame = tk.Frame(self, bg=C["bg3"], padx=10, pady=5)
        code_frame.pack(pady=(5, 20))
        code_label = tk.Label(code_frame, text=self.secret,
                              font=("Courier New", 10, "bold"),
                              bg=C["bg3"], fg=C["accent"])
        code_label.pack()

        # Test code entry
        tk.Label(self, text="Enter a test code to verify:",
                 font=("Courier New", 9),
                 bg=C["bg"], fg=C["muted"]).pack()

        self.test_entry = tk.Entry(self, font=("Courier New", 12),
                                   bg=C["bg3"], fg=C["text"],
                                   insertbackground=C["accent2"],
                                   relief="flat", bd=0, justify="center")
        self.test_entry.pack(ipady=8, padx=50, pady=(5, 10))

        # Error label
        self.error_label = tk.Label(self, text="", font=("Courier New", 9),
                                    bg=C["bg"], fg=C["danger"])
        self.error_label.pack(pady=(0, 10))

        # Buttons
        btn_frame = tk.Frame(self, bg=C["bg"])
        btn_frame.pack(pady=10)

        cancel_btn = tk.Button(btn_frame, text="CANCEL",
                               font=("Courier New", 10),
                               bg=C["bg3"], fg=C["text"], relief="flat", bd=0,
                               padx=20, pady=5, cursor="hand2",
                               command=self.destroy)
        cancel_btn.pack(side="left", padx=5)

        enable_btn = tk.Button(btn_frame, text="ENABLE 2FA",
                               font=("Courier New", 10, "bold"),
                               bg=C["ok"], fg="#000", relief="flat", bd=0,
                               padx=20, pady=5, cursor="hand2",
                               command=self._enable_2fa)
        enable_btn.pack(side="left", padx=5)

    def _enable_2fa(self):
        test_code = self.test_entry.get().strip()
        if not test_code:
            self.error_label.config(text="Please enter a test code")
            return

        if len(test_code) != 6 or not test_code.isdigit():
            self.error_label.config(text="Code must be 6 digits")
            return

        if _verify_totp_code(self.secret, test_code):
            if _setup_user_2fa(self.username, self.secret):
                messagebox.showinfo("Success", "2FA has been enabled for your account!")
                audit_log(user=self.username, action="2FA_SETUP_SUCCESS",
                          status="OK", detail="2fa_enabled")
                self.destroy()
            else:
                self.error_label.config(text="Failed to save 2FA settings")
        else:
            self.error_label.config(text="Invalid test code")


# ══════════════════════════════════════════════════════════════════════════════
#  Dashboard
# ══════════════════════════════════════════════════════════════════════════════
class Dashboard(tk.Frame):
    def __init__(self, master, username, role, on_logout):
        super().__init__(master, bg=C["bg"])
        self.username    = username
        self.role        = role
        self.session_id  = uuid.uuid4().hex[:10]
        self._on_logout  = on_logout
        self._selected   = None
        self._cards      = {}
        self._cache      = {}   # city → weather dict
        self._events     = {}   # city → event str
        self._risk_scores = {}  # city -> int
        self._risk_factors = {} # city -> list[str]
        self._geo_points = []
        self._map_canvas = None
        self._busy       = False
        self._auto_after = None
        self._last_refresh_ts = None

        master.title("Farmer Alert — Admin Dashboard")
        master.geometry("1280x820")
        master.minsize(1000, 640)
        master.resizable(True, True)

        self._alert_sys  = WeatherAlertSystemXML()
        self._notifier   = NotificationDispatcher()
        self._incidents  = IncidentStore()
        self._loc        = {city: (lat, lon) for city, lat, lon in locations}
        for city, _, _ in locations:
            self._alert_sys.add_region(name=city,
                                       number=f"RGN-{city}", region=city)

        self._apply_ttk_styles()
        self._last_activity = time.time()
        self._session_timeout = 30 * 60  # 30 minutes
        self._build()
        self._sec_log(action="DASHBOARD_LOGIN", status="OK",
                      detail="dashboard_opened")
        self._check_session_timeout()
        # Bind activity events
        self.master.bind_all("<Key>", self._update_activity)
        self.master.bind_all("<Button>", self._update_activity)
        self.master.bind_all("<Motion>", self._update_activity)
        self.master.after(200, self._bring_front)
        self.master.after(400, lambda: threading.Thread(
            target=self._fetch_all, daemon=True).start())

    def _can(self, action):
        allowed = {
            "admin": {"refresh", "auto_send", "send_selected", "send_all", "export", "incident_update"},
            "analyst": {"refresh", "auto_send", "send_selected", "export", "incident_update"},
            "viewer": {"refresh", "export"},
        }
        return action in allowed.get(self.role, set())

    # ── TTK dark scrollbars ────────────────────────────────────────────────────
    def _apply_ttk_styles(self):
        s = ttk.Style(self.master)
        s.theme_use("default")
        for ori in ("Vertical", "Horizontal"):
            s.configure(f"{ori}.TScrollbar",
                        background=C["bg3"], troughcolor=C["bg"],
                        bordercolor=C["bg"], arrowcolor=C["muted"],
                        darkcolor=C["bg3"], lightcolor=C["bg3"])

    # ── Layout builder ─────────────────────────────────────────────────────────
    def _build(self):
        self._build_header()
        self._build_stats()
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")
        self._build_body()
        self._build_action_bar()
        self._build_log()
        self._tick()

    # ── Header ─────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self, bg=C["bg2"], pady=12)
        hdr.pack(fill="x")

        left = tk.Frame(hdr, bg=C["bg2"])
        left.pack(side="left", padx=20)
        RadarWidget(left).pack(side="left", padx=(0, 12))
        titl = tk.Frame(left, bg=C["bg2"])
        titl.pack(side="left")
        tk.Label(titl, text="WeatherAlert",
                 font=("Helvetica", 18, "bold"),
                 bg=C["bg2"], fg=C["text"]).pack(anchor="w")
        tk.Label(titl, text="REGIONAL MONITORING SYSTEM — TANZANIA",
                 font=("Courier New", 9),
                 bg=C["bg2"], fg=C["muted"]).pack(anchor="w")

        right = tk.Frame(hdr, bg=C["bg2"])
        right.pack(side="right", padx=20)

        # live dot
        lf = tk.Frame(right, bg=C["bg2"])
        lf.pack(side="left", padx=(0, 16))
        dot = tk.Canvas(lf, width=10, height=10,
                        bg=C["bg2"], highlightthickness=0)
        dot.pack(side="left", padx=(0, 5))
        dot.create_oval(1, 1, 9, 9, fill=C["ok"], outline="")
        tk.Label(lf, text="LIVE", font=("Courier New", 10),
                 bg=C["bg2"], fg=C["ok"]).pack(side="left")

        # user badge
        tk.Label(right, text=f"👤  {self.username.upper()} ({self.role.upper()})",
                 font=("Courier New", 10, "bold"),
                 bg=C["bg2"], fg=C["accent2"]).pack(side="left", padx=(0, 16))

        # clock
        self._clock_var = tk.StringVar()
        tk.Label(right, textvariable=self._clock_var,
                 font=("Courier New", 13),
                 bg=C["bg2"], fg=C["muted"]).pack(side="left", padx=(0, 20))

        # 2FA setup
        fa = tk.Button(right, text="2FA",
                       font=("Courier New", 9, "bold"),
                       bg=C["bg3"], fg=C["accent"], relief="flat", bd=0,
                       padx=10, pady=4, cursor="hand2",
                       activebackground=C["accent2"],
                       activeforeground="#000",
                       command=self._setup_2fa)
        fa.pack(side="left", padx=(0, 10))

        # logout
        lo = tk.Button(right, text="LOGOUT",
                       font=("Courier New", 9, "bold"),
                       bg=C["bg3"], fg=C["muted"], relief="flat", bd=0,
                       padx=10, pady=4, cursor="hand2",
                       activebackground=C["danger"],
                       activeforeground="white",
                       command=self._logout)
        lo.pack(side="left")

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")

    # ── Stats bar ──────────────────────────────────────────────────────────────
    def _build_stats(self):
        bar = tk.Frame(self, bg=C["border"])
        bar.pack(fill="x")
        inner = tk.Frame(bar, bg=C["border"])
        inner.pack(fill="x")

        self._sc_total = StatCard(inner, "Regions Monitored",
                                   value=str(len(locations)),
                                   color=C["accent2"])
        self._sc_alert = StatCard(inner, "Danger",         color=C["danger"])
        self._sc_warn  = StatCard(inner, "Possible Danger", color=C["warn"])
        self._sc_clear = StatCard(inner, "Safe",           color=C["ok"])
        self._sc_risk  = StatCard(inner, "Avg Risk",       color=C["accent"])

        for i, w in enumerate([self._sc_total, self._sc_alert,
                    self._sc_warn, self._sc_clear, self._sc_risk]):
            w.grid(row=0, column=i, sticky="nsew", padx=1, pady=1)
            inner.columnconfigure(i, weight=1)

    # ── Main body (sidebar + card grid) ───────────────────────────────────────
    def _build_body(self):
        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True)

        # sidebar
        sb = tk.Frame(body, bg=C["bg2"], width=220)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)
        tk.Frame(sb, bg=C["border"], width=1).pack(side="right", fill="y")

        tk.Label(sb, text="REGIONS", font=("Courier New", 9),
                 bg=C["bg2"], fg=C["muted"],
                 padx=14, pady=10).pack(anchor="w")

        sb_c = tk.Canvas(sb, bg=C["bg2"], highlightthickness=0)
        sb_s = ttk.Scrollbar(sb, orient="vertical", command=sb_c.yview)
        sb_c.configure(yscrollcommand=sb_s.set)
        sb_s.pack(side="right", fill="y")
        sb_c.pack(side="left", fill="both", expand=True)

        self._sb_inner = tk.Frame(sb_c, bg=C["bg2"])
        sb_c.create_window((0, 0), window=self._sb_inner, anchor="nw")
        self._sb_inner.bind(
            "<Configure>",
            lambda e: sb_c.configure(scrollregion=sb_c.bbox("all")))
        sb_c.bind("<MouseWheel>",
                  lambda e: sb_c.yview_scroll(-1 * (e.delta // 120), "units"))
        self._sb_inner.bind("<MouseWheel>",
                  lambda e: sb_c.yview_scroll(-1 * (e.delta // 120), "units"))
        self._chips = {}
        self._build_chips()

        # card grid area (center)
        right = tk.Frame(body, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)

        # filter bar
        fbar = tk.Frame(right, bg=C["bg"], pady=10, padx=16)
        fbar.pack(fill="x")
        tk.Label(fbar, text="ALL REGIONS", font=("Courier New", 9, "bold"),
                 bg=C["bg"], fg=C["muted"]).pack(side="left", padx=(0, 20))

        self._filt = tk.StringVar(value="All")
        for lbl in ("All", "Danger", "Possible", "Safe"):
            tk.Radiobutton(fbar, text=lbl, variable=self._filt, value=lbl,
                           command=self._reflow,
                           bg=C["bg"], fg=C["muted"],
                           selectcolor=C["bg3"],
                           activebackground=C["bg"],
                           activeforeground=C["accent2"],
                           font=("Courier New", 9)).pack(side="right", padx=8)

        # scrollable canvas for cards
        self._cv = tk.Canvas(right, bg=C["bg"], highlightthickness=0)
        cv_s = ttk.Scrollbar(right, orient="vertical", command=self._cv.yview)
        self._cv.configure(yscrollcommand=cv_s.set)
        cv_s.pack(side="right", fill="y")
        self._cv.pack(side="left", fill="both", expand=True)

        self._cf = tk.Frame(self._cv, bg=C["bg"])
        self._cv_window = self._cv.create_window((0, 0), window=self._cf,
                                                 anchor="nw")
        self._cf.bind("<Configure>",
                      lambda e: self._cv.configure(
                          scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>", self._on_canvas_resize)
        self._cv.bind("<MouseWheel>",
                      lambda e: self._cv.yview_scroll(
                          -1 * (e.delta // 120), "units"))
        self._cf.bind("<MouseWheel>",
                      lambda e: self._cv.yview_scroll(
                          -1 * (e.delta // 120), "units"))

        # smart panel (fills right side with useful project info)
        panel = tk.Frame(body, bg=C["bg2"], width=260)
        panel.pack(side="right", fill="y")
        panel.pack_propagate(False)
        tk.Frame(panel, bg=C["border"], width=1).pack(side="left", fill="y")
        self._build_smart_panel(panel)

        self._build_cards()

    def _build_smart_panel(self, parent):
        tk.Label(parent, text="SMART PANEL", font=("Courier New", 10, "bold"),
                 bg=C["bg2"], fg=C["accent2"], pady=10).pack(anchor="w", padx=14)

        self._ins_counts = tk.StringVar(value="Danger: 0  |  Possible: 0  |  Safe: 0")
        tk.Label(parent, textvariable=self._ins_counts,
                 font=("Courier New", 8), bg=C["bg2"], fg=C["muted"],
                 justify="left").pack(anchor="w", padx=14, pady=(0, 10))

        tk.Label(parent, text="RISK LEGEND", font=("Courier New", 8, "bold"),
                 bg=C["bg2"], fg=C["muted"]).pack(anchor="w", padx=14)
        for txt, col in [("DANGER", C["danger"]),
                         ("POSSIBLE DANGER", C["warn"]),
                         ("SAFE", C["ok"])]:
            row = tk.Frame(parent, bg=C["bg2"])
            row.pack(fill="x", padx=14, pady=2)
            d = tk.Canvas(row, width=10, height=10, bg=C["bg2"], highlightthickness=0)
            d.create_oval(1, 1, 9, 9, fill=col, outline="")
            d.pack(side="left", padx=(0, 8))
            tk.Label(row, text=txt, font=("Courier New", 8),
                     bg=C["bg2"], fg=C["text"]).pack(side="left")

        tk.Frame(parent, bg=C["border"], height=1).pack(fill="x", padx=14, pady=10)

        tk.Label(parent, text="SELECTED REGION", font=("Courier New", 8, "bold"),
                 bg=C["bg2"], fg=C["muted"]).pack(anchor="w", padx=14)
        self._ins_selected = tk.StringVar(value="No region selected")
        tk.Label(parent, textvariable=self._ins_selected,
                 font=("Courier New", 9, "bold"), bg=C["bg2"], fg=C["text"],
                 wraplength=220, justify="left").pack(anchor="w", padx=14, pady=(4, 10))

        self._ins_tip = tk.StringVar(value="Tip: Select a region to see actions.")
        tk.Label(parent, textvariable=self._ins_tip, font=("Courier New", 8),
                 bg=C["bg2"], fg=C["accent2"], wraplength=220,
                 justify="left").pack(anchor="w", padx=14, pady=(0, 10))

        self._ins_data_age = tk.StringVar(value="Data age: waiting for first refresh")
        tk.Label(parent, textvariable=self._ins_data_age, font=("Courier New", 8),
             bg=C["bg2"], fg=C["muted"], wraplength=220,
             justify="left").pack(anchor="w", padx=14, pady=(0, 10))

        tk.Button(parent, text="Focus Highest Risk", font=("Courier New", 9, "bold"),
                  bg=C["accent"], fg="#000", relief="flat", bd=0,
                  activebackground=C["accent2"], activeforeground="#000",
                  cursor="hand2", padx=10, pady=7,
                  command=self._focus_highest_risk).pack(fill="x", padx=14, pady=(0, 10))

        tk.Button(parent, text="Open Risk Map", font=("Courier New", 9, "bold"),
              bg=C["bg3"], fg=C["text"], relief="flat", bd=0,
              cursor="hand2", padx=10, pady=7,
              command=self._open_map_view).pack(fill="x", padx=14, pady=(0, 10))

        tk.Label(parent, text="TOP FLAGGED", font=("Courier New", 8, "bold"),
                 bg=C["bg2"], fg=C["muted"]).pack(anchor="w", padx=14)
        self._ins_top_vars = []
        for _ in range(5):
            v = tk.StringVar(value="• —")
            self._ins_top_vars.append(v)
            tk.Label(parent, textvariable=v, font=("Courier New", 8),
                     bg=C["bg2"], fg=C["text"], justify="left").pack(
                         anchor="w", padx=14, pady=1)

    def _on_canvas_resize(self, e):
        # Keep the cards frame as wide as the canvas to remove blank right space.
        self._cv.itemconfigure(self._cv_window, width=e.width)
        self._reflow()

    def _build_chips(self):
        for w in self._sb_inner.winfo_children():
            w.destroy()
        self._chips.clear()
        for entry in self._alert_sys.regions:
            city = entry["region"]
            f = tk.Frame(self._sb_inner, bg=C["bg2"],
                         cursor="hand2", padx=12, pady=8,
                         highlightthickness=1, highlightbackground=C["border"],
                         relief="flat")
            f.pack(fill="x", padx=6, pady=3)
            dot = tk.Canvas(f, width=10, height=10,
                            bg=C["bg2"], highlightthickness=0)
            dot.create_oval(1, 1, 9, 9, fill=C["muted"], outline="")
            dot.pack(side="right", padx=6)
            lbl = tk.Label(f, text=city, font=("Helvetica", 10, "bold"),
                     bg=C["bg2"], fg=C["text"])
            lbl.pack(side="left", fill="x", expand=True)

            def _hover_on(e, fr=f, lb=lbl):
                fr.config(bg=C["bg3"], highlightbackground=C["accent"])
                lb.config(fg=C["accent2"])
            def _hover_off(e, fr=f, lb=lbl, c=city):
                is_sel = self._selected == c
                fr.config(bg=C["selected"] if is_sel else C["bg2"],
                         highlightbackground=C["accent"] if is_sel else C["border"])
                lb.config(fg=C["accent2"] if is_sel else C["text"])

            for w in [f, lbl, dot]:
                w.bind("<Button-1>", lambda e, c=city: self._select(c))
                w.bind("<Enter>", _hover_on)
                w.bind("<Leave>", _hover_off)
            self._chips[city] = (f, dot, lbl)


    def _build_cards(self):
        for w in self._cf.winfo_children():
            w.destroy()
        self._cards.clear()
        for entry in self._alert_sys.regions:
            city = entry["region"]
            card = RegionCard(self._cf, city, self._select)
            self._cards[city] = card
        self._reflow()

    def _reflow(self):
        w = self._cv.winfo_width() or 1200
        card_w = 330
        cols = max(1, (w - 16) // (card_w + 16))

        for c in self._cf.winfo_children():
            c.grid_forget()

        flt = self._filt.get()
        row = col = 0
        for city, card in self._cards.items():
            ev = self._events.get(city)
            level = _event_level(ev)
            if flt == "Danger" and level != "danger":
                continue
            if flt == "Possible" and level != "possible":
                continue
            if flt == "Safe" and level != "safe":
                continue
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            self._cf.columnconfigure(col, weight=1)
            self._cf.rowconfigure(row, weight=0)
            col += 1
            if col >= cols:
                col = 0
                row += 1

    # ── Action bar ─────────────────────────────────────────────────────────────
    def _build_action_bar(self):
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")
        bar = tk.Frame(self, bg=C["bg2"], pady=10, padx=14)
        bar.pack(fill="x")

        self._sel_lbl = tk.Label(bar, text="No region selected",
                                 font=("Courier New", 10),
                                 bg=C["bg2"], fg=C["muted"])
        self._sel_lbl.pack(side="left", padx=6)

        # progress bar (hidden until busy)
        self._prog_var = tk.IntVar(value=0)
        self._prog = ttk.Progressbar(bar, mode="indeterminate", length=160)
        # don't pack yet

        kw = dict(font=("Helvetica", 11), bd=0, cursor="hand2",
                  padx=12, pady=6, relief="flat")
        self._action_buttons = {}
        for txt, key, bg, fg, active_bg, cmd in [
            ("↻ Refresh All",       "refresh",      C["accent"],  "#000", C["accent2"],       self._refresh_async),
            ("⚠ Auto Alerts",       "auto_send",    C["danger"],  "#fff", "#ff5555",          self._auto_send),
            ("⚠ Send Selected",     "send_selected", C["warn"],    "#000", "#ffdd00",          self._send_selected),
            ("⚠ Send All",          "send_all",      C["danger"],  "#fff", "#ff5555",          self._send_all),
        ]:
            b = tk.Button(bar, text=txt, bg=bg, fg=fg,
                          activebackground=active_bg,
                          activeforeground=fg,
                          command=cmd, **kw)
            b.pack(side="right", padx=4)
            self._action_buttons[key] = b

        for key, btn in self._action_buttons.items():
            if not self._can(key):
                btn.configure(state="disabled", bg=C["bg3"], fg=C["muted"])

        # auto-refresh toggle
        tk.Frame(bar, bg=C["border"], width=1).pack(side="right",
                                                     fill="y", padx=8)
        self._auto_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Auto",
                       variable=self._auto_var,
                       command=self._toggle_auto,
                       bg=C["bg2"], fg=C["muted"],
                       selectcolor=C["bg3"],
                       activebackground=C["bg2"],
                       activeforeground=C["text"],
                       font=("Courier New", 9)).pack(side="right")
        self._int_var = tk.IntVar(value=120)
        tk.Spinbox(bar, from_=30, to=900, textvariable=self._int_var,
                   width=5, bg=C["bg3"], fg=C["text"],
                   insertbackground=C["text"],
                   relief="flat", bd=0,
                   buttonbackground=C["border"]).pack(side="right", padx=4)
        tk.Label(bar, text="s", font=("Courier New", 9),
                 bg=C["bg2"], fg=C["muted"]).pack(side="right")

    # ── Log panel ──────────────────────────────────────────────────────────────
    def _build_log(self):
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")
        panel = tk.Frame(self, bg=C["bg2"], height=160)
        panel.pack(fill="x")
        panel.pack_propagate(False)

        tabs = ttk.Notebook(panel)
        tabs.pack(fill="both", expand=True, padx=10, pady=8)

        t1 = tk.Frame(tabs, bg=C["bg2"])
        t2 = tk.Frame(tabs, bg=C["bg2"])
        t3 = tk.Frame(tabs, bg=C["bg2"])
        tabs.add(t1, text="Activity")
        tabs.add(t2, text="Security")
        tabs.add(t3, text="Incidents")

        self._log_txt = tk.Text(t1, bg=C["bg2"], fg=C["muted"],
                                font=("Courier New", 10), bd=0,
                                highlightthickness=0, wrap="word",
                                state="disabled")
        ls1 = ttk.Scrollbar(t1, orient="vertical", command=self._log_txt.yview)
        self._log_txt.configure(yscrollcommand=ls1.set)
        ls1.pack(side="right", fill="y", padx=(0, 4))
        self._log_txt.pack(fill="both", expand=True, padx=(4, 0), pady=4)

        self._sec_txt = tk.Text(t2, bg=C["bg2"], fg=C["muted"],
                                font=("Courier New", 9), bd=0,
                                highlightthickness=0, wrap="none",
                                state="disabled")
        ctl = tk.Frame(t2, bg=C["bg2"])
        ctl.pack(fill="x", padx=4, pady=(4, 0))

        tk.Label(ctl, text="Status", font=("Courier New", 8),
             bg=C["bg2"], fg=C["muted"]).pack(side="left")
        self._sec_status = tk.StringVar(value="ALL")
        ttk.Combobox(ctl, width=10, state="readonly",
                 textvariable=self._sec_status,
                 values=["ALL", "OK", "WARN", "ALERT", "INFO"]).pack(side="left", padx=(4, 8))

        tk.Label(ctl, text="Find", font=("Courier New", 8),
             bg=C["bg2"], fg=C["muted"]).pack(side="left")
        self._sec_query = tk.StringVar(value="")
        tk.Entry(ctl, textvariable=self._sec_query, width=24,
             bg=C["bg3"], fg=C["text"], insertbackground=C["text"],
             relief="flat", bd=0).pack(side="left", padx=(4, 8), ipady=3)

        tk.Button(ctl, text="Apply", font=("Courier New", 8, "bold"),
              bg=C["bg3"], fg=C["text"], relief="flat", bd=0,
              cursor="hand2", command=self._render_security_log).pack(side="left", padx=(0, 8))
        tk.Button(ctl, text="Export CSV", font=("Courier New", 8, "bold"),
              bg=C["accent"], fg="#000", relief="flat", bd=0,
              cursor="hand2", command=self._export_security_csv).pack(side="right")

        self._sec_entries = []

        ls2 = ttk.Scrollbar(t2, orient="vertical", command=self._sec_txt.yview)
        self._sec_txt.configure(yscrollcommand=ls2.set)
        ls2.pack(side="right", fill="y", padx=(0, 4))
        self._sec_txt.pack(fill="both", expand=True, padx=(4, 0), pady=4)

        self._log_txt.tag_config("ok",   foreground=C["ok"])
        self._log_txt.tag_config("warn", foreground=C["warn"])
        self._log_txt.tag_config("err",  foreground=C["danger"])
        self._log_txt.tag_config("ts",   foreground=C["accent2"])

        self._sec_txt.tag_config("ok",   foreground=C["ok"])
        self._sec_txt.tag_config("warn", foreground=C["warn"])
        self._sec_txt.tag_config("err",  foreground=C["danger"])
        self._sec_txt.tag_config("info", foreground=C["accent2"])
        self._load_security_log_tail()

        cols = ("id", "city", "event", "risk", "status", "assignee", "updated")
        self._inc_tree = ttk.Treeview(t3, columns=cols, show="headings", height=5)
        self._inc_tree.heading("id", text="ID")
        self._inc_tree.heading("city", text="City")
        self._inc_tree.heading("event", text="Event")
        self._inc_tree.heading("risk", text="Risk")
        self._inc_tree.heading("status", text="Status")
        self._inc_tree.heading("assignee", text="Assigned")
        self._inc_tree.heading("updated", text="Updated")
        self._inc_tree.column("id", width=70, anchor="center")
        self._inc_tree.column("city", width=120)
        self._inc_tree.column("event", width=90, anchor="center")
        self._inc_tree.column("risk", width=60, anchor="center")
        self._inc_tree.column("status", width=100, anchor="center")
        self._inc_tree.column("assignee", width=100)
        self._inc_tree.column("updated", width=140)
        self._inc_tree.pack(fill="both", expand=True, padx=6, pady=(6, 4))

        inc_ctl = tk.Frame(t3, bg=C["bg2"])
        inc_ctl.pack(fill="x", padx=6, pady=(0, 6))
        tk.Label(inc_ctl, text="Assignee", bg=C["bg2"], fg=C["muted"],
                 font=("Courier New", 8)).pack(side="left")
        self._inc_assignee = tk.StringVar(value=self.username)
        tk.Entry(inc_ctl, textvariable=self._inc_assignee, width=14,
                 bg=C["bg3"], fg=C["text"], relief="flat", bd=0,
                 insertbackground=C["text"]).pack(side="left", padx=4, ipady=3)
        tk.Label(inc_ctl, text="Note", bg=C["bg2"], fg=C["muted"],
                 font=("Courier New", 8)).pack(side="left")
        self._inc_note = tk.StringVar(value="")
        tk.Entry(inc_ctl, textvariable=self._inc_note, width=30,
                 bg=C["bg3"], fg=C["text"], relief="flat", bd=0,
                 insertbackground=C["text"]).pack(side="left", padx=4, ipady=3)

        for txt, action in [
            ("Acknowledge", "acknowledged"),
            ("Assign", "assigned"),
            ("Resolve", "resolved"),
        ]:
            tk.Button(
                inc_ctl,
                text=txt,
                font=("Courier New", 8, "bold"),
                bg=C["bg3"],
                fg=C["text"],
                relief="flat",
                bd=0,
                cursor="hand2",
                command=lambda s=action: self._update_selected_incident(s),
            ).pack(side="right", padx=3)

        self._load_incidents()

    def _load_incidents(self):
        for row in self._inc_tree.get_children():
            self._inc_tree.delete(row)
        for inc in self._incidents.list_incidents():
            self._inc_tree.insert(
                "",
                "end",
                values=(
                    inc.get("id", ""),
                    inc.get("city", ""),
                    str(inc.get("event", "")).upper(),
                    f"{inc.get('risk_score', 0)}/100",
                    inc.get("status", ""),
                    inc.get("assigned_to", ""),
                    inc.get("updated_at", ""),
                ),
            )

    def _selected_incident_id(self):
        sel = self._inc_tree.selection()
        if not sel:
            return None
        vals = self._inc_tree.item(sel[0], "values")
        return vals[0] if vals else None

    def _update_selected_incident(self, new_status):
        if not self._can("incident_update"):
            messagebox.showwarning("Permission", "Your role cannot update incident state.")
            return
        inc_id = self._selected_incident_id()
        if not inc_id:
            messagebox.showinfo("Incident", "Select an incident first.")
            return
        note = self._inc_note.get().strip()
        assignee = self._inc_assignee.get().strip()
        payload = {
            "status": new_status,
            "assigned_to": assignee if new_status in {"assigned", "resolved"} else None,
            "notes": note if new_status != "resolved" else None,
            "resolution_note": note if new_status == "resolved" else None,
        }
        updated = self._incidents.update_incident(inc_id, **payload)
        if not updated:
            messagebox.showwarning("Incident", "Incident not found.")
            return
        self._sec_log(
            action="INCIDENT_UPDATED",
            status="OK",
            city=updated.get("city", "-"),
            event=updated.get("event", "-"),
            detail=f"id={inc_id};status={new_status};assignee={assignee or '-'}",
        )
        self._load_incidents()

    def _create_incident_for_alert(self, city, event, source, note=""):
        score = self._risk_scores.get(city, 0)
        incident = self._incidents.create_incident(
            city=city,
            event=event,
            risk_score=score,
            notes=f"source={source}; {note}".strip(),
            created_by=self.username,
        )
        self._sec_log(
            action="INCIDENT_CREATED",
            status="WARN",
            city=city,
            event=event,
            detail=f"id={incident['id']};risk={score};source={source}",
        )
        self._load_incidents()

    def _dispatch_notifications(self, city, event, message):
        statuses = self._notifier.send_alert(city, event, message)
        sent = sum(1 for s in statuses if s.get("status") == "SENT")
        failed = sum(1 for s in statuses if s.get("status") == "FAILED")
        skipped = sum(1 for s in statuses if s.get("status") == "SKIPPED")
        self._sec_log(
            action="NOTIFY_DISPATCH",
            status="OK" if sent else "WARN",
            city=city,
            event=event,
            detail=f"sent={sent};failed={failed};skipped={skipped}",
        )
        for row in statuses:
            st = row.get("status", "").upper()
            level = "OK" if st == "SENT" else "ALERT" if st == "FAILED" else "WARN"
            self._sec_log(
                action="DELIVERY_STATUS",
                status=level,
                city=city,
                event=event,
                detail=(
                    f"provider={row.get('provider','-')};status={row.get('status','-')};"
                    f"message_id={row.get('message_id','-')};detail={row.get('detail','-')}"
                ),
            )

    def _open_map_view(self):
        _ensure_geojson_file()
        if not self._geo_points:
            try:
                with open(MAP_GEOJSON_FILE, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                self._geo_points = payload.get("features", [])
            except Exception:
                messagebox.showerror("Map", "Failed to load GeoJSON.")
                return

        win = tk.Toplevel(self)
        win.title("Risk Map")
        win.geometry("860x560")
        win.configure(bg=C["bg"])
        self._map_canvas = tk.Canvas(win, bg="#0b1220", highlightthickness=0)
        self._map_canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self._map_canvas.bind("<Configure>", lambda e: self._draw_map())
        self._draw_map()

    def _draw_map(self):
        if not self._map_canvas:
            return
        cv = self._map_canvas
        cv.delete("all")
        w = max(cv.winfo_width(), 400)
        h = max(cv.winfo_height(), 250)
        pad = 30

        lons = [feat.get("geometry", {}).get("coordinates", [0, 0])[0] for feat in self._geo_points]
        lats = [feat.get("geometry", {}).get("coordinates", [0, 0])[1] for feat in self._geo_points]
        outline_lons = [p[0] for p in TANZANIA_OUTLINE]
        outline_lats = [p[1] for p in TANZANIA_OUTLINE]
        lons.extend(outline_lons)
        lats.extend(outline_lats)
        if not lons or not lats:
            return
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)
        lon_span = max(max_lon - min_lon, 1e-6)
        lat_span = max(max_lat - min_lat, 1e-6)

        def project(lon, lat):
            x = pad + ((lon - min_lon) / lon_span) * (w - 2 * pad)
            y = h - pad - ((lat - min_lat) / lat_span) * (h - 2 * pad)
            return x, y

        # Ocean background gradient bands.
        cv.create_rectangle(0, 0, w, h, fill="#0b1220", outline="")
        for i, color in enumerate(["#0e1730", "#102040", "#13254c"]):
            y0 = int(i * h / 3)
            y1 = int((i + 1) * h / 3)
            cv.create_rectangle(0, y0, w, y1, fill=color, outline="")

        # Graticule grid for map context.
        for gx in range(5):
            x = pad + gx * (w - 2 * pad) / 4
            cv.create_line(x, pad, x, h - pad, fill="#22314f", width=1)
        for gy in range(5):
            y = pad + gy * (h - 2 * pad) / 4
            cv.create_line(pad, y, w - pad, y, fill="#22314f", width=1)

        # Tanzania silhouette.
        poly = []
        for lon, lat in TANZANIA_OUTLINE:
            x, y = project(lon, lat)
            poly.extend([x, y])
        cv.create_polygon(poly, fill="#1e4f44", outline="#5fd1ad", width=2)

        for feat in self._geo_points:
            props = feat.get("properties", {})
            city = props.get("name", "Unknown")
            lon, lat = feat.get("geometry", {}).get("coordinates", [0, 0])
            x, y = project(lon, lat)

            score = self._risk_scores.get(city, 0)
            level = _event_level(self._events.get(city))
            col = C["danger"] if level == "danger" else C["warn"] if level == "possible" else C["ok"]
            r = 5 + int(score / 12)
            cv.create_oval(x - r - 2, y - r - 2, x + r + 2, y + r + 2, fill="#081325", outline="")
            cv.create_oval(x - r, y - r, x + r, y + r, fill=col, outline="")
            tag = f"city_{city.replace(' ', '_')}"
            cv.create_text(x + r + 4, y, text=city, fill=C["text"], anchor="w", font=("Courier New", 8), tags=(tag,))
            cv.tag_bind(tag, "<Button-1>", lambda _e, c=city: self._select(c))

        cv.create_text(
            14,
            14,
            anchor="nw",
            fill=C["muted"],
            font=("Courier New", 9),
            text="Tanzania risk map: silhouette + risk markers (click labels to select)",
        )

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _tick(self):
        self._clock_var.set(time.strftime("%H:%M:%S"))
        if self._last_refresh_ts:
            age = int(time.time() - self._last_refresh_ts)
            self._ins_data_age.set(f"Data age: {age}s")
        self.after(1000, self._tick)
        self._check_session_timeout()

    def _check_session_timeout(self):
        if time.time() - self._last_activity > self._session_timeout:
            self._sec_log(action="SESSION_TIMEOUT", status="WARN", detail="auto_logout_due_to_inactivity")
            self._on_logout()

    def _update_activity(self, event=None):
        self._last_activity = time.time()

    def _bring_front(self):
        self.master.lift()
        self.master.attributes("-topmost", True)
        self.master.after(300,
                          lambda: self.master.attributes("-topmost", False))

    def _logout(self):
        if messagebox.askyesno("Logout", "Return to login screen?"):
            self._sec_log(action="LOGOUT", status="OK", detail="user_requested")
            self._on_logout()

    def _setup_2fa(self):
        # Show 2FA management dialog
        TwoFAManagementDialog(self.master, self.username)

    def _log(self, msg, kind="ok"):
        ts = time.strftime("%H:%M:%S")
        self._log_txt.configure(state="normal")
        self._log_txt.insert("end", ts + "  ", "ts")
        self._log_txt.insert("end", msg + "\n", kind)
        self._log_txt.see("end")
        self._log_txt.configure(state="disabled")

    def _load_security_log_tail(self):
        self._sec_entries = []
        for ln in read_audit_tail(limit=300):
            self._sec_entries.append(_parse_audit_line(ln))
        self._render_security_log()

    def _filtered_security_entries(self):
        status = self._sec_status.get().strip().upper()
        query = self._sec_query.get().strip().lower()
        out = []
        for entry in self._sec_entries:
            if status != "ALL" and entry.get("status", "").upper() != status:
                continue
            raw = entry.get("raw", "").lower()
            if query and query not in raw:
                continue
            out.append(entry)
        return out

    def _render_security_log(self):
        self._sec_txt.configure(state="normal")
        self._sec_txt.delete("1.0", "end")
        for entry in self._filtered_security_entries():
            ln = entry.get("raw", "")
            tag = "info"
            if entry.get("status") == "OK":
                tag = "ok"
            elif entry.get("status") == "WARN":
                tag = "warn"
            elif entry.get("status") == "ALERT":
                tag = "err"
            self._sec_txt.insert("end", ln + "\n", tag)
        self._sec_txt.see("end")
        self._sec_txt.configure(state="disabled")

    def _export_security_csv(self):
        if not self._can("export"):
            messagebox.showwarning("Permission", "Your role cannot export security logs.")
            return
        rows = self._filtered_security_entries()
        if not rows:
            messagebox.showinfo("Export", "No rows match current filter.")
            return
        out = os.path.join(
            os.path.dirname(__file__),
            f"security_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        fields = [
            "timestamp", "user", "status", "action", "role", "session",
            "city", "event", "source", "detail",
        ]
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fields})
        self._log(f"Security export created: {os.path.basename(out)}", "ok")
        messagebox.showinfo("Export complete", f"Saved: {out}")

    def _sec_log(self, action, status="INFO", city="-", event="-", detail=""):
        line = audit_log(user=self.username, action=action, status=status,
                         city=city, event=event, detail=detail,
                         role=self.role, session_id=self.session_id)
        self._sec_entries.append(_parse_audit_line(line))
        self._render_security_log()

    def _update_stats(self):
        n      = len(self._alert_sys.regions)
        alerts = sum(1 for e in self._events.values() if _event_level(e) == "danger")
        warns  = sum(1 for e in self._events.values() if _event_level(e) == "possible")
        self._sc_total.set(n)
        self._sc_alert.set(alerts)
        self._sc_warn.set(warns)
        self._sc_clear.set(max(n - alerts - warns, 0))
        avg_risk = int(sum(self._risk_scores.values()) / len(self._risk_scores)) if self._risk_scores else 0
        self._sc_risk.set(f"{avg_risk}/100")
        self._update_smart_panel()
        if self._map_canvas and self._map_canvas.winfo_exists():
            self._draw_map()

    def _update_chips(self):
        for city, (frame, dot, lbl) in self._chips.items():
            ev = self._events.get(city)
            level = _event_level(ev)
            col = C["danger"] if level == "danger" else C["warn"] if level == "possible" else C["ok"]
            dot.delete("all")
            dot.create_oval(1, 1, 9, 9, fill=col, outline="")
            bg = C["selected"] if self._selected == city else C["bg2"]
            hl = C["accent"] if self._selected == city else C["border"]
            fg = C["accent2"] if self._selected == city else C["text"]
            frame.config(bg=bg, highlightbackground=hl)
            lbl.config(bg=bg, fg=fg)

    def _update_smart_panel(self):
        danger = [c for c, e in self._events.items() if _event_level(e) == "danger"]
        possible = [c for c, e in self._events.items() if _event_level(e) == "possible"]
        safe = max(len(self._loc) - len(danger) - len(possible), 0)
        self._ins_counts.set(
            f"Danger: {len(danger)}  |  Possible: {len(possible)}  |  Safe: {safe}")

        if self._selected:
            ev = self._events.get(self._selected)
            level = _event_level(ev)
            score = self._risk_scores.get(self._selected, 0)
            factors = ", ".join(self._risk_factors.get(self._selected, []))
            if level == "danger":
                self._ins_selected.set(f"{self._selected}: DANGER ({score}/100)")
                self._ins_tip.set(f"Top factors: {factors}")
            elif level == "possible":
                self._ins_selected.set(f"{self._selected}: POSSIBLE DANGER ({score}/100)")
                self._ins_tip.set(f"Top factors: {factors}")
            else:
                self._ins_selected.set(f"{self._selected}: SAFE ({score}/100)")
                self._ins_tip.set(f"Top factors: {factors}")
        else:
            self._ins_selected.set("No region selected")
            self._ins_tip.set("Tip: Select a region to see actions.")

        top = sorted(self._risk_scores.items(), key=lambda x: x[1], reverse=True)[:5]
        for i, var in enumerate(self._ins_top_vars):
            if i < len(top):
                city, score = top[i]
                level = _event_level(self._events.get(city))
                label = "DANGER" if level == "danger" else "POSSIBLE" if level == "possible" else "SAFE"
                var.set(f"• {city}  ({label}, {score}/100)")
            else:
                var.set("• —")

    def _focus_highest_risk(self):
        for city, ev in self._events.items():
            if _event_level(ev) == "danger":
                self._select(city)
                return
        for city, ev in self._events.items():
            if _event_level(ev) == "possible":
                self._select(city)
                return
        messagebox.showinfo("No Risk", "All regions are currently safe.")

    def _select(self, city):
        if self._selected == city:
            self._selected = None
            self._sel_lbl.config(text="No region selected")
        else:
            self._selected = city
            self._sel_lbl.config(text=f"Selected:  {city}")
        for name, card in self._cards.items():
            card.set_selected(name == self._selected)
        self._update_chips()
        self._update_smart_panel()

    # ── Data fetch ─────────────────────────────────────────────────────────────
    def _fetch_all(self):
        """Run in background thread. Updates self._cache then schedules UI update."""
        regions = list(self._loc.items())
        loaded = 0
        for city, (lat, lon) in regions:
            data = fetch_forecast(city, lat, lon)
            if data:
                cur = data.get("current", {})
                if data.get("_cached"):
                    cur["_cached"] = True
                    cur["_cached_at"] = data.get("_cached_at")
                self._cache[city] = cur
                loaded += 1
            time.sleep(1)  # Rate limiting to avoid API throttling

        def apply():
            self._events.clear()
            self._risk_scores.clear()
            self._risk_factors.clear()
            for city, wx in self._cache.items():
                ev = self._alert_sys.determine_event(wx)
                if ev:
                    self._events[city] = ev
                score, factors = self._alert_sys.calculate_risk_score(wx, ev)
                self._risk_scores[city] = score
                self._risk_factors[city] = factors
            for city, card in self._cards.items():
                card.update_weather(
                    self._cache.get(city, {}),
                    self._events.get(city),
                    self._risk_scores.get(city, 0))
            if loaded:
                self._last_refresh_ts = time.time()
            self._update_stats()
            self._update_chips()
            self._reflow()
            n = len(self._events)
            total  = len(self._loc)
            self._log(f"Refreshed {loaded}/{total} regions — "
                      f"{n} alert(s) detected",
                      "warn" if n else "ok")
            self._sec_log(action="REFRESH_COMPLETE", status="OK",
                          detail=f"loaded={loaded};total={total};flagged={n}")
            self._busy = False

        self.master.after(0, apply)

    def _refresh_async(self):
        if self._busy:
            return
        self._busy = True
        self._log("Refresh started…", "ok")
        self._sec_log(action="REFRESH_START", status="INFO",
                      detail="manual_refresh_triggered")
        threading.Thread(target=self._fetch_all, daemon=True).start()

    # ── Actions ────────────────────────────────────────────────────────────────
    def _auto_send(self):
        """Send alerts only to regions that actually need them."""
        if not self._can("auto_send"):
            messagebox.showwarning("Permission", "Your role cannot send automatic alerts.")
            self._sec_log(action="AUTO_SEND_BLOCKED", status="WARN",
                          detail="permission_denied")
            return
        if not self._cache:
            messagebox.showinfo("No Data", "Refresh weather data first.")
            self._sec_log(action="AUTO_SEND_BLOCKED", status="WARN",
                          detail="no_weather_cache")
            return
        if not self._events:
            messagebox.showinfo("All Clear",
                "No regions need alerts — all conditions are normal.")
            self._sec_log(action="AUTO_SEND_SKIPPED", status="OK",
                          detail="no_flagged_regions")
            return
        preview = "\n".join(f"  • {r}: {e.upper()}"
                            for r, e in list(self._events.items())[:12])
        extra = (f"\n  …and {len(self._events)-12} more"
                 if len(self._events) > 12 else "")
        if not messagebox.askyesno(
                "Confirm Auto Alerts",
                f"{len(self._events)} region(s) flagged:\n\n{preview}{extra}"
                "\n\nSend now?"):
            self._sec_log(action="AUTO_SEND_CANCELLED", status="WARN",
                          detail=f"flagged_regions={len(self._events)}")
            return

        def work():
            sent = 0
            sent_items = []
            for rgn, ev in self._events.items():
                entry = next((r for r in self._alert_sys.regions
                              if r["region"] == rgn), None)
                if not entry:
                    continue
                msg = self._alert_sys.create_alert(entry, ev, self._cache[rgn])
                self._alert_sys.log_to_xml(entry, ev, msg)
                notify = self._notifier.send_alert(rgn, ev, msg)
                sent += 1
                sent_items.append((rgn, ev, notify))
            self._alert_sys.save_xml()
            return sent, sent_items

        def ok(data):
            sent, sent_items = data
            self._log(f"Auto alerts sent: {sent} region(s)", "warn")
            self._sec_log(action="AUTO_SEND_COMPLETE", status="OK",
                          detail=f"sent_regions={sent}")
            for rgn, ev, notify_rows in sent_items:
                self._sec_log(action="ALERT_SENT", status="ALERT",
                              city=rgn, event=ev,
                              detail="source=auto_send")
                self._create_incident_for_alert(rgn, ev, "auto_send")
                for row in notify_rows:
                    st = row.get("status", "").upper()
                    level = "OK" if st == "SENT" else "ALERT" if st == "FAILED" else "WARN"
                    self._sec_log(
                        action="DELIVERY_STATUS",
                        status=level,
                        city=rgn,
                        event=ev,
                        detail=(
                            f"provider={row.get('provider','-')};status={row.get('status','-')};"
                            f"message_id={row.get('message_id','-')};detail={row.get('detail','-')}"
                        ),
                    )
            messagebox.showinfo("Done", f"✅  {sent} alert(s) sent.")

        def err(exc):
            self._log(f"Auto send error: {exc}", "err")
            self._sec_log(action="AUTO_SEND_ERROR", status="ALERT",
                          detail=str(exc))

        self._bg(work, ok, err)

    def _send_selected(self):
        if not self._can("send_selected"):
            messagebox.showwarning("Permission", "Your role cannot send selected alerts.")
            self._sec_log(action="SEND_SELECTED_BLOCKED", status="WARN",
                          detail="permission_denied")
            return
        if not self._selected:
            messagebox.showinfo("No Selection", "Click a region card to select it.")
            self._sec_log(action="SEND_SELECTED_BLOCKED", status="WARN",
                          detail="no_region_selected")
            return
        city  = self._selected
        entry = next((r for r in self._alert_sys.regions
                      if r["region"] == city), None)
        if not entry:
            return

        def work():
            wx = self._cache.get(city)
            if not wx:
                lat, lon = self._loc[city]
                data = fetch_forecast(city, lat, lon)
                if not data:
                    return None
                wx = data.get("current", {})
                self._cache[city] = wx
            ev = self._alert_sys.determine_event(wx)
            if not ev:
                return "clear"
            msg = self._alert_sys.create_alert(entry, ev, wx)
            self._alert_sys.log_to_xml(entry, ev, msg)
            self._alert_sys.save_xml()
            self._events[city] = ev
            return msg

        def ok(result):
            score, factors = self._alert_sys.calculate_risk_score(
                self._cache.get(city, {}), self._events.get(city)
            )
            self._risk_scores[city] = score
            self._risk_factors[city] = factors
            self._cards[city].update_weather(
                self._cache.get(city, {}), self._events.get(city), score)
            self._update_stats()
            self._update_chips()
            if result is None:
                messagebox.showerror("API Error",
                                     f"No weather data for {city}.")
                self._log(f"FAILED: {city} — no API data", "err")
                self._sec_log(action="SEND_SELECTED_ERROR", status="ALERT",
                              city=city, detail="api_data_missing")
            elif result == "clear":
                messagebox.showinfo("No Alert Needed",
                                    f"{city}: conditions normal.")
                self._log(f"CLEAR: {city}", "ok")
                self._sec_log(action="SEND_SELECTED_SKIPPED", status="OK",
                              city=city, detail="conditions_safe")
            else:
                messagebox.showinfo("Alert Sent", result)
                self._log(f"Alert sent: {city}", "warn")
                self._sec_log(action="ALERT_SENT", status="ALERT",
                              city=city, event=self._events.get(city, "-"),
                              detail="source=send_selected")
                event = self._events.get(city, "-")
                if event and event != "-":
                    self._dispatch_notifications(city, event, result)
                    self._create_incident_for_alert(city, event, "send_selected")

        def err(exc):
            self._log(f"ERROR {city}: {exc}", "err")
            self._sec_log(action="SEND_SELECTED_ERROR", status="ALERT",
                          city=city, detail=str(exc))

        self._bg(work, ok, err)

    def _send_all(self):
        if not self._can("send_all"):
            messagebox.showwarning("Permission", "Your role cannot send global alerts.")
            self._sec_log(action="SEND_ALL_BLOCKED", status="WARN",
                          detail="permission_denied")
            return
        if not self._cache:
            messagebox.showinfo("No Data", "Refresh weather data first.")
            self._sec_log(action="SEND_ALL_BLOCKED", status="WARN",
                          detail="no_weather_cache")
            return
        if not messagebox.askyesno(
                "Send All Alerts",
                f"Send alerts for ALL {len(self._alert_sys.regions)} "
                "regions regardless of conditions?"):
            self._sec_log(action="SEND_ALL_CANCELLED", status="WARN",
                          detail="user_cancelled")
            return

        def work():
            sent_items = []
            for region_entry in self._alert_sys.regions:
                city = region_entry["region"]
                weather = self._cache.get(city)
                if not weather:
                    continue
                event = self._alert_sys.determine_event(weather) or "rain"
                msg = self._alert_sys.create_alert(region_entry, event, weather)
                self._alert_sys.log_to_xml(region_entry, event, msg)
                notify = self._notifier.send_alert(city, event, msg)
                sent_items.append((city, event, notify))
            self._alert_sys.save_xml()
            return sent_items

        def ok(sent_items):
            n = len(self._alert_sys.regions)
            self._log(f"All alerts sent ({n} regions)", "warn")
            self._sec_log(action="SEND_ALL_COMPLETE", status="ALERT",
                          detail=f"regions_processed={n}")
            for city, event, notify_rows in sent_items:
                self._create_incident_for_alert(city, event, "send_all")
                for row in notify_rows:
                    st = row.get("status", "").upper()
                    level = "OK" if st == "SENT" else "ALERT" if st == "FAILED" else "WARN"
                    self._sec_log(
                        action="DELIVERY_STATUS",
                        status=level,
                        city=city,
                        event=event,
                        detail=(
                            f"provider={row.get('provider','-')};status={row.get('status','-')};"
                            f"message_id={row.get('message_id','-')};detail={row.get('detail','-')}"
                        ),
                    )
            self._load_incidents()
            messagebox.showinfo("Done", "All region alerts processed.")

        def err(exc):
            self._log(f"Send all error: {exc}", "err")
            self._sec_log(action="SEND_ALL_ERROR", status="ALERT",
                          detail=str(exc))

        self._bg(work, ok, err)

    def _bg(self, fn, on_ok, on_err):
        def run():
            try:
                r = fn()
                self.master.after(0, lambda: on_ok(r))
            except Exception as exc:
                self.master.after(
                    0,
                    lambda: self._sec_log(action="BACKGROUND_TASK_ERROR",
                                          status="ALERT", detail=str(exc)))
                self.master.after(0, lambda: on_err(exc))
        threading.Thread(target=run, daemon=True).start()

    # ── Auto-refresh ───────────────────────────────────────────────────────────
    def _toggle_auto(self):
        if self._auto_after:
            self.after_cancel(self._auto_after)
            self._auto_after = None
        if self._auto_var.get():
            self._sched_auto()

    def _sched_auto(self):
        self._auto_after = self.after(
            self._int_var.get() * 1000, self._auto_tick)

    def _auto_tick(self):
        self._auto_after = None
        self._refresh_async()
        if self._auto_var.get():
            self._sched_auto()


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════
def main():
    _ensure_user_store()
    _ensure_geojson_file()
    root = tk.Tk()
    root.configure(bg=C["bg"])
    _current = [None]

    def show_login():
        if _current[0]:
            _current[0].destroy()
        f = LoginScreen(root, on_login)
        f.pack(fill="both", expand=True)
        _current[0] = f

    def on_login(auth_user):
        _current[0].destroy()
        _current[0] = None
        f = Dashboard(root, auth_user["username"], auth_user["role"], on_logout=show_login)
        f.pack(fill="both", expand=True)
        _current[0] = f

    show_login()
    root.mainloop()



if __name__ == "__main__":
    main()
