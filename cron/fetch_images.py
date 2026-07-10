import requests
import os
import time
from supabase import create_client
from datetime import datetime

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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
    "User-Agent": "PakTourPlanner/1.0 (https://github.com/YOUR_USERNAME/paktour; contact@example.com)"
}


def fetch_wikimedia_images(query: str, limit: int = 8) -> list[dict]:
    """Fetch real visitor photos from Wikimedia Commons — no API key needed."""
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": 1200,
        "format": "json",
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
            # Skip tiny images (icons, logos)
            if width < 400 or height < 300:
                continue
            meta = info.get("extmetadata", {})
            license_name = meta.get("LicenseShortName", {}).get("value", "unknown")
            # Only use open licenses
            if not any(x in license_name for x in ["CC", "Public domain", "PD", "cc"]):
                continue
            images.append({
                "url": thumb_url,
                "source": "wikimedia",
                "width": width,
                "height": height,
                "license": license_name,
            })
        return images
    except Exception as e:
        print(f"    [wikimedia] error: {e}")
        return []


def fetch_flickr_images(query: str, limit: int = 5) -> list[dict]:
    """Fetch CC-licensed photos from Flickr free API."""
    flickr_key = os.environ.get("FLICKR_API_KEY", "")
    if not flickr_key:
        print("    [flickr] FLICKR_API_KEY not set, skipping")
        return []

    params = {
        "method":        "flickr.photos.search",
        "api_key":       flickr_key,
        "text":          query,
        "license":       "1,2,4,5,6,9,10",   # all CC licenses
        "sort":          "relevance",
        "content_type":  1,
        "media":         "photos",
        "extras":        "url_l,url_c,license",
        "per_page":      limit,
        "format":        "json",
        "nojsoncallback": 1,
    }
    try:
        resp = requests.get(
            "https://api.flickr.com/services/rest/",
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", {}).get("photo", [])
        images = []
        for p in photos:
            img_url = p.get("url_l") or p.get("url_c", "")
            if not img_url:
                continue
            images.append({
                "url":     img_url,
                "source":  "flickr",
                "width":   int(p.get("width_l", 0)),
                "height":  int(p.get("height_l", 0)),
                "license": f"CC-{p.get('license', '')}",
            })
        return images
    except Exception as e:
        print(f"    [flickr] error: {e}")
        return []


def upsert_images(place_id: str, images: list[dict]) -> int:
    """Insert images into Supabase. Skip if URL already exists (on_conflict)."""
    if not images:
        return 0
    rows = [
        {
            "place_id":   place_id,
            "url":        img["url"],
            "source":     img["source"],
            "width":      img.get("width"),
            "height":     img.get("height"),
            "license":    img.get("license"),
            "fetched_at": datetime.utcnow().isoformat(),
        }
        for img in images
    ]
    supabase.table("place_images").upsert(rows, on_conflict="url").execute()
    return len(rows)


def run():
    print(f"\n=== PakTour image fetch — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} ===\n")
    total = 0
    for place in PLACES:
        print(f"→ {place['id']}  (query: {place['query']})")
        images = []
        images += fetch_wikimedia_images(place["query"], limit=8)
        images += fetch_flickr_images(place["query"], limit=5)
        count = upsert_images(place["id"], images)
        print(f"   saved {count} rows  ({len(images)} fetched)")
        total += count
        time.sleep(1)   # be polite to APIs

    print(f"\n=== Done. Total upserted: {total} ===\n")


if __name__ == "__main__":
    run()
