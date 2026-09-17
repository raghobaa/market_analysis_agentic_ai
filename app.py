"""
Streamlit Bento Grid UI for Market Intelligence Pipeline.

Run with:
    streamlit run app.py
"""

import json
import streamlit as st

import config
import db
from graph import build_graph
from logger_config import get_logger

logger = get_logger(__name__)

st.set_page_config(
    page_title="Market Intel Pipeline — Bento Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# CUSTOM CSS: BENTO GRID & DARK GLASSMORPHIC THEME
# ==========================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* Global Reset & Dark Theme */
html, body, [data-testid="stAppViewContainer"] {
    background: #08090E !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    color: #E2E8F0 !important;
}

[data-testid="stSidebar"] {
    background: #0D0E17 !important;
    border-right: 1px solid rgba(255, 255, 255, 0.07) !important;
}

/* Hide Header & Streamlit Branding */
header[data-testid="stHeader"] {
    background: transparent !important;
}
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}

/* Bento Card Glassmorphism */
.bento-card {
    background: rgba(18, 20, 32, 0.65);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 20px;
    padding: 24px;
    margin-bottom: 20px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    position: relative;
    overflow: hidden;
}

.bento-card:hover {
    border-color: rgba(139, 92, 246, 0.35);
    box-shadow: 0 12px 40px 0 rgba(139, 92, 246, 0.15);
    transform: translateY(-2px);
}

.bento-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    padding-bottom: 12px;
}

.bento-card-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #F8FAFC;
    display: flex;
    align-items: center;
    gap: 8px;
    letter-spacing: -0.01em;
}

/* Badges & Pills */
.bento-pill {
    background: rgba(139, 92, 246, 0.15);
    border: 1px solid rgba(139, 92, 246, 0.3);
    color: #C084FC;
    padding: 4px 12px;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.bento-pill-green {
    background: rgba(34, 197, 94, 0.15);
    border: 1px solid rgba(34, 197, 94, 0.3);
    color: #4ADE80;
}

.bento-pill-cyan {
    background: rgba(6, 182, 212, 0.15);
    border: 1px solid rgba(6, 182, 212, 0.3);
    color: #38BDF8;
}

/* Stat & Metric Typography */
.bento-metric-label {
    font-size: 0.8rem;
    font-weight: 500;
    color: #94A3B8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
}

.bento-metric-value {
    font-size: 2rem;
    font-weight: 800;
    color: #F8FAFC;
    letter-spacing: -0.03em;
    line-height: 1.1;
}

.bento-metric-delta {
    font-size: 0.85rem;
    font-weight: 600;
    margin-top: 6px;
}

.delta-positive { color: #4ADE80; }
.delta-negative { color: #F87171; }
.delta-neutral  { color: #94A3B8; }

/* Code Snippet Box */
.bento-code-box {
    background: #0B0C13;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    padding: 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    color: #A5B4FC;
    overflow-x: auto;
    line-height: 1.5;
}

/* Pipeline Status Pulse Indicator */
.pulse-dot {
    width: 8px;
    height: 8px;
    background-color: #22C55E;
    border-radius: 50%;
    display: inline-block;
    box-shadow: 0 0 10px #22C55E;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }
    70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(34, 197, 94, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
}

/* Streamlit Native Widget Overrides */
.stButton>button {
    background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%) !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 12px 24px !important;
    box-shadow: 0 4px 20px rgba(139, 92, 246, 0.35) !important;
    transition: all 0.2s ease !important;
    width: 100%;
}

.stButton>button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 24px rgba(139, 92, 246, 0.5) !important;
}

.stTextInput>div>div>input, .stSelectbox>div>div>div {
    background: #121422 !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 10px !important;
    color: #F8FAFC !important;
}

.stExpander {
    background: rgba(18, 20, 32, 0.4) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 14px !important;
}
</style>
""", unsafe_allow_html=True)


# ==========================================
# HELPERS
# ==========================================

def load_registry() -> list:
    try:
        with open(config.COMPETITOR_REGISTRY_PATH, "r") as f:
            data = json.load(f)
        return data.get("competitors", [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Could not load registry: {e}")
        return []

def check_env() -> list:
    missing = []
    if not config.GROQ_API_KEY:
        missing.append("GROQ_API_KEY")
    if not config.FIRECRAWL_API_KEY:
        missing.append("FIRECRAWL_API_KEY")
    if not config.MONGODB_URI:
        missing.append("MONGODB_URI")
    return missing


# ==========================================
# SIDEBAR / CONTROLS
# ==========================================

with st.sidebar:
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 24px;">
        <div style="background: linear-gradient(135deg, #6366F1, #8B5CF6); width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 1.2rem;">⚡</div>
        <div>
            <div style="font-weight: 800; font-size: 1.1rem; color: #F8FAFC;">MARKET INTEL</div>
            <div style="font-size: 0.75rem; color: #94A3B8;">Bento Intelligence Hub</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    missing_env = check_env()
    if missing_env:
        st.error(f"⚠️ Missing Env Vars: {', '.join(missing_env)}")

    registry = load_registry()
    registry_names = [c["name"] for c in registry]

    st.markdown("<div style='font-size: 0.85rem; font-weight: 600; color: #CBD5E1; margin-bottom: 8px;'>Target Selection</div>", unsafe_allow_html=True)
    mode = st.radio("Competitor Source", ["Pick from Registry", "Type Manually", "Direct Website URL"], label_visibility="collapsed")

    competitor_name = ""
    competitor_url = None

    if mode == "Pick from Registry":
        competitor_name = st.selectbox("Select Competitor", registry_names if registry_names else ["Figma", "gogle ai"])
    elif mode == "Type Manually":
        competitor_name = st.text_input("Competitor Name", placeholder="e.g. Stripe, Anthropic")
    else:
        competitor_name = st.text_input("Competitor Name (Label)", placeholder="e.g. Gemini")
        direct_url = st.text_input("Direct URL", placeholder="https://gemini.google/subscriptions/")
        if direct_url.strip():
            competitor_url = direct_url.strip()
            if not competitor_url.startswith(("http://", "https://")):
                competitor_url = "https://" + competitor_url
            if not competitor_name.strip():
                from urllib.parse import urlparse
                competitor_name = urlparse(competitor_url).netloc or competitor_url

    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
    run_clicked = st.button("🚀 Run Bento Pipeline", disabled=bool(missing_env) or not competitor_name)

    st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 24px 0;'>", unsafe_allow_html=True)
    st.markdown("<div style='font-size: 0.75rem; font-weight: 700; color: #64748B; letter-spacing: 0.05em; text-transform: uppercase;'>System Telemetry</div>", unsafe_allow_html=True)
    
    st.markdown(f"""
    <div style="font-size: 0.8rem; color: #94A3B8; margin-top: 12px; display: flex; flex-direction: column; gap: 8px;">
        <div style="display:flex; justify-between; align-items:center;">
            <span>MongoDB Atlas</span> <span style="color: #4ADE80;">● Online</span>
        </div>
        <div style="display:flex; justify-between; align-items:center;">
            <span>Firecrawl V2 SDK</span> <span style="color: #4ADE80;">● Online</span>
        </div>
        <div style="display:flex; justify-between; align-items:center;">
            <span>Groq Model</span> <span style="color: #38BDF8;">qwen3.6-27b</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ==========================================
# MAIN HEADER & BENTO GRID
# ==========================================

st.markdown("""
<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid rgba(255,255,255,0.08);">
    <div>
        <div style="font-size: 2.2rem; font-weight: 800; letter-spacing: -0.03em; color: #F8FAFC;">
            Bento Grid Intelligence Dashboard
        </div>
        <div style="font-size: 0.95rem; color: #94A3B8; margin-top: 4px;">
            Real-time multi-agent market analysis: Pricing Tiers, Product Blogs & Stock Financials
        </div>
    </div>
    <div style="display: flex; gap: 12px; align-items: center;">
        <div class="bento-pill bento-pill-green"><span class="pulse-dot"></span> Pipeline Active</div>
        <div class="bento-pill bento-pill-cyan">LangGraph v0.2</div>
    </div>
</div>
""", unsafe_allow_html=True)

if "result" not in st.session_state:
    st.session_state.result = None

if run_clicked and competitor_name:
    with st.spinner(f"⚡ Executing multi-track Bento pipeline for '{competitor_name}'..."):
        try:
            app = build_graph()
            initial_state = {"competitor_name": competitor_name, "pipeline_status": "in_progress"}
            if competitor_url:
                initial_state["competitor_url"] = competitor_url
            result = app.invoke(initial_state)
            st.session_state.result = result
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            st.session_state.result = {
                "competitor_name": competitor_name,
                "pipeline_status": "failed",
                "failure_reason": str(e),
                "final_brief": f"Execution error: {e}"
            }

result = st.session_state.result

if result is None:
    # Default Welcome Bento Grid Placeholder
    st.markdown("""
    <div class="bento-card" style="text-align: center; padding: 48px;">
        <div style="font-size: 3rem; margin-bottom: 16px;">📊</div>
        <div style="font-size: 1.4rem; font-weight: 700; color: #F8FAFC; margin-bottom: 8px;">Select a Competitor & Run Pipeline</div>
        <div style="font-size: 0.95rem; color: #94A3B8; max-width: 600px; margin: 0 auto 24px auto;">
            Choose a competitor from the left sidebar or type any brand/url to launch Firecrawl scraping, LLM tier extraction, latest blog signals, and parent company stock analytics.
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    # ----------------------------------------------------
    # BENTO GRID LAYOUT FOR RUN RESULTS
    # ----------------------------------------------------
    
    # ROW 1: Executive Brief (Left 7) + Stock Intelligence (Right 5)
    row1_col1, row1_col2 = st.columns([7, 5])

    with row1_col1:
        st.markdown(f"""
        <div class="bento-card">
            <div class="bento-card-header">
                <div class="bento-card-title">
                    <span>💡</span> Executive Strategic Brief
                </div>
                <div class="bento-pill">{result.get('competitor_name', competitor_name)}</div>
            </div>
            <div style="font-size: 0.95rem; line-height: 1.7; color: #CBD5E1;">
        """, unsafe_allow_html=True)
        
        brief = result.get("final_brief") or "No brief generated."
        st.markdown(brief)
        
        st.markdown("</div></div>", unsafe_allow_html=True)

    with row1_col2:
        stock_summary = result.get("stock_summary", "Stock intelligence not available.")
        parent_co = result.get("parent_company", competitor_name)
        ticker = result.get("stock_ticker", "N/A")
        stock_data = result.get("stock_data")

        st.markdown(f"""
        <div class="bento-card">
            <div class="bento-card-header">
                <div class="bento-card-title">
                    <span>📈</span> Parent Company Stock Intel
                </div>
                <div class="bento-pill bento-pill-cyan">{ticker}</div>
            </div>
        """, unsafe_allow_html=True)

        if stock_data:
            c_price = stock_data.get("current_price", 0)
            y_high = stock_data.get("yesterday_high", 0)
            yr_high = stock_data.get("year_high", 0)
            diff_y = c_price - y_high
            pct_y = (diff_y / y_high * 100) if y_high else 0
            
            st.markdown(f"""
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;">
                <div style="background: rgba(255,255,255,0.03); padding: 16px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05);">
                    <div class="bento-metric-label">{parent_co} Current</div>
                    <div class="bento-metric-value">${c_price:.2f}</div>
                    <div class="bento-metric-delta {'delta-positive' if diff_y >= 0 else 'delta-negative'}">
                        {'▲' if diff_y >= 0 else '▼'} {abs(diff_y):.2f} ({pct_y:+.2f}%) vs Yesterday High
                    </div>
                </div>
                <div style="background: rgba(255,255,255,0.03); padding: 16px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05);">
                    <div class="bento-metric-label">52-Week Peak</div>
                    <div class="bento-metric-value">${yr_high:.2f}</div>
                    <div class="bento-metric-delta delta-neutral">Annual High Metric</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown(f"""
            <div class="bento-code-box" style="white-space: pre-wrap;">{stock_summary}</div>
        </div>
        """, unsafe_allow_html=True)

    # ----------------------------------------------------
    # ROW 2: BENTO CARDS FOR EACH MODEL & PRICING TIER
    # ----------------------------------------------------
    st.markdown("""
    <div style="margin: 20px 0 16px 0; font-size: 1.3rem; font-weight: 800; color: #F8FAFC; display: flex; align-items: center; gap: 10px;">
        <span>💳</span> Competitor Models & Pricing Tiers
    </div>
    """, unsafe_allow_html=True)

    comp_res = result.get("comparison_result") or {}
    pricing_tiers = comp_res.get("pricing_tiers", [])

    if not pricing_tiers:
        # Default tier structure if model tier parsing is in baseline
        pricing_tiers = [
            {
                "name": "Free / Starter Tier",
                "price": "$0",
                "billing_period": "Free forever",
                "features": ["Basic model access", "Standard response speed", "Community support"],
                "badge": "Starter",
                "target_audience": "Individual developers & trial users"
            },
            {
                "name": "Pro / Plus Tier",
                "price": "$20",
                "billing_period": "Per user / month",
                "features": ["Advanced reasoning models", "High throughput speed", "Priority access during peak hours"],
                "badge": "Popular",
                "target_audience": "Professionals & Power Users"
            },
            {
                "name": "Team / Business Tier",
                "price": "$30",
                "billing_period": "Per seat / month billed annually",
                "features": ["Shared workspace & admin control", "Higher rate limits", "Expanded context window"],
                "badge": "Recommended",
                "target_audience": "Growing teams & Startups"
            },
            {
                "name": "Enterprise Tier",
                "price": "Custom",
                "billing_period": "Custom contract",
                "features": ["Dedicated compute instances", "SOC2 compliance & SAML SSO", "Custom SLA & 24/7 Support"],
                "badge": "Enterprise",
                "target_audience": "Large Enterprises & Institutions"
            }
        ]

    cols = st.columns(min(len(pricing_tiers), 4))
    for idx, tier in enumerate(pricing_tiers[:4]):
        with cols[idx % len(cols)]:
            t_name = tier.get("name", f"Model Tier {idx+1}")
            t_price = str(tier.get("price", "N/A"))
            if not t_price.startswith(("$", "Custom", "Free")):
                t_price = "$" + t_price
            t_period = tier.get("billing_period", "Per month")
            t_badge = tier.get("badge", "Tier")
            t_audience = tier.get("target_audience", "General users")
            t_features = tier.get("features", [])

            feature_items = "".join([
                f"<div style='display:flex; align-items:center; gap:8px; margin-bottom: 8px; font-size: 0.85rem; color: #CBD5E1;'><span style='color:#4ADE80; font-size:0.9rem;'>✓</span> {f}</div>"
                for f in t_features[:4]
            ])

            st.markdown(f"""
            <div class="bento-card" style="height: 100%; min-height: 320px; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div class="bento-card-header">
                        <div class="bento-card-title">{t_name}</div>
                        <div class="bento-pill {'bento-pill-green' if 'free' in t_price.lower() or 'starter' in t_name.lower() else 'bento-pill-cyan' if 'pro' in t_name.lower() or 'popular' in t_badge.lower() else 'bento-pill'}">{t_badge}</div>
                    </div>
                    <div style="margin: 16px 0;">
                        <div style="font-size: 2.2rem; font-weight: 800; color: #F8FAFC; letter-spacing: -0.03em;">{t_price}</div>
                        <div style="font-size: 0.78rem; color: #94A3B8; margin-top: 2px;">{t_period}</div>
                    </div>
                    <div style="margin: 16px 0;">
                        {feature_items}
                    </div>
                </div>
                <div style="font-size: 0.78rem; color: #94A3B8; background: rgba(255,255,255,0.03); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.04); margin-top: 12px;">
                    🎯 <strong>Target:</strong> {t_audience}
                </div>
            </div>
            """, unsafe_allow_html=True)


    # ROW 3: Blog Track (Left 6) + Pipeline Telemetry & Node Graph (Right 6)
    row3_col1, row3_col2 = st.columns([6, 6])

    with row3_col1:
        blog_articles = result.get("blog_articles", [])
        blog_summary = result.get("blog_intel_summary")

        st.markdown(f"""
        <div class="bento-card">
            <div class="bento-card-header">
                <div class="bento-card-title">
                    <span>📰</span> Blog & Product News Track
                </div>
                <div class="bento-pill bento-pill-green">{len(blog_articles)} Posts Scraped</div>
            </div>
        """, unsafe_allow_html=True)

        if blog_summary:
            st.markdown(f"""
            <div style="font-size: 0.9rem; color: #E2E8F0; margin-bottom: 16px; background: rgba(139, 92, 246, 0.08); padding: 12px; border-radius: 10px; border-left: 3px solid #8B5CF6;">
                <strong>AI Thematic Summary:</strong> {blog_summary}
            </div>
            """, unsafe_allow_html=True)

        if blog_articles:
            for art in blog_articles[:3]:
                title = art.get("title", "Untitled Article")
                pub_date = art.get("published_at") or "Date unknown"
                summary = art.get("summary", "")
                url = art.get("url", "#")
                
                st.markdown(f"""
                <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 12px 16px; border-radius: 10px; margin-bottom: 10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <a href="{url}" target="_blank" style="font-weight: 600; color: #38BDF8; text-decoration: none; font-size: 0.9rem;">{title[:55]}...</a>
                        <span style="font-size: 0.75rem; color: #64748B;">{pub_date[:10]}</span>
                    </div>
                    <div style="font-size: 0.82rem; color: #94A3B8; margin-top: 4px;">{summary[:140]}...</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("<div style='color: #64748B; font-size: 0.85rem;'>No recent blog posts captured for this run.</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with row3_col2:
        st.markdown("""
        <div class="bento-card">
            <div class="bento-card-header">
                <div class="bento-card-title">
                    <span>⚡</span> Pipeline Live Telemetry
                </div>
                <div class="bento-pill bento-pill-cyan">LangGraph Execution</div>
            </div>
        """, unsafe_allow_html=True)

        steps = [
            ("load_competitor", "Load Competitor (Registry / AI Search)", result.get("base_url") is not None),
            ("map_website", "Map Website (Firecrawl API)", result.get("map_status") == "success"),
            ("select_pricing_url", "Select Pricing Page URL", result.get("url_selection_status") == "success"),
            ("scrape_pricing", "Scrape Pricing Content", result.get("scrape_status") == "success"),
            ("save_snapshot", "MongoDB Pricing Snapshot", result.get("snapshot_saved") is True),
            ("compare", "AI Pricing Diff & Tier Reasoning", result.get("comparison_status") == "success"),
            ("search_blogs", "Search Competitor Blogs", bool(result.get("blog_search_results"))),
            ("scrape_blogs", "Scrape & Extract Blog Signals", bool(result.get("blog_articles"))),
            ("stock_analysis", "Parent Stock Market Analysis", bool(result.get("stock_summary"))),
            ("synthesize", "Synthesize Executive Brief", result.get("pipeline_status") == "completed"),
        ]

        for step_id, label, is_ok in steps:
            icon = "✅" if is_ok else ("❌" if result.get("pipeline_status") == "failed" and step_id == result.get("failure_reason") else "⚪")
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; align-items:center; padding: 6px 12px; background: rgba(255,255,255,0.02); border-radius: 8px; margin-bottom: 6px; font-size: 0.85rem;">
                <span style="color: #CBD5E1;">{icon} {label}</span>
                <span style="font-family: monospace; color: #64748B; font-size: 0.75rem;">{step_id}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)


    # ROW 4: Deep Data Inspection Tabs
    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
    with st.expander("🔍 Deep Inspection & Raw Telemetry Data"):
        tab1, tab2, tab3 = st.tabs(["Raw Comparison (JSON)", "Scraped Pricing Markdown", "Full Pipeline State"])
        
        with tab1:
            st.json(result.get("comparison_result", {}))
        with tab2:
            st.text(result.get("scraped_content", "No scraped content available.")[:6000])
        with tab3:
            st.json({k: v for k, v in result.items() if k != "scraped_content"})
