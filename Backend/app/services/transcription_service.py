"""
Optimized Transcription Service
================================
Mirrors the Colab multimedia_pipeline.py logic for speed + accuracy:

1. Language detection on the FIRST 30-second clip only (fast spectral probe).
2. Short probe transcription (best_of=1, beam_size=3) for text-based fallback.
3. Final transcription with confirmed language (best_of=3, beam_size=5).
4. All CPU-bound work runs in a thread pool via run_in_executor.
5. Deterministic langdetect (seed=0).
"""

from __future__ import annotations

import os
import time
import uuid
import logging
import asyncio
from functools import partial
from typing import Any, Dict, Tuple, Optional

import numpy as np
import whisper
from bson import ObjectId
from langdetect import DetectorFactory, LangDetectException, detect

from app.utils.audio_utils import extract_audio
from app.models.response_model import TranscriptionResponse
from app.core.config import get_whisper_model
from app.core.database import db_manager
from app.services.rag_service import rag_service
from app.services.sbert_service import domain_service
from app.services.dubbing_service import dubbing_service
from app.core.gpu_manager import gpu_manager
from app.ffmpeg_utils import merge_to_ott_video

# Deterministic langdetect (matches Colab seed=0)
DetectorFactory.seed = 0

logger = logging.getLogger("transcription-service")

SUPPORTED_LANGUAGES = {"hi", "mr", "gu", "ta", "te", "kn", "en"}


# ---------------------------------------------------------------------------
# Helpers (pure, synchronous — safe to run in thread pool)
# ---------------------------------------------------------------------------

def _safe_text_language(sample_text: str) -> Optional[str]:
    """Return langdetect result or None if text is too short / detection fails."""
    cleaned = sample_text.strip()
    if len(cleaned) < 10:
        return None
    try:
        return detect(cleaned)
    except LangDetectException:
        return None


def _detect_language(audio_path: str, model: whisper.Whisper) -> Dict[str, Any]:
    """
    Detect source language using the user's robust two-pass method.
    1. Spectral Whisper probabilities.
    2. Full auto-detect transcription to extract a text sample.
    3. langdetect on the text sample.
    4. Combined decision for the most accurate language.
    """
    # Step 1: 30-second clip for fast spectral probabilities
    audio = whisper.load_audio(audio_path)
    audio = whisper.pad_or_trim(audio)
    mel = whisper.log_mel_spectrogram(audio).to(model.device)
    mel_batched = mel.unsqueeze(0)

    _, probs_raw = model.detect_language(mel_batched)

    if isinstance(probs_raw, list) and len(probs_raw) > 0 and isinstance(probs_raw[0], dict):
        probs: Dict[str, float] = probs_raw[0]
    elif isinstance(probs_raw, list):
        probs = {lang: float(p) for lang, p in probs_raw}
    else:
        probs = probs_raw

    whisper_lang = max(probs, key=probs.get)
    whisper_conf = float(probs.get(whisper_lang, 0.0))
    logger.info(f"Whisper spectral: lang={whisper_lang} conf={whisper_conf:.4f}")

    # Step 2: Fast first-pass auto-detect transcription on the 30s padded chunk
    logger.info("Running 30s fast-pass auto-detect transcription for text sample...")
    result = model.transcribe(
        audio, 
        task="transcribe",
        temperature=0.0,
        condition_on_previous_text=False,
        fp16=(str(model.device) != "cpu")
    )
    text_sample = str(result.get("text", ""))[:500]

    # Step 3: Text-based langdetect
    try:
        text_lang = detect(text_sample)
    except:
        text_lang = "unknown"
    logger.info(f"Text-based lang: {text_lang}")

    # Step 4: Final Language Decision
    def final_language_decision(w_lang, t_lang, p):
        if p.get(w_lang, 0) > 0.6 and w_lang in SUPPORTED_LANGUAGES:
            return w_lang
        if t_lang in SUPPORTED_LANGUAGES:
            return t_lang
        return w_lang

    final_lang = final_language_decision(whisper_lang, text_lang, probs)
    logger.info(f"✅ FINAL DETECTED LANGUAGE: {final_lang}")

    return {
        "final_language": final_lang,
        "whisper_language": whisper_lang,
        "whisper_confidence": whisper_conf,
        "text_language": text_lang,
        "decision": "two_pass_robust",
    }


def _transcribe_audio(audio_path: str, language: str, model: whisper.Whisper) -> Dict[str, Any]:
    """
    Final full transcription constrained to the exact detected language,
    optimized for speed without losing core text accuracy.
    """
    result = model.transcribe(
        audio_path,
        language=language,
        task="transcribe",
        fp16=(str(model.device) != "cpu"),
        temperature=(0.0, 0.2),
        best_of=2,
        beam_size=2,
        condition_on_previous_text=False
    )
    # Clean up transcript (strip blank lines)
    raw = str(result.get("text", ""))
    clean = "\n".join(line.strip() for line in raw.splitlines() if line.strip())
    result["clean_text"] = clean
    return result


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class TranscriptionService:
    def __init__(self):
        self.model = get_whisper_model()
        logger.info(
            f"TranscriptionService ready — device={self.model.device}"
        )

    async def transcribe_video(
        self, video_path: str, project_id: Optional[str] = None
    ) -> TranscriptionResponse:
        """
        Full 4-Stage Neural Pipeline:
          1. AI Perception (Extraction + Transcription)
          2. Neural Intelligence (RAG + SBERT Refinement)
          3. Synthesis & Localization (Parallel Translation + TTS)
          4. Finalization (OTT Muxing)
        """
        start_time = time.monotonic()
        projects_col = db_manager.get_projects_collection()
        loop = asyncio.get_event_loop()
        current_stage = "Initialization"  # Ensure always defined for error handler

        # Prepare unique filenames
        audio_id = str(uuid.uuid4())
        audio_filename = f"{audio_id}.wav"
        static_audio_dir = os.path.join("static", "audio")
        os.makedirs(static_audio_dir, exist_ok=True)
        audio_path = os.path.join(static_audio_dir, audio_filename)
        audio_url = f"/static/audio/{audio_filename}"

        async def update_status(prog: float, stage_name: str, msg: str = ""):
            if project_id:
                await projects_col.update_one(
                    {"_id": ObjectId(project_id)},
                    {"$set": {
                        "progress": prog,
                        "stage": stage_name,
                        "timeRemaining": msg or f"Executing {stage_name}..."
                    }}
                )

        try:
            # ── Step 1: Audio Extraction (0%) ─────────────────────────
            await update_status(5, "Audio Extraction", "Extracting high-fidelity WAV...")
            await loop.run_in_executor(None, extract_audio, video_path, audio_path)

            # ── Step 2: Language Detection (12.5%) ────────────────────
            await update_status(12.5, "Language Detection", "Probing spectral frequencies...")
            await gpu_manager.acquire_gpu("Whisper_Detect")
            try:
                detect_fn = partial(_detect_language, audio_path, self.model)
                detection = await loop.run_in_executor(None, detect_fn)
                final_lang = detection["final_language"]
            finally:
                gpu_manager.release_gpu()
            
            # ── Step 3: Domain Detection (25%) ────────────────────────
            await update_status(25, "Domain Detection", "Analyzing semantic context...")
            await loop.run_in_executor(None, rag_service.auto_index_knowledge_base)
            
            # ── Step 4: Transcription Generation (37.5%) ──────────────
            current_stage = "Transcription Generation"
            await update_status(37.5, current_stage, f"Generating {final_lang} script...")
            await gpu_manager.acquire_gpu("Whisper_Transcribe")
            try:
                transcribe_fn = partial(_transcribe_audio, audio_path, final_lang, self.model)
                result = await loop.run_in_executor(None, transcribe_fn)
                transcript_text = result.get("clean_text", result.get("text", "")).strip()
            finally:
                gpu_manager.release_gpu()

            # ── Step 5: Parallel Translating (50%) ────────────────────
            current_stage = "Parallel Translating"
            await update_status(50, current_stage, "Neural machine translation...")
            
            # ── Step 6: Transcript Refinement (62.5%) ─────────────────
            current_stage = "Transcript Refinement"
            await update_status(62.5, current_stage, "Granite RAG optimization...")
            # Detect domain FIRST so we can fetch domain-specific RAG context
            domain = domain_service.detect_domain(transcript_text)
            logger.info(f"[Pipeline] Detected domain: {domain}")

            # Retrieve context from domain-specific FAISS index
            context = rag_service.retrieve_context(transcript_text[:500], domain=domain)
            refined_transcript = await loop.run_in_executor(
                None, rag_service.refine_with_granite, transcript_text, context
            )
            # If refinement failed or was skipped, use original
            if not refined_transcript:
                refined_transcript = transcript_text
            
            # ── Step 7: Audio Generation (75%) ────────────────────────
            current_stage = "Audio Generation"
            await update_status(75, current_stage, "Synthesizing localized voices...")
            project_data = await projects_col.find_one({"_id": ObjectId(project_id)})
            target_langs = project_data.get("target_languages", ["hi"])
            segments = result.get("segments", [])
            # Store refined transcript into the correct domain folder → re-indexes only that domain
            await loop.run_in_executor(
                None, rag_service.store_transcript_context, refined_transcript, domain
            )

            audio_results = await dubbing_service.translate_and_dub_parallel(segments, target_langs, audio_path)

            # ── Step 8: Mux with Video (87.5%) ────────────────────────
            await update_status(87.5, "Mux with Video", "Finalizing OTT multi-track...")
            
            # Extract paths and transcripts from the results
            audio_paths = {lang: res["audio_path"] for lang, res in audio_results.items()}
            translations = {lang: res["transcript"] for lang, res in audio_results.items()}

            output_dir = os.path.join("static", "videos")
            os.makedirs(output_dir, exist_ok=True)
            output_video_path = os.path.join(output_dir, f"ott_{project_id}.mp4")
            
            mux_success = await loop.run_in_executor(
                None, merge_to_ott_video, video_path, audio_paths, output_video_path
            )
            
            if not mux_success or not os.path.exists(output_video_path):
                raise RuntimeError("Failed to generate final multi-track video file.")

            # Convert audio_paths to URLs for frontend consumption
            track_urls = {
                lang: "/" + path.replace("\\", "/") if path else None 
                for lang, path in audio_paths.items()
            }

            processing_time = time.monotonic() - start_time
            if project_id:
                await projects_col.update_one(
                    {"_id": ObjectId(project_id)},
                    {"$set": {
                        "status": "Completed",
                        "progress": 100,
                        "stage": "Finalized",
                        "video_url": f"/static/videos/ott_{project_id}.mp4",
                        "audio_tracks": track_urls,
                        "translations": translations,
                        "transcript": refined_transcript,
                        "domain": domain,
                        "lang": final_lang,
                        "detected_language": final_lang,
                        "timeRemaining": "0s",
                    }},
                )

            return TranscriptionResponse(
                detected_language=final_lang,
                confidence=round(detection.get("whisper_confidence", 0), 3),
                transcript=refined_transcript,
                processing_time=round(processing_time, 2),
                audio_url=audio_url,
            )

        except Exception as e:
            logger.exception(f"[{project_id}] Pipeline failed: {e}")
            if project_id:
                # Use current_stage to pinpoint failure
                error_msg = f"Error [{current_stage}]: {str(e)[:100]}"
                await projects_col.update_one(
                    {"_id": ObjectId(project_id)},
                    {"$set": {
                        "status": "Failed",
                        "stage": error_msg,
                        "timeRemaining": "Failed",
                        "progress": 0,
                    }},
                )
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except OSError:
                    pass
            raise


transcription_service = TranscriptionService()
