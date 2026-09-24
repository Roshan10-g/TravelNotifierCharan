"""
Hyderabad Metro Network & Station Sequence Data
Supports Red, Blue, and Green lines with sequences, coordinates, and preceding station detection.
"""

from typing import Optional, Dict, List, Tuple

METRO_STATIONS = {
    # Corridor 1: Red Line (Miyapur to LB Nagar)
    "red": [
        {"name": "Miyapur", "lat": 17.4968, "lng": 78.3614, "aliases": ["miyapur"]},
        {"name": "JNTU College", "lat": 17.4975, "lng": 78.3892, "aliases": ["jntu", "jntu college", "jntuh"]},
        {"name": "KPHB Colony", "lat": 17.4930, "lng": 78.4014, "aliases": ["kphb", "kphb colony"]},
        {"name": "Kukatpally", "lat": 17.4842, "lng": 78.4138, "aliases": ["kukatpally", "kpt"]},
        {"name": "Balanagar", "lat": 17.4729, "lng": 78.4287, "aliases": ["balanagar", "dr br ambedkar balanagar"]},
        {"name": "Moosapet", "lat": 17.4682, "lng": 78.4352, "aliases": ["moosapet"]},
        {"name": "Bharat Nagar", "lat": 17.4635, "lng": 78.4418, "aliases": ["bharat nagar", "bharatnagar"]},
        {"name": "Erragadda", "lat": 17.4578, "lng": 78.4452, "aliases": ["erragadda"]},
        {"name": "ESI Hospital", "lat": 17.4502, "lng": 78.4468, "aliases": ["esi", "esi hospital"]},
        {"name": "SR Nagar", "lat": 17.4431, "lng": 78.4480, "aliases": ["sr nagar", "sanjeeva reddy nagar"]},
        {"name": "Ameerpet", "lat": 17.4375, "lng": 78.4482, "aliases": ["ameerpet", "ameerpet interchange"], "interchange": True},
        {"name": "Punjagutta", "lat": 17.4273, "lng": 78.4524, "aliases": ["punjagutta", "panjagutta"]},
        {"name": "Irrum Manzil", "lat": 17.4199, "lng": 78.4578, "aliases": ["irrum manzil", "erramanzil"]},
        {"name": "Khairatabad", "lat": 17.4124, "lng": 78.4616, "aliases": ["khairatabad", "khairtabad"]},
        {"name": "Lakdikapul", "lat": 17.4048, "lng": 78.4651, "aliases": ["lakdikapul", "lakdi ka pul"]},
        {"name": "Assembly", "lat": 17.3992, "lng": 78.4687, "aliases": ["assembly"]},
        {"name": "Nampally", "lat": 17.3923, "lng": 78.4719, "aliases": ["nampally", "hyderabad rly station"]},
        {"name": "Gandhi Bhavan", "lat": 17.3871, "lng": 78.4764, "aliases": ["gandhi bhavan"]},
        {"name": "Osmania Medical College", "lat": 17.3812, "lng": 78.4815, "aliases": ["omc", "osmania", "osmania medical college", "koti"]},
        {"name": "MGBS", "lat": 17.3775, "lng": 78.4847, "aliases": ["mgbs", "imlibun"], "interchange": True},
        {"name": "Malakpet", "lat": 17.3752, "lng": 78.4946, "aliases": ["malakpet"]},
        {"name": "New Market", "lat": 17.3734, "lng": 78.5032, "aliases": ["new market"]},
        {"name": "Musarambagh", "lat": 17.3712, "lng": 78.5135, "aliases": ["musarambagh"]},
        {"name": "Dilsukhnagar", "lat": 17.3688, "lng": 78.5247, "aliases": ["dsnr", "dilsukhnagar", "dilsukh nagar"]},
        {"name": "Chaitanyapuri", "lat": 17.3642, "lng": 78.5376, "aliases": ["chaitanyapuri"]},
        {"name": "Victoria Memorial", "lat": 17.3592, "lng": 78.5492, "aliases": ["victoria memorial", "kothapet"]},
        {"name": "LB Nagar", "lat": 17.3541, "lng": 78.5583, "aliases": ["lb nagar", "l b nagar"]}
    ],

    # Corridor 3: Blue Line (Nagole to Raidurg)
    "blue": [
        {"name": "Nagole", "lat": 17.3866, "lng": 78.5645, "aliases": ["nagole"]},
        {"name": "Uppal", "lat": 17.4025, "lng": 78.5601, "aliases": ["uppal"]},
        {"name": "Stadium", "lat": 17.4082, "lng": 78.5516, "aliases": ["stadium", "uppal stadium"]},
        {"name": "NGRI", "lat": 17.4136, "lng": 78.5422, "aliases": ["ngri"]},
        {"name": "Habsiguda", "lat": 17.4184, "lng": 78.5332, "aliases": ["habsiguda"]},
        {"name": "Tarnaka", "lat": 17.4258, "lng": 78.5235, "aliases": ["tarnaka"]},
        {"name": "Mettuguda", "lat": 17.4328, "lng": 78.5152, "aliases": ["mettuguda"]},
        {"name": "Secunderabad East", "lat": 17.4398, "lng": 78.5038, "aliases": ["secunderabad east", "sec east", "secunderabad"]},
        {"name": "Parade Ground", "lat": 17.4442, "lng": 78.4975, "aliases": ["parade ground"], "interchange": True},
        {"name": "Paradise", "lat": 17.4431, "lng": 78.4862, "aliases": ["paradise"]},
        {"name": "Rasoolpura", "lat": 17.4418, "lng": 78.4735, "aliases": ["rasoolpura"]},
        {"name": "Prakash Nagar", "lat": 17.4426, "lng": 78.4618, "aliases": ["prakash nagar", "begumpet airport"]},
        {"name": "Begumpet", "lat": 17.4385, "lng": 78.4552, "aliases": ["begumpet"]},
        {"name": "Ameerpet", "lat": 17.4375, "lng": 78.4482, "aliases": ["ameerpet", "ameerpet interchange"], "interchange": True},
        {"name": "Madhura Nagar", "lat": 17.4352, "lng": 78.4382, "aliases": ["madhura nagar"]},
        {"name": "Yousufguda", "lat": 17.4312, "lng": 78.4285, "aliases": ["yousufguda"]},
        {"name": "Jubilee Hills Road No 5", "lat": 17.4282, "lng": 78.4215, "aliases": ["jubilee hills road no 5", "road no 5"]},
        {"name": "Jubilee Hills Check Post", "lat": 17.4262, "lng": 78.4118, "aliases": ["check post", "jh check post", "jubilee hills check post"]},
        {"name": "Peddamma Gudi", "lat": 17.4286, "lng": 78.4032, "aliases": ["peddamma gudi", "peddammagudi"]},
        {"name": "Madhapur", "lat": 17.4365, "lng": 78.3932, "aliases": ["madhapur"]},
        {"name": "Durgam Cheruvu", "lat": 17.4428, "lng": 78.3842, "aliases": ["durgam cheruvu", "durgamcheruvu"]},
        {"name": "HITEC City", "lat": 17.4474, "lng": 78.3762, "aliases": ["hitec city", "hitech city", "cyber towers", "hitec"]},
        {"name": "Raidurg", "lat": 17.4412, "lng": 78.3685, "aliases": ["raidurg", "mindspace"]}
    ],

    # Corridor 2: Green Line (JBS Parade Ground to MGBS)
    "green": [
        {"name": "JBS Parade Ground", "lat": 17.4485, "lng": 78.4985, "aliases": ["jbs", "jbs parade ground"], "interchange": True},
        {"name": "Secunderabad West", "lat": 17.4415, "lng": 78.4998, "aliases": ["secunderabad west", "sec west"]},
        {"name": "Gandhi Hospital", "lat": 17.4305, "lng": 78.5042, "aliases": ["gandhi hospital"]},
        {"name": "Musheerabad", "lat": 17.4218, "lng": 78.5065, "aliases": ["musheerabad"]},
        {"name": "RTC X Roads", "lat": 17.4112, "lng": 78.5005, "aliases": ["rtc x roads", "rtc crossroads", "rtc x road"]},
        {"name": "Chikkadpally", "lat": 17.4022, "lng": 78.4982, "aliases": ["chikkadpally"]},
        {"name": "Narayanguda", "lat": 17.3945, "lng": 78.4942, "aliases": ["narayanguda"]},
        {"name": "Sultan Bazaar", "lat": 17.3855, "lng": 78.4892, "aliases": ["sultan bazaar", "koti green line"]},
        {"name": "MGBS", "lat": 17.3775, "lng": 78.4847, "aliases": ["mgbs", "imlibun"], "interchange": True}
    ]
}


def search_metro_stations(query: str) -> List[Dict]:
    """
    Search metro stations by name, alias, or substring.
    Returns list of matching station dicts with line info.
    """
    q = query.strip().lower()
    matches = []
    seen = set()

    for line_name, stations in METRO_STATIONS.items():
        for idx, station in enumerate(stations):
            s_name = station["name"].lower()
            aliases = station.get("aliases", [])
            is_match = q in s_name or any(q == alias or q in alias for alias in aliases)

            if is_match:
                key = (station["name"], line_name)
                if key not in seen:
                    seen.add(key)
                    matches.append({
                        "name": station["name"],
                        "lat": station["lat"],
                        "lng": station["lng"],
                        "line": line_name,
                        "sequence_index": idx,
                        "mode": "metro",
                        "display_title": f"🚇 {station['name']} ({line_name.capitalize()} Line)"
                    })

    return matches


def normalize_metro_name(name: str) -> str:
    """Strips 'metro', 'station', 'interchange' etc. for fuzzy matching."""
    n = name.lower()
    for w in ["metro station", "metro", "station", "interchange"]:
        n = n.replace(w, "")
    return " ".join(n.split()).strip()


def find_station(name: str, line: Optional[str] = None) -> Optional[Dict]:
    """Retrieve station metadata by name and optional line."""
    name_clean = normalize_metro_name(name)
    for line_name, stations in METRO_STATIONS.items():
        if line and line.lower() != line_name:
            continue
        for idx, station in enumerate(stations):
            s_clean = normalize_metro_name(station["name"])
            aliases_clean = [normalize_metro_name(a) for a in station.get("aliases", [])]
            if s_clean == name_clean or name_clean in aliases_clean:
                return {
                    "name": station["name"],
                    "lat": station["lat"],
                    "lng": station["lng"],
                    "line": line_name,
                    "sequence_index": idx,
                    "mode": "metro"
                }
    return None


def get_preceding_metro_station(origin_name: str, target_name: str, preferred_line: Optional[str] = None) -> Optional[Dict]:
    """
    Calculates the exact station that is ONE STOP BEFORE target_name
    when traveling from origin_name to target_name.
    """
    origin_clean = normalize_metro_name(origin_name)
    target_clean = normalize_metro_name(target_name)

    # Check lines that contain BOTH stations
    for line_name, stations in METRO_STATIONS.items():
        if preferred_line and preferred_line != line_name:
            continue

        o_idx = None
        t_idx = None
        for idx, s in enumerate(stations):
            s_clean = normalize_metro_name(s["name"])
            aliases_clean = [normalize_metro_name(a) for a in s.get("aliases", [])]

            if s_clean == origin_clean or origin_clean in aliases_clean:
                o_idx = idx
            if s_clean == target_clean or target_clean in aliases_clean:
                t_idx = idx

        if o_idx is not None and t_idx is not None:
            if o_idx == t_idx:
                return None
            # Direction:
            # If o_idx < t_idx, traveling in increasing index order. Station before target is t_idx - 1
            # If o_idx > t_idx, traveling in decreasing index order. Station before target is t_idx + 1
            prec_idx = t_idx - 1 if o_idx < t_idx else t_idx + 1
            if 0 <= prec_idx < len(stations):
                prec_station = stations[prec_idx]
                return {
                    "name": prec_station["name"],
                    "lat": prec_station["lat"],
                    "lng": prec_station["lng"],
                    "line": line_name,
                    "sequence_index": prec_idx
                }

    # If origin and target are on different lines (e.g. DSNR to HITEC City where Ameerpet is interchange),
    # then for leg 1 (DSNR to Ameerpet): Ameerpet is on Red Line. Preceding is Punjagutta.
    # for leg 2 (Ameerpet to HITEC City): HITEC City is on Blue Line. Preceding is Durgam Cheruvu.
    return None
