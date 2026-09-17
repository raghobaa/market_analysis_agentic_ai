"""
Thin wrapper around Firecrawl's search + map + scrape endpoints.

search_web()  -> searches the web for a company's official website
map_website()  -> discovers all URLs on a site (sitemap + links)
scrape_url()   -> scrapes a single specific URL and returns clean content

All functions catch and log errors rather than raising, returning a
result dict with a "status" field instead - this keeps failure handling
consistent and visible in the graph state rather than as stack traces.
"""

from typing import Optional

from firecrawl import FirecrawlApp

import config
from logger_config import get_logger

logger = get_logger(__name__)

_app: Optional[FirecrawlApp] = None


def _get_app() -> FirecrawlApp:
    global _app
    if _app is None:
        _app = FirecrawlApp(api_key=config.FIRECRAWL_API_KEY)
    return _app


def search_web(query: str, limit: int = 5) -> dict:
    """
    Searches the web for a company's official website.

    Returns:
        {"status": "success", "results": [{"title", "url", "description"}, ...]}
        {"status": "empty", "results": [], "error": "..."}
        {"status": "error", "results": [], "error": "..."}
    """
    try:
        app = _get_app()
        logger.info(f"Searching web for: {query}")
        result = app.search(query, limit=limit)

        web_results = []
        if isinstance(result, dict):
            web_results = result.get("web") or result.get("data") or []
        else:
            web_results = getattr(result, "web", None) or getattr(result, "data", None) or []

        results = []
        for item in web_results:
            if isinstance(item, dict):
                title = item.get("title") or ""
                url = item.get("url") or ""
                description = item.get("description") or ""
            else:
                title = getattr(item, "title", None) or ""
                url = getattr(item, "url", None) or ""
                description = getattr(item, "description", None) or ""
            if url:
                results.append({"title": title, "url": url, "description": description})

        if not results:
            logger.error(f"Firecrawl search returned no results for '{query}'")
            return {"status": "empty", "results": [], "error": "No search results returned"}

        logger.info(f"Found {len(results)} web results for '{query}'")
        return {"status": "success", "results": results}

    except Exception as e:
        logger.error(f"Firecrawl search failed for '{query}': {e}", exc_info=True)
        return {"status": "error", "results": [], "error": str(e)}


def map_website(base_url: str) -> dict:
    """
    Discovers URLs on a site.

    Returns:
        {"status": "success", "urls": [...]} or
        {"status": "error", "urls": [], "error": "..."}
    """
    try:
        app = _get_app()
        logger.info(f"Mapping website: {base_url}")
        result = app.map_url(base_url)

        # firecrawl-py returns MapData (.links) in v2 SDK, each link being a
        # LinkResult object, or a dict in older versions. Normalize to plain URL strings.
        raw_links = None
        if isinstance(result, dict):
            raw_links = result.get("links") or result.get("urls")
        else:
            raw_links = getattr(result, "links", None) or getattr(result, "urls", None)

        urls = []
        for link in raw_links or []:
            if isinstance(link, str):
                urls.append(link)
            elif isinstance(link, dict):
                if link.get("url"):
                    urls.append(link["url"])
            else:
                url = getattr(link, "url", None)
                if url:
                    urls.append(url)

        if not urls:
            logger.error(f"Firecrawl map returned no URLs for {base_url}")
            return {"status": "empty", "urls": [], "error": "No URLs discovered"}

        logger.info(f"Mapped {len(urls)} URLs from {base_url}")
        return {"status": "success", "urls": urls}

    except Exception as e:
        logger.error(f"Firecrawl map failed for {base_url}: {e}", exc_info=True)
        return {"status": "error", "urls": [], "error": str(e)}


def scrape_url(url: str) -> dict:
    """
    Scrapes a single URL.

    Returns:
        {"status": "success", "content": "...markdown..."} or
        {"status": "empty", "content": "", "error": "..."} or
        {"status": "error", "content": "", "error": "..."}
    """
    try:
        app = _get_app()
        logger.info(f"Scraping URL: {url}")
        result = app.scrape_url(url, formats=["markdown"])

        content = None
        if isinstance(result, dict):
            content = result.get("markdown") or result.get("content")
        else:
            content = getattr(result, "markdown", None) or getattr(result, "content", None)

        if not content or not content.strip():
            logger.error(f"Firecrawl scrape returned empty content for {url}")
            return {"status": "empty", "content": "", "error": "Empty content returned"}

        logger.info(f"Scraped {len(content)} characters from {url}")
        return {"status": "success", "content": content}

    except Exception as e:
        logger.error(f"Firecrawl scrape failed for {url}: {e}", exc_info=True)
        return {"status": "error", "content": "", "error": str(e)}
