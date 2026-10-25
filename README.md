# 🎫 Ticket Booking (TSN)

A transport ticket booking system — book bus and train tickets, manage transports, routes and masters, handle payments, and view reports.

The cross-platform web version is built using **Python + Flask + SQLite**, and the original desktop version is built using **Visual Basic .NET WinForms + Oracle** with Crystal Reports.

---

## 🌐 Live Demo

🔗 **Try the application here:**
https://rishabh4630.github.io/Ticket-Booking-Platform/

> This is a browser demo of the web version, hosted on GitHub Pages — it works for anyone. Booking in the demo needs a free Login / Sign Up (accounts and bookings live only in that browser, and demo data only). For the full version with a saved database, run the web version below.

---

## 📌 Project Overview

This project manages ticket bookings for **TSN (TransServiceNet)** through a simple interface for transport-related operations.

This repository contains **two versions** of the same project:

| Version | Technology | Runs on |
|---|---|---|
| **Cross-Platform Web Version** — [`cross_platform_web/`](cross_platform_web/) | Python + Flask + SQLite | **Windows, macOS and Linux** |
| Original Desktop Version — [`original/TSN - Ticket Booking/`](original/TSN%20-%20Ticket%20Booking/) | Visual Basic .NET WinForms + Oracle | Windows only |

> **Using a Mac?** Use the web version in `cross_platform_web/` — the original VB.NET WinForms app cannot run on macOS because WinForms, the Oracle client and Crystal Reports are Windows-only technologies.

Users can manage transport types, transports, routes, streets, cities, states and customers, search transports by route and date, book tickets and get a booking number, cancel bookings, and view reports. The web version also shows live train information (between stations, running status, PNR status and train schedule) via a free RapidAPI key.

> **Note:** The original code contained hardcoded Oracle database passwords. In this repository they have been replaced with the placeholder `YOUR_ORACLE_PASSWORD`. Put your own Oracle credentials in `ModConnection.vb` (and the transaction/report forms) before running the original application. The original demo login was `aaa` / `aaa`.

---

## ✨ Features

- 🚌🚆 Transport Management — types, transports, capacities, rates, routes and timings
- 🗺️ Route, Street, City and State Masters
- 👥 Customer Management
- 🎫 Ticket Booking with capacity check — a booking is accepted only if seats are free on that transport and date
- 🪑 Duplicate-seat check — the same seat on the same transport and date cannot be booked twice
- ❌ Cancel Bookings — cancelling frees the booked seats
- 💰 Automatic fare calculation — fare = seats × the transport's major rate
- 💳 Payment Transaction Management
- 📊 Reports (R1–R6) — Transport Type, Transport, Transport Transaction, Payment, Customer and Route reports (admin only in the web version)
- 🔐 Login / Sign Up — customers book and manage only their own reservations; logging in with the owner's email automatically signs you in as an admin (no separate admin login page)
- 📝 Booking under your own name — the New Booking form shows only the logged-in user's name (admins see all customers)
- 🔍 Home search, popular routes and route info — search by From / To / Date / Type, click a Popular Routes card to search it directly, and see road distance, duration and destination weather on results (free keyless APIs; search and booking never break if they fail)
- 📍 PIN suggestion — PIN code auto-fill suggestion on the customer form (free keyless API)
- 🚆 Train Info — live train data (trains between stations, live running status, PNR status, train search and train schedule) via the RapidAPI Indian Railway API; on the demo your key stays only in your own browser, on the web version it comes from an environment variable, and the page never shows fake train data
- 🌍 All-India routes — 18 states, 28 cities, 42 routes and 88 transports in the seed data (AC Bus, Non-AC Bus and Train); all demo data uses invented TSN names only, no real operators or train numbers
- 🎬 Premium video background — a cinematic 4K airplane-window video (cloudscape from above, 3840x2160, 60 sec loop, muted) plays as the page wallpaper, with a brand-blue gradient overlay so text stays readable, and the video is hidden for users who prefer reduced motion
- 🎨 Premium design with dark-mode support and an organized two-row header

---

## 📂 Project Structure

```text
Ticket-Booking-Platform/
│
├── README.md                  This file — overview, screens, structure
├── .gitignore                 Excludes build outputs, caches, local databases
│
├── original/
│   └── TSN - Ticket Booking/  Original VB.NET WinForms + Oracle project (untouched,
│                              except Oracle passwords replaced with a placeholder)
│       ├── *.vb / *.resx      Forms F1–F12, reports R1–R6, modules
│       ├── *.rpt              Crystal Reports files
│       └── *.sln / *.vbproj   Visual Studio solution and project
│
├── cross_platform_web/        Python + Flask + SQLite version (runs everywhere)
│   ├── app.py                 Single-file web app
│   ├── requirements.txt       Flask>=3.0
│   ├── run_mac_linux.sh       macOS/Linux launcher
│   ├── run_windows.bat        Windows launcher
│   └── README.md              How to run, fare rule, booking rules, seed data
│
├── docs/                      Original documentation and database scripts
│   ├── TransServiceNetMainDoc1.doc   Main project documentation
│   ├── tables/                Oracle table scripts (tnstb.sql, tnstb.txt)
│   └── dfd-erd/               Data-flow and ER diagrams (.ppt)
│
└── README.md
```

Live demo source (GitHub Pages) lives on the `gh-pages` branch as a single `index.html` — it mirrors the web version in the browser only.

---

## 🛠️ Technologies Used

- Python
- Flask
- SQLite
- HTML / CSS
- Visual Basic .NET
- .NET Framework
- Visual Studio (2003-era project)
- Oracle (via `OraOLEDB.ORACLE`, ADODB)
- Crystal Reports

---

## 📊 Booking Details

| Field | Description |
|----------|-------------|
| Booking No. | Booking number, generated automatically |
| Customer | Customer the booking is recorded under |
| Transport | e.g. TSN Express (AC Bus / Non-AC Bus / Train) |
| Route | From city → To city |
| Travel Date | Date of travel |
| Seats | Number of seats booked |
| Fare Amount | Taken automatically — seats × the transport's major rate |
| Payment Mode | Payment mode selected at booking |
| Cancellation | Cancelling a booking frees the booked seats |

---

## 🧠 How It Works

### Booking Rules

A booking is accepted only if seats are free on that transport and date (capacity check), and the same seat on the same transport and date cannot be booked twice. The fare is calculated automatically from the transport's major rate — seats × rate. Cancelling a booking frees its seats for others.

### Sample Data

Sample data is created automatically on the first run of the web version, so the app works immediately — for example:

| Transport | Route | Timings | Fare |
|----------|-------|---------|------|
| TSN Express | Lucknow → Delhi | 06:00 — 12:00 | Rs. 500 per seat (AC Bus, capacity 40) |

The full seed data covers 18 states, 28 cities, 42 routes and 88 transports — all demo data with invented TSN names only.

### Screens

From the main menu:

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

### Database

See `docs/tables/tnstb.sql` for the Oracle table definitions:

- `trans_type_mast`, `trans_mast`, `trans_tranc_mast`, `trans_tranc_details`
- `payment_mast`, `payment_det`
- `cust_mast`, `cust_det`
- `street_mast`, `city_mast`, `state_mast`
- `route_mast`, `route_det`

---

## ⚙️ Installation

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/rishabh4630/Ticket-Booking-Platform.git
```

### 2️⃣ Navigate to the Project Folder

```bash
cd Ticket-Booking-Platform
```

### 3️⃣ Web Version — Navigate to the Web Folder

```bash
cd cross_platform_web
```

### 4️⃣ Create a Virtual Environment

```bash
python3 -m venv venv
```

### 5️⃣ Activate the Virtual Environment

#### Windows

```bash
venv\Scripts\activate
```

#### macOS/Linux

```bash
source venv/bin/activate
```

### 6️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### Desktop Version — Windows Only

1. Open the solution in `original/TSN - Ticket Booking/` in Visual Studio on a compatible Windows environment.
2. Install the Oracle client and Crystal Reports runtime.
3. Replace the `YOUR_ORACLE_PASSWORD` placeholder with your own Oracle credentials.
4. Build and run the project.

> Note: the original desktop project is Windows-only — WinForms, the Oracle client and Crystal Reports do not run on macOS/Linux. Build outputs (`bin/`, `obj/`, `*.suo`, `*.user`, `*.exe`, `*.dll`) are excluded from this repository via `.gitignore`. The web version has no such dependency — it is fully standalone.

---

## 📦 Requirements

Create a **requirements.txt** file with the following content:

```text
Flask>=3.0
```

The web version's `requirements.txt` is already included in `cross_platform_web/`.

---

## ▶️ Run the Application

### Web Version

#### Windows

```bash
run_windows.bat
```

Or manually:

```bash
py -m pip install -r requirements.txt
py app.py
```

#### macOS / Linux

```bash
chmod +x run_mac_linux.sh
./run_mac_linux.sh
```

Or manually:

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

After running the command, open your browser and visit:

```text
http://127.0.0.1:5000
```

> Requirements: Python 3.10 or newer — download from https://www.python.org/downloads/ (on Windows, tick "Add Python to PATH" during install).

Then sign up, log in, manage masters, book tickets (fare = seats × the transport's major rate) and view reports (admin only). The owner email `rishabhsingh4630@gmail.com` becomes admin automatically on login (please confirm this is the right owner email).

---

## 📈 Booking Workflow

1. Sign up and log in
2. Search a route by From / To / Date / Type, or click a Popular Routes card
3. Choose a transport from the results
4. Enter seats and payment mode — fare is calculated automatically
5. Capacity and duplicate-seat checks run — the booking is created with a booking number
6. View the booking in Bookings, or cancel it when needed (seats are freed)
7. View reports (admin only)

---

## 📷 Application Preview

Add screenshots here after running the application.

```text
assets/
├── home.png
├── booking.png
├── ticket.png
```

Example:

```markdown
![Home](assets/home.png)

![Booking](assets/booking.png)

![Ticket](assets/ticket.png)
```

---

## 🚀 Future Improvements

- Add online payment integration
- Send e-tickets by email
- Add seat-map selection
- Deploy using Docker
- Add real bus/train booking integration (currently demo data for booking, and RapidAPI data for train information only — no free keyless Indian bus/train booking API exists today)

---

## 🤝 Contributing

Contributions are welcome!

1. Fork this repository

2. Create a new branch

```bash
git checkout -b feature-name
```

3. Commit your changes

```bash
git commit -m "Added new feature"
```

4. Push to GitHub

```bash
git push origin feature-name
```

5. Create a Pull Request

---

## 👨‍💻 Author

**Rishabh Singh Rajput**

B.Tech Computer Science & Engineering Student

Interested in:

- Web Development
- Problem-Solving
- Python Development
- Software Engineering

### GitHub

https://github.com/rishabh4630

---

## ⭐ Show Your Support

If you found this project useful, please consider giving it a ⭐ on GitHub.

It motivates me to build more projects.

---

## 📄 License

This project is intended for educational and learning purposes.

Feel free to use, modify, and share it for learning purposes.
