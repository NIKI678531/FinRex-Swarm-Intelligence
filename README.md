<div align="center">

# FinRex

A Simple and Universal Swarm Intelligence Engine, Predicting Anything

[English](./README.md) | [中文文档](./README-ZH.md)

</div>

## Overview

**FinRex** is a multi-agent AI prediction engine: upload real-world seed information (news, research reports, financial signals) and describe what you want to predict in natural language, and it builds an interactive parallel digital world, simulates how the future unfolds, and produces a detailed prediction report.

## Workflow

FinRex generates predictions through two complementary workflows that ultimately converge into a single report:

**Workflow A — Swarm Intelligence Simulation (qualitative: "what will happen")**

1. **Graph building**: Extract entities and relationships from the seed material, inject individual and collective memory, and construct a GraphRAG knowledge graph.
2. **Environment setup**: Extract entity relationships, generate agent personas, and let a configuration agent parse the prediction request and inject simulation parameters.
3. **Dual-platform parallel simulation**: Drive thousands of agents interacting freely across Reddit- and Twitter-style platforms in parallel, updating temporal memory dynamically along the way.
4. **Report generation & deep interaction**: ReportAgent uses a rich toolset to interact deeply with the post-simulation environment and produce a report; you can also chat with any agent in the world or with ReportAgent directly.

**Workflow B — Foundation-Model Quantitative Forecasting (quantitative: "what the numbers are")**

1. **Market data ingestion**: Fetch historical and real-time data for cryptocurrencies and stocks via ccxt / yfinance / akshare.
2. **Price forecasting**: Generate price forecast sequences using the Kronos and Chronos-Bolt foundation models.
3. **Backtesting & validation**: Backtest forecasts and validate them through paper trading to quantify strategy performance.

**How the two workflows work together:** The swarm simulation (A) captures the *qualitative* side — market sentiment and the evolution of events — while quantitative forecasting (B) provides the *quantitative* side of price movement. Public-opinion sentiment analysis bridges the two: it supplies sentiment labels to the simulated agents and also feeds features into the quantitative forecast. Finally, ReportAgent integrates both into a single prediction report and supports ongoing conversation and deep interaction.

## Features

- **Multi-agent swarm simulation**: Powered by CAMEL-OASIS, driving thousands of agents with independent personalities, long-term memory, and behavioral logic that interact freely.
- **GraphRAG graph and long-term memory**: Builds a user-profile graph with Zep Cloud + FalkorDB, injects individual and collective memory, and updates temporal memory dynamically.
- **Dual-platform parallel simulation**: Reddit- and Twitter-style platforms run in parallel, automatically parsing natural-language prediction requests.
- **Foundation-model quantitative forecasting**: Integrates the Kronos and Chronos-Bolt foundation models to support price forecasting and backtesting for cryptocurrencies and stocks.
- **Public-opinion sentiment analysis**: Optional Hugging Face remote inference produces financial and multilingual emotion labels, with automatic fallback to local rule-based labels on failure.
- **In-depth report generation**: ReportAgent leverages a rich toolset to interact deeply with the post-simulation environment and produce a detailed prediction report.
- **Interactive digital-world conversations**: Hold natural-language conversations with any agent in the simulated world or with ReportAgent.
- **Content Studio and paper trading**: Built-in Content Studio, paper trading, and backtesting capabilities cover the full pipeline from research to execution.

## Tech Stack

| Layer | Technologies |
|-------|--------------|
| **Frontend** | Vue 3 · Vite 7 · Vue Router · Vue I18n · ECharts · D3 · Lightweight Charts · Axios |
| **Backend** | Python 3.11/3.12 · Flask 3 · Flask-CORS · OpenAI SDK · Pydantic |
| **Agents / Memory** | CAMEL-OASIS · CAMEL-AI · Zep Cloud · FalkorDB (Graphiti graph backend) |
| **Quant / Forecasting** | PyTorch · Kronos · Chronos-Bolt · LightGBM · scikit-learn · pandas · numpy |
| **Market Data** | ccxt · yfinance · akshare |
| **Documents & Processing** | PyMuPDF · charset-normalizer · chardet |
| **Infrastructure** | Docker · docker-compose · uv (Python package manager) · Node.js 18+ |

## Local Environment Setup

#### Prerequisites

| Tool | Version | Description | Check Installation |
|------|---------|-------------|-------------------|
| **Node.js** | 18+ | Frontend runtime, includes npm | `node -v` |
| **Python** | ≥3.11, ≤3.12 | Backend runtime | `python --version` |
| **uv** | Latest | Python package manager | `uv --version` |

#### Configure Environment Variables

```bash
# Copy the example configuration file
cp .env.example .env

# Edit the .env file and fill in the required API keys
```

**Required environment variables:** On startup the backend only enforces `LLM_API_KEY` and `ZEP_API_KEY`; everything else is optional.

```env
# ===== LLM API configuration (supports any LLM API in OpenAI SDK format) =====
# Compatible with OpenAI / Azure OpenAI / any compatible endpoint
# Consumption can be high, so start with fewer than 40 simulation rounds
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-4o-mini
# Azure OpenAI only: the deployment may differ from the model name; falls back to LLM_MODEL_NAME if empty
LLM_API_VERSION=2024-12-01-preview
LLM_DEPLOYMENT_NAME=

# ===== Zep memory graph configuration =====
# The free monthly quota is enough for simple usage: https://app.getzep.com/
ZEP_API_KEY=your_zep_api_key_here
```

**Optional configuration (enable as needed):**

```env
# ----- Boost LLM (optional) -----
# Disabled by default; when set to true, dual-platform parallel simulation uses this faster model
LLM_BOOST_ENABLED=false
LLM_BOOST_API_KEY=your_api_key_here
LLM_BOOST_BASE_URL=your_base_url_here
LLM_BOOST_MODEL_NAME=your_model_name_here

# ----- Hugging Face remote inference (optional) -----
# Adds financial / multilingual emotion labels to the Public Opinion Layer
# Falls back to local rule-based labels if the token is missing or the remote call fails
HF_TOKEN=your_huggingface_token_here
HF_ENABLE_REMOTE_INFERENCE=true
HF_INFERENCE_BASE_URL=https://router.huggingface.co/hf-inference/models
HF_FINANCIAL_SENTIMENT_MODEL=mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis
HF_EMOTION_MODEL=tabularisai/multilingual-emotion-classification
# The multilingual emotion model is non-commercial (CC-BY-NC-4.0); remote calls require explicit opt-in, otherwise local rules are used
HF_ALLOW_NON_COMMERCIAL_MODELS=false

# ----- Cloudflare D1 (Binance Square community data source, optional) -----
# When missing or the token has expired, related endpoints fall back to local cache / public announcement feeds
CLOUDFLARE_D1_ACCOUNT_ID=your_cloudflare_account_id
CLOUDFLARE_D1_DATABASE_ID=your_d1_database_id
CLOUDFLARE_D1_API_TOKEN=your_d1_api_token
```

> Frontend environment variables (optional): set `VITE_REPORT_V2=true` (the default) in `frontend/.env.local` to enable the v2 report UI, or set it to `false` to fall back to the legacy UI.

#### Local Docker Setup

```bash
# 1. Configure environment variables (same as source deployment)
cp .env.example .env

# 2. Pull the image and start
docker compose up -d
```

By default it reads `.env` from the root directory and maps ports `3000 (frontend) / 5001 (backend)`. `docker-compose.yml` starts both the `finrex` main service and the `falkordb` graph backend (which exposes `6379` for Graphiti clients and `3001` for its built-in dashboard).

> `docker-compose.yml` provides mirror image addresses in comments that you can swap in as needed.

## Getting Started

### Install Dependencies

```bash
# Install all dependencies in one step (root + frontend + backend)
npm run setup:all
```

Or install step by step:

```bash
# Install Node dependencies (root + frontend)
npm run setup

# Install Python dependencies (backend, auto-creates a virtual environment)
npm run setup:backend
```

### Run in Development Mode with npm

```bash
# Start both frontend and backend (run from the project root)
npm run dev
```

**Service URLs:**
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5001`

**Start individually:**

```bash
npm run backend   # Start the backend only
npm run frontend  # Start the frontend only
```

### Build for Production

```bash
# Build the frontend production bundle (output to frontend/dist)
npm run build
```

## Project Structure

```text
FinRex_rebrand/
├── package.json                # Root workspace scripts (setup / dev / build / backend / frontend)
├── docker-compose.yml          # Orchestrates the finrex main service + falkordb graph backend
├── Dockerfile                  # Unified frontend + backend image
│
├── backend/                    # Flask backend (Python dependencies managed by uv)
│   ├── run.py                  # Backend entry point (starts the Flask app, port 5001)
│   ├── pyproject.toml          # Python dependencies and project configuration
│   ├── app/
│   │   ├── config.py           # Environment variable and global configuration loading
│   │   ├── controllers/        # HTTP layer (Flask Blueprints, mounted on demand)
│   │   ├── services/           # Business logic layer
│   │   │   ├── simulation_*     #   Swarm simulation orchestration and execution (Workflow A)
│   │   │   ├── graph_builder    #   GraphRAG graph construction
│   │   │   ├── persona_graph/   #   Agent personas and profile graph
│   │   │   ├── zep_*            #   Zep long-term memory read/write and updates
│   │   │   ├── asset_forecast/  #   Kronos / Chronos price forecasting (Workflow B)
│   │   │   ├── public_opinion_* #   Public-opinion and sentiment analysis
│   │   │   └── report_agent     #   ReportAgent report generation and interaction
│   │   ├── quant/              # Quantitative forecasting core algorithms
│   │   ├── repositories/       # Data access layer (cache / persistence)
│   │   ├── models/             # Data model definitions
│   │   └── utils/              # Shared utility functions
│   ├── scripts/                # Scheduling and offline scripts (paper trading, backtesting, validation, etc.)
│   ├── tests/                  # pytest tests
│   └── uploads/                # Runtime artifacts and various caches (market data / news / graphs, etc.)
│
├── frontend/                   # Vue 3 + Vite frontend (port 3000)
│   └── src/
│       ├── api/                # Axios API wrappers (mapped one-to-one to backend controllers)
│       ├── pages/              # Page-level views
│       ├── components/         # Reusable components
│       ├── context/            # Global state
│       ├── hooks/              # Composables
│       ├── i18n/               # Internationalization resources
│       └── utils/              # Frontend utility functions
│
├── Kronos/                     # Kronos foundation-model source, fine-tuning scripts, and examples
└── locales/                    # Top-level localization files (en / zh)
```

## API Integration

The backend organizes its endpoints with **Flask Blueprints**. Controllers live in [backend/app/controllers](backend/app/controllers) and are mounted on demand at startup (blueprints whose optional dependencies are missing are skipped safely). The main endpoint domains are:

| Domain | Description |
|--------|-------------|
| `graph` | Graph construction and querying |
| `simulation` | Swarm simulation lifecycle management |
| `report` | Report generation and interaction |
| `public_opinion` | Public-opinion and sentiment analysis |
| `content_studio` | Content Studio |
| `financial` | Financial data and metrics |
| `persona` | Persona generation and profiling |
| `quant` | Quantitative forecasting and backtesting |
| `paper_trading` | Paper trading |
| `market` / `articles` / `reaction` | Market data, news, and reaction data |

The frontend calls these endpoints through the Axios modules under [frontend/src/api](frontend/src/api), mapped one-to-one.

## API Management and Optimization

- **Unified LLM access**: Connect to any LLM through the OpenAI SDK-compatible protocol (`LLM_BASE_URL` / `LLM_MODEL_NAME`), making it easy to switch providers and models.
- **Graceful degradation**: Controllers mount on demand, so missing LLM / simulation dependencies do not affect other blueprints; Hugging Face remote inference falls back to local rule-based labels on failure.
- **Caching**: Market data, news, graphs, and other results are cached under `backend/uploads/*_cache` to reduce redundant external requests and token consumption.
- **Cost control**: We recommend starting with fewer than 40 simulation rounds to avoid high LLM call costs.

## Contributing

1. Fork the repository and create a feature branch: `git checkout -b feature/your-feature`
2. Follow the existing code style and make sure the backend tests pass before committing: `cd backend && uv run pytest`
3. Write clear commit messages and open a pull request explaining the motivation and scope of your changes.
4. When changing an endpoint, update the frontend `frontend/src/api` and this document accordingly.

## Version History

| Version | Description |
|---------|-------------|
| `0.1.0` | Initial release: multi-agent swarm simulation, GraphRAG memory, foundation-model quantitative forecasting, and report generation. |

## Recent Updates

- **Unified Docker deployment**: `docker-compose.yml` integrates the `finrex` main service and the `falkordb` graph backend, ready to run out of the box.
- **Foundation-model quantitative forecasting**: Integrated Kronos and Chronos-Bolt to support cryptocurrency and stock forecasting.

## Changelog

- Added optional Hugging Face remote inference, with an automatic fallback path to local rule-based labels.
- Added on-demand controller mounting that safely skips blueprints when optional dependencies are missing.
- Added a unified frontend + backend `Dockerfile` and docker-compose deployment support.

## License

This project is open source under the [AGPL-3.0](./LICENSE) license.
