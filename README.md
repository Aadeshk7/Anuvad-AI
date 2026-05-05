# Anuvad AI - Localize Engine 🌐

[![Status: Active](https://img.shields.io/badge/Status-Active-success.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-20232A?style=flat&logo=react&logoColor=61DAFB)](https://reactjs.org/)
[![MongoDB](https://img.shields.io/badge/MongoDB-4EA94B?style=flat&logo=mongodb&logoColor=white)](https://www.mongodb.com/)

An advanced, AI-powered video localization engine designed to seamlessly transcribe, translate, and dub educational and informational video content. Built with parallel neural processing, RAG-enhanced translation techniques, and a scalable architecture to provide high-quality localized output.

## 🚀 Key Features

- **Automated Video Transcription:** Leveraging robust Whisper models to generate highly accurate captions from video audio.
- **RAG-Enhanced Translation:** High-fidelity translation powered by IndicTrans2 / IBM Granite models combined with a FAISS-based Vector Database retrieval (RAG pipeline) to ensure domain-specific accuracy (e.g., STEM terminology).
- **Parallel Neural Processing:** Highly optimized processing queue using `asyncio` and sophisticated GPU memory management for multi-stage inference without out-of-memory (OOM) errors.
- **AI Voice Dubbing:** Synthesizes translated text back into natural-sounding speech.
- **Secure Authentication:** Integrated JWT/session-based user authentication using MongoDB, restricting high-cost localization tasks to authorized users.
- **Rich Dashboard UI:** A beautiful, responsive frontend built with React, Tailwind CSS, and Framer Motion, featuring glassmorphism elements, dynamic micro-animations, and real-time processing status.

---

## 🛠️ Technology Stack

**Frontend:**
- React 19 (via Vite)
- TypeScript
- Tailwind CSS
- Framer Motion (Animations)
- React Router DOM
- Lucide React (Icons)

**Backend:**
- Python 3.10+
- FastAPI
- FFmpeg (Audio/Video extraction & manipulation)
- Whisper (Speech-to-Text)
- IndicTrans2 / IBM Granite (Machine Translation)
- FAISS (Vector Database for RAG)
- MongoDB / Motor (Async Database / Auth)

---

## 🏗️ System Architecture

1. **Upload & Extract:** User uploads an `.mp4` video. The backend validates the session and uses `FFmpeg` to extract the audio track.
2. **Transcription:** The audio is processed by the Whisper model to generate text segments with timestamps.
3. **Retrieval-Augmented Translation:** The source text queries the FAISS vector database for contextual knowledge (like technical dictionaries), and the generative model (IndicTrans/Granite) translates the text into the target language.
4. **Synthesis (Dubbing):** The translated text is passed to an AI TTS module, matching the generated audio lengths to the original timestamps.
5. **Final Output:** The user receives real-time progress updates on the frontend, and can download the fully translated audio track.

---

## ⚙️ Installation & Setup

### Prerequisites
- Python 3.10 or higher
- Node.js (v18 or higher)
- FFmpeg installed and added to system PATH
- MongoDB running locally or via MongoDB Atlas
- CUDA Toolkit (if running on a dedicated NVIDIA GPU for inference)

### 1. Clone the Repository
```bash
git clone https://github.com/Aadeshk7/Anuvad-AI.git
cd Anuvad-AI
```

### 2. Backend Setup
```bash
cd Backend

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup Environment Variables
# Create a .env file in the Backend directory and add necessary variables:
# MONGODB_URI=mongodb://localhost:27017/
# JWT_SECRET=your_secret_key
```

### 3. Frontend Setup
```bash
cd ../Frontend

# Install dependencies
npm install
```

---

## 💻 How to Run Locally

To start the full application, run the backend and frontend servers simultaneously.

**Start the FastAPI Backend:**
```bash
cd Backend
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```
*The backend API will be available at `http://localhost:8000`*

**Start the React Frontend:**
```bash
cd Frontend
npm run dev
```
*The UI will be accessible at `http://localhost:5173`*

---

## 🤝 Contributing
Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/Aadeshk7/Anuvad-AI/issues).

## 📄 License
This project is open-source and available under the [MIT License](LICENSE).
