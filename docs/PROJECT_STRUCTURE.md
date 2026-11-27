# FinRex Project Structure

This document describes the files and folders that should remain in the public repository after cleanup. Local Git history, secrets, dependency folders, logs, and generated pitch/output artifacts should not be published.

## Root

- `.dockerignore`: Excludes local state, dependency folders, caches, uploads, and build artifacts from Docker build context.
- `.env.example`: Root backend/runtime environment template. Copy to `.env` for local development and fill in API keys outside Git.
- `.gitignore`: Public-repo ignore rules for secrets, local tools, dependencies, caches, uploads, generated decks, and one-off output files.
- `.github/workflows/docker-image.yml`: GitHub Actions workflow for building the Docker image.
- `Dockerfile`: Builds the combined production image for backend and frontend assets.
- `docker-compose.yml`: Local Docker orchestration for FinRex plus supporting services.
- `LICENSE`: Project license.
- `package.json` / `package-lock.json`: Root workspace scripts for setup, dev, build, backend, and frontend orchestration.
- `README.md` / `README-ZH.md`: English and Chinese project overview, setup guide, workflow summary, and API overview.
- `Kronos/`: Vendored/reference foundation-model code used by the quant forecasting stack.
- `locales/`: Shared top-level locale JSON resources.

## Backend

- `backend/pyproject.toml` / `backend/uv.lock`: Python package metadata and locked dependency graph managed by `uv`.
- `backend/run.py`: Flask backend entrypoint. Starts the application factory from `app`.
- `backend/app/__init__.py`: Flask application factory. Configures CORS, logging, health checks, optional blueprint loading, and startup model warmup.
- `backend/app/config.py`: Central runtime configuration loaded from environment variables.
- `backend/app/controllers/`: HTTP API layer. Each module owns a Flask Blueprint for a product domain, such as graph, simulation, report, financial, market, validation, quant, paper trading, and news/sentiment sources.
- `backend/app/repositories/`: Persistence and cache access helpers. Keeps project, task, and validation storage concerns outside controllers.
- `backend/app/models/`: Lightweight data model definitions shared by backend services.
- `backend/app/services/`: Business logic layer. Includes simulation orchestration, graph/persona generation, report generation, public opinion analysis, market data providers, asset forecast services, validation logic, and integration helpers.
- `backend/app/services/historical_signals/`: Historical signal builders/loaders used by current quant and validation workflows after the old backtest service tree was removed.
- `backend/app/quant/`: Quant forecasting and strategy modules, including market features, foundation model towers, walk-forward evaluation, performance metrics, and paper-trading signal fusion.
- `backend/app/utils/`: Shared utilities for logging, locale handling, retry logic, file parsing, text encoding, LLM access, and Zep pagination.
- `backend/scripts/`: Operational and offline scripts for refresh jobs, evaluation, simulation runners, paper-trading scheduling, and validation scheduling.
- `backend/tests/`: Pytest coverage for controllers/services, quant modules, market-data fallbacks, forecasting, validation, and utility behavior.

## Frontend

- `frontend/package.json` / `frontend/package-lock.json`: Vue/Vite dependencies and frontend scripts.
- `frontend/index.html`: Vite HTML entry that loads `src/app/main.js`.
- `frontend/vite.config.js`: Vite configuration, aliases, dev server behavior, and build settings.
- `frontend/.env.example`: Frontend environment template. Copy to `frontend/.env.local` when local overrides are needed.
- `frontend/src/app/`: Current frontend application shell. Contains `App.vue`, `main.js`, and the active Vue Router in `router/index.js`.
- `frontend/src/pages/`: Route-level views for home, process, simulation, report, interaction, persona hub, sentiment, validation, quant backtest, and paper trading.
- `frontend/src/components/`: Reusable UI and domain components. Organized into chat, home, market, paper, persona, report, report widgets, validation, backtest charts, and shared `ui` primitives.
- `frontend/src/api/`: Axios client and frontend API wrappers. These map to backend controller domains and expose only the helpers used by current pages/components.
- `frontend/src/assets/`: Frontend themes, design tokens, and static source assets used by the active app.
- `frontend/src/context/`: Shared frontend state/context modules.
- `frontend/src/hooks/`: Vue composables such as workflow resolution helpers.
- `frontend/src/i18n/`: Vue I18n setup.
- `frontend/src/utils/`: Frontend helper modules for signal taxonomy and other local transformations.

## Current Public Cleanup Policy

Do not publish these from a local working tree:

- `.git/`, `.codex/`, `.playwright-cli/`, `.cursor/`, `.claude/`
- `.env`, `.env.local`, or any real credential file
- `node_modules/`, `frontend/node_modules/`, `backend/.venv/`, `.venv/`
- `frontend/dist/`, `backend/uploads/`, `backend/logs/`, `*.log`
- `outputs/`, `pitch-assets/`, local PPT decks, one-off exported HTML/Markdown reports

For a company public repository, create a fresh repository or archive from the cleaned working tree after committing the cleanup. Do not copy the existing `.git` directory if old personal history should be excluded.
