import os
import cv2
import json
import math
import numpy as np
import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from l2cs import Pipeline

app = FastAPI(title="L2CS-Net Gaze Estimation Backend")

# Enable CORS so the Flask dashboard on port 5000 can reach this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5000", "http://127.0.0.1:5000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration from environment variables with defaults
THRESHOLD_YAW = float(os.getenv("THRESHOLD_YAW", "15.0"))
THRESHOLD_PITCH = float(os.getenv("THRESHOLD_PITCH", "10.0"))
MODEL_PATH = os.getenv("MODEL_PATH", "models/L2CSNet_gaze360.pkl")
DEVICE = os.getenv("DEVICE", "cuda" if torch.cuda.is_available() else "cpu")

print(f"Initializing L2CS-Net on device: {DEVICE}")
print(f"Model path: {MODEL_PATH}")
print(f"Thresholds: Yaw={THRESHOLD_YAW}°, Pitch={THRESHOLD_PITCH}°")

# Global pipeline instance, loaded on startup
gaze_pipeline = None

@app.on_event("startup")
def startup_event():
    global gaze_pipeline
    # Ensure weights file exists
    if not os.path.exists(MODEL_PATH):
        print(f"WARNING: Model file not found at {MODEL_PATH}. Please run setup.py first.")
        return
    
    try:
        gaze_pipeline = Pipeline(
            weights=MODEL_PATH,
            arch='ResNet50',
            device=torch.device(DEVICE)
        )
        print("✓ L2CS-Net model loaded successfully.")
    except Exception as e:
        print(f"Error loading model: {e}")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "model_loaded": gaze_pipeline is not None,
        "device": DEVICE,
        "thresholds": {"yaw": THRESHOLD_YAW, "pitch": THRESHOLD_PITCH}
    }

def classify_direction(yaw_deg: float, pitch_deg: float) -> str:
    """Classifies yaw and pitch degrees into gaze directions."""
    magnitude_yaw = abs(yaw_deg)
    magnitude_pitch = abs(pitch_deg)

    if magnitude_yaw > magnitude_pitch:
        if yaw_deg < -THRESHOLD_YAW:
            return "LEFT"
        elif yaw_deg > THRESHOLD_YAW:
            return "RIGHT"
        else:
            return "CENTER"
    else:
        if pitch_deg > THRESHOLD_PITCH:
            return "UP"
        elif pitch_deg < -THRESHOLD_PITCH:
            return "DOWN"
        else:
            return "CENTER"

def calculate_confidence(direction: str, yaw_deg: float, pitch_deg: float) -> int:
    """Calculates confidence percentage based on how far into the target zone the gaze is."""
    if direction == "CENTER":
        # Closer to 0,0 is 100% confidence, at the thresholds it is 0%
        ratio_yaw = abs(yaw_deg) / THRESHOLD_YAW
        ratio_pitch = abs(pitch_deg) / THRESHOLD_PITCH
        dist = max(ratio_yaw, ratio_pitch)
        confidence = (1.0 - min(1.0, dist)) * 100
    else:
        # For active directions, confidence increases the further past the threshold the gaze goes
        if direction in ["LEFT", "RIGHT"]:
            val = abs(yaw_deg)
            thresh = THRESHOLD_YAW
        else:
            val = abs(pitch_deg)
            thresh = THRESHOLD_PITCH
        
        # 0% confidence at threshold, ramping up to 100% at 2x threshold
        if val <= thresh:
            confidence = 0
        else:
            confidence = ((val - thresh) / thresh) * 100
            
    return max(0, min(100, int(confidence)))

@app.websocket("/ws/gaze")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connection established.")
    
    if gaze_pipeline is None:
        print("Error: Model was not loaded on startup.")
        await websocket.send_json({
            "error": "Model not initialized",
            "face_detected": False,
            "direction": "CENTER",
            "yaw": 0.0,
            "pitch": 0.0,
            "confidence": 0,
            "bbox": []
        })
        await websocket.close()
        return

    try:
        while True:
            # Receive binary frame from frontend
            data = await websocket.receive_bytes()
            
            # Decode JPEG frame
            nparr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                await websocket.send_json({
                    "face_detected": False,
                    "direction": "CENTER",
                    "yaw": 0.0,
                    "pitch": 0.0,
                    "confidence": 0,
                    "bbox": []
                })
                continue
            
            # Run gaze estimation step
            try:
                results = gaze_pipeline.step(frame)
            except Exception as e:
                print(f"Error during model inference: {e}")
                await websocket.send_json({
                    "face_detected": False,
                    "direction": "CENTER",
                    "yaw": 0.0,
                    "pitch": 0.0,
                    "confidence": 0,
                    "bbox": []
                })
                continue

            # Process outputs if face is detected
            if results.bboxes is not None and len(results.bboxes) > 0:
                # Extract gaze angles for the first detected face (in radians)
                yaw_rad = results.yaw[0]
                pitch_rad = results.pitch[0]
                
                # Convert to degrees
                yaw_deg = float(np.rad2deg(yaw_rad))
                pitch_deg = float(np.rad2deg(pitch_rad))
                
                # Extract bounding box [x1, y1, x2, y2]
                bbox = [int(v) for v in results.bboxes[0]]
                
                # Determine direction
                direction = classify_direction(yaw_deg, pitch_deg)
                
                # Calculate confidence
                confidence = calculate_confidence(direction, yaw_deg, pitch_deg)
                
                response = {
                    "face_detected": True,
                    "direction": direction,
                    "yaw": round(yaw_deg, 2),
                    "pitch": round(pitch_deg, 2),
                    "confidence": confidence,
                    "bbox": bbox
                }
            else:
                response = {
                    "face_detected": False,
                    "direction": "CENTER",
                    "yaw": 0.0,
                    "pitch": 0.0,
                    "confidence": 0,
                    "bbox": []
                }
                
            await websocket.send_json(response)
            
    except WebSocketDisconnect:
        print("WebSocket connection disconnected.")
    except Exception as e:
        print(f"WebSocket error: {e}")

# Static file serving is handled by the Flask app on port 5000.
# This FastAPI server only exposes the /ws/gaze WebSocket endpoint.
print("✓ Eye tracking WebSocket server ready — connect via ws://localhost:8000/ws/gaze")

