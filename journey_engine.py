"""
Journey Tracking Engine for TravelNotifier.
Evaluates live location updates against user's scheduled route.
Supports:
- Metro: 1-stop before alert (with current passing stop, next stop, and final dest)
- Bus / Other: 500m advance notification
- Destination arrival detection
"""

from typing import Dict, List, Optional, Tuple, Any
from geopy.distance import geodesic
import metro_data
import database
import config


def calculate_distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculates geodesic distance in meters between two lat/lng coordinates."""
    return geodesic((lat1, lng1), (lat2, lng2)).meters


class JourneyEvaluationResult:
    def __init__(
        self,
        should_notify: bool = False,
        message: str = "",
        is_completed: bool = False,
        updated_index: Optional[int] = None
    ):
        self.should_notify = should_notify
        self.message = message
        self.is_completed = is_completed
        self.updated_index = updated_index


def process_location_update(user_id: int, live_lat: float, live_lng: float) -> Optional[JourneyEvaluationResult]:
    """
    Evaluates a single live GPS coordinate stream update for user_id.
    Returns JourneyEvaluationResult if an alert message needs to be sent to the user.
    """
    journey = database.get_active_journey(user_id)
    if not journey:
        return None

    direction = journey["direction"]
    target_idx = journey["current_target_index"]
    one_stop_sent = bool(journey["one_stop_alert_sent"])
    arrival_sent = bool(journey["arrival_alert_sent"])

    stops = database.get_user_route(user_id, direction)
    if not stops or target_idx >= len(stops):
        database.end_journey(user_id)
        return JourneyEvaluationResult(
            should_notify=True,
            message="🎉 Journey completed! All stops have been reached.",
            is_completed=True
        )

    origin_stop = stops[target_idx - 1]
    target_stop = stops[target_idx]
    final_dest = stops[-1]
    is_final_dest = (target_idx == len(stops) - 1)
    mode = target_stop.get("mode", "metro").lower()

    # Update latest coordinates in database
    database.update_journey_state(user_id, last_lat=live_lat, last_lng=live_lng)

    dist_to_target = calculate_distance_meters(live_lat, live_lng, target_stop["lat"], target_stop["lng"])

    # -------------------------------------------------------------
    # 1. ARRIVAL CHECK (At the target stop, < 250m)
    # -------------------------------------------------------------
    if dist_to_target <= config.DEFAULT_ARRIVAL_RADIUS_METERS and not arrival_sent:
        if is_final_dest:
            database.end_journey(user_id)
            return JourneyEvaluationResult(
                should_notify=True,
                message=(
                    f"🎉 <b>DESTINATION REACHED!</b>\n\n"
                    f"🏢 <b>{target_stop['stop_name']}</b>\n"
                    f"You have arrived safely. Commute tracking completed! ✅"
                ),
                is_completed=True
            )
        else:
            # Mid-stop / interchange reached
            next_idx = target_idx + 1
            next_stop = stops[next_idx]
            database.update_journey_state(
                user_id,
                current_target_index=next_idx,
                one_stop_alert_sent=0,
                arrival_alert_sent=0
            )

            icon = "🚇" if target_stop.get("mode") == "metro" else "🚌"
            next_icon = "🚇" if next_stop.get("mode") == "metro" else "🚌"

            return JourneyEvaluationResult(
                should_notify=True,
                message=(
                    f"{icon} <b>YOU ARE AT {target_stop['stop_name'].upper()}!</b>\n\n"
                    f"🔄 <b>Interchange / Transfer Point:</b>\n"
                    f"Deboard here now.\n\n"
                    f"👉 Next Leg: {next_icon} <b>{next_stop['stop_name']}</b> ({next_stop.get('mode', 'transit').capitalize()})\n"
                    f"🎯 Final Destination: <b>{final_dest['stop_name']}</b>"
                ),
                is_completed=False,
                updated_index=next_idx
            )

    # -------------------------------------------------------------
    # 2. METRO 1-STOP BEFORE NOTIFICATION
    # -------------------------------------------------------------
    if mode == "metro" and not one_stop_sent:
        # Determine the preceding station along the line
        preceding = metro_data.get_preceding_metro_station(
            origin_name=origin_stop["stop_name"],
            target_name=target_stop["stop_name"],
            preferred_line=target_stop.get("metro_line")
        )

        should_fire_metro_alert = False
        preceding_name = "Approaching Station"

        if preceding:
            preceding_name = preceding["name"]
            dist_to_preceding = calculate_distance_meters(live_lat, live_lng, preceding["lat"], preceding["lng"])
            # If within 800m of the preceding station
            if dist_to_preceding <= config.DEFAULT_METRO_ALERT_METERS:
                should_fire_metro_alert = True
        else:
            # If no preceding station found (e.g. adjacent stations), alert at ~1000m from target
            if dist_to_target <= 1000:
                should_fire_metro_alert = True
                preceding_name = origin_stop["stop_name"]

        if should_fire_metro_alert:
            database.update_journey_state(user_id, one_stop_alert_sent=1)
            action_text = "Deboard & Transfer" if not is_final_dest else "Deboard at Destination"

            return JourneyEvaluationResult(
                should_notify=True,
                message=(
                    f"🔔 <b>METRO ALERT: 1 STOP BEFORE TARGET!</b>\n\n"
                    f"📍 <b>Current / Passing:</b> {preceding_name}\n"
                    f"🚇 <b>NEXT STOP:</b> <b>{target_stop['stop_name']}</b> (~1-2 mins)\n"
                    f"🎯 <b>Final Destination:</b> {final_dest['stop_name']}\n\n"
                    f"⚡ <i>Action: Get ready to {action_text.lower()}!</i>"
                ),
                is_completed=False
            )

    # -------------------------------------------------------------
    # 3. BUS / OTHER 500M ADVANCE NOTIFICATION
    # -------------------------------------------------------------
    if mode != "metro" and not one_stop_sent:
        alert_dist = target_stop.get("alert_distance_m") or config.DEFAULT_BUS_ALERT_METERS
        if dist_to_target <= alert_dist:
            database.update_journey_state(user_id, one_stop_alert_sent=1)
            action_text = "Alight for transfer" if not is_final_dest else "Alight at Destination"

            return JourneyEvaluationResult(
                should_notify=True,
                message=(
                    f"🔔 <b>STOP ALERT (~500m Away)!</b>\n\n"
                    f"🚌 <b>Approaching:</b> <b>{target_stop['stop_name']}</b>\n"
                    f"🎯 <b>Final Destination:</b> {final_dest['stop_name']}\n"
                    f"📏 <b>Distance:</b> ~{int(dist_to_target)} meters\n\n"
                    f"⚡ <i>Action: {action_text}!</i>"
                ),
                is_completed=False
            )

    return None
