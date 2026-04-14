"""
Demo EEG streaming engine with placeholder signals and mock prediction behavior.
This is intentionally separated from Flask routes to keep logic testable and clean.
"""

import os
import random
import threading
import time


class EEGDemoEngine(object):
    """Simulates 14-channel EEG packets and mock predictions in a background thread."""

    def __init__(self, send_robot_command_callback=None):
        self._lock = threading.Lock()
        self._thread = None
        self._running = False

        self.send_robot_command_callback = send_robot_command_callback

        self.channels = ["CH{:02d}".format(idx) for idx in range(1, 15)]
        self.commands = ["ATTENTION_1", "GO_LEFT", "GO_RIGHT", "BWD_SHORT_STEP"]

        self.packet_interval_sec = float(os.getenv("DEMO_PACKET_INTERVAL_SEC", "0.25"))
        self.switch_delay_sec = float(os.getenv("DEMO_SWITCH_DELAY_SEC", "2.0"))
        self.auto_switch_every_sec = float(os.getenv("DEMO_AUTO_SWITCH_EVERY_SEC", "6.0"))
        self.confidence_threshold = float(os.getenv("DEMO_CONFIDENCE_THRESHOLD", "80.0"))
        self.required_streak = int(os.getenv("DEMO_STREAK_REQUIRED", "3"))

        self.robot_bridge_enabled = False

        self.packet_id = 0
        self.current_label = self.commands[0]
        self.pending_label = None
        self.pending_switch_at = None
        self.next_auto_switch_at = time.time() + self.auto_switch_every_sec

        self.command_bases = self._build_command_bases()

        self.current_packet = self._generate_packet(self.current_label)
        self.predicted_label = self.current_label
        self.confidence = 0.0
        self.is_correct = True

        self.total_predictions = 0
        self.correct_predictions = 0

        self.last_stable_prediction = None
        self.current_streak = 0

        self.last_dispatch = {
            "sent": False,
            "command": None,
            "message": "No command dispatched yet",
            "timestamp": None
        }
        self._pending_dispatch_command = None

    def _build_command_bases(self):
        bases = {}
        for cmd_index, command in enumerate(self.commands):
            start = 12.0 + (cmd_index * 3.0)
            bases[command] = [start + (channel_index * 0.8) for channel_index in range(14)]
        return bases

    def _generate_packet(self, label):
        base = self.command_bases[label]
        packet = []
        drift = random.uniform(-0.45, 0.45)

        for i in range(14):
            noise = random.uniform(-1.8, 1.8)
            value = base[i] + drift + noise
            packet.append(round(value, 3))

        return packet

    def _choose_next_label(self):
        options = [cmd for cmd in self.commands if cmd != self.current_label]
        return random.choice(options)

    def _schedule_transition(self, next_label=None, delay_sec=None):
        if next_label is None:
            next_label = self._choose_next_label()
        if next_label not in self.commands or next_label == self.current_label:
            return False, "Invalid transition command"

        delay = self.switch_delay_sec if delay_sec is None else max(0.1, float(delay_sec))
        self.pending_label = next_label
        self.pending_switch_at = time.time() + delay
        return True, "Transition scheduled to {} in {:.1f}s".format(next_label, delay)

    def trigger_transition(self, next_label=None, delay_sec=None):
        with self._lock:
            ok, message = self._schedule_transition(next_label, delay_sec)
            return {"success": ok, "message": message}

    def set_robot_bridge(self, enabled):
        with self._lock:
            self.robot_bridge_enabled = bool(enabled)
            return {
                "success": True,
                "enabled": self.robot_bridge_enabled,
                "message": "Robot bridge {}".format("enabled" if self.robot_bridge_enabled else "disabled")
            }

    def start(self):
        with self._lock:
            if self._running:
                return {"success": True, "message": "Demo stream already running"}
            self._running = True
            self._thread = threading.Thread(target=self._run_loop)
            self._thread.daemon = True
            self._thread.start()
            return {"success": True, "message": "Demo stream started"}

    def stop(self):
        with self._lock:
            self._running = False
        return {"success": True, "message": "Demo stream stopped"}

    def _simulate_prediction(self):
        if self.pending_label is not None:
            if random.random() < 0.55:
                prediction = self.current_label
            else:
                prediction = self.pending_label
            confidence = random.uniform(52.0, 74.0)
        else:
            if random.random() < 0.9:
                prediction = self.current_label
                confidence = random.uniform(85.0, 97.0)
            else:
                prediction = random.choice([c for c in self.commands if c != self.current_label])
                confidence = random.uniform(50.0, 72.0)

        confidence = round(confidence, 1)
        correct = prediction == self.current_label
        return prediction, confidence, correct

    def _update_streak(self, prediction, confidence):
        if confidence >= self.confidence_threshold and prediction == self.last_stable_prediction:
            self.current_streak += 1
        elif confidence >= self.confidence_threshold:
            self.last_stable_prediction = prediction
            self.current_streak = 1
        else:
            self.current_streak = 0

    def _attempt_dispatch(self):
        if not self.robot_bridge_enabled:
            self.last_dispatch = {
                "sent": False,
                "command": None,
                "message": "Bridge disabled",
                "timestamp": time.time()
            }
            return

        if self.current_streak < self.required_streak:
            self.last_dispatch = {
                "sent": False,
                "command": self.predicted_label,
                "message": "Waiting for stability ({}/{})".format(self.current_streak, self.required_streak),
                "timestamp": time.time()
            }
            return

        if self.send_robot_command_callback is None:
            self.last_dispatch = {
                "sent": False,
                "command": self.predicted_label,
                "message": "No robot callback configured",
                "timestamp": time.time()
            }
            return

        self._pending_dispatch_command = self.predicted_label
        self.last_dispatch = {
            "sent": False,
            "command": self.predicted_label,
            "message": "Dispatch queued",
            "timestamp": time.time()
        }

    def _tick(self):
        now = time.time()

        if self.pending_label and self.pending_switch_at and now >= self.pending_switch_at:
            self.current_label = self.pending_label
            self.pending_label = None
            self.pending_switch_at = None
            self.next_auto_switch_at = now + self.auto_switch_every_sec

        if not self.pending_label and now >= self.next_auto_switch_at:
            self._schedule_transition()

        self.packet_id += 1
        self.current_packet = self._generate_packet(self.current_label)
        self.predicted_label, self.confidence, self.is_correct = self._simulate_prediction()

        self.total_predictions += 1
        if self.is_correct:
            self.correct_predictions += 1

        self._update_streak(self.predicted_label, self.confidence)
        self._attempt_dispatch()

    def _run_loop(self):
        while True:
            dispatch_command = None
            with self._lock:
                if not self._running:
                    break
                self._tick()
                dispatch_command = self._pending_dispatch_command
                self._pending_dispatch_command = None

            if dispatch_command is not None:
                sent = self.send_robot_command_callback(dispatch_command)
                with self._lock:
                    self.last_dispatch = {
                        "sent": bool(sent),
                        "command": dispatch_command,
                        "message": "Dispatched" if sent else "Robot send failed or busy",
                        "timestamp": time.time()
                    }

            time.sleep(self.packet_interval_sec)

    def snapshot(self):
        with self._lock:
            accuracy = 0.0
            if self.total_predictions > 0:
                accuracy = (float(self.correct_predictions) / float(self.total_predictions)) * 100.0

            return {
                "running": self._running,
                "packet_id": self.packet_id,
                "timestamp": time.time(),
                "channels": self.channels,
                "packet": self.current_packet,
                "ground_truth": self.current_label,
                "pending_label": self.pending_label,
                "pending_switch_at": self.pending_switch_at,
                "predicted_label": self.predicted_label,
                "confidence": self.confidence,
                "is_correct": self.is_correct,
                "accuracy": round(accuracy, 2),
                "total_predictions": self.total_predictions,
                "correct_predictions": self.correct_predictions,
                "packet_interval_sec": self.packet_interval_sec,
                "switch_delay_sec": self.switch_delay_sec,
                "auto_switch_every_sec": self.auto_switch_every_sec,
                "confidence_threshold": self.confidence_threshold,
                "required_streak": self.required_streak,
                "streak": self.current_streak,
                "robot_bridge_enabled": self.robot_bridge_enabled,
                "last_dispatch": self.last_dispatch
            }
