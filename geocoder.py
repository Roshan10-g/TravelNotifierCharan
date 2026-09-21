"""
Location Resolver and Autocomplete Engine
Merges pre-cached Hyderabad Metro database & Major Transit Bus Stops with Photon & Nominatim geocoding.
Biased and filtered to Greater Hyderabad / Telangana coordinates.
"""

import requests
import re
from typing import List, Dict
import metro_data

PHOTON_API_URL = "https://photon.komoot.io/api/"
NOMINATIM_API_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    "User-Agent": "TravelNotifierBot/1.0 (Hyderabad Commute Assistant)"
}

HYD_LAT = 17.3850
HYD_LON = 78.4867

# Major Hyderabad bus stops, IT corridor hubs & transit stages
HYD_BUS_STOPS: List[Dict] = [
    {
        "name": "Jayabheri Bus Stop (HITEC City)",
        "display_title": "🚌 Jayabheri Bus Stop (HITEC City / Kondapur)",
        "subtitle": "Near Silicon Towers & County, Hitec City Main Road",
        "mode": "bus",
        "lat": 17.4586,
        "lng": 78.3706,
        "aliases": [
            "jayabheri", "jayabheri bus stop", "jayabheri hitech city", "jayabheri hitechcity",
            "jayabheri silicon towers", "jayabheri silicon county", "jayabheri kondapur",
            "jayabheri 4 seasons", "jayabheri silicon", "jayabheri bus stoip"
        ]
    },
    {
        "name": "Cyber Towers Bus Stop",
        "display_title": "🚌 Cyber Towers Bus Stop (HITEC City)",
        "subtitle": "HITEC City Junction, Madhapur",
        "mode": "bus",
        "lat": 17.4506,
        "lng": 78.3801,
        "aliases": ["cyber towers", "cyber towers bus stop", "cyber gateway", "hitec city bus stop"]
    },
    {
        "name": "Mindspace Bus Stop",
        "display_title": "🚌 Mindspace Bus Stop / Raheja IT Park",
        "subtitle": "Madhapur / Raidurg, Hyderabad",
        "mode": "bus",
        "lat": 17.4395,
        "lng": 78.3805,
        "aliases": ["mindspace", "mindspace bus stop", "raheja mindspace", "mindspace madhapur"]
    },
    {
        "name": "Kothaguda X Roads Bus Stop",
        "display_title": "🚌 Kothaguda Junction Bus Stop",
        "subtitle": "Kothaguda - Botanical Garden Road",
        "mode": "bus",
        "lat": 17.4580,
        "lng": 78.3630,
        "aliases": ["kothaguda", "kothaguda bus stop", "kothaguda cross roads", "kothaguda x roads"]
    },
    {
        "name": "Botanical Garden Bus Stop",
        "display_title": "🚌 Botanical Garden Bus Stop",
        "subtitle": "Kondapur - Gachibowli Road",
        "mode": "bus",
        "lat": 17.4530,
        "lng": 78.3580,
        "aliases": ["botanical garden", "botanical garden bus stop", "botanical garden kondapur"]
    },
    {
        "name": "DLF Cybercity Bus Stop",
        "display_title": "🚌 DLF Cybercity Bus Stop (Gachibowli)",
        "subtitle": "Opposite DLF IT Park, Gachibowli",
        "mode": "bus",
        "lat": 17.4475,
        "lng": 78.3580,
        "aliases": ["dlf", "dlf bus stop", "dlf gachibowli", "dlf cybercity"]
    },
    {
        "name": "Bio-Diversity Park Bus Stop",
        "display_title": "🚌 Bio-Diversity Park Bus Stop (Gachibowli)",
        "subtitle": "Old Mumbai Highway, Gachibowli",
        "mode": "bus",
        "lat": 17.4310,
        "lng": 78.3820,
        "aliases": ["bio diversity", "biodiversity", "biodiversity park", "biodiversity bus stop"]
    },
    {
        "name": "Wipro Circle Bus Stop",
        "display_title": "🚌 Wipro Circle Bus Stop (Financial District)",
        "subtitle": "Wipro Junction, Gachibowli / Nanakramguda",
        "mode": "bus",
        "lat": 17.4180,
        "lng": 78.3375,
        "aliases": ["wipro circle", "wipro junction", "wipro circle bus stop", "financial district wipro"]
    },
    {
        "name": "IIIT Junction Bus Stop",
        "display_title": "🚌 IIIT Junction Bus Stop (Gachibowli)",
        "subtitle": "Near Gachibowli Stadium & IIIT Hyderabad",
        "mode": "bus",
        "lat": 17.4430,
        "lng": 78.3490,
        "aliases": ["iiit", "iiit bus stop", "iiit junction", "iiit hyderabad"]
    },
    {
        "name": "WaveRock / SEZ Bus Stop",
        "display_title": "🚌 WaveRock SEZ Bus Stop (Nanakramguda)",
        "subtitle": "Financial District, Nanakramguda",
        "mode": "bus",
        "lat": 17.4150,
        "lng": 78.3410,
        "aliases": ["waverock", "wave rock", "waverock bus stop", "waverock nanakramguda"]
    },
    {
        "name": "Mehdipatnam Bus Depot",
        "display_title": "🚌 Mehdipatnam Bus Depot / Rythu Bazar",
        "subtitle": "Mehdipatnam, Hyderabad",
        "mode": "bus",
        "lat": 17.3915,
        "lng": 78.4410,
        "aliases": ["mehdipatnam", "mehdipatnam bus stop", "mehdipatnam depot"]
    },
    {
        "name": "Ameerpet Mythrivanam Bus Stop",
        "display_title": "🚌 Ameerpet Mythrivanam Bus Stop",
        "subtitle": "Opposite Mythrivanam, Ameerpet",
        "mode": "bus",
        "lat": 17.4365,
        "lng": 78.4470,
        "aliases": ["mythrivanam", "mythrivanam bus stop", "ameerpet bus stop"]
    },
    {
        "name": "Dilsukhnagar Bus Depot",
        "display_title": "🚌 Dilsukhnagar Bus Depot (DSNR)",
        "subtitle": "Near DSNR Metro Station, NH 65",
        "mode": "bus",
        "lat": 17.3690,
        "lng": 78.5255,
        "aliases": ["dsnr bus stop", "dilsukhnagar bus stop", "dilsukhnagar depot"]
    },
    {
        "name": "KPHB Colony Bus Stop",
        "display_title": "🚌 KPHB Colony Bus Stop",
        "subtitle": "KPHB Main Road, Kukatpally",
        "mode": "bus",
        "lat": 17.4935,
        "lng": 78.4010,
        "aliases": ["kphb bus stop", "kphb colony bus stop"]
    },
    {
        "name": "Kukatpally Y-Junction Bus Stop",
        "display_title": "🚌 Kukatpally Y-Junction Bus Stop",
        "subtitle": "Kukatpally - Balanagar Highway",
        "mode": "bus",
        "lat": 17.4850,
        "lng": 78.4140,
        "aliases": ["y junction", "kukatpally y junction", "y junction bus stop"]
    },
    {
        "name": "JNTU Bus Stop",
        "display_title": "🚌 JNTU College Bus Stop",
        "subtitle": "Near JNTU Metro, Nizampet X Roads",
        "mode": "bus",
        "lat": 17.4980,
        "lng": 78.3890,
        "aliases": ["jntu bus stop", "jntu college bus stop", "nizampet x roads"]
    }
]


def is_in_hyderabad_region(lat: float, lng: float) -> bool:
    """Filters results to the Greater Hyderabad / Telangana geographic bounding box."""
    return 16.5 <= lat <= 18.5 and 77.5 <= lng <= 79.5


def clean_search_term(raw_query: str) -> str:
    """Removes transit stopwords like 'bus stop', 'stoip', 'stand' to improve search accuracy."""
    cleaned = re.sub(
        r'\b(bus stop|bus stand|busstop|bus stoip|bus\s*stop|bus|stop|stoip|stand|station)\b',
        '',
        raw_query,
        flags=re.IGNORECASE
    ).strip()
    return cleaned if len(cleaned) >= 2 else raw_query.strip()


def search_locations(query: str, limit: int = 5) -> List[Dict]:
    """
    Search for locations matching query.
    1. Checks curated Hyderabad Transit Bus Stops.
    2. Checks Hyderabad Metro database for exact/partial matches.
    3. Queries Photon (OpenStreetMap) with cleaned search terms.
    4. Falls back to Nominatim if needed.
    Returns deduplicated list with title, subtitle, mode, lat, lng.
    """
    results: List[Dict] = []
    seen_coords = set()

    clean_raw = query.strip().lower()
    cleaned = clean_search_term(query).lower()

    if not clean_raw:
        return results

    # 1. Curated Bus Stops & Transit Hubs first
    for b in HYD_BUS_STOPS:
        b_name = b["name"].lower()
        aliases = [a.lower() for a in b.get("aliases", [])]
        is_match = (
            cleaned in b_name or
            clean_raw in b_name or
            any(cleaned in alias or alias in cleaned or clean_raw in alias or alias in clean_raw for alias in aliases)
        )
        if is_match:
            coord_key = (round(b["lat"], 3), round(b["lng"], 3))
            if coord_key not in seen_coords:
                seen_coords.add(coord_key)
                results.append({
                    "name": b["name"],
                    "display_title": b["display_title"],
                    "subtitle": b["subtitle"],
                    "mode": "bus",
                    "lat": b["lat"],
                    "lng": b["lng"],
                    "metro_line": None
                })

    # 2. Metro station matches (instant, 100% accurate)
    metro_matches = metro_data.search_metro_stations(cleaned if cleaned else clean_raw)
    for m in metro_matches:
        coord_key = (round(m["lat"], 3), round(m["lng"], 3))
        if coord_key not in seen_coords:
            seen_coords.add(coord_key)
            results.append({
                "name": m["name"],
                "display_title": f"🚇 {m['name']} Metro ({m['line'].capitalize()} Line)",
                "subtitle": f"Hyderabad Metro ({m['line'].capitalize()} Line)",
                "mode": "metro",
                "lat": m["lat"],
                "lng": m["lng"],
                "metro_line": m["line"]
            })

    # 3. Photon (OpenStreetMap) search with Hyderabad qualification using cleaned query
    try:
        search_target = cleaned if len(cleaned) >= 3 else clean_raw
        search_term = f"{search_target} Hyderabad" if "hyderabad" not in search_target else search_target
        params = {
            "q": search_term,
            "lat": HYD_LAT,
            "lon": HYD_LON,
            "limit": limit * 2
        }
        resp = requests.get(PHOTON_API_URL, params=params, headers=HEADERS, timeout=4)
        if resp.status_code == 200:
            data = resp.json()
            features = data.get("features", [])
            for feat in features:
                if len(results) >= limit:
                    break

                props = feat.get("properties", {})
                geometry = feat.get("geometry", {})
                coords = geometry.get("coordinates", [])

                if len(coords) < 2:
                    continue

                lng = float(coords[0])
                lat = float(coords[1])

                if not is_in_hyderabad_region(lat, lng):
                    continue

                coord_key = (round(lat, 3), round(lng, 3))
                if coord_key in seen_coords:
                    continue
                seen_coords.add(coord_key)

                name = props.get("name", query)
                osm_key = props.get("osm_key", "")
                osm_value = props.get("osm_value", "")
                city = props.get("city", props.get("district", "Hyderabad"))
                street = props.get("street", props.get("suburb", ""))

                is_bus = (
                    "bus" in name.lower() or
                    osm_value in ["bus_stop", "platform", "stop_position"] or
                    (osm_key in ["highway", "public_transport"] and osm_value == "bus_stop")
                )

                mode = "bus" if is_bus else "place"
                icon = "🚌" if is_bus else "📍"

                details = []
                if street:
                    details.append(street)
                if city:
                    details.append(city)
                subtitle = ", ".join(details) if details else "Hyderabad, Telangana"

                results.append({
                    "name": name,
                    "display_title": f"{icon} {name}",
                    "subtitle": subtitle,
                    "mode": mode,
                    "lat": lat,
                    "lng": lng,
                    "metro_line": None
                })
    except Exception as e:
        print(f"[geocoder] Photon search error: {e}")

    # 4. Nominatim Fallback if results are still sparse
    if len(results) < 2:
        try:
            search_target = cleaned if len(cleaned) >= 3 else clean_raw
            nom_params = {
                "q": f"{search_target}, Hyderabad",
                "format": "json",
                "addressdetails": 1,
                "countrycodes": "in",
                "viewbox": "78.1,17.1,78.7,17.6",
                "limit": 3
            }
            n_resp = requests.get(NOMINATIM_API_URL, params=nom_params, headers=HEADERS, timeout=4)
            if n_resp.status_code == 200:
                for item in n_resp.json():
                    if len(results) >= limit:
                        break
                    n_lat = float(item["lat"])
                    n_lng = float(item["lon"])
                    if not is_in_hyderabad_region(n_lat, n_lng):
                        continue

                    coord_key = (round(n_lat, 3), round(n_lng, 3))
                    if coord_key in seen_coords:
                        continue
                    seen_coords.add(coord_key)

                    n_name = item.get("name") or item.get("display_name", "").split(",")[0]
                    parts = item.get("display_name", "").split(",")
                    sub = ", ".join([p.strip() for p in parts[1:3]]) if len(parts) > 2 else "Hyderabad"

                    results.append({
                        "name": n_name,
                        "display_title": f"📍 {n_name}",
                        "subtitle": sub,
                        "mode": "place",
                        "lat": n_lat,
                        "lng": n_lng,
                        "metro_line": None
                    })
        except Exception as e:
            print(f"[geocoder] Nominatim error: {e}")

    return results[:limit]
