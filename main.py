import tkinter as tk
from tkinter import messagebox, simpledialog, font, ttk
from weather import locations, fetch_forecast
from alerts import WeatherAlertSystemXML

class WeatherAlertDashboard:
    def __init__(self, master):
        self.master = master
        master.title("Weather Alert Dashboard")
        master.geometry("800x600")
        master.configure(bg="#1f2937")  # Dark modern background

        self.alert_system = WeatherAlertSystemXML()

        # Add all regions from weather.py
        for city, _, _ in locations:
            self.alert_system.add_region(name=city, number=f"REGION-{city}", region=city)

        # Header
        header_font = font.Font(master, size=20, weight="bold")
        self.header = tk.Label(master, text="Weather Alerts by Region", font=header_font, bg="#1f2937", fg="white")
        self.header.pack(pady=10)

        # Scrollable Canvas for cards
        self.canvas_frame = tk.Frame(master, bg="#1f2937")
        self.canvas_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(self.canvas_frame, bg="#1f2937", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#1f2937")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0,0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Buttons frame
        btn_frame = tk.Frame(master, bg="#1f2937")
        btn_frame.pack(pady=10)

        btn_style = {"width": 20, "bg": "#2563eb", "fg": "white", "bd": 0, "font": ("Arial", 12), "activebackground": "#1d4ed8"}

        self.add_region_btn = tk.Button(btn_frame, text="Add Region", command=self.add_region, **btn_style)
        self.add_region_btn.grid(row=0, column=0, padx=5)

        self.send_all_btn = tk.Button(btn_frame, text="Send All Alerts", command=self.send_all_alerts, **btn_style)
        self.send_all_btn.grid(row=0, column=1, padx=5)

        self.send_selected_btn = tk.Button(btn_frame, text="Send Selected Alert", command=self.send_selected_alert, **btn_style)
        self.send_selected_btn.grid(row=0, column=2, padx=5)

        self.refresh_btn = tk.Button(btn_frame, text="Refresh Cards", command=self.update_cards, **btn_style)
        self.refresh_btn.grid(row=0, column=3, padx=5)

        self.exit_btn = tk.Button(btn_frame, text="Exit", command=master.quit, **btn_style)
        self.exit_btn.grid(row=0, column=4, padx=5)

        # Region cards
        self.region_cards = {}
        self.selected_region = None  # Track currently selected card
        self.create_region_cards()
        self.update_cards()

    def create_region_cards(self):
        """Create clickable card frames for each region."""
        for region in self.alert_system.regions:
            card = tk.Frame(self.scrollable_frame, bg="#374151", bd=1, relief="raised", padx=10, pady=10)
            card.pack(fill="x", pady=5)
            card.bind("<Button-1>", lambda e, r=region['region']: self.select_card(r))

            title = tk.Label(card, text=region['region'], font=("Arial", 14, "bold"), bg="#374151", fg="white")
            title.pack(anchor="w")
            title.bind("<Button-1>", lambda e, r=region['region']: self.select_card(r))

            weather_label = tk.Label(card, text="Fetching weather...", font=("Consolas", 12), bg="#374151", fg="white")
            weather_label.pack(anchor="w", pady=5)
            weather_label.bind("<Button-1>", lambda e, r=region['region']: self.select_card(r))

            alert_label = tk.Label(card, text="No alert", font=("Arial", 12, "bold"), bg="#374151", fg="green")
            alert_label.pack(anchor="w")
            alert_label.bind("<Button-1>", lambda e, r=region['region']: self.select_card(r))

            self.region_cards[region['region']] = {"card": card, "weather": weather_label, "alert": alert_label}

    def select_card(self, region_name):
        """Highlight the clicked card as selected."""
        if self.selected_region:
            # Reset previous selection color
            self.region_cards[self.selected_region]['card'].config(bg="#374151")
        # Highlight new selection
        self.selected_region = region_name
        self.region_cards[region_name]['card'].config(bg="#2563eb")

    def update_cards(self):
        """Refresh card content without sending alerts."""
        weather_by_region = {}
        for city, lat, lon in locations:
            data = fetch_forecast(city, lat, lon)
            if data:
                weather_by_region[city] = data.get("current", {})

        for region in self.alert_system.regions:
            city = region['region']
            weather = weather_by_region.get(city, {})
            event = self.alert_system.determine_event(weather)

            weather_text = f"Temp: {weather.get('temp_c', 'N/A')}°C | Condition: {weather.get('condition', {}).get('text','N/A')}"
            self.region_cards[city]['weather'].config(text=weather_text)
            if event:
                self.region_cards[city]['alert'].config(text=f"⚠️ {event.upper()}", fg="red")
            else:
                self.region_cards[city]['alert'].config(text="No alert", fg="green")

    def add_region(self):
        region_names = [loc[0] for loc in locations]
        region = simpledialog.askstring("Add Region", f"Enter region to monitor:\nOptions:\n{', '.join(region_names)}")
        if not region or region not in region_names:
            messagebox.showerror("Invalid Region", "Please enter a valid region from the list.")
            return
        if region in [r['region'] for r in self.alert_system.regions]:
            messagebox.showinfo("Already Exists", f"Region {region} is already being monitored.")
            return
        self.alert_system.add_region(name=region, number=f"REGION-{region}", region=region)
        self.create_region_cards()
        self.update_cards()
        messagebox.showinfo("Success", f"Added region: {region}.")

    def send_all_alerts(self):
        """Send alerts for all regions."""
        weather_by_region = {}
        for city, lat, lon in locations:
            data = fetch_forecast(city, lat, lon)
            if data:
                weather_by_region[city] = data.get("current", {})
        self.alert_system.send_alerts(weather_by_region)
        self.update_cards()
        messagebox.showinfo("Done", "All alerts sent and logged to alert_log.xml.")

    def send_selected_alert(self):
        """Send alert only for the selected card."""
        if not self.selected_region:
            messagebox.showinfo("No Selection", "Please select a region first.")
            return
        city = self.selected_region
        data = fetch_forecast(city, next(lat for n, lat, lon in locations if n==city),
                                     next(lon for n, lat, lon in locations if n==city))
        weather = data.get("current", {}) if data else {}
        region_entry = next(r for r in self.alert_system.regions if r['region'] == city)
        event = self.alert_system.determine_event(weather)
        if event:
            message = self.alert_system.create_alert(region_entry, event, weather)
            self.alert_system.log_to_xml(region_entry, event, message)
            self.alert_system.save_xml()
            messagebox.showinfo(f"Alert Sent: {city}", message)
        else:
            messagebox.showinfo(f"No Alert: {city}", "No weather event detected for this region.")
        self.update_cards()


if __name__ == "__main__":
    root = tk.Tk()
    app = WeatherAlertDashboard(root)
    root.mainloop()