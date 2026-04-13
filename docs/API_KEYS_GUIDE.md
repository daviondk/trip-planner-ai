# API Keys Guide

This guide explains where and how to obtain API keys for all external services used in Trip Planner AI.

## Required APIs

### 1. OpenRouteService (Routes)

**Purpose:** Building routes between waypoints (driving, walking, cycling)

**Free Tier:** 2000 requests/day

**How to get the key:**
1. Go to https://openrouteservice.org/
2. Click "Sign up" in the top right
3. Register with email or OAuth (Google/GitHub)
4. After registration, go to https://api.openrouteservice.org/
5. Sign in and navigate to "Dashboard" or "My Tokens"
6. Create a new token (give it a name like "Trip Planner AI")
7. Copy the token

**Environment variable:**
```bash
OPENROUTESERVICE_API_KEY=your-token-here
```

**Documentation:** https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/

---

### 2. SerpApi (Google Hotels & Flights)

**Purpose:** Searching hotels and flights via Google Hotels and Google Flights APIs

**Free Tier:** 100 searches/month

**How to get the key:**
1. Go to https://serpapi.com/
2. Click "Sign up" in the top right
3. Register with email
4. Verify your email
5. Go to https://serpapi.com/users/sign_up
6. After registration, go to "API Key" section in dashboard
7. Copy your API key

**Environment variables:**
```bash
SERPAPI_API_KEY=your-api-key-here
SERPAPI_TIMEOUT=10
```

**Documentation:**
- Google Hotels: https://serpapi.com/google-hotels-api
- Google Flights: https://serpapi.com/google-flights-api

---

## Optional APIs

### 3. OpenRouter (LLM)

**Purpose:** Alternative to YandexGPT for text generation and embeddings

**Free Tier:** Free models available (no credit card required)

**How to get the key:**
1. Go to https://openrouter.ai/
2. Click "Sign up" in the top right
3. Register with email
4. Verify your email
5. Go to https://openrouter.ai/keys
6. Create a new API key
7. Copy the key

**Environment variables:**
```bash
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free
OPENROUTER_EMBEDDING_MODEL=nvidia/llama-nemotron-embed-vl-1b-v2:free
```

**Documentation:** https://openrouter.ai/docs

---

### 4. YandexGPT (LLM)

**Purpose:** Primary LLM for Russian language support

**Free Tier:** Limited free tier, then paid

**How to get the key:**
1. Go to https://cloud.yandex.ru/
2. Create an account (or sign in with Yandex ID)
3. Go to https://console.cloud.yandex.ru/
4. Create a new folder or select existing
5. In the folder, go to "Service Accounts" → "Create service account"
6. Create service account with "ai.languageModels.user" role
7. For the service account, create an API key:
   - Service accounts → [your account] → Create authorized key
8. Copy the API key and Folder ID

**Environment variables:**
```bash
YANDEXGPT_API_KEY=your-api-key-here
YANDEXGPT_FOLDER_ID=your-folder-id-here
YANDEXGPT_MODEL=yandexgpt-lite/latest
```

**Documentation:** https://cloud.yandex.ru/docs/yandexgpt/

---

### 5. Langfuse (Observability)

**Purpose:** Tracing, monitoring, and cost tracking for LLM calls

**Free Tier:** Self-hosted (free) or cloud tier with limits

**How to get the key:**
1. **Option 1: Self-hosted (recommended for PoC)**
   - Follow Docker setup in docker-compose.yml
   - No API key needed
   - Set: `LANGFUSE_HOST=http://langfuse:3000`

2. **Option 2: Cloud**
   - Go to https://cloud.langfuse.com/
   - Sign up for an account
   - Create a new project
   - Get Public Key and Secret Key from project settings

**Environment variables (self-hosted):**
```bash
LANGFUSE_PUBLIC_KEY=pk-lf-your-key
LANGFUSE_SECRET_KEY=sk-lf-your-secret
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_PG_USER=langfuse
LANGFUSE_PG_PASSWORD=your-password
LANGFUSE_SECRET=mysecret
```

**Documentation:** https://langfuse.com/docs

---

### 6. OpenTripMap API (POI)

**Purpose:** Points of Interest data (museums, restaurants, parks, attractions)

**Free Tier:** 5000 requests/day, 10 requests/second (non-commercial)

**How to get the key:**
1. Go to https://dev.opentripmap.org/
2. Click "Register" in the top right
3. Register with email
4. After registration, go to "My Account" or "API Key" section
5. Copy your API key

**Environment variables:**
```bash
OPENTRIPMAP_API_KEY=your-api-key-here
OPENTRIPMAP_TIMEOUT=10
```

**Documentation:** https://dev.opentripmap.org/docs

---

## No API Key Required

### 6. Nominatim (OpenStreetMap)

**Purpose:** Geocoding (address ↔ coordinates) and POI search

**Free Tier:** 1 request/second (free, no key required)

**Usage:**
- No API key needed
- Just set a User-Agent header to identify your application

**Environment variable:**
```bash
NOMINATIM_USER_AGENT=trip-planner-ai-poc
```

**Documentation:** https://nominatim.openstreetmap.org/

---

### 7. ChromaDB

**Purpose:** Vector database for semantic search

**Free Tier:** Self-hosted (completely free)

**Usage:**
- No API key needed
- Self-hosted via Docker in docker-compose.yml

**Environment variables:**
```bash
CHROMA_HOST=chromadb
CHROMA_PORT=8100
```

**Documentation:** https://docs.trychroma.com/

---

## Quick Setup

### Minimal Setup (Free APIs only)

```bash
# OpenRouteService (required for routes)
OPENROUTESERVICE_API_KEY=your-ors-key
OPENROUTESERVICE_TIMEOUT=10

# SerpApi (required for hotels/flights)
SERPAPI_API_KEY=your-serpapi-key
SERPAPI_TIMEOUT=10

# OpenTripMap (required for POI data)
OPENTRIPMAP_API_KEY=your-opentripmap-key
OPENTRIPMAP_TIMEOUT=10

# Nominatim (no key needed)
NOMINATIM_USER_AGENT=trip-planner-ai-poc

# LLM (choose one)
# Option 1: OpenRouter (free models)
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free

# Option 2: YandexGPT
LLM_PROVIDER=yandexgpt
YANDEXGPT_API_KEY=your-yandex-key
YANDEXGPT_FOLDER_ID=your-folder-id
YANDEXGPT_MODEL=yandexgpt-lite/latest

# Optional: Langfuse (self-hosted)
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_PG_USER=langfuse
LANGFUSE_PG_PASSWORD=changeme
LANGFUSE_SECRET=mysecret
```

---

## Cost Summary (PoC)

| Service | Free Tier | Cost after free tier |
|---------|-----------|---------------------|
| OpenRouteService | 2000 requests/day | Contact for pricing |
| SerpApi | 100 searches/month | $50/month for 500 searches |
| OpenTripMap | 5000 requests/day | Contact for pricing |
| OpenRouter | Free models | Pay per token for paid models |
| YandexGPT | Limited free tier | ~$0.001-0.005 per 1K tokens |
| Nominatim | 1 req/sec (free) | Free |
| ChromaDB | Self-hosted (free) | Free |
| Langfuse | Self-hosted (free) | Cloud pricing available |

**Total for PoC:** $0 (using only free tiers)
