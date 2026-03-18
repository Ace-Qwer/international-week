import requests
import pandas as pd
from datetime import datetime, timedelta

API_KEY = "6471d6b96a0646ab81f90409261703"  

# List of Tanzanian locations
locations = [
    ("Dar es Salaam", -6.7924, 39.2083),
    ("Dodoma", -6.1620, 35.7516),
    ("Arusha", -3.3869, 36.6830),
    ("Mwanza", -2.5167, 32.9001),
    ("Mbeya", -8.9000, 33.4833),
    ("Zanzibar", -6.1630, 39.1970),
    ("Morogoro", -6.8167, 37.6667),
    ("Tanga", -5.0667, 39.1000),
    # ... add remaining locations if needed
]

# Function to fetch historical weather for a specific date
def fetch_historical(city, lat, lon, date):
    url = "https://api.weatherapi.com/v1/history.json"
    params = {
        "key": API_KEY,
        "q": f"{lat},{lon}",
        "dt": date  # format: YYYY-MM-DD
    }
    response = requests.get(url, params=params)
    return response.json() if response.status_code == 200 else None

# Collect historical data
all_weather_data = []

# Example: last 7 days
from datetime import datetime, timedelta, timezone

# Example: last 7 days
num_days = 7
for city, lat, lon in locations:
    for i in range(num_days):
        date = (datetime.now(timezone.utc) - timedelta(days=i+1)).strftime("%Y-%m-%d")
        data = fetch_historical(city, lat, lon, date)
        if data:
            day = data.get("forecast", {}).get("forecastday", [])[0]["day"]
            all_weather_data.append({
                "city": city,
                "date": date,
                "avg_temp": day.get('avgtemp_c'),
                "max_temp": day.get('maxtemp_c'),
                "min_temp": day.get('mintemp_c'),
                "total_precip": day.get('totalprecip_mm'),
                "humidity": day.get('avghumidity'),
                "condition_text": day.get('condition', {}).get('text'),
                "max_wind_kph": day.get('maxwind_kph'),
                "uv": day.get('uv')
            })

# Create pandas DataFrame
df = pd.DataFrame(all_weather_data)
if df.empty:
    print("CRITICAL: No historical data was collected.")
else:
    print(f"Success: Collected historical data for {len(df)} entries.")
print(df.head())