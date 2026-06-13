# NeuroMotion Web Interface

## Overview

NeuroMotion is a modern, responsive web control dashboard for humanoid robotic interaction. It features secure database-backed login authentication, live EEG-style command simulation, and real-time gaze-direction tracking using L2CS-Net.

---

## What's Included

- **Secure Login Access**: Fully integrated database authentication system (SQLite) with automatic admin seed (`admin` / `admin`).
- **Dashboard Telemetry & Metrics**: Displays overall session counters, accuracy percentages, and average intent confidence. Includes collapsible panels.
- **Mental Command Streaming**: Simulates real-time neural intent streaming to test command dispatching, bridge latency, and intent success streaks.
- **Real-Time Eye Tracking**: Uses a side-by-side feed of L2CS-Net gaze estimation alongside an interactive robot view, enabling gaze-direction-based robot control.
- **Independent Scrolling Sidebar**: A sticky sidebar that scrolls on its own if the viewport height is restricted.
- **Clean Architecture**: Refactored to separate HTML templates from static assets:
  - Stylesheet is located in `static/css/style.css`
  - JavaScript logic is located in `static/js/app.js`

---

## File Structure

```
Web_Interface/
├── app.py                     # Flask backend server
├── controller.py              # Robot communication bridge
├── demo_mode.py               # EEG packet generation engine
├── neuro_motion_db.py         # Database models and CRUD queries
├── security.py                # Session logging and key management
├── static/                    # External static assets
│   ├── css/
│   │   └── style.css          # Core stylesheet
│   └── js/
│       └── app.js             # Interactive client-side scripts
├── templates/
│   └── index.html             # Clean HTML template shell
└── Robot Illustrations/       # Front, back, left, and right robot JPEGs
```

---

## Running the Interface

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Main Flask Application
```bash
python app.py
```
*The database and encryption keys will automatically initialize on the first run.*

### 3. Run the Eye Tracking Server (Optional)
If utilizing the gaze estimation mode, run the uvicorn service:
```bash
uvicorn EyeTrack_Featrue.main:app --port 8000
```

---

## Environmental Settings

You can customize the runtime behaviour using the following optional variables:
- `FLASK_SECRET_KEY`: Custom Flask cryptographic key for session storage.
- `SESSION_LIFETIME_HOURS`: Cookie expiration limit (defaults to `8`).
- `DEMO_BRIDGE_SEND_REAL`: Set to `1` to forward stable intent predictions to the robot interface.
- `ROBOT_TCP_HOST` & `ROBOT_TCP_PORT`: TCP endpoint configurations for the Socat connection.
