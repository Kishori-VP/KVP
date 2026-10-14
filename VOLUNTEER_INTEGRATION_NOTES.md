# KVP Volunteer Integration Notes

This integration is based on the newly supplied KVP project ZIP. Existing Stakeholder source files and the current backend implementation were preserved wherever possible. The previous Volunteer implementation was used selectively for the Volunteer UI and required endpoint/authorization changes.

## Included
- Role-based Volunteer navigation and routes within the existing React app.
- Volunteer dashboard, field records, contacts, groups, and personal reports.
- Volunteer-friendly shared girls, cases, events, targets, case detail, girl detail, event detail, and notifications screens.
- Personal Volunteer dashboard/report/assignment-history API endpoints.
- Additional village-scope/ownership checks for relevant records.
- Idempotency support for offline retries of home visits and activity reports.

## Important validation note
The source archive did not include installed frontend `node_modules` or a project Python virtual environment. This ZIP has not been validated against a live MongoDB instance or real Volunteer/Stakeholder accounts. Before deployment, install the dependencies in the project environment, run backend tests and the frontend build, then test API authorization with two accounts assigned to different villages.

## Suggested local checks (PowerShell)
```powershell
cd backend
python -m pip install -r requirements.txt
python -m compileall app
python -m pytest -q

cd ..\frontend
npm ci
npm run build
npm run lint
```

Volunteer access must remain enforced by the backend. Frontend route guards are for navigation only and are not a security boundary.


## SEDT follow-up additions (13 October 2026)
- Explicitly block converting a Stakeholder/Admin account into a Volunteer; create a separate account instead.
- Added Stakeholder-only Volunteer attendance register API and UI, with daily register and CSV export.
- Added a floating, Stakeholder-only Gemini RAG assistant widget (`/api/v1/ai`): a compact button stays fixed at the bottom-right and opens a picture-in-picture-style chat panel on every app screen. It is not a dedicated page or navigation route. It indexes operational records into `ai_knowledge_chunks`; credentials, password hashes, provider configuration and authentication secrets are excluded. Configure `GEMINI_API_KEY` in `backend/.env`, install updated requirements, then use Reindex in the floating panel. Rebuild after meaningful database changes.
- Existing volunteer field voice input, media upload endpoint, chart/dashboard foundations, and brand classes were retained. The dashboard charts and upload flow should still be validated in the browser against a live database.
- New MongoDB collections/indexes are created by the existing `ensure_indexes()` startup flow: `ai_knowledge_chunks` and `volunteer_attendance`. No destructive migration is required.
- AI retrieval is a snapshot, not live database querying: click Rebuild index after data changes. The model sees retrieved context only; it is not granted direct database access.


## Gemini RAG setup
1. In `backend/.env`, set `GEMINI_API_KEY=...` and optionally `GEMINI_CHAT_MODEL` / `GEMINI_EMBEDDING_MODEL`. Never put the key in `frontend/.env` or commit it.
2. From `backend`, install dependencies with `python -m pip install -r requirements.txt`, then restart FastAPI.
3. Sign in as a Stakeholder, click **Ask KVP AI** in the bottom-right corner, and click **Reindex** before asking questions.
4. Rebuild after significant changes to database data. This is a snapshot-based RAG index, not an always-live index. Embeddings and retrieved content are sent to Google Gemini; confirm the organisation's data-processing/privacy approval before indexing beneficiary, health, or case data.
5. The index uses a local cosine-similarity scan in MongoDB rather than Atlas Vector Search. For larger datasets, migrate retrieval to MongoDB Atlas Vector Search and use incremental re-indexing.

## Review notes / recommended next improvements
- Frontend production build succeeded on the previously integrated baseline, but this modified ZIP could not be built in this environment because dependency installation was unavailable; run `npm ci` then `npm run build` locally.
- Python source passed `compileall`; backend tests and live MongoDB/Gemini calls could not be run here because the environment lacks PyMongo and external dependency installation timed out.
- Add automated authorization tests for the AI and attendance routes and cross-village access tests.
- Add incremental/background RAG indexing, retention controls, explicit consent/approval for sending sensitive programme data to an external AI provider, and stronger retrieval evaluation.
- Verify all new UI flows against the actual database. Existing app already includes browser speech input, media upload endpoints/volunteer photo upload flow, daily/weekly/monthly trend charts, and past-versus-upcoming dashboards; these were retained rather than duplicated.
- Existing data model has a unique daily activity-report index per volunteer/date. Confirm the programme wants one daily report per Volunteer per date before changing that constraint.
