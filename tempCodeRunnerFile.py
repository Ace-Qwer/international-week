import xgboost as xgb
import pandas as pd
import numpy as np
from sklearn.metrics import confusion_matrix, classification_report

class AgriIntelligence:
    def __init__(self):
        # Using Regressor to predict human impact severity
        self.model = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=5)
        self.is_trained = False

    def train_on_history(self, history_csv='history_weather_output.csv'):
        """Phase 1: Learn from the 30-day targeted windows created by historyweather.py"""
        # 1. Load the targeted history
        df = pd.read_csv(history_csv)
        
        # 2. Features and Target
        # The target is 'is_event_day' (1 for disaster, 0 for the 29 days before it)
        features = ['avg_temp', 'max_temp', 'total_precip', 'humidity']
        X = df[features]
        y = df['is_event_day']
        
        # 3. Train
        self.model.fit(X, y)
        self.is_trained = True

        # 4. Performance Report
        y_pred = [1 if p > 0.5 else 0 for p in self.model.predict(X)]
        print("\n📊 --- AI TRAINING PERFORMANCE (30-DAY WINDOWS) ---")
        print(classification_report(y, y_pred, target_names=['Precursor', 'Disaster'], zero_division=0))

    def predict_current_risk(self, live_csv='current_weather_check.csv'):
        """Phase 2: Compare TODAY'S 30-day buildup against the history"""
        if not self.is_trained:
            self.train_on_history()

        # Load the data from weather.py (last 30 days of our time)
        live_df = pd.read_csv(live_csv)
        
        X_live = live_df[['avg_temp', 'max_temp', 'total_precip', 'humidity']]
        live_df['risk_score'] = self.model.predict(X_live)

        # Group by city to find the most dangerous trend in the last 30 days
        regional_report = live_df.groupby('city').agg({
            'date': 'max',
            'risk_score': 'max' # Find the highest risk spike in the 30 day window
        }).reset_index()

        def get_risk_label(score):
            if score > 0.8: return "🚨 DANGER"
            if score > 0.4: return "⚠️ CAUTION"
            return "✅ STABLE"

        regional_report['status'] = regional_report['risk_score'].apply(get_risk_label)
        return regional_report

if __name__ == "__main__":
    intel = AgriIntelligence()
    try:
        # Step 1: Train on the history (the past 30-day precursors)
        intel.train_on_history()
        
        # Step 2: Predict on current weather (the last 30 days of our time)
        report = intel.predict_current_risk()
        
        print("\n🌍 --- TANZANIA REGIONAL RISK REPORT (CURRENT 30-DAY TREND) ---")
        print(report[['city', 'status', 'risk_score']].to_string(index=False))
        
    except Exception as e:
        print(f"⚠️ Error in Handshake: {e}")