"""
One-off build script: converts Translated_Robot_Data.csv into the
.npy / .pkl artifacts expected by EEGDemoEngine (demo_mode.py) and
NeuroMotionFinalController (controller.py).

Run once with: python build_demo_dataset.py
"""
import csv
import os

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from controller import (
    CHANNELS,
    NeuroMotionFinalController,
    extract_channel_meanvar_features,
    extract_lr_diff_meanvar_features,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "Translated_Robot_Data.csv")
SUBJECT_ID = "Subject_01"
DATA_DIR = os.path.join(BASE_DIR, "Hack_Processed_Data", "AI_Ready_Numpy", SUBJECT_ID)
MODELS_DIR = os.path.join(BASE_DIR, "Trained_Models")

# Matches EEGDemoEngine.target_names
LABEL_IDS = {"FORWARD": 1, "BACKWARD": 2, "LEFT": 3, "RIGHT": 4}


def load_directional_epochs():
    epochs_by_id = {}
    epoch_order = []
    with open(CSV_PATH, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            command = row["Command"].strip().upper()
            if command not in LABEL_IDS:
                continue
            epoch_id = row["Epoch"]
            if epoch_id not in epochs_by_id:
                epochs_by_id[epoch_id] = {"label": LABEL_IDS[command], "samples": []}
                epoch_order.append(epoch_id)
            epochs_by_id[epoch_id]["samples"].append([float(row[ch]) for ch in CHANNELS])

    X_data = np.array(
        [np.array(epochs_by_id[e]["samples"], dtype=float).T for e in epoch_order]
    )  # (n_epochs, 14, n_samples)
    y_data = np.array([epochs_by_id[e]["label"] for e in epoch_order], dtype=int)
    return X_data, y_data


def main():
    X_data, y_data = load_directional_epochs()
    print(f"Loaded {X_data.shape[0]} directional epochs, shape {X_data.shape}")

    os.makedirs(DATA_DIR, exist_ok=True)
    np.save(os.path.join(DATA_DIR, f"{SUBJECT_ID}_X.npy"), X_data)
    np.save(os.path.join(DATA_DIR, f"{SUBJECT_ID}_Y.npy"), y_data)
    print(f"Saved {SUBJECT_ID}_X.npy / {SUBJECT_ID}_Y.npy to {DATA_DIR}")

    hor_pipeline = Pipeline([
        ("feat", FunctionTransformer(extract_lr_diff_meanvar_features)),
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000, C=10)),
    ])
    hor_pipeline.fit(X_data, y_data)

    ver_pipeline = Pipeline([
        ("feat", FunctionTransformer(extract_channel_meanvar_features)),
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000, C=10)),
    ])
    ver_pipeline.fit(X_data, y_data)

    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump(hor_pipeline, os.path.join(MODELS_DIR, f"{SUBJECT_ID}_Horizontal.pkl"))
    joblib.dump(ver_pipeline, os.path.join(MODELS_DIR, f"{SUBJECT_ID}_Vertical.pkl"))
    print(f"Saved {SUBJECT_ID}_Horizontal.pkl / {SUBJECT_ID}_Vertical.pkl to {MODELS_DIR}")

    # Sanity-check using the exact same hierarchical logic as get_action()
    controller = NeuroMotionFinalController(MODELS_DIR, SUBJECT_ID, threshold=0.60)
    correct = 0
    for i in range(X_data.shape[0]):
        sample = X_data[i:i + 1]
        action, conf, status = controller.get_action(sample)
        truth = {1: "FORWARD", 2: "BACKWARD", 3: "LEFT", 4: "RIGHT"}[y_data[i]]
        is_correct = action == truth
        correct += int(is_correct)
        print(f"  epoch {i+1:2d}: truth={truth:<9} pred={action:<9} conf={conf:.2f} {'OK' if is_correct else 'X'}")

    print(f"\nLive accuracy on streamed dataset: {correct}/{X_data.shape[0]} ({100*correct/X_data.shape[0]:.1f}%)")


if __name__ == "__main__":
    main()
