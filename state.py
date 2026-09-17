"""
Shared state passed between all nodes in the LangGraph pipeline.

Every node reads from and writes to this dict. Keeping it a flat TypedDict
(rather than nested objects) makes it easy to log the entire state at any
point in the graph for debugging.
"""

from typing import TypedDict, Optional, List


class PipelineState(TypedDict, total=False):
    # --- input ---
    competitor_name: str
    competitor_url: Optional[str]    # direct URL to scrape, skips map/select

    # --- competitor lookup ---
    base_url: Optional[str]
    base_url_source: Optional[str]   # "registry" | "web_search"
    website_discovered: bool         # True if found via web search (not in registry)
    added_to_registry: Optional[bool]  # whether the discovered competitor was written to the registry file
    search_results: List[dict]       # raw web search results used for discovery
    registry_error: Optional[str]

    # --- mapping step ---
    mapped_urls: List[str]
    map_status: Optional[str]        # "success" | "empty" | "error"
    map_error: Optional[str]

    # --- URL selection step ---
    selected_pricing_url: Optional[str]
    url_selection_status: Optional[str]  # "success" | "not_found" | "error"

    # --- scraping step ---
    scraped_content: Optional[str]
    scrape_status: Optional[str]     # "success" | "empty" | "error"
    scrape_error: Optional[str]

    # --- write-back step ---
    snapshot_saved: Optional[bool]

    # --- comparison data ---
    previous_snapshot: Optional[dict]
    previous_data_available: bool
    our_pricing: Optional[dict]
    churn_data: List[dict]

    # --- comparison result ---
    comparison_result: Optional[dict]
    comparison_status: Optional[str]  # "success" | "error"

    # --- final output ---
    final_brief: Optional[str]

    # --- overall pipeline status ---
    pipeline_status: str              # "in_progress" | "completed" | "failed"
    failure_reason: Optional[str]

    # --- blog intelligence ---
    blog_search_results: List[dict]   # raw Firecrawl search results (up to MAX_BLOG_POSTS)
    blog_articles: List[dict]         # scraped + LLM-extracted articles with published_at
    blog_snapshots_saved: Optional[bool]
    blog_intel_summary: Optional[str] # LLM-written summary of key themes across blog posts

    # --- stock market intelligence ---
    parent_company: Optional[str]     # Name of parent company (or same if standalone)
    stock_ticker: Optional[str]       # Stock ticker symbol e.g. "GOOGL" or "PRIVATE"
    stock_data: Optional[dict]        # Raw metrics: current_price, yesterday_high, week_high, month_high, year_high
    stock_summary: Optional[str]     # 4-line conclusion on stock positioning (not saved in DB)
