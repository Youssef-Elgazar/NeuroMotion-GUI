import os
import sqlite3
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
DATABASE_PATH = os.path.join(INSTANCE_DIR, 'neuro_motion.db')
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin'
ADMIN_DISPLAY_NAME = 'Administrator'


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_instance_dir():
    os.makedirs(INSTANCE_DIR, exist_ok=True)


def get_connection():
    ensure_instance_dir()
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    ensure_instance_dir()
    with get_connection() as connection:
        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                created_at TEXT NOT NULL
            )
            '''
        )
        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS demo_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                packets_processed INTEGER NOT NULL DEFAULT 0,
                accuracy REAL NOT NULL DEFAULT 0,
                confidence REAL NOT NULL DEFAULT 0,
                subject TEXT,
                notes TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            '''
        )
        connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_demo_sessions_user_started ON demo_sessions(user_id, started_at DESC)'
        )

        admin_row = connection.execute(
            'SELECT id FROM users WHERE username = ?',
            (ADMIN_USERNAME,)
        ).fetchone()
        if admin_row is None:
            connection.execute(
                '''
                INSERT INTO users (username, display_name, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    ADMIN_USERNAME,
                    ADMIN_DISPLAY_NAME,
                    generate_password_hash(ADMIN_PASSWORD),
                    'admin',
                    utc_now_iso(),
                )
            )
        connection.commit()


def authenticate_user(username, password):
    if not username or not password:
        return None

    with get_connection() as connection:
        user = connection.execute(
            'SELECT * FROM users WHERE username = ?',
            (username.strip(),)
        ).fetchone()

    if user is None:
        return None

    if not check_password_hash(user['password_hash'], password):
        return None

    return dict(user)


def get_user_by_id(user_id):
    with get_connection() as connection:
        user = connection.execute(
            'SELECT id, username, display_name, role, created_at FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()

    return dict(user) if user else None


def create_demo_session(user_id, mode='mental_command_streaming'):
    with get_connection() as connection:
        cursor = connection.execute(
            '''
            INSERT INTO demo_sessions (user_id, mode, status, started_at)
            VALUES (?, ?, ?, ?)
            ''',
            (user_id, mode, 'running', utc_now_iso())
        )
        connection.commit()
        return cursor.lastrowid


def update_demo_session(session_id, **fields):
    if not fields:
        return

    allowed_fields = {
        'mode',
        'status',
        'ended_at',
        'packets_processed',
        'accuracy',
        'confidence',
        'subject',
        'notes',
    }
    updates = []
    values = []
    for key, value in fields.items():
        if key in allowed_fields:
            updates.append(f'{key} = ?')
            values.append(value)
    if not updates:
        return

    values.append(session_id)
    with get_connection() as connection:
        connection.execute(
            f'UPDATE demo_sessions SET {", ".join(updates)} WHERE id = ?',
            values,
        )
        connection.commit()


def finalize_demo_session(session_id, snapshot=None, status='completed'):
    snapshot = snapshot or {}
    update_demo_session(
        session_id,
        status=status,
        ended_at=utc_now_iso(),
        packets_processed=int(snapshot.get('packet_id', 0) or 0),
        accuracy=float(snapshot.get('accuracy', 0) or 0),
        confidence=float(snapshot.get('confidence', 0) or 0),
        subject=snapshot.get('active_subject'),
        notes=snapshot.get('last_dispatch', {}).get('message') if snapshot.get('last_dispatch') else None,
    )


def get_user_metrics(user_id):
    with get_connection() as connection:
        row = connection.execute(
            '''
            SELECT
                COUNT(*) AS total_sessions,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_sessions,
                COALESCE(AVG(accuracy), 0) AS average_accuracy,
                COALESCE(AVG(confidence), 0) AS average_confidence,
                COALESCE(SUM(packets_processed), 0) AS total_packets,
                MAX(started_at) AS last_started_at
            FROM demo_sessions
            WHERE user_id = ?
            ''',
            (user_id,)
        ).fetchone()

        last_mode_row = connection.execute(
            '''
            SELECT mode
            FROM demo_sessions
            WHERE user_id = ?
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            ''',
            (user_id,)
        ).fetchone()

        recent_sessions = connection.execute(
            '''
            SELECT id, mode, status, started_at, ended_at, packets_processed, accuracy, confidence, subject, notes
            FROM demo_sessions
            WHERE user_id = ?
            ORDER BY started_at DESC
            LIMIT 5
            ''',
            (user_id,)
        ).fetchall()

    metrics = dict(row) if row else {}
    metrics['total_sessions'] = int(metrics.get('total_sessions') or 0)
    metrics['completed_sessions'] = int(metrics.get('completed_sessions') or 0)
    metrics['average_accuracy'] = round(float(metrics.get('average_accuracy') or 0), 2)
    metrics['average_confidence'] = round(float(metrics.get('average_confidence') or 0), 2)
    metrics['total_packets'] = int(metrics.get('total_packets') or 0)
    metrics['last_started_at'] = metrics.get('last_started_at')
    metrics['last_mode'] = last_mode_row['mode'] if last_mode_row else 'N/A'
    metrics['recent_sessions'] = [dict(item) for item in recent_sessions]
    return metrics


def get_demo_session(session_id):
    with get_connection() as connection:
        row = connection.execute(
            'SELECT * FROM demo_sessions WHERE id = ?',
            (session_id,)
        ).fetchone()
    return dict(row) if row else None
