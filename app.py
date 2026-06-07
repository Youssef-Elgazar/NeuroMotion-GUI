#!/usr/bin/env python3
"""
NeuroMotion web interface with login, dashboard, and demo streaming controls.
"""

from datetime import timedelta
from functools import wraps
import ipaddress
import os
import secrets
import threading
import time

import serial
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

from demo_mode import EEGDemoEngine
from neuro_motion_db import (
    authenticate_user,
    create_demo_session,
    finalize_demo_session,
    get_demo_session,
    get_user_by_id,
    get_user_metrics,
    initialize_database,
)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
    hours=int(os.getenv('SESSION_LIFETIME_HOURS', '8'))
)
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


# SERIAL_PORT = choose_serial_port()
SERIAL_PORT = "COM8"
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

initialize_database()


def login_required_html(view_function):
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('index'))
        return view_function(*args, **kwargs)

    return wrapper


def login_required_api(view_function):
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({'success': False, 'message': 'Login required.'}), 401
        return view_function(*args, **kwargs)

    return wrapper


def get_current_user_context():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return get_user_by_id(user_id)


def build_dashboard_context():
    user = get_current_user_context()
    if not user:
        return None

    metrics = get_user_metrics(user['id'])
    live_state = demo_engine.snapshot()
    active_mode = session.get('selected_mode', 'mental_command_streaming')
    active_session_id = session.get('active_demo_session_id')
    active_session = get_demo_session(active_session_id) if active_session_id else None

    return {
        'user': user,
        'metrics': metrics,
        'live_state': live_state,
        'active_mode': active_mode,
        'active_session': active_session,
        'current_user_name': user['display_name'],
        'selected_mode_label': 'Mental command streaming' if active_mode == 'mental_command_streaming' else 'Eye tracking',
    }


def ensure_active_demo_session(mode='mental_command_streaming'):
    user = get_current_user_context()
    if not user:
        return None

    active_session_id = session.get('active_demo_session_id')
    if active_session_id:
        return active_session_id

    new_session_id = create_demo_session(user['id'], mode=mode)
    session['active_demo_session_id'] = new_session_id
    return new_session_id


def close_active_demo_session(snapshot=None, status='completed'):
    active_session_id = session.pop('active_demo_session_id', None)
    if not active_session_id:
        return None

    finalize_demo_session(active_session_id, snapshot=snapshot or demo_engine.snapshot(), status=status)
    return active_session_id


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
    """Prevent command spoofing by verifying X-Neuro-Auth header.

    Private/local network clients are allowed without the header so the UI
    works on a hotspot or LAN without extra setup.
    """
    if request.path.startswith('/api/'):
        token = request.headers.get('X-Neuro-Auth')
        remote_addr = request.remote_addr

        is_private_client = False
        if remote_addr:
            try:
                address = ipaddress.ip_address(remote_addr)
                is_private_client = address.is_private or address.is_loopback
            except ValueError:
                is_private_client = False

        if token == API_SECURE_TOKEN or is_private_client:
            return

        if not token or token != API_SECURE_TOKEN:
            from flask import abort
            abort(403, description="Unauthorized: Invalid or missing API Secure Token")

@app.route('/')
def index():
    """Serve the login page or redirect authenticated users to the dashboard."""
    if session.get('user_id'):
        return redirect(url_for('dashboard'))

    return render_template(
        'index.html',
        logged_in=False,
        api_token=API_SECURE_TOKEN,
        brand_name='NeuroMotion',
        slogan='Your thoughts, our commands',
        login_error=None,
    )


@app.route('/login', methods=['POST'])
def login():
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    user = authenticate_user(username, password)

    if not user:
        return render_template(
            'index.html',
            logged_in=False,
            api_token=API_SECURE_TOKEN,
            brand_name='NeuroMotion',
            slogan='Your thoughts, our commands',
            login_error='Invalid username or password.',
        ), 401

    session.clear()
    session.permanent = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['display_name'] = user['display_name']
    session['selected_mode'] = 'mental_command_streaming'
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
@login_required_html
def dashboard():
    context = build_dashboard_context()
    if context is None:
        return redirect(url_for('index'))

    return render_template(
        'index.html',
        logged_in=True,
        api_token=API_SECURE_TOKEN,
        brand_name='NeuroMotion',
        slogan='Your thoughts, our commands',
        login_error=None,
        **context,
    )


@app.route('/logout', methods=['POST'])
@login_required_html
def logout():
    close_active_demo_session(status='interrupted')
    session.clear()
    return redirect(url_for('index'))


@app.route('/api/dashboard/overview')
@login_required_api
def dashboard_overview():
    context = build_dashboard_context()
    if context is None:
        return jsonify({'success': False, 'message': 'Login required.'}), 401

    return jsonify({
        'success': True,
        'user': context['user'],
        'metrics': context['metrics'],
        'live_state': context['live_state'],
        'selected_mode': context['active_mode'],
        'selected_mode_label': context['selected_mode_label'],
        'active_session': context['active_session'],
    })


@app.route('/api/dashboard/select-mode', methods=['POST'])
@login_required_api
def dashboard_select_mode():
    data = request.get_json(silent=True) or {}
    mode = data.get('mode')

    if mode == 'mental_command_streaming':
        session['selected_mode'] = mode
        return jsonify({'success': True, 'mode': mode, 'message': 'Mental command streaming selected.'})

    if mode == 'eye_tracking':
        session['selected_mode'] = mode
        return jsonify({'success': True, 'mode': mode, 'message': 'Eye tracking mode will be available soon.'})

    return jsonify({'success': False, 'message': 'Unknown mode selection.'}), 400

@app.route('/api/commands')
@login_required_api
def get_commands():
    """Return list of available commands"""
    return jsonify(list(ROBOT_COMMANDS.keys()))

@app.route('/api/send_command', methods=['POST'])
@login_required_api
def handle_command():
    """Handle command from web interface via AJAX"""
    data = request.get_json()
    command_name = data.get('command')
    force = bool(data.get('force'))
    success, message = send_named_command(command_name, force=force)
    return jsonify({'success': success, 'message': message})


@app.route('/api/demo/state')
@login_required_api
def demo_state():
    """Return latest demo engine state snapshot."""
    return jsonify(demo_engine.snapshot())


@app.route('/api/demo/start', methods=['POST'])
@login_required_api
def demo_start():
    """Start background EEG simulation stream."""
    result = demo_engine.start()
    if result.get('success') or 'Already running' in result.get('message', ''):
        session['selected_mode'] = 'mental_command_streaming'
        ensure_active_demo_session(mode='mental_command_streaming')
    return jsonify(result)


@app.route('/api/demo/stop', methods=['POST'])
@login_required_api
def demo_stop():
    """Stop background EEG simulation stream."""
    result = demo_engine.stop()
    close_active_demo_session(snapshot=demo_engine.snapshot(), status='completed')
    return jsonify(result)


@app.route('/api/demo/transition', methods=['POST'])
@login_required_api
def demo_transition():
    """Schedule transition to another simulated mental command."""
    data = request.get_json() or {}
    next_command = data.get('next_command')
    delay_sec = data.get('delay_sec')
    result = demo_engine.trigger_transition(next_label=next_command, delay_sec=delay_sec)
    return jsonify(result)


@app.route('/api/demo/robot_bridge', methods=['POST'])
@login_required_api
def demo_robot_bridge():
    """Enable or disable robot dispatch from stable demo predictions."""
    data = request.get_json() or {}
    enabled = bool(data.get('enabled'))
    return jsonify(demo_engine.set_robot_bridge(enabled))

@app.route('/api/status')
@login_required_api
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
