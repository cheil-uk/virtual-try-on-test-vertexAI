# Virtual Try-On Prototype (Vertex AI)

This repo contains a prototype that calls Google's Vertex AI Virtual Try-On API to generate a preview image of a person wearing a garment.

## What this does

- Takes a **person photo** and a **garment photo**.
- Sends both to the Vertex AI Virtual Try-On endpoint.
- Saves the generated image to local disk (for display on a kiosk / mirror screen).
- The backend uses direct REST calls to Vertex AI (no SDK required).

## Quick start

1. **Install deps (Python 3.9.6 compatible)**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. **Authenticate**

Use Application Default Credentials (ADC) so tokens auto-refresh:

```bash
gcloud auth application-default login
```

3. **Run the API + React demo (kiosk-style)**

First-time checklist:

- `python -m venv .venv`
- `source .venv/bin/activate`
- `pip install -r requirements.txt`
- `gcloud auth application-default login`

Backend (FastAPI):

```bash
uvicorn api_app:app --reload --port 8000
```

Frontend (Vite):

```bash
cd frontend
npm install
npm run dev
```

The React app uses `frontend/.env` to point at the backend (`VITE_API_BASE=http://localhost:8000`).
You can override this by setting `VITE_API_BASE` in your environment.
Create your local env files from the examples:

- `cp .env.example .env`
- `cp frontend/.env.example frontend/.env`

Keep both the backend and frontend running at the same time for the demo to work.

Background prompt preview (Imagen):

- Step 3 lets you generate a background image via Imagen using a text prompt.
- The generated background is sent back with the try-on request and composited server-side.
  The server also removes the original background from the try-on output (using `rembg`)
  before compositing, so the new background shows cleanly.
  `rembg` requires `onnxruntime`, which is included in `requirements.txt`.
- The default Imagen model is the highest-quality GA option: `imagen-4.0-ultra-generate-001`.
  You can override it with `IMAGEN_MODEL_ID` if needed.
- Try-on requests are sent to `us-central1` (model availability) while background generation
  can use `europe-west2`. This split is hard-coded in `frontend/src/App.jsx`.

4. **Run the CLI demo (optional)**

This script is a simple, local sanity check. It makes a single REST call to the
Vertex Virtual Try-On model and writes the result to `./out/`.

First-time checklist:

- `python -m venv .venv`
- `source .venv/bin/activate`
- `pip install -r requirements.txt`
- `gcloud auth application-default login`

Basic example:

```bash
python virtual_try_on_demo.py \
  --project YOUR_GCP_PROJECT \
  --location us-central1 \
  --person ./samples/person.jpg \
  --garment ./samples/garment.jpg \
  --output ./out/try_on.png
```

If you prefer, you can pass an access token explicitly:

```bash
python virtual_try_on_demo.py \
  --project YOUR_GCP_PROJECT \
  --location us-central1 \
  --person ./samples/person.jpg \
  --garment ./samples/garment.jpg \
  --output ./out/try_on.png \
  --access-token "$(gcloud auth application-default print-access-token)"
```

Override the model if your org uses a different Virtual Try-On model name:

```bash
python virtual_try_on_demo.py \
  --project YOUR_GCP_PROJECT \
  --location us-central1 \
  --model virtual-try-on-001 \
  --person ./samples/person.jpg \
  --garment ./samples/garment.jpg \
  --output ./out/try_on.png \
  --max-retries 3 \
  --backoff-seconds 2
```

## Notes

- This is intentionally a **rough example** to validate the workflow.
- The same flow can be wired to an in-store camera capture + large display to simulate an AR mirror.
- Swap `MODEL_ID` in the script if your org uses a different model name.
- **Production auth:** do not use manually copied access tokens. Run the backend with a
  service account (or workload identity) so credentials are provided by the runtime and
  tokens are refreshed automatically.

## Security

- **Never commit secrets.** Keep `.env` files local and use `.env.example` as a template.
  In production, use service accounts or workload identity (no manual tokens).
- **Images are in-memory only.** The backend does not persist user images; avoid logging raw bytes.
- **Frontend should not hold secrets.** The React app must only call the backend.
- **AWS hosting:** use HTTPS, restrict CORS, and add rate limiting at the edge.

## Troubleshooting

- **404 Not Found from the predict endpoint**
  - Double-check that `--project` is your **Google Cloud project ID** (not the display name).
  - Verify the model name your org has access to. If it differs from `virtual-try-on`, pass it with `--model`.

- **429 Too Many Requests**
  - Reduce request volume and retry; the script now supports `--max-retries` and `--backoff-seconds`.
  - Check Vertex AI quotas in Google Cloud Console and request an increase if needed.

- **LibreSSL / urllib3 warning**
  - This warning is from your Python SSL build on macOS. It is safe to ignore for the demo.

- **"Response exceeded max allowed size"**
  - Very large input images can produce responses over the 40 MB limit. The app auto-resizes inputs
    to a max dimension and encodes them as JPEG before sending to Vertex AI.

- **"Invalid number of product images. Expected 1, got 2."**
  - The `virtual-try-on-001` model currently accepts **exactly one** garment image per request.

