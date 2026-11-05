import os
import numpy as np
import joblib

# Channel order matches EEGDemoEngine.channels / Translated_Robot_Data.csv columns
CHANNELS = ["AF3", "F7", "F3", "FC5", "T7", "P7", "O1", "O2", "P8", "T8", "FC6", "F4", "F8", "AF4"]

# Index pairs for matching left/right hemisphere electrodes (AF3<->AF4, F7<->F8, ...)
_LEFT_HEMISPHERE_IDX = [0, 1, 2, 3, 4, 5, 6]
_RIGHT_HEMISPHERE_IDX = [13, 12, 11, 10, 9, 8, 7]


def extract_lr_diff_meanvar_features(X):
    """X: (n, 14, samples) -> (n, 14) left-minus-right hemisphere mean/variance differences.

    Used by the "Horizontal" model, which specializes in LEFT/RIGHT discrimination.
    """
    X = np.asarray(X)
    mean, var = X.mean(axis=2), X.var(axis=2)
    return np.concatenate([
        mean[:, _LEFT_HEMISPHERE_IDX] - mean[:, _RIGHT_HEMISPHERE_IDX],
        var[:, _LEFT_HEMISPHERE_IDX] - var[:, _RIGHT_HEMISPHERE_IDX],
    ], axis=1)


def extract_channel_meanvar_features(X):
    """X: (n, 14, samples) -> (n, 28) per-channel mean and variance.

    Used by the "Vertical" model, which specializes in FORWARD/BACKWARD discrimination.
    """
    X = np.asarray(X)
    return np.concatenate([X.mean(axis=2), X.var(axis=2)], axis=1)


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
