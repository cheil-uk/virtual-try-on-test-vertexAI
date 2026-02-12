import { useEffect, useRef, useState } from "react";

// API base for the FastAPI backend (override with VITE_API_BASE)
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
// Optional API key guard:
// If API_KEY is set in backend .env, you must also set VITE_API_KEY in frontend/.env
// so requests include the correct x-api-key header.
const API_KEY = import.meta.env.VITE_API_KEY;
// Vertex regions are split: Try-On is only available in us-central1
const TRYON_LOCATION = "us-central1";
// Background generation can use Europe (Imagen availability permitting)
const BACKGROUND_LOCATION = "europe-west2";
// Explicit Imagen model ID for background generation (kept in sync with backend default)
const IMAGEN_MODEL_ID = "imagen-4.0-ultra-generate-001";

// Curated background prompts (luxury tone)
const BACKGROUND_OPTIONS = [
  { label: "No background", value: "" },
  { label: "Golf", value: "luxury golf course at golden hour, manicured fairway, soft cinematic light, shallow depth of field, premium resort atmosphere" },
  { label: "Tennis", value: "luxury tennis court at sunset, clean modern club aesthetic, warm soft light, elegant minimal surroundings, shallow depth of field" },
  { label: "Outdoors", value: "luxury outdoor terrace garden, refined resort ambience, warm natural light, modern landscaping, soft bokeh background" }
];

// Local sample garments (served from /frontend/public/samples)
const SAMPLE_GARMENTS = [
  { id: "1", label: "Grey Coat", src: "/samples/hbCoatGrey.png" },
  { id: "2", label: "Jeans", src: "/samples/jeans-womens.jpeg" },
  { id: "3", label: "Womens' Jumper", src: "/samples/jumper-womens.jpeg" },
  { id: "4", label: "Mens Tracksuit Bottoms", src: "/samples/mens-tracksuit-bottoms.jpeg" },
  { id: "5", label: "Womens' Mesh Top", src: "/samples/mesh-top.jpeg" },
  { id: "6", label: "Mens' Overshirt", src: "/samples/overshirt-mens.jpeg" },
  { id: "7", label: "Mens' Shorts", src: "/samples/shorts-mens.jpeg" },
  { id: "8", label: "Womens' Skirt", src: "/samples/skirt-2.jpeg" },
  { id: "9", label: "Womens' Skirt", src: "/samples/skirt-3.jpeg" },
  { id: "10", label: "Womens' Skirt", src: "/samples/skirt.jpeg" },
  { id: "11", label: "Mens Slim Fit TShirt", src: "/samples/slim-fit-tshirt-mens.jpeg" },
  { id: "12", label: "Tennis Dress", src: "/samples/tennis-dress.jpeg" },
  { id: "13", label: "Womens' Zip Up Jacket", src: "/samples/zip-up-womens.jpeg" },
];

// Top-level journey steps displayed in the progress bar
const STEPS = ["Garment", "Photo", "Result"];

// Read a File into a data URL for preview + base64 extraction
function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// Convert a data URL into raw base64 for API payloads
function base64FromDataUrl(dataUrl) {
  if (!dataUrl) return "";
  const parts = dataUrl.split(",");
  return parts.length > 1 ? parts[1] : "";
}

export default function App() {
  // Step state
  const [stepIndex, setStepIndex] = useState(0);
  // Garment selection + cached base64
  const [selectedGarment, setSelectedGarment] = useState(null);
  const [garmentImage, setGarmentImage] = useState("");
  // User photo (data URL)
  const [personPhoto, setPersonPhoto] = useState("");
  // Camera capture state
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [cameraStatus, setCameraStatus] = useState("");
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  // Background prompt used only for Imagen (not sent to Try-On)
  const [backgroundPrompt, setBackgroundPrompt] = useState("");
  const [backgroundImage, setBackgroundImage] = useState("");
  // Loading + results
  const [isGenerating, setIsGenerating] = useState(false);
  const [resultImage, setResultImage] = useState("");
  const [gallery, setGallery] = useState([]);
  const [error, setError] = useState("");

  // Gate actions based on required inputs
  const canProceedFromGarment = Boolean(selectedGarment && garmentImage);
  const canProceedFromPhoto = Boolean(personPhoto);
  const canGenerate = Boolean(
    personPhoto && selectedGarment && garmentImage && !isGenerating
  );

  // Progress bar enablement rules
  const isStepEnabled = (index) => {
    if (index === 0) return true;
    if (index === 1) return canProceedFromGarment;
    if (index === 2) return canProceedFromGarment && canProceedFromPhoto;
    return false;
  };

  // Handle photo upload
  const onPhotoUpload = async (file) => {
    setError("");
    if (!file) return;
    const dataUrl = await readFileAsDataUrl(file);
    setPersonPhoto(dataUrl);
  };

  // Start device camera for capture
  const startCamera = async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setIsCameraOpen(true);
        setCameraStatus("Camera started");
      }
    } catch (err) {
      setCameraStatus("Camera permission denied or unavailable.");
      setError("Unable to access camera. Please allow camera permissions.");
    }
  };

  // Stop device camera
  const stopCamera = () => {
    if (videoRef.current?.srcObject) {
      const tracks = videoRef.current.srcObject.getTracks();
      tracks.forEach((track) => track.stop());
      videoRef.current.srcObject = null;
    }
    setIsCameraOpen(false);
    setCameraStatus("Camera closed");
  };

  // Capture a frame from the live video
  const capturePhoto = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    const width = video.videoWidth || 1024;
    const height = video.videoHeight || 768;
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, width, height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
    setPersonPhoto(dataUrl);
    stopCamera();
    setCameraStatus("Photo captured");
  };

  // Load selected garment image into base64 for API use
  useEffect(() => {
    const loadGarmentImage = async () => {
      if (!selectedGarment?.src) {
        setGarmentImage("");
        return;
      }
      const response = await fetch(selectedGarment.src);
      const blob = await response.blob();
      const file = new File([blob], "garment.jpg", { type: blob.type });
      const dataUrl = await readFileAsDataUrl(file);
      setGarmentImage(dataUrl);
    };

    loadGarmentImage();
  }, [selectedGarment]);

  // Generate try-on result (optionally with background)
  const handleGenerate = async () => {
    setError("");
    setIsGenerating(true);
    setResultImage("");

    try {
      // Lazily generate a background if a prompt is selected
      const bgDataUrl = await ensureBackgroundImage();
      const response = await fetch(`${API_BASE}/try-on`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(API_KEY ? { "x-api-key": API_KEY } : {})
        },
        body: JSON.stringify({
          project: "project-a250af6f-f898-4bf6-872",
          location: TRYON_LOCATION,
          model: "virtual-try-on-001",
          personImageBase64: base64FromDataUrl(personPhoto),
          garmentImageBase64: base64FromDataUrl(garmentImage),
          backgroundImageBase64: bgDataUrl
            ? base64FromDataUrl(bgDataUrl)
            : null
        })
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "Request failed");
      }

      const data = await response.json();
      if (!data.imageBase64) {
        throw new Error("No image returned from the server at all");
      }
      // Update UI state with result + gallery
      const dataUrl = `data:image/png;base64,${data.imageBase64}`;
      setResultImage(dataUrl);
      setGallery((prev) => [dataUrl, ...prev].slice(0, 6));
      setStepIndex(2);
    } catch (err) {
      setError(err.message || "Failed to generate image.");
    } finally {
      setIsGenerating(false);
    }
  };

  // Ensure background image exists if a prompt is selected
  const ensureBackgroundImage = async () => {
    if (!backgroundPrompt) return "";
    setBackgroundImage("");

    const response = await fetch(`${API_BASE}/background`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(API_KEY ? { "x-api-key": API_KEY } : {})
      },
      body: JSON.stringify({
        project: "project-a250af6f-f898-4bf6-872",
        location: BACKGROUND_LOCATION,
        model: IMAGEN_MODEL_ID,
        prompt: backgroundPrompt
      })
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || "Failed to generate background.");
    }

    const data = await response.json();
    if (!data.imageBase64) {
      throw new Error("No background image returned from the server.");
    }
    const dataUrl = `data:image/png;base64,${data.imageBase64}`;
    setBackgroundImage(dataUrl);
    return dataUrl;
  };

  // Download a gallery item
  const downloadImage = (dataUrl, filename) => {
    const link = document.createElement("a");
    link.href = dataUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="kiosk">
      <header className="kiosk-header">
        <div>
          <p className="eyebrow">Virtual Try-On</p>
          <h1>Mirror Demo</h1>
          <p className="privacy-note">
            Images are processed in-memory for this demo and are not stored.
          </p>
        </div>
        <div className="step-indicator">
          <span className="step-count">
            Step {stepIndex + 1} of {STEPS.length}
          </span>
          <span className="step-name">{STEPS[stepIndex]}</span>
        </div>
      </header>

      <nav className="progress-bar" aria-label="Progress">
        {STEPS.map((step, index) => (
          <button
            key={step}
            type="button"
            className={`progress-step ${index === stepIndex ? "active" : ""} ${!isStepEnabled(index) ? "disabled" : ""
              }`}
            onClick={() => isStepEnabled(index) && setStepIndex(index)}
            disabled={!isStepEnabled(index)}
          >
            <span className="dot" />
            <span className="label">{step}</span>
          </button>
        ))}
      </nav>

      <main className="journey">
        <section
          className={`step ${stepIndex === 0 ? "active" : ""}`}
          id="step-garment"
        >
          <div className="step-inner">
            <div className="panel">
              <p className="step-label">Step 1</p>
              <h2>Choose your garment</h2>
              <p className="muted">
                Select one garment to try on. Tap to continue.
              </p>
              <div className="card-grid">
                {SAMPLE_GARMENTS.map((garment) => (
                  <button
                    key={garment.id}
                    className={
                      selectedGarment?.id === garment.id
                        ? "card selected"
                        : "card"
                    }
                    type="button"
                    onClick={() => {
                      setSelectedGarment(garment);
                    }}
                  >
                    <img src={garment.src} alt={garment.label} />
                    <span>{garment.label}</span>
                  </button>
                ))}
              </div>
              <div className="cta-row">
                <button
                  className="primary"
                  type="button"
                  disabled={!canProceedFromGarment}
                  onClick={() => setStepIndex(1)}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </section>

        <section
          className={`step ${stepIndex === 1 ? "active" : ""}`}
          id="step-photo"
        >
          <div className="step-inner">
            <div className="panel">
              <p className="step-label">Step 2</p>
              <h2>Add your photo</h2>
              <p className="muted">Use the camera or upload an image.</p>
              <div className="upload">
                {personPhoto ? (
                  <div className="photo-preview">
                    <img src={personPhoto} alt="Preview" className="preview" />
                    <button
                      type="button"
                      className="photo-clear"
                      onClick={() => setPersonPhoto("")}
                      aria-label="Remove photo"
                    >
                      ×
                    </button>
                  </div>
                ) : (
                  <div className="preview-slot">
                    <div className={`camera-preview ${isCameraOpen ? "open" : ""}`}>
                      <video ref={videoRef} playsInline muted />
                      {isCameraOpen && (
                        <div className="camera-controls">
                          <button
                            type="button"
                            className="primary"
                            onClick={capturePhoto}
                          >
                            Capture Photo
                          </button>
                          <button
                            type="button"
                            className="secondary"
                            onClick={stopCamera}
                          >
                            Close Camera
                          </button>
                        </div>
                      )}
                      <canvas ref={canvasRef} className="hidden-canvas" />
                    </div>
                    {!isCameraOpen && (
                      <div className="placeholder">No photo yet</div>
                    )}
                  </div>
                )}
                <div className="upload-actions">
                  {!isCameraOpen && (
                    <button
                      type="button"
                      className="button"
                      onClick={startCamera}
                    >
                      Open Camera
                    </button>
                  )}
                  <label className="button">
                    Upload Photo
                    <input
                      type="file"
                      accept="image/*"
                      capture="environment"
                      onChange={(event) => onPhotoUpload(event.target.files?.[0])}
                    />
                  </label>
                  {personPhoto && (
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setPersonPhoto("")}
                    >
                      Retake
                    </button>
                  )}
                  {cameraStatus && (
                    <span className="camera-status">{cameraStatus}</span>
                  )}
                </div>
                {/* camera preview now lives in the main preview slot */}
              </div>
              <div className="background-inline">
                <p className="muted">Optional background</p>
                <select
                  className="select"
                  value={backgroundPrompt}
                  onChange={(event) => {
                    setBackgroundPrompt(event.target.value);
                  }}
                >
                  {BACKGROUND_OPTIONS.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="cta-row">
                <button
                  className="secondary"
                  type="button"
                  onClick={() => setStepIndex(0)}
                >
                  Back
                </button>
                <button
                  className="primary"
                  type="button"
                  disabled={!canGenerate}
                  onClick={handleGenerate}
                >
                  {isGenerating ? "Generating..." : "Generate Try-On"}
                </button>
                {!canProceedFromGarment && (
                  <span className="hint">Select a garment to continue</span>
                )}
                {canProceedFromGarment && !canProceedFromPhoto && (
                  <span className="hint">Add a photo to continue</span>
                )}
              </div>
            </div>
          </div>
        </section>

        <section
          className={`step ${stepIndex === 2 ? "active" : ""}`}
          id="step-result"
        >
          <div className="step-inner">
            <div className="panel">
              <p className="step-label">Step 3</p>
              <h2>See your result</h2>
              <p className="muted">
                Results are session-only and not stored.
              </p>
              <div className="result">
                {isGenerating ? (
                  <div className="result-loading">
                    <div className="spinner" />
                    <p className="muted">Generating your try-on...</p>
                  </div>
                ) : resultImage ? (
                  <img src={resultImage} alt="Try-on result" />
                ) : (
                  <div className="placeholder">
                    Your result will appear here.
                  </div>
                )}
              </div>
              <div className="gallery">
                <div>
                  <h3>Gallery</h3>
                  <p className="muted">Session only. Images are not stored.</p>
                </div>
                <div className="gallery-actions">
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => setGallery([])}
                    disabled={gallery.length === 0}
                  >
                    Clear gallery
                  </button>
                </div>
                <div className="gallery-strip">
                  {gallery.length === 0 && (
                    <span className="muted">No images yet.</span>
                  )}
                  {gallery.map((image, index) => (
                    <button
                      key={index}
                      className="gallery-item"
                      type="button"
                      onClick={() =>
                        downloadImage(image, `try_on_${index + 1}.png`)
                      }
                    >
                      <img src={image} alt={`Result ${index + 1}`} />
                      <span>Download</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="cta-row">
                <button
                  className="secondary"
                  type="button"
                  onClick={() => setStepIndex(1)}
                >
                  Back
                </button>
                <button
                  className="primary"
                  type="button"
                  onClick={() => {
                    setPersonPhoto("");
                    setBackgroundPrompt("");
                    setResultImage("");
                    setGallery([]);
                    setStepIndex(0);
                  }}
                >
                  Start over
                </button>
              </div>
              {error && <p className="error">{error}</p>}
            </div>
          </div>
        </section>
      </main>

      {isGenerating && (
        <div className="overlay" role="status" aria-live="polite">
          <div className="overlay-card">
            <div className="spinner" />
            <h2>Generating your try-on</h2>
            <p className="muted">This takes a few moments.</p>
          </div>
        </div>
      )}
    </div>
  );
}
