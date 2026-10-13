# KHIETTRAN AI STUDIO

Desktop photo editing MVP built with Tauri + React and a FastAPI backend. AI image operations use Replicate from the server only.

## Deploy API on Render

This repository includes `render.yaml` and `backend/Dockerfile`. In Render, create a Blueprint from this repository and set `REPLICATE_API_TOKEN` as a secret environment variable. Never commit the token.

After deployment, verify:
- `https://YOUR-SERVICE.onrender.com/health`
- `https://YOUR-SERVICE.onrender.com/api/v1/capabilities`

## Backend local development

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Desktop

Copy `desktop/.env.production.example` to `desktop/.env.production` and set `VITE_API_BASE_URL` to the deployed HTTPS API origin before building the Windows app.
