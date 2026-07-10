import requests
import os
import time
import re
from datetime import datetime
from io import BytesIO

try:
    from supabase import create_client, Client
except ImportError:
    raise ImportError("Run: pip install supabase>=2.0.0")

# ── Config ─────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Public URL base for Supabase Storage
STORAGE_BASE = f"{SUPABASE_URL}/storage/v1/object/public/place-images"

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

WIKI_HEADERS = {
    "User-Agent": "PakTourPlanner/1.0 (https://github.com/asifweb005/tour; contact@example.com)",
    "Referer":    "https://en.wikipedia.org/",
    "Accept":     "image/webp,image/jpeg,image/png,*/*",
}

# ── Upload image to Supabase Storage ──────────────────────────────────────

def upload_to_storage(place_id: str, filename: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str | None:
    """Upload image bytes to Supabase Storage, return public URL."""
    storage_path = f"{place_id}/{filename}"
    try:
        # Check if already exists
        try:
            existing = supabase.storage.from_("place-images").list(place_id)
            names = [f["name"] for f in existing] if existing else []
            if filename in names:
                return f"{STORAGE_BASE}/{storage_path}"
        except Exception:
            pass

        supabase.storage.from_("place-images").upload(
            path=storage_path,
            file=image_bytes,
            file_options={"content-type": content_type, "upsert": "true"},
        )
        return f"{STORAGE_BASE}/{storage_path}"
    except Exception as e:
        print(f"      [storage] upload failed {filename}: {e}")
        return None

# ── Wikimedia Commons ──────────────────────────────────────────────────────

def fetch_wikimedia_images(place_id: str, query: str, limit: int = 8) -> list[dict]:
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
        resp = requests.get(url, params=params, headers=WIKI_HEADERS, timeout=20)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {}).values()
        images = []
        for page in pages:
            info = page.get("imageinfo", [{}])[0]
            original_url = info.get("thumburl") or info.get("url", "")
            if not original_url:
                continue
            width  = info.get("thumbwidth", 0)
            height = info.get("thumbheight", 0)
            if width < 400 or height < 300:
                continue
            meta = info.get("extmetadata", {})
            license_name = meta.get("LicenseShortName", {}).get("value", "unknown")
            if not any(x in license_name for x in ["CC", "Public domain", "PD", "cc"]):
                continue

            uploader  = info.get("user", "")
            artist_raw = meta.get("Artist", {}).get("value", "")
            author = re.sub(r'<[^>]+>', '', artist_raw).strip() if artist_raw else uploader
            timestamp  = info.get("timestamp", "")
            upload_date = timestamp[:10] if timestamp else ""

            # Download the image
            try:
                img_resp = requests.get(original_url, headers=WIKI_HEADERS, timeout=30)
                img_resp.raise_for_status()
                image_bytes = img_resp.content
                content_type = img_resp.headers.get("content-type", "image/jpeg").split(";")[0]
            except Exception as e:
                print(f"      [wikimedia] download failed: {e}")
                continue

            # Generate safe filename from URL
            fname = re.sub(r'[^a-zA-Z0-9._-]', '_', original_url.split("/")[-1])[:100]
            if not any(fname.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                fname += '.jpg'

            # Upload to Supabase Storage
            public_url = upload_to_storage(place_id, fname, image_bytes, content_type)
            if not public_url:
                continue

            images.append({
                "url":         public_url,   # ← Supabase URL, not Wikimedia
                "source":      "wikimedia",
                "width":       width,
                "height":      height,
                "license":     license_name,
                "author":      author[:100] if author else "",
                "upload_date": upload_date,
            })
            time.sleep(0.3)  # polite to Wikimedia
        return images
    except Exception as e:
        print(f"    [wikimedia] error: {e}")
        return []

# ── Pixabay ────────────────────────────────────────────────────────────────

def fetch_pixabay_images(place_id: str, query: str, limit: int = 6) -> list[dict]:
    pixabay_key = os.environ.get("PIXABAY_API_KEY", "")
    if not pixabay_key:
        return []
    params = {
        "key":         pixabay_key,
        "q":           query,
        "image_type":  "photo",
        "orientation": "horizontal",
        "category":    "travel",
        "min_width":   800,
        "safesearch":  "true",
        "per_page":    limit,
        "order":       "popular",
    }
    try:
        resp = requests.get("https://pixabay.com/api/", params=params, timeout=20)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        images = []
        for h in hits:
            original_url = h.get("largeImageURL") or h.get("webformatURL", "")
            if not original_url:
                continue

            # Download the image
            try:
                img_resp = requests.get(original_url, timeout=30)
                img_resp.raise_for_status()
                image_bytes = img_resp.content
            except Exception as e:
                print(f"      [pixabay] download failed: {e}")
                continue

            fname = f"pixabay_{h.get('id', '')}.jpg"
            public_url = upload_to_storage(place_id, fname, image_bytes, "image/jpeg")
            if not public_url:
                continue

            images.append({
                "url":         public_url,
                "source":      "pixabay",
                "width":       h.get("imageWidth", 0),
                "height":      h.get("imageHeight", 0),
                "license":     "CC0",
                "author":      h.get("user", ""),
                "upload_date": "",
            })
        return images
    except Exception as e:
        print(f"    [pixabay] error: {e}")
        return []

# ── Supabase DB upsert ─────────────────────────────────────────────────────

def upsert_images(place_id: str, images: list[dict]) -> int:
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
        print(f"    [supabase] upsert error: {e}")
        return 0

# ── Main ───────────────────────────────────────────────────────────────────

def run():
    print(f"\n{'='*60}")
    print(f"PakTour image fetch — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Pixabay: {'enabled' if os.environ.get('PIXABAY_API_KEY') else 'disabled'}")
    print(f"Strategy: download → upload to Supabase Storage → save URL")
    print(f"{'='*60}\n")

    total = 0
    for place in PLACES:
        print(f"→ {place['id']}  ({place['query']})")
        images = []
        images += fetch_wikimedia_images(place["id"], place["query"], limit=8)
        images += fetch_pixabay_images(place["id"], place["query"], limit=6)
        count = upsert_images(place["id"], images)
        print(f"   saved={count}  "
              f"wiki={len([i for i in images if i['source']=='wikimedia'])}  "
              f"pixabay={len([i for i in images if i['source']=='pixabay'])}")
        total += count
        time.sleep(1)

    print(f"\n{'='*60}")
    print(f"Done. Total: {total}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    run()