"""
cities.py — CITIES dict with lat/lng for 15 major Indian cities.
Coordinates verified against latlong.net, geodatos.net, latitude.to.

Key geo-velocity pairs (haversine distances):
  Mumbai  -> Bengaluru:  ~984 km  (impossible in <10 min = >5,904 km/h)
  Delhi   -> Mumbai:     ~1,148 km (impossible in <10 min = >6,888 km/h)
  Chennai -> Hyderabad:  ~625 km  (impossible in <10 min = >3,750 km/h)
"""

CITIES = {
    "Mumbai":        {"lat": 19.0760, "lng": 72.8777},
    "Delhi":         {"lat": 28.6139, "lng": 77.2090},
    "Bengaluru":     {"lat": 12.9716, "lng": 77.5946},
    "Chennai":       {"lat": 13.0827, "lng": 80.2707},
    "Hyderabad":     {"lat": 17.3850, "lng": 78.4867},
    "Kolkata":       {"lat": 22.5726, "lng": 88.3639},
    "Pune":          {"lat": 18.5204, "lng": 73.8567},
    "Ahmedabad":     {"lat": 23.0225, "lng": 72.5714},
    "Jaipur":        {"lat": 26.9124, "lng": 75.7873},
    "Lucknow":       {"lat": 26.8467, "lng": 80.9462},
    "Surat":         {"lat": 21.1702, "lng": 72.8311},
    "Nagpur":        {"lat": 21.1458, "lng": 79.0882},
    "Visakhapatnam": {"lat": 17.6868, "lng": 83.2185},
    "Kochi":         {"lat": 9.9312,  "lng": 76.2673},
    "Indore":        {"lat": 22.7196, "lng": 75.8577},
}

# Ordered list of city names for random selection
CITY_NAMES = list(CITIES.keys())
