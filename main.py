"""
Farmer Alert — Admin Platform
Login-protected admin dashboard.  Visual style based on MAIN_STYLE.py.
"""
import math
import os
import threading
import time
from datetime import datetime

import tkinter as tk
from tkinter import messagebox, ttk

from alerts import WeatherAlertSystemXML
from weather import fetch_forecast, locations

# ── Auth ──────────────────────────────────────────────────────────────────────
CREDENTIALS = {"admin": "admin123", "farmer": "farm2026"}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 30
SECURITY_LOG_FILE = os.path.join(
    os.path.dirname(__file__), "security_audit.log")

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


def audit_log(user, action, status="INFO", city="-", event="-", detail=""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = (
        f"{ts} | user={user or '-'} | status={status} | action={action} "
        f"| city={city} | event={event} | detail={detail}\n"
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

    def update_weather(self, weather, event):
        if not weather:
            return
        temp  = weather.get("temp_c", "—")
        feels = weather.get("feelslike_c", "—")
        cond  = weather.get("condition", {}).get("text", "N/A")
        hum   = weather.get("humidity", "—")
        wind  = weather.get("wind_kph", "—")
        uv    = weather.get("uv", "—")
        pres  = weather.get("pressure_mb", "—")

        self._icon.config(text=_wx_icon(cond))
        self._temp.config(text=f"{temp}°C")
        self._cond.config(text=f"{cond}  ·  Feels {feels}°C")

        for k, (var, unit) in self._meta.items():
            val = {"Humidity": hum, "Wind": wind, "UV": uv, "Pressure": pres}[k]
            var.set(f"{val}{unit}")

        level = _event_level(event)
        if level == "danger":
            self._badge.config(text=f"⛔  DANGER • {event.upper()}",
                               fg=C["danger"], bg="#2a1a1a")
            if not self._selected:
                self.configure(highlightbackground=C["danger"])
        elif level == "possible":
            self._badge.config(text=f"⚠  POSSIBLE DANGER • {event.upper()}",
                               fg=C["warn"], bg="#2a2000")
            if not self._selected:
                self.configure(highlightbackground=C["warn"])
        else:
            self._badge.config(text="✓  SAFE", fg=C["ok"], bg=C["bg3"])
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

        if CREDENTIALS.get(user) == pwd:
            self._failed_attempts = 0
            audit_log(user=user, action="LOGIN_SUCCESS", status="OK",
                      detail="dashboard_access_granted")
            self._on_success(user)
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


# ══════════════════════════════════════════════════════════════════════════════
#  Dashboard
# ══════════════════════════════════════════════════════════════════════════════
class Dashboard(tk.Frame):
    def __init__(self, master, username, on_logout):
        super().__init__(master, bg=C["bg"])
        self.username    = username
        self._on_logout  = on_logout
        self._selected   = None
        self._cards      = {}
        self._cache      = {}   # city → weather dict
        self._events     = {}   # city → event str
        self._busy       = False
        self._auto_after = None

        master.title("Farmer Alert — Admin Dashboard")
        master.geometry("1280x820")
        master.minsize(1000, 640)
        master.resizable(True, True)

        self._alert_sys  = WeatherAlertSystemXML()
        self._loc        = {city: (lat, lon) for city, lat, lon in locations}
        for city, _, _ in locations:
            self._alert_sys.add_region(name=city,
                                       number=f"RGN-{city}", region=city)

        self._apply_ttk_styles()
        self._build()
        self._sec_log(action="DASHBOARD_LOGIN", status="OK",
                      detail="dashboard_opened")
        self.master.after(200, self._bring_front)
        self.master.after(400, lambda: threading.Thread(
            target=self._fetch_all, daemon=True).start())

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
        tk.Label(right, text=f"👤  {self.username.upper()}",
                 font=("Courier New", 10, "bold"),
                 bg=C["bg2"], fg=C["accent2"]).pack(side="left", padx=(0, 16))

        # clock
        self._clock_var = tk.StringVar()
        tk.Label(right, textvariable=self._clock_var,
                 font=("Courier New", 13),
                 bg=C["bg2"], fg=C["muted"]).pack(side="left", padx=(0, 20))

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

        for i, w in enumerate([self._sc_total, self._sc_alert,
                                self._sc_warn, self._sc_clear]):
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

        tk.Button(parent, text="Focus Highest Risk", font=("Courier New", 9, "bold"),
                  bg=C["accent"], fg="#000", relief="flat", bd=0,
                  activebackground=C["accent2"], activeforeground="#000",
                  cursor="hand2", padx=10, pady=7,
                  command=self._focus_highest_risk).pack(fill="x", padx=14, pady=(0, 10))

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
        for txt, bg, fg, active_bg, cmd in [
            ("↻ Refresh All",       C["accent"],  "#000", C["accent2"],       self._refresh_async),
            ("⚠ Auto Alerts",       C["danger"],  "#fff", "#ff5555",          self._auto_send),
            ("⚠ Send Selected",     C["warn"],    "#000", "#ffdd00",          self._send_selected),
            ("⚠ Send All",          C["danger"],  "#fff", "#ff5555",          self._send_all),
        ]:
            b = tk.Button(bar, text=txt, bg=bg, fg=fg,
                          activebackground=active_bg,
                          activeforeground=fg,
                          command=cmd, **kw)
            b.pack(side="right", padx=4)

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
        tabs.add(t1, text="Activity")
        tabs.add(t2, text="Security")

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

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _tick(self):
        self._clock_var.set(time.strftime("%H:%M:%S"))
        self.after(1000, self._tick)

    def _bring_front(self):
        self.master.lift()
        self.master.attributes("-topmost", True)
        self.master.after(300,
                          lambda: self.master.attributes("-topmost", False))

    def _logout(self):
        if messagebox.askyesno("Logout", "Return to login screen?"):
            self._sec_log(action="LOGOUT", status="OK", detail="user_requested")
            self._on_logout()

    def _log(self, msg, kind="ok"):
        ts = time.strftime("%H:%M:%S")
        self._log_txt.configure(state="normal")
        self._log_txt.insert("end", ts + "  ", "ts")
        self._log_txt.insert("end", msg + "\n", kind)
        self._log_txt.see("end")
        self._log_txt.configure(state="disabled")

    def _load_security_log_tail(self):
        for ln in read_audit_tail(limit=300):
            tag = "info"
            if "| status=OK |" in ln:
                tag = "ok"
            elif "| status=WARN |" in ln:
                tag = "warn"
            elif "| status=ALERT |" in ln:
                tag = "err"
            self._sec_txt.configure(state="normal")
            self._sec_txt.insert("end", ln + "\n", tag)
            self._sec_txt.configure(state="disabled")
        self._sec_txt.see("end")

    def _sec_log(self, action, status="INFO", city="-", event="-", detail=""):
        line = audit_log(user=self.username, action=action, status=status,
                         city=city, event=event, detail=detail)
        tag = "info"
        if status == "OK":
            tag = "ok"
        elif status == "WARN":
            tag = "warn"
        elif status == "ALERT":
            tag = "err"
        self._sec_txt.configure(state="normal")
        self._sec_txt.insert("end", line + "\n", tag)
        self._sec_txt.see("end")
        self._sec_txt.configure(state="disabled")

    def _update_stats(self):
        n      = len(self._alert_sys.regions)
        alerts = sum(1 for e in self._events.values() if _event_level(e) == "danger")
        warns  = sum(1 for e in self._events.values() if _event_level(e) == "possible")
        self._sc_total.set(n)
        self._sc_alert.set(alerts)
        self._sc_warn.set(warns)
        self._sc_clear.set(max(n - alerts - warns, 0))
        self._update_smart_panel()

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
            if level == "danger":
                self._ins_selected.set(f"{self._selected}: DANGER")
                self._ins_tip.set("Tip: Send alert immediately and monitor every refresh.")
            elif level == "possible":
                self._ins_selected.set(f"{self._selected}: POSSIBLE DANGER")
                self._ins_tip.set("Tip: Watch closely and send targeted advisory alert.")
            else:
                self._ins_selected.set(f"{self._selected}: SAFE")
                self._ins_tip.set("Tip: No immediate action required.")
        else:
            self._ins_selected.set("No region selected")
            self._ins_tip.set("Tip: Select a region to see actions.")

        top = danger + possible
        for i, var in enumerate(self._ins_top_vars):
            if i < len(top):
                city = top[i]
                level = "DANGER" if city in danger else "POSSIBLE"
                var.set(f"• {city}  ({level})")
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
        for city, (lat, lon) in regions:
            data = fetch_forecast(city, lat, lon)
            if data:
                cur = data.get("current", {})
                self._cache[city] = cur

        def apply():
            self._events.clear()
            for city, wx in self._cache.items():
                ev = self._alert_sys.determine_event(wx)
                if ev:
                    self._events[city] = ev
            for city, card in self._cards.items():
                card.update_weather(
                    self._cache.get(city, {}),
                    self._events.get(city))
            self._update_stats()
            self._update_chips()
            self._reflow()
            n = len(self._events)
            loaded = len(self._cache)
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
                sent += 1
                sent_items.append((rgn, ev))
            self._alert_sys.save_xml()
            return sent, sent_items

        def ok(data):
            sent, sent_items = data
            self._log(f"Auto alerts sent: {sent} region(s)", "warn")
            self._sec_log(action="AUTO_SEND_COMPLETE", status="OK",
                          detail=f"sent_regions={sent}")
            for rgn, ev in sent_items:
                self._sec_log(action="ALERT_SENT", status="ALERT",
                              city=rgn, event=ev,
                              detail="source=auto_send")
            messagebox.showinfo("Done", f"✅  {sent} alert(s) sent.")

        def err(exc):
            self._log(f"Auto send error: {exc}", "err")
            self._sec_log(action="AUTO_SEND_ERROR", status="ALERT",
                          detail=str(exc))

        self._bg(work, ok, err)

    def _send_selected(self):
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
            self._cards[city].update_weather(
                self._cache.get(city, {}), self._events.get(city))
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

        def err(exc):
            self._log(f"ERROR {city}: {exc}", "err")
            self._sec_log(action="SEND_SELECTED_ERROR", status="ALERT",
                          city=city, detail=str(exc))

        self._bg(work, ok, err)

    def _send_all(self):
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
            self._alert_sys.send_alerts(self._cache)

        def ok(_):
            n = len(self._alert_sys.regions)
            self._log(f"All alerts sent ({n} regions)", "warn")
            self._sec_log(action="SEND_ALL_COMPLETE", status="ALERT",
                          detail=f"regions_processed={n}")
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
    root = tk.Tk()
    root.configure(bg=C["bg"])
    _current = [None]

    def show_login():
        if _current[0]:
            _current[0].destroy()
        f = LoginScreen(root, on_login)
        f.pack(fill="both", expand=True)
        _current[0] = f

    def on_login(username):
        _current[0].destroy()
        _current[0] = None
        f = Dashboard(root, username, on_logout=show_login)
        f.pack(fill="both", expand=True)
        _current[0] = f

    show_login()
    root.mainloop()



if __name__ == "__main__":
    main()
