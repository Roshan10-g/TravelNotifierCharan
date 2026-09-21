"""
Database layer for TravelNotifier bot.
Manages users, schedules, custom commute routes, and active journey tracking state.
Uses SQLite for zero-setup, reliable storage.
"""

import sqlite3
import os
from typing import Optional, Dict, List, Any
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "travel_notifier.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they do not exist."""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                morning_time TEXT DEFAULT '08:00',
                evening_time TEXT DEFAULT '18:30',
                active_days TEXT DEFAULT 'mon,tue,wed,thu,fri',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                direction TEXT NOT NULL,           -- 'morning' or 'evening'
                stop_order INTEGER NOT NULL,       -- 0 = Origin, 1..N = Mid, End = Dest
                stop_name TEXT NOT NULL,
                mode TEXT DEFAULT 'metro',         -- 'metro', 'bus', 'walk', 'place'
                lat REAL NOT NULL,
                lng REAL NOT NULL,
                metro_line TEXT,
                alert_distance_m INTEGER DEFAULT 500,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_journeys (
                user_id INTEGER PRIMARY KEY,
                direction TEXT NOT NULL,
                current_target_index INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'IDLE', -- 'IDLE', 'AWAITING_LOCATION', 'IN_TRANSIT', 'SNOOZED', 'COMPLETED'
                one_stop_alert_sent INTEGER DEFAULT 0,
                arrival_alert_sent INTEGER DEFAULT 0,
                last_lat REAL,
                last_lng REAL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        conn.commit()


def get_or_create_user(user_id: int, first_name: str = "", username: str = "") -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)

        cursor.execute(
            "INSERT INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
            (user_id, first_name, username)
        )
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return dict(cursor.fetchone())


def update_user_schedule(user_id: int, morning_time: str, evening_time: str, active_days: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users
            SET morning_time = ?, evening_time = ?, active_days = ?
            WHERE user_id = ?
        """, (morning_time, evening_time, active_days, user_id))
        conn.commit()


def get_all_users() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        return [dict(row) for row in cursor.fetchall()]


def save_user_route(user_id: int, direction: str, stops: List[Dict]):
    """
    Saves an ordered list of stops for 'morning' or 'evening'.
    stops = [
        {"stop_name": "...", "mode": "...", "lat": 17.x, "lng": 78.x, "metro_line": "...", "alert_distance_m": 800},
        ...
    ]
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_routes WHERE user_id = ? AND direction = ?", (user_id, direction))

        for idx, s in enumerate(stops):
            alert_dist = s.get("alert_distance_m", 800 if s.get("mode") == "metro" else 500)
            cursor.execute("""
                INSERT INTO user_routes (user_id, direction, stop_order, stop_name, mode, lat, lng, metro_line, alert_distance_m)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                direction,
                idx,
                s["stop_name"],
                s.get("mode", "metro"),
                float(s["lat"]),
                float(s["lng"]),
                s.get("metro_line"),
                alert_dist
            ))
        conn.commit()


def auto_generate_evening_route(user_id: int):
    """
    Automatically creates the evening route by reversing the morning route stops.
    """
    morning_stops = get_user_route(user_id, "morning")
    if not morning_stops:
        return

    # Reverse the order of stops
    reversed_stops = list(reversed(morning_stops))
    evening_stops = []
    for s in reversed_stops:
        evening_stops.append({
            "stop_name": s["stop_name"],
            "mode": s["mode"],
            "lat": s["lat"],
            "lng": s["lng"],
            "metro_line": s["metro_line"],
            "alert_distance_m": s["alert_distance_m"]
        })
    save_user_route(user_id, "evening", evening_stops)


def get_user_route(user_id: int, direction: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM user_routes
            WHERE user_id = ? AND direction = ?
            ORDER BY stop_order ASC
        """, (user_id, direction))
        return [dict(row) for row in cursor.fetchall()]


def has_user_route(user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM user_routes WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row["cnt"] > 0


def start_journey(user_id: int, direction: str = "morning") -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO active_journeys (user_id, direction, current_target_index, status, one_stop_alert_sent, arrival_alert_sent, started_at)
            VALUES (?, ?, 1, 'AWAITING_LOCATION', 0, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                direction = excluded.direction,
                current_target_index = 1,
                status = 'AWAITING_LOCATION',
                one_stop_alert_sent = 0,
                arrival_alert_sent = 0,
                started_at = CURRENT_TIMESTAMP
        """, (user_id, direction))
        conn.commit()
        return get_active_journey(user_id)


def get_active_journey(user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM active_journeys WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_journey_state(
    user_id: int,
    current_target_index: Optional[int] = None,
    status: Optional[str] = None,
    one_stop_alert_sent: Optional[int] = None,
    arrival_alert_sent: Optional[int] = None,
    last_lat: Optional[float] = None,
    last_lng: Optional[float] = None
):
    with get_connection() as conn:
        cursor = conn.cursor()
        fields = []
        values = []

        if current_target_index is not None:
            fields.append("current_target_index = ?")
            values.append(current_target_index)
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if one_stop_alert_sent is not None:
            fields.append("one_stop_alert_sent = ?")
            values.append(one_stop_alert_sent)
        if arrival_alert_sent is not None:
            fields.append("arrival_alert_sent = ?")
            values.append(arrival_alert_sent)
        if last_lat is not None:
            fields.append("last_lat = ?")
            values.append(last_lat)
        if last_lng is not None:
            fields.append("last_lng = ?")
            values.append(last_lng)

        if not fields:
            return

        values.append(user_id)
        sql = f"UPDATE active_journeys SET {', '.join(fields)} WHERE user_id = ?"
        cursor.execute(sql, tuple(values))
        conn.commit()


def end_journey(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM active_journeys WHERE user_id = ?", (user_id,))
        conn.commit()


def seed_defaults():
    """Seeds the default commuter route if database is initialized on a new cloud host."""
    user_id = 6430193583
    if not has_user_route(user_id):
        get_or_create_user(user_id, "Sri", "Sricharan_2690")
        update_user_schedule(user_id, "08:30", "16:45", "mon,tue,wed,thu,fri")
        stops = [
            {"stop_name": "Dilsukhnagar Metro", "mode": "metro", "lat": 17.3688, "lng": 78.5247, "metro_line": "red", "alert_distance_m": 800},
            {"stop_name": "Ameerpet Metro", "mode": "metro", "lat": 17.4375, "lng": 78.4482, "metro_line": "red", "alert_distance_m": 800},
            {"stop_name": "HITEC City Metro", "mode": "metro", "lat": 17.4474, "lng": 78.3762, "metro_line": "blue", "alert_distance_m": 800},
            {"stop_name": "Jayabheri Bus Stop (HITEC City)", "mode": "bus", "lat": 17.4586, "lng": 78.3706, "metro_line": None, "alert_distance_m": 500}
        ]
        save_user_route(user_id, "morning", stops)
        auto_generate_evening_route(user_id)


# Initialize database and seed user when module is imported
init_db()
seed_defaults()
