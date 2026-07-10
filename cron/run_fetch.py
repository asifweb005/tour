import requests, os, time, re
from datetime import datetime
from supabase import create_client

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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.google.com/",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120"',
    "sec-fetch-dest": "image",
    "sec-fetch-mode": "no-cors",
    "sec-fetch-site": "cross-site",
}

STORAGE_BASE = f"{SUPABASE_URL}/storage/v1/object/public/place-images"

def upload(place_id, filename, image_bytes, ct="image/jpeg"):
    path = f"{place_id}/{filename}"
    try:
        supabase.storage.from_("place-images").upload(
            path=path, file=image_bytes,
            file_options={"content-type": ct, "upsert": "true"}
        )
        return f"{STORAGE_BASE}/{path}"
    except Exception as e:
        print(f"   storage error: {e}")
        return None

def fetch(place_id, query, limit=8):
    params = {
        "action": "query", "generator": "search",
        "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrlimit": limit, "prop": "imageinfo",
        "iiprop": "url|size|extmetadata|user|timestamp",
        "iiurlwidth": 800, "format": "json",
    }
    resp = requests.get("https://commons.wikimedia.org/w/api.php",
                       params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {}).values()
    images = []
    for page in pages:
        info = page.get("imageinfo", [{}])[0]
        url = info.get("thumburl") or info.get("url", "")
        if not url: continue
        w = info.get("thumbwidth", 0)
        h = info.get("thumbheight", 0)
        if w < 400 or h < 300: continue
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not any(x in lic for x in ["CC", "Public", "PD"]): continue
        author = info.get("user", "")
        ts = info.get("timestamp", "")
        upload_date = ts[:10] if ts else ""
        try:
            img = requests.get(url, headers=HEADERS, timeout=30)
            img.raise_for_status()
            img_bytes = img.content
            ct = img.headers.get("content-type", "image/jpeg").split(";")[0]
        except Exception as e:
            print(f"   download failed ({img.status_code}): {url[-50:]}")
            continue
        fname = re.sub(r'[^a-zA-Z0-9._-]', '_', url.split("/")[-1])[:80]
        if not any(fname.lower().endswith(x) for x in ['.jpg','.jpeg','.png']):
            fname += '.jpg'
        pub_url = upload(place_id, fname, img_bytes, ct)
        if not pub_url: continue
        print(f"   OK: {fname}")
        images.append({
            "place_id": place_id, "url": pub_url,
            "source": "wikimedia", "width": w, "height": h,
            "license": lic, "author": author[:100],
            "upload_date": upload_date,
            "fetched_at": datetime.utcnow().isoformat()
        })
        time.sleep(0.5)
    return images

print("=" * 50)
print(f"PakTour — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
print("Using browser-like headers to bypass 403")
print("=" * 50)
total = 0
for place in PLACES:
    print(f"\n-> {place['id']}")
    try:
        images = fetch(place["id"], place["query"])
        if images:
            supabase.table("place_images").upsert(images, on_conflict="url").execute()
        print(f"   saved: {len(images)}")
        total += len(images)
    except Exception as e:
        print(f"   ERROR: {e}")
    time.sleep(1)
print(f"\nTotal: {total}")
