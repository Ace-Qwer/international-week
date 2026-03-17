import xgboost as xgb
import pandas as pd

class AgriIntelligence:
    def __init__(self):
        self.model = xgb.XGBClassifier()
        # Pre-train with your expert rules (logic thresholds)
        self.is_trained = False

    def train_on_rules(self, weather_df):
        def check_risk(row):
            if row['total_precip'] > 50 or (row['max_temp'] > 35 and row['total_precip'] < 2):
                return 1
            return 0
        
        weather_df['is_danger'] = weather_df.apply(check_risk, axis=1)
        X = weather_df[['avg_temp', 'max_temp', 'total_precip', 'humidity']]
        y = weather_df['is_danger']
        
        self.model.fit(X, y)
        self.is_trained = True

    def predict_risks(self, weather_df):
        X = weather_df[['avg_temp', 'max_temp', 'total_precip', 'humidity']]
        weather_df['ai_prediction'] = self.model.predict(X)
        return weather_df[weather_df['ai_prediction'] == 1]