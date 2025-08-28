# Accountability Bot (Event-Driven Rework Scaffold)

## Quick Start (Local)
1. Python 3.12+
2. `python -m venv .venv && . .venv/Scripts/Activate.ps1` (Windows PowerShell)
3. `pip install -r requirements.txt`
4. Set token: `$env:DISCORD_TOKEN="YOUR_TOKEN_HERE"`
5. Run: `python run.py`

## Docker Run (Single Container)
Build and run manually:
```
docker build -t accountability-bot .
# Insert your key in the command below (DO NOT COMMIT IT):
docker run -d --name accountability-bot -e DISCORD_TOKEN=YOUR_TOKEN_HERE -v bot_data:/data accountability-bot
```

## Docker Compose (Recommended)
Edit `docker-compose.yml` and replace this line:
```
DISCORD_TOKEN: "REPLACE_WITH_YOUR_DISCORD_BOT_TOKEN"  # <- INSERT YOUR TOKEN HERE
```
Then start:
```
docker compose up -d --build
```
(Compose will create a named volume `bot_data` storing `bot.db`.)

Alternatively use an `.env` file:
1. Copy `.env.example` to `.env`
2. Put your token: `DISCORD_TOKEN=YOUR_TOKEN_HERE`
3. In `docker-compose.yml` comment the inline DISCORD_TOKEN and uncomment:
```
# env_file:
#   - .env
```
4. Run `docker compose up -d --build`

## Environment Variables
- `DISCORD_TOKEN` (required)
- `BOT_DB_PATH` (default `/data/bot.db` inside container)
- `BACKFILL_DEFAULT_DAYS` (default 30)
- `USE_DB_ONLY` (default false)

## Current Status
Scaffold includes: migrations, event bus, channel registration, message ingestion, habit parsing (raw scores), basic weekly report (raw sums). Normalization, backfill, reminders, and rich reporting pending.

## License
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Botson is licensed under the Apache License 2.0. This permissive license allows commercial use, modifications, and redistribution while providing explicit patent protection for contributors and users. It includes a patent retaliation clause to deter patent misuse.

By contributing, you agree to license your work under Apache-2.0 and grant maintainers the right to relicense future versions under other OSI-approved licenses if needed (see CONTRIBUTING.md for details).

## Safety Note
Never commit your real Discord bot token. Use `.env`, compose environment section, or secret management.
