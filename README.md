# KHIETTRAN AI STUDIO

Windows desktop photo-editing MVP using Tauri 2 + React + TypeScript and a FastAPI backend. AI image processing is performed server-side through Replicate; never embed `REPLICATE_API_TOKEN` in the desktop app.

## Deploy the API to Render

This repository contains `render.yaml` and `backend/Dockerfile`. In Render, choose **New → Blueprint**, connect this repository, and apply the Blueprint. The Docker build context is `backend/`.

Set `REPLICATE_API_TOKEN` as a secret environment variable in the Render service (Render Dashboard → service → Environment). `render.yaml` declares this key with `sync: false`, so Render will prompt for it when applying the Blueprint. Do not commit a real token to GitHub.

After deployment, replace `YOUR-SERVICE` with the actual Render service hostname and check:

- `https://YOUR-SERVICE.onrender.com/health`
- `https://YOUR-SERVICE.onrender.com/api/v1/capabilities`

The capabilities endpoint reports whether a token is configured; it does not prove that a real Replicate inference succeeds. Test an actual image operation before production use.

## Run the backend locally

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run tests from `backend/` with `python -m pytest -q tests`.

## Build the Windows desktop app

Install Node.js LTS, Rust, and the Windows prerequisites for Tauri 2. Copy `desktop/.env.production.example` to `desktop/.env.production`, then replace the placeholder with the exact Render HTTPS origin:

```dotenv
VITE_API_BASE_URL=https://YOUR-SERVICE.onrender.com
```

Then run in PowerShell:

```powershell
cd desktop
npm install
npm run build
npm run tauri build
```

The installer output is generated under `desktop/src-tauri/target/release/bundle/nsis/`. The desktop build has not been verified in this environment; build and test it on Windows after the real API URL is available.
