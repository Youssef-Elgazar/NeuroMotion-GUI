const API_TOKEN = document.querySelector('meta[name="api-token"]').content;
const appShell = document.getElementById('app-shell');
const bootDataNode = document.getElementById('boot-data');
const boot = JSON.parse((bootDataNode && bootDataNode.textContent) || '{}');
boot.urls = appShell ? appShell.dataset : {};

function apiFetch(url, options = {}) {
    const headers = Object.assign({}, options.headers || {}, {
        'Content-Type': 'application/json',
        'X-Neuro-Auth': API_TOKEN,
    });

    return fetch(url, Object.assign({}, options, {
        headers,
        credentials: 'same-origin',
    }));
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function formatPercent(value) {
    const number = Number(value || 0);
    return `${number.toFixed(2)}%`;
}

function formatMode(mode) {
    if (mode === 'mental_command_streaming') {
        return 'Mental command streaming';
    }
    if (mode === 'eye_tracking') {
        return 'Eye tracking';
    }
    return mode || 'N/A';
}

function updateModeCards(mode) {
    document.querySelectorAll('[data-mode-card]').forEach((card) => {
        card.classList.toggle('active', card.dataset.modeCard === mode);
    });

    const currentModeLabel = document.getElementById('current-mode-label');
    if (currentModeLabel) {
        currentModeLabel.textContent = formatMode(mode);
    }
}

function renderSessions(rows) {
    const body = document.getElementById('session-history-body');
    if (!body) {
        return;
    }

    if (!rows || !rows.length) {
        body.innerHTML = '<tr><td colspan="4"><div class="empty-state">No demo sessions recorded yet. Start the mental command stream to populate history.</div></td></tr>';
        return;
    }

    body.innerHTML = rows.map((row) => {
        return `<tr>
            <td>${escapeHtml(row.started_at || 'N/A')}</td>
            <td>${escapeHtml(formatMode(row.mode))}</td>
            <td>${escapeHtml(row.status || 'unknown')}</td>
            <td>${formatPercent(row.accuracy)}</td>
        </tr>`;
    }).join('');
}

function updateLiveState(state) {
    const live = state || {};
    boot.liveState = live;
    const map = [
        ['active-subject', live.active_subject || 'N/A'],
        ['stream-accuracy', formatPercent(live.accuracy)],
        ['predicted-command', live.predicted_label || 'IDLE'],
        ['prediction-confidence', formatPercent(live.confidence)],
        ['streak', `${live.streak || 0}/${live.required_streak || 0}`],
        ['ground-truth', live.ground_truth || '---'],
    ];

    map.forEach(([id, value]) => {
        const node = document.getElementById(id);
        if (node) {
            node.textContent = value;
        }
    });

    const streamStatus = document.getElementById('stream-status-pill');
    if (streamStatus) {
        streamStatus.textContent = live.running ? 'Streaming' : 'Idle';
        streamStatus.className = `status-pill ${live.running ? 'status-success' : 'status-muted'}`;
    }

    const bridgePill = document.getElementById('bridge-state-pill');
    if (bridgePill) {
        bridgePill.textContent = live.robot_bridge_enabled ? 'Bridge enabled' : 'Bridge idle';
        bridgePill.className = `status-pill ${live.robot_bridge_enabled ? 'status-success' : 'status-ghost'}`;
    }

    const note = document.getElementById('stream-note');
    if (note) {
        const dispatch = live.last_dispatch || {};
        note.textContent = dispatch.message || 'Demo telemetry ready.';
    }

    const bridgeButton = document.getElementById('bridge-toggle');
    if (bridgeButton) {
        bridgeButton.textContent = live.robot_bridge_enabled ? 'Disable robot bridge' : 'Enable robot bridge';
    }

    const bridgeButtonSidebar = document.getElementById('bridge-toggle-sidebar');
    if (bridgeButtonSidebar) {
        bridgeButtonSidebar.textContent = live.robot_bridge_enabled ? 'Disable robot bridge' : 'Enable robot bridge';
    }

    // ── Robot art viewer ──────────────────────────────────────
    const dispatch = live.last_dispatch || {};
    const rawCmd = String(dispatch.command || live.mapped_robot_command || live.predicted_label || '').toUpperCase();
    _updateRobotViewer(rawCmd, live.running);
}

/* Map a command string to one of four robot views. */
const _CMD_VIEW_MAP = {
    // Forward / front
    FWD_SHORT_STEP: 'front',
    FWD_RUN: 'front',
    FORWARD: 'front',
    FORWARD_STEP: 'front',
    WALK_FORWARD: 'front',
    RUN_FORWARD: 'front',
    BOW: 'front',
    ATTENTION: 'front',
    ATTENTION_1: 'front',
    IDLE: 'front',
    NEUTRAL: 'front',
    // Backward / back
    BWD_SHORT_STEP: 'back',
    BWD_RUN: 'back',
    BACKWARD: 'back',
    BACKWARD_STEP: 'back',
    WALK_BACKWARD: 'back',
    RUN_BACKWARD: 'back',
    BACK: 'back',
    TUMBLING_BACKWARD: 'back',
    // Left
    LEFT_TURN: 'left',
    GO_LEFT: 'left',
    LEFT: 'left',
    TURN_LEFT: 'left',
    STRAFE_LEFT: 'left',
    STEP_LEFT: 'left',
    LEFT_FRONT_SIDE_ATTACK: 'left',
    LEFT_SIDE_ATTACK: 'left',
    LEFT_BACK_ATTACK: 'left',
    HEAD_LEFT: 'left',
    // Right
    RIGHT_TURN: 'right',
    GO_RIGHT: 'right',
    RIGHT: 'right',
    TURN_RIGHT: 'right',
    STRAFE_RIGHT: 'right',
    STEP_RIGHT: 'right',
    RIGHT_FRONT_SIDE_ATTACK: 'right',
    RIGHT_SIDE_ATTACK: 'right',
    RIGHT_BACK_ATTACK: 'right',
    HEAD_RIGHT: 'right',
};

const _VIEW_LABEL = { front: 'Front', back: 'Back', left: 'Left', right: 'Right' };
let _currentRobotView = 'front';

function _resolveView(cmd) {
    if (!cmd) return 'front';
    // Direct lookup
    if (_CMD_VIEW_MAP[cmd]) return _CMD_VIEW_MAP[cmd];
    // Partial-match fallback — check if any key is contained in cmd
    for (const [key, view] of Object.entries(_CMD_VIEW_MAP)) {
        if (cmd.includes(key)) return view;
    }
    // Keyword heuristics
    if (cmd.includes('LEFT'))  return 'left';
    if (cmd.includes('RIGHT')) return 'right';
    if (cmd.includes('BACK'))  return 'back';
    return 'front';
}

function _updateRobotViewer(cmd, running) {
    const view = _resolveView(cmd);

    // Only animate when the view actually changes
    if (view !== _currentRobotView) {
        _currentRobotView = view;

        const ids = { front: 'robot-img-front', back: 'robot-img-back', left: 'robot-img-left', right: 'robot-img-right' };
        Object.entries(ids).forEach(([v, id]) => {
            const el = document.getElementById(id);
            if (el) el.classList.toggle('robot-img-active', v === view);
        });

        const eyeIds = { front: 'eye-robot-img-front', back: 'eye-robot-img-back', left: 'eye-robot-img-left', right: 'eye-robot-img-right' };
        Object.entries(eyeIds).forEach(([v, id]) => {
            const el = document.getElementById(id);
            if (el) el.classList.toggle('robot-img-active', v === view);
        });

        const chip = document.getElementById('robot-view-chip');
        if (chip) chip.textContent = _VIEW_LABEL[view] || 'Front';

        const eyeChip = document.getElementById('eye-robot-view-chip');
        if (eyeChip) eyeChip.textContent = _VIEW_LABEL[view] || 'Front';
    }

    // Badge: show command label and active dot when streaming
    const badge     = document.getElementById('robot-badge');
    const badgeLbl  = document.getElementById('robot-badge-label');
    if (badge)    badge.classList.toggle('active', !!running && !!cmd && cmd !== 'IDLE');
    if (badgeLbl) badgeLbl.textContent = (running && cmd) ? cmd : 'Idle';

    const eyeBadge     = document.getElementById('eye-robot-badge');
    const eyeBadgeLbl  = document.getElementById('eye-robot-badge-label');
    if (eyeBadge)    eyeBadge.classList.toggle('active', !!_eyeRunning && !!cmd && cmd !== 'IDLE');
    if (eyeBadgeLbl) eyeBadgeLbl.textContent = (_eyeRunning && cmd) ? cmd : 'Idle';
}

function updateMetrics(metrics) {
    if (!metrics) {
        return;
    }

    boot.metrics = metrics;

    const updates = {
        'metric-total-sessions': metrics.total_sessions,
        'metric-average-accuracy': formatPercent(metrics.average_accuracy),
        'metric-average-confidence': formatPercent(metrics.average_confidence),
        'metric-total-packets': metrics.total_packets,
        'last-mode': formatMode(metrics.last_mode),
        'recent-session-count': (metrics.recent_sessions || []).length,
        'history-count-pill': `${metrics.completed_sessions || 0} completed`,
    };

    // mirror some values into the image-led hero small cards
    const smallUpdates = {
        'metric-total-sessions_small': metrics.total_sessions,
        'metric-average-accuracy_small': formatPercent(metrics.average_accuracy),
        'active-subject_small': boot.liveState.active_subject || 'N/A',
        'bridge-state-small': boot.liveState.robot_bridge_enabled ? 'Enabled' : 'Idle',
    };

    Object.entries(updates).forEach(([id, value]) => {
        const node = document.getElementById(id);
        if (node) {
            node.textContent = value;
        }
    });

    Object.entries(smallUpdates).forEach(([id, value]) => {
        const node = document.getElementById(id);
        if (node) {
            node.textContent = value;
        }
    });

    renderSessions(metrics.recent_sessions || []);
}

async function refreshOverview() {
    const response = await apiFetch(boot.urls.dashboardOverviewUrl, { method: 'GET' });
    const payload = await response.json();

    if (!response.ok || !payload.success) {
        return;
    }

    updateModeCards(payload.selected_mode);
    updateMetrics(payload.metrics);
    updateLiveState(payload.live_state);
}

// Renders the correct controls in the sidebar dynamically depending on the current mode
function renderSidebarControls(mode) {
    const container = document.getElementById('sidebar-mode-controls');
    if (!container) return;

    if (mode === 'mental_command_streaming') {
        container.innerHTML = `
            <div class="section-title">Streaming Controls</div>
            <div class="control-stack">
                <button class="btn btn-primary" type="button" onclick="startDemo()">Start streaming</button>
                <button class="btn btn-danger" type="button" onclick="stopDemo()">Stop streaming</button>
                <button class="btn btn-secondary" type="button" id="bridge-toggle-sidebar" onclick="toggleBridge()">
                    ${boot.liveState && boot.liveState.robot_bridge_enabled ? 'Disable robot bridge' : 'Enable robot bridge'}
                </button>
            </div>
            <div style="height: 18px;"></div>
        `;
    } else if (mode === 'eye_tracking') {
        container.innerHTML = `
            <div class="section-title">Eye Tracking Controls</div>
            <div class="control-stack">
                <button class="btn btn-primary" id="eye-start-btn-sidebar" type="button" onclick="startEyeTracking()">Start tracking</button>
                <button class="btn btn-danger"  id="eye-stop-btn-sidebar"  type="button" onclick="stopEyeTracking()" disabled>Stop tracking</button>
                <button class="btn btn-secondary" type="button" id="bridge-toggle-sidebar" onclick="toggleBridge()">
                    ${boot.liveState && boot.liveState.robot_bridge_enabled ? 'Disable robot bridge' : 'Enable robot bridge'}
                </button>
            </div>
            <div style="height: 18px;"></div>
        `;
    } else {
        container.innerHTML = '';
    }
}

async function activateMode(mode) {
    const response = await apiFetch(boot.urls.dashboardSelectModeUrl, {
        method: 'POST',
        body: JSON.stringify({ mode }),
    });

    const payload = await response.json();
    if (payload.success) {
        updateModeCards(mode);
        renderSidebarControls(mode);
        const note = document.getElementById('sidebar-session-message');
        if (note) {
            note.textContent = payload.message || 'Mode updated.';
        }

        // Toggle panel visibility
        const mentalPanel = document.getElementById('mental-stream-panel');
        const eyePanel    = document.getElementById('eye-tracking-panel');
        const heroPanel   = document.querySelector('.hero');

        if (mode === 'mental_command_streaming') {
            if (heroPanel) heroPanel.style.display = '';
            if (mentalPanel) mentalPanel.style.display = '';
            if (eyePanel)    eyePanel.classList.remove('visible');
            stopEyeTracking();
            await startDemo();
        }

        if (mode === 'eye_tracking') {
            if (heroPanel) heroPanel.style.display = 'none';
            if (mentalPanel) mentalPanel.style.display = 'none';
            if (eyePanel)    eyePanel.classList.add('visible');
            await refreshOverview();
        }
    }
}

async function startDemo() {
    await apiFetch(boot.urls.dashboardSelectModeUrl, {
        method: 'POST',
        body: JSON.stringify({ mode: 'mental_command_streaming' }),
    });

    const response = await apiFetch(boot.urls.demoStartUrl, { method: 'POST', body: '{}' });
    const payload = await response.json();
    const note = document.getElementById('sidebar-session-message');

    if (note) {
        note.textContent = payload.message || 'Demo stream started.';
    }

    await refreshOverview();
}

async function stopDemo() {
    const response = await apiFetch(boot.urls.demoStopUrl, { method: 'POST', body: '{}' });
    const payload = await response.json();
    const note = document.getElementById('sidebar-session-message');

    if (note) {
        note.textContent = payload.message || 'Demo stream stopped.';
    }

    await refreshOverview();
}

async function toggleBridge() {
    const current = boot.liveState && boot.liveState.robot_bridge_enabled;
    const response = await apiFetch(boot.urls.demoRobotBridgeUrl, {
        method: 'POST',
        body: JSON.stringify({ enabled: !current }),
    });

    const payload = await response.json();
    if (payload && Object.prototype.hasOwnProperty.call(payload, 'enabled')) {
        boot.liveState.robot_bridge_enabled = payload.enabled;
    }

    await refreshOverview();
}

/* ── Collapsible Metrics Toggle ────────────────────────────── */
window.toggleOverviewMetrics = function() {
    const cardGrid = document.querySelector('.card-grid');
    const metricGrid = document.querySelector('.metric-grid');
    const icon = document.getElementById('collapse-icon');
    const isCollapsed = cardGrid.style.display === 'none';

    if (isCollapsed) {
        cardGrid.style.display = '';
        if (metricGrid) metricGrid.style.display = '';
        if (icon) icon.style.transform = 'rotate(0deg)';
    } else {
        cardGrid.style.display = 'none';
        if (metricGrid) metricGrid.style.display = 'none';
        if (icon) icon.style.transform = 'rotate(180deg)';
    }
};

/* ── EYE TRACKING — Inline WebSocket + Webcam Controller ── */
const EYE_WS_URL = 'ws://localhost:8000/ws/gaze';
const FRAME_INTERVAL_MS = 150;  // ~6-7 fps to reduce server load
const SMOOTHING = 0.35;          // exponential smoothing factor (0=frozen, 1=raw)

let _eyeWs           = null;
let _eyeStream       = null;
let _eyeFrameTimer   = null;
let _eyeRenderTimer  = null;
let _eyeRunning      = false;
let _eyeSmoothedYaw  = 0;
let _eyeSmoothedPitch = 0;
let _eyeLastData     = null;    // latest JSON payload from server

// DOM references cached on first use
function _eyeEl(id) { return document.getElementById(id); }

function _setEyeWsBadge(connected) {
    const b = _eyeEl('eye-ws-badge');
    if (!b) return;
    b.textContent  = connected ? 'Server connected' : 'Server offline';
    b.className    = 'eye-ws-badge ' + (connected ? 'connected' : 'disconnected');
}

function _setEyeStreamPill(running) {
    const p = _eyeEl('eye-stream-pill');
    if (!p) return;
    p.textContent = running ? 'Streaming' : 'Idle';
    p.className   = 'status-pill ' + (running ? 'status-success' : 'status-muted');
}

function _updateEyeButtons(running) {
    const s = _eyeEl('eye-start-btn');
    const t = _eyeEl('eye-stop-btn');
    if (s) s.disabled = running;
    if (t) t.disabled = !running;

    const sSidebar = _eyeEl('eye-start-btn-sidebar');
    const tSidebar = _eyeEl('eye-stop-btn-sidebar');
    if (sSidebar) sSidebar.disabled = running;
    if (tSidebar) tSidebar.disabled = !running;
}

function _updateEyeUI(data) {
    if (!data) return;
    _eyeLastData = data;

    const dir  = data.direction || 'CENTER';
    const conf = data.confidence || 0;
    const yaw  = typeof data.yaw   === 'number' ? data.yaw   : 0;
    const pitch= typeof data.pitch === 'number' ? data.pitch : 0;

    // Exponential smoothing on angles
    _eyeSmoothedYaw   = _eyeSmoothedYaw   + SMOOTHING * (yaw   - _eyeSmoothedYaw);
    _eyeSmoothedPitch = _eyeSmoothedPitch + SMOOTHING * (pitch - _eyeSmoothedPitch);

    // Direction overlay in canvas
    const overlay = _eyeEl('eye-direction-overlay');
    const dirLabel = _eyeEl('eye-dir-label');
    const confLabel = _eyeEl('eye-conf-label');
    if (overlay)  overlay.style.display = '';
    if (dirLabel) {
        dirLabel.textContent = dir;
        dirLabel.className   = 'eye-direction-label ' + dir;
    }
    if (confLabel) confLabel.textContent = 'Confidence: ' + conf + '%';

    // No-face badge
    const noFace = _eyeEl('eye-no-face-badge');
    if (noFace) noFace.classList.toggle('visible', !data.face_detected);

    // Stats row
    const sd = _eyeEl('eye-stat-direction');
    const sy = _eyeEl('eye-stat-yaw');
    const sp = _eyeEl('eye-stat-pitch');
    if (sd) sd.textContent = dir;
    if (sy) sy.textContent = _eyeSmoothedYaw.toFixed(1)   + '°';
    if (sp) sp.textContent = _eyeSmoothedPitch.toFixed(1) + '°';

    // Note box
    const note = _eyeEl('eye-note');
    if (note && data.face_detected) {
        note.textContent = 'Gaze detected — direction: ' + dir + ' (' + conf + '% confidence)';
    }

    // Sync robot viewer on eye command
    _updateRobotViewer(dir, _eyeRunning);
}

/* Render loop: draws mirrored webcam video onto canvas. */
function _eyeRenderFrame() {
    const video  = _eyeEl('eye-video');
    const canvas = _eyeEl('eye-canvas');
    if (!video || !canvas || video.readyState < 2) return;

    const W = video.videoWidth  || 640;
    const H = video.videoHeight || 480;
    canvas.width  = W;
    canvas.height = H;

    const ctx = canvas.getContext('2d');

    // Mirror the video horizontally (natural selfie view)
    ctx.save();
    ctx.translate(W, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, W, H);
    ctx.restore();

    const d = _eyeLastData;
    if (!d || !d.face_detected) return;

    // Draw face bounding box
    if (d.bbox && d.bbox.length === 4) {
        // Mirror bbox x coords
        const x1m = W - d.bbox[2];
        const x2m = W - d.bbox[0];
        const bw  = x2m - x1m;
        const bh  = d.bbox[3] - d.bbox[1];
        ctx.strokeStyle = 'rgba(99,202,183,0.9)';
        ctx.lineWidth   = 2;
        ctx.strokeRect(x1m, d.bbox[1], bw, bh);

        // Draw gaze direction arrow from face center
        const cx = x1m + bw / 2;
        const cy = d.bbox[1] + bh / 2;
        const L  = Math.min(bw, bh) * 0.7;
        const yawRad   = _eyeSmoothedYaw   * Math.PI / 180;
        const pitchRad = _eyeSmoothedPitch * Math.PI / 180;
        // Mirrored view: negate yaw direction for natural rendering
        const ex = cx - L * Math.sin(yawRad);
        const ey = cy - L * Math.sin(pitchRad);

        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(ex, ey);
        ctx.strokeStyle = 'rgba(251,191,36,0.95)';
        ctx.lineWidth   = 3;
        ctx.lineCap     = 'round';
        ctx.stroke();

        // Arrow head
        const angle   = Math.atan2(ey - cy, ex - cx);
        const headLen = 14;
        ctx.beginPath();
        ctx.moveTo(ex, ey);
        ctx.lineTo(ex - headLen * Math.cos(angle - Math.PI / 6),
                   ey - headLen * Math.sin(angle - Math.PI / 6));
        ctx.lineTo(ex - headLen * Math.cos(angle + Math.PI / 6),
                   ey - headLen * Math.sin(angle + Math.PI / 6));
        ctx.closePath();
        ctx.fillStyle = 'rgba(251,191,36,0.95)';
        ctx.fill();
    }
}

/* Send one JPEG frame over the WebSocket. */
function _eyeSendFrame() {
    if (!_eyeWs || _eyeWs.readyState !== WebSocket.OPEN) return;
    const video  = _eyeEl('eye-video');
    if (!video || video.readyState < 2) return;

    // Draw to a small offscreen canvas for JPEG encoding
    const offscreen = document.createElement('canvas');
    offscreen.width  = video.videoWidth  || 640;
    offscreen.height = video.videoHeight || 480;
    const ctx = offscreen.getContext('2d');
    // Send natural (un-mirrored) frame to the model
    ctx.drawImage(video, 0, 0);

    offscreen.toBlob((blob) => {
        if (!blob || !_eyeWs || _eyeWs.readyState !== WebSocket.OPEN) return;
        blob.arrayBuffer().then(buf => {
            if (_eyeWs && _eyeWs.readyState === WebSocket.OPEN) {
                _eyeWs.send(buf);
            }
        });
    }, 'image/jpeg', 0.75);
}

async function startEyeTracking() {
    if (_eyeRunning) return;

    const note = _eyeEl('eye-note');

    // Request webcam access
    try {
        _eyeStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    } catch (err) {
        if (note) note.textContent = 'Webcam access denied: ' + err.message;
        return;
    }

    const video = _eyeEl('eye-video');
    video.srcObject = _eyeStream;
    await video.play();

    // Hide placeholder
    const placeholder = _eyeEl('eye-placeholder');
    if (placeholder) placeholder.style.display = 'none';

    // Open WebSocket
    _eyeWs = new WebSocket(EYE_WS_URL);
    _eyeWs.binaryType = 'arraybuffer';

    _eyeWs.onopen = () => {
        _setEyeWsBadge(true);
        if (note) note.textContent = 'Connected to gaze server. Streaming...';
    };

    _eyeWs.onmessage = (evt) => {
        try {
            const data = JSON.parse(evt.data);
            _updateEyeUI(data);
        } catch (e) { /* ignore malformed */ }
    };

    _eyeWs.onerror = () => {
        _setEyeWsBadge(false);
        if (note) note.textContent = 'WebSocket error — is the eye tracking server running on port 8000?';
    };

    _eyeWs.onclose = () => {
        _setEyeWsBadge(false);
        if (_eyeRunning) {
            if (note) note.textContent = 'Connection closed. Server may have stopped.';
        }
    };

    _eyeRunning = true;
    _updateEyeButtons(true);
    _setEyeStreamPill(true);

    // Start frame send loop
    _eyeFrameTimer  = setInterval(_eyeSendFrame,   FRAME_INTERVAL_MS);
    // Start render loop at ~30fps
    _eyeRenderTimer = setInterval(_eyeRenderFrame, 33);
}

function stopEyeTracking() {
    _eyeRunning = false;

    clearInterval(_eyeFrameTimer);
    clearInterval(_eyeRenderTimer);
    _eyeFrameTimer  = null;
    _eyeRenderTimer = null;

    if (_eyeWs) {
        _eyeWs.close();
        _eyeWs = null;
    }

    if (_eyeStream) {
        _eyeStream.getTracks().forEach(t => t.stop());
        _eyeStream = null;
    }

    // Reset video
    const video = _eyeEl('eye-video');
    if (video) { video.srcObject = null; }

    // Clear canvas
    const canvas = _eyeEl('eye-canvas');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    // Show placeholder again
    const placeholder = _eyeEl('eye-placeholder');
    if (placeholder) placeholder.style.display = '';

    // Hide direction overlay
    const overlay = _eyeEl('eye-direction-overlay');
    if (overlay) overlay.style.display = 'none';

    // Reset no-face badge
    const noFace = _eyeEl('eye-no-face-badge');
    if (noFace) noFace.classList.remove('visible');

    // Reset stats
    ['eye-stat-direction','eye-stat-yaw','eye-stat-pitch'].forEach(id => {
        const el = _eyeEl(id);
        if (el) el.textContent = '---';
    });

    _setEyeWsBadge(false);
    _setEyeStreamPill(false);
    _updateEyeButtons(false);
    _eyeSmoothedYaw   = 0;
    _eyeSmoothedPitch = 0;
    _eyeLastData      = null;
    _updateRobotViewer('IDLE', false);
}

/* ── Mode Select / Dashboard transition ─────────────── */
function showModeSelect() {
    const selectScreen = document.getElementById('mode-select-screen');
    const dashSection  = document.getElementById('dashboard-section');
    if (selectScreen) selectScreen.classList.remove('hidden-section');
    if (dashSection)  dashSection.classList.add('hidden-section');

    // Stop any active streams when returning to selector
    stopEyeTracking();
}

function showDashboard() {
    const selectScreen = document.getElementById('mode-select-screen');
    const dashSection  = document.getElementById('dashboard-section');
    if (selectScreen) selectScreen.classList.add('hidden-section');
    if (dashSection)  dashSection.classList.remove('hidden-section');
}

// Patch activateMode to handle the screen transition
const _origActivateMode = activateMode;
activateMode = async function(mode) {
    await _origActivateMode(mode);
    showDashboard();
};

document.addEventListener('DOMContentLoaded', () => {
    updateModeCards(boot.selectedMode);
    updateMetrics(boot.metrics);
    updateLiveState(boot.liveState);
    renderSidebarControls(boot.selectedMode);

    // Always start on mode-select screen on fresh page load
    showModeSelect();

    // If server-side session had eye_tracking selected, pre-set panels
    if (boot.selectedMode === 'eye_tracking') {
        const mentalPanel = document.getElementById('mental-stream-panel');
        const eyePanel    = document.getElementById('eye-tracking-panel');
        const heroPanel   = document.querySelector('.hero');
        if (heroPanel) heroPanel.style.display = 'none';
        if (mentalPanel) mentalPanel.style.display = 'none';
        if (eyePanel)    eyePanel.classList.add('visible');
    }

    setInterval(refreshOverview, 5000);
});
