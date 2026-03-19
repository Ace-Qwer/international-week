import xgboost as xgb
import pandas as pd
import numpy as np
from sklearn.metrics import confusion_matrix, classification_report

class AgriIntelligence:
    def __init__(self):
        self.model = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=5)
        self.is_trained = False

    def train_on_history(self, history_csv='history_weather_output.csv'):
        df = pd.read_csv(history_csv)
        features = ['avg_temp', 'max_temp', 'total_precip', 'humidity']
        X = df[features]
        y = df['is_event_day']
        
        self.model.fit(X, y)
        self.is_trained = True
        print("🧠 AI Training Complete.")

    def predict_current_risk(self, live_csv='current_weather_check.csv'):
        if not self.is_trained:
            self.train_on_history()

        live_df = pd.read_csv(live_csv)
        X_live = live_df[['avg_temp', 'max_temp', 'total_precip', 'humidity']]
        live_df['risk_score'] = self.model.predict(X_live)

        # 🚀 NEW: Hazard Identification Logic
        def identify_hazard(row):
            if row['risk_score'] < 0.4:
                return "Stable"
            
            # If precipitation is high, it's likely a Flood pattern
            if row['total_precip'] > 5.0: 
                return "FLOOD"
            # If temp is high and humidity is low, it's likely a Drought pattern
            elif row['avg_temp'] > 28 and row['humidity'] < 50:
                return "DROUGHT"
            else:
                return "Extreme Weather"

        live_df['hazard_type'] = live_df.apply(identify_hazard, axis=1)

        # Get the highest risk day for each city
        regional_report = live_df.sort_values('risk_score', ascending=False).groupby('city').head(1).copy()
        
        def get_status(row):
            score = row['risk_score']
            hazard = row['hazard_type']
            if score > 0.8: return f"🚨 DANGER: {hazard}"
            if score > 0.4: return f"⚠️ CAUTION: {hazard}"
            return "✅ SAFE"

        regional_report['status'] = regional_report.apply(get_status, axis=1)
        return regional_report[['city', 'status', 'risk_score', 'total_precip', 'avg_temp']]

if __name__ == "__main__":
    intel = AgriIntelligence()
    try:
        intel.train_on_history()
        report = intel.predict_current_risk()
        
        print("\n🌍 --- TANZANIA REGIONAL RISK REPORT ---")
        # Added columns to show WHY the AI chose that status
        print(report.to_string(index=False))
        
    except Exception as e:
        print(f"⚠️ Error: {e}")