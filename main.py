import tkinter as tk
from tkinter import messagebox, simpledialog
from weather import locations, fetch_forecast
from alerts import WeatherAlertSystemXML

class WeatherAlertApp:
    def __init__(self, master):
        self.master = master
        master.title("Weather Alert System")

        self.alert_system = WeatherAlertSystemXML()

        # Example farmers
        example_farmers = [
            {"name": "Maria", "number": "+1234567890", "region": "Dar es Salaam"},
            {"name": "Ahmed", "number": "+0987654321", "region": "Dodoma"},
            {"name": "Lina", "number": "+1122334455", "region": "Arusha"},
        ]
        for f in example_farmers:
            self.alert_system.add_farmer(f["name"], f["number"], f["region"])

        # Farmer List
        self.farmer_listbox = tk.Listbox(master, width=50)
        self.farmer_listbox.pack(pady=10)
        self.update_farmer_list()

        # Buttons
        self.add_button = tk.Button(master, text="Add Farmer", command=self.add_farmer)
        self.add_button.pack(pady=5)

        self.send_alert_button = tk.Button(master, text="Send Alerts", command=self.send_alerts)
        self.send_alert_button.pack(pady=5)

        self.exit_button = tk.Button(master, text="Exit", command=master.quit)
        self.exit_button.pack(pady=5)

    def update_farmer_list(self):
        self.farmer_listbox.delete(0, tk.END)
        for f in self.alert_system.farmers:
            self.farmer_listbox.insert(tk.END, f"{f['name']} ({f['number']}) - {f['region']}")

    def add_farmer(self):
        name = simpledialog.askstring("Farmer Name", "Enter farmer name:")
        if not name:
            return
        number = simpledialog.askstring("Phone Number", "Enter phone number:")
        if not number:
            return
        # Choose region
        region_names = [loc[0] for loc in locations]
        region = simpledialog.askstring("Region", f"Enter region:\nOptions:\n{', '.join(region_names)}")
        if not region or region not in region_names:
            messagebox.showerror("Invalid Region", "Please enter a valid region from the list.")
            return

        self.alert_system.add_farmer(name, number, region)
        self.update_farmer_list()
        messagebox.showinfo("Success", f"Added {name} in {region}.")

    def send_alerts(self):
        messagebox.showinfo("Fetching", "Fetching weather data. Please wait...")
        weather_by_region = {}
        for city, lat, lon in locations:
            data = fetch_forecast(city, lat, lon)
            if data:
                weather_by_region[city] = data.get("current", {})
        self.alert_system.send_alerts(weather_by_region)
        messagebox.showinfo("Done", "Alerts sent and logged to alert_log.xml.")

if __name__ == "__main__":
    root = tk.Tk()
    app = WeatherAlertApp(root)
    root.mainloop()