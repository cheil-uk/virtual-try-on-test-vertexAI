# Virtual Try-On Prototype (Vertex AI)

This repo contains a tiny, rough working example that calls Google's Vertex AI Virtual Try-On API to generate a preview image of a person wearing a garment. The goal is to **vibe-code** a minimal flow that could power an in-store AR mirror experience (capture → generate → display).

## What this does

- Takes a **person photo** and a **garment photo**.
- Sends both to the Vertex AI Virtual Try-On endpoint.
- Saves the generated image to disk (for display on a kiosk / mirror screen).

## Quick start

1. **Install deps (Python 3.9.6 compatible)**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. **Authenticate**

You can use `gcloud` to grab an access token:

```bash
gcloud auth application-default login
gcloud auth print-access-token
```

3. **Run the demo**

```bash
python virtual_try_on_demo.py \
  --project YOUR_GCP_PROJECT \
  --location us-central1 \
  --person ./samples/person.jpg \
  --garment ./samples/garment.jpg \
  --output ./out/try_on.png
```

You can also pass an access token explicitly:

```bash
python virtual_try_on_demo.py \
  --project YOUR_GCP_PROJECT \
  --location us-central1 \
  --person ./samples/person.jpg \
  --garment ./samples/garment.jpg \
  --output ./out/try_on.png \
  --access-token "$(gcloud auth print-access-token)"
```

You can override the model if your org uses a different Vertex AI Virtual Try-On model name:

```bash
python virtual_try_on_demo.py \
  --project YOUR_GCP_PROJECT \
  --location us-central1 \
  --model virtual-try-on \
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

## Troubleshooting

- **404 Not Found from the predict endpoint**
  - Double-check that `--project` is your **Google Cloud project ID** (not the display name).
  - Verify the model name your org has access to. If it differs from `virtual-try-on`, pass it with `--model`.

- **429 Too Many Requests**
  - Reduce request volume and retry; the script now supports `--max-retries` and `--backoff-seconds`.
  - Check Vertex AI quotas in Google Cloud Console and request an increase if needed.

- **LibreSSL / urllib3 warning**
  - This warning is from your Python SSL build on macOS. It is safe to ignore for the demo.

## When to add a product catalog

Start by validating that **one person image + one garment image** can successfully return a try-on render. Once that API round-trip works reliably, layer in a catalog service so you can pick garments by ID and map them to image assets (or URLs). This avoids debugging catalog plumbing while the core model call is still unproven.

If you want to stub this now, there's a small mock catalog you can adapt (`samples_catalog.json`) that mirrors the structure you shared and adds a single field (`garmentImagePath`) you can map to the `--garment` input for the demo script. You can then build a thin UI/API layer (Node + Express or similar) that:

1. Lists products from the catalog (or client API).
2. Lets a user pick an item.
3. Resolves the selected item to a garment image path/URL.
4. Calls the Python try-on script or a small wrapper service.
