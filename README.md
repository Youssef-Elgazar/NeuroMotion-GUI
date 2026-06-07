# NeuroMotion Web Interface

## Overview

The application now opens with a database-backed login page and, after authentication, redirects to a cleaner dashboard for the NeuroMotion experience.

### What it includes

- A seeded SQLite-backed admin account created automatically on first launch.
- Login credentials for the default admin user: `admin` / `admin`.
- A polished dashboard with mental command streaming, eye tracking placeholder mode, live telemetry, and session history.
- Persistent demo-session metrics stored in the local database.

### Demo controls in the page

- **Start streaming**: starts the EEG-style demo stream.
- **Stop streaming**: stops the demo stream.
- **Activate demo**: selects the mental command mode and starts the stream.
- **Eye tracking mode**: shown as the next implementation target.

### Optional environment variables

- `FLASK_SECRET_KEY` (recommended for persistent sessions)
- `SESSION_LIFETIME_HOURS` (default `8`)
- `SERIAL_PORT` if you want to override the robot connection in code later
- `DEMO_PACKET_INTERVAL_SEC` (default `3.0`)
- `DEMO_CONFIDENCE_THRESHOLD` (default `0.60`)
- `DEMO_STREAK_REQUIRED` (default `2`)
- `DEMO_BRIDGE_SEND_REAL` (default `0`, set `1` to forward stable predictions to robot serial)

### API endpoints added

- `GET /api/demo/state`
- `POST /api/demo/start`
- `POST /api/demo/stop`
- `POST /api/demo/transition`
- `POST /api/demo/robot_bridge`

## Run It

```bash
pip install -r requirements.txt
python app.py
```

The first run creates `instance/neuro_motion.db` and seeds the admin user automatically.

## Files Structure

The current project layout is:

```
Web_Interface/
├── app.py
├── controller.py
├── demo_mode.py
├── neuro_motion_db.py
├── security.py
└── templates/
   └── index.html
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
