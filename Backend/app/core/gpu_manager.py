import asyncio
import torch
import logging
from typing import Optional

logger = logging.getLogger("gpu-manager")

class GPUManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GPUManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.lock = asyncio.Lock()
        self.vram_semaphore = asyncio.Semaphore(1) # Strict 1-at-a-time for heavy GPU tasks
        self.current_model: Optional[str] = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._initialized = True
        logger.info(f"GPUManager initialized on {self.device}")

    async def acquire_gpu(self, model_id: str):
        """Acquire the GPU for a specific model, potentially offloading the previous one."""
        await self.vram_semaphore.acquire()
        logger.info(f"GPU Acquired by: {model_id}")
        
        if self.current_model and self.current_model != model_id:
            logger.info(f"Switching GPU context from {self.current_model} to {model_id}")
            # Clear cache to make room
            if self.device == "cuda":
                torch.cuda.empty_cache()
        
        self.current_model = model_id

    def release_gpu(self):
        """Release the GPU semaphore."""
        logger.info(f"GPU Released by: {self.current_model}")
        self.vram_semaphore.release()

    def check_vram(self):
        """Utility to log current VRAM usage."""
        if self.device == "cuda":
            allocated = torch.cuda.memory_allocated() / 1024**2
            reserved = torch.cuda.memory_reserved() / 1024**2
            logger.info(f"VRAM Status: Allocated={allocated:.2f}MB, Reserved={reserved:.2f}MB")
            return allocated, reserved
        return 0, 0

gpu_manager = GPUManager()
