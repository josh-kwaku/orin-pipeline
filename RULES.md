# Pipeline Development Rules

**IMPORTANT: Reference this file before making any changes to the pipeline.**

---

## 1. API Keys & Secrets

### Storage
- All API keys, secrets, and credentials MUST be stored in `.env` files
- `.env` files MUST NOT be committed to version control
- Use `.env.example` to document required variables (without actual values)

### Usage
- NEVER directly read `.env` files in code
- NEVER hardcode API keys or secrets in source code
- NEVER log or print API keys, even partially
- Load environment variables through `os.environ` after they've been loaded into the environment
- Use `python-dotenv` to load `.env` at application startup (in entry point only)

### Example Pattern
```python
# CORRECT - in entry point (e.g., run_pipeline.py)
from dotenv import load_dotenv
load_dotenv()  # Loads .env into os.environ

# CORRECT - in modules
import os
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY environment variable not set")

# WRONG - never do this
api_key = "sk-xxxxx"  # Hardcoded
open(".env").read()   # Direct file read
```

---

## 2. Git & Version Control

### Must Ignore
```gitignore
# Environment files
.env
.env.local
.env.*.local

# API keys and secrets
*.key
*.pem
secrets/

# Large data files
*.db
*.sqlite
data/lrclib.db
data/lrclib.sqlite3

# Audio files (too large)
*.mp3
*.opus
*.wav
audio/

# Model files
*.bin
*.onnx
models/
```

### Must Commit
- `.env.example` (template without values)
- `requirements.txt`
- Source code
- Documentation

---

## 3. Data & File Handling

### Large Files
- Do NOT commit database dumps (lrclib.db)
- Do NOT commit audio files
- Do NOT commit model weights
- Use symlinks or document paths in config

### Sensitive Data
- Log files may contain sensitive info - add to .gitignore
- Skipped songs logs are OK to commit (no secrets)

---

## 4. Error Handling

- Never expose API keys in error messages
- Sanitize logs before output
- Use generic error messages for auth failures

---

## 5. Required Environment Variables

Document in `.env.example`:
```
# LLM APIs
GROQ_API_KEY=
TOGETHER_API_KEY=

# Storage (for later)
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
R2_ENDPOINT=

# Database paths (optional, can use defaults)
LRCLIB_DB_PATH=
OUTPUT_DIR=
```

---

## Checklist Before Committing

- [ ] No API keys in code
- [ ] No `.env` files staged
- [ ] `.gitignore` is up to date
- [ ] `.env.example` documents all required variables
- [ ] No secrets in error messages or logs
