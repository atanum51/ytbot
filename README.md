# ytbot (Telegram + yt-dlp)
This repository contains a Telegram bot that downloads videos using `yt-dlp` and sends them back to the chat.
It supports browser-exported cookies (Netscape `cookies.txt`) provided via an environment variable so you don't commit secrets to the repo.

---

## What's included
- `bot.py` — main bot code (reads `YTDLP_COOKIES_CONTENT` if present and writes `/tmp/cookies.txt`)
- `requirements.txt` — dependencies
- `Procfile` — (optional) `web: python bot.py`
- `.gitignore` — recommended ignores
- This `README.md` — step-by-step deploy instructions

---

## Quick local test (Linux / macOS)
1. Install dependencies in a virtualenv:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Export your Telegram token and cookies (do **not** commit cookies file):
```bash
export TELEGRAM_TOKEN="<your-telegram-bot-token-here>"
# if you have a cookies file locally:
export YTDLP_COOKIES_CONTENT="$(cat /path/to/youtube.com_cookies.txt)"
export YTDLP_COOKIES_FILE="/tmp/cookies.txt"
python bot.py
```
3. Interact with the bot on Telegram (`/start`, `/dl <URL>` or just paste a YouTube link).

---
## Deploy to Render.com (step-by-step)

### 1) Push this repo to GitHub
Create a new repository on GitHub (e.g. `ytbot`) and push these files:
```bash
git init
git add .
git commit -m "initial ytbot")
git branch -M main
git remote add origin https://github.com/<yourusername>/ytbot.git
git push -u origin main
```

### 2) Create a new **Web Service** on Render
- In Render: **New → Web Service → Connect** your GitHub account and select this repo.
- Build Command: `pip install -r requirements.txt` (Render will usually auto-install but explicit is safe)
- Start Command (exact): (copy-paste)
```
bash -lc 'if [ -n "$YTDLP_COOKIES_CONTENT" ]; then printf "%s" "$YTDLP_COOKIES_CONTENT" > /tmp/cookies.txt; fi && export YTDLP_COOKIES_FILE=/tmp/cookies.txt && python bot.py'
```
- Important: set Python runtime to 3.11 (recommended) — either add an environment variable or add `.python-version` to repo:
  - In Render Dashboard → Environment → Add `PYTHON_VERSION` = `3.11.16`
  - OR add `.python-version` file containing `3.11.16` to this repo before pushing.

### 3) Add Environment Variables (secrets)
In Render Dashboard → Environment:
- `TELEGRAM_TOKEN` = `your-bot-token` (secret)
- `YTDLP_COOKIES_CONTENT` = **(optional)** paste your **cookies.txt** file content here (multiline). **Do not commit cookies file to repo.**
- `YTDLP_COOKIES_FILE` = `/tmp/cookies.txt`
- `PYTHON_VERSION` = `3.11.16` (recommended)

### 4) Deploy & logs
- Click **Manual Deploy** → Deploy latest commit.
- Watch logs: build (`pip install`) should succeed, then `Wrote cookies to /tmp/cookies.txt` (if provided), then `Bot starting...`.
- Test on Telegram: send `/start` and then `/dl <youtube link>`.

---
## Security notes
- **Cookies are sensitive.** Never commit `cookies.txt` into the repository. Use `YTDLP_COOKIES_CONTENT` secret on Render or local env only.
- After use, clear or invalidate cookies by logging out of the browser/account if concerned.
- Keep `TELEGRAM_TOKEN` secret.

---
## Troubleshooting
- If build fails because of Python version incompatibilities (AttributeError on `Updater`), set `PYTHON_VERSION=3.11.16` in Render or add `.python-version` with `3.11.16` and redeploy.
- If yt-dlp reports login/age errors, re-export cookies (they may expire) and update `YTDLP_COOKIES_CONTENT` secret.
- If bot fails to send large files (>50MB), it will split into parts automatically.

If you want, paste any Render build/runtime logs here and I'll help debug the exact error.
