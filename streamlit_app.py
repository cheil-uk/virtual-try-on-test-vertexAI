import base64
import os
import time
from pathlib import Path
from typing import Optional

import streamlit as st

from virtual_try_on_demo import call_virtual_try_on


def list_image_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    images = [
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ]
    return sorted(images)


def encode_uploaded_file(uploaded_file) -> str:
    return base64.b64encode(uploaded_file.getvalue()).decode("utf-8")


def encode_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def resolve_token(explicit_token: str) -> str:
    if explicit_token:
        return explicit_token
    token = os.environ.get("ACCESS_TOKEN")
    if not token:
        raise ValueError("Missing access token. Provide it or set ACCESS_TOKEN.")
    return token


st.set_page_config(page_title="Virtual Try-On Demo", layout="wide")

st.title("Virtual Try-On Demo")
st.write(
    "Upload a person image and up to two garment images, then generate a try-on preview."
)

with st.sidebar:
    st.subheader("Vertex AI Settings")
    project = st.text_input("Project ID", value="project-a250af6f-f898-4bf6-872")
    location = st.text_input("Location", value="us-central1")
    model = st.text_input("Model", value="virtual-try-on-001")
    access_token = st.text_input(
        "Access Token (optional if ACCESS_TOKEN is set)",
        type="password",
    )

samples_dir = Path("samples")
sample_images = list_image_files(samples_dir)
sample_labels = ["(none)"] + [p.name for p in sample_images]

col1, col2 = st.columns(2)

with col1:
    st.subheader("Person Image")
    person_upload = st.file_uploader(
        "Upload person image", type=["png", "jpg", "jpeg"], key="person_upload"
    )
    person_sample = st.selectbox(
        "Or select sample",
        sample_labels,
        index=0,
        key="person_sample",
    )

with col2:
    st.subheader("Garment Images")
    st.caption("Select up to two garments (e.g., top + skirt).")
    garment_top_upload = st.file_uploader(
        "Upload top image", type=["png", "jpg", "jpeg"], key="garment_top_upload"
    )
    garment_top_sample = st.selectbox(
        "Or select top sample",
        sample_labels,
        index=0,
        key="garment_top_sample",
    )
    garment_bottom_upload = st.file_uploader(
        "Upload bottom image", type=["png", "jpg", "jpeg"], key="garment_bottom_upload"
    )
    garment_bottom_sample = st.selectbox(
        "Or select bottom sample",
        sample_labels,
        index=0,
        key="garment_bottom_sample",
    )


def get_person_b64() -> Optional[str]:
    if person_upload is not None:
        return encode_uploaded_file(person_upload)
    if person_sample != "(none)":
        return encode_file(samples_dir / person_sample)
    return None


def get_garment_b64(uploaded, selected_label: str) -> Optional[str]:
    if uploaded is not None:
        return encode_uploaded_file(uploaded)
    if selected_label != "(none)":
        return encode_file(samples_dir / selected_label)
    return None


def build_payload_multi(person_b64: str, garment_b64_list: list[str]) -> dict:
    product_images = [
        {"image": {"bytesBase64Encoded": garment_b64}}
        for garment_b64 in garment_b64_list
    ]
    return {
        "instances": [
            {
                "personImage": {"image": {"bytesBase64Encoded": person_b64}},
                "productImages": product_images,
            }
        ],
        "parameters": {"sampleCount": 1},
    }


if st.button("Generate Try-On"):
    person_b64 = get_person_b64()
    garment_top_b64 = get_garment_b64(garment_top_upload, garment_top_sample)
    garment_bottom_b64 = get_garment_b64(garment_bottom_upload, garment_bottom_sample)
    garment_b64_list = [b64 for b64 in [garment_top_b64, garment_bottom_b64] if b64]

    if not person_b64:
        st.error("Please upload or select a person image.")
    elif not garment_b64_list:
        st.error("Please upload or select at least one garment image.")
    else:
        try:
            token = resolve_token(access_token.strip())
        except ValueError as exc:
            st.error(str(exc))
        else:
            payload = build_payload_multi(person_b64, garment_b64_list)
            with st.spinner("Calling Vertex AI..."):
                response_json = call_virtual_try_on(
                    project=project.strip(),
                    location=location.strip(),
                    model=model.strip(),
                    token=token,
                    payload=payload,
                    max_retries=3,
                    backoff_seconds=2.0,
                )

            predictions = response_json.get("predictions", [])
            if not predictions:
                st.error("No predictions returned from API.")
            else:
                image_payload = predictions[0].get("bytesBase64Encoded")
                if not image_payload:
                    st.error("Missing image data in API response.")
                else:
                    image_bytes = base64.b64decode(image_payload)
                    st.subheader("Result")
                    st.image(image_bytes, caption="Try-On Result", use_container_width=True)

                    output_dir = Path("out")
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_path = output_dir / f"try_on_{int(time.time())}.png"
                    output_path.write_bytes(image_bytes)
                    st.success(f"Saved to {output_path}")
