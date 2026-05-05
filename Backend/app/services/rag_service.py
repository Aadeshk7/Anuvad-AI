import os
import glob
import logging
import torch
import faiss
import numpy as np
from pathlib import Path
from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForCausalLM
from app.core.config import settings

logger = logging.getLogger("rag-service")

# Canonical domain names — must match SBERT service output
KNOWN_DOMAINS = ["STEM", "Humanities", "Business", "General"]


class RAGService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RAGService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Root knowledge base — flat files (legacy / shared)
        self.kb_path = Path("knowledge_base")
        self.kb_path.mkdir(exist_ok=True)

        # ── NEW: Per-domain sub-directories ───────────────────────────────────
        # Structure:
        #   knowledge_base/
        #       STEM/          ← auto-created
        #       Humanities/    ← auto-created
        #       Business/      ← auto-created
        #       General/       ← auto-created
        for domain in KNOWN_DOMAINS:
            (self.kb_path / domain).mkdir(exist_ok=True)

        # Models
        self.embed_model = None
        self.llm_model = None
        self.llm_tokenizer = None
        self.llm_load_err = None  # Track load errors

        # ── NEW: One FAISS index + document list per domain ───────────────────
        # { "STEM": faiss.Index, "Humanities": faiss.Index, ... }
        self.domain_indices: dict = {}
        self.domain_documents: dict = {d: [] for d in KNOWN_DOMAINS}

        # Legacy flat index (for backward compat with flat kb root files)
        self.index = None
        self.documents = []

        self._initialized = True

    # ─────────────────────────────────────────────────────────────────────────
    # Model Loaders
    # ─────────────────────────────────────────────────────────────────────────

    def _load_embed_model(self):
        if self.embed_model is None:
            logger.info("Loading SBERT for RAG indexing...")
            try:
                # SBERT is small enough for GPU if we use it intermittently 
                # but let's keep it on CPU to maximize VRAM for core dubbing
                self.embed_model = SentenceTransformer('all-MiniLM-L6-v2', device="cpu")
            except Exception as e:
                logger.error(f"Failed to load RAG embed model: {e}")
                self.embed_model = "FAILED"

    def _load_llm_model(self):
        if self.llm_model is None:
            model_name = "ibm-granite/granite-3.0-2b-instruct"
            logger.info(f"Loading IBM Granite model: {model_name} (CPU ONLY)...")

            import time, traceback
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    hf_token = os.getenv("HF_TOKEN")
                    self.llm_tokenizer = AutoTokenizer.from_pretrained(
                        model_name,
                        token=hf_token
                    )
                    # Force CPU to save VRAM for transcription and translation
                    self.llm_model = AutoModelForCausalLM.from_pretrained(
                        model_name,
                        token=hf_token,
                        trust_remote_code=True,
                        low_cpu_mem_usage=True,
                        torch_dtype=torch.float32,
                        device_map="cpu"  # Fixed: string instead of dict
                    )
                    logger.info("✅ Granite model loaded successfully on CPU.")
                    self.llm_load_err = None
                    break
                except Exception as e:
                    self.llm_load_err = str(e) + "\n" + traceback.format_exc()
                    logger.error(f"Attempt {attempt + 1} failed to load Granite: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(1)
                    else:
                        self.llm_model = "FAILED"
                        logger.error(f"Granite failed to load after {max_retries} attempts. Error:\n{self.llm_load_err}")
        elif self.llm_model == "FAILED":
            return

    # ─────────────────────────────────────────────────────────────────────────
    # ── NEW: Build FAISS index for a single domain ────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────

    def _build_domain_index(self, domain: str):
        """
        Scan knowledge_base/<domain>/ for all .txt and .pdf files,
        chunk them, embed with SBERT, and build a FAISS IndexFlatL2.
        Overwrites any existing index for that domain.
        """
        self._load_embed_model()
        if self.embed_model == "FAILED":
            logger.warning(f"[{domain}] Skipping FAISS build — embed model failed.")
            return

        domain_path = self.kb_path / domain
        files = (glob.glob(str(domain_path / "*.txt")) +
                 glob.glob(str(domain_path / "*.pdf")))

        docs = []
        for file_path in files:
            try:
                text = ""
                if file_path.endswith(".txt"):
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read()
                elif file_path.endswith(".pdf"):
                    reader = PdfReader(file_path)
                    for page in reader.pages:
                        text += page.extract_text() + "\n"

                chunks = [c.strip() for c in text.split("\n\n") if len(c.strip()) > 20]
                docs.extend(chunks)
                logger.info(f"[{domain}] Indexed {len(chunks)} chunks from {os.path.basename(file_path)}")
            except Exception as e:
                logger.error(f"[{domain}] Failed to index {file_path}: {e}")

        if not docs:
            logger.warning(f"[{domain}] No documents found — index not built.")
            self.domain_indices[domain] = None
            self.domain_documents[domain] = []
            return

        self.domain_documents[domain] = docs
        embeddings = self.embed_model.encode(docs)
        dim = embeddings.shape[1]

        idx = faiss.IndexFlatL2(dim)
        idx.add(np.array(embeddings).astype('float32'))

        self.domain_indices[domain] = idx
        logger.info(f"[{domain}] FAISS index built with {len(docs)} vectors.")

    # ─────────────────────────────────────────────────────────────────────────
    # ── UPDATED: Full knowledge base indexing (flat root + all domains) ───────
    # ─────────────────────────────────────────────────────────────────────────

    def auto_index_knowledge_base(self):
        """
        1. Index all flat files in knowledge_base/ root (legacy support).
        2. Index each domain sub-directory separately.
        """
        self._load_embed_model()
        if self.embed_model == "FAILED":
            logger.warning("RAG indexing skipped due to model loading failure.")
            return

        # ── Legacy flat index (root .txt / .pdf) ──────────────────────────────
        files = (glob.glob(str(self.kb_path / "*.txt")) +
                 glob.glob(str(self.kb_path / "*.pdf")))
        new_docs = []
        for file_path in files:
            try:
                text = ""
                if file_path.endswith(".txt"):
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read()
                elif file_path.endswith(".pdf"):
                    reader = PdfReader(file_path)
                    for page in reader.pages:
                        text += page.extract_text() + "\n"

                chunks = [c.strip() for c in text.split("\n\n") if len(c.strip()) > 20]
                new_docs.extend(chunks)
            except Exception as e:
                logger.error(f"Failed to index flat file {file_path}: {e}")

        if new_docs:
            self.documents = new_docs
            embeddings = self.embed_model.encode(new_docs)
            self.index = faiss.IndexFlatL2(embeddings.shape[1])
            self.index.add(np.array(embeddings).astype('float32'))
            logger.info(f"[Root] FAISS flat index built with {len(new_docs)} vectors.")

        # ── Domain-partitioned indices ─────────────────────────────────────────
        for domain in KNOWN_DOMAINS:
            self._build_domain_index(domain)

    # ─────────────────────────────────────────────────────────────────────────
    # ── UPDATED: Retrieve context — domain-aware with root fallback ───────────
    # ─────────────────────────────────────────────────────────────────────────

    def retrieve_context(self, query: str, k: int = 3, domain: str = "General") -> str:
        """
        Retrieve top-k most relevant chunks.
        Priority:  domain-specific index  →  root flat index  →  empty string

        k=3 means: return the 3 most semantically similar text chunks
                   from the knowledge base to use as context for Granite.
        """
        self._load_embed_model()
        if self.embed_model == "FAILED":
            return ""

        query_vector = self.embed_model.encode([query]).astype('float32')

        # ── Try domain-specific index first ───────────────────────────────────
        domain_idx = self.domain_indices.get(domain)
        domain_docs = self.domain_documents.get(domain, [])

        if domain_idx is not None and len(domain_docs) > 0:
            real_k = min(k, len(domain_docs))
            distances, indices = domain_idx.search(query_vector, real_k)
            chunks = [domain_docs[i] for i in indices[0] if i != -1 and i < len(domain_docs)]
            if chunks:
                logger.info(f"[RAG] Retrieved {len(chunks)} chunks from [{domain}] index.")
                return "\n---\n".join(chunks)

        # ── Fallback to flat root index ────────────────────────────────────────
        if self.index is not None and self.documents:
            real_k = min(k, len(self.documents))
            distances, indices = self.index.search(query_vector, real_k)
            chunks = [self.documents[i] for i in indices[0] if i != -1]
            if chunks:
                logger.info(f"[RAG] Fallback: Retrieved {len(chunks)} chunks from [root] index.")
                return "\n---\n".join(chunks)

        logger.warning("[RAG] No context retrieved from any index.")
        return ""

    # ─────────────────────────────────────────────────────────────────────────
    # ── UPDATED: Store new transcript → correct domain folder → re-index ──────
    # ─────────────────────────────────────────────────────────────────────────

    def store_transcript_context(self, transcript: str, domain: str = "General"):
        """
        Save processed transcript to knowledge_base/<domain>/
        and immediately rebuild the FAISS index for that domain.
        This makes the system self-learning and domain-aware.
        """
        import uuid
        if not transcript.strip():
            return

        # Validate domain
        if domain not in KNOWN_DOMAINS:
            domain = "General"

        # Save to domain-specific subfolder
        file_id = str(uuid.uuid4())[:8]
        domain_path = self.kb_path / domain
        domain_path.mkdir(exist_ok=True)
        file_path = domain_path / f"transcript_{file_id}.txt"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(transcript)

        logger.info(f"[RAG] Stored transcript to [{domain}] folder: {file_path}")

        # Re-index ONLY the affected domain (efficient — not full rebuild)
        self._build_domain_index(domain)
        logger.info(f"[RAG] FAISS index for [{domain}] updated with new transcript.")

    # ─────────────────────────────────────────────────────────────────────────
    # Granite Refinement (unchanged)
    # ─────────────────────────────────────────────────────────────────────────

    def refine_with_granite(self, transcript: str, context: str) -> str:
        """Use IBM Granite to standardize and refine the transcript based on context."""
        self._load_llm_model()
        if self.llm_model is None or self.llm_model == "FAILED":
            logger.warning(f"Granite refinement skipped. Reason: {self.llm_load_err or 'Model not loaded'}")
            return transcript

        try:
            prompt = f"""<|system|>
You are an expert AI educational content editor for a multilingual video localization system.
Your task is to refine raw speech-to-text transcripts into accurate, structured educational content.

You MUST:
- Correct grammar and spelling errors
- Convert phonetic mathematical expressions into proper notation (e.g., "x square" -> x²)
- Improve clarity for educational use
- Preserve meaning exactly
- Use provided context only if relevant
- Do NOT translate. Only refine and correct.
<|user|>
Raw Transcript:
{transcript}

Retrieved Context (RAG):
{context if context else 'No context available.'}

Refine the transcript into a clean, structured educational script.
<|assistant|>
"""

            inputs = self.llm_tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=2048
            ).to("cpu")

            with torch.no_grad():
                outputs = self.llm_model.generate(
                    **inputs,
                    max_new_tokens=300,
                    temperature=0.2,
                    do_sample=True,
                    pad_token_id=self.llm_tokenizer.eos_token_id,
                    eos_token_id=self.llm_tokenizer.eos_token_id,
                )

            # Decode only the newly generated tokens (not the prompt)
            input_length = inputs["input_ids"].shape[1]
            new_tokens = outputs[0][input_length:]
            refined_text = self.llm_tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
            
            if not refined_text:
                logger.warning("Granite returned empty output; using original transcript.")
                return transcript
                
            logger.info("✅ Granite refinement complete.")
            return refined_text

        except Exception as e:
            logger.error(f"Granite generation failed: {e}")
            return transcript


rag_service = RAGService()
