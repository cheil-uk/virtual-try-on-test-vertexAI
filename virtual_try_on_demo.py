import argparse
import base64
import json
import os
import time
from pathlib import Path
from typing import Optional

import requests

MODEL_ID = "virtual-try-on-001"

def read_image_base64(path: Path) -> str:
    data = path.read_bytes()
    return base64.b64encode(data).decode("utf-8")


def build_payload(person_b64: str, garment_b64: str) -> dict:
    return {
        "instances": [
            {
                "personImage": {
                    "image": {
                        "bytesBase64Encoded": person_b64
                    }
                },
                "productImages": [
                    {
                        "image": {
                            "bytesBase64Encoded": garment_b64
                        }
                    }
                ],
            }
        ],
        "parameters": {
            "sampleCount": 1,
        },
    }


def get_access_token(explicit_token: Optional[str]) -> str:
    if explicit_token:
        return explicit_token
    token = os.environ.get("ACCESS_TOKEN")
    if not token:
        raise SystemExit(
            "Missing access token. Provide --access-token or set ACCESS_TOKEN."
        )
    return token


def call_virtual_try_on(
    project: str,
    location: str,
    model: str,
    token: str,
    payload: dict,
    max_retries: int,
    backoff_seconds: float,
) -> dict:
    # Publisher model predict endpoint (no project in path)
    url = (
      "https://{location}-aiplatform.googleapis.com/v1/projects/"
      "{project}/locations/{location}/publishers/google/models/{model}:predict"
    ).format(location=location, project=project, model=model)




    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)

            if not response.ok:
                print("STATUS:", response.status_code)
                print("RESPONSE BODY:", response.text)

            response.raise_for_status()
            return response.json()

        except requests.HTTPError as e:
            last_exc = e
            if attempt >= max_retries:
                raise

            sleep_for = backoff_seconds * (2 ** attempt)
            time.sleep(sleep_for)

    # Should never get here
    raise SystemExit(f"Unexpected retry loop exit. Last error: {last_exc}")

def save_output(response_json: dict, output_path: Path) -> None:
    predictions = response_json.get("predictions", [])
    if not predictions:
        raise SystemExit("No predictions returned from API.")

    image_payload = predictions[0].get("bytesBase64Encoded")
    if not image_payload:
        raise SystemExit("Missing image data in API response.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(image_payload))


def main() -> None:
    parser = argparse.ArgumentParser(description="Vertex AI Virtual Try-On demo")
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="us-central1")
    parser.add_argument("--person", required=True)
    parser.add_argument("--garment", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--access-token")
    parser.add_argument("--model", default=MODEL_ID)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--backoff-seconds", type=float, default=2.0)

    args = parser.parse_args()

    person_path = Path(args.person)
    garment_path = Path(args.garment)

    if not person_path.exists():
        raise SystemExit(f"Person image not found: {person_path}")
    if not garment_path.exists():
        raise SystemExit(f"Garment image not found: {garment_path}")

    token = get_access_token(args.access_token)
    payload = build_payload(
        read_image_base64(person_path),
        read_image_base64(garment_path),
    )
    response_json = call_virtual_try_on(
        args.project,
        args.location,
        args.model,
        token,
        payload,
        args.max_retries,
        args.backoff_seconds,
    )
    save_output(response_json, Path(args.output))

    print(f"Saved try-on image to {args.output}")


if __name__ == "__main__":
    main()
