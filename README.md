# Pricing Intelligence Pipeline (v1)

A LangGraph pipeline that scrapes a competitor's pricing page (via Firecrawl),
compares it against historical data and your own pricing (via MongoDB Atlas),
and produces a brief. Uses Groq for URL selection and comparison reasoning.

## Flow

```
load_competitor -> map_website -> select_pricing_url -> scrape_pricing
  -> save_snapshot -> fetch_comparison_data -> compare -> synthesize -> END
```

`load_competitor` resolves the competitor's website from the registry, or if
it isn't listed, discovers it via AI web search (Firecrawl search + Groq picks
the official homepage) so brand-new competitors can be scraped without editing
the registry.

Any node can fail and route straight to `handle_failure`, which produces a
clear failure brief instead of crashing.

## Setup

1. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```
   cp .env.example .env
   ```
   Fill in `GROQ_API_KEY`, `FIRECRAWL_API_KEY`, and `MONGODB_URI`.

3. **MongoDB Atlas setup**
   - Create a free cluster: https://www.mongodb.com/cloud/atlas
   - Database Access → create a DB user, note username/password
   - Network Access → add your IP (or `0.0.0.0/0` for local testing only)
   - Connect → Drivers → copy the connection string into `MONGODB_URI`
   - Test the connection and create indexes:
     ```
     python db.py
     ```

4. **Populate your own pricing data** (this pipeline does NOT scrape your own
   site — you own that data). Insert at least one document into the
   `our_pricing` collection, e.g. via `mongosh` or Compass:
   ```json
   {
     "tiers": [
       {"name": "Starter", "price": 29, "features": ["..."]},
       {"name": "Pro", "price": 99, "features": ["..."]}
     ],
     "updated_at": "2026-08-01T00:00:00Z"
   }
   ```

5. **(Optional) Populate churn_data collection** for churn-risk notes to be
   meaningful:
   ```json
   {"tier": "Pro", "churn_rate_pct": 8.2, "period": "2026-Q2"}
   ```

6. **Edit `competitor_registry.json`** with real competitor names + base URLs.
   (Optional — if a competitor isn't listed, the pipeline will try to discover
   their website via AI web search instead of failing.)

## Run

**CLI:**
```
python main.py "CompetitorX"
```
Output is printed to the console.

**Streamlit UI:**
```
streamlit run app.py
```
Opens a browser UI where you can pick a competitor from the registry (or type
one), run the pipeline, and see:
- the final brief
- a step-by-step trace showing exactly which stage succeeded/failed
- raw comparison JSON and raw scraped content (expandable)
- warnings for soft failures (e.g. no previous snapshot, write-back failed)

In both cases: full trace goes to `logs/pipeline.log`, only failures go to
`logs/failures.log` — check that file first if a run doesn't produce a
useful brief.

## Edge cases this pipeline handles

| Situation | Behavior |
|---|---|
| Competitor not in registry | `load_competitor` searches the web, and the LLM picks the official homepage so the pipeline continues; only fails (`competitor_website_not_found`) if neither the search nor LLM pick succeeds |
| Firecrawl `map` fails or returns no URLs | Fails at `map_website`, logged to failures.log |
| No pricing-like URL found (pattern match + LLM both fail) | Fails at `select_pricing_url` |
| Firecrawl `scrape` fails or returns empty content | Fails at `scrape_pricing` |
| MongoDB write-back fails | **Soft failure** — logged, but pipeline continues using in-memory scraped data |
| No previous snapshot exists (first run for this competitor) | `compare` explicitly notes no historical baseline was used, compares against our pricing only |
| No internal pricing (`our_pricing` empty) | Fails at `compare` — there's nothing meaningful to compare against |
| No churn data | Not a failure — comparison proceeds, churn risk notes are simply omitted/limited |
| LLM call fails (rate limit, timeout, bad JSON) | Retried up to 3x with backoff, then fails that node with reason logged |

## What's intentionally simple in this v1

- Master Agent takes a competitor name directly rather than parsing free-form
  natural language into a task plan. Add an NLU/routing layer in front of
  `run_pipeline()` later if needed.
- Only pricing is covered. Blogs/changelogs would follow the same shape but
  need different discovery (RSS-first) and different comparison logic
  (thematic, not numeric) — intentionally left out for now.
- Single competitor per run. Looping over multiple competitors is a thin
  wrapper around `run_pipeline()` — not added yet to keep this readable.

## Files

- `main.py` — entry point (CLI)
- `app.py` — entry point (Streamlit UI)
- `graph.py` — LangGraph wiring
- `nodes.py` — all pipeline step logic
- `state.py` — shared state schema
- `db.py` — MongoDB Atlas access
- `firecrawl_client.py` — Firecrawl map/scrape wrapper
- `llm_client.py` — Groq wrapper with retries
- `config.py` — env var loading/validation
- `logger_config.py` — logging setup (pipeline.log + failures.log)
- `competitor_registry.json` — competitor name → base URL
