from weather import locations, fetch_forecast
from alerts import WeatherAlertSystemXML
from module import AgriIntelligence
# Example farmers
farmers = [
    {"name": "Maria", "number": "+1234567890", "region": "Dar es Salaam"},
    {"name": "Ahmed", "number": "+0987654321", "region": "Dodoma"},
    {"name": "Lina", "number": "+1122334455", "region": "Arusha"},
]

# Fetch current weather for all regions
weather_by_region = {}
for city, lat, lon in locations:
    data = fetch_forecast(city, lat, lon)
    if data:
        weather_by_region[city] = data.get("current", {})
    else:
        print(f"Could not fetch weather for {city}")

# Initialize alert system
alert_system = WeatherAlertSystemXML()
for f in farmers:
    alert_system.add_farmer(f["name"], f["number"], f["region"])

# Send alerts based on current weather
alert_system.send_alerts(weather_by_region)