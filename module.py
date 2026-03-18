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
    
    
if __name__ == "__main__":
    # 1. Create fake weather data to test the logic
    print(" Starting Internal Module Test...")
    
    test_data = {
        'city': ['Test_Flood', 'Test_Drought', 'Test_Safe'],
        'avg_temp': [25, 38, 22],
        'max_temp': [28, 40, 25],
        'total_precip': [65, 1, 5], # 65mm should trigger flood
        'humidity': [90, 20, 50]
    }
    
    test_df = pd.DataFrame(test_data)
    
    # 2. Initialize and Train the Brain
    intel = AgriIntelligence()
    print("Brain initialized. Training on test rules...")
    intel.train_on_rules(test_df)
    
    # 3. Predict and Verify
    results = intel.predict_risks(test_df)
    
    print("\n--- TEST RESULTS ---")
    if not results.empty:
        print("AI identified these risks successfully:")
        print(results[['city', 'ai_prediction']])
        
        # Simple verification
        if 'Test_Flood' in results['city'].values:
            print("✅ Success: AI caught the flood risk.")
        if 'Test_Drought' in results['city'].values:
            print("✅ Success: AI caught the drought risk.")
    else:
        print("❌ Error: AI failed to identify the risks.")