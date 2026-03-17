import requests
import os

API_KEY = os.getenv("WEATHER_API_KEY", "6471d6b96a0646ab81f90409261703")

# Expanded list of Tanzanian locations (cities and regional capitals)
locations = [
    ("Dar es Salaam", -6.7924, 39.2083),
    ("Dodoma", -6.1620, 35.7516),
    ("Arusha", -3.3869, 36.6830),
    ("Mwanza", -2.5167, 32.9001),
    ("Mbeya", -8.9000, 33.4833),
    ("Zanzibar", -6.1630, 39.1970),
    ("Morogoro", -6.8167, 37.6667),
    ("Tanga", -5.0667, 39.1000),
    ("Kigoma", -4.8824, 29.6267),
    ("Moshi", -3.3400, 37.3400),
    ("Sumbawanga", -7.9489, 31.6169),
    ("Songea", -10.6833, 35.6500),
    ("Kahama", -3.8333, 32.6000),
    ("Mpanda", -6.3438, 31.0695),
    ("Musoma", -1.5000, 33.8000),
    ("Shinyanga", -3.6667, 33.4333),
    ("Tabora", -5.0167, 32.8000),
    ("Singida", -4.8167, 34.7500),
    ("Rukwa", -7.8667, 31.5000),
    ("Ruvuma", -10.6333, 35.7667),
    ("Manyara", -3.8667, 35.7500),
    ("Katavi", -6.8000, 31.4000),
    ("Geita", -2.8500, 32.2000),
    ("Songwe", -9.3000, 33.5000),
    ("Kilimanjaro", -3.0674, 37.3556),
    ("Pwani", -6.8000, 38.9000),
    ("Kagera", -1.0000, 31.0000),
    ("Njombe", -9.3333, 35.7000),
    ("Kusini Unguja", -6.2000, 39.3500),
    ("Kaskazini Unguja", -5.0000, 39.3000),
    ("Kusini Pemba", -5.2000, 39.7500),
    ("Kaskazini Pemba", -5.0000, 39.7000),
    ("Mjini Magharibi", -6.1600, 39.2000),
]

def fetch_forecast(city, lat, lon):
    url = "https://api.weatherapi.com/v1/forecast.json"
    params = {"key": API_KEY, "q": f"{lat},{lon}", "days": 3}
    try:
        response = requests.get(url, params=params, timeout=12)
    except requests.RequestException:
        return None
    return response.json() if response.status_code == 200 else None


def collect_weather_data():
    all_weather_data = []
    for city, lat, lon in locations:
        data = fetch_forecast(city, lat, lon)
        if not data:
            continue

        forecast_days = data.get("forecast", {}).get("forecastday", [])
        if not forecast_days:
            continue

        forecast_day = forecast_days[0].get("day", {})
        current = data.get("current", {})

        all_weather_data.append(
            {
                "city": city,
                "avg_temp": forecast_day.get("avgtemp_c"),
                "max_temp": forecast_day.get("maxtemp_c"),
                "total_precip": forecast_day.get("totalprecip_mm"),
                "humidity": current.get("humidity"),
                "condition_text": current.get("condition", {}).get("text"),
            }
        )
    return all_weather_data


def build_weather_dataframe():
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required for dataframe features. Install with: pip install pandas")

    return pd.DataFrame(collect_weather_data())


if __name__ == "__main__":
    df = build_weather_dataframe()
    if df.empty:
        print("CRITICAL: No weather data was collected. AI training aborted.")
    else:
        print(f"Success: Collected data for {len(df)} Tanzanian regions.")
    print(df.head())