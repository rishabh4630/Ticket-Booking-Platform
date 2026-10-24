#!/bin/bash
# TSN Ticket Booking (web version) - macOS / Linux launcher
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
python3 app.py
