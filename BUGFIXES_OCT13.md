# KVP bug-fix update

## Included fixes
- Stakeholders no longer see the Register girl action, and the API rejects Stakeholder POST /girls requests.
- Volunteer registration is restricted server-side to the authenticated Volunteer account's assigned village; a missing assignment or mismatched submitted village is rejected.
- Floating assistant UI no longer displays the Gemini brand name.
- The assistant uses the explicit Google API key parameter for the chat model, surfaces actionable provider errors with key redaction, and stages a reindex before publishing it so a failed reindex does not immediately erase the previous index.
- Vite's default API proxy target is port 8001, matching the KVP backend when another service uses port 8000.
- Volunteer report print view prints the report content only, not the app navigation and filters.

## Local setup reminder
If `frontend/.env` exists, edit it to contain:

`VITE_PROXY_TARGET=http://localhost:8001`

Restart the Vite dev server after changing this variable. Keep the Gemini API key only in `backend/.env`. Restart Uvicorn after changing backend environment variables.

## Validation status
Backend Python source compilation passed. Frontend build and live MongoDB/provider requests still need to be run in the local environment. Reindex may take time depending on database size and provider quota.
