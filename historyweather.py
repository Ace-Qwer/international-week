import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import time

API_KEY = "6471d6b96a0646ab81f90409261703"  

# 1. Map for Coordinates (Required to turn "Region" name into a location for the API)
region_map = {
    "Arusha": (-3.3869, 36.6830), "Dar es Salaam": (-6.7924, 39.2083),
    "Dodoma": (-6.1620, 35.7516), "Geita": (-2.8500, 32.2000),
    "Iringa": (-7.7667, 35.7000), "Kagera": (-1.0000, 31.0000),
    "Katavi": (-6.8000, 31.4000), "Kigoma": (-4.8824, 29.6267),
    "Kilimanjaro": (-3.0674, 37.3556), "Lindi": (-9.9971, 39.7165),
    "Manyara": (-3.8667, 35.7500), "Mara": (-1.5000, 33.8000),
    "Mbeya": (-8.9000, 33.4833), "Morogoro": (-6.8167, 37.6667),
    "Mtwara": (-10.2736, 40.1828), "Mwanza": (-2.5167, 32.9001),
    "Njombe": (-9.3333, 35.7000), "Pwani": (-6.8000, 38.9000),
    "Rukwa": (-7.8667, 31.5000), "Ruvuma": (-10.6333, 35.7667),
    "Shinyanga": (-3.6667, 33.4333), "Simiyu": (-2.8309, 34.1532),
    "Singida": (-4.8167, 34.7500), "Songwe": (-9.3000, 33.5000),
    "Tabora": (-5.0167, 32.8000), "Tanga": (-5.0667, 39.1000)
}

def fetch_historical(lat, lon, date_str):
    url = "https://api.weatherapi.com/v1/history.json"
    params = {"key": API_KEY, "q": f"{lat},{lon}", "dt": date_str}
    response = requests.get(url, params=params)
    return response.json() if response.status_code == 200 else None

all_weather_data = []
disaster_df = pd.read_csv('tanzania_floods_droughts_cleaned.csv')

# 2. Targeted Loop through every disaster event
for index, event in disaster_df.iterrows():
    region_name = event['Region']
    
    # Check if we have coordinates for this region
    if region_name not in region_map:
        continue
    
    lat, lon = region_map[region_name]
    event_date = pd.to_datetime(event['Date'])

    print(f"🛰️ Scraping 30-day window for {region_name} leading to {event['Disaster_Type']} on {event_date.date()}")

    # 3. Lookback Logic: 30 days BEFORE the disaster
    for day_offset in range(30, -1, -1):
        target_date = (event_date - timedelta(days=day_offset)).strftime("%Y-%m-%d")
        
        # We use 'target_date' here, not 'i'
        data = fetch_historical(lat, lon, target_date)
        
        if data and "forecast" in data:
            day = data["forecast"]["forecastday"][0]["day"]
            all_weather_data.append({
                "city": region_name,
                "date": target_date,
                "avg_temp": day.get('avgtemp_c'),
                "max_temp": day.get('maxtemp_c'),
                "total_precip": day.get('totalprecip_mm'),
                "humidity": day.get('avghumidity'),
                # This label helps the AI distinguish precursors (0) from the actual disaster (1)
                "is_event_day": 1 if day_offset == 0 else 0 
            })
            time.sleep(0.15) # Stay safe from API rate limits

# 4. Save results
df = pd.DataFrame(all_weather_data)
if not df.empty:
    df.to_csv('history_weather_output.csv', index=False)
    print(f"✅ Master History File Saved! Collected {len(df)} targeted weather days.")
else:
    print("❌ No data collected. Verify API key or file paths.")