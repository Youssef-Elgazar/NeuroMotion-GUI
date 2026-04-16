#!/usr/bin/env python3
"""
Robot Control Web Interface - Python 3.6 Compatible
Provides a web-based GUI to control the HanBack RobonovaAI robot
"""

from flask import Flask, render_template, jsonify, request
import threading
import time
import serial
import json
import os
import secrets
from demo_mode import EEGDemoEngine

app = Flask(__name__)
API_SECURE_TOKEN = secrets.token_urlsafe(32)

# Robot command mappings (from robot_protocol.h)
ROBOT_COMMANDS = {
    'BOW': 1,
    'SIT_DOWN': 26,
    'RIGHT_SHOOTING': 2,
    'LEFT_SHOOTING': 6,
    'FWD_SHORT_STEP': 11,
    'BWD_SHORT_STEP': 12,
    'FWD_RUN': 5,
    'BWD_RUN': 10,
    'LEFT_TURN': 7,
    'RIGHT_TURN': 9,
    'GO_LEFT': 14,
    'GO_RIGHT': 13,
    'LEFT_FRONT_SIDE_ATTACK': 17,
    'RIGHT_FRONT_SIDE_ATTACK': 27,
    'LOSER1': 3,
    'LOSER2': 4,
    'LEFT_SIDE_ATTACK': 18,
    'RIGHT_SIDE_ATTACK': 23,
    'HEAD_LEFT': 15,
    'HEAD_RIGHT': 20,
    'FLAPPING_AND_STANDUP': 28,
    'MARK_TIME': 30,
    'BACK_LIFT_ATTACK': 31,
    'ATTENTION_1': 29,
    'TUMBLING_FORWARD': 25,
    'TUMBLING_BACKWARD': 19,
    'LEFT_BACK_ATTACK': 22,
    'RIGHT_BACK_ATTACK': 24,
    'FRONT_BOTH_SIDE_PUNCH': 32,
    'MOTION_CAPTURE': 16,
    'CEREMONY': 8,
    'FRONT_LIFT_ATTACK': 21
}

# Serial port configuration (override with SERIAL_PORT env if needed)
DEFAULT_PORT_CANDIDATES = (
    ['COM3', 'COM4'] if os.name == 'nt'
    else ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyACM0', '/dev/ttyS1']
)


def choose_serial_port():
    """Pick serial port from env or first existing candidate."""
    env_port = os.getenv('SERIAL_PORT')
    if env_port:
        return env_port
    for candidate in DEFAULT_PORT_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return DEFAULT_PORT_CANDIDATES[0]


SERIAL_PORT = choose_serial_port()
BAUD_RATE = 4800
ROBOT_BUSY_SEC = float(os.getenv('ROBOT_BUSY_SEC', '1.5'))
serial_connection = None
serial_lock = threading.Lock()
last_error_message = None
last_command = None
last_send_time = None
busy_until = 0
serial_setup_done = False
DEMO_BRIDGE_SEND_REAL = os.getenv('DEMO_BRIDGE_SEND_REAL', '0') == '1'


def send_named_command(command_name, force=False):
    """Send robot command by name and respect busy window unless forced."""
    now = time.time()
    if command_name not in ROBOT_COMMANDS:
        return False, 'Unknown command: {}'.format(command_name)

    if not force and now < busy_until:
        remaining_ms = int((busy_until - now) * 1000)
        return False, 'Robot busy, wait {} ms'.format(max(0, remaining_ms))

    command_code = ROBOT_COMMANDS[command_name]
    if send_command(command_code):
        return True, 'Command sent: {}'.format(command_name)
    return False, 'Failed to send command: {}'.format(command_name)


def _demo_robot_callback(command_name):
    """Callback used by demo engine to dispatch stable predictions."""
    if not DEMO_BRIDGE_SEND_REAL:
        return True
    success, _ = send_named_command(command_name, force=False)
    return success


demo_engine = EEGDemoEngine(send_robot_command_callback=_demo_robot_callback)


def ensure_serial_open():
    """Make sure the serial port is open; attempt to re-init if not."""
    global serial_connection
    if serial_connection and serial_connection.is_open:
        return True
    return init_serial()

def init_serial():
    """Initialize serial connection to robot"""
    global serial_connection
    global last_error_message
    try:
        serial_connection = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1
        )
        print("Serial port {} opened successfully".format(SERIAL_PORT))
        last_error_message = None
        return True
    except Exception as e:
        print("Error opening serial port: {}".format(e))
        last_error_message = str(e)
        return False

def send_command(command_code):
    """Send command byte to robot via serial"""
    global serial_connection
    global last_error_message
    global last_command
    global last_send_time
    global busy_until
    with serial_lock:
        if not ensure_serial_open():
            print("Serial connection not open")
            last_error_message = "Serial connection not open"
            return False
        try:
            serial_connection.write(bytes([command_code]))
            serial_connection.flush()
            print("Sent command code: {}".format(command_code))
            last_command = command_code
            last_send_time = time.time()
            busy_until = last_send_time + ROBOT_BUSY_SEC
            last_error_message = None
            return True
        except Exception as e:
            print("Error sending command: {}".format(e))
            last_error_message = str(e)
            return False


@app.before_request
def setup_serial_once():
    """Initialize serial port once in a Flask-version-compatible way."""
    global serial_setup_done
    if not serial_setup_done:
        ensure_serial_open()
        serial_setup_done = True

@app.before_request
def verify_api_token():
    """Prevent command spoofing by verifying X-Neuro-Auth header."""
    if request.path.startswith('/api/'):
        token = request.headers.get('X-Neuro-Auth')
        if not token or token != API_SECURE_TOKEN:
            from flask import abort
            abort(403, description="Unauthorized: Invalid or missing API Secure Token")

@app.route('/')
def index():
    """Serve the main web interface"""
    return render_template('index.html', api_token=API_SECURE_TOKEN)

@app.route('/api/commands')
def get_commands():
    """Return list of available commands"""
    return jsonify(list(ROBOT_COMMANDS.keys()))

@app.route('/api/send_command', methods=['POST'])
def handle_command():
    """Handle command from web interface via AJAX"""
    data = request.get_json()
    command_name = data.get('command')
    force = bool(data.get('force'))
    success, message = send_named_command(command_name, force=force)
    return jsonify({'success': success, 'message': message})


@app.route('/api/demo/state')
def demo_state():
    """Return latest demo engine state snapshot."""
    return jsonify(demo_engine.snapshot())


@app.route('/api/demo/start', methods=['POST'])
def demo_start():
    """Start background EEG simulation stream."""
    return jsonify(demo_engine.start())


@app.route('/api/demo/stop', methods=['POST'])
def demo_stop():
    """Stop background EEG simulation stream."""
    return jsonify(demo_engine.stop())


@app.route('/api/demo/transition', methods=['POST'])
def demo_transition():
    """Schedule transition to another simulated mental command."""
    data = request.get_json() or {}
    next_command = data.get('next_command')
    delay_sec = data.get('delay_sec')
    result = demo_engine.trigger_transition(next_label=next_command, delay_sec=delay_sec)
    return jsonify(result)


@app.route('/api/demo/robot_bridge', methods=['POST'])
def demo_robot_bridge():
    """Enable or disable robot dispatch from stable demo predictions."""
    data = request.get_json() or {}
    enabled = bool(data.get('enabled'))
    return jsonify(demo_engine.set_robot_bridge(enabled))

@app.route('/api/status')
def get_status():
    """Return system status"""
    remaining_ms = int(max(0, (busy_until - time.time()) * 1000))
    return jsonify({
        'serial_connected': serial_connection is not None and serial_connection.is_open,
        'serial_port': SERIAL_PORT,
        'baud_rate': BAUD_RATE,
        'last_error': last_error_message,
        'last_command': last_command,
        'last_send_time': last_send_time,
        'busy_until': busy_until,
        'busy_for_ms': remaining_ms
    })

if __name__ == '__main__':
    # Initialize serial connection
    if not init_serial():
        print("Warning: Could not initialize serial connection")
        print("Commands will not be sent to robot")
    
    # Get local IP address
    import socket
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except:
        local_ip = "Unable to determine"
    
    print("\n" + "="*60)
    print("Robot Control Web Interface")
    print("="*60)
    print("Access locally at: http://localhost:5000")
    print("Access from network at: http://{}:5000".format(local_ip))
    print("="*60 + "\n")
    
    # Run the Flask app
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    finally:
        if serial_connection and serial_connection.is_open:
            serial_connection.close()
            print("Serial connection closed")
