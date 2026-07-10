import requests
import os
import time
from datetime import datetime

try:
    from supabase import create_client, Client
except ImportError:
    raise ImportError("Run: pip install supabase>=2.0.0")

# ── Config ─────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise EnvironmentError(
        "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.\n"
        "GitHub: Settings → Secrets and variables → Actions"
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

PLACES = [
    {"id": "islamabad",    "query": "Islamabad Pakistan city"},
    {"id": "murree",       "query": "Murree hill station Pakistan"},
    {"id": "nathiagali",   "query": "Nathia Gali Galiyat Pakistan"},
    {"id": "kaghan",       "query": "Kaghan Valley Naran Pakistan"},
    {"id": "swat",         "query": "Swat Valley Pakistan"},
    {"id": "chitral",      "query": "Chitral Kalash Valley Pakistan"},
    {"id": "fairymeadows", "query": "Fairy Meadows Nanga Parbat Pakistan"},
    {"id": "gilgit",       "query": "Gilgit city Pakistan"},
    {"id": "hunza",        "query": "Hunza Valley Karimabad Pakistan"},
    {"id": "skardu",       "query": "Skardu Baltistan Pakistan"},
]

HEADERS = {
    "User-Agent": "PakTourPlanner/1.0 (https://github.com/asifweb005/tour)"
}

# ── Wikimedia Commons ──────────────────────────────────────────────────────

def fetch_wikimedia_images(query: str, limit: int = 8) -> list[dict]:
    """Real visitor photos from Wikimedia Commons — no API key needed."""
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action":       "query",
        "generator":    "search",
        "gsrnamespace": 6,
        "gsrsearch":    f"{query} filetype:bitmap",
        "gsrlimit":     limit,
        "prop":         "imageinfo",
        "iiprop":       "url|size|extmetadata|user|timestamp",
        "iiurlwidth":   1200,
        "format":       "json",
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {}).values()
        images = []
        for page in pages:
            info = page.get("imageinfo", [{}])[0]
            thumb_url = info.get("thumburl") or info.get("url", "")
            if not thumb_url:
                continue
            width  = info.get("thumbwidth", 0)
            height = info.get("thumbheight", 0)
            if width < 400 or height < 300:
                continue
            meta = info.get("extmetadata", {})
            license_name = meta.get("LicenseShortName", {}).get("value", "unknown")
            if not any(x in license_name for x in ["CC", "Public domain", "PD", "cc"]):
                continue

            # Uploader info
            uploader = info.get("user", "")
            # Try to get real author from metadata (sometimes different from uploader)
            artist_raw = meta.get("Artist", {}).get("value", "")
            # Strip HTML tags from artist field
            import re
            author = re.sub(r'<[^>]+>', '', artist_raw).strip() if artist_raw else uploader

            # Upload date
            timestamp = info.get("timestamp", "")  # e.g. "2021-06-15T10:30:00Z"
            upload_date = timestamp[:10] if timestamp else ""  # keep YYYY-MM-DD only

            images.append({
                "url":         thumb_url,
                "source":      "wikimedia",
                "width":       width,
                "height":      height,
                "license":     license_name,
                "author":      author[:100] if author else "",
                "upload_date": upload_date,
            })
        return images
    except Exception as e:
        print(f"    [wikimedia] error: {e}")
        return []

# ── Pixabay ────────────────────────────────────────────────────────────────

def fetch_pixabay_images(query: str, limit: int = 6) -> list[dict]:
    """High-quality CC0 photos from Pixabay — free API key required."""
    pixabay_key = os.environ.get("PIXABAY_API_KEY", "")
    if not pixabay_key:
        print("    [pixabay] PIXABAY_API_KEY not set, skipping")
        return []
    params = {
        "key":          pixabay_key,
        "q":            query,
        "image_type":   "photo",
        "orientation":  "horizontal",
        "category":     "travel",
        "min_width":    800,
        "safesearch":   "true",
        "per_page":     limit,
        "order":        "popular",
    }
    try:
        resp = requests.get(
            "https://pixabay.com/api/",
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        images = []
        for h in hits:
            img_url = h.get("largeImageURL") or h.get("webformatURL", "")
            if not img_url:
                continue
            images.append({
                "url":         img_url,
                "source":      "pixabay",
                "width":       h.get("imageWidth", 0),
                "height":      h.get("imageHeight", 0),
                "license":     "CC0",
                "author":      h.get("user", ""),
                "upload_date": "",   # Pixabay doesn't return upload date in free API
            })
        return images
    except Exception as e:
        print(f"    [pixabay] error: {e}")
        return []

# ── Supabase upsert ────────────────────────────────────────────────────────

def upsert_images(place_id: str, images: list[dict]) -> int:
    """Save images to Supabase. Skips duplicates via on_conflict='url'."""
    if not images:
        return 0
    rows = [
        {
            "place_id":    place_id,
            "url":         img["url"],
            "source":      img["source"],
            "width":       img.get("width"),
            "height":      img.get("height"),
            "license":     img.get("license"),
            "author":      img.get("author", ""),
            "upload_date": img.get("upload_date", ""),
            "fetched_at":  datetime.utcnow().isoformat(),
        }
        for img in images
    ]
    try:
        supabase.table("place_images").upsert(rows, on_conflict="url").execute()
        return len(rows)
    except Exception as e:
        print(f"    [supabase] upsert error for {place_id}: {e}")
        return 0

# ── Main ───────────────────────────────────────────────────────────────────

def run():
    print(f"\n{'='*60}")
    print(f"PakTour image fetch — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Supabase: {SUPABASE_URL}")
    print(f"Pixabay: {'enabled' if os.environ.get('PIXABAY_API_KEY') else 'disabled (key not set)'}")
    print(f"{'='*60}\n")

    total = 0
    for place in PLACES:
        print(f"→ {place['id']}  ({place['query']})")
        images = []
        images += fetch_wikimedia_images(place["query"], limit=8)
        images += fetch_pixabay_images(place["query"], limit=6)
        count = upsert_images(place["id"], images)
        print(f"   wikimedia={len([i for i in images if i['source']=='wikimedia'])}  "
              f"pixabay={len([i for i in images if i['source']=='pixabay'])}  "
              f"saved={count}")
        total += count
        time.sleep(1)

    print(f"\n{'='*60}")
    print(f"Done. Total rows upserted: {total}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run()
