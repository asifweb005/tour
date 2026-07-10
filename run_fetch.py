import requests, os, time, re
from datetime import datetime
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
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

HEADERS = {
    "User-Agent": "PakTourPlanner/1.0 (https://github.com/asifweb005/tour)",
    "Referer": "https://en.wikipedia.org/",
}

def run():
    print("=" * 50)
    print(f"PakTour fetch — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("NEW SCRIPT: Downloading images to Supabase Storage")
    print("=" * 50)
    total = 0
    for place in PLACES:
        print(f"\n-> {place['id']}")
        try:
            # Step 1: Get image URLs from Wikimedia
            params = {
                "action": "query", "generator": "search",
                "gsrnamespace": 6,
                "gsrsearch": f"{place['query']} filetype:bitmap",
                "gsrlimit": 8, "prop": "imageinfo",
                "iiprop": "url|size|extmetadata|user|timestamp",
                "iiurlwidth": 1200, "format": "json",
            }
            resp = requests.get(
                "https://commons.wikimedia.org/w/api.php",
                params=params, headers=HEADERS, timeout=20
            )
            pages = resp.json().get("query", {}).get("pages", {}).values()
            count = 0
            for page in pages:
                info = page.get("imageinfo", [{}])[0]
                orig_url = info.get("thumburl") or info.get("url", "")
                if not orig_url:
                    continue
                w = info.get("thumbwidth", 0)
                h = info.get("thumbheight", 0)
                if w < 400 or h < 300:
                    continue
                meta = info.get("extmetadata", {})
                lic = meta.get("LicenseShortName", {}).get("value", "")
                if not any(x in lic for x in ["CC", "Public", "PD"]):
                    continue
                uploader = info.get("user", "")
                ts = info.get("timestamp", "")
                upload_date = ts[:10] if ts else ""

                # Step 2: Download the image
                try:
                    img = requests.get(orig_url, headers=HEADERS, timeout=30)
                    img.raise_for_status()
                    img_bytes = img.content
                    ct = img.headers.get("content-type", "image/jpeg").split(";")[0]
                except Exception as e:
                    print(f"   download failed: {e}")
                    continue

                # Step 3: Upload to Supabase Storage
                fname = re.sub(r'[^a-zA-Z0-9._-]', '_', orig_url.split("/")[-1])[:80]
                if not any(fname.lower().endswith(x) for x in ['.jpg','.jpeg','.png','.webp']):
                    fname += '.jpg'
                storage_path = f"{place['id']}/{fname}"
                try:
                    supabase.storage.from_("place-images").upload(
                        path=storage_path,
                        file=img_bytes,
                        file_options={"content-type": ct, "upsert": "true"},
                    )
                    pub_url = f"{STORAGE_BASE}/{storage_path}"
                    print(f"   uploaded: {fname}")
                except Exception as e:
                    print(f"   storage failed: {e}")
                    continue

                # Step 4: Save Supabase URL to DB
                try:
                    supabase.table("place_images").upsert({
                        "place_id": place["id"],
                        "url": pub_url,
                        "source": "wikimedia",
                        "width": w, "height": h,
                        "license": lic,
                        "author": uploader[:100],
                        "upload_date": upload_date,
                        "fetched_at": datetime.utcnow().isoformat(),
                    }, on_conflict="url").execute()
                    count += 1
                except Exception as e:
                    print(f"   db failed: {e}")
                time.sleep(0.3)
            print(f"   DONE: {count} images saved to Supabase Storage")
            total += count
        except Exception as e:
            print(f"   ERROR: {e}")
        time.sleep(1)
    print(f"\nTotal: {total} images")

if __name__ == "__main__":
    run()