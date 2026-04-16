"""
Live Data Streaming Engine using Pre-processed Neural Models
Reads .npy files and streams exactly as recorded, feeding into the ML Controller.
"""
import os
import threading
import time
import numpy as np
import uuid
import json
from controller import NeuroMotionFinalController
from security import SecureSessionVault

class EEGDemoEngine(object):
    def __init__(self, send_robot_command_callback=None):
        self._lock = threading.Lock()
        self._thread = None
        self._running = False
        self.send_robot_command_callback = send_robot_command_callback
        
        self.packet_interval_sec = float(os.getenv("DEMO_PACKET_INTERVAL_SEC", "3.0")) # Slowed down to 3s per epoch to simulate thought
        self.confidence_threshold = float(os.getenv("DEMO_CONFIDENCE_THRESHOLD", "0.60"))
        self.required_streak = int(os.getenv("DEMO_STREAK_REQUIRED", "2"))
        
        self.vault = SecureSessionVault()
        self.current_session_uuid = None
        self.session_history = []
        
        self.robot_bridge_enabled = False
        
        # Target mapping in notebook: 1:'FORWARD', 2:'BACKWARD', 3:'LEFT', 4:'RIGHT'
        self.target_names = {1: 'FORWARD', 2: 'BACKWARD', 3: 'LEFT', 4: 'RIGHT'}
        self.command_mapping = {
            'FORWARD': 'FWD_SHORT_STEP',
            'BACKWARD': 'BWD_SHORT_STEP',
            'LEFT': 'GO_LEFT',
            'RIGHT': 'GO_RIGHT'
        }
        
        self.base_dir = r"C:\Users\YoussefB\Downloads\Graduation Project PreProcessing layer"
        self.data_dir = os.path.join(self.base_dir, "Hack_Processed_Data", "AI_Ready_Numpy")
        self.models_dir = os.path.join(self.base_dir, "Trained_Models")
        
        # Dynamically load all available subjects
        self.subjects = sorted([d for d in os.listdir(self.data_dir) if d.startswith("Subject_")])
        self.current_subject_idx = 0
        
        self.packet_id = 0
        self.current_test_idx = 0
        
        # State tracking
        self.X_data = None
        self.y_data = None
        self.controller = None
        
        self.channels = ["AF3", "F7", "F3", "FC5", "T7", "P7", "O1", "O2", "P8", "T8", "FC6", "F4", "F8", "AF4"]
        self.current_packet = [0.0] * 14
        
        self.ground_truth_label = "UNKNOWN"
        self.predicted_label = "IDLE/STOP"
        self.confidence = 0.0
        self.is_correct = False
        
        self.total_predictions = 0
        self.correct_predictions = 0
        self.current_streak = 0
        self.last_stable_prediction = None
        
        self.last_dispatch = {
            "sent": False,
            "command": None,
            "message": "No command dispatched yet",
            "timestamp": None
        }
        self._pending_dispatch_command = None
        
        if self.subjects:
            self.load_subject()

    def set_robot_bridge(self, enabled):
        with self._lock:
            self.robot_bridge_enabled = bool(enabled)
            return {"success": True, "enabled": self.robot_bridge_enabled}

    def start(self):
        """Start or resume generated simulation."""
        with self._lock:
            if self._running:
                return {"success": False, "message": "Already running"}
            
            # Initiate secure session
            self.current_session_uuid = str(uuid.uuid4())
            self.session_history = []
            
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            return {"success": True, "message": "Simulation started. Session logged securely."}

    def stop(self):
        """Stop background simulation."""
        with self._lock:
            if not self._running:
                return {"success": False, "message": "Already stopped"}
            self._running = False
            
            # Terminate and encrypt session
            if self.current_session_uuid and self.session_history:
                try:
                    payload = json.dumps(self.session_history)
                    enc_data = self.vault.encrypt_data(payload)
                    output_file = os.path.join(self.vault.output_dir, f"session_{self.current_session_uuid}.enc")
                    with open(output_file, "wb") as f:
                        f.write(enc_data)
                    msg = f"Session {self.current_session_uuid[:8]} encrypted."
                except Exception as e:
                    msg = f"Failed to secure session: {e}"
            else:
                msg = "No session data to encrypt."
                
            return {"success": True, "message": f"Simulation stopped. {msg}"}

    def trigger_transition(self, next_label=None, delay_sec=None):
        return {"success": False, "message": "Flow is controlled by real pre-recorded arrays from models."}
        
    def load_subject(self):
        if not self.subjects:
            return
            
        subject_id = self.subjects[self.current_subject_idx]
        print(f"Loading Models & Data for {subject_id}...")
        try:
            self.controller = NeuroMotionFinalController(self.models_dir, subject_id, threshold=self.confidence_threshold)
            subj_data_dir = os.path.join(self.data_dir, subject_id)
            self.X_data = np.load(os.path.join(subj_data_dir, f"{subject_id}_X.npy"))
            self.y_data = np.load(os.path.join(subj_data_dir, f"{subject_id}_Y.npy"))
            self.current_test_idx = 0
        except Exception as e:
            error_msg = f"Failed to load {subject_id}: {e}"
            print(error_msg)
            self.last_dispatch = {
                "sent": False,
                "command": "LOAD_ERROR",
                "message": error_msg,
                "timestamp": time.time()
            }
            if self.current_subject_idx < len(self.subjects) - 1:
                self.current_subject_idx += 1
                self.load_subject()

    def advance_data(self):
        if not self.subjects:
            return
            
        if self.X_data is None or self.current_test_idx >= len(self.X_data):
            self.current_subject_idx = (self.current_subject_idx + 1) % len(self.subjects)
            self.load_subject()
            if self.X_data is None: 
                return # couldn't load any
                
        # Load a single epoch/trial
        sample = self.X_data[self.current_test_idx : self.current_test_idx + 1]
        y_label_idx = self.y_data[self.current_test_idx]
        self.ground_truth_label = self.target_names.get(y_label_idx, "UNKNOWN")
        
        action, conf, status = self.controller.get_action(sample)
        self.predicted_label = action
        self.confidence = conf
        self.is_correct = (self.predicted_label == self.ground_truth_label)
        
        # Feature vector visualization mean (scale Volts to microVolts for UI display)
        self.current_packet = (sample[0].mean(axis=1) * 1e6).tolist()
        
        # Log to secure record
        if self.current_session_uuid:
            self.session_history.append({
                "timestamp": time.time(),
                "packet_id": self.packet_id,
                "subject": self.subjects[self.current_subject_idx],
                "ground_truth": self.ground_truth_label,
                "prediction": self.predicted_label,
                "confidence": self.confidence,
                "is_correct": self.is_correct
            })
        
        self.total_predictions += 1
        if self.is_correct:
            self.correct_predictions += 1
            
        self.current_test_idx += 1

    def _update_streak(self):
        # We don't count streaks if it's explicitly rejected by threshold
        if self.predicted_label == self.last_stable_prediction and "LOW CONF" not in self.predicted_label:
            self.current_streak += 1
        else:
            self.last_stable_prediction = self.predicted_label
            self.current_streak = 1 if "LOW CONF" not in self.predicted_label else 0

    def _attempt_dispatch(self):
        if not self.robot_bridge_enabled:
            return
            
        if "LOW CONF" in self.predicted_label or self.predicted_label == "UNKNOWN":
            return
            
        if self.current_streak < self.required_streak:
            self.last_dispatch = {
                "sent": False, 
                "command": self.predicted_label, 
                "message": f"Waiting stability ({self.current_streak}/{self.required_streak})", 
                "timestamp": time.time()
            }
            return
            
        if self.send_robot_command_callback is None:
            return
            
        mapped_command = self.command_mapping.get(self.predicted_label)
        if not mapped_command:
            return
            
        self._pending_dispatch_command = mapped_command

    def _tick(self):
        self.packet_id += 1
        self.advance_data()
        self._update_streak()
        self._attempt_dispatch()

    def _run_loop(self):
        while True:
            dispatch_cmd = None
            with self._lock:
                if not self._running:
                    break
                try:
                    self._tick()
                except Exception as e:
                    print(f"Engine Tick Error: {e}")
                    self.last_dispatch = {
                        "sent": False,
                        "command": "ERROR",
                        "message": str(e),
                        "timestamp": time.time()
                    }
                dispatch_cmd = self._pending_dispatch_command
                self._pending_dispatch_command = None
                
            if dispatch_cmd:
                sent = self.send_robot_command_callback(dispatch_cmd)
                with self._lock:
                    self.last_dispatch = {
                        "sent": bool(sent),
                        "command": dispatch_cmd,
                        "message": "Dispatched" if sent else "Failed/Busy",
                        "timestamp": time.time()
                    }
                    
            time.sleep(self.packet_interval_sec)

    def snapshot(self):
        with self._lock:
            acc = 0.0
            if self.total_predictions > 0:
                acc = (float(self.correct_predictions) / float(self.total_predictions)) * 100.0
                
            subj = self.subjects[self.current_subject_idx] if self.subjects else "None"
            
            return {
                "running": self._running,
                "packet_id": self.packet_id,
                "timestamp": time.time(),
                "channels": self.channels,
                "packet": [round(float(p), 4) for p in self.current_packet],
                "ground_truth": self.ground_truth_label,
                "predicted_label": self.predicted_label,
                "mapped_robot_command": self.command_mapping.get(self.predicted_label, "N/A"),
                "confidence": round(self.confidence * 100, 2),
                "is_correct": self.is_correct,
                "accuracy": round(acc, 2),
                "total_predictions": self.total_predictions,
                "correct_predictions": self.correct_predictions,
                "robot_bridge_enabled": self.robot_bridge_enabled,
                "active_subject": subj,
                "streak": self.current_streak,
                "required_streak": self.required_streak,
                "last_dispatch": self.last_dispatch
            }
