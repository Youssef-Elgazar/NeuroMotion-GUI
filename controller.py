import os
import numpy as np
import joblib

class NeuroMotionFinalController:
    def __init__(self, models_dir, subject_id, threshold=0.60):
        self.threshold = threshold
        self.subject_id = subject_id
        
        # Loading specialized models
        hor_path = os.path.join(models_dir, f"{subject_id}_Horizontal.pkl")
        ver_path = os.path.join(models_dir, f"{subject_id}_Vertical.pkl")
        
        if not os.path.exists(hor_path) or not os.path.exists(ver_path):
            raise FileNotFoundError(f"Models not found for {subject_id} in {models_dir}")
            
        self.model_hor = joblib.load(hor_path)
        self.model_ver = joblib.load(ver_path)
        
        self.target_names = {1: 'FORWARD', 2: 'BACKWARD', 3: 'LEFT', 4: 'RIGHT'}

    def get_action(self, live_data_buffer):
        """
        Logic: Smart Hierarchical Prediction with Confidence Threshold
        Expects a 3D numpy array segment: shape (1, channels, samples) e.g. (1, 14, 193)
        """
        probs_hor = self.model_hor.predict_proba(live_data_buffer)[0]
        probs_ver = self.model_ver.predict_proba(live_data_buffer)[0]
        
        max_hor = np.max(probs_hor)
        max_ver = np.max(probs_ver)
        
        if max_hor > max_ver:
            best_conf = max_hor
            prediction = self.model_hor.predict(live_data_buffer)[0]
        else:
            best_conf = max_ver
            prediction = self.model_ver.predict(live_data_buffer)[0]
            
        action = self.target_names.get(prediction, "UNKNOWN")
        
        if best_conf >= self.threshold:
            return action, float(best_conf), "✅ EXECUTING"
        else:
            # Tell the interface exactly what happened
            return f"BLOCKED (LOW CONF)", float(best_conf), "⚠️ REJECTED"
