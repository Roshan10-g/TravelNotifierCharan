"""
Comprehensive Test Suite for TravelNotifier Bot
Tests Metro sequences, Geocoding, SQLite storage, Journey Engine, and Scheduler.
"""

import unittest
import os
import metro_data
import geocoder
import database
import journey_engine


class TestTravelNotifier(unittest.TestCase):

    def setUp(self):
        database.init_db()

    def test_metro_preceding_station_forward(self):
        # DSNR (idx 23) -> Ameerpet (idx 10) on Red Line (decreasing)
        # Preceding should be idx 11 -> Punjagutta
        prec = metro_data.get_preceding_metro_station("Dilsukhnagar", "Ameerpet", preferred_line="red")
        self.assertIsNotNone(prec)
        self.assertEqual(prec["name"], "Punjagutta")

        # Ameerpet (idx 13) -> HITEC City (idx 21) on Blue Line (increasing)
        # Preceding should be idx 20 -> Durgam Cheruvu
        prec2 = metro_data.get_preceding_metro_station("Ameerpet", "HITEC City", preferred_line="blue")
        self.assertIsNotNone(prec2)
        self.assertEqual(prec2["name"], "Durgam Cheruvu")

    def test_metro_preceding_station_reverse(self):
        # HITEC City (idx 21) -> Ameerpet (idx 13) on Blue Line (decreasing)
        # Preceding should be idx 14 -> Madhura Nagar
        prec = metro_data.get_preceding_metro_station("HITEC City", "Ameerpet", preferred_line="blue")
        self.assertIsNotNone(prec)
        self.assertEqual(prec["name"], "Madhura Nagar")

    def test_geocoder_search(self):
        results = geocoder.search_locations("Ameerpet", limit=5)
        self.assertTrue(len(results) > 0)
        has_metro = any(r["mode"] == "metro" for r in results)
        self.assertTrue(has_metro)

    def test_database_and_journey_engine(self):
        user_id = 88888
        database.get_or_create_user(user_id, "TestUser", "tester")
        database.update_user_schedule(user_id, "08:15", "18:45", "mon-fri")

        stops = [
            {"stop_name": "Dilsukhnagar", "mode": "metro", "lat": 17.3688, "lng": 78.5247, "metro_line": "red"},
            {"stop_name": "Ameerpet", "mode": "metro", "lat": 17.4375, "lng": 78.4482, "metro_line": "red"},
            {"stop_name": "HITEC City", "mode": "metro", "lat": 17.4474, "lng": 78.3762, "metro_line": "blue"}
        ]
        database.save_user_route(user_id, "morning", stops)
        database.auto_generate_evening_route(user_id)

        # Verify evening route is auto-reversed
        ev_stops = database.get_user_route(user_id, "evening")
        self.assertEqual(len(ev_stops), 3)
        self.assertEqual(ev_stops[0]["stop_name"], "HITEC City")
        self.assertEqual(ev_stops[1]["stop_name"], "Ameerpet")
        self.assertEqual(ev_stops[2]["stop_name"], "Dilsukhnagar")

        # Start morning journey
        database.start_journey(user_id, "morning")
        j = database.get_active_journey(user_id)
        self.assertEqual(j["current_target_index"], 1)

        # 1. Simulate passing Punjagutta (preceding Ameerpet)
        r1 = journey_engine.process_location_update(user_id, 17.4273, 78.4524)
        self.assertIsNotNone(r1)
        self.assertTrue(r1.should_notify)
        self.assertIn("1 STOP BEFORE", r1.message)
        self.assertIn("Punjagutta", r1.message)

        # 2. Simulate reaching Ameerpet
        r2 = journey_engine.process_location_update(user_id, 17.4375, 78.4482)
        self.assertIsNotNone(r2)
        self.assertTrue(r2.should_notify)
        self.assertIn("YOU ARE AT AMEERPET", r2.message)

        # Journey index advanced to 2
        j2 = database.get_active_journey(user_id)
        self.assertEqual(j2["current_target_index"], 2)

        # 3. Simulate reaching HITEC City
        r3 = journey_engine.process_location_update(user_id, 17.4474, 78.3762)
        self.assertIsNotNone(r3)
        self.assertTrue(r3.should_notify)
        self.assertTrue(r3.is_completed)
        self.assertIn("DESTINATION REACHED", r3.message)

        # Active journey should be cleaned up
        j_final = database.get_active_journey(user_id)
        self.assertIsNone(j_final)


if __name__ == "__main__":
    unittest.main()
