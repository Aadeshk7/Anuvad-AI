import os
import logging
import numpy as np
import librosa
import soundfile as sf
from sklearn.cluster import KMeans
from typing import List, Dict, Any

logger = logging.getLogger("speaker-service")

class SpeakerService:
    def __init__(self):
        self.n_speakers_limit = 2 # Reduced for stability in demo videos
        self.profile_memory = {} # For smoothing

    def analyze_speakers(self, audio_path: str, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyzes the original audio segments to identify unique speakers and their tone profiles.
        Adds 'speaker_id' and 'tone_profile' to each segment.
        """
        if not os.path.exists(audio_path) or not segments:
            return segments

        try:
            logger.info(f"Analyzing speakers for {len(segments)} segments...")
            y, sr = librosa.load(audio_path, sr=16000)
            
            features = []
            valid_indices = []

            for i, seg in enumerate(segments):
                start = seg.get("start", 0)
                end = seg.get("end", start + 1)
                
                # Extract chunk
                start_sample = int(start * sr)
                end_sample = int(end * sr)
                chunk = y[start_sample:end_sample]
                
                if len(chunk) < 1600: # Ignore very short segments (<0.1s)
                    continue
                
                # Extract Tone Features
                # 1. MFCC (Timbre/Identity)
                mfcc = librosa.feature.mfcc(y=chunk, sr=sr, n_mfcc=13)
                mfcc_mean = np.mean(mfcc, axis=1)
                
                # 2. Pitch (F0) - Fundamental Frequency
                pitches, magnitudes = librosa.piptrack(y=chunk, sr=sr)
                pitch = self._get_median_pitch(pitches, magnitudes)
                
                # 3. Spectral Centroid (Brightness)
                centroid = np.mean(librosa.feature.spectral_centroid(y=chunk, sr=sr))
                
                # Combined feature vector for clustering
                # We weight MFCCs heavily for identity, and centroid for tone
                feat_vec = np.concatenate([mfcc_mean, [centroid / 1000.0]])
                features.append(feat_vec)
                valid_indices.append(i)
                
                # Store raw profile for later matching
                segments[i]["raw_tone"] = {
                    "pitch": float(pitch),
                    "brightness": float(centroid),
                    "energy": float(np.sqrt(np.mean(chunk**2)))
                }

            if not features:
                return segments

            # Cluster speakers
            # For short demos, we usually have 1-2 speakers. 
            # High n_clusters causes 'speaker jumping'.
            n_samples = len(features)
            n_clusters = 1
            if n_samples > 10:
                n_clusters = 2 # Most demos have 1 or 2 speakers
            
            kmeans = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
            labels = kmeans.fit_predict(features)

            # --- PROFILE SMOOTHING & OUTLIER REMOVAL ---
            # Calculate cluster centers for stable profiles
            cluster_profiles = {}
            for label in range(n_clusters):
                cluster_indices = [valid_indices[i] for i, l in enumerate(labels) if l == label]
                if not cluster_indices: continue
                
                avg_pitch = np.median([segments[idx]["raw_tone"]["pitch"] for idx in cluster_indices])
                avg_brightness = np.median([segments[idx]["raw_tone"]["brightness"] for idx in cluster_indices])
                
                cluster_profiles[label] = {
                    "pitch": float(avg_pitch),
                    "brightness": float(avg_brightness)
                }

            for idx, label in zip(valid_indices, labels):
                segments[idx]["speaker_id"] = int(label)
                # Apply smoothed cluster profile instead of raw segment profile
                # This prevents the 'jittery' voice changes
                segments[idx]["raw_tone"]["pitch"] = cluster_profiles[label]["pitch"]
                segments[idx]["raw_tone"]["brightness"] = cluster_profiles[label]["brightness"]
                
            logger.info(f"Identified {n_clusters} potential speaker profiles.")
            return segments

        except Exception as e:
            logger.error(f"Speaker analysis failed: {e}")
            return segments

    def _get_median_pitch(self, pitches, magnitudes):
        """Extracts the dominant pitch from piptrack output."""
        pitch_values = []
        for t in range(pitches.shape[1]):
            index = magnitudes[:, t].argmax()
            pitch = pitches[index, t]
            if pitch > 0:
                pitch_values.append(pitch)
        return np.median(pitch_values) if pitch_values else 150.0

speaker_service = SpeakerService()
