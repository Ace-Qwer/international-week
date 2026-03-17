from datetime import datetime
import xml.etree.ElementTree as ET

class WeatherAlertSystemXML:
    """Send weather alerts to farmers and log them to XML."""

    ADVICE = {
        "flood": "Move livestock to higher ground and protect crops from water damage.",
        "drought": "Delay planting and conserve water for essential crops.",
        "storm": "Secure loose equipment and reinforce crop protection.",
        "heatwave": "Provide extra water to crops and shade for livestock.",
        "cold_snap": "Protect crops from frost and keep animals warm.",
        "rain": "Ensure drainage is clear and crops are protected.",
    }

    def __init__(self, xml_filename="alert_log.xml"):
        self.farmers = []  # List of {"name", "number", "region"}
        self.xml_filename = xml_filename
        self.root = ET.Element("Alerts")

    def add_farmer(self, name, number, region):
        self.farmers.append({"name": name, "number": number, "region": region})

    def determine_event(self, weather):
        """Determine alert type based on temperature, precipitation, or condition."""
        temp = weather.get("temp_c")
        precip = weather.get("precip_mm", 0)
        condition = weather.get("condition", {})
        condition_text = condition.get("text", "").lower()  # Extract only the text

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

    def create_alert(self, farmer, event, weather):
        """Create personalized alert using only the text of the condition."""
        temp = weather.get("temp_c")
        condition = weather.get("condition", {})
        condition_text = condition.get("text", "Unknown")  # Only text
        advice = self.ADVICE.get(event, "Stay alert and monitor conditions.")

        message = (
            f"Hello {farmer['name']} in {farmer['region']}!\n"
            f"⚠️ Weather Alert: {event.upper()}\n"
            f"Current Temp: {temp}°C\n"
            f"Condition: {condition_text}\n"
            f"Action: {advice}"
        )
        return message

    def log_to_xml(self, farmer, event, message):
        """Log a sent message to the XML structure."""
        alert = ET.SubElement(self.root, "Alert")
        ET.SubElement(alert, "Timestamp").text = datetime.now().isoformat()
        ET.SubElement(alert, "Farmer").text = farmer['name']
        ET.SubElement(alert, "Number").text = farmer['number']
        ET.SubElement(alert, "Region").text = farmer['region']
        ET.SubElement(alert, "Event").text = event
        ET.SubElement(alert, "Message").text = message

    def save_xml(self):
        """Write the XML file with pretty formatting."""
        from xml.dom import minidom
        xml_str = ET.tostring(self.root, 'utf-8')
        pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="  ")
        with open(self.xml_filename, "w", encoding="utf-8") as f:
            f.write(pretty_xml)
        print(f"Alerts saved to {self.xml_filename}")

    def send_alerts(self, weather_by_region):
        """Send alerts to all farmers based on current weather."""
        for farmer in self.farmers:
            region = farmer['region']
            weather = weather_by_region.get(region)
            if weather:
                event = self.determine_event(weather)
                if event:
                    message = self.create_alert(farmer, event, weather)
                    print(f"Sending to {farmer['number']}:\n{message}\n")
                    self.log_to_xml(farmer, event, message)
        self.save_xml()