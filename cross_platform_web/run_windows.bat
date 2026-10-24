@echo off
REM TSN Ticket Booking (web version) - Windows launcher
cd /d "%~dp0"
py -m pip install -q -r requirements.txt
py app.py
