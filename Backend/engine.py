import os
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class ScholarShield:
    def __init__(self):
        # Neural-Sync strictly shields Universal Mathematical symbols and formulas.
        self.math_regex = re.compile(
            r'\\\w+({[^}]+})*|'                     # LaTeX commands
            r'\b(?:[a-zA-Z0-9]+\b\s*[\+\-\*/=]\s*)+\b[a-zA-Z0-9]+\b|' # Standard equations
            r'\bdy/dx\b|\$[^$]+\$|'                   # Leibniz notation and inline math
            r'\b[a-zA-Z](?:\^[\d\w]+)\b'             # Superscripts like x^2
        )
        
        # Dynamic Tech Keywords based on Domain
        self.domain_glossaries = {
            "STEM": self._load_glossary("STEM"),
            "Business": self._load_glossary("Business"),
            "Humanities": self._load_glossary("Humanities"),
            "General": {}
        }

    def _load_glossary(self, domain: str):
        """Dynamically loads glossaries from knowledge_base/<domain>/*_glossary.txt"""
        glossary = {}
        kb_path = os.path.join("knowledge_base", domain)
        if not os.path.exists(kb_path):
            return glossary

        # Search for any file ending in _glossary.txt
        import glob
        glossary_files = glob.glob(os.path.join(kb_path, "*_glossary.txt"))
        
        # Hardcoded core STEM pedagogy for absolute reliability in demo
        if domain == "STEM":
            glossary = {
                "differentiation": "डिफरेंशिएशन", 
                "integration": "इंटीग्रेशन",
                "calculus": "कॅल्क्युलस",
                "integral": "इंटीग्रल",
                "derivative": "डेरिव्हेटिव्ह",
                "formula": "फॉर्म्युला"
            }

        for gf in glossary_files:
            try:
                with open(gf, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("-") and ":" in line:
                            parts = line.split(":")
                            term = parts[0].strip("- ").lower()
                            # We keep the English term as the translation to force phonetic consistency in IndicTrans
                            glossary[term] = term.capitalize() 
            except Exception as e:
                print(f"Failed to load glossary {gf}: {e}")
        
        return glossary

    def shield_text(self, text: str, domain: str = "STEM"):
        mapping = {}
        counter = 0
        masked_text = text

        # 1. Shield Math Formulas (MATH_N)
        for match in self.math_regex.finditer(masked_text):
            formula = match.group(0)
            if formula not in mapping.values(): 
                placeholder = f"MATH_{counter}"
                mapping[placeholder] = formula
                masked_text = masked_text.replace(formula, placeholder)
                counter += 1
                
        # 2. Shield Technical Keywords from the detected Domain
        tech_keywords = self.domain_glossaries.get(domain, {})
        if tech_keywords:
            tech_regex = re.compile(rf"\b({'|'.join(re.escape(k) for k in tech_keywords.keys())})\b", re.IGNORECASE)
            for match in tech_regex.finditer(masked_text):
                term = match.group(0)
                placeholder = f"TECH_{counter}"
                # Use phonetic transliteration if provided, otherwise keep term original
                mapping[placeholder] = tech_keywords.get(term.lower(), term)
                masked_text = masked_text.replace(term, placeholder)
                counter += 1

        return masked_text, mapping

    def _to_indic(self, num_str):
        indic_map = str.maketrans("0123456789", "०१२३४५६७८९")
        return num_str.translate(indic_map)

    def unshield_text(self, text: str, mapping: dict):
        if not mapping:
            return text
            
        unmasked = text
        
        # 1. Capture all types of markers the AI might have outputted.
        # We look for something that looks like a marker (TECH/MATH/मॅथ/टेक) followed by any numeric-like string.
        marker_pattern = re.compile(
            r'(?:MATH|मॅथ|मैथ|टेक|टेक्|TECH|TECHNOLOGY)\s*[:\-\s_]*\s*([0-9०१२३४५६७८९]{1,3})', 
            re.IGNORECASE
        )
        
        # 2. Get all original placeholders in the order they were created.
        placeholders = list(mapping.keys())
        
        # 3. Find all matches in the translated text.
        matches = list(marker_pattern.finditer(unmasked))
        
        # 4. Sequential replacement: Replace the Nth match with the Nth placeholder.
        # We work backwards to avoid offset issues with string slicing.
        for i in range(min(len(matches), len(placeholders)) - 1, -1, -1):
            match = matches[i]
            placeholder = placeholders[i]
            unmasked = unmasked[:match.start()] + placeholder + unmasked[match.end():]

        # 5. Restore original terms from the standardized placeholders
        for placeholder, original in mapping.items():
            unmasked = unmasked.replace(placeholder, original)
            
        return unmasked

class NeuralSyncEngine:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(NeuralSyncEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name="ai4bharat/indictrans2-en-indic-1B"):
        if self._initialized:
            return
            
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        from app.core.gpu_manager import gpu_manager
        self.gpu_manager = gpu_manager
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32
        
        print(f"Loading Neural Engine ({model_name}) on {self.device} with {self.dtype}...")
        hf_token = os.getenv("HF_TOKEN")
        
        # Memory optimization for 6GB GPUs
        model_kwargs = {
            "token": hf_token,
            "trust_remote_code": True,
        }
        if self.device == "cuda":
            model_kwargs["device_map"] = "auto"
            model_kwargs["torch_dtype"] = torch.float16
        
        try:
            print(f"Loading Primary Neural Engine ({model_name}) on {self.device}...")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, **model_kwargs)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name, **model_kwargs)
        except Exception as e:
            print(f"Primary engine failed (Gated/Auth issue): {e}")
            fallback_model = "facebook/m2m100_418M"
            print(f"Loading Fallback Neural Engine ({fallback_model}) on {self.device}...")
            self.tokenizer = AutoTokenizer.from_pretrained(fallback_model)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(fallback_model).to(self.device)
            self.is_fallback = True
        else:
            self.is_fallback = False
            
        self._initialized = True
        
    async def translate_batch(self, texts: list, src_lang: str, tgt_lang: str, batch_size=8):
        """Highly optimized batch translation for neural parallelization."""
        import torch
        if not texts:
            return []
            
        await self.gpu_manager.acquire_gpu("TranslationEngine")
        try:
            # Handle M2M100 Fallback language mapping
            if getattr(self, 'is_fallback', False):
                it2_to_m2m = {
                    "eng_Latn": "en", "hin_Deva": "hi", "mar_Deva": "mr", 
                    "tam_Taml": "ta", "tel_Telu": "te", "kan_Knda": "kn", "guj_Gujr": "gu"
                }
                src_lang = it2_to_m2m.get(src_lang, "en")
                tgt_lang = it2_to_m2m.get(tgt_lang, "hi")
                self.tokenizer.src_lang = src_lang
            else:
                self.tokenizer.src_lang = src_lang
                self.tokenizer.tgt_lang = tgt_lang
            
            translations = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i+batch_size]
                formatted_batch = [f"{src_lang} {tgt_lang} {text}" for text in batch] if not self.is_fallback else batch
                
                inputs = self.tokenizer(
                    formatted_batch, 
                    padding=True, 
                    truncation=True, 
                    max_length=256,
                    return_tensors="pt"
                ).to(self.device)
                
                with torch.no_grad():
                    forced_bos_id = None
                    if self.is_fallback:
                        try:
                            forced_bos_id = self.tokenizer.get_lang_id(tgt_lang)
                        except:
                            # If language is missing in fallback, default to Hindi or skip
                            forced_bos_id = self.tokenizer.get_lang_id("hi") 
                    elif hasattr(self.tokenizer, 'lang_code_to_id') and tgt_lang in self.tokenizer.lang_code_to_id:
                        forced_bos_id = self.tokenizer.lang_code_to_id[tgt_lang]
                        
                    generated_tokens = self.model.generate(
                        **inputs,
                        forced_bos_token_id=forced_bos_id,
                        max_length=256,
                        num_beams=4,
                        do_sample=False
                    )
                    
                decoded = self.tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)
                translations.extend(decoded)
            return translations
        finally:
            self.gpu_manager.release_gpu()
