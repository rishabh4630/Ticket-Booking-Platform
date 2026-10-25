"""
TSN Ticket Booking - Cross-Platform Web Version
=================================================
Original project: VB.NET WinForms + Oracle (Windows only, needs an Oracle
client and Crystal Reports). This version: Python + Flask + SQLite, so it
runs on Windows, macOS and Linux with the same code. SQLite replaces Oracle,
the browser replaces WinForms, and reports are plain HTML tables instead of
Crystal Reports.

Run:
    macOS/Linux : ./run_mac_linux.sh   (or: python3 app.py)
    Windows     : run_windows.bat      (or: py app.py)
Then open http://127.0.0.1:5000 in any browser.

Fare rule (stated explicitly, because the original Oracle fare logic was not
recoverable from the SQL schema alone):
    ticket total = number of seats x transport's r_major rate.
The per-seat rate is shown on the booking form and the total on the ticket.

Seed data in this file is DEMO data only, not real schedules or fares.
The original demo login (hardcoded) is NOT copied here: this version has
proper signup/login with hashed passwords (see below).
"""

import html
import json
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from functools import wraps

from flask import Flask, flash, g, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "ticket_booking.db")

app = Flask(__name__)
app.secret_key = "tsn-ticket-booking-dev-key-change-me"

# The owner account: logging in with this email automatically becomes admin,
# so there is no separate admin signup/login page.
# NOTE (same as the Airline project): this email is the GitHub account email
# on file and must be confirmed/changed if it is not the owner's real email.
OWNER_EMAIL = "rishabhsingh4630@gmail.com"


# ---------------------------------------------------------------------------
# Free external APIs (keyless; never allowed to break search or booking)
# OSRM (road distance/driving time), Open-Meteo (destination weather) and
# SearchPinCode (PIN -> post office/city/state) are all free with no key.
# Every call has a short timeout and every failure degrades to "info
# uplabdh nahi" -- the search results and booking flow always still render.
# ---------------------------------------------------------------------------
CITY_COORDS = {
    "Lucknow": (26.8467, 80.9462),
    "Delhi": (28.6139, 77.2090),
    "Mumbai": (19.0760, 72.8777),
    "Bengaluru": (12.9716, 77.5946),
    "Varanasi": (25.3176, 82.9739),
"Agra": (27.1767, 78.0081),
    "Ahmedabad": (23.0225, 72.5714),
    "Amritsar": (31.634, 74.8723),
    "Bhopal": (23.2599, 77.4126),
    "Bhubaneswar": (20.2961, 85.8245),
    "Chandigarh": (30.7333, 76.7794),
    "Chennai": (13.0827, 80.2707),
    "Dehradun": (30.3165, 78.0322),
    "Gorakhpur": (26.7606, 83.3732),
    "Guwahati": (26.1445, 91.7362),
    "Hyderabad": (17.385, 78.4867),
    "Indore": (22.7196, 75.8577),
    "Jaipur": (26.9124, 75.7873),
    "Kanpur": (26.4499, 80.3319),
    "Kochi": (9.9312, 76.2673),
    "Kolkata": (22.5726, 88.3639),
    "Madurai": (9.9252, 78.1198),
    "Nagpur": (21.1458, 79.0882),
    "Panaji": (15.4909, 74.8273),
    "Patna": (25.5941, 85.1376),
    "Prayagraj": (25.4358, 81.8463),
    "Pune": (18.5204, 73.8567),
    "Surat": (21.1702, 72.8311),
}


def _fetch_json(url, timeout=5, headers=None):
    """GET a JSON URL, or None on any failure (timeout, HTTP error, bad JSON)."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def weather_label(code):
    """WMO weather code -> short Hinglish-friendly label."""
    if code is None:
        return "mausam uplabdh nahi"
    code = int(code)
    if code == 0:
        return "Saaf aasmaan"
    if code == 1:
        return "Zyaada tar saaf"
    if code == 2:
        return "Halke baadal"
    if code == 3:
        return "Baadal"
    if code in (45, 48):
        return "Kohra"
    if code in (51, 53, 55, 56, 57):
        return "Halki boondabaandi"
    if code in (61, 80):
        return "Halki baarish"
    if code in (63, 81):
        return "Baarish"
    if code in (65, 82, 66, 67):
        return "Tez baarish"
    if code in (71, 73, 75, 77, 85, 86):
        return "Barf"
    if code in (95, 96, 99):
        return "Aandhi-toofan"
    return "mausam uplabdh nahi"


def fmt_distance(metres):
    if metres < 10000:
        return f"{metres / 1000:.1f} km"
    return f"{round(metres / 1000)} km"


def fmt_duration(seconds):
    hours = int(seconds // 3600)
    minutes = int(round((seconds % 3600) / 60))
    if minutes == 60:
        hours += 1
        minutes = 0
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def resolve_coords(city):
    """(lat, lon) for a city: seed table first, else keyless Nominatim."""
    if city in CITY_COORDS:
        return CITY_COORDS[city]
    data = _fetch_json(
        "https://nominatim.openstreetmap.org/search?format=json&limit=1&q="
        + urllib.parse.quote(city + ", India"),
        headers={"User-Agent": "TSN-Ticket-Booking/1.0 (student demo)"},
    )
    if data and isinstance(data, list) and data:
        try:
            return (float(data[0]["lat"]), float(data[0]["lon"]))
        except (KeyError, TypeError, ValueError):
            return None
    return None


def route_info(from_city, to_city):
    """Road distance + driving time + destination weather. Never raises;
    returns a dict that may be partial or empty when a service fails."""
    info = {}
    try:
        start = resolve_coords(from_city)
        dest = resolve_coords(to_city)
        if start and dest:
            data = _fetch_json(
                "https://router.project-osrm.org/route/v1/driving/"
                f"{start[1]},{start[0]};{dest[1]},{dest[0]}?overview=false"
            )
            routes = (data or {}).get("routes") or []
            if routes:
                info["distance"] = fmt_distance(routes[0]["distance"])
                info["duration"] = fmt_duration(routes[0]["duration"])
        if dest:
            data = _fetch_json(
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={dest[0]}&longitude={dest[1]}"
                "&current=temperature_2m,weather_code&timezone=Asia%2FKolkata"
            )
            current = (data or {}).get("current") or {}
            if "temperature_2m" in current:
                info["weather"] = (
                    f"{current['temperature_2m']}°C, "
                    f"{weather_label(current.get('weather_code'))}"
                )
    except Exception:
        pass
    return info


# ---------------------------------------------------------------------------
# Train live data (Flask only, via RapidAPI "Indian Railway API")
# The listing page confirms the feature areas (trains between stations, live
# running status, PNR status) and a free BASIC plan, but its Endpoints tab
# does not expose exact paths without login, so NO endpoint path is
# hard-coded here -- paths come from env vars once confirmed on the listing.
# Never invent endpoint URLs. The key is read only from the environment and
# is never sent to the browser or the static demo.
# ---------------------------------------------------------------------------
RAPIDAPI_HOST = os.environ.get("RAPIDAPI_HOST", "indian-railway-api1.p.rapidapi.com")
TRAIN_API_ENDPOINTS = {
    "between": os.environ.get("RAPIDAPI_TRAINS_BETWEEN", ""),
    "live": os.environ.get("RAPIDAPI_LIVE_STATUS", ""),
    "pnr": os.environ.get("RAPIDAPI_PNR_STATUS", ""),
}


def rapidapi_get(path, params):
    """Call RapidAPI server-side. Returns (data, error); error is one of
    'no-key', 'no-endpoint', or a short failure message. Never raises."""
    key = os.environ.get("RAPIDAPI_KEY", "")
    if not key:
        return None, "no-key"
    if not path:
        return None, "no-endpoint"
    url = "https://" + RAPIDAPI_HOST + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"X-RapidAPI-Key": key, "X-RapidAPI-Host": RAPIDAPI_HOST}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", "replace")), None
    except Exception as exc:
        return None, str(exc)


def train_setup_card():
    return """<div class="card"><h2>Train Info — setup chahiye</h2>
    <p>Live train data (do stations ke beech trains, live running status, PNR status)
    ke liye <b>free RapidAPI key</b> chahiye. Key ke bina ye page error nahi dega —
    bas setup steps dikhayega.</p>
    <ol>
    <li><b>RapidAPI par free account banao</b> (rapidapi.com).</li>
    <li><b>Indian Railway API</b> listing kholo aur <b>free BASIC plan</b> subscribe karo.</li>
    <li>Apni key copy karo aur server start karne se <b>pehle</b> environment variable me daalo:
    Mac/Linux par <code>export RAPIDAPI_KEY=apki-key</code>, Windows par <code>set RAPIDAPI_KEY=apki-key</code>.</li>
    <li>Server restart karo — phir ye page live train data dikhayega.</li>
    </ol>
    <p class="muted">Key kabhi code me, GitHub par ya static demo me mat daalo — sirf server
    ke environment me rakho. RapidAPI key ke bina koi live train call nahi bheji jaati.</p></div>"""


def train_endpoint_card():
    return """<div class="card"><h2>Train Info — endpoint configure karna baaki hai</h2>
    <p>RapidAPI key mil gayi hai, lekin is API ke <b>exact endpoint paths</b> listing se
    confirm nahi ho paye (RapidAPI page ka Endpoints tab bina login ke paths nahi dikhata),
    isliye koi live call nahi bheji gayi — galat/andaze wale URL par call karna sahi nahi hoga.</p>
    <p>Listing ke Endpoints tab se path dekhkar server start karne se pehle ye environment
    variables daalo, phir server restart karo:</p>
    <ul>
    <li><code>RAPIDAPI_TRAINS_BETWEEN</code> — do stations ke beech trains wala path</li>
    <li><code>RAPIDAPI_LIVE_STATUS</code> — live running status wala path</li>
    <li><code>RAPIDAPI_PNR_STATUS</code> — PNR status wala path</li>
    </ul>
    <p class="muted">Feature areas listing se confirmed hain: trains between stations,
    live running status aur 10-digit PNR status. Paths confirm hote hi ye forms live ho jayenge.</p></div>"""


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS states (
            state_code INTEGER PRIMARY KEY,
            state_name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cities (
            city_code INTEGER PRIMARY KEY,
            city_name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS streets (
            st_code INTEGER PRIMARY KEY,
            st_name TEXT NOT NULL,
            p_code TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS transport_types (
            ttid INTEGER PRIMARY KEY,
            ttname TEXT NOT NULL,
            tdesc TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS routes (
            rid INTEGER PRIMARY KEY,
            r_name TEXT NOT NULL,
            st_pos TEXT NOT NULL,
            dest TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS route_det (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rid INTEGER NOT NULL REFERENCES routes(rid),
            via TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transports (
            tid INTEGER PRIMARY KEY,
            tname TEXT NOT NULL,
            capacity INTEGER NOT NULL DEFAULT 0,
            r_minor INTEGER NOT NULL DEFAULT 0,
            r_major INTEGER NOT NULL DEFAULT 0,
            r_uom TEXT DEFAULT 'per seat',
            st_pos TEXT NOT NULL,
            dest TEXT NOT NULL,
            st_time TEXT DEFAULT '',
            reach_time TEXT DEFAULT '',
            ttid INTEGER REFERENCES transport_types(ttid),
            rid INTEGER REFERENCES routes(rid)
        );
        CREATE TABLE IF NOT EXISTS payments (
            pmid INTEGER PRIMARY KEY,
            pname TEXT NOT NULL,
            amt INTEGER NOT NULL DEFAULT 0,
            p_desc TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS payment_det (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pmid INTEGER NOT NULL REFERENCES payments(pmid),
            ch_no TEXT DEFAULT '',
            ch_date TEXT DEFAULT '',
            dsc TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS customers (
            cust_code INTEGER PRIMARY KEY,
            cust_add TEXT DEFAULT '',
            st_code INTEGER REFERENCES streets(st_code),
            city_code INTEGER REFERENCES cities(city_code),
            state_code INTEGER REFERENCES states(state_code),
            cust_phone TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS cust_det (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cust_code INTEGER NOT NULL REFERENCES customers(cust_code),
            cust_name TEXT NOT NULL,
            age INTEGER,
            sex TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS bookings (
            book_no INTEGER PRIMARY KEY,
            book_date TEXT NOT NULL,
            cust_id INTEGER REFERENCES customers(cust_code),
            cust_name TEXT NOT NULL,
            tid INTEGER NOT NULL REFERENCES transports(tid),
            pmode_id INTEGER REFERENCES payments(pmid),
            user_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS booking_seats (
            book_no INTEGER NOT NULL REFERENCES bookings(book_no),
            seat_no INTEGER NOT NULL,
            PRIMARY KEY (book_no, seat_no)
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'customer'
        );
        """
    )
    # Demo seed data (labelled as demo in the README). Only on a fresh DB.
    if db.execute("SELECT COUNT(*) FROM transports").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO states VALUES (?,?)",
            [(1, "Uttar Pradesh"), (2, "Maharashtra"), (3, "Karnataka"), (4, "Delhi")],
        )
        db.executemany(
            "INSERT INTO cities VALUES (?,?)",
            [(1, "Lucknow"), (2, "Mumbai"), (3, "Bengaluru"), (4, "Delhi"), (5, "Varanasi")],
        )
        db.executemany(
            "INSERT INTO streets VALUES (?,?,?)",
            [(1, "MG Road", "226001"), (2, "Station Road", "400001"),
             (3, "Civil Lines", "226001"), (4, "Brigade Road", "560001")],
        )
        db.executemany(
            "INSERT INTO transport_types VALUES (?,?,?)",
            [(1, "AC Bus", "Air-conditioned bus"), (2, "Non-AC Bus", "Ordinary bus"),
             (3, "Train", "Passenger train")],
        )
        db.executemany(
            "INSERT INTO routes VALUES (?,?,?,?)",
            [(1, "Lucknow-Delhi", "Lucknow", "Delhi"),
             (2, "Delhi-Mumbai", "Delhi", "Mumbai"),
             (3, "Lucknow-Bengaluru", "Lucknow", "Bengaluru")],
        )
        db.executemany(
            "INSERT INTO route_det (rid, via) VALUES (?,?)",
            [(1, "Bareilly"), (1, "Moradabad"), (2, "Jaipur"),
             (2, "Udaipur"), (3, "Nagpur"), (3, "Hyderabad")],
        )
        db.executemany(
            "INSERT INTO transports VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (1, "TSN Express", 40, 300, 500, "per seat", "Lucknow", "Delhi",
                 "06:00", "12:00", 1, 1),
                (2, "TSN Deluxe", 50, 400, 750, "per seat", "Delhi", "Mumbai",
                 "08:00", "20:00", 1, 2),
                (3, "TSN Mail", 120, 600, 950, "per seat", "Lucknow", "Bengaluru",
                 "09:00", "21:00", 3, 3),
                (4, "TSN Ordinary", 45, 250, 450, "per seat", "Delhi", "Mumbai",
                 "07:30", "19:30", 2, 2),
            ],
        )
        db.executemany(
            "INSERT INTO payments VALUES (?,?,?,?)",
            [(1, "Cash", 0, "Pay in cash"), (2, "Cheque", 0, "Pay by cheque")],
        )
        db.executemany(
            "INSERT INTO customers VALUES (?,?,?,?,?,?)",
            [(1, "12 MG Road", 1, 1, 1, "9876543210"),
             (2, "45 Civil Lines", 3, 1, 1, "9876501234")],
        )
        db.executemany(
            "INSERT INTO cust_det (cust_code, cust_name, age, sex) VALUES (?,?,?,?)",
            [(1, "Rahul Sharma", 30, "Male"), (2, "Priya Verma", 27, "Female")],
        )
    # All-India expansion (2026-10-25, demo data only, not real schedules
    # or fares). Append-only sync: INSERT OR IGNORE adds these rows to
    # existing local DBs on next run without touching the old seed rows.
    # Route rows are one per corridor (both directions share the corridor
    # row, like the existing 'Lucknow-Delhi' naming); transports are
    # directed both ways because search matches transports by exact
    # st_pos/dest. Home shows only the first 9 routes (see home()).
    db.executemany("INSERT OR IGNORE INTO states VALUES (?,?)",
        [(5, 'Rajasthan'), (6, 'Gujarat'), (7, 'Madhya Pradesh'), (8, 'Bihar'), (9, 'West Bengal'), (10, 'Odisha'), (11, 'Assam'), (12, 'Telangana'), (13, 'Tamil Nadu'), (14, 'Kerala'), (15, 'Punjab'), (16, 'Uttarakhand'), (17, 'Goa'), (18, 'Chandigarh')])
    db.executemany("INSERT OR IGNORE INTO cities VALUES (?,?)",
        [(6, 'Jaipur'), (7, 'Agra'), (8, 'Kanpur'), (9, 'Chandigarh'), (10, 'Amritsar'), (11, 'Dehradun'), (12, 'Gorakhpur'), (13, 'Prayagraj'), (14, 'Patna'), (15, 'Kolkata'), (16, 'Bhubaneswar'), (17, 'Guwahati'), (18, 'Ahmedabad'), (19, 'Surat'), (20, 'Pune'), (21, 'Nagpur'), (22, 'Bhopal'), (23, 'Indore'), (24, 'Hyderabad'), (25, 'Chennai'), (26, 'Kochi'), (27, 'Madurai'), (28, 'Panaji')])
    db.executemany("INSERT OR IGNORE INTO routes VALUES (?,?,?,?)",
        [(4, 'Delhi-Jaipur', 'Delhi', 'Jaipur'),
         (5, 'Mumbai-Pune', 'Mumbai', 'Pune'),
         (6, 'Bengaluru-Chennai', 'Bengaluru', 'Chennai'),
         (7, 'Delhi-Kolkata', 'Delhi', 'Kolkata'),
         (8, 'Lucknow-Varanasi', 'Lucknow', 'Varanasi'),
         (9, 'Mumbai-Bengaluru', 'Mumbai', 'Bengaluru'),
         (10, 'Delhi-Agra', 'Delhi', 'Agra'),
         (11, 'Delhi-Kanpur', 'Delhi', 'Kanpur'),
         (12, 'Delhi-Chandigarh', 'Delhi', 'Chandigarh'),
         (13, 'Delhi-Amritsar', 'Delhi', 'Amritsar'),
         (14, 'Delhi-Dehradun', 'Delhi', 'Dehradun'),
         (15, 'Delhi-Varanasi', 'Delhi', 'Varanasi'),
         (16, 'Delhi-Bhopal', 'Delhi', 'Bhopal'),
         (17, 'Delhi-Indore', 'Delhi', 'Indore'),
         (18, 'Delhi-Patna', 'Delhi', 'Patna'),
         (19, 'Delhi-Ahmedabad', 'Delhi', 'Ahmedabad'),
         (20, 'Delhi-Nagpur', 'Delhi', 'Nagpur'),
         (21, 'Delhi-Hyderabad', 'Delhi', 'Hyderabad'),
         (22, 'Delhi-Chennai', 'Delhi', 'Chennai'),
         (23, 'Lucknow-Kanpur', 'Lucknow', 'Kanpur'),
         (24, 'Lucknow-Gorakhpur', 'Lucknow', 'Gorakhpur'),
         (25, 'Lucknow-Prayagraj', 'Lucknow', 'Prayagraj'),
         (26, 'Lucknow-Agra', 'Lucknow', 'Agra'),
         (27, 'Lucknow-Kolkata', 'Lucknow', 'Kolkata'),
         (28, 'Lucknow-Patna', 'Lucknow', 'Patna'),
         (29, 'Mumbai-Ahmedabad', 'Mumbai', 'Ahmedabad'),
         (30, 'Mumbai-Surat', 'Mumbai', 'Surat'),
         (31, 'Mumbai-Nagpur', 'Mumbai', 'Nagpur'),
         (32, 'Mumbai-Hyderabad', 'Mumbai', 'Hyderabad'),
         (33, 'Mumbai-Panaji', 'Mumbai', 'Panaji'),
         (34, 'Bengaluru-Hyderabad', 'Bengaluru', 'Hyderabad'),
         (35, 'Bengaluru-Kochi', 'Bengaluru', 'Kochi'),
         (36, 'Bengaluru-Madurai', 'Bengaluru', 'Madurai'),
         (37, 'Chennai-Hyderabad', 'Chennai', 'Hyderabad'),
         (38, 'Chennai-Madurai', 'Chennai', 'Madurai'),
         (39, 'Chennai-Kochi', 'Chennai', 'Kochi'),
         (40, 'Kolkata-Patna', 'Kolkata', 'Patna'),
         (41, 'Kolkata-Bhubaneswar', 'Kolkata', 'Bhubaneswar'),
         (42, 'Kolkata-Guwahati', 'Kolkata', 'Guwahati')])
    db.executemany("INSERT OR IGNORE INTO transports VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(5, 'TSN Aravalli', 45, 200, 300, 'per seat', 'Delhi', 'Jaipur', '06:00', '11:00', 1, 4),
         (6, 'TSN Aravalli', 45, 200, 300, 'per seat', 'Jaipur', 'Delhi', '16:00', '21:00', 1, 4),
         (7, 'TSN Aravalli Mail', 110, 250, 350, 'per seat', 'Delhi', 'Jaipur', '07:30', '12:00', 3, 4),
         (8, 'TSN Aravalli Mail', 110, 250, 350, 'per seat', 'Jaipur', 'Delhi', '17:00', '21:30', 3, 4),
         (9, 'TSN Sahyadri', 45, 150, 200, 'per seat', 'Mumbai', 'Pune', '07:00', '10:30', 1, 5),
         (10, 'TSN Sahyadri', 45, 150, 200, 'per seat', 'Pune', 'Mumbai', '17:00', '20:30', 1, 5),
         (11, 'TSN Sahyadri Mail', 110, 180, 250, 'per seat', 'Mumbai', 'Pune', '08:00', '11:30', 3, 5),
         (12, 'TSN Sahyadri Mail', 110, 180, 250, 'per seat', 'Pune', 'Mumbai', '18:00', '21:30', 3, 5),
         (13, 'TSN Kaveri', 45, 250, 350, 'per seat', 'Bengaluru', 'Chennai', '07:00', '12:30', 1, 6),
         (14, 'TSN Kaveri', 45, 250, 350, 'per seat', 'Chennai', 'Bengaluru', '16:00', '21:30', 1, 6),
         (15, 'TSN Kaveri Mail', 110, 280, 400, 'per seat', 'Bengaluru', 'Chennai', '08:00', '13:00', 3, 6),
         (16, 'TSN Kaveri Mail', 110, 280, 400, 'per seat', 'Chennai', 'Bengaluru', '17:00', '22:00', 3, 6),
         (17, 'TSN Hooghly', 120, 800, 1150, 'per seat', 'Delhi', 'Kolkata', '17:00', '11:30', 3, 7),
         (18, 'TSN Hooghly', 120, 800, 1150, 'per seat', 'Kolkata', 'Delhi', '18:00', '12:30', 3, 7),
         (19, 'TSN Awadh', 45, 250, 350, 'per seat', 'Lucknow', 'Varanasi', '07:00', '12:00', 1, 8),
         (20, 'TSN Awadh', 45, 250, 350, 'per seat', 'Varanasi', 'Lucknow', '15:00', '20:00', 1, 8),
         (21, 'TSN Tungabhadra', 120, 650, 950, 'per seat', 'Mumbai', 'Bengaluru', '19:00', '10:00', 3, 9),
         (22, 'TSN Tungabhadra', 120, 650, 950, 'per seat', 'Bengaluru', 'Mumbai', '20:00', '11:00', 3, 9),
         (23, 'TSN Braj', 45, 180, 250, 'per seat', 'Delhi', 'Agra', '07:00', '11:00', 1, 10),
         (24, 'TSN Braj', 45, 180, 250, 'per seat', 'Agra', 'Delhi', '15:00', '19:00', 1, 10),
         (25, 'TSN Ganga', 50, 320, 450, 'per seat', 'Delhi', 'Kanpur', '20:00', '06:00', 2, 11),
         (26, 'TSN Ganga', 50, 320, 450, 'per seat', 'Kanpur', 'Delhi', '20:30', '06:30', 2, 11),
         (27, 'TSN Shivalik', 45, 200, 300, 'per seat', 'Delhi', 'Chandigarh', '07:00', '11:30', 1, 12),
         (28, 'TSN Shivalik', 45, 200, 300, 'per seat', 'Chandigarh', 'Delhi', '16:00', '20:30', 1, 12),
         (29, 'TSN Amrit', 120, 380, 550, 'per seat', 'Delhi', 'Amritsar', '08:00', '14:30', 3, 13),
         (30, 'TSN Amrit', 120, 380, 550, 'per seat', 'Amritsar', 'Delhi', '15:00', '21:30', 3, 13),
         (31, 'TSN Doon', 45, 200, 300, 'per seat', 'Delhi', 'Dehradun', '06:30', '12:00', 1, 14),
         (32, 'TSN Doon', 45, 200, 300, 'per seat', 'Dehradun', 'Delhi', '15:30', '21:00', 1, 14),
         (33, 'TSN Kashi', 120, 550, 800, 'per seat', 'Delhi', 'Varanasi', '18:00', '08:00', 3, 15),
         (34, 'TSN Kashi', 120, 550, 800, 'per seat', 'Varanasi', 'Delhi', '19:00', '09:00', 3, 15),
         (35, 'TSN Vindhya', 110, 520, 750, 'per seat', 'Delhi', 'Bhopal', '21:00', '07:00', 3, 16),
         (36, 'TSN Vindhya', 110, 520, 750, 'per seat', 'Bhopal', 'Delhi', '21:30', '07:30', 3, 16),
         (37, 'TSN Malwa', 110, 550, 800, 'per seat', 'Delhi', 'Indore', '20:00', '08:30', 3, 17),
         (38, 'TSN Malwa', 110, 550, 800, 'per seat', 'Indore', 'Delhi', '20:30', '09:00', 3, 17),
         (39, 'TSN Saryu', 120, 650, 950, 'per seat', 'Delhi', 'Patna', '17:00', '10:00', 3, 18),
         (40, 'TSN Saryu', 120, 650, 950, 'per seat', 'Patna', 'Delhi', '18:00', '11:00', 3, 18),
         (41, 'TSN Sabarmati', 120, 620, 900, 'per seat', 'Delhi', 'Ahmedabad', '19:00', '09:30', 3, 19),
         (42, 'TSN Sabarmati', 120, 620, 900, 'per seat', 'Ahmedabad', 'Delhi', '19:30', '10:00', 3, 19),
         (43, 'TSN Vidarbha', 110, 700, 1000, 'per seat', 'Delhi', 'Nagpur', '18:30', '10:30', 3, 20),
         (44, 'TSN Vidarbha', 110, 700, 1000, 'per seat', 'Nagpur', 'Delhi', '19:00', '11:00', 3, 20),
         (45, 'TSN Deccan', 120, 850, 1200, 'per seat', 'Delhi', 'Hyderabad', '16:00', '12:00', 3, 21),
         (46, 'TSN Deccan', 120, 850, 1200, 'per seat', 'Hyderabad', 'Delhi', '17:00', '13:00', 3, 21),
         (47, 'TSN Coromandel', 120, 1000, 1400, 'per seat', 'Delhi', 'Chennai', '15:00', '13:00', 3, 22),
         (48, 'TSN Coromandel', 120, 1000, 1400, 'per seat', 'Chennai', 'Delhi', '16:00', '14:00', 3, 22),
         (49, 'TSN Gomti', 50, 100, 150, 'per seat', 'Lucknow', 'Kanpur', '08:00', '10:00', 2, 23),
         (50, 'TSN Gomti', 50, 100, 150, 'per seat', 'Kanpur', 'Lucknow', '17:00', '19:00', 2, 23),
         (51, 'TSN Terai', 45, 200, 300, 'per seat', 'Lucknow', 'Gorakhpur', '07:30', '12:00', 1, 24),
         (52, 'TSN Terai', 45, 200, 300, 'per seat', 'Gorakhpur', 'Lucknow', '15:30', '20:00', 1, 24),
         (53, 'TSN Sangam', 50, 150, 200, 'per seat', 'Lucknow', 'Prayagraj', '08:00', '11:30', 2, 25),
         (54, 'TSN Sangam', 50, 150, 200, 'per seat', 'Prayagraj', 'Lucknow', '16:00', '19:30', 2, 25),
         (55, 'TSN Chambal', 45, 250, 350, 'per seat', 'Lucknow', 'Agra', '07:00', '12:30', 1, 26),
         (56, 'TSN Chambal', 45, 250, 350, 'per seat', 'Agra', 'Lucknow', '15:00', '20:30', 1, 26),
         (57, 'TSN Purvanchal', 120, 650, 950, 'per seat', 'Lucknow', 'Kolkata', '18:00', '10:00', 3, 27),
         (58, 'TSN Purvanchal', 120, 650, 950, 'per seat', 'Kolkata', 'Lucknow', '19:00', '11:00', 3, 27),
         (59, 'TSN Sone', 110, 420, 600, 'per seat', 'Lucknow', 'Patna', '20:00', '06:00', 3, 28),
         (60, 'TSN Sone', 110, 420, 600, 'per seat', 'Patna', 'Lucknow', '21:00', '07:00', 3, 28),
         (61, 'TSN Tapti', 50, 380, 550, 'per seat', 'Mumbai', 'Ahmedabad', '07:00', '14:00', 1, 29),
         (62, 'TSN Tapti', 50, 380, 550, 'per seat', 'Ahmedabad', 'Mumbai', '15:00', '22:00', 1, 29),
         (63, 'TSN Narmada', 45, 200, 300, 'per seat', 'Mumbai', 'Surat', '07:30', '12:30', 1, 30),
         (64, 'TSN Narmada', 45, 200, 300, 'per seat', 'Surat', 'Mumbai', '16:00', '21:00', 1, 30),
         (65, 'TSN Wardha', 110, 550, 800, 'per seat', 'Mumbai', 'Nagpur', '20:00', '08:00', 3, 31),
         (66, 'TSN Wardha', 110, 550, 800, 'per seat', 'Nagpur', 'Mumbai', '20:30', '08:30', 3, 31),
         (67, 'TSN Krishna', 110, 520, 750, 'per seat', 'Mumbai', 'Hyderabad', '21:00', '07:30', 3, 32),
         (68, 'TSN Krishna', 110, 520, 750, 'per seat', 'Hyderabad', 'Mumbai', '21:30', '08:00', 3, 32),
         (69, 'TSN Konkan', 45, 420, 600, 'per seat', 'Mumbai', 'Panaji', '07:00', '17:00', 1, 33),
         (70, 'TSN Konkan', 45, 420, 600, 'per seat', 'Panaji', 'Mumbai', '08:00', '18:00', 1, 33),
         (71, 'TSN Godavari', 110, 420, 600, 'per seat', 'Bengaluru', 'Hyderabad', '21:00', '07:00', 3, 34),
         (72, 'TSN Godavari', 110, 420, 600, 'per seat', 'Hyderabad', 'Bengaluru', '21:30', '07:30', 3, 34),
         (73, 'TSN Malabar', 45, 380, 550, 'per seat', 'Bengaluru', 'Kochi', '07:30', '17:30', 1, 35),
         (74, 'TSN Malabar', 45, 380, 550, 'per seat', 'Kochi', 'Bengaluru', '08:00', '18:00', 1, 35),
         (75, 'TSN Pandya', 50, 320, 450, 'per seat', 'Bengaluru', 'Madurai', '20:00', '05:00', 2, 36),
         (76, 'TSN Pandya', 50, 320, 450, 'per seat', 'Madurai', 'Bengaluru', '21:00', '06:00', 2, 36),
         (77, 'TSN Pennar', 110, 450, 650, 'per seat', 'Chennai', 'Hyderabad', '20:00', '07:00', 3, 37),
         (78, 'TSN Pennar', 110, 450, 650, 'per seat', 'Hyderabad', 'Chennai', '21:00', '08:00', 3, 37),
         (79, 'TSN Vaigai', 45, 320, 450, 'per seat', 'Chennai', 'Madurai', '07:00', '13:30', 1, 38),
         (80, 'TSN Vaigai', 45, 320, 450, 'per seat', 'Madurai', 'Chennai', '15:00', '21:30', 1, 38),
         (81, 'TSN Nilgiri', 110, 480, 700, 'per seat', 'Chennai', 'Kochi', '19:30', '07:00', 3, 39),
         (82, 'TSN Nilgiri', 110, 480, 700, 'per seat', 'Kochi', 'Chennai', '20:00', '07:30', 3, 39),
         (83, 'TSN Koshi', 110, 420, 600, 'per seat', 'Kolkata', 'Patna', '19:00', '06:00', 3, 40),
         (84, 'TSN Koshi', 110, 420, 600, 'per seat', 'Patna', 'Kolkata', '20:00', '07:00', 3, 40),
         (85, 'TSN Kalinga', 110, 350, 500, 'per seat', 'Kolkata', 'Bhubaneswar', '08:00', '14:30', 3, 41),
         (86, 'TSN Kalinga', 110, 350, 500, 'per seat', 'Bhubaneswar', 'Kolkata', '15:00', '21:30', 3, 41),
         (87, 'TSN Brahmaputra', 120, 650, 950, 'per seat', 'Kolkata', 'Guwahati', '17:30', '11:00', 3, 42),
         (88, 'TSN Brahmaputra', 120, 650, 950, 'per seat', 'Guwahati', 'Kolkata', '18:30', '12:00', 3, 42)])
    # route_det has no unique key, so guard via rows with NOT EXISTS
    # to keep re-runs from duplicating them.
    db.executemany(
        "INSERT INTO route_det (rid, via) SELECT ?, ? WHERE NOT EXISTS "
        "(SELECT 1 FROM route_det WHERE rid = ? AND via = ?)",
        [(4, 'Alwar', 4, 'Alwar'), (5, 'Lonavala', 5, 'Lonavala'), (6, 'Vellore', 6, 'Vellore'), (10, 'Mathura', 10, 'Mathura'), (12, 'Ambala', 12, 'Ambala'), (23, 'Unnao', 23, 'Unnao')])
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Auth helpers (same pattern as the Airline project)
# ---------------------------------------------------------------------------
def current_user():
    if "user_id" not in session:
        return None
    return get_db().execute(
        "SELECT * FROM users WHERE id=?", (session["user_id"],)
    ).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Admin only.")
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapped


def next_code(db, table, column):
    row = db.execute(f"SELECT MAX({column}) AS m FROM {table}").fetchone()
    return (row["m"] or 0) + 1


# ---------------------------------------------------------------------------
# Layout (ALL CSS is inside this <style> tag)
# ---------------------------------------------------------------------------
LAYOUT = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TSN Ticket Booking - {{ title }}</title>
<style>
:root{--navy:#063B78;--blue:#0878D1;--light:#EAF5FF;--bg:#f4f8fc;--surface:#fff;
--ink:#12283e;--muted:#5d6f84;--line:#dbe7f3;--shadow:0 10px 30px rgba(6,59,120,.10)}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,'Segoe UI',Arial,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
header{background:var(--navy);color:#fff;position:sticky;top:0;z-index:10}
.topbar{max-width:1100px;margin:0 auto;padding:12px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.topbar a{color:#fff;text-decoration:none;font-weight:600}
.topbar a.cta{background:var(--blue);padding:7px 14px;border-radius:999px}
.brand{font-size:1.15rem;margin-right:auto}
.brand span{display:block;font-size:.75rem;font-weight:400;color:#cfe6fb}.nav-links{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.nav-links a{font-weight:700;font-size:.95rem;letter-spacing:.2px;padding:8px 12px;border-radius:10px}.nav-links a:hover{background:rgba(255,255,255,.16)}.nav-auth{display:flex;gap:6px;align-items:center;margin-left:auto;flex-wrap:wrap;padding-left:14px;border-left:1px solid rgba(255,255,255,.25)}.nav-auth a{font-weight:600;padding:8px 10px;border-radius:10px}.nav-auth a:hover{background:rgba(255,255,255,.16)}.topbar a.brand{font-weight:800}@media (max-width:600px){.nav-auth{margin-left:0;padding-left:0;border-left:0}}
main{max-width:1100px;margin:0 auto;padding:22px 20px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:var(--shadow);margin-bottom:18px}
.hero{background:linear-gradient(120deg,var(--navy),var(--blue) 55%,#5db2f0);color:#fff;border-radius:20px;padding:28px;margin-bottom:22px}
.hero h1{margin:0 0 6px}
.hero p{margin:0;color:#dbeeff}
table{width:100%;border-collapse:collapse}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--muted);font-size:.85rem;text-transform:uppercase}
label{display:block;margin:10px 0 4px;font-weight:600}
input,select{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:10px;font-size:1rem}
button,.btn{background:var(--blue);color:#fff;border:0;padding:10px 18px;border-radius:10px;font-size:1rem;cursor:pointer;text-decoration:none;display:inline-block}
button.secondary,.btn.secondary{background:#fff;color:var(--navy);border:1px solid var(--line)}
.flash{background:#fff3cd;border:1px solid #ffe08a;padding:10px 14px;border-radius:10px;margin-bottom:16px}
.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}
.stat b{font-size:1.8rem;color:var(--navy)}
@media (max-width:600px){main{padding-left:14px;padding-right:14px}}
.search-card{background:#fff;border-radius:16px;padding:18px;box-shadow:var(--shadow);margin-top:20px;color:var(--ink)}
.search-card label{margin:0}
.search-grid{display:grid;grid-template-columns:1.2fr 1.2fr 1fr 1fr auto;gap:12px;align-items:end}
.search-card .btn{height:44px;white-space:nowrap}
.trust{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:18px}
.trust .card{margin-bottom:0}
.route-card h3{margin:0 0 4px}
.route-card .fare{font-size:1.4rem;font-weight:700;color:var(--navy);margin:8px 0}
.footer{border-top:1px solid var(--line);background:#fff;border-radius:16px;margin-top:8px}
.footer-inner{padding:24px 20px;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:20px}
.footer h4{margin:0 0 8px;color:var(--navy)}
.footer a{color:var(--blue);text-decoration:none}
@media (max-width:700px){.search-grid{grid-template-columns:1fr 1fr}}
.route-info{border-left:4px solid var(--blue)}
.route-info p{margin:4px 0 0}
/* --- Premium polish: rhythm, depth, focus, motion, dark mode (overrides above) --- */
:root{--blue-dark:#0668b3;--accent:#4aa8ec;--shadow:0 12px 32px rgba(6,59,120,.12);--shadow-lg:0 20px 44px rgba(6,59,120,.16);--shadow-hover:0 18px 38px rgba(6,59,120,.18);--focus:0 0 0 3px rgba(8,120,209,.30);--ease:180ms ease}
main{padding:28px 20px}
h2{letter-spacing:-.01em;line-height:1.25}
main>h2{margin:26px 0 14px}
.card{padding:22px;margin-bottom:20px;transition:transform var(--ease),box-shadow var(--ease);animation:rise .5s ease both}
.card:hover{transform:translateY(-2px);box-shadow:var(--shadow-hover)}
.hero{background:linear-gradient(125deg,#04294f 0%,var(--navy) 32%,var(--blue) 64%,#63b6f2 100%);padding:34px 32px;margin-bottom:26px;box-shadow:var(--shadow-lg);animation:rise .5s ease both}
.hero h1{font-size:clamp(1.7rem,3vw,2.3rem);font-weight:800;letter-spacing:-.02em;line-height:1.15;margin:0 0 8px}
.hero p{font-size:1.05rem;line-height:1.55}
.eyebrow{font-size:.78rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--blue);margin:0 0 6px}
.hero .eyebrow{color:#bfe3ff;margin-bottom:10px}
button,.btn{padding:11px 20px;box-shadow:0 6px 16px rgba(8,120,209,.25);transition:transform var(--ease),box-shadow var(--ease),background var(--ease)}
button:hover,.btn:hover{transform:translateY(-1px);box-shadow:0 10px 22px rgba(8,120,209,.30);background:var(--blue-dark)}
button:active,.btn:active{transform:scale(.98);box-shadow:0 4px 10px rgba(8,120,209,.25)}
button.secondary:hover,.btn.secondary:hover{background:var(--light);box-shadow:0 8px 18px rgba(6,59,120,.14)}
.topbar a.cta{transition:transform var(--ease),background var(--ease),box-shadow var(--ease)}
.topbar a.cta:hover{background:var(--blue-dark);transform:translateY(-1px);box-shadow:0 8px 18px rgba(0,0,0,.25)}
.nav-links a,.nav-auth a{transition:background var(--ease),box-shadow var(--ease)}
.nav-links a:hover,.nav-auth a:hover{background:rgba(255,255,255,.18)}
.nav-links a.active,.nav-auth a.active{background:rgba(255,255,255,.22);box-shadow:inset 0 0 0 1px rgba(255,255,255,.28)}
input,select,textarea{padding:11px 13px;transition:border-color var(--ease),box-shadow var(--ease)}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--blue);box-shadow:var(--focus)}
button:focus-visible,.btn:focus-visible,a:focus-visible{outline:none;box-shadow:var(--focus)}
.topbar a:focus-visible{box-shadow:0 0 0 3px rgba(255,255,255,.5)}
.trust{gap:18px;margin-bottom:20px}
.grid{gap:18px}
.search-card{padding:22px;box-shadow:var(--shadow-lg)}
.search-card .btn{height:46px}
.footer{margin-top:12px}
.footer-inner{padding:28px 24px;gap:22px}
.route-card .fare{margin:10px 0}
th,td{padding:10px 12px}
@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
@media (prefers-color-scheme:dark){
:root{--bg:#0a1727;--surface:#12273f;--ink:#e9f2fb;--muted:#9db6cf;--line:#24405f;--light:#173452;--shadow:0 12px 32px rgba(0,0,0,.5);--shadow-lg:0 20px 44px rgba(0,0,0,.55);--shadow-hover:0 18px 38px rgba(0,0,0,.6);--focus:0 0 0 3px rgba(74,168,236,.45)}
header{background:#041f3d}
.hero{background:linear-gradient(125deg,#021a33 0%,#063B78 40%,#0a6cb8 75%,#2f8fd4 100%)}
.stat b,.route-card .fare,.footer h4{color:#8ec9f5}
.search-card,.footer{background:var(--surface)}
button.secondary,.btn.secondary{background:var(--surface);color:#dbeeff}
input,select,textarea{background:#0d1f36;color:var(--ink)}
.tabs button{background:var(--surface);color:#dbeeff}
.pill{background:var(--light);color:#bfe0fa}
.flash,.demo-note{background:#3a2e08;border-color:#6b5a1d;color:#ffe9a8}
button:hover,.btn:hover{box-shadow:0 10px 22px rgba(0,0,0,.5)}
button.secondary:hover,.btn.secondary:hover{background:var(--light)}
}
</style></head><body>
<header><div class="topbar">
<a class="brand" href="{{ url_for('home') }}">TSN Ticket Booking<span>Transport Service Network - Web Version</span></a>
<nav class="nav-links">
<a href="{{ url_for('home') }}">Home</a>
<a href="{{ url_for('masters_index') }}">Masters</a>
<a class="cta" href="{{ url_for('new_booking') }}">New Booking</a>
<a href="{{ url_for('bookings') }}">Bookings</a>
<a href="{{ url_for('reports') }}">Reports</a>
<a href="{{ url_for('train_info') }}">Train Info</a>
</nav>
<nav class="nav-auth">
{% if session.get('user_id') %}
<a href="{{ url_for('logout') }}">Logout ({{ session.get('user_name','') }})</a>
{% else %}
<a href="{{ url_for('login') }}">Login</a>
<a href="{{ url_for('register') }}">Register</a>
{% endif %}
</nav>
</div></header>
<main>
{% with messages = get_flashed_messages() %}
{% if messages %}<div class="flash">{{ messages|join('<br>')|safe }}</div>{% endif %}
{% endwith %}
{{ body|safe }}
</main></body></html>"""


def page(title, body, **ctx):
    return render_template_string(LAYOUT, title=title, body=body, **ctx)


def table_html(rows, cols):
    if not rows:
        return "<p>No records yet.</p>"
    head = "".join(f"<th>{c[1]}</th>" for c in cols)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(
            f"<td>{'' if r[c[0]] is None else r[c[0]]}</td>" for c in cols
        ) + "</tr>"
    return f"<table><tr>{head}</tr>{body}</table>"


def field(name, label, value="", type="text", required=True):
    req = " required" if required else ""
    return f'<label>{label}<input name="{name}" type="{type}" value="{value}"{req}></label>'


def select_field(name, label, options, selected=""):
    opts = "".join(
        f'<option value="{v}"{" selected" if str(v) == str(selected) else ""}>{t}</option>'
        for v, t in options
    )
    return f'<label>{label}<select name="{name}">{opts}</select></label>'


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    db = get_db()
    if request.method == "POST":
        f = request.form
        if not f["name"].strip() or not f["email"].strip() or not f["password"]:
            flash("Name, email and password are required.")
            return redirect(url_for("register"))
        if db.execute("SELECT id FROM users WHERE email=?", (f["email"].strip(),)).fetchone():
            flash("That email is already registered. Please log in.")
            return redirect(url_for("login"))
        db.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?,?,?,?)",
            (f["name"].strip(), f["email"].strip(),
             generate_password_hash(f["password"]), "customer"),
        )
        db.commit()
        flash("Account created. Please log in.")
        return redirect(url_for("login"))
    body = """<div class="card"><h2>Create your account</h2><form method="post">
    """ + field("name", "Full name") + field("email", "Email", type="email") + \
        field("password", "Password", type="password") + """
    <p><button>Sign Up</button></p>
    <p class="muted">Already have an account? <a href="/login">Log in</a></p>
    </form></div>"""
    return page("Sign Up", body)


@app.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    if request.method == "POST":
        f = request.form
        user = db.execute(
            "SELECT * FROM users WHERE email=?", (f["email"].strip(),)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], f["password"]):
            # Owner email auto-upgrades to admin on login (same as Airline).
            if user["email"] == OWNER_EMAIL and user["role"] != "admin":
                db.execute("UPDATE users SET role='admin' WHERE id=?", (user["id"],))
                db.commit()
                user = db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["role"] = user["role"]
            flash(f"Welcome, {user['name']} ({user['role']}).")
            return redirect(url_for("home"))
        flash("Invalid email or password.")
        return redirect(url_for("login"))
    body = """<div class="card"><h2>Welcome back</h2><form method="post">
    """ + field("email", "Email", type="email") + field("password", "Password", type="password") + """
    <p><button>Log In</button></p>
    <p class="muted">No account yet? <a href="/register">Sign up</a></p>
    </form></div>"""
    return page("Log In", body)


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("home"))


# ---------------------------------------------------------------------------
# Shared footer (shown on the home and search pages only, so other pages
# keep their existing layout exactly)
# ---------------------------------------------------------------------------
FOOTER = """<div class="footer"><div class="footer-inner">
<div><h4>Help</h4><p><a href="/masters">Masters</a> &middot; <a href="/booking/new">New Booking</a> &middot; <a href="/reports">Reports</a></p>
<p class="muted">Fare rule: ticket total = seats &times; the transport's major (r_major) rate.</p></div>
<div><h4>About</h4><p class="muted">TSN Ticket Booking &mdash; a transport ticket booking
system, here as a cross-platform web app with a saved SQLite database.</p></div>
<div><h4>Contact</h4><p><a href="https://github.com/rishabh4630/Ticket-Booking-Platform">GitHub repository</a></p></div>
</div></div>"""


def search_card(cities, types, selected=None):
    selected = selected or {}
    from_opts = '<option value="">Anywhere</option>' + "".join(
        f'<option value="{c["city_name"]}"{" selected" if selected.get("from") == c["city_name"] else ""}>{c["city_name"]}</option>'
        for c in cities
    )
    to_opts = '<option value="">Anywhere</option>' + "".join(
        f'<option value="{c["city_name"]}"{" selected" if selected.get("to") == c["city_name"] else ""}>{c["city_name"]}</option>'
        for c in cities
    )
    type_opts = '<option value="">Any type</option>' + "".join(
        f'<option value="{t["ttid"]}"{" selected" if str(selected.get("type", "")) == str(t["ttid"]) else ""}>{t["ttname"]}</option>'
        for t in types
    )
    date_val = selected.get("date", "")
    return f"""<div class="search-card"><form method="get" action="/search">
    <div class="search-grid">
    <label>From<select name="from">{from_opts}</select></label>
    <label>To<select name="to">{to_opts}</select></label>
    <label>Date<input name="date" type="date" value="{date_val}"></label>
    <label>Transport Type<select name="type">{type_opts}</select></label>
    <p style="margin:0"><button class="btn">Search</button></p>
    </div></form></div>"""


# ---------------------------------------------------------------------------
# Home / Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    db = get_db()
    counts = {
        "Transports": db.execute("SELECT COUNT(*) FROM transports").fetchone()[0],
        "Routes": db.execute("SELECT COUNT(*) FROM routes").fetchone()[0],
        "Customers": db.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "Bookings": db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0],
    }
    recent = db.execute(
        """SELECT b.book_no, b.book_date, b.cust_name, t.tname, b.tid
           FROM bookings b JOIN transports t ON t.tid = b.tid
           ORDER BY b.book_no DESC LIMIT 5"""
    ).fetchall()
    cities = db.execute("SELECT * FROM cities ORDER BY city_name").fetchall()
    types = db.execute("SELECT * FROM transport_types ORDER BY ttid").fetchall()
    # Popular Routes on home: first 9 routes only (originals + trunk
    # corridors). All routes stay searchable and visible under Masters.
    routes = db.execute("SELECT * FROM routes ORDER BY rid LIMIT 9").fetchall()
    all_transports = db.execute("SELECT * FROM transports").fetchall()
    route_cards = ""
    for r in routes:
        on_route = [t for t in all_transports if t["rid"] == r["rid"]]
        if not on_route:
            continue
        cheapest = min(on_route, key=lambda t: t["r_major"])
        via = db.execute(
            "SELECT via FROM route_det WHERE rid=? ORDER BY id", (r["rid"],)
        ).fetchall()
        via_text = ", ".join(v["via"] for v in via)
        route_cards += f"""<div class="card route-card"><h3>{r["st_pos"]} &rarr; {r["dest"]}</h3>
        <p class="muted">{r["r_name"]}{" &middot; Via: " + via_text if via_text else ""}</p>
        <p class="fare">From Rs. {cheapest["r_major"]} per seat</p>
        <p><a class="btn" href="/booking/new?tid={cheapest["tid"]}">Book</a>
        <a class="btn secondary" href="/search?from={r["st_pos"]}&to={r["dest"]}">View Transports</a></p></div>"""
    stats = "".join(
        f'<div class="card stat"><div class="muted">{k}</div><b>{v}</b></div>'
        for k, v in counts.items()
    )
    body = f"""<div class="hero"><p class="eyebrow">Bus &amp; Train Booking</p><h1>Your journey begins here.</h1>
    <p>Book bus and train tickets across the network &mdash; transparent fares,
    seats of your choice, and instant cancellation.</p>
    {search_card(cities, types)}</div>
    <div class="trust">
    <div class="card"><h3>&#10003; Transparent fares</h3><p class="muted">What you see is what you pay: total = seats &times; the transport's major (r_major) rate. No hidden charges.</p></div>
    <div class="card"><h3>&#10003; Seat of your choice</h3><p class="muted">Pick your own seat numbers. A seat already booked for the same transport and date can never be sold twice.</p></div>
    <div class="card"><h3>&#10003; Instant cancellation</h3><p class="muted">Cancel any booking and its seats are freed immediately for other travellers.</p></div>
    </div>
    <div class="grid">{stats}</div>
    <div class="card"><h2>Recent bookings</h2>
    {table_html(recent, [('book_no', 'Booking No'), ('book_date', 'Date'),
                          ('cust_name', 'Customer'), ('tname', 'Transport')])}
    <p><a class="btn" href="/booking/new">New Booking</a>
    <a class="btn secondary" href="/masters">Manage Masters</a></p></div>
    <h2>Popular Routes</h2>
    <div class="grid">{route_cards or "<p>No routes yet.</p>"}</div>
    <div class="card"><h2>Why TSN</h2>
    <ul>
    <li><b>Complete masters</b> &mdash; transport types, transports, routes with via stops, payment modes and customers, all in one place.</li>
    <li><b>Reports for all six areas</b> &mdash; the original R1&ndash;R6 reports as plain tables (admin only).</li>
    <li><b>Login-protected booking</b> &mdash; you see and cancel only your own bookings; admins see everything.</li>
    </ul>
    <p class="muted">The original project is VB.NET WinForms + Oracle. This web
    version keeps the same masters, transactions and reports on SQLite.
    Seed data is demo data.</p></div>
    {FOOTER}"""
    return page("Home", body)


@app.route("/search")
def search():
    db = get_db()
    from_city = request.args.get("from", "").strip()
    to_city = request.args.get("to", "").strip()
    travel_date = request.args.get("date", "").strip()
    type_id = request.args.get("type", "").strip()
    cities = db.execute("SELECT * FROM cities ORDER BY city_name").fetchall()
    types = db.execute("SELECT * FROM transport_types ORDER BY ttid").fetchall()
    sql = """SELECT t.*, tt.ttname FROM transports t
             LEFT JOIN transport_types tt ON tt.ttid = t.ttid WHERE 1=1"""
    params = []
    if from_city:
        sql += " AND t.st_pos = ?"
        params.append(from_city)
    if to_city:
        sql += " AND t.dest = ?"
        params.append(to_city)
    if type_id:
        sql += " AND t.ttid = ?"
        params.append(type_id)
    sql += " ORDER BY t.r_major"
    rows = db.execute(sql, params).fetchall()
    cards = ""
    for t in rows:
        if travel_date:
            taken = len(booked_seats(db, t["tid"], travel_date))
            seats_left = t["capacity"] - taken
            seats_text = f"{seats_left} seat(s) left on {travel_date}"
        else:
            seats_text = f"Capacity {t['capacity']} seats"
        book_url = f"/booking/new?tid={t['tid']}"
        if travel_date:
            book_url += f"&date={travel_date}"
        cards += f"""<div class="card"><h3>{t["tname"]}</h3>
        <p>{t["st_pos"]} &rarr; {t["dest"]} &middot; {t["st_time"]} &ndash; {t["reach_time"]} &middot; {t["ttname"] or "Transport"}</p>
        <p><b>Rs. {t["r_major"]} per seat</b> &middot; {seats_text}</p>
        <p><a class="btn" href="{book_url}">Book</a></p></div>"""
    if not cards:
        cards = """<div class="card"><h3>No transport on this route.</h3>
        <p class="muted">No transport matches this search. Try different cities,
        any transport type, or browse the <a href="/masters/transports">Transports</a> list.</p></div>"""
    selected = {"from": from_city, "to": to_city, "date": travel_date, "type": type_id}
    # Route info strip (free OSRM + Open-Meteo data). External failures only
    # hide pieces of the strip -- the results below always still render.
    strip = ""
    if from_city and to_city:
        info = route_info(from_city, to_city)
        if info:
            parts = []
            if "distance" in info:
                parts.append(f"Road distance: {info['distance']}")
            if "duration" in info:
                parts.append(f"Driving time: {info['duration']}")
            if "weather" in info:
                parts.append(f"{html.escape(to_city)} ka mausam: {html.escape(info['weather'])}")
            strip = ('<div class="card route-info"><p><b>Route info:</b> '
                     + " &middot; ".join(parts) + "</p>"
                     '<p class="muted">Live data: OSRM (road route) / Open-Meteo (weather). '
                     "Ye sirf jaankari hai — booking ke liye neeche wale transports use karo.</p></div>")
        else:
            strip = ('<div class="card route-info"><p class="muted">Route/weather info '
                     "uplabdh nahi hai (live service se data nahi mila). "
                     "Search results neeche hain.</p></div>")
    body = f"""<div class="hero"><h1>Search Transports</h1>
    <p>Find a transport for your route and book in a few clicks.</p>
    {search_card(cities, types, selected)}</div>
    <h2>Results</h2>
    {strip}
    {cards}
    {FOOTER}"""
    return page("Search Transports", body)


# ---------------------------------------------------------------------------
# Masters
# ---------------------------------------------------------------------------
MASTER_KINDS = [
    ("transport_types", "Transport Types"),
    ("transports", "Transports"),
    ("routes", "Routes"),
    ("payments", "Payment Modes"),
    ("customers", "Customers"),
    ("streets", "Streets"),
    ("cities", "Cities"),
    ("states", "States"),
]

MASTER_TABLES = {
    "transport_types": ("SELECT * FROM transport_types ORDER BY ttid",
                        [("ttid", "ID"), ("ttname", "Name"), ("tdesc", "Description")]),
    "transports": ("""SELECT t.*, tt.ttname FROM transports t
                      LEFT JOIN transport_types tt ON tt.ttid = t.ttid ORDER BY t.tid""",
                   [("tid", "ID"), ("tname", "Name"), ("capacity", "Capacity"),
                    ("r_minor", "Minor Rate"), ("r_major", "Major Rate"),
                    ("st_pos", "From"), ("dest", "To"), ("st_time", "Departs"),
                    ("reach_time", "Arrives"), ("ttname", "Type")]),
    "routes": ("SELECT * FROM routes ORDER BY rid",
               [("rid", "ID"), ("r_name", "Route"), ("st_pos", "From"), ("dest", "To")]),
    "payments": ("SELECT * FROM payments ORDER BY pmid",
                 [("pmid", "ID"), ("pname", "Mode"), ("amt", "Amount"), ("p_desc", "Description")]),
    "customers": ("""SELECT c.cust_code, d.cust_name, d.age, d.sex, c.cust_add, c.cust_phone
                     FROM customers c LEFT JOIN cust_det d ON d.cust_code = c.cust_code
                     ORDER BY c.cust_code""",
                  [("cust_code", "Code"), ("cust_name", "Name"), ("age", "Age"),
                   ("sex", "Sex"), ("cust_add", "Address"), ("cust_phone", "Phone")]),
    "streets": ("SELECT * FROM streets ORDER BY st_code",
                [("st_code", "Code"), ("st_name", "Street"), ("p_code", "PIN")]),
    "cities": ("SELECT * FROM cities ORDER BY city_code",
               [("city_code", "Code"), ("city_name", "City")]),
    "states": ("SELECT * FROM states ORDER BY state_code",
               [("state_code", "Code"), ("state_name", "State")]),
}


@app.route("/masters")
def masters_index():
    links = "".join(
        f'<div class="card"><h3>{title}</h3>'
        f'<p><a class="btn" href="/masters/{kind}">View</a></p></div>'
        for kind, title in MASTER_KINDS
    )
    return page("Masters", f"<h2>Masters</h2><div class='grid'>{links}</div>")


@app.route("/masters/<kind>")
def masters_list(kind):
    if kind not in MASTER_TABLES:
        return page("Not found", "<p>Unknown master.</p>"), 404
    db = get_db()
    sql, cols = MASTER_TABLES[kind]
    rows = db.execute(sql).fetchall()
    extra = ""
    if kind == "routes":
        stops = db.execute(
            "SELECT rid, GROUP_CONCAT(via, ', ') AS stops FROM route_det GROUP BY rid"
        ).fetchall()
        stopmap = {r["rid"]: r["stops"] for r in stops}
        extra = "<div class='card'><h3>Via stops</h3><p class='muted'>" + "<br>".join(
            f"Route {rid}: {stops}" for rid, stops in stopmap.items()
        ) + "</p></div>" if stopmap else ""
    admin_link = ""
    if session.get("role") == "admin":
        admin_link = f'<p><a class="btn" href="/masters/{kind}/new">Add New</a></p>'
    title = dict(MASTER_KINDS)[kind]
    return page(title, f"<div class='card'><h2>{title}</h2>{table_html(rows, cols)}{admin_link}</div>{extra}")


@app.route("/masters/<kind>/new", methods=["GET", "POST"])
@admin_required
def masters_new(kind):
    if kind not in MASTER_TABLES:
        return page("Not found", "<p>Unknown master.</p>"), 404
    db = get_db()
    title = dict(MASTER_KINDS)[kind]
    if request.method == "POST":
        f = request.form
        try:
            if kind == "transport_types":
                code = next_code(db, "transport_types", "ttid")
                db.execute("INSERT INTO transport_types VALUES (?,?,?)",
                           (code, f["ttname"].strip(), f["tdesc"].strip()))
            elif kind == "states":
                code = next_code(db, "states", "state_code")
                db.execute("INSERT INTO states VALUES (?,?)", (code, f["state_name"].strip()))
            elif kind == "cities":
                code = next_code(db, "cities", "city_code")
                db.execute("INSERT INTO cities VALUES (?,?)", (code, f["city_name"].strip()))
            elif kind == "streets":
                code = next_code(db, "streets", "st_code")
                db.execute("INSERT INTO streets VALUES (?,?,?)",
                           (code, f["st_name"].strip(), f["p_code"].strip()))
            elif kind == "payments":
                code = next_code(db, "payments", "pmid")
                db.execute("INSERT INTO payments VALUES (?,?,?,?)",
                           (code, f["pname"].strip(), int(f["amt"] or 0), f["p_desc"].strip()))
                if f.get("ch_no", "").strip():
                    db.execute("INSERT INTO payment_det (pmid, ch_no, ch_date, dsc) VALUES (?,?,?,?)",
                               (code, f["ch_no"].strip(), f["ch_date"].strip(), f["ch_dsc"].strip()))
            elif kind == "routes":
                code = next_code(db, "routes", "rid")
                db.execute("INSERT INTO routes VALUES (?,?,?,?)",
                           (code, f["r_name"].strip(), f["st_pos"].strip(), f["dest"].strip()))
                for via in [v.strip() for v in f["via"].split(",") if v.strip()]:
                    db.execute("INSERT INTO route_det (rid, via) VALUES (?,?)", (code, via))
            elif kind == "transports":
                code = next_code(db, "transports", "tid")
                db.execute("INSERT INTO transports VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                           (code, f["tname"].strip(), int(f["capacity"] or 0),
                            int(f["r_minor"] or 0), int(f["r_major"] or 0),
                            f["r_uom"].strip() or "per seat", f["st_pos"].strip(),
                            f["dest"].strip(), f["st_time"].strip(),
                            f["reach_time"].strip(),
                            int(f["ttid"]) if f["ttid"] else None,
                            int(f["rid"]) if f["rid"] else None))
            elif kind == "customers":
                code = next_code(db, "customers", "cust_code")
                db.execute("INSERT INTO customers VALUES (?,?,?,?,?,?)",
                           (code, f["cust_add"].strip(),
                            int(f["st_code"]) if f["st_code"] else None,
                            int(f["city_code"]) if f["city_code"] else None,
                            int(f["state_code"]) if f["state_code"] else None,
                            f["cust_phone"].strip()))
                db.execute("INSERT INTO cust_det (cust_code, cust_name, age, sex) VALUES (?,?,?,?)",
                           (code, f["cust_name"].strip(), int(f["age"] or 0), f["sex"].strip()))
            db.commit()
        except (ValueError, KeyError):
            flash("Please check the form values and try again.")
            return redirect(url_for("masters_new", kind=kind))
        flash(f"{title} added.")
        return redirect(url_for("masters_list", kind=kind))

    types = db.execute("SELECT ttid, ttname FROM transport_types ORDER BY ttid").fetchall()
    routes = db.execute("SELECT rid, r_name FROM routes ORDER BY rid").fetchall()
    streets = db.execute("SELECT st_code, st_name FROM streets ORDER BY st_code").fetchall()
    cities = db.execute("SELECT city_code, city_name FROM cities ORDER BY city_code").fetchall()
    states = db.execute("SELECT state_code, state_name FROM states ORDER BY state_code").fetchall()
    forms = {
        "transport_types": field("ttname", "Type name") + field("tdesc", "Description", required=False),
        "states": field("state_name", "State name"),
        "cities": field("city_name", "City name"),
        "streets": field("st_name", "Street name") + field("p_code", "PIN code", required=False),
        "payments": field("pname", "Payment mode") + field("amt", "Amount", type="number") +
                    field("p_desc", "Description", required=False) +
                    field("ch_no", "Cheque no. (optional)", required=False) +
                    field("ch_date", "Cheque date (optional)", type="date", required=False) +
                    field("ch_dsc", "Cheque note (optional)", required=False),
        "routes": field("r_name", "Route name") + field("st_pos", "Starting point") +
                  field("dest", "Destination") +
                  field("via", "Via stops (comma-separated, optional)", required=False),
        "transports": field("tname", "Transport name") + field("capacity", "Capacity", type="number") +
                      field("r_minor", "Minor rate", type="number") +
                      field("r_major", "Major rate (per seat)", type="number") +
                      field("r_uom", "Rate unit", value="per seat", required=False) +
                      field("st_pos", "Starting point") + field("dest", "Destination") +
                      field("st_time", "Departure time") + field("reach_time", "Arrival time") +
                      select_field("ttid", "Transport type",
                                   [(r["ttid"], r["ttname"]) for r in types]) +
                      select_field("rid", "Route",
                                   [(r["rid"], r["r_name"]) for r in routes]),
        "customers": field("cust_name", "Customer name") + field("age", "Age", type="number") +
                     field("sex", "Sex", required=False) + field("cust_add", "Address", required=False) +
                     field("cust_phone", "Phone", required=False) +
                     select_field("st_code", "Street",
                                  [("", "—")] + [(r["st_code"], r["st_name"]) for r in streets]) +
                     select_field("city_code", "City",
                                  [("", "—")] + [(r["city_code"], r["city_name"]) for r in cities]) +
                     select_field("state_code", "State",
                                  [("", "—")] + [(r["state_code"], r["state_name"]) for r in states]),
    }
    pin_block = ""
    if kind == "customers":
        # PIN lookup helper (not a submitted field: it has no name attribute).
        # On a 6-digit PIN it calls keyless SearchPinCode and, when the
        # returned District/State match a city/state option, selects them.
        # Any failure only shows a note -- the form keeps working by hand.
        pin_block = """<div><label>PIN code (city/state auto-fill ke liye)<input id="pinLookup" inputmode="numeric" maxlength="6" placeholder="e.g. 226001"></label><p class="muted" id="pinSuggest"></p></div>
    <script>
    document.getElementById('pinLookup').addEventListener('input', function () {
      var pin = this.value.replace(/\\D/g, '').slice(0, 6);
      this.value = pin;
      var note = document.getElementById('pinSuggest');
      if (pin.length !== 6) { note.textContent = ''; return; }
      note.textContent = 'PIN dhoondha ja raha hai...';
      fetch('https://searchpincode.in/api/pincode/' + pin)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          // Real shape: [{Status, PostOffice: [{Name, District, State, ...}]}]
          var list = data;
          if (data && data.length && data[0].PostOffice) list = data[0].PostOffice;
          if (!list || !list.length) { note.textContent = 'Is PIN ke liye koi post office nahi mila.'; return; }
          var po = list[0];
          note.textContent = 'Suggestion: ' + po.Name + ', ' + po.District + ', ' + po.State + ' — city/state neeche match hone par auto-select ho gaye hain.';
          var citySel = document.querySelector('select[name=city_code]');
          var stateSel = document.querySelector('select[name=state_code]');
          function pick(sel, wanted) {
            if (!sel) return;
            for (var i = 0; i < sel.options.length; i++) {
              if (sel.options[i].text.trim().toLowerCase() === String(wanted).toLowerCase()) { sel.selectedIndex = i; break; }
            }
          }
          pick(citySel, po.District);
          pick(stateSel, po.State);
        })
        .catch(function () { note.textContent = 'PIN lookup uplabdh nahi hai, aap city/state haath se chun sakte hain.'; });
    });
    </script>"""
    body = f"""<div class="card"><h2>Add {title}</h2><form method="post">
    {forms[kind]}{pin_block}<p><button>Save</button></p></form></div>"""
    return page(f"Add {title}", body)


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------
def parse_seats(raw):
    seats = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        seats.append(int(part))
    return seats


def booked_seats(db, tid, travel_date):
    rows = db.execute(
        """SELECT bs.seat_no FROM booking_seats bs
           JOIN bookings b ON b.book_no = bs.book_no
           WHERE b.tid = ? AND b.book_date = ?""",
        (tid, travel_date),
    ).fetchall()
    return {r["seat_no"] for r in rows}


@app.route("/booking/new", methods=["GET", "POST"])
@login_required
def new_booking():
    db = get_db()
    transports = db.execute("SELECT * FROM transports ORDER BY tid").fetchall()
    customers = db.execute(
        """SELECT c.cust_code, d.cust_name FROM customers c
           LEFT JOIN cust_det d ON d.cust_code = c.cust_code ORDER BY c.cust_code"""
    ).fetchall()
    payments = db.execute("SELECT * FROM payments ORDER BY pmid").fetchall()
    if request.method == "POST":
        f = request.form
        try:
            tid = int(f["tid"])
            cust_code = int(f["cust_code"])
            pmode_id = int(f["pmode_id"]) if f["pmode_id"] else None
            seats = parse_seats(f["seats"])
            travel_date = f["book_date"].strip()
        except (ValueError, KeyError):
            flash("Please check the form values (seat numbers must be numbers).")
            return redirect(url_for("new_booking"))
        transport = db.execute("SELECT * FROM transports WHERE tid=?", (tid,)).fetchone()
        cust = db.execute(
            "SELECT cust_name FROM cust_det WHERE cust_code=? ORDER BY id LIMIT 1",
            (cust_code,),
        ).fetchone()
        if not transport or not cust or not travel_date or not seats:
            flash("Transport, customer, date and at least one seat are required.")
            return redirect(url_for("new_booking"))
        if len(set(seats)) != len(seats) or any(s <= 0 for s in seats):
            flash("Seat numbers must be positive and not repeated in one booking.")
            return redirect(url_for("new_booking"))
        taken = booked_seats(db, tid, travel_date)
        clash = sorted(set(seats) & taken)
        if clash:
            flash(f"Seat(s) already booked for this transport and date: {', '.join(map(str, clash))}.")
            return redirect(url_for("new_booking"))
        if len(taken) + len(seats) > transport["capacity"]:
            flash(f"Over capacity: {len(taken)} seat(s) already booked, "
                  f"capacity is {transport['capacity']}, so only "
                  f"{transport['capacity'] - len(taken)} more seat(s) are available.")
            return redirect(url_for("new_booking"))
        book_no = next_code(db, "bookings", "book_no")
        db.execute(
            "INSERT INTO bookings VALUES (?,?,?,?,?,?,?)",
            (book_no, travel_date, cust_code, cust["cust_name"], tid, pmode_id,
             session["user_id"]),
        )
        for seat in seats:
            db.execute("INSERT INTO booking_seats VALUES (?,?)", (book_no, seat))
        db.commit()
        total = len(seats) * transport["r_major"]
        flash(f"Booking created. Booking No: {book_no} - Seats: {', '.join(map(str, sorted(seats)))} - Total: Rs. {total}.")
        return redirect(url_for("ticket", book_no=book_no))

    # Preselect from search / popular-route links: ?tid=<id>&date=<YYYY-MM-DD>.
    # Values are validated here so query strings cannot inject HTML.
    try:
        pre_tid = int(request.args.get("tid", ""))
    except (TypeError, ValueError):
        pre_tid = None
    pre_date = request.args.get("date", "")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", pre_date or ""):
        pre_date = ""
    transport_opts = "".join(
        f'<option value="{t["tid"]}"{" selected" if pre_tid == t["tid"] else ""} data-rate="{t["r_major"]}">{t["tname"]} '
        f'({t["st_pos"]} to {t["dest"]}, {t["st_time"]}) - Rs. {t["r_major"]} per seat, '
        f'capacity {t["capacity"]}</option>'
        for t in transports
    )
    body = f"""<div class="card"><h2>New Booking</h2><form method="post" id="bookForm">
    <label>Transport<select name="tid" id="tidSel">{transport_opts}</select></label>
    {select_field("cust_code", "Customer", [(c["cust_code"], c["cust_name"] or f'Customer {c["cust_code"]}') for c in customers])}
    <label>Travel date<input name="book_date" type="date" required value="{pre_date}"></label>
    {select_field("pmode_id", "Payment mode", [(p["pmid"], p["pname"]) for p in payments])}
    <label>Seat numbers (comma-separated, e.g. 1, 2, 3)<input name="seats" required placeholder="1, 2"></label>
    <p class="muted" id="totalLine">Fare rule: total = seats x the transport's major (r_major) rate.</p>
    <p><button>Book Tickets</button></p></form></div>
    <script>
    function updTotal(){{
      var sel = document.getElementById('tidSel');
      var rate = parseInt(sel.options[sel.selectedIndex].dataset.rate || '0', 10);
      var n = document.querySelector('input[name=seats]').value.split(',').filter(function(s){{ return s.trim() !== ''; }}).length;
      document.getElementById('totalLine').textContent = 'Fare: ' + n + ' seat(s) x Rs. ' + rate + ' = Rs. ' + (n * rate) + '.';
    }}
    document.getElementById('tidSel').addEventListener('change', updTotal);
    document.querySelector('input[name=seats]').addEventListener('input', updTotal);
    updTotal();
    </script>"""
    return page("New Booking", body)


@app.route("/bookings")
@login_required
def bookings():
    db = get_db()
    if session.get("role") == "admin":
        rows = db.execute(
            """SELECT b.*, t.tname FROM bookings b
               JOIN transports t ON t.tid = b.tid ORDER BY b.book_no DESC"""
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT b.*, t.tname FROM bookings b
               JOIN transports t ON t.tid = b.tid
               WHERE b.user_id = ? ORDER BY b.book_no DESC""",
            (session["user_id"],),
        ).fetchall()
    cards = ""
    for r in rows:
        seats = db.execute(
            "SELECT seat_no FROM booking_seats WHERE book_no=? ORDER BY seat_no",
            (r["book_no"],),
        ).fetchall()
        seat_list = ", ".join(str(s["seat_no"]) for s in seats)
        cards += (f'<div class="card"><h3>Booking {r["book_no"]} - {r["tname"]}</h3>'
                  f'<p>{r["book_date"]} | {r["cust_name"]} | Seats: {seat_list}</p>'
                  f'<p><a class="btn" href="/booking/{r["book_no"]}">View Ticket</a> '
                  f'<a class="btn secondary" href="/booking/{r["book_no"]}/cancel">Cancel</a></p></div>')
    return page("Bookings", f"<h2>Bookings</h2>{cards or '<p>No bookings yet.</p>'}")


def load_booking_or_404(db, book_no):
    row = db.execute("SELECT * FROM bookings WHERE book_no=?", (book_no,)).fetchone()
    if not row:
        return None
    if session.get("role") != "admin" and row["user_id"] != session.get("user_id"):
        return "forbidden"
    return row


@app.route("/booking/<int:book_no>")
@login_required
def ticket(book_no):
    db = get_db()
    booking = load_booking_or_404(db, book_no)
    if booking is None:
        return page("Not found", "<p>Booking not found.</p>"), 404
    if booking == "forbidden":
        flash("You can only view your own bookings.")
        return redirect(url_for("bookings"))
    transport = db.execute("SELECT * FROM transports WHERE tid=?", (booking["tid"],)).fetchone()
    payment = db.execute("SELECT * FROM payments WHERE pmid=?", (booking["pmode_id"],)).fetchone() if booking["pmode_id"] else None
    seats = db.execute(
        "SELECT seat_no FROM booking_seats WHERE book_no=? ORDER BY seat_no", (book_no,)
    ).fetchall()
    seat_list = ", ".join(str(s["seat_no"]) for s in seats)
    total = len(seats) * transport["r_major"]
    body = f"""<div class="card"><h2>Ticket - Booking {book_no}</h2>
    <table>
    <tr><th>Customer</th><td>{booking["cust_name"]}</td></tr>
    <tr><th>Transport</th><td>{transport["tname"]} ({transport["st_pos"]} to {transport["dest"]})</td></tr>
    <tr><th>Departure / Arrival</th><td>{transport["st_time"]} / {transport["reach_time"]}</td></tr>
    <tr><th>Travel date</th><td>{booking["book_date"]}</td></tr>
    <tr><th>Seats</th><td>{seat_list}</td></tr>
    <tr><th>Rate per seat (r_major)</th><td>Rs. {transport["r_major"]}</td></tr>
    <tr><th>Total fare</th><td><b>Rs. {total}</b> ({len(seats)} seat(s) x Rs. {transport["r_major"]})</td></tr>
    <tr><th>Payment mode</th><td>{payment["pname"] if payment else "-"}</td></tr>
    </table>
    <p><a class="btn secondary" href="/booking/{book_no}/cancel">Cancel Booking</a>
    <a class="btn secondary" href="/bookings">All Bookings</a></p></div>"""
    return page(f"Ticket {book_no}", body)


@app.route("/booking/<int:book_no>/cancel", methods=["GET", "POST"])
@login_required
def cancel_booking(book_no):
    db = get_db()
    booking = load_booking_or_404(db, book_no)
    if booking is None:
        return page("Not found", "<p>Booking not found.</p>"), 404
    if booking == "forbidden":
        flash("You can only cancel your own bookings.")
        return redirect(url_for("bookings"))
    if request.method == "POST":
        db.execute("DELETE FROM booking_seats WHERE book_no=?", (book_no,))
        db.execute("DELETE FROM bookings WHERE book_no=?", (book_no,))
        db.commit()
        flash(f"Booking {book_no} cancelled. Its seats are free again.")
        return redirect(url_for("bookings"))
    body = f"""<div class="card"><h2>Cancel Booking {book_no}?</h2>
    <p>{booking["cust_name"]} - {booking["book_date"]}. This frees the booked seats.</p>
    <form method="post"><p><button>Yes, Cancel Booking</button>
    <a class="btn secondary" href="/booking/{book_no}">Keep Booking</a></p></form></div>"""
    return page("Cancel Booking", body)


# ---------------------------------------------------------------------------
# Reports (admin only) - the six original report areas
# ---------------------------------------------------------------------------
@app.route("/reports")
@admin_required
def reports():
    db = get_db()
    sections = []
    sections.append(("1 - Transport Type Master",
                     db.execute("SELECT * FROM transport_types ORDER BY ttid").fetchall(),
                     [("ttid", "ID"), ("ttname", "Name"), ("tdesc", "Description")]))
    sections.append(("2 - Transport Master",
                     db.execute("SELECT * FROM transports ORDER BY tid").fetchall(),
                     [("tid", "ID"), ("tname", "Name"), ("capacity", "Capacity"),
                      ("r_major", "Major Rate"), ("st_pos", "From"), ("dest", "To")]))
    sections.append(("3 - Transport Transactions (Bookings)",
                     db.execute("""SELECT b.book_no, b.book_date, b.cust_name, t.tname,
                                   (SELECT COUNT(*) FROM booking_seats s WHERE s.book_no = b.book_no) AS seats
                                   FROM bookings b JOIN transports t ON t.tid = b.tid
                                   ORDER BY b.book_no""").fetchall(),
                     [("book_no", "Booking No"), ("book_date", "Date"),
                      ("cust_name", "Customer"), ("tname", "Transport"), ("seats", "Seats")]))
    sections.append(("4 - Payment Transactions",
                     db.execute("""SELECT b.book_no, b.book_date, b.cust_name, p.pname
                                   FROM bookings b LEFT JOIN payments p ON p.pmid = b.pmode_id
                                   ORDER BY b.book_no""").fetchall(),
                     [("book_no", "Booking No"), ("book_date", "Date"),
                      ("cust_name", "Customer"), ("pname", "Payment Mode")]))
    sections.append(("5 - Customer Transactions",
                     db.execute("""SELECT c.cust_code, d.cust_name, b.book_no, b.book_date
                                   FROM customers c LEFT JOIN cust_det d ON d.cust_code = c.cust_code
                                   LEFT JOIN bookings b ON b.cust_id = c.cust_code
                                   ORDER BY c.cust_code, b.book_no""").fetchall(),
                     [("cust_code", "Code"), ("cust_name", "Customer"),
                      ("book_no", "Booking No"), ("book_date", "Date")]))
    sections.append(("6 - Route Transactions",
                     db.execute("""SELECT r.r_name, r.st_pos, r.dest, t.tname, b.book_no
                                   FROM routes r JOIN transports t ON t.rid = r.rid
                                   LEFT JOIN bookings b ON b.tid = t.tid
                                   ORDER BY r.rid, b.book_no""").fetchall(),
                     [("r_name", "Route"), ("st_pos", "From"), ("dest", "To"),
                      ("tname", "Transport"), ("book_no", "Booking No")]))
    body = "<h2>Reports (Admin)</h2>" + "".join(
        f"<div class='card'><h3>{title}</h3>{table_html(rows, cols)}</div>"
        for title, rows, cols in sections
    )
    return page("Reports", body)


# ---------------------------------------------------------------------------
# Train Info (Flask only) - live Indian train data via RapidAPI, server-side
# ---------------------------------------------------------------------------
@app.route("/train-info", methods=["GET", "POST"])
def train_info():
    key_set = bool(os.environ.get("RAPIDAPI_KEY", ""))
    result = ""
    if request.method == "POST":
        kind = request.form.get("form_kind", "")
        if not key_set:
            result = train_setup_card()
        elif kind == "pnr":
            pnr = request.form.get("pnr", "").strip()
            if not re.match(r"^\d{10}$", pnr):
                result = '<div class="card"><p>PNR 10 digits ka hona chahiye.</p></div>'
            else:
                data, err = rapidapi_get(TRAIN_API_ENDPOINTS["pnr"], {"pnr": pnr})
                result = train_result_html("PNR status", data, err)
        elif kind == "between":
            frm = request.form.get("from_station", "").strip().upper()
            to = request.form.get("to_station", "").strip().upper()
            travel_date = request.form.get("travel_date", "").strip()
            if not frm or not to:
                result = '<div class="card"><p>From aur To station code dono chahiye.</p></div>'
            else:
                params = {"from": frm, "to": to}
                if travel_date:
                    params["date"] = travel_date
                data, err = rapidapi_get(TRAIN_API_ENDPOINTS["between"], params)
                result = train_result_html("Do stations ke beech trains", data, err)
        elif kind == "live":
            train_no = request.form.get("train_no", "").strip()
            travel_date = request.form.get("travel_date", "").strip()
            if not train_no.isdigit():
                result = '<div class="card"><p>Train number sirf digits me daalo.</p></div>'
            else:
                params = {"train": train_no}
                if travel_date:
                    params["date"] = travel_date
                data, err = rapidapi_get(TRAIN_API_ENDPOINTS["live"], params)
                result = train_result_html("Live running status", data, err)
        else:
            result = '<div class="card"><p>Unknown form.</p></div>'
    if not key_set:
        body = train_setup_card()
    else:
        body = """<div class="card"><h2>Train Info — Live Train Data</h2>
        <p class="muted">Live data RapidAPI "Indian Railway API" (free plan) se aata hai.
        Ye sirf jaankari hai — isse ticket book nahi hota, booking ke liye
        <a href="/booking/new">New Booking</a> use karo.</p></div>
        <div class="card"><h3>Do stations ke beech trains</h3><form method="post">
        <input type="hidden" name="form_kind" value="between">
        <label>From station code<input name="from_station" placeholder="e.g. LKO" required></label>
        <label>To station code<input name="to_station" placeholder="e.g. NDLS" required></label>
        <label>Date (optional)<input name="travel_date" type="date"></label>
        <p><button>Search Trains</button></p></form></div>
        <div class="card"><h3>Live running status</h3><form method="post">
        <input type="hidden" name="form_kind" value="live">
        <label>Train number<input name="train_no" placeholder="e.g. 12429" required></label>
        <label>Date (optional)<input name="travel_date" type="date"></label>
        <p><button>Check Live Status</button></p></form></div>
        <div class="card"><h3>PNR status</h3><form method="post">
        <input type="hidden" name="form_kind" value="pnr">
        <label>10-digit PNR<input name="pnr" maxlength="10" placeholder="e.g. 1234567890" required></label>
        <p><button>Check PNR Status</button></p></form></div>"""
        if result:
            body = result + body
    return page("Train Info", body)


def train_result_html(title, data, err):
    if err == "no-endpoint":
        return train_endpoint_card()
    if err:
        return (f'<div class="card"><h3>{html.escape(title)}</h3>'
                f'<p class="muted">Live data nahi mila: {html.escape(err)}. '
                "Thodi der baad dobara try karo.</p></div>")
    pretty = html.escape(json.dumps(data, indent=2, ensure_ascii=False))
    return (f'<div class="card"><h3>{html.escape(title)}</h3>'
            f'<pre style="white-space:pre-wrap;word-break:break-word">{pretty}</pre>'
            '<p class="muted">Live data: RapidAPI Indian Railway API.</p></div>')


if __name__ == "__main__":
    init_db()
    # 0.0.0.0 lets other devices on the same network open it too.
    app.run(host="0.0.0.0", port=5000, debug=True)
else:
    init_db()
