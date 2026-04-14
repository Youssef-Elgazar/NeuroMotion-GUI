# Robot Control Web Interface - Setup Guide (Python 3.6)

## EEG Demo Mode (Simulated Input)

The interface now includes a separated **Prediction Model Demo** panel that simulates real-time EEG packets without a headset.

### What it does

- Streams placeholder 14-channel EEG packets.
- Simulates delayed transitions between mental commands.
- Shows live packet values, ground-truth label, predicted label, confidence, and cumulative accuracy.
- Uses stability gating before dispatching predicted commands to the robot.

### Demo controls in the page

- **Start Stream**: starts the EEG simulation.
- **Stop Stream**: stops simulation.
- **Next Command Transition**: schedules a delayed switch to another command.
- **Enable Robot Bridge**: allows stable predicted outputs to trigger robot commands.

### Optional environment variables

- `DEMO_PACKET_INTERVAL_SEC` (default `0.25`)
- `DEMO_SWITCH_DELAY_SEC` (default `2.0`)
- `DEMO_AUTO_SWITCH_EVERY_SEC` (default `6.0`)
- `DEMO_CONFIDENCE_THRESHOLD` (default `80.0`)
- `DEMO_STREAK_REQUIRED` (default `3`)
- `DEMO_BRIDGE_SEND_REAL` (default `0`, set `1` to forward stable predictions to robot serial)

### API endpoints added

- `GET /api/demo/state`
- `POST /api/demo/start`
- `POST /api/demo/stop`
- `POST /api/demo/transition`
- `POST /api/demo/robot_bridge`

## Files Structure

Create the following directory structure:

```
robot_web_control/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
└── templates/
    └── index.html        # Web interface
```

## Requirements File

Create `requirements.txt`:

```
Flask==1.1.4
pyserial==3.5
Werkzeug==1.0.1
MarkupSafe==2.0.1
Jinja2==2.11.3
itsdangerous==1.1.0
click==7.1.2
```

## Installation Steps

### 1. Install Python Dependencies

```bash
# Navigate to your project directory
cd robot_web_control

# Upgrade pip first (important for Python 3.6)
pip3 install --upgrade pip

# Install required packages
pip3 install -r requirements.txt
```

### 2. Setup Files

- Copy the Python code into `app.py`
- Create `templates` folder: `mkdir -p templates`
- Copy the HTML code into `templates/index.html`

### 3. Configure Serial Port

Edit `app.py` if needed to match your serial port:

```python
SERIAL_PORT = '/dev/ttyS1'  # Change if different
BAUD_RATE = 4800
```

### 4. Grant Serial Port Permissions

```bash
# Add your user to dialout group
sudo usermod -a -G dialout $USER

# Then logout and login again, or:
sudo chmod 666 /dev/ttyS1
```

### 5. Run the Application

```bash
python3 app.py
```

You'll see output like:

```
Serial port /dev/ttyS1 opened successfully
============================================================
Robot Control Web Interface
============================================================
Access locally at: http://localhost:5000
Access from network at: http://192.168.1.100:5000
============================================================
 * Running on http://0.0.0.0:5000/ (Press CTRL+C to quit)
```

## Accessing from Other Devices

1. **From the same computer:**
   - Open browser: `http://localhost:5000`

2. **From other devices on the network:**
   - Use the IP address shown: `http://192.168.1.100:5000`
   - Make sure firewall allows port 5000

3. **On mobile devices:**
   - Simply enter the network IP in your mobile browser
   - Interface is responsive and mobile-friendly

## Features

### Web Interface

- ✅ Beautiful, modern UI with gradient design
- ✅ Organized by command categories
- ✅ Quick action buttons for common commands
- ✅ Real-time status updates via AJAX
- ✅ Mobile responsive design
- ✅ Keyboard shortcuts (WASD for movement)
- ✅ Works with Python 3.6+ (no SocketIO needed)

### Keyboard Shortcuts

- `W` - Forward Step
- `S` - Backward Step
- `A` - Turn Left
- `D` - Turn Right
- `Q` - Go Left
- `E` - Go Right
- `Space` - Attention

### Command Categories

1. **Movement** - Walking, running, turning
2. **Attack Moves** - Various punches and kicks
3. **Acrobatics** - Tumbling, flips
4. **Expressions** - Head movements, emotions

## Troubleshooting

### Serial Port Issues

```bash
# Check if device exists
ls -l /dev/ttyS1

# Check permissions
groups $USER

# Test serial port
stty -F /dev/ttyS1 4800
echo "test" > /dev/ttyS1
```

### Python Version Check

```bash
# Verify Python version
python3 --version

# Should show Python 3.6.x or higher
```

### Port Already in Use

```bash
# Find what's using port 5000
sudo lsof -i :5000

# Kill the process if needed
sudo kill -9 <PID>
```

### Cannot Access from Other Devices

1. Find your actual IP address:

   ```bash
   ip addr show
   # or
   hostname -I
   ```

2. Ensure devices are on same network

3. Check firewall:

   ```bash
   # Allow port 5000 (Ubuntu/Debian)
   sudo ufw allow 5000

   # Or temporarily disable
   sudo ufw disable
   ```

### ImportError Issues

If you get import errors, try:

```bash
# Uninstall all and reinstall
pip3 uninstall Flask pyserial Werkzeug MarkupSafe Jinja2 itsdangerous click
pip3 install -r requirements.txt
```

## Running as a Service (Optional)

To run automatically on boot, create a systemd service:

`/etc/systemd/system/robot-control.service`:

```ini
[Unit]
Description=Robot Control Web Interface
After=network.target

[Service]
Type=simple
User=odroid
WorkingDirectory=/home/odroid/robot_web_control
ExecStart=/usr/bin/python3 /home/odroid/robot_web_control/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable robot-control
sudo systemctl start robot-control
sudo systemctl status robot-control
```

View logs:

```bash
sudo journalctl -u robot-control -f
```

## Testing Without Robot

To test the interface without the actual robot connected:

In `app.py`, the code will already handle missing serial gracefully. You'll see:

```
Warning: Could not initialize serial connection
Commands will not be sent to robot
```

The interface will still work and show command feedback.

## Security Notes

⚠️ **Important:** This interface has no authentication. Only use on trusted networks!

For production use, consider adding:

- User authentication (Flask-Login)
- HTTPS/SSL
- Rate limiting
- Command validation
- Access logging

## Quick Test

After starting the server, test with:

```bash
# From another terminal
curl http://localhost:5000/api/status
# Should return: {"serial_connected":true,"serial_port":"/dev/ttyS1"}

curl -X POST http://localhost:5000/api/send_command \
  -H "Content-Type: application/json" \
  -d '{"command":"BOW"}'
# Should return: {"success":true,"message":"Command sent: BOW"}
```

## Common Issues on Odroid

### 1. Serial Port Name

Odroid might use different serial port names:

- `/dev/ttyS1` (most common)
- `/dev/ttySAC1` (Samsung SoC)
- Check with: `ls /dev/tty*`

### 2. Permission Denied

```bash
sudo chmod 666 /dev/ttyS1
# Or add to dialout group permanently:
sudo usermod -a -G dialout odroid
```

### 3. Port 5000 Already Used

Change port in app.py:

```python
app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
```

## Need Help?

- Check Python version: `python3 --version`
- Check pip version: `pip3 --version`
- List installed packages: `pip3 list`
- Test serial manually: `echo "test" > /dev/ttyS1`
