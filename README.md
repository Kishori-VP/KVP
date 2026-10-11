# Kishori Vikas Program

| Layer    | Tech                      |
|----------|---------------------------|
| Database | MongoDB                   |
| Backend  | FastAPI (Python 3.11)     |
| Frontend | React (Vite) + Tailwind CSS v4 |

## Project structure

```
kishori-vikas-program/
├── backend/
│   ├── app/
│   │   ├── api/routes/   # Route modules (one per resource)
│   │   ├── api/router.py # Aggregates all routes under /api/v1
│   │   ├── core/         # Settings, auth, permission matrix, encryption
│   │   ├── db/           # MongoDB connection, collection names, indexes
│   │   ├── schemas/      # Pydantic request schemas
│   │   ├── services/     # Business logic (targets, metrics, reports, alerts, scheduler...)
│   │   ├── seed/         # Default lookups, admin bootstrap, Excel data import
│   │   ├── assets/fonts/ # Noto fonts for Marathi PDF reports
│   │   └── main.py       # FastAPI app entry point
│   ├── tests/            # End-to-end API tests (use a separate test database)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── components/
    │   ├── lib/api.js    # Axios instance
    │   ├── pages/
    │   └── App.jsx       # Routes
    └── vite.config.js    # Tailwind plugin + /api proxy to backend
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- MongoDB (local install, Docker, or MongoDB Atlas)

## Backend setup

```bash
cd backend
py -3.11 -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # then set JWT_SECRET_KEY and CREDENTIALS_ENCRYPTION_KEY
fastapi dev app/main.py         # http://localhost:8000  (docs at /docs)
```

### First-time data setup

```bash
# Import talukas, the 20 villages, 88 Kishori Groups, 20 Bal Panchayat groups and the
# Girls' Unique ID list (also seeds default lookups). Safe to re-run.
python -m app.seed.import_kvp_data "C:/Users/HP/Downloads/KVP Data" --dry-run
python -m app.seed.import_kvp_data "C:/Users/HP/Downloads/KVP Data"

# Create the first Stakeholder (admin) account
python -m app.seed.create_admin --name "Programme Coordinator" --phone 9876543210 --email pc@example.org
```

Log in with `POST /api/v1/auth/login` (`identifier` = phone or email), or use **Authorize** in `/docs`.

### Tests

```bash
python -m pytest -q             # uses the kishori_vikas_test database, dropped afterwards
```

### API overview (Stakeholder / admin)

| Area | Endpoints |
|------|-----------|
| Auth & users | `/auth/*`, `/users` (create, role, status, reset password) |
| Volunteers | `/volunteers` — create without a village and `assign` later (at most one village), reassign with history, groups, dashboard, activity, performance, submission status, coverage |
| Master data | `/talukas`, `/districts`, `/villages` (+ bulk `/villages/locations`), `/groups` |
| Contacts | `/contacts` — 4 mandatory categories per village, verification, coverage |
| Girls | `/girls` — Girl ID, filters, duplicate check/scan/merge, participation, `/girls/{id}/health`, `/girls/{id}/cases` |
| Cases | `/cases` — notes, status workflow, assignment |
| Field records | `/home-visits`, `/activity-reports` (daily report, replaces the Google Form) |
| Events | `/events` — calendar, checklists, attendance, report, expenditure, media, PDF/Excel export, planned vs conducted |
| Targets | `/targets` — daily/weekly/monthly/quarterly/custom, live progress & status, revisions |
| Dashboard | `/dashboard/*` — summary, trends, cases, villages (map), targets, participation, health, alerts, drilldown, past-vs-upcoming |
| Reports | `/reports/{type}?format=json|pdf|xlsx`, share, schedules, generated history |
| Report templates | `/reports/templates` — choose sections/columns/summary, scope, title; run, share, schedule |
| Push / SMS / sync | `/push/*` (Web Push subscriptions), `/messages` (SMS outbox, test SMS), `/sync/status` (offline sync health) |
| Notifications | `/notifications` — in-app, announcements, run-checks |
| Configuration | `/config/lookups`, `/config/settings/{key}`, `/config/permissions`, `/config/providers` |
| Audit | `/audit-logs` |

## Frontend setup (Stakeholder portal)

```bash
cd frontend
npm install
copy .env.example .env          # set VITE_PROXY_TARGET if the backend is not on port 8000
npm run dev                     # http://localhost:5173
```

In development, requests to `/api/*` are proxied to `VITE_PROXY_TARGET` (default `http://localhost:8000`).
Pages: dashboard, girls, cases, events (list / calendar / planned vs conducted), field records, volunteers,
targets, users, villages, groups & talukas, contacts, reports (run / templates / schedules / generated),
notifications, SMS & sync, configuration and audit log.

## Optional integrations

| Feature | Setup |
|---------|-------|
| Phone push notifications | `python -m app.seed.generate_vapid` → paste keys into `backend/.env`; then *Notifications → Enable push on this device* (needs HTTPS in production) |
| SMS reminders to girls' families | *Configuration → Providers*: type `sms`, provider `console` (log only), `twilio` or `fast2sms`, mark active + default; tick *SMS reminder* when scheduling an event |
| Emailing reports | Set `SMTP_*` in `backend/.env`; external addresses must be on *Configuration → Rules → report_sharing* |

## Health check

`GET /api/v1/health` returns the API status and whether MongoDB is reachable.
