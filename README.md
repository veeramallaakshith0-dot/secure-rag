# Secure Enterprise RAG

Local-first document search and question answering with FastAPI, PostgreSQL, Qdrant, SentenceTransformers, Ollama, and React/Vite.

## Public demo link at no hosting cost

This project can be shared for a temporary demo through a Cloudflare Quick Tunnel. It serves the built React site and API from one local origin, keeps PostgreSQL, Qdrant, Ollama, uploads, and the model on your laptop, and binds the Qdrant/Ollama ports to localhost. Anyone with the temporary URL can visit and create an account; account and document permissions still apply.

This is a laptop-hosted demo, not an always-on production deployment. Keep the laptop awake, connected to the internet, PostgreSQL running, Docker Desktop open, and both terminal windows open. The tunnel gives a temporary random URL that changes when it restarts. Cloudflare describes Quick Tunnels as for testing/development and does not guarantee uptime. Model answers are limited by the laptop’s CPU/GPU and available memory.

1. Start Docker Desktop and make sure the PostgreSQL 17 Windows service is running.
2. Open PowerShell in the project folder and run `.\start_public_demo.ps1`. Keep that window open; wait for Uvicorn to report that it is running.
3. Install `cloudflared` from the [official Windows download page](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/).
4. In a second PowerShell window, run `cloudflared tunnel --url http://127.0.0.1:8000`.
5. Copy the `https://...trycloudflare.com` link shown in the tunnel window and share it. Stop the public link with Ctrl+C in the tunnel window; stop the app with Ctrl+C in the first window.

Public registration is limited to eight new accounts per source address per hour in demo mode. API documentation is disabled in that mode. Do not use this temporary public demo for sensitive or regulated documents. For a stable permanent site, use a managed Cloudflare Tunnel on a domain and plan for persistent hosting, backups, access controls, and ongoing hosting costs.

## Start the local services

The project already uses your Windows PostgreSQL 17 service and `secure_rag_db` database. Start Qdrant and Ollama with Docker Desktop:

```cmd
cd /d "%USERPROFILE%\OneDrive\Desktop\secure-enterprise-rag"
docker compose up -d
```

Download the local answer model once:

```cmd
docker compose exec ollama ollama pull qwen2.5:3b
```

The embedding model (`sentence-transformers/all-MiniLM-L6-v2`) downloads from Hugging Face the first time a document is indexed. After it is cached, embedding runs locally.

## Configure the administrator

Edit `backend/.env` and add these settings, choosing your own unique password of at least 12 characters:

```dotenv
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_EMAIL=admin@example.com
INITIAL_ADMIN_PASSWORD=choose-a-unique-password
QDRANT_URL=http://localhost:6333
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
```

Keep the existing `DATABASE_URL` and `SECRET_KEY` values. The initial admin is created only if its username/email are unused. Remove `INITIAL_ADMIN_PASSWORD` after the first successful startup. Alternatively, leave `QDRANT_URL` unset to use Qdrant's persistent local embedded mode.

## Run the backend

Open PowerShell in the project folder and run:

```powershell
cd backend
..\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

This starts Uvicorn with the project's virtual-environment Python, so it uses the dependencies installed for this project. It also avoids PowerShell's script-execution restriction, which can prevent `venv\Scripts\Activate.ps1` from running. If your terminal is not already in the project folder, first run:

```powershell
cd "$env:USERPROFILE\OneDrive\Desktop\secure-enterprise-rag"
```

API docs: <http://127.0.0.1:8000/docs>
Service checks:

- `http://127.0.0.1:8000/health` confirms that the API process is responding.
- `http://127.0.0.1:8000/health/ready` checks PostgreSQL, Qdrant, and whether the configured Ollama model is installed. The website refreshes this status every 30 seconds while signed in.

## Run the web app

Open a second Command Prompt:

```cmd
cd /d "%USERPROFILE%\OneDrive\Desktop\secure-enterprise-rag\frontend"
npm install
npm run dev
```

Open <http://127.0.0.1:5173>, sign in with the initial admin, and upload a PDF, DOCX, TXT, or Markdown file. Scanned PDFs can be OCR-indexed when Tesseract OCR is installed and available on PATH; ordinary text-based PDFs do not need it. Ask questions from the indexed documents. Your 50 most recent questions and their source passages are saved privately to your account; use Clear history in the workspace to remove them. A new registration creates a standard user account.

## OCR for scanned PDFs

PDFs with extractable text work without additional setup. For image-only/scanned pages, install the Tesseract OCR engine for Windows, ensure `tesseract.exe` is on PATH, and restart the backend terminal. The app detects pages with little extracted text and applies local English OCR automatically. OCR language and DPI can be adjusted with `OCR_LANGUAGE` and `OCR_DPI`; set `OCR_ENABLED=false` to disable OCR. OCR runs on the machine and may take longer for large scans.

## Check answer quality with a question set

Copy `backend/evaluation/rag_cases.example.json` to a new JSON file and replace its sample question, expected phrases, and expected source with examples based on uploaded documents. From the `backend` folder, run:

```powershell
..\venv\Scripts\python.exe scripts\evaluate_rag.py evaluation\my_cases.json --username YOUR_USERNAME --report evaluation\my_report.json
```

The report gives source match rate and exact expected-phrase coverage. These are quick screening heuristics, not proof that an answer is correct; review each answer and cited passage yourself. The script uses the selected account's existing permissions and does not add questions to saved history.

## Admin audit history

Administrators can use **View audit history** under Account access to review recent successful sign-ins, registrations, role/status changes, document uploads/deletions, and share creation/redemption/revocation. It records event summaries and IDs, not question text, document content, passwords, or raw share keys. The `audit_events` table is created automatically at backend startup.

## Security and data

- Standard users can search, list, and delete only their own documents. Admins can access all uploaded documents, review saved user question history, and inspect the workspace audit history from Account access.
- Search filters are applied in Qdrant using the authenticated account ID.
- Original uploads are stored under `backend/data/uploads`; vectors are stored in Qdrant or `backend/data/qdrant` when embedded mode is used.
- The API accepts files up to 20 MB and rejects duplicate files per account.
- The bundled Vite server allows local development origins only.

## Local diagnostics

Backend logs include request IDs, route templates, response codes, total time, and separate embedding, retrieval, and answer-generation timings. They do not include question text, document contents, passwords, or access tokens. API responses also include an `X-Request-ID` header that can be used to locate the matching log entry.
Users can rate each saved answer as helpful or not helpful and change the rating later. Ratings are visible to the account owner; the admin history view excludes ratings.
## Sign-in protection

After five failed sign-in attempts for the same account from the same device within 15 minutes, further attempts are temporarily rate-limited. The server stores a hash of the account/device key with failure timestamps; it does not store attempted passwords. Old attempt records are removed as new failed sign-ins are recorded.
## Document tags

Add up to eight comma-separated tags when uploading a document. Use the workspace filters to narrow the document list or limit question retrieval to one tag. Tags are stored with each account’s document and vector payload. Existing documents without tags remain available under All documents.
## Share a document with another account

A document owner or admin can create a one-time share key from the document list. The key expires after seven days and is stored only as a hash. The recipient signs in, enters the key under **Access a shared document**, and receives read/search access to that document. Shared documents are read-only for recipients. The owner or an admin can revoke an unused key or remove access later from the document’s **Access** controls.