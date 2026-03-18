from datetime import datetime
import xml.etree.ElementTree as ET
import os

class WeatherAlertSystemXML:
    """Send weather alerts to regions and log them to XML (append mode)."""

    ADVICE = {
        "flood": "Move livestock to higher ground and protect crops from water damage.",
        "drought": "Delay planting and conserve water for essential crops.",
        "storm": "Secure loose equipment and reinforce crop protection.",
        "heatwave": "Provide extra water to crops and shade for livestock.",
        "cold_snap": "Protect crops from frost and keep animals warm.",
        "rain": "Ensure drainage is clear and crops are protected.",
    }

    def __init__(self, xml_filename="alert_log.xml"):
        self.regions = []  # List of {"name", "number", "region"}
        self.xml_filename = xml_filename

        # Load existing XML or create root if file doesn't exist
        if os.path.exists(xml_filename):
            self.tree = ET.parse(xml_filename)
            self.root = self.tree.getroot()
        else:
            self.root = ET.Element("Alerts")
            self.tree = ET.ElementTree(self.root)

    def add_region(self, name, number, region):
        """Add a region placeholder for alerts."""
        if any(entry.get("region") == region for entry in self.regions):
            return False
        self.regions.append({"name": name, "number": number, "region": region})
        return True

    def determine_event(self, weather):
        """Determine alert type based on temperature, precipitation, or condition."""
        temp = weather.get("temp_c")
        precip = weather.get("precip_mm", 0)
        condition = weather.get("condition", {})
        condition_text = condition.get("text", "").lower()

        if "storm" in condition_text:
            return "storm"
        elif "rain" in condition_text and precip > 20:
            return "flood"
        elif temp is not None and temp > 35:
            return "heatwave"
        elif temp is not None and temp < 10:
            return "cold_snap"
        elif "drought" in condition_text:
            return "drought"
        elif "rain" in condition_text:
            return "rain"
        else:
            return None

    def calculate_risk_score(self, weather, event=None):
        """Return a 0-100 risk score and the top contributing factors."""
        score = 0
        factors = []

        temp = weather.get("temp_c")
        precip = weather.get("precip_mm", 0)
        humidity = weather.get("humidity")
        wind = weather.get("wind_kph")
        uv = weather.get("uv")
        condition_text = weather.get("condition", {}).get("text", "").lower()

        if temp is not None:
            if temp >= 38:
                score += 35
                factors.append("extreme heat")
            elif temp >= 34:
                score += 22
                factors.append("high temperature")
            elif temp <= 7:
                score += 25
                factors.append("extreme cold")
            elif temp <= 12:
                score += 14
                factors.append("cold conditions")

        if precip >= 35:
            score += 30
            factors.append("very heavy rain")
        elif precip >= 20:
            score += 20
            factors.append("heavy rain")
        elif precip >= 8:
            score += 8
            factors.append("moderate rain")

        if humidity is not None and humidity >= 88:
            score += 8
            factors.append("very high humidity")

        if wind is not None and wind >= 45:
            score += 12
            factors.append("strong wind")

        if uv is not None and uv >= 8:
            score += 7
            factors.append("high UV")

        if "storm" in condition_text or "thunder" in condition_text:
            score += 35
            factors.append("storm signal")

        if event == "flood":
            score += 20
        elif event == "storm":
            score += 18
        elif event == "heatwave":
            score += 15
        elif event in {"cold_snap", "drought"}:
            score += 10
        elif event == "rain":
            score += 6

        score = max(0, min(100, score))
        if not factors:
            factors = ["stable weather pattern"]
        return score, factors[:3]

    def create_alert(self, region_entry, event, weather):
        """Create alert message for a region."""
        temp = weather.get("temp_c")
        condition = weather.get("condition", {})
        condition_text = condition.get("text", "Unknown")
        advice = self.ADVICE.get(event, "Stay alert and monitor conditions.")

        message = (
            f"Region: {region_entry['region']}\n"
            f"⚠️ Weather Alert: {event.upper()}\n"
            f"Current Temp: {temp}°C\n"
            f"Condition: {condition_text}\n"
            f"Action: {advice}"
        )
        return message

    def log_to_xml(self, region_entry, event, message):
        alert = ET.SubElement(self.root, "Alert")
        ET.SubElement(alert, "Timestamp").text = datetime.now().isoformat()
        ET.SubElement(alert, "Region").text = region_entry['region']
        ET.SubElement(alert, "Event").text = event
        ET.SubElement(alert, "Message").text = message

    def save_xml(self):
        """Save XML to file, appending new alerts to existing log."""
        from xml.dom import minidom
        xml_str = ET.tostring(self.root, 'utf-8')
        pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="  ")
        with open(self.xml_filename, "w", encoding="utf-8") as f:
            f.write(pretty_xml)
        print(f"Alerts saved (appended) to {self.xml_filename}")

    def send_alerts(self, weather_by_region):
        """Send alerts to all regions based on current weather."""
        for region_entry in self.regions:
            region = region_entry['region']
            weather = weather_by_region.get(region)
            if weather:
                event = self.determine_event(weather)
                if event:
                    message = self.create_alert(region_entry, event, weather)
                    print(f"Alert for {region}:\n{message}\n")
                    self.log_to_xml(region_entry, event, message)
        self.save_xml()