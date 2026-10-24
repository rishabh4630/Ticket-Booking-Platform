# Ticket Booking (TSN)

A transport ticket booking system, originally built as a **VB.NET WinForms** application
with an **Oracle** database and Crystal Reports.

> **Note:** The original code contained hardcoded Oracle database passwords.
> In this repository they have been replaced with the placeholder
> `YOUR_ORACLE_PASSWORD`. Put your own Oracle credentials in
> `ModConnection.vb` (and the transaction/report forms) before running the
> original application. The original demo login was `aaa` / `aaa`.

## What it does

From the main menu (**Screens**):

| # | Screen | What it manages |
|---|--------|-----------------|
| 1 | Transport Type Master | Types of transport (e.g. bus, train) |
| 2 | Transport Master | Transports: name, capacity, rates, route, timings |
| 3 | Transport Transaction | Transport bookings |
| 4 | Payment Transaction | Payments and payment details |
| 5 | Customer Transaction | Customers and their bookings |
| 6 | Route Transaction | Routes and route details |
| 7 | Street Master | Streets |
| 8 | City Master | Cities |
| 9 | State Master | States |

**Reports** (Crystal Reports R1–R6) cover the same six areas:
Transport Type Master, Transport Master, Transport Transaction,
Payment Transaction, Customer Transaction, Route Transaction.

## Database

See `docs/tables/tnstb.sql` for the Oracle table definitions:

- `trans_type_mast`, `trans_mast`, `trans_tranc_mast`, `trans_tranc_details`
- `payment_mast`, `payment_det`
- `cust_mast`, `cust_det`
- `street_mast`, `city_mast`, `state_mast`
- `route_mast`, `route_det`

Supporting documents: `docs/` holds the original documentation (`.doc`),
the data-flow / ER diagrams (`.ppt`), and the table scripts.

## Original project

- Location: `original/TSN - Ticket Booking/`
- Language: VB.NET (Visual Studio 2003-era project, `.vbproj` / `.sln`)
- Database: Oracle via `OraOLEDB.ORACLE` (ADODB)
- Reports: Crystal Reports (`.rpt`)
- Startup form: Login (`F11 - Login`)

The original project is Windows-only: WinForms, Oracle client and
Crystal Reports do not run on macOS/Linux. Build outputs (`bin/`, `obj/`,
`*.suo`, `*.user`, `*.exe`, `*.dll`) are excluded from this repository
via `.gitignore`.

## Live Demo

Try it in your browser, no install needed:

**https://rishabh4630.github.io/Ticket-Booking-Platform/**

The demo runs fully in your browser (accounts and bookings live only in
that browser, demo data only) — it mirrors the web version below.

## Cross-platform web version

A Python + Flask + SQLite web version lives in `cross_platform_web/`
(same approach as the Airline Reservation System project), so the system
runs on Windows, macOS and Linux with no Oracle or Crystal Reports install.

Run it:

```bash
cd cross_platform_web
bash run_mac_linux.sh        # macOS / Linux
# or on Windows: run_windows.bat
```

Then open http://127.0.0.1:5000 — sign up, log in, manage masters,
book tickets (fare = seats × the transport's major rate), view reports
(admin only). The owner email `rishabhsingh4630@gmail.com` becomes admin
automatically on login (please confirm this is the right owner email).
