# Accountability Bot

## Quick Start
1. Python 3.12+
2. `python -m venv .venv && . .venv/Scripts/Activate.ps1` (Windows PowerShell)
3. `pip install -r requirements.txt`
4. Set token: `$env:DISCORD_TOKEN="YOUR_TOKEN_HERE"`
5. Run: `python run.py`


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
- `BOT_DB_PATH` (default `/data/bot.db` inside container or `bot.db` locally)
- `BACKFILL_DEFAULT_DAYS` (default 30)
- `USE_DB_ONLY` (default false)
- `GUILD_ID` (optional; speeds up slash command sync in a primary guild)
- `DAILY_GOAL_TASKS` (default 5)

Scheduler (embed posts):

## Anchored weekly schedules

You can create anchored schedules that align to the start of the week (Monday 00:00 UTC). Use the slash command UI under the schedule manager or the dedicated command to create them.

Expression format:

- Basic interval: tokens w (weeks), d (days), h (hours), m (minutes)
- Combined form: `interval@offset`
	- interval: how often it repeats (e.g., `w1` = every week, `w2` = every 2 weeks)
	- offset: shift from Monday 00:00 (e.g., `d2h10` = Wednesday 10:00)

Examples:

- `d2h4` → every 2 days and 4 hours from Monday 00:00
- `w1@d2h10` → weekly on Wednesday at 10:00 (Monday + 2 days + 10 hours)
- `w2@h9m30` → every 2 weeks at Monday 09:30

Create via UI:

- Use `/schedule manage` → Create Anchored → pick report → Enter `interval` or `interval@offset`.

Create via slash command:

- `/schedule create_anchored report_type:<type> expression:<interval or interval@offset>`

## License
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Botson is licensed under the Apache License 2.0. This permissive license allows commercial use, modifications, and redistribution while providing explicit patent protection for contributors and users. It includes a patent retaliation clause to deter patent misuse.

By contributing, you agree to license your work under Apache-2.0 and grant maintainers the right to relicense future versions under other OSI-approved licenses if needed (see CONTRIBUTING.md for details).

## Safety Note
## Development

Run tests locally:

```
pip install -r requirements.txt
pytest -q
```
Never commit your real Discord bot token. Use `.env`, compose environment section, or secret management.



