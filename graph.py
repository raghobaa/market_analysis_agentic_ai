"""
Builds the LangGraph StateGraph for the pricing intelligence pipeline.

Flow:
  load_competitor -> map_website -> select_pricing_url -> scrape_pricing
    -> save_snapshot -> fetch_comparison_data -> compare
    -> search_blogs -> scrape_blogs -> save_blog_snapshots
    -> stock_analysis -> synthesize -> END

The blog & stock tracks run sequentially after compare (before synthesize).
"""

from langgraph.graph import StateGraph, END

import nodes
from logger_config import get_logger
from state import PipelineState

logger = get_logger(__name__)


def _route_after_load(state: PipelineState) -> str:
    """After load_competitor: skip map/select if a direct URL was supplied."""
    if state.get("pipeline_status") == "failed":
        return "handle_failure"
    if state.get("selected_pricing_url"):
        logger.info("[router] Direct URL provided, skipping map_website/select_pricing_url -> scrape_pricing.")
        return "scrape_pricing"
    return "map_website"


def _route_after(node_name: str):
    """
    Returns a routing function: if pipeline_status is "failed", go to
    handle_failure; otherwise continue to the given next node.
    """
    def router(state: PipelineState) -> str:
        if state.get("pipeline_status") == "failed":
            logger.info(f"[router] Failure detected after '{node_name}', routing to handle_failure.")
            return "handle_failure"
        return "continue"
    return router


def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("load_competitor", nodes.node_load_competitor)
    graph.add_node("map_website", nodes.node_map_website)
    graph.add_node("select_pricing_url", nodes.node_select_pricing_url)
    graph.add_node("scrape_pricing", nodes.node_scrape_pricing)
    graph.add_node("save_snapshot", nodes.node_save_snapshot)
    graph.add_node("fetch_comparison_data", nodes.node_fetch_comparison_data)
    graph.add_node("compare", nodes.node_compare)
    graph.add_node("search_blogs", nodes.node_search_blogs)
    graph.add_node("scrape_blogs", nodes.node_scrape_blogs)
    graph.add_node("save_blog_snapshots", nodes.node_save_blog_snapshots)
    graph.add_node("stock_analysis", nodes.node_stock_analysis)
    graph.add_node("synthesize", nodes.node_synthesize)
    graph.add_node("handle_failure", nodes.node_handle_failure)

    graph.set_entry_point("load_competitor")

    graph.add_conditional_edges(
        "load_competitor", _route_after_load,
        {"scrape_pricing": "scrape_pricing", "map_website": "map_website", "handle_failure": "handle_failure"},
    )
    graph.add_conditional_edges(
        "map_website", _route_after("map_website"),
        {"continue": "select_pricing_url", "handle_failure": "handle_failure"},
    )
    graph.add_conditional_edges(
        "select_pricing_url", _route_after("select_pricing_url"),
        {"continue": "scrape_pricing", "handle_failure": "handle_failure"},
    )
    graph.add_conditional_edges(
        "scrape_pricing", _route_after("scrape_pricing"),
        {"continue": "save_snapshot", "handle_failure": "handle_failure"},
    )

    # save_snapshot is a soft-failure node (write-back failing shouldn't
    # kill the pipeline) - it always continues forward.
    graph.add_edge("save_snapshot", "fetch_comparison_data")

    graph.add_conditional_edges(
        "fetch_comparison_data", _route_after("fetch_comparison_data"),
        {"continue": "compare", "handle_failure": "handle_failure"},
    )
    graph.add_conditional_edges(
        "compare", _route_after("compare"),
        # On success: enter blog track; on failure: handle_failure
        {"continue": "search_blogs", "handle_failure": "handle_failure"},
    )

    # Blog & Stock tracks: unconditional edges (these nodes never fail the pipeline)
    graph.add_edge("search_blogs", "scrape_blogs")
    graph.add_edge("scrape_blogs", "save_blog_snapshots")
    graph.add_edge("save_blog_snapshots", "stock_analysis")
    graph.add_edge("stock_analysis", "synthesize")

    graph.add_edge("synthesize", END)
    graph.add_edge("handle_failure", END)

    return graph.compile()
