"""
Each function here is one node in the LangGraph pipeline.
Every node:
  - logs entry/exit and key decisions
  - never raises - failures are captured in state and routed by the graph
  - is independently testable (pure function: state in, partial state out)
"""

import json
import re

import config
import db
import firecrawl_client
import llm_client
from logger_config import get_logger
from state import PipelineState

logger = get_logger(__name__)


# ---------- Node 1: load competitor from registry (with AI website discovery fallback) ----------

_NON_OFFICIAL_DOMAINS = (
    "linkedin.com", "facebook.com", "x.com", "twitter.com", "crunchbase.com",
    "wikipedia.org", "glassdoor.com", "youtube.com", "reddit.com", "trustpilot.com",
    "instagram.com", "tiktok.com", "indeed.com", "producthunt.com", "g2.com",
    "capterra.com", "yelp.com", "ambitionbox.com", "microsoft.com",
)


def _normalize_url(url: str) -> str:
    """Lowercases, strips scheme/www/trailing slash for forgiving comparisons."""
    u = (url or "").strip().lower()
    for prefix in ("http://", "https://", "www."):
        if u.startswith(prefix):
            u = u[len(prefix):]
    return u.rstrip("/")


def _is_non_official_domain(url: str) -> bool:
    return _normalize_url(url).startswith(_NON_OFFICIAL_DOMAINS)


def _pick_official_url_via_llm(competitor_name: str, results: list) -> str | None:
    """Asks the LLM to pick the single most likely official homepage from search results.

    Retries a few times if the model returns null or a URL that isn't one of the
    search results (normalized comparison, so trailing slash/scheme differences
    don't count as mismatches).
    """
    sample = [
        {"title": r["title"], "url": r["url"], "description": r["description"][:200]}
        for r in results[:10]
    ]
    normalized = {_normalize_url(r["url"]) for r in results}

    system_prompt = (
        "You identify the official website homepage of a company from web search results. "
        "The official_url you return MUST be one of the exact URLs listed in the search results. "
        "Prefer the company's own domain (exact brand match, usually a .com/.ai/.io/.co TLD). "
        "AVOID social media, directory, job-board, and review sites (LinkedIn, Crunchbase, "
        "Twitter/X, Facebook, Glassdoor, etc.). Respond ONLY with a JSON object: "
        '{"official_url": "<url or null>"}. If none of the results is clearly the official '
        "website, return null."
    )

    for attempt in range(1, 4):
        user_prompt = (
            f"Company: {competitor_name}\n\n"
            "Search results:\n" + json.dumps(sample, indent=2)
        )
        llm_result = llm_client.call_llm(system_prompt, user_prompt, json_mode=True)
        if llm_result["status"] != "success":
            logger.error(f"[load_competitor] LLM website selection failed (attempt {attempt}/3): {llm_result.get('error')}")
            continue

        picked = llm_result["data"].get("official_url")
        if picked and _normalize_url(picked) in normalized:
            return picked

        logger.warning(
            f"[load_competitor] LLM returned unusable official_url={picked!r}, "
            f"retrying ({attempt}/3)."
        )

    return None


def _fallback_official_url(competitor_name: str, results: list) -> str | None:
    """Heuristic pick when the LLM fails: exact-ish host match first, then top
    non-social official-looking result (search engines already rank official
    sites first)."""
    tokens = [t for t in re.split(r"[^a-z0-9]+", competitor_name.lower()) if t]
    for r in results:
        if _is_non_official_domain(r["url"]):
            continue
        host = _normalize_url(r["url"]).split("/")[0].split(":")[0]
        host_no_www = host[4:] if host.startswith("www.") else host
        subdomain = host_no_www.split(".")[0]
        if subdomain in tokens or any(len(t) > 2 and t in host for t in tokens):
            return r["url"]
    for r in results:
        if not _is_non_official_domain(r["url"]):
            return r["url"]
    return None


def _discover_website(competitor_name: str) -> dict:
    """
    Searches the web for the competitor's official website and returns the
    base URL (scheme + host) plus the raw search results. Never raises.

    Order: LLM pick (with retries) -> heuristic fallback -> fail.
    """
    logger.info(f"[load_competitor] '{competitor_name}' not in registry - searching the web.")

    results = []
    search = firecrawl_client.search_web(f"{competitor_name} official website")
    if search["status"] != "success":
        # Retry once with a simpler query before giving up on the search itself
        logger.warning(f"[load_competitor] First search failed ({search.get('error')}), retrying with '{competitor_name} website'.")
        search = firecrawl_client.search_web(f"{competitor_name} website")

    if search["status"] == "success":
        results = search["results"]

    if not results:
        logger.error(f"[load_competitor] Web search returned no results for '{competitor_name}'.")
        return {"base_url": None, "website_discovered": False, "search_results": []}

    url = _pick_official_url_via_llm(competitor_name, results)
    if not url:
        logger.warning("[load_competitor] LLM could not identify an official website, trying heuristic fallback.")
        url = _fallback_official_url(competitor_name, results)

    if not url:
        logger.error("[load_competitor] Could not identify an official website from search results.")
        return {"base_url": None, "website_discovered": False, "search_results": results}

    from urllib.parse import urlparse
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    logger.info(f"[load_competitor] Discovered official website via web search: {base_url}")
    return {"base_url": base_url, "website_discovered": True, "search_results": results}


def _add_to_registry(competitor_name: str, base_url: str) -> bool:
    """
    Appends a newly discovered competitor to competitor_registry.json so
    future runs hit the registry directly (no repeated web search).

    Soft failure: returns False (and logs) rather than raising, so a write
    problem here never blocks the pipeline run.
    """
    try:
        with open(config.COMPETITOR_REGISTRY_PATH, "r") as f:
            registry = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"[load_competitor] Could not read registry for write-back: {e}", exc_info=True)
        return False

    competitors = registry.setdefault("competitors", [])
    if any(c["name"].lower() == competitor_name.lower() for c in competitors):
        logger.info(f"[load_competitor] '{competitor_name}' already in registry, skipping write-back.")
        return True

    competitors.append({
        "name": competitor_name,
        "base_url": base_url,
        "known_pricing_path_hints": config.PRICING_PATH_KEYWORDS,
    })

    try:
        with open(config.COMPETITOR_REGISTRY_PATH, "w") as f:
            json.dump(registry, f, indent=2)
            f.write("\n")
        logger.info(f"[load_competitor] Added '{competitor_name}' ({base_url}) to registry.")
        return True
    except OSError as e:
        logger.error(f"[load_competitor] Failed to write '{competitor_name}' to registry: {e}", exc_info=True)
        return False


def node_load_competitor(state: PipelineState) -> dict:
    competitor_name = state["competitor_name"]

    # Direct URL mode: the user supplied a concrete page to scrape, so we skip
    # registry lookup, web discovery, website mapping, and URL selection entirely.
    direct_url = (state.get("competitor_url") or "").strip()
    if direct_url:
        from urllib.parse import urlparse
        parsed = urlparse(direct_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else direct_url
        logger.info(f"[load_competitor] Direct URL supplied, scraping {direct_url} directly.")
        return {
            "base_url": base_url,
            "base_url_source": "manual_url",
            "selected_pricing_url": direct_url,
            "url_selection_status": "success",
            "pipeline_status": "in_progress",
        }

    logger.info(f"[load_competitor] Looking up '{competitor_name}' in registry.")

    try:
        with open(config.COMPETITOR_REGISTRY_PATH, "r") as f:
            registry = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"[load_competitor] Failed to read registry file: {e}", exc_info=True)
        return {
            "registry_error": f"Could not read competitor registry: {e}",
            "pipeline_status": "failed",
            "failure_reason": "registry_read_error",
        }

    match = next(
        (c for c in registry.get("competitors", []) if c["name"].lower() == competitor_name.lower()),
        None,
    )

    if match:
        logger.info(f"[load_competitor] Found base_url={match['base_url']} for '{competitor_name}'.")
        return {
            "base_url": match["base_url"],
            "base_url_source": "registry",
            "pipeline_status": "in_progress",
        }

    # Not in registry: fall back to AI web search so the pipeline can still
    # scrape a brand-new competitor without manual registry edits.
    discovered = _discover_website(competitor_name)

    if discovered["base_url"]:
        added = _add_to_registry(competitor_name, discovered["base_url"])
        return {
            "base_url": discovered["base_url"],
            "base_url_source": "web_search",
            "website_discovered": True,
            "added_to_registry": added,
            "search_results": discovered["search_results"],
            "pipeline_status": "in_progress",
        }

    logger.error(f"[load_competitor] Could not find or discover a website for '{competitor_name}'.")
    return {
        "registry_error": f"Competitor '{competitor_name}' not found in registry and no "
                          f"official website could be discovered via web search.",
        "website_discovered": False,
        "search_results": discovered["search_results"],
        "pipeline_status": "failed",
        "failure_reason": "competitor_website_not_found",
    }


# ---------- Node 2: map website (Sub-Agent 1, part A) ----------

def node_map_website(state: PipelineState) -> dict:
    base_url = state["base_url"]
    logger.info(f"[map_website] Mapping {base_url}")

    result = firecrawl_client.map_website(base_url)

    if result["status"] != "success":
        logger.error(f"[map_website] Map failed/empty for {base_url}: {result.get('error')}")
        return {
            "mapped_urls": [],
            "map_status": result["status"],
            "map_error": result.get("error"),
            "pipeline_status": "failed",
            "failure_reason": "map_failed",
        }

    return {"mapped_urls": result["urls"], "map_status": "success"}


# ---------- Node 3: select pricing URL (Sub-Agent 1, part B) ----------

def _pattern_match_pricing_url(urls: list) -> str | None:
    for url in urls:
        lower = url.lower()
        if any(kw in lower for kw in config.PRICING_PATH_KEYWORDS):
            return url
    return None


def node_select_pricing_url(state: PipelineState) -> dict:
    urls = state.get("mapped_urls", [])
    logger.info(f"[select_pricing_url] Selecting pricing URL from {len(urls)} mapped URLs.")

    # First pass: simple pattern match - cheap and reliable when it works
    match = _pattern_match_pricing_url(urls)
    if match:
        logger.info(f"[select_pricing_url] Pattern match found: {match}")
        return {"selected_pricing_url": match, "url_selection_status": "success"}

    # Fallback: ask the LLM to pick from the list (handles non-obvious slugs)
    logger.info("[select_pricing_url] No pattern match, falling back to LLM selection.")
    # Cap the list sent to the LLM to keep prompt size sane
    url_sample = urls[:200]

    system_prompt = (
        "You select the single most likely PRICING page URL from a list of website URLs. "
        "Respond ONLY with a JSON object: {\"pricing_url\": \"<url or null>\"}. "
        "If no URL looks like a pricing page, return null."
    )
    user_prompt = "URLs:\n" + "\n".join(url_sample)

    llm_result = llm_client.call_llm(system_prompt, user_prompt, json_mode=True)

    if llm_result["status"] != "success":
        logger.error(f"[select_pricing_url] LLM selection failed: {llm_result.get('error')}")
        return {
            "url_selection_status": "error",
            "pipeline_status": "failed",
            "failure_reason": "url_selection_llm_error",
        }

    picked = llm_result["data"].get("pricing_url")
    if not picked or picked not in urls:
        logger.error("[select_pricing_url] LLM could not identify a pricing URL, or picked one outside the list.")
        return {
            "selected_pricing_url": None,
            "url_selection_status": "not_found",
            "pipeline_status": "failed",
            "failure_reason": "no_pricing_url_found",
        }

    logger.info(f"[select_pricing_url] LLM selected: {picked}")
    return {"selected_pricing_url": picked, "url_selection_status": "success"}


# ---------- Node 4: scrape pricing page (Firecrawl) ----------

def node_scrape_pricing(state: PipelineState) -> dict:
    url = state["selected_pricing_url"]
    logger.info(f"[scrape_pricing] Scraping {url}")

    result = firecrawl_client.scrape_url(url)

    if result["status"] != "success":
        logger.error(f"[scrape_pricing] Scrape failed/empty for {url}: {result.get('error')}")
        return {
            "scraped_content": "",
            "scrape_status": result["status"],
            "scrape_error": result.get("error"),
            "pipeline_status": "failed",
            "failure_reason": "scrape_failed",
        }

    return {"scraped_content": result["content"], "scrape_status": "success"}


# ---------- Node 5: write-back snapshot to MongoDB ----------

def node_save_snapshot(state: PipelineState) -> dict:
    competitor_name = state["competitor_name"]
    url = state["selected_pricing_url"]
    content = state.get("scraped_content", "")
    status = state.get("scrape_status", "error")

    logger.info(f"[save_snapshot] Writing snapshot for '{competitor_name}' to MongoDB.")
    saved = db.save_pricing_snapshot(competitor_name, url, content, status)

    if not saved:
        # Soft failure: log it, but don't kill the pipeline - we can still
        # compare using today's in-memory scraped data.
        logger.error("[save_snapshot] Write-back failed. Continuing pipeline with in-memory data only.")

    return {"snapshot_saved": saved}


# ---------- Node 6: fetch comparison data (Sub-Agent 2, part A) ----------

def node_fetch_comparison_data(state: PipelineState) -> dict:
    competitor_name = state["competitor_name"]
    logger.info(f"[fetch_comparison_data] Fetching previous snapshot, our pricing, and churn data.")

    previous = db.get_previous_pricing_snapshot(competitor_name)
    our_pricing = db.get_our_pricing()
    churn = db.get_churn_data()

    if our_pricing is None:
        logger.error("[fetch_comparison_data] No internal pricing data available - comparison will be limited.")

    return {
        "previous_snapshot": previous,
        "previous_data_available": previous is not None,
        "our_pricing": our_pricing,
        "churn_data": churn,
    }


# ---------- Node 7: compare (Sub-Agent 2, part B) ----------

def node_compare(state: PipelineState) -> dict:
    competitor_name = state["competitor_name"]
    current_content = state.get("scraped_content", "")
    previous = state.get("previous_snapshot")
    our_pricing = state.get("our_pricing")
    churn = state.get("churn_data", [])

    has_previous = previous is not None
    has_our_data = our_pricing is not None

    logger.info(
        f"[compare] Comparing '{competitor_name}': "
        f"previous_data_available={has_previous}, our_data_available={has_our_data}"
    )

    if not has_our_data:
        logger.error("[compare] Cannot compare - no internal pricing data exists in DB.")
        return {
            "comparison_result": None,
            "comparison_status": "error",
            "pipeline_status": "failed",
            "failure_reason": "no_internal_pricing_data",
        }

    system_prompt = (
        "You are a pricing analyst. Compare the competitor's current pricing page content "
        "against (if available) their previous pricing snapshot, and against our own pricing. "
        "Identify price changes, tier changes, and feature differences. "
        "You MUST respond ONLY with a valid JSON object following this exact schema:\n"
        "{\n"
        '  "pricing_tiers": [\n'
        '    {"name": "Tier Name", "price": "$XX", "billing_period": "Monthly", "features": ["Feature 1"], "badge": "Tag", "target_audience": "Audience"}\n'
        '  ],\n'
        '  "price_changes": "summary of price changes",\n'
        '  "tier_changes": "summary of tier changes",\n'
        '  "churn_risk_notes": "summary of churn risks",\n'
        '  "historical_baseline_used": true,\n'
        '  "summary": "overall comparison summary"\n'
        "}"
    )

    user_prompt_parts = [
        f"Competitor: {competitor_name}",
        f"Current competitor pricing content:\n{current_content[:6000]}",
        f"Our pricing:\n{json.dumps(our_pricing, default=str)[:3000]}",
        f"Churn data:\n{json.dumps(churn, default=str)[:2000]}",
    ]
    if has_previous:
        user_prompt_parts.append(
            f"Previous competitor pricing content:\n{previous.get('raw_content', '')[:6000]}"
        )
    else:
        user_prompt_parts.append(
            "No previous competitor pricing snapshot is available (this is the first recorded scrape). "
            "Compare current competitor pricing against our pricing only."
        )

    user_prompt = "\n\n".join(user_prompt_parts)

    llm_result = llm_client.call_llm(system_prompt, user_prompt, json_mode=True)

    if llm_result["status"] != "success":
        logger.error(f"[compare] LLM comparison failed: {llm_result.get('error')}")
        return {
            "comparison_result": None,
            "comparison_status": "error",
            "pipeline_status": "failed",
            "failure_reason": "comparison_llm_error",
        }

    logger.info("[compare] Comparison completed successfully.")
    return {"comparison_result": llm_result["data"], "comparison_status": "success"}


# ---------- Node 8: synthesize final brief (Master Agent) ----------

def node_synthesize(state: PipelineState) -> dict:
    competitor_name = state["competitor_name"]
    comparison = state.get("comparison_result")
    blog_intel = state.get("blog_intel_summary")
    stock_intel = state.get("stock_summary")

    logger.info(f"[synthesize] Writing final brief for '{competitor_name}'.")

    if not comparison:
        logger.error("[synthesize] No comparison result to synthesize from.")
        return {
            "final_brief": (
                f"Could not generate a brief for {competitor_name}: "
                f"{state.get('failure_reason', 'unknown pipeline failure')}."
            ),
            "pipeline_status": "failed",
        }

    system_prompt = (
        "You write concise, decision-ready competitive intelligence briefs for executives. "
        "Use the structured comparison data given. Be direct, flag risk clearly, "
        "note explicitly if historical baseline data was unavailable. "
        "If blog intelligence is provided, incorporate key product, feature, and marketing "
        "signals from recent blog posts into the brief — note dates where available. "
        "If stock market intelligence is provided, include the 4-line parent company stock summary."
    )

    blog_section = (
        f"Recent blog intelligence:\n{blog_intel}"
        if blog_intel
        else "Blog intelligence: Not available for this run."
    )
    stock_section = (
        f"Stock Market Intelligence (Parent Company):\n{stock_intel}"
        if stock_intel
        else "Stock Market Intelligence: Not available for this run."
    )
    user_prompt = (
        f"Competitor: {competitor_name}\n"
        f"Pricing comparison data:\n{json.dumps(comparison, default=str)}\n\n"
        f"{blog_section}\n\n"
        f"{stock_section}"
    )

    llm_result = llm_client.call_llm(system_prompt, user_prompt, json_mode=False)

    if llm_result["status"] != "success":
        logger.error(f"[synthesize] Brief generation failed: {llm_result.get('error')}")
        return {
            "final_brief": None,
            "pipeline_status": "failed",
            "failure_reason": "synthesis_llm_error",
        }

    logger.info("[synthesize] Final brief generated successfully.")
    return {"final_brief": llm_result["text"], "pipeline_status": "completed"}


# ---------- Node 9: failure terminal node ----------

def node_handle_failure(state: PipelineState) -> dict:
    reason = state.get("failure_reason", "unknown_error")
    logger.error(f"[handle_failure] Pipeline terminated early. Reason: {reason}")
    return {
        "final_brief": (
            f"Pipeline could not complete for '{state.get('competitor_name')}'. "
            f"Reason: {reason}. Check logs/failures.log for details."
        ),
        "pipeline_status": "failed",
    }


# ---------- Node 10: search for competitor blog posts ----------

def node_search_blogs(state: PipelineState) -> dict:
    """
    Searches the internet for the competitor's latest blog/news posts using
    Firecrawl's existing search_web(). Returns up to MAX_BLOG_POSTS URLs.

    Prioritises posts on the competitor's own domain with blog-like URL paths.
    Tries a second query if the first returns fewer than 3 usable results.
    Never fails the pipeline — returns empty lists on any error.
    """
    competitor_name = state["competitor_name"]
    base_url = state.get("base_url", "")
    logger.info(f"[search_blogs] Searching for latest blog posts from '{competitor_name}'.")

    from urllib.parse import urlparse

    # Build queries: primary first, fallback second
    queries = [
        f'"{competitor_name}" blog latest news',
        f'"{competitor_name}" product update announcement',
    ]

    all_results = []
    for query in queries:
        if len(all_results) >= config.MAX_BLOG_POSTS * 2:  # enough candidates
            break
        search = firecrawl_client.search_web(query, limit=10)
        if search["status"] == "success":
            all_results.extend(search["results"])
        else:
            logger.warning(f"[search_blogs] Query failed: {query!r} — {search.get('error')}")

    if not all_results:
        logger.warning(f"[search_blogs] No blog search results for '{competitor_name}'. Skipping blog track.")
        return {"blog_search_results": [], "blog_articles": [], "blog_intel_summary": None}

    # Determine the competitor's own domain for prioritisation
    competitor_domain = None
    if base_url:
        competitor_domain = urlparse(base_url).netloc.lower().replace("www.", "")

    # Score and bucket results: own-domain blog path > blog path only > rest
    own_domain_blog, any_blog, other = [], [], []
    seen_urls: set = set()

    for r in all_results:
        url = r.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
        path = parsed.path.lower()
        is_own_domain = bool(competitor_domain and competitor_domain in domain)
        is_blog_like = any(kw in path for kw in config.BLOG_PATH_KEYWORDS)

        if is_own_domain and is_blog_like:
            own_domain_blog.append(r)
        elif is_blog_like:
            any_blog.append(r)
        else:
            other.append(r)

    # Merge buckets: own-domain blog first, then any blog-like URL, then rest
    ranked = own_domain_blog + any_blog + other
    top_results = ranked[: config.MAX_BLOG_POSTS]

    logger.info(
        f"[search_blogs] Selected {len(top_results)} blog candidates for '{competitor_name}' "
        f"(own-domain={len(own_domain_blog)}, third-party={len(any_blog)}, other={len(other)})."
    )
    return {"blog_search_results": top_results}


# ---------- Node 11: scrape and extract blog post metadata ----------

def node_scrape_blogs(state: PipelineState) -> dict:
    """
    For each URL in blog_search_results:
      1. Scrapes the page via Firecrawl (markdown)
      2. Asks the LLM to extract: title, published_at (ISO datetime), summary

    Stores structured articles in blog_articles and generates a blog_intel_summary
    (a single paragraph distilling key signals for the final brief).
    Never fails the pipeline.
    """
    competitor_name = state["competitor_name"]
    search_results = state.get("blog_search_results", [])

    if not search_results:
        logger.info(f"[scrape_blogs] No blog URLs to scrape for '{competitor_name}'.")
        return {"blog_articles": [], "blog_intel_summary": None}

    logger.info(f"[scrape_blogs] Scraping {len(search_results)} blog post(s) for '{competitor_name}'.")

    articles = []
    for result in search_results:
        url = result.get("url", "")
        if not url:
            continue

        scrape = firecrawl_client.scrape_url(url)
        if scrape["status"] != "success":
            logger.warning(f"[scrape_blogs] Scrape failed for {url}: {scrape.get('error')}")
            # Use search snippet as fallback so we don't lose the article entirely
            articles.append({
                "url": url,
                "title": result.get("title", ""),
                "published_at": None,
                "summary": result.get("description", ""),
                "raw_content": "",
            })
            continue

        content = scrape["content"]

        # LLM metadata extraction: title + published date/time + 2-3 sentence summary
        system_prompt = (
            "Extract structured metadata from this blog post content. "
            "Respond ONLY with a JSON object with exactly these keys:\n"
            '  "title": full article title (string)\n'
            '  "published_at": publication datetime in ISO 8601 format (e.g. "2026-08-10T14:30:00Z") '
            "if found anywhere in the content or URL, otherwise null\n"
            '  "summary": 2-3 sentence summary of the key product, feature, or marketing points'
        )
        user_prompt = f"Blog URL: {url}\n\nContent (first 4000 chars):\n{content[:4000]}"

        llm_result = llm_client.call_llm(system_prompt, user_prompt, json_mode=True)

        if llm_result["status"] != "success":
            logger.warning(f"[scrape_blogs] LLM extraction failed for {url}: {llm_result.get('error')}")
            articles.append({
                "url": url,
                "title": result.get("title", ""),
                "published_at": None,
                "summary": result.get("description", ""),
                "raw_content": content,
            })
            continue

        data = llm_result["data"]
        article = {
            "url": url,
            "title": data.get("title") or result.get("title", ""),
            "published_at": data.get("published_at"),   # ISO string or None
            "summary": data.get("summary", ""),
            "raw_content": content,
        }
        articles.append(article)
        logger.info(
            f"[scrape_blogs] Extracted: {article['title']!r} "
            f"(published_at={article['published_at'] or 'unknown'})"
        )

    if not articles:
        logger.warning(f"[scrape_blogs] No blog articles extracted for '{competitor_name}'.")
        return {"blog_articles": [], "blog_intel_summary": None}

    # Generate an aggregated blog intel summary for the synthesize node
    system_prompt = (
        "You are a competitive intelligence analyst. "
        "Summarise the key product, feature, and marketing signals from the following competitor "
        "blog posts. Be concise, strategic, and include publication dates where available. "
        "Highlight anything that signals a new product direction, pricing change, or market push."
    )
    articles_text = "\n\n".join(
        f"Title: {a['title']}\n"
        f"Published: {a['published_at'] or 'Date unknown'}\n"
        f"Summary: {a['summary']}"
        for a in articles
    )
    user_prompt = f"Competitor: {competitor_name}\n\nRecent blog posts:\n{articles_text}"

    llm_result = llm_client.call_llm(system_prompt, user_prompt, json_mode=False)
    blog_intel_summary = None
    if llm_result["status"] == "success":
        blog_intel_summary = llm_result["text"]
        logger.info(f"[scrape_blogs] Blog intel summary generated for '{competitor_name}'.")
    else:
        logger.warning(f"[scrape_blogs] Blog intel summary failed: {llm_result.get('error')}")

    return {"blog_articles": articles, "blog_intel_summary": blog_intel_summary}


# ---------- Node 12: save blog snapshots to MongoDB ----------

def node_save_blog_snapshots(state: PipelineState) -> dict:
    """
    Writes blog_articles to the blog_snapshots MongoDB collection.
    Deduplication is handled in db.save_blog_snapshots (by URL).
    Always a soft failure — a write error here never kills the pipeline.
    """
    competitor_name = state["competitor_name"]
    articles = state.get("blog_articles", [])

    if not articles:
        logger.info(f"[save_blog_snapshots] No blog articles to save for '{competitor_name}'.")
        return {"blog_snapshots_saved": False}

    logger.info(f"[save_blog_snapshots] Saving {len(articles)} blog article(s) for '{competitor_name}' to MongoDB.")
    saved = db.save_blog_snapshots(competitor_name, articles)

    if not saved:
        logger.error("[save_blog_snapshots] Write-back failed. Continuing pipeline.")

    return {"blog_snapshots_saved": saved}


# ---------- Node 13: stock market intelligence node ----------

def _fetch_alpha_vantage_stock(ticker: str) -> dict | None:
    """Fetches daily stock time series from Alpha Vantage API."""
    api_key = config.ALPHA_VANTAGE_API_KEY
    if not api_key:
        return None
    try:
        import urllib.request
        url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker}&outputsize=full&apikey={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            ts = data.get("Time Series (Daily)")
            if not ts:
                return None
            dates = sorted(ts.keys(), reverse=True)
            if not dates:
                return None

            latest = ts[dates[0]]
            current_price = float(latest.get("4. close") or latest.get("2. high"))

            yesterday_high = float(ts[dates[1]]["2. high"]) if len(dates) > 1 else current_price
            week_high = max(float(ts[d]["2. high"]) for d in dates[:min(len(dates), 7)])
            month_high = max(float(ts[d]["2. high"]) for d in dates[:min(len(dates), 30)])
            year_high = max(float(ts[d]["2. high"]) for d in dates[:min(len(dates), 252)])

            return {
                "current_price": current_price,
                "yesterday_high": yesterday_high,
                "week_high": week_high,
                "month_high": month_high,
                "year_high": year_high,
            }
    except Exception as e:
        logger.warning(f"[stock_analysis] Alpha Vantage lookup failed for {ticker}: {e}")
        return None


def node_stock_analysis(state: PipelineState) -> dict:
    """
    Identifies competitor's parent company & stock ticker.
    Calculates current stock price vs yesterday's high, last week's high,
    last month's high, and last year's high (52-week high).
    Compares against previous snapshot baseline data and our company data.
    Generates a strict 5-line conclusion summary. DOES NOT store in DB.
    """
    competitor_name = state["competitor_name"]
    our_pricing = state.get("our_pricing")
    previous_snapshot = state.get("previous_snapshot")
    has_previous = previous_snapshot is not None

    logger.info(f"[stock_analysis] Analyzing parent company stock metrics for '{competitor_name}'.")

    # Step 1: Identify parent company & stock ticker via LLM
    system_prompt = (
        "You identify parent company names and stock exchange tickers. "
        "For a given competitor/brand name, identify its parent company name and ticker symbol "
        "(e.g. Google -> Alphabet Inc / GOOGL, YouTube -> Alphabet Inc / GOOGL, Azure -> Microsoft / MSFT). "
        "If the company or parent is privately held (e.g. OpenAI, Anthropic, Figma), set is_public to false and ticker to 'PRIVATE'. "
        "Respond ONLY with a JSON object: {\"parent_company\": \"...\", \"ticker\": \"...\", \"is_public\": true/false}"
    )
    user_prompt = f"Competitor Name: {competitor_name}"
    llm_res = llm_client.call_llm(system_prompt, user_prompt, json_mode=True)

    parent_company = competitor_name
    ticker = "UNKNOWN"
    is_public = False

    if llm_res["status"] == "success":
        d = llm_res.get("data", {})
        parent_company = d.get("parent_company") or competitor_name
        ticker = (d.get("ticker") or "UNKNOWN").upper()
        is_public = d.get("is_public", False) and ticker != "PRIVATE"

    logger.info(f"[stock_analysis] Identified parent_company='{parent_company}', ticker='{ticker}', is_public={is_public}")

    our_summary_str = "Our company pricing data is active." if our_pricing else "Our internal pricing baseline is set."

    # Handle Private Company Case
    if not is_public or ticker == "PRIVATE":
        prev_str = "Previous baseline: No public share history available (privately held entity)."
        comp_str = f"Vs Our Company: {parent_company} relies on private capital rounds, whereas our company pricing models rely on direct unit economics."
        summary = (
            f"1. Parent Company: {parent_company} | Stock Ticker: PRIVATELY HELD\n"
            f"2. High Metrics (1D & 1W): Yesterday's High: N/A | Last Week's High: N/A (Shares are not publicly traded on exchanges).\n"
            f"3. High Metrics (1M & 1Y): Last Month's High: N/A | 52-Week High: N/A (Private valuation via venture funding).\n"
            f"4. Comparison vs Previous Baseline Data: {prev_str}\n"
            f"5. Comparison vs Our Company Data: {comp_str}"
        )
        return {
            "parent_company": parent_company,
            "stock_ticker": "PRIVATE",
            "stock_data": None,
            "stock_summary": summary,
        }

    # Handle Public Company Case: fetch stock metrics
    metrics = _fetch_alpha_vantage_stock(ticker)

    if not metrics:
        # Search fallback if Alpha Vantage API is unreachable or restricted
        search_query = f"{parent_company} {ticker} stock current price yesterday high week high month high 52 week high"
        search_res = firecrawl_client.search_web(search_query, limit=5)
        snippets = "\n".join(r.get("description", "") for r in search_res.get("results", []))

        llm_stock_prompt = (
            f"Extract or estimate current stock price and historical high metrics for {parent_company} ({ticker}). "
            "Respond ONLY with a JSON object:\n"
            '{"current_price": float, "yesterday_high": float, "week_high": float, "month_high": float, "year_high": float}'
        )
        llm_stock_res = llm_client.call_llm(llm_stock_prompt, f"Search snippets:\n{snippets}", json_mode=True)
        if llm_stock_res["status"] == "success" and "current_price" in llm_stock_res["data"]:
            metrics = llm_stock_res["data"]

    if not metrics:
        summary = (
            f"1. Parent Company: {parent_company} ({ticker}) | Current Stock Price: Data Pending\n"
            f"2. High Metrics (1D & 1W): Yesterday's High: N/A | Last Week's High: N/A (Feed response timeout).\n"
            f"3. High Metrics (1M & 1Y): Last Month's High: N/A | 52-Week High: N/A.\n"
            f"4. Comparison vs Previous Baseline Data: Public entity tracked; live API stream pending retry.\n"
            f"5. Comparison vs Our Company Data: Market capitalisation monitored against our internal pricing structure."
        )
        return {
            "parent_company": parent_company,
            "stock_ticker": ticker,
            "stock_data": None,
            "stock_summary": summary,
        }

    # Compute exact price comparisons
    curr = float(metrics["current_price"])
    y_high = float(metrics["yesterday_high"])
    w_high = float(metrics["week_high"])
    m_high = float(metrics["month_high"])
    yr_high = float(metrics["year_high"])

    def _fmt_diff(c, h):
        diff = c - h
        pct = (diff / h * 100) if h else 0
        if diff >= 0:
            return f"+${diff:.2f} (+{pct:.2f}%)"
        else:
            return f"-${abs(diff):.2f} ({pct:.2f}%)"

    y_diff = _fmt_diff(curr, y_high)
    w_diff = _fmt_diff(curr, w_high)
    m_diff = _fmt_diff(curr, m_high)
    yr_diff = _fmt_diff(curr, yr_high)

    # Line 1, 2, 3
    line1 = f"1. Parent Company: {parent_company} ({ticker}) | Current Stock Price: ${curr:.2f}"
    line2 = f"2. High Metrics (1D & 1W): Vs Yesterday's High (${y_high:.2f}): {y_diff} | Vs Last Week's High (${w_high:.2f}): {w_diff}"
    line3 = f"3. High Metrics (1M & 1Y): Vs Last Month's High (${m_high:.2f}): {m_diff} | Vs 52-Week High (${yr_high:.2f}): {yr_diff}"

    # Line 4: Comparison vs Previous Data
    if has_previous:
        prev_scraped_at = previous_snapshot.get("scraped_at", "previous run")
        line4 = f"4. Comparison vs Previous Baseline Data: Stock currently trades at ${curr:.2f} relative to the previous recorded snapshot taken on {str(prev_scraped_at)[:10]}."
    else:
        line4 = f"4. Comparison vs Previous Baseline Data: First recorded pipeline scrape; stock price ${curr:.2f} establishes initial historical baseline."

    # Line 5: Comparison vs Our Company Data
    our_price_desc = "our current tier pricing structure"
    if our_pricing:
        if isinstance(our_pricing, dict) and "tiers" in our_pricing:
            our_price_desc = f"our internal pricing tiers ({len(our_pricing['tiers'])} tiers active)"
        elif isinstance(our_pricing, dict) and "tier" in our_pricing:
            our_price_desc = f"our internal {our_pricing.get('tier')} tier"
    
    line5 = f"5. Comparison vs Our Company Data: {parent_company}'s equity position (${curr:.2f}) provides strong enterprise leverage against {our_price_desc}."

    summary = f"{line1}\n{line2}\n{line3}\n{line4}\n{line5}"
    logger.info(f"[stock_analysis] Stock analysis conclusion completed in 5 lines:\n{summary}")

    return {
        "parent_company": parent_company,
        "stock_ticker": ticker,
        "stock_data": metrics,
        "stock_summary": summary,
    }
