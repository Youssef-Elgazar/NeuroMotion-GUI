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

import socket
# import serial  # [SERIAL] uncomment and replace socket logic to use direct serial instead of Socat TCP
from flask import Flask, abort, jsonify, redirect, render_template, request, session, send_from_directory, url_for
import subprocess
import sys
import atexit

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
ROBOT_ILLUSTRATIONS_DIR = os.path.join(os.path.dirname(__file__), 'Robot Illustrations')

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

# TCP socket configuration for Socat robot bridge
ROBOT_TCP_HOST = os.getenv('ROBOT_TCP_HOST', '10.147.196.185')  # Odroid's hotspot IP
ROBOT_TCP_PORT = int(os.getenv('ROBOT_TCP_PORT', '5000'))
ROBOT_TCP_TIMEOUT = float(os.getenv('ROBOT_TCP_TIMEOUT', '2.0'))
BAUD_RATE = 4800  # kept for status display only
ROBOT_BUSY_SEC = float(os.getenv('ROBOT_BUSY_SEC', '1.5'))
tcp_lock = threading.Lock()
# serial_lock = threading.Lock()  # [SERIAL] was used for pyserial thread safety
last_error_message = None
last_command = None
last_send_time = None
busy_until = 0
serial_setup_done = False
DEMO_BRIDGE_SEND_REAL = '1'
_tcp_connected = False

# [SERIAL] Previous direct serial configuration:
# DEFAULT_PORT_CANDIDATES = (
#     ['COM3', 'COM4'] if os.name == 'nt'
#     else ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyACM0', '/dev/ttyS1']
# )
# def choose_serial_port():
#     env_port = os.getenv('SERIAL_PORT')
#     if env_port:
#         return env_port
#     for candidate in DEFAULT_PORT_CANDIDATES:
#         if os.path.exists(candidate):
#             return candidate
#     return DEFAULT_PORT_CANDIDATES[0]
# SERIAL_PORT = "COM8"
# BAUD_RATE = 4800
# serial_connection = None
# serial_lock = threading.Lock()


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
    print(f"[CALLBACK] called with {command_name}, DEMO_BRIDGE_SEND_REAL={DEMO_BRIDGE_SEND_REAL}")
    if not DEMO_BRIDGE_SEND_REAL:
        return True
    success, msg = send_named_command(command_name, force=False)
    print(f"[CALLBACK] send result: {success}, {msg}")
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


@app.route('/robot-illustrations/<path:filename>')
def robot_illustration(filename):
    return send_from_directory(ROBOT_ILLUSTRATIONS_DIR, filename)


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


# [SERIAL] Previous ensure_serial_open:
# def ensure_serial_open():
#     global serial_connection
#     if serial_connection and serial_connection.is_open:
#         return True
#     return init_serial()

def test_tcp_connection():
    """Test if the Socat TCP bridge is reachable."""
    global _tcp_connected, last_error_message
    try:
        s = socket.create_connection((ROBOT_TCP_HOST, ROBOT_TCP_PORT), timeout=ROBOT_TCP_TIMEOUT)
        s.close()
        _tcp_connected = True
        last_error_message = None
        print("TCP bridge {}:{} reachable".format(ROBOT_TCP_HOST, ROBOT_TCP_PORT))
        return True
    except Exception as e:
        _tcp_connected = False
        last_error_message = str(e)
        print("TCP bridge unreachable: {}".format(e))
        return False

def init_serial():
    """Alias kept for compatibility — tests TCP bridge instead."""
    return test_tcp_connection()

# [SERIAL] Previous serial init:
# def init_serial():
#     global serial_connection, last_error_message
#     try:
#         serial_connection = serial.Serial(
#             port=SERIAL_PORT,
#             baudrate=BAUD_RATE,
#             bytesize=serial.EIGHTBITS,
#             parity=serial.PARITY_NONE,
#             stopbits=serial.STOPBITS_ONE,
#             timeout=1
#         )
#         print("Serial port {} opened successfully".format(SERIAL_PORT))
#         last_error_message = None
#         return True
#     except Exception as e:
#         print("Error opening serial port: {}".format(e))
#         last_error_message = str(e)
#         return False

def send_command(command_code):
    """Send command byte to robot via Socat TCP bridge."""
    print(f"[TCP] Sending {command_code} to {ROBOT_TCP_HOST}:{ROBOT_TCP_PORT}")
    global last_error_message, last_command, last_send_time, busy_until, _tcp_connected
    with tcp_lock:
        try:
            s = socket.create_connection((ROBOT_TCP_HOST, ROBOT_TCP_PORT), timeout=ROBOT_TCP_TIMEOUT)
            s.sendall(bytes([command_code]))
            s.close()
            print("Sent command code: {} to {}:{}".format(command_code, ROBOT_TCP_HOST, ROBOT_TCP_PORT))
            last_command = command_code
            last_send_time = time.time()
            busy_until = last_send_time + ROBOT_BUSY_SEC
            last_error_message = None
            _tcp_connected = True
            return True
        except Exception as e:
            print("TCP send error: {}".format(e))
            last_error_message = str(e)
            _tcp_connected = False
            return False

# [SERIAL] Previous serial send:
# def send_command(command_code):
#     global serial_connection, last_error_message, last_command, last_send_time, busy_until
#     with serial_lock:
#         if not ensure_serial_open():
#             last_error_message = "Serial connection not open"
#             return False
#         try:
#             serial_connection.write(bytes([command_code]))
#             serial_connection.flush()
#             last_command = command_code
#             last_send_time = time.time()
#             busy_until = last_send_time + ROBOT_BUSY_SEC
#             last_error_message = None
#             return True
#         except Exception as e:
#             last_error_message = str(e)
#             return False


# Eye tracking server monitor (keeps uvicorn running)
_eye_proc = None

def _stop_eye_tracking_server():
    global _eye_proc
    try:
        if _eye_proc and _eye_proc.poll() is None:
            print("Stopping eye tracking server...")
            _eye_proc.terminate()
            try:
                _eye_proc.wait(timeout=5)
            except Exception:
                _eye_proc.kill()
    except Exception as e:
        print(f"Error stopping eye tracking server: {e}")

def _start_eye_tracking_monitor():
    """Start and monitor the EyeTrack uvicorn server; restart if it exits."""
    global _eye_proc
    models_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'EyeTrack_Featrue', 'models', 'L2CSNet_gaze360.pkl'))
    env = os.environ.copy()
    env['MODEL_PATH'] = models_path
    cmd = [sys.executable, '-m', 'uvicorn', 'EyeTrack_Featrue.main:app', '--port', '8000']

    def _port_in_use(port, host='127.0.0.1'):
        import socket as _s
        with _s.socket(_s.AF_INET, _s.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
                return False
            except OSError:
                return True

    # If port already in use, assume a server is running and do not start another.
    if _port_in_use(8000):
        print("Port 8000 in use; assuming eye tracking server already running. Monitor exiting.")
        return

    try:
        print(f"Starting Eye tracking server: {cmd} with MODEL_PATH={models_path}")
        _eye_proc = subprocess.Popen(cmd, env=env)
        _eye_proc.wait()
        rc = _eye_proc.returncode
        print(f"Eye tracking server exited with code {rc}")
        _eye_proc = None
    except Exception as e:
        print(f"Error launching eye tracking server: {e}")

# Ensure we stop the child on exit
atexit.register(_stop_eye_tracking_server)


@app.before_request
def setup_serial_once():
    """Test TCP bridge reachability once on first request."""
    global serial_setup_done
    if not serial_setup_done:
        test_tcp_connection()  # [SERIAL] was: ensure_serial_open()
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


@app.route('/api/demo/preset_mode', methods=['POST'])
@login_required_api
def demo_preset_mode():
    """Enable or disable the preset forward/bow demo loop."""
    data = request.get_json() or {}
    enabled = bool(data.get('enabled'))
    return jsonify(demo_engine.set_preset_mode(enabled))

@app.route('/api/status')
@login_required_api
def get_status():
    """Return system status"""
    remaining_ms = int(max(0, (busy_until - time.time()) * 1000))
    return jsonify({
        'tcp_connected': _tcp_connected,
        'robot_host': ROBOT_TCP_HOST,
        'robot_port': ROBOT_TCP_PORT,
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
    print("Robot TCP bridge: {}:{}".format(ROBOT_TCP_HOST, ROBOT_TCP_PORT))
    print("="*60 + "\n")
    
    # Start eye tracking monitor thread so the uvicorn server runs alongside Flask
    monitor_thread = threading.Thread(target=_start_eye_tracking_monitor, daemon=True)
    monitor_thread.start()

    # Run the Flask app
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)