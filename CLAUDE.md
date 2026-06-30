# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SAIL is a Flask web app that helps international tennis players find U.S. college tennis programs (school search, scholarship estimates, AI-assisted coach outreach emails, athlete profiles/achievements).

## Running the app

```
python run.py
```

Loads `.env` via `python-dotenv`. `backend/app.py:create_app()` configures `SQLALCHEMY_DATABASE_URI` from `DATABASE_URL` (production: Neon Postgres; falls back to local `sqlite:///sail.db` if unset).

No test suite, linter, or build step currently exists in this repo.

### Verifying a change before committing

- `python -m py_compile <changed_file>.py` on every edited Python file.
- `grep -n "^def \|^class " <file>.py` before and after editing to confirm no existing routes/functions were silently dropped (this has happened before from whole-file rewrites).

## Critical rules specific to this project

1. **Git is the source of truth.** Never assume a file's contents from memory — read it from disk before editing, and re-read after editing to confirm the change landed correctly.
2. **Templates live in `frontend/pages/`, not `templates/`.** `create_app()` sets `template_folder='../frontend/pages'`, so `render_template('x.html')` resolves to `frontend/pages/x.html`. Static assets are in `frontend/static/`.
3. **The database does NOT auto-migrate.** `db.create_all()` (called in `create_app()`) only creates missing tables — it never adds columns to existing tables. Any new SQLAlchemy model column requires a manual `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...` run by the user against Neon **before** deploying. Always supply that exact SQL when adding a model field, and tell the user to run it first.
4. **Prefer small, surgical edits over whole-file rewrites.** A whole-file rewrite previously deleted an entire route function unnoticed. When editing a large file, change only the needed lines and verify all other functions survive (see grep check above).
5. **Don't break working features without being asked.** The "Find Schools" page and `/api/tennis/preview` (the landing-page preview endpoint) currently work well — don't change their behavior unless a task explicitly requires it.
6. **Secrets stay with the user.** Scripts that need `SCORECARD_API_KEY` or the Neon connection string cannot be run directly — write the script and give the user the exact command to run themselves.
7. Ask before destructive/irreversible actions (deleting files, force git operations).

## Architecture

Flask app factory pattern (`backend/app.py:create_app`), entry point `run.py`. Six blueprints registered in `create_app()`, each with no `url_prefix` (routes define their own full paths):

- `auth_bp` (`backend/routes/auth.py`) — registration, login/logout, password reset, login_required pages.
- `pages_bp` (`backend/routes/pages.py`) — all page routes (`render_template(...)`) for `/`, `/dashboard`, `/advisor`, `/schools`, `/achievements`, `/pricing`, `/privacy`, `/terms`, `/about`, `/admin`.
- `athlete_bp` (`backend/routes/athlete.py`) — `AthleteProfile` model (table `athlete_profiles`), profile CRUD, and the AI-recommended-matches logic (`smart_filter`, `refresh_matches`, `get_matches`).
- `ai_bp` (`backend/routes/ai_routes.py`) — Anthropic-powered chat (`/chat`-style) and coach outreach email generation (`generate_email`).
- `tennis_bp` (`backend/routes/tennis_routes.py`) — school search/filtering, scholarship estimation (`estimate_scholarship`, `utr_fit_score`, `get_avg_utrs`), `FavoriteSchool` model, and `/api/tennis/preview` (the landing-page preview).
- `analytics_bp` (`backend/routes/analytics.py`).

### Data layer

- Two data sources: Postgres (Neon)/SQLite via SQLAlchemy for user accounts (`backend/models/user.py:User`), athlete profiles, and favorites — and a static JSON file, `backend/routes/tennis_schools.json` (~1,146 school records), loaded via each module's own `load_schools()` helper (duplicated in both `tennis_routes.py` and `athlete.py`).
- School JSON fields of note: `school`, `division` (NCAA I/II/III, NAIA, JUCO, CCCAA, USCAA, NWAC, NCCAA), `city`, `state`, `lat`/`latitude` (~874/1146 have coords), `mens_scholarship`/`womens_scholarship`, `instate_tuition`/`outstate_tuition`, `top_lineup_utr_{men,women}`/`bottom_lineup_utr_{men,women}`/`power6_utr_{men,women}` (~120-128 schools), `avg_sat` (currently only the SAT *Math* subscore, not full score — a known data bug), `niche_grade` (~316 schools).
- Timestamped backups of the school JSON (`tennis_schools.backup-YYYYMMDD-HHMMSS.json`) are kept in `backend/routes/` — follow that convention before any script that rewrites `tennis_schools.json`.
- `backend/routes/fetch_scorecard_data.py` is the existing pattern for scripts that enrich `tennis_schools.json` from the College Scorecard API (requires `SCORECARD_API_KEY`, run by the user, not Claude).

### Matching / recommendation logic

- `athlete.py:smart_filter` and `athlete.py:refresh_matches` drive the dashboard's AI-recommended schools, factoring UTR/GPA/division/gender against the JSON school data.
- `tennis_routes.py:estimate_scholarship` / `utr_fit_score` / `get_avg_utrs` drive scholarship estimates and fit scoring shown on the Find Schools page.
