import os
from dotenv import load_dotenv

load_dotenv()

# --- Groq ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")

# --- Firecrawl ---
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

# --- MongoDB Atlas ---
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "market_intel")

# --- Alpha Vantage ---
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

# --- Misc ---
COMPETITOR_REGISTRY_PATH = os.getenv("COMPETITOR_REGISTRY_PATH", "competitor_registry.json")

# Pricing URL path hints used as a first-pass filter before falling back to LLM selection
PRICING_PATH_KEYWORDS = [
    "pricing", "price", "prices",
    "plans", "plan", "tiers", "tier",
    "cost", "costs", "rates", "rate", "fees", "fee",
    "packages", "package", "bundles", "bundle",
    "subscribe", "subscription", "subscriptions", "billing", "checkout",
    "buy", "purchase", "order", "quote", "get-started", "get-quote",
    "editions", "edition", "license", "licensing", "licenses",
    "upgrade", "compare-plans", "compare",
    "tarif", "tarifs", "preise", "precio", "precios",
]

# Blog URL path hints used to identify blog/news post URLs
BLOG_PATH_KEYWORDS = [
    "blog", "news", "updates", "update", "changelog", "releases", "release",
    "announcement", "announcements", "insights", "press", "media", "article",
    "post", "stories", "story", "journal", "engineering",
]

# Maximum number of blog posts to scrape per pipeline run
MAX_BLOG_POSTS = 5


def validate_env():
    """
    Raises EnvironmentError listing any missing required variables.
    Call this at startup so failures happen immediately and clearly,
    instead of failing deep inside a graph node later.
    """
    required = {
        "GROQ_API_KEY": GROQ_API_KEY,
        "FIRECRAWL_API_KEY": FIRECRAWL_API_KEY,
        "MONGODB_URI": MONGODB_URI,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill these in."
        )
