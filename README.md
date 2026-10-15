# MediTrack — Hospital Medicine Inventory & Analytics

A fresh Flask + SQLite educational prototype with a consistent MediTrack navy/teal dashboard theme across every authenticated page.

## Requirements
- Windows 10/11
- Python 3.10 or newer
- VS Code (recommended)

## Run in Windows PowerShell

```powershell
cd MediTrack
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** in your browser. The SQLite database is created automatically at `instance/meditrack.sqlite3` and is populated with clearly marked demonstration records on first startup.

If PowerShell blocks virtual environment activation, run this for the current terminal:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Demo sign-in
- Username: `admin`
- Password: `Admin@123`

Change the default password by creating a replacement admin account and deactivate the demo account for any shared deployment. Set a strong `MEDITRACK_SECRET_KEY` environment variable before deployment. This app is intended for local educational demonstration, not production hospital use without a security and clinical review.

## Included features
- Login/logout with hashed passwords and server-side sessions
- CSRF protection on POST forms
- Dashboard KPIs and Chart.js charts sourced from SQLite
- Medicine inventory search and stock/expiry filters
- Add, view, edit and admin-only delete medicine records
- Stock receipt and issue history, with transactions and negative-stock prevention
- Dynamic expiry monitoring
- Transparent shortage estimates based on recorded issue history; no estimate is claimed where history is insufficient
- Analytics charts, alerts, printable reports and CSV exports
- Admin-only user creation and account activation/deactivation
- Responsive shared `templates/base.html` and `static/css/style.css`

## Notes
- All starter inventory and initial stock movements are demonstration data, not real hospital records.
- Prediction estimates are simple planning aids, not medical advice or a validated forecasting model.
- Chart.js, Font Awesome and Google Fonts load from CDNs, so these visual assets need internet access. Core Flask routes and forms run locally.
- The `instance/` database is generated automatically and excluded from the source ZIP; it will be recreated on first run.
