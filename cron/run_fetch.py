import requests, os, time
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

HEADERS = {"User-Agent": "PakTourPlanner/1.0 (https://github.com/asifweb005/tour)"}

def fetch_urls(query, limit=8):
    params = {
        "action": "query", "generator": "search",
        "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrlimit": limit, "prop": "imageinfo",
        "iiprop": "url|size|extmetadata|user|timestamp",
        "iiurlwidth": 1200, "format": "json",
    }
    resp = requests.get("https://commons.wikimedia.org/w/api.php",
                       params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {}).values()
    results = []
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
        results.append({
            "url": url,
            "author": author[:100],
            "upload_date": ts[:10] if ts else "",
            "license": lic,
            "width": w,
            "height": h,
        })
    return results

print("=" * 50)
print(f"PakTour URL save — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
print("Saving Wikimedia URLs directly to DB")
print("=" * 50)
total = 0
for place in PLACES:
    print(f"\n-> {place['id']}")
    try:
        urls = fetch_urls(place["query"])
        rows = [{
            "place_id": place["id"],
            "url": u["url"],
            "source": "wikimedia",
            "width": u["width"],
            "height": u["height"],
            "license": u["license"],
            "author": u["author"],
            "upload_date": u["upload_date"],
            "fetched_at": datetime.utcnow().isoformat(),
        } for u in urls]
        if rows:
            supabase.table("place_images").upsert(rows, on_conflict="url").execute()
        print(f"   saved: {len(rows)} URLs")
        total += len(rows)
    except Exception as e:
        print(f"   ERROR: {e}")
    time.sleep(1)
print(f"\nDone. Total: {total} URLs saved")
