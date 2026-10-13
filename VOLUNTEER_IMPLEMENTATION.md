# KVP Volunteer Workspace

This change adds a role-specific Volunteer experience inside the existing React application. Stakeholder routes and management screens remain restricted to Stakeholders.

## Volunteer experience

- Role-based home dashboard with assigned-village context, girl/group counts, visit metrics, active targets, upcoming events/visits, case follow-ups, contact status, recent submissions and assignment history.
- Village-scoped girls and Kishori Group browsing, including group-to-girl drill-down.
- Volunteer field records for home visits and daily activity reports, with historical dates, GPS capture, Marathi browser speech input and photo upload while online.
- Local offline queue for home visits and daily activity reports, automatic retry after connectivity returns, manual retry, sync-status reporting and idempotency keys to avoid duplicate records on retry.
- Read-only village contact directory with verified status and quick call/SMS/WhatsApp actions. Contact maintenance and verification remain Stakeholder-only, as required by PRD v1.1.
- Personal reporting with activity history, target progress, assignment history, CSV export for Excel and browser print-to-PDF.

## Authorization changes

- Volunteer routes are role-gated in the frontend.
- Volunteer dashboard/report APIs only return the signed-in volunteer's activity and assigned-village data.
- Volunteer record lists are constrained by village; a volunteer cannot change another volunteer's home visit.
- Case creation by a volunteer assigns the case to that volunteer and source records must be in the assigned village.
- Event attendance cannot include girls from another village.
- Volunteer duplicate checks are constrained to the assigned village.
- Contacts remain Stakeholder-maintained and verified.

## Offline behavior

Home visits and daily activity reports can be queued on the current device and retried when online. Photos are **not** stored in the offline queue and must be uploaded after reconnecting. Event attendance, case changes and other API actions still require connectivity.

## Validation performed

- Python backend modules passed `compileall` syntax validation.
- All frontend JS/JSX files passed TypeScript parser syntax validation.
- Full pytest and Vite build were not run in this environment because backend dependencies (including `pymongo`) were unavailable and npm packages could not be installed from the registry. Run the commands below in the project environment.

```powershell
# Backend (from backend/ after installing requirements)
pytest -q

# Frontend (from frontend/ after npm ci)
npm run build
npm run lint
```
