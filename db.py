"""
MongoDB Atlas access layer.

Collections used:
  - pricing_snapshots : every scrape we've ever taken, per competitor, timestamped
  - our_pricing        : our own current pricing (you populate this manually or via
                          your own internal system - not scraped)
  - churn_data         : internal telemetry, keyed by pricing tier
  - blog_snapshots     : competitor blog/news articles, deduplicated by URL

Setup (MongoDB Atlas):
  1. Create a free cluster at https://www.mongodb.com/cloud/atlas
  2. Create a database user (Database Access) and note username/password
  3. Add your IP to Network Access (or 0.0.0.0/0 for local dev/testing only)
  4. Get the connection string (Connect > Drivers) and put it in .env as MONGODB_URI
  5. Run `python db.py` once to test the connection and create indexes
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError, ConnectionFailure, ServerSelectionTimeoutError

import config
from logger_config import get_logger

logger = get_logger(__name__)

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    """Lazily creates and reuses a single MongoClient instance."""
    global _client
    if _client is None:
        try:
            _client = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=8000)
            # Force connection check now, rather than on first real query
            _client.admin.command("ping")
            logger.info("Connected to MongoDB Atlas successfully.")
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB Atlas: {e}", exc_info=True)
            raise
    return _client


def get_db():
    return get_client()[config.MONGODB_DB_NAME]


def ensure_indexes():
    """Create indexes needed for efficient lookups. Safe to call repeatedly."""
    try:
        db = get_db()
        db.pricing_snapshots.create_index([("competitor_name", 1), ("scraped_at", DESCENDING)])
        db.our_pricing.create_index([("updated_at", DESCENDING)])
        db.churn_data.create_index([("tier", 1)])
        # Blog snapshots: fast lookup by competitor + time, and unique URL to prevent duplicates
        db.blog_snapshots.create_index([("competitor_name", 1), ("scraped_at", DESCENDING)])
        db.blog_snapshots.create_index([("url", 1)], unique=True)
        logger.info("MongoDB indexes ensured.")
    except PyMongoError as e:
        logger.error(f"Failed to create indexes: {e}", exc_info=True)
        raise


# ---------- Pricing snapshots (write-back step) ----------

def save_pricing_snapshot(competitor_name: str, url: str, raw_content: str, status: str) -> bool:
    """
    Saves a scraped pricing snapshot. This is the write-back step that makes
    historical comparison possible on future runs.

    Returns True on success, False on failure (does not raise - callers should
    log this as a soft failure and continue the pipeline, since a failed
    write-back shouldn't crash a comparison that only needs today's in-memory data).
    """
    try:
        db = get_db()
        doc = {
            "competitor_name": competitor_name,
            "url": url,
            "raw_content": raw_content,
            "status": status,  # "success" | "empty" | "error"
            "scraped_at": datetime.now(timezone.utc),
        }
        db.pricing_snapshots.insert_one(doc)
        logger.info(f"Saved pricing snapshot for '{competitor_name}' (status={status}).")
        return True
    except PyMongoError as e:
        logger.error(f"Failed to save pricing snapshot for '{competitor_name}': {e}", exc_info=True)
        return False


def get_previous_pricing_snapshot(competitor_name: str, exclude_latest: bool = True) -> Optional[dict]:
    """
    Returns the most recent PREVIOUS successful snapshot for a competitor
    (i.e. not counting the one just saved in this same run), or None if
    no historical data exists yet. This is the "first run" edge case.
    """
    try:
        db = get_db()
        cursor = (
            db.pricing_snapshots.find({"competitor_name": competitor_name, "status": "success"})
            .sort("scraped_at", DESCENDING)
            .limit(2 if exclude_latest else 1)
        )
        docs = list(cursor)
        if not docs:
            logger.info(f"No previous pricing data found for '{competitor_name}' (first run).")
            return None
        if exclude_latest and len(docs) > 1:
            return docs[1]
        if exclude_latest and len(docs) <= 1:
            # Only the just-saved snapshot exists, nothing older
            logger.info(f"No previous pricing data found for '{competitor_name}' (first run).")
            return None
        return docs[0]
    except PyMongoError as e:
        logger.error(f"Failed to fetch previous snapshot for '{competitor_name}': {e}", exc_info=True)
        return None



# ---------- Blog snapshots ----------

def save_blog_snapshots(competitor_name: str, articles: list) -> bool:
    """
    Bulk-saves blog article snapshots. Deduplicates by URL — only inserts
    articles not already in the collection (the unique index on 'url' also
    protects against duplicates at the DB level as a safety net).

    Returns True on success, False on failure (soft failure — callers log
    and continue rather than crashing the pipeline).
    """
    try:
        db = get_db()
        scraped_at = datetime.now(timezone.utc)

        # Collect URLs already stored for this competitor to avoid re-inserting
        existing_urls = {
            doc["url"]
            for doc in db.blog_snapshots.find(
                {"competitor_name": competitor_name},
                {"url": 1, "_id": 0},
            )
        }

        new_docs = []
        for article in articles:
            url = article.get("url", "").strip()
            if not url or url in existing_urls:
                logger.info(f"Skipping already-stored blog article: {url}")
                continue
            new_docs.append(
                {
                    "competitor_name": competitor_name,
                    "url": url,
                    "title": article.get("title", ""),
                    "published_at": article.get("published_at"),   # ISO string or None
                    "summary": article.get("summary", ""),
                    "raw_content": article.get("raw_content", ""),
                    "is_new": True,
                    "scraped_at": scraped_at,
                }
            )

        if not new_docs:
            logger.info(f"No new blog articles to save for '{competitor_name}' (all already in DB).")
            return True

        db.blog_snapshots.insert_many(new_docs, ordered=False)
        logger.info(f"Saved {len(new_docs)} new blog article(s) for '{competitor_name}'.")
        return True

    except PyMongoError as e:
        logger.error(f"Failed to save blog snapshots for '{competitor_name}': {e}", exc_info=True)
        return False


def get_recent_blog_snapshots(competitor_name: str, days: int = 30) -> list:
    """
    Returns blog articles for a competitor scraped within the last `days` days,
    sorted most-recent first. Raw content is excluded to keep response size small.
    """
    try:
        db = get_db()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return list(
            db.blog_snapshots.find(
                {"competitor_name": competitor_name, "scraped_at": {"$gte": cutoff}},
                {"_id": 0, "raw_content": 0},
            )
            .sort("scraped_at", DESCENDING)
            .limit(10)
        )
    except PyMongoError as e:
        logger.error(f"Failed to fetch recent blog snapshots for '{competitor_name}': {e}", exc_info=True)
        return []


# ---------- Our own pricing ----------

def get_our_pricing() -> Optional[dict]:
    """Returns our latest internal pricing doc, or None if not populated yet."""
    try:
        db = get_db()
        doc = db.our_pricing.find_one(sort=[("updated_at", DESCENDING)])
        if doc is None:
            logger.error("No internal pricing data found in 'our_pricing' collection.")
        return doc
    except PyMongoError as e:
        logger.error(f"Failed to fetch our pricing data: {e}", exc_info=True)
        return None


# ---------- Churn / telemetry ----------

def get_churn_data() -> list:
    """Returns churn telemetry docs. Empty list (not an exception) if none exist."""
    try:
        db = get_db()
        return list(db.churn_data.find({}))
    except PyMongoError as e:
        logger.error(f"Failed to fetch churn data: {e}", exc_info=True)
        return []


if __name__ == "__main__":
    # Quick connectivity + setup check: `python db.py`
    config.validate_env()
    get_client()
    ensure_indexes()
    print("MongoDB Atlas connection OK, indexes ensured.")
