import xgboost as xgb
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from datetime import datetime, timedelta


class AgriIntelligence:
    """
    Flood risk is predicted by an XGBClassifier trained on 30-day rolling
    weather windows before known flood events.

    Drought risk uses a rule-based Drought Severity Index (DSI) because the
    historical dataset contains no drought-labelled records. The DSI combines:
      - 30-day cumulative precipitation deficit (below climatological normal)
      - Sustained high temperature
      - Low humidity
    Each dimension is scored 0-1 and the composite DSI drives drought alerts.
    """

    # Tanzania long-term monthly normal precip (mm/day) — used for drought baseline
    MONTHLY_PRECIP_NORMAL = {
        1: 4.0, 2: 4.5, 3: 6.5, 4: 8.0, 5: 4.5, 6: 1.0,
        7: 0.5, 8: 0.5, 9: 1.0, 10: 2.5, 11: 4.5, 12: 5.0
    }

    def __init__(self):
        self.flood_model = None
        self.is_trained = False
        self.flood_precip_7d = None
        self.flood_humidity = None
        self.drought_temp_thresh = None
        self.drought_humidity_thresh = None

    # ------------------------------------------------------------------
    # Feature Engineering
    # ------------------------------------------------------------------

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add rolling weather features that are predictive of flood onset."""
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(['city', 'date'])

        grp = df.groupby('city')
        df['rolling_precip_7d']  = grp['total_precip'].transform(lambda x: x.rolling(7,  min_periods=1).sum())
        df['rolling_precip_14d'] = grp['total_precip'].transform(lambda x: x.rolling(14, min_periods=1).sum())
        df['rolling_precip_30d'] = grp['total_precip'].transform(lambda x: x.rolling(30, min_periods=1).sum())
        df['rolling_humidity']   = grp['humidity'].transform(lambda x: x.rolling(7,  min_periods=1).mean())
        df['rolling_temp']       = grp['avg_temp'].transform(lambda x: x.rolling(7,  min_periods=1).mean())
        df['precip_spike']       = grp['total_precip'].transform(lambda x: x.rolling(3,  min_periods=1).max())
        return df

    def _drought_severity_index(self, df: pd.DataFrame) -> pd.Series:
        """
        Composite Drought Severity Index (0-1) per row.

        Three sub-scores averaged with weights:
          1. Precip deficit  (weight 0.50) — how far below 30-day climatological normal
          2. Temperature     (weight 0.25) — sustained heat above threshold
          3. Humidity        (weight 0.25) — sustained dryness below threshold
        """
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df['month'] = df['date'].dt.month
        df['expected_30d'] = df['month'].map(self.MONTHLY_PRECIP_NORMAL) * 30

        deficit = (df['expected_30d'] - df['rolling_precip_30d']).clip(lower=0)
        precip_score = (deficit / df['expected_30d'].replace(0, 1)).clip(0, 1)

        temp_excess = (df['rolling_temp'] - self.drought_temp_thresh).clip(lower=0)
        temp_score = (temp_excess / 5.0).clip(0, 1)   # 5 C above threshold = score 1

        humidity_deficit = (self.drought_humidity_thresh - df['rolling_humidity']).clip(lower=0)
        humidity_score = (humidity_deficit / 20.0).clip(0, 1)  # 20% below threshold = score 1

        return (precip_score * 0.50 + temp_score * 0.25 + humidity_score * 0.25)

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train_on_history(self, history_csv='history_weather_output.csv'):
        df = pd.read_csv(history_csv)

        required = ['avg_temp', 'max_temp', 'total_precip', 'humidity', 'is_event_day', 'city', 'date']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Training data is missing columns: {missing}")

        df = self._engineer_features(df)

        # Drought thresholds from training data distribution
        self.drought_temp_thresh     = df['avg_temp'].quantile(0.80)
        self.drought_humidity_thresh = df['humidity'].quantile(0.25)

        flood_features = [
            'avg_temp', 'max_temp', 'total_precip', 'humidity',
            'rolling_precip_7d', 'rolling_precip_14d', 'rolling_precip_30d',
            'rolling_humidity', 'rolling_temp', 'precip_spike'
        ]

        X = df[flood_features]
        y = df['is_event_day']

        # Record flood signal thresholds for reporting
        event_rows = df[df['is_event_day'] == 1]
        self.flood_precip_7d = event_rows['rolling_precip_7d'].quantile(0.25)
        self.flood_humidity  = event_rows['rolling_humidity'].quantile(0.25)

        # Class imbalance correction
        counts = y.value_counts()
        scale_pos_weight = counts[0] / counts[1] if 1 in counts else 1.0

        self.flood_model = xgb.XGBClassifier(
            n_estimators=150,
            learning_rate=0.05,
            max_depth=5,
            scale_pos_weight=scale_pos_weight,
            eval_metric='logloss',
            random_state=42
        )

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        self.flood_model.fit(X_train, y_train)
        self.is_trained = True

        y_pred = self.flood_model.predict(X_test)
        print("Flood Model Training Complete.")
        print(f"\nEvaluation (test set - {len(y_test)} samples):")
        print(classification_report(y_test, y_pred, target_names=['No Flood', 'Flood']))
        print("Confusion Matrix:")
        print(confusion_matrix(y_test, y_pred))
        print(f"\nDerived Thresholds:")
        print(f"  Flood  - 7d rolling precip  : >= {self.flood_precip_7d:.1f} mm")
        print(f"  Flood  - rolling humidity    : >= {self.flood_humidity:.1f} %")
        print(f"  Drought - temp threshold     : >  {self.drought_temp_thresh:.1f} C")
        print(f"  Drought - humidity threshold : <  {self.drought_humidity_thresh:.1f} %")

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict_current_risk(self, live_csv='current_weather_check.csv'):
        if not self.is_trained:
            self.train_on_history()

        live_df = pd.read_csv(live_csv)

        required = ['avg_temp', 'max_temp', 'total_precip', 'humidity', 'city', 'date']
        missing = [c for c in required if c not in live_df.columns]
        if missing:
            raise ValueError(f"Live data is missing columns: {missing}")

        live_df = self._engineer_features(live_df)

        flood_features = [
            'avg_temp', 'max_temp', 'total_precip', 'humidity',
            'rolling_precip_7d', 'rolling_precip_14d', 'rolling_precip_30d',
            'rolling_humidity', 'rolling_temp', 'precip_spike'
        ]

        live_df['flood_prob']  = self.flood_model.predict_proba(live_df[flood_features])[:, 1]
        live_df['drought_dsi'] = self._drought_severity_index(live_df)

        def classify_hazard(row):
            """
            Returns only FLOOD or DROUGHT (or SAFE).
            When both signals are elevated the stronger one wins.
            """
            flood_score   = row['flood_prob']
            drought_score = row['drought_dsi']

            if flood_score < 0.4 and drought_score < 0.35:
                return 'SAFE', max(flood_score, drought_score)

            if flood_score >= drought_score:
                return 'FLOOD', flood_score
            else:
                return 'DROUGHT', drought_score

        results = live_df.apply(classify_hazard, axis=1, result_type='expand')
        live_df['hazard_type'] = results[0]
        live_df['risk_score']  = results[1]

        def get_status(row):
            h = row['hazard_type']
            s = row['risk_score']
            if h == 'SAFE':
                return 'SAFE'
            if s > 0.75:
                return f'DANGER: {h}'
            return f'CAUTION: {h}'

        live_df['status'] = live_df.apply(get_status, axis=1)

        # Worst day per city (alert days first)
        alert_rows = live_df[live_df['hazard_type'] != 'SAFE']
        safe_rows  = live_df[live_df['hazard_type'] == 'SAFE']

        regional_report = pd.concat([
            alert_rows.sort_values('risk_score', ascending=False).groupby('city').head(1),
            safe_rows.sort_values('risk_score', ascending=False).groupby('city').head(1)
        ]).sort_values('risk_score', ascending=False)

        return regional_report[[
            'city', 'date', 'status', 'risk_score',
            'rolling_precip_7d', 'drought_dsi', 'avg_temp', 'humidity'
        ]].rename(columns={
            'rolling_precip_7d': '7d_precip_mm',
            'drought_dsi': 'drought_index'
        })


if __name__ == "__main__":
    intel = AgriIntelligence()
    try:
        # 1. Train the Brain
        intel.train_on_history()
        
        # 2. Get the results
        report = intel.predict_current_risk()

        print("\n--- TANZANIA REGIONAL RISK REPORT ---")
        pd.set_option('display.max_rows', 60)
        pd.set_option('display.width', 140)
        print(report.to_string(index=False))
        
        # 3. Save the results to CSV
        today_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"tanzania_risk_report_{today_str}.csv"
        
        # CRITICAL: This line actually writes the file to your folder
        report.to_csv(filename, index=False)
        
        print(f"\n✅ Success! Regional report saved as: {filename}")

    except Exception as e:
        print(f"Error: {e}")
        raise