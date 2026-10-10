# Requirements and setup

Everything you need to install and run WITNESS on your own computer. The commands below are for **Windows 11 with PowerShell**, which is where the project was built and tested. The code is plain Python and a prebuilt web app, so macOS and Linux should work with the equivalent commands, but we have not tested them.

> **What you need in one line:** a computer with a recent GPU (8 GB of video memory is comfortable), Python, Git, LM Studio, a free Gemini API key, and about 6 GB of free disk space.

---

## 1. What you need

### Hardware
| | Minimum | Recommended (what we used) |
|---|---|---|
| **GPU** | Optional. A CPU-only run works but the local writer is much slower | NVIDIA GPU with 8 GB of video memory (RTX 5050 Laptop) |
| **RAM** | 8 GB | 16 GB |
| **Disk** | 6 GB free | 10 GB free (models, Python packages, caches) |
| **Internet** | Needed for setup, and for the Gemini judge during a live check | Replay mode and the local models work offline |

### Software
| Software | Version | Why |
|---|---|---|
| **Python** | 3.11 or newer (developed and tested on 3.14) | Backend and verification engine |
| **Git** | any recent version | To clone the repository |
| **LM Studio** | 0.4 or newer, from [lmstudio.ai](https://lmstudio.ai) | Runs **Gemma 4 E2B** locally (the answer writer) |
| **Node.js** | 20 or newer, *optional* | Only to rebuild or edit the frontend. The built app is already in the repository |

### Accounts
| Account | Why | Cost |
|---|---|---|
| **Google AI Studio** ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)) | A **Gemini API key**: the Gemma 4 judge runs through the Gemini API | Free tier available; check the rate limits shown for your key |

### Downloads (one time)
| What | Size | Source |
|---|---|---|
| Gemma 4 E2B, Q4_K_M quantisation | about 3.4 GB | LM Studio (Hugging Face `lmstudio-community/gemma-4-E2B-it-GGUF`) |
| NLI model `cross-encoder/nli-deberta-v3-small` | about 570 MB | Hugging Face, fetched by the setup command below |
| Embedding model `all-MiniLM-L6-v2` | about 90 MB | Hugging Face, fetched by the setup command below |
| Python packages (torch is the largest) | about 1.5 GB | PyPI |

---

## 2. Step-by-step setup

### Step 1: Get the code
```powershell
git clone https://github.com/aryanvermaj67-sys/WITNESS-MLH.git
cd WITNESS-MLH\backend
```

### Step 2: Create the Python environment
```powershell
py -m venv .venv
```
```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
`requirements.txt` lists the packages without versions. If you want the **exact versions we tested** (recommended on Python 3.14), use `requirements.lock.txt` instead:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

### Step 3: Add your Gemini API key
```powershell
copy .env.example .env
```
Open `backend\.env` in Notepad and find the line that starts with `GEMINI_API_KEY` and paste your key right after the equals sign (no quotes, no spaces). **Never commit or share this file**; git already ignores it. Everything else in `.env` has a sensible default (see the table in section 4).

### Step 4: Download the two small models (once)
The server loads these from the local cache so it can run offline, so they must be downloaded one time:
```powershell
.\.venv\Scripts\python.exe -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); CrossEncoder('cross-encoder/nli-deberta-v3-small'); print('models cached')"
```
This downloads about 660 MB. If a download stalls, set `HF_HUB_DISABLE_XET=1` in the same PowerShell window and run the command again (it resumes).

### Step 5: Install Gemma 4 E2B in LM Studio
1. Install and open **LM Studio**, and keep it open (it starts the `lms` command-line tool on first run).
2. In LM Studio's **Discover** tab, search for **`gemma-4-e2b-it`** and download the **Q4_K_M** file from `lmstudio-community` (about 3.4 GB). Or from the command line (this also fetches an optional 1 GB vision file we do not use):
```powershell
& "$env:USERPROFILE\.lmstudio\bin\lms.exe" get https://huggingface.co/lmstudio-community/gemma-4-E2B-it-GGUF --gguf -y
```
3. Start the local server and load the model with exactly these settings. They matter: one parallel slot keeps the whole context window for each request, and the long keep-alive stops LM Studio unloading the model while you work.
```powershell
& "$env:USERPROFILE\.lmstudio\bin\lms.exe" server start --port 1234
```
```powershell
& "$env:USERPROFILE\.lmstudio\bin\lms.exe" load gemma-4-e2b-it --identifier gemma-4-e2b-it --gpu max --context-length 8192 --parallel 1 --ttl 86400 -y
```
If your GPU has less memory, use `--gpu 0.5` (half offloaded) or `--gpu off`.

### Step 6: Start WITNESS
Still in the `backend` folder:
```powershell
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
```
Wait about 25 seconds until it prints `Application startup complete` (it is loading the search index and the NLI model). Then open **http://localhost:8000** in your browser.

The four dots at the top (Backend, LM Studio, Gemini, NLI) should all be **green**. Click a demo question and press **Run check**, or open **Grade any AI** and load a saved answer.

---

## 3. Check that it works

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
Runs the **100 automated tests**. They need no network and no API key (both model clients are mocked).
```powershell
.\.venv\Scripts\python.exe -m witness.smoke
```
An offline, one-second check that the data files and saved replay results are healthy.
```powershell
curl http://localhost:8000/api/health
```
Shows which services are up and which models are in use.

## 4. Configuration (`backend/.env`)

All values are optional except the API key. Set only what you want to change.

| Setting | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | none | **Required** for the Gemma judge |
| `GEMINI_MODEL` | `gemma-4-26b-a4b-it` | Gemma model used for judging through the Gemini API. `gemma-4-31b-it` also works but is slower and often overloaded |
| `LMSTUDIO_BASE_URL` | `http://localhost:1234/v1` | Where LM Studio's server listens. If a check feels slow, try `http://127.0.0.1:1234/v1` (saves about 1.6 s on Windows) |
| `LMSTUDIO_MODEL` | `gemma-4-e2b-it` | The loaded local model (must match the identifier you loaded) |
| `NLI_MODEL` / `NLI_DEVICE` | DeBERTa-v3-small / `cpu` | The second judge, kept on the CPU so the GPU stays free for the writer |
| `EMBED_MODEL` | `all-MiniLM-L6-v2` | Search embedding model |
| `TOP_K` / `RRF_K` | `5` / `60` | Passages sent to the models / rank-fusion constant |
| `NLI_ENTAIL_THRESHOLD` / `NLI_CONTRA_THRESHOLD` | `0.70` / `0.70` | How sure the NLI judge must be |
| `NLI_RELATED_K` / `NLI_RELATED_MIN_SIM` | `3` / `0.55` | Only the 3 most related sentences (similarity at least 0.55) can contradict a claim |
| `GEN_TEMPERATURE` / `GEN_MAX_TOKENS` | `0.0` / `200` | Writer settings (temperature 0 keeps answers repeatable) |
| `OFFLINE_REPLAY` | `false` | `true` makes replay the default mode |
| `KB_DIR` / `CACHE_DIR` | `data/handbook` / `data/cached` | Source documents and saved results (relative to `backend/`) |
| `FRONTEND_DIST` | `../frontend/dist` | The built web app that the server serves |

## 5. Optional: work on the frontend
The built app is already in `frontend/dist`, and the server serves it. To change the interface you need **Node.js 20+**:
```powershell
cd frontend
npm install
```
```powershell
npm run dev        # development server on http://localhost:5173, forwards /api to the backend on port 8000
```
```powershell
npm run build      # rebuilds frontend/dist, which the backend serves
```
```powershell
npm run typecheck  # TypeScript check
```

## 6. Using your own PDF
In the **Check against** row, click **Upload a PDF** (text-based, up to 10 MB and 100 pages). It is kept **in memory only**: never written to disk and never saved for replay. Scanned, image-only PDFs have no text to read and are not supported yet.

## 7. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| **LM Studio dot is red**, or "LM Studio is not reachable" | Open LM Studio, then run the `server start` and `load` commands from Step 5 |
| **First answer times out**, error says the model may still be loading | LM Studio unloaded the idle model. Reload it with the Step 5 command (`--ttl 86400` keeps it loaded for 24 hours) |
| **Gemini dot is red** | The key in `backend\.env` is missing or wrong |
| **"Gemma judge did not answer (HTTP 503)"** | Google's model is overloaded. The server retries automatically; if it keeps happening, switch `GEMINI_MODEL` to `gemma-4-26b-a4b-it` |
| **Startup fails with a model-not-found error** | Run Step 4 once so the two small models are cached |
| **`WinError 4551 ... Application Control policy has blocked this file`** when importing torch | Windows Smart App Control blocks unsigned DLLs it has not seen before. Install the pinned versions with `requirements.lock.txt` (we pin `torch==2.9.1`, which loads fine). Do not turn the protection off |
| **Port 8000 is already in use** | Another copy of the server is running. Stop it, or start this one with `--port 8001` |
| **Checks are slow** | A live check takes about 10-30 s because real models run. Replay mode answers instantly from saved results |

## 8. What is in the repository
See the layout in [README.md](README.md#repository-layout). The full data model, HTTP API and design rules are in [docs/SPECIFICATION.md](docs/SPECIFICATION.md).
