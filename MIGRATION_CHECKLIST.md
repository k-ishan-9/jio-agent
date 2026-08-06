# Migration Checklist — Corporate/Accops Environment (if ever needed later)

## What's already done (this package)
- [x] Code refactored out of Colab-specific dependencies
- [x] Clean folder structure with `config.py` centralizing all paths/settings
- [x] `requirements.txt` with pinned versions
- [x] `.env` support for local secrets management

## What you'd need from IT if deploying inside Accops/Citrix later

1. **Proxy / PyPI mirror config for pip installs** — ask for the internal
   mirror URL or corporate proxy address, and check if `faiss-cpu`,
   `google-genai`, `google-adk` are already mirrored internally.
2. **Outbound network access confirmation** — the agent needs to reach
   `generativelanguage.googleapis.com` at runtime, not just during pip install.
3. **Where GOOGLE_API_KEY should live** — env var, corporate secrets manager,
   or `.env` file, per IT/security policy.

## Data files to carry over
Copy these from your Drive-based build into `data/` (or wherever `JIO_DATA_ROOT` points):
```
jio_plans.db
jio_faiss_index/
    index.faiss
    metadata.json
```

## Steps to run anywhere (personal laptop, VM, or eventually Accops)

```bash
pip install -r requirements.txt
cp .env.example .env        # then edit .env with your real GOOGLE_API_KEY
python -c "from config import verify_data_files_exist; verify_data_files_exist(); print('OK')"
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
