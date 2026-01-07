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

app = Flask(__name__)

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

# Serial port configuration
SERIAL_PORT = '/dev/ttyS1'
BAUD_RATE = 4800
serial_connection = None
serial_lock = threading.Lock()

def init_serial():
    """Initialize serial connection to robot"""
    global serial_connection
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
        return True
    except Exception as e:
        print("Error opening serial port: {}".format(e))
        return False

def send_command(command_code):
    """Send command byte to robot via serial"""
    global serial_connection
    with serial_lock:
        try:
            if serial_connection and serial_connection.is_open:
                serial_connection.write(bytes([command_code]))
                print("Sent command code: {}".format(command_code))
                return True
            else:
                print("Serial connection not open")
                return False
        except Exception as e:
            print("Error sending command: {}".format(e))
            return False

@app.route('/')
def index():
    """Serve the main web interface"""
    return render_template('index.html')

@app.route('/api/commands')
def get_commands():
    """Return list of available commands"""
    return jsonify(list(ROBOT_COMMANDS.keys()))

@app.route('/api/send_command', methods=['POST'])
def handle_command():
    """Handle command from web interface via AJAX"""
    data = request.get_json()
    command_name = data.get('command')
    
    if command_name not in ROBOT_COMMANDS:
        return jsonify({
            'success': False,
            'message': 'Unknown command: {}'.format(command_name)
        })
    
    command_code = ROBOT_COMMANDS[command_name]
    
    if send_command(command_code):
        return jsonify({
            'success': True,
            'message': 'Command sent: {}'.format(command_name)
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to send command: {}'.format(command_name)
        })

@app.route('/api/status')
def get_status():
    """Return system status"""
    return jsonify({
        'serial_connected': serial_connection is not None and serial_connection.is_open,
        'serial_port': SERIAL_PORT
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
