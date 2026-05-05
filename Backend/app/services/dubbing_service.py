import os
import asyncio
import logging
import torch
import soundfile as sf
import numpy as np
from typing import List, Dict, Any
from pathlib import Path
from engine import NeuralSyncEngine, ScholarShield
from app.services.rag_service import rag_service
from app.core.config import settings
from app.core.gpu_manager import gpu_manager

logger = logging.getLogger("dubbing-service")

class DubbingService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DubbingService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.output_dir = Path("static/dubbed_audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Models
        self.translator = None
        self.shield = ScholarShield()
        self.tts_model = None
        self.tts_tokenizer = None
        
        self._initialized = True

    def _load_translator(self):
        if self.translator is None:
            logger.info("Loading IndicTrans2 Translator Engine...")
            self.translator = NeuralSyncEngine()

    def _load_tts(self, lang: str = "hi"):
        """Dynamically load the appropriate TTS model for the target language."""
        lang_model_map = {
            "hi": "facebook/mms-tts-hin",
            "mr": "facebook/mms-tts-mar",
            "ta": "facebook/mms-tts-tam",
            "gu": "facebook/mms-tts-guj",
            "te": "facebook/mms-tts-tel",
            "kn": "facebook/mms-tts-kan"
        }
        model_id = lang_model_map.get(lang, "facebook/mms-tts-hin")
        
        # If model is already loaded and is the right one, skip
        if hasattr(self, '_current_model_id') and self._current_model_id == model_id and self.tts_model:
            return

        from transformers import VitsModel, AutoTokenizer
        logger.info(f"Loading/Switching TTS Model: {model_id}...")
        self.tts_tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.tts_model = VitsModel.from_pretrained(model_id).to(self.device)
        self._current_model_id = model_id

    async def translate_and_dub_parallel(
        self, segments: List[Dict[str, Any]], target_languages: List[str],
        audio_path: str = None  # optional: source audio path for context
    ) -> Dict[str, Any]:
        """
        Translates and generates audio for multiple languages in parallel.
        Uses a Semaphore to limit concurrent processing.
        """
        # 1. Group segments by sentence to ensure natural 'flow' and prevent 'breaking' sentences
        grouped_segments = self._group_segments_by_sentence(segments)
        logger.info(f"Grouped {len(segments)} segments into {len(grouped_segments)} sentence blocks for natural flow.")

        self._load_translator()
        
        loop = asyncio.get_event_loop()
        # Limit to 2 concurrent languages to avoid OOM on 6GB VRAM
        vram_semaphore = asyncio.Semaphore(2)
        
        # 1. OPTIMIZATION: Extract texts and run RAG & Shielding ONLY ONCE for the original source!
        texts = [seg["text"] for seg in segments]
        source_blob = " ".join(texts)
        
        # Retrieval & Refinement (Contextual Intelligence)
        context = await loop.run_in_executor(None, rag_service.retrieve_context, source_blob)
        refined_source = await loop.run_in_executor(None, rag_service.refine_with_granite, source_blob, context)
        
        # Transcript-Driven Self-Knowledge Retrieval: Store for future context
        await loop.run_in_executor(None, rag_service.store_transcript_context, refined_source)
        
        # Shielding Math/STEM Phonics
        masked_text, shield_mapping = getattr(self.shield, "shield_text")(refined_source)
        
        # Parallel execution across languages with semaphore protection
        async def semi_limited_process(lang):
            async with vram_semaphore:
                return await self._process_single_language(grouped_segments, lang, masked_text, shield_mapping)

        tasks = []
        for lang in target_languages:
            tasks.append(semi_limited_process(lang))
        
        results = await asyncio.gather(*tasks)
        
        # Map results back to language codes
        return {
            lang: res 
            for lang, res in zip(target_languages, results) 
            if res and res.get("audio_path")
        }

    def _clean_hallucinations(self, text: str) -> str:
        """Removes repetitive noise loops while preserving valid sentences."""
        if not text: return ""
        import re
        pattern = r"((?:एस|स|S|s)\.?\s*){5,}"
        cleaned = re.sub(pattern, " ", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"(\b\w+\b\s*)\1{6,}", r"\1", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    async def _process_single_language(self, segments: List[Dict[str, Any]], target_lang: str, masked_text: str, shield_mapping: dict) -> Dict[str, str]:
        """Process translation and TTS for a single target language."""
        try:
            logger.info(f"Processing language: {target_lang}")
            
            # Map target_lang to IndicTrans2 language code format
            it2_lang = "hin_Deva" 
            lang_map = {
                "hi": "hin_Deva", "mr": "mar_Deva", "gu": "guj_Gujr",
                "ta": "tam_Taml", "te": "tel_Telu", "kn": "kan_Knda"
            }
            if target_lang in lang_map:
                it2_lang = lang_map[target_lang]
            
            # 1. RAG-Enhanced Translation
            # OPTIMIZATION: Translate segments as a batch to preserve mapping exactly
            masked_segments = []
            # We assume domain is passed or detected; for demo reliability, we can detect it here if not passed
            from app.services.sbert_service import domain_service
            # Detect domain for the whole project context if needed, or use a default
            project_domain = domain_service.detect_domain(" ".join([s["text"] for s in segments]))
            
            for seg in segments:
                m_t, _ = getattr(self.shield, "shield_text")(seg["text"], domain=project_domain)
                masked_segments.append(m_t)
            
            raw_translated_segments = await self.translator.translate_batch(masked_segments, src_lang="eng_Latn", tgt_lang=it2_lang)
            
            # Step D: Unshielding
            translated_texts = []
            for raw_t in raw_translated_segments:
                final_t = getattr(self.shield, "unshield_text")(raw_t, shield_mapping)
                translated_texts.append(final_t)
            
            from indic_transliteration import sanscript
            transliteration_map = {
                "ta": sanscript.TAMIL, "gu": sanscript.GUJARATI,
                "te": sanscript.TELUGU, "kn": sanscript.KANNADA
            }
            
            cleaned_texts = []
            for t in translated_texts:
                cleaned = self._clean_hallucinations(t)
                if target_lang in transliteration_map and len(cleaned) > 1:
                    cleaned = sanscript.transliterate(cleaned, sanscript.DEVANAGARI, transliteration_map[target_lang])
                cleaned_texts.append(cleaned if len(cleaned) > 1 else "")
                
            full_translated_transcript = " ".join([t for t in cleaned_texts if t.strip()])
            
            # 2. TTS Generation (Locked for GPU safety)
            await gpu_manager.acquire_gpu(f"TTS_{target_lang}")
            try:
                self._load_tts(target_lang)
                seg_info = []
                for idx, text in enumerate(cleaned_texts):
                    if not text.strip():
                        continue
                    start = segments[idx].get("start", 0)
                    end = segments[idx].get("end", start + 2.0)
                    audio_path, duration = await self._generate_tts(text, target_lang, f"seg_{idx}")
                    seg_info.append({
                        "path": audio_path, 
                        "start": start, 
                        "end": end,
                        "duration": duration
                    })
            finally:
                gpu_manager.release_gpu()
            
            # 3. Concatenate and align audio using FFmpeg
            final_audio_path = self.output_dir / f"final_{target_lang}_{os.urandom(4).hex()}.wav"
            duration = segments[-1].get("end", 60) if segments else 60
            
            success = await self._merge_segments_to_final_track(seg_info, str(final_audio_path), duration)
            
            if success:
                logger.info(f"Completed dubbing for {target_lang}")
                return {
                    "audio_path": str(final_audio_path),
                    "transcript": full_translated_transcript
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to process language {target_lang}: {e}")
            return None

    async def _generate_tts(self, text: str, lang: str, label: str) -> tuple[str, float]:
        """Generates TTS for a single piece of text. Returns (path, duration)."""
        output_file = self.output_dir / f"{lang}_{label}.wav"
        try:
            if not text.strip():
                sf.write(str(output_file), np.zeros(8000), 16000)
                return str(output_file), 0.5

            from transformers import VitsModel, AutoTokenizer
            inputs = self.tts_tokenizer(text, return_tensors="pt").to(self.device)
            with torch.no_grad():
                output = self.tts_model(**inputs).waveform

            wav_data = output.cpu().numpy().squeeze()
            target_sr = 22050
            if self.tts_model.config.sampling_rate != target_sr:
                import librosa
                wav_data = librosa.resample(wav_data, orig_sr=self.tts_model.config.sampling_rate, target_sr=target_sr)
            
            sf.write(str(output_file), wav_data, target_sr)
            duration = len(wav_data) / target_sr
            return str(output_file), duration
        except Exception as e:
            logger.error(f"TTS generation failed for {label}: {e}")
            sf.write(str(output_file), np.zeros(8000), 16000)
            return str(output_file), 0.5

    async def _merge_segments_to_final_track(self, seg_info: List[Dict], output_path: str, total_duration: float) -> bool:
        """Align multiple audio segments with ABSOLUTE positioning (adelay + amix)."""
        import subprocess
        
        if not seg_info:
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=22050:cl=mono", "-t", str(total_duration), output_path]
            subprocess.run(cmd, check=True, capture_output=True)
            return True

        try:
            inputs = []
            filter_chains = []
            amix_labels = []
            
            for i, seg in enumerate(seg_info):
                if not seg["path"] or not os.path.exists(seg["path"]):
                    continue
                
                inputs.append("-i")
                inputs.append(seg["path"])
                input_idx = len(inputs) // 2 - 1 
                
                start_ms = int(seg["start"] * 1000)
                # Strict target window
                target_dur = max(0.1, seg["end"] - seg["start"])
                gen_dur = seg["duration"]
                
                # Speed up or slow down to FIT the exact window
                tempo = gen_dur / target_dur
                tempo = max(0.6, min(2.0, tempo))
                
                label = f"a{i}"
                # 1. Fit to duration 2. Smooth fade out 3. Clean up 4. Delay to start
                filter_chains.append(
                    f"[{input_idx}:a]atempo={tempo:.2f},afade=t=out:st={target_dur-0.05:.3f}:d=0.05,"
                    f"volume=2.5,adelay={start_ms}|{start_ms}[{label}]"
                )
                amix_labels.append(f"[{label}]")
            
            # Combine all delayed segments. amix with normalize=0 keeps original volumes.
            # Then apply compand (compressor) for 'broadcast' quality and a limiter to prevent clipping.
            amix_str = f"{''.join(amix_labels)}amix=inputs={len(amix_labels)}:normalize=0,compand=attacks=0:points=-80/-80|-20/-10|0/-3|20/-3,alimiter=limit=0.9,apad=whole_dur={total_duration:.2f}[out]"
            filter_chains.append(amix_str)
            
            command = ["ffmpeg", "-y"] + inputs + ["-filter_complex", ";".join(filter_chains), "-map", "[out]", "-c:a", "pcm_s16le", output_path]
            
            logger.info(f"Running Absolute Aligner: {' '.join(command)}")
            subprocess.run(command, check=True, capture_output=True, text=True)
            return True
        except Exception as e:
            logger.error(f"Failed to merge segments: {e}")
            return False

    def _group_segments_by_sentence(self, segments: List[Dict]) -> List[Dict]:
        """Merges chopped Whisper segments into complete sentence blocks for natural TTS flow."""
        grouped = []
        if not segments: return grouped
        
        current_group = segments[0].copy()
        
        for i in range(1, len(segments)):
            seg = segments[i]
            prev_text = current_group["text"].strip()
            # If segments are consecutive (< 0.5s gap) AND the previous doesn't end in sentence terminal
            is_consecutive = (seg["start"] - current_group["end"] < 0.5)
            is_fragment = not prev_text.endswith(('.', '?', '!', ':', ';'))
            
            if is_consecutive and is_fragment:
                current_group["text"] += " " + seg["text"]
                current_group["end"] = seg["end"]
            else:
                grouped.append(current_group)
                current_group = seg.copy()
                
        grouped.append(current_group)
        return grouped

dubbing_service = DubbingService()
