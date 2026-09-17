"""
Entry point.

Usage:
    python main.py "CompetitorX"
    python main.py "https://gemini.google/subscriptions/"

Runs the full pricing intelligence pipeline for the given competitor name.
If the name matches a "name" entry in competitor_registry.json its base_url is
used; otherwise the official website is discovered via AI web search. If a URL
is passed instead of a name, that exact URL is scraped directly (skipping
website mapping and URL selection). Prints the final brief. Full trace goes to
logs/pipeline.log, failures to logs/failures.log.
"""

import sys
from urllib.parse import urlparse

import config
from graph import build_graph
from logger_config import get_logger

logger = get_logger(__name__)


def run_pipeline(competitor_name: str, competitor_url: str | None = None) -> dict:
    config.validate_env()

    app = build_graph()

    initial_state = {
        "competitor_name": competitor_name,
        "pipeline_status": "in_progress",
    }
    if competitor_url:
        initial_state["competitor_url"] = competitor_url

    logger.info(f"=== Starting pipeline run for '{competitor_name}' ===")
    final_state = app.invoke(initial_state)
    logger.info(f"=== Pipeline run finished with status: {final_state.get('pipeline_status')} ===")

    return final_state


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <competitor_name | website_url>")
        sys.exit(1)

    arg = sys.argv[1]

    # If the arg is a URL, treat it as a direct page to scrape.
    competitor_url = None
    if arg.startswith(("http://", "https://")):
        competitor_url = arg
        arg = urlparse(arg).netloc or arg

    try:
        result = run_pipeline(arg, competitor_url=competitor_url)
    except EnvironmentError as e:
        # Missing env vars - fail fast and clearly, don't even enter the graph
        logger.error(f"Startup failed: {e}")
        print(f"\nSTARTUP ERROR: {e}\n")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"STATUS: {result.get('pipeline_status')}")
    print("=" * 60)
    print(result.get("final_brief", "No brief generated."))
