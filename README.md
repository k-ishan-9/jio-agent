# 🤖 Jio AI Agent — Production-Grade Hybrid RAG Customer Assistant

An enterprise-ready, high-performance RAG (Retrieval-Augmented Generation) AI assistant designed specifically for Reliance Jio telecom, broadband, business services, and digital apps ecosystem.

---

## 🎯 Problem Statement & Focus Area

### What Problem Does It Solve?
Telecom and digital service providers like Reliance Jio offer hundreds of complex, constantly changing prepaid/postpaid plans, fiber broadband tiers, OTT bundle packages, enterprise IT solutions, and device troubleshooting guides. Standard customer support channels face key challenges:

1. **LLM Hallucinations on Numeric Data**: Generic AI models often fabricate plan pricing, data limits, speeds, and OTT offerings, causing customer mistrust and compliance risks.
2. **High Latency & Expensive API Calls**: Querying an LLM for repetitive customer queries (e.g., "what's the cheapest 5G plan?") wastes latency and budget.
3. **Unstructured FAQ & Policy Complexity**: Telecom support requires handling both strict tabular database lookups (price filters) and semantic document searches (porting policies, device guides).
4. **Safety & Off-Topic Risks**: AI assistants on public websites are vulnerable to prompt injections, competitor inquiries (e.g., Airtel/Vi), or general off-topic abuse.

### Target Focus
The Jio AI Agent is built to serve as an intelligent, secure, 24/7 conversational frontline support system for Jio users. It focuses on:
- **Instant Plan Discovery**: Precise multi-criteria search (price, data, speed, validity, OTT bundle).
- **FAQ & Policy Assistance**: Instant semantic lookup for JioFiber, AirFiber, SIM porting (MNP), eSIM, and app features.
- **Enterprise & App Ecosystem**: Direct guidance on JioBusiness solutions and Jio App suite (JioCinema, JioTV, JioSaavn, JioCloud).

---

## 🌟 Why It Is Different & Better

Compared to conventional AI chatbots or standard RAG setups:

| Feature / Metric | Conventional Chatbots | Standard RAG Systems | **Jio AI Agent** |
| :--- | :--- | :--- | :--- |
| **Numeric Accuracy (Plans)** | ❌ Hallucinates rates & specs | ⚠️ Unreliable chunk search | **✅ 100% Deterministic SQLite SQL Queries** |
| **Knowledge Coverage** | ❌ Static text only | ⚠️ Single vector index | **✅ Dual-Retrieval: SQL + FAISS Hybrid** |
| **Response Latency** | 🐌 2–5 seconds per response | 🐌 Always hits LLM | **⚡ Near 0ms via Semantic FAISS Caching** |
| **Topic Safety & Guardrails** | ❌ Basic keyword block | ⚠️ Prompt engineering only | **🛡️ Dual-Tier LLM Intent Guardrails & Sanitization** |
| **Query Precision** | ❌ Raw natural language | ❌ Raw natural language | **🧠 Intelligent Query Rewriting Engine** |
| **User Experience** | 💬 Plain text box | 💬 Simple chatbot component | **🎨 Full Jio-Themed Portal + Floating AI Widget** |

---

## ⚡ Key Features

- **Dual-Retrieval Architecture (SQL + Vector RAG)**:
  - **Tool 1: `find_jio_plans`** — Filter SQLite database by price range (`min_price`/`max_price`), data GB (`min_data_gb`), fiber speed (`min_speed_mbps`), validity, and included OTT subscriptions (Netflix, Prime Video, Disney+ Hotstar).
  - **Tool 2: `search_jio_faq_and_info`** — FAISS Vector Search over normalized embeddings for policies, MNP, troubleshooting, Jio Apps, and JioBusiness.
- **Google Agent Development Kit (ADK) Integration**: Native agent orchestration with tool routing, state tracking, and session memory (`InMemorySessionService`).
- **High-Performance Semantic Cache (`SemanticCache`)**:
  - Custom FAISS Inner-Product index (0.88 cosine similarity threshold).
  - Bypasses LLM generation for cached/similar questions, dramatically reducing API costs and serving responses in milliseconds.
  - Automatic 24-Hour Time-To-Live (TTL) expiration.
- **AI Safety & Security Guardrails (`evaluate_intent`)**:
  - Automatically filters competitor references (Airtel, Vi, BSNL), prompt injection attempts, and off-topic requests.
  - Context-aware intent verification using multi-turn conversation history.
- **Search Query Optimizer (`rewrite_query`)**:
  - Strips filler words and transforms conversational queries into optimized search keywords prior to DB/FAISS retrieval.
- **Production FastAPI Server & Web Portal**:
  - Modern, responsive Jio-themed web application (`/`, `/prepaid`, `/fiber`, `/business`, `/apps`).
  - Sleek floating chat widget with direct API integration.
- **Async Concurrency & Resiliency**:
  - Non-blocking I/O via `asyncio.to_thread` for SQLite and FAISS operations.
  - Exponential backoff retries for API resilience (`ServerError` handling).
  - Byte-serialization monkeypatch for telemetry logs.
- **Automated Evaluation Suite**: End-to-end question test bench (`evaluation/run_eval.py`).
- **Container Ready**: Full `Dockerfile` and `docker-compose.yml` for seamless cloud deployment.

---

## 🏗️ How It Was Built (Architecture)

```
                       ┌─────────────────────────┐
                       │   User Query / Web UI   │
                       └────────────┬────────────┘
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │   FastAPI Web Server    │
                       └────────────┬────────────┘
                                    │
                         ┌──────────┴──────────┐
                         │  1. Semantic Cache  ├────── [Hit] ──► Return Cached Answer (⚡ <10ms)
                         └──────────┬──────────┘
                                    │ [Miss]
                                    ▼
                         ┌─────────────────────┐
                         │  2. AI Guardrails   ├────── [Block] ─► Return Refusal Message
                         └──────────┬──────────┘
                                    │ [Safe]
                                    ▼
                         ┌─────────────────────┐
                         │ 3. Query Rewriter   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │  4. Google ADK      │
                         │     Agent Engine    │
                         └──────┬──────────┬───┘
                                │          │
           ┌────────────────────┘          └────────────────────┐
           ▼                                                    ▼
┌─────────────────────────┐                          ┌──────────────────────────┐
│  Tool 1: SQL Retrieval  │                          │ Tool 2: Vector Retrieval │
│   (jio_plans.db SQLite) │                          │ (FAISS + Gemini Embed)   │
└─────────────────────────┘                          └──────────────────────────┘
```

### Technical Workflow
1. **Incoming Request**: User submits a question via the web interface or `/ask` endpoint.
2. **Semantic Cache Lookup**: Query embedding is generated via `text-embedding-004` and compared against cached embeddings in FAISS. On match (similarity ≥ 0.88), cached response is returned instantly.
3. **Guardrail Intent Check**: On cache miss, LLM guardrails inspect the query and conversation history for safety and topic relevance. Off-topic/competitor queries are blocked gracefully.
4. **Query Optimization**: LLM query rewriter strips conversational noise and reformulates keywords.
5. **ADK Agent Execution**: Google ADK Agent analyzes intent and selects the optimal tool (`find_jio_plans`, `search_jio_faq_and_info`, or both).
6. **Data Retrieval & Answer Generation**: The agent synthesizes ground-truth data from SQLite and FAISS into a natural response with source citations.
7. **Cache Invalidation & Save**: The response is saved to the semantic cache with timestamp for future instantaneous resolution.

---

## 💻 Tech Stack Used

- **AI & Agent Framework**:
  - [Google Agent Development Kit (ADK)](https://github.com/google/adk) — Agent runner, session management, tool binding.
  - [Google GenAI SDK](https://pypi.org/project/google-genai/) — Gemini 2.5/Gemini models & `text-embedding-004`.
- **Retrieval & Storage**:
  - **SQLite3** — Structured plan relational storage.
  - **FAISS (Facebook AI Similarity Search)** — In-memory vector database for FAQ retrieval & semantic caching.
- **Backend & Server**:
  - **FastAPI** — High-performance asynchronous REST API framework.
  - **Uvicorn** — ASGI web server implementation.
  - **Pydantic v2** — Data validation and schema enforcement.
  - **Celery & Redis** — Async task queue background worker support.
- **Frontend UI**:
  - HTML5, Vanilla CSS, JS (Modern Jio-branded design, responsive layout, glassmorphism chat widget).
- **DevOps & Testing**:
  - **Docker & Docker Compose** — Containerized environment.
  - **Python `unittest` / Requests** — End-to-end evaluation suite.

---

## 📂 Project Structure

```
jio_ai_agent/
├── README.md                 # Comprehensive project documentation
├── MIGRATION_CHECKLIST.md    # Production deployment checklist
├── requirements.txt          # Python dependencies
├── Dockerfile                # Docker container configuration
├── docker-compose.yml        # Docker Compose configuration
├── .env.example              # Environment variables template
├── config.py                 # Configuration settings & paths
├── agent/
│   ├── adk_agent.py          # ADK Agent definition & tool binding
│   ├── guardrails.py         # AI safety & intent filter
│   └── semantic_cache.py     # FAISS semantic query cache
├── retrieval/
│   └── tools.py              # SQL & Vector search tool implementations
├── api/
│   └── main.py               # FastAPI application server & routes
├── static/                   # Jio-themed frontend HTML/CSS/JS web pages
├── evaluation/
│   └── run_eval.py           # Automated evaluation suite
├── tasks/                    # Background task definitions (Celery)
└── data/                     # Database storage (SQLite & FAISS indices)
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Google Gemini API Key

### 1. Clone & Setup Virtual Environment
```bash
git clone https://github.com/k-ishan-9/jio-agent.git
cd jio-agent

python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and enter your Google API Key:
```bash
cp .env.example .env
```
Edit `.env`:
```env
GOOGLE_API_KEY="your_actual_google_gemini_api_key_here"
```

### 4. Verify Data Files
Ensure `jio_plans.db` and `jio_faiss_index/` exist in `data/`:
```bash
python -c "from config import verify_data_files_exist; verify_data_files_exist(); print('Data files verified successfully!')"
```

---

## 🏃 Running the Application

### Start Web Application & API
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
- **Web App Landing Page**: Open [http://localhost:8000](http://localhost:8000) in your browser.
- **Prepaid Plans Page**: [http://localhost:8000/prepaid](http://localhost:8000/prepaid)
- **JioFiber Page**: [http://localhost:8000/fiber](http://localhost:8000/fiber)
- **JioBusiness Page**: [http://localhost:8000/business](http://localhost:8000/business)
- **Jio Apps Page**: [http://localhost:8000/apps](http://localhost:8000/apps)

### API Example (`POST /ask`)
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the best 5G prepaid plan under 500 rupees with Netflix?"}'
```

---

## 🧪 Running Evaluations
Run the automated evaluation benchmark against the running server:
```bash
python evaluation/run_eval.py --base-url http://localhost:8000
```

---

## 🐳 Docker Deployment

### Build and Run with Docker Compose
```bash
docker-compose up --build
```
The application will be accessible at `http://localhost:8000`.