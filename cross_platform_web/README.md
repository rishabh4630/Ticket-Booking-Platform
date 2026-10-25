# TSN Ticket Booking — Cross-Platform Web Version

A Python + Flask + SQLite web version of the original **TSN Ticket Booking**
project, so it runs on Windows, macOS and Linux with the same code.

The original project is VB.NET WinForms + Oracle (Windows only, needs an
Oracle client and Crystal Reports). In this version SQLite replaces Oracle,
the browser replaces WinForms, and reports are plain HTML tables instead of
Crystal Reports. The original VB.NET code is untouched in `../original/`.

## Run

```
Windows : run_windows.bat        (or: py app.py)
macOS   : ./run_mac_linux.sh     (or: python3 app.py)
Linux   : ./run_mac_linux.sh     (or: python3 app.py)
```

Then open http://127.0.0.1:5000 in any browser. A `ticket_booking.db`
SQLite file is created next to `app.py` on first run.

Requirements: Python 3 + Flask (`pip install -r requirements.txt`).

## What is in the app

- **Home / Dashboard** — counts of transports, routes, customers and
  bookings, plus recent bookings.
- **Masters** — Transport Types, Transports, Routes (with via stops),
  Payment Modes, Customers, Streets, Cities, States. Lists are public;
  adding a master row is admin-only.
- **New Booking** — choose a transport, customer, travel date, payment mode
  and one or more seat numbers. The form shows the per-seat rate and the
  running total before you book.
- **Ticket** — booking details with seats and total fare.
- **Cancel Booking** — frees the booked seats again.
- **Reports (admin only)** — the six original report areas: Transport Type
  Master, Transport Master, Transport Transactions, Payment Transactions,
  Customer Transactions, Route Transactions.
- **Login / Sign Up** — passwords are hashed (Werkzeug), never stored in
  plain text. The original project's hardcoded demo login is deliberately
  NOT copied here. Logging in with the owner email
  `rishabhsingh4630@gmail.com` automatically becomes admin (same pattern as
  the Airline Reservation System project — please confirm/change this email
  if it is not the owner's real email); all other accounts stay customers.
  Customers see and cancel only their own bookings; admins see all bookings
  and the reports.

## Fare rule

Ticket total = **number of seats × the transport's major (r_major) rate**.

This rule is stated explicitly because the original Oracle fare logic was
not recoverable from the SQL schema alone. The per-seat rate is shown on the
booking form and the total on the ticket.

## Booking rules

- Seat numbers must be positive and not repeated within one booking.
- A seat already booked for the same transport and travel date cannot be
  booked again.
- Already-booked seats for that transport and date, plus the requested
  seats, must not exceed the transport's capacity — otherwise the booking
  is rejected with a clear message.

## Seed data (demo data)

On a fresh database the app seeds demo data only — not real schedules or
fares: 18 states, 28 cities, 4 streets, 3 transport types, 42 routes, 88
transports, 2 payment modes (Cash, Cheque) and 2 customers. The database
tables are adapted from `../docs/tables/tnstb.sql` (Oracle types converted
to SQLite integer/text).

## Structure

```
cross_platform_web/
  app.py             Single-file Flask app (inline templates)
  requirements.txt   Flask>=3.0
  run_mac_linux.sh   macOS/Linux launcher (port 5000)
  run_windows.bat    Windows launcher (port 5000)
  ticket_booking.db  Created on first run (not in version control)
```

No Oracle password or real credential is stored anywhere in this code.
