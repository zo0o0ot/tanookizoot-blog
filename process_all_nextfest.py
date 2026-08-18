import os
import csv
import re
import urllib.request
import html
import time
from datetime import datetime
from PIL import Image

CSV_FILE = "Feb 2025 Next Fest List - Sheet1.csv"
IMAGE_DIR = "static/images/reviews"
CONTENT_DIR = "content/blogs"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Delete individual post created earlier
INDIVIDUAL_POST = os.path.join(CONTENT_DIR, "bao-bao-s-cozy-landromat.md")
if os.path.exists(INDIVIDUAL_POST):
    os.remove(INDIVIDUAL_POST)
    print(f"Removed individual post: {INDIVIDUAL_POST}")

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def get_steam_game_details(store_url):
    details = {
        'screenshot_url': None,
        'developer': None,
        'publisher': None,
        'release_date': None,
        'tags': [],
        'modes': 'Single-player'
    }
    try:
        req = urllib.request.Request(store_url, headers=HEADERS)
        req.add_header('Cookie', 'birthtime=283996801; lastagecheckage=1-0-1990')
        with urllib.request.urlopen(req, timeout=10) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
        
        html_unescaped = html.unescape(html_content).replace(r'\/', '/')
        
        # 1. Screenshot URL
        pattern = r'https://[a-zA-Z0-9.-]+\.steamstatic\.com/store_item_assets/steam/apps/\d+/(?:[a-zA-Z0-9_]+/)?ss_[a-f0-9]+\.1920x1080\.jpg'
        matches = re.findall(pattern, html_unescaped)
        if matches:
            details['screenshot_url'] = list(dict.fromkeys(matches))[0]
            
        # 2. Developer
        dev_matches = re.findall(r'<b>Developer:</b>\s*<a[^>]*>([^<]+)</a>', html_unescaped, re.IGNORECASE)
        if not dev_matches:
            dev_matches = re.findall(r'id="developers_list".*?<a[^>]*>([^<]+)</a>', html_unescaped, re.DOTALL | re.IGNORECASE)
        if dev_matches:
            details['developer'] = ", ".join(list(dict.fromkeys([d.strip() for d in dev_matches])))

        # 3. Publisher
        pub_matches = re.findall(r'<b>Publisher:</b>\s*<a[^>]*>([^<]+)</a>', html_unescaped, re.IGNORECASE)
        if not pub_matches:
            pub_matches = re.findall(r'<b>Publisher:</b>.*?<a[^>]*>([^<]+)</a>', html_unescaped, re.DOTALL | re.IGNORECASE)
        if pub_matches:
            details['publisher'] = ", ".join(list(dict.fromkeys([p.strip() for p in pub_matches])))

        # 4. Release Date
        release_matches = re.findall(r'<div class="date">([^<]+)</div>', html_unescaped, re.IGNORECASE)
        if release_matches:
            details['release_date'] = release_matches[0].strip()

        # 5. Tags
        tag_matches = re.findall(r'class="app_tag"[^>]*>\s*([^<\r\n\t]+)\s*</a>', html_unescaped, re.IGNORECASE)
        tags = [t.strip() for t in tag_matches if t.strip()]
        details['tags'] = tags[:6]

        # 6. Specs / Modes
        spec_matches = re.findall(r'class="game_area_details_specs_ctn"[^>]*>.*?<div class="label">([^<]+)</div>', html_unescaped, re.DOTALL | re.IGNORECASE)
        specs = [s.strip() for s in spec_matches if s.strip()]
        
        is_sp = any("single" in s.lower() for s in specs + tags)
        is_mp = any(any(x in s.lower() for x in ["multi", "co-op", "coop", "pvp", "mmo", "split screen"]) for s in specs + tags)
        modes = []
        if is_sp:
            modes.append("Single-player")
        if is_mp:
            modes.append("Multiplayer")
        details['modes'] = ", ".join(modes) if modes else "Single-player"

    except Exception as e:
        print(f"Error scraping Steam URL {store_url}: {e}")
    return details

def download_image(url, dest_path):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as response:
            with open(dest_path, 'wb') as f:
                f.write(response.read())
        return True
    except Exception as e:
        print(f"Error downloading image from {url}: {e}")
        return False

def resize_image(image_path, target_size=(1280, 720)):
    try:
        with Image.open(image_path) as img:
            # Resize using High Quality LANCZOS filter
            img_resized = img.resize(target_size, Image.Resampling.LANCZOS)
            # Save as optimized JPEG with 85% quality to save space and load faster
            img_resized.save(image_path, "JPEG", quality=85, optimize=True)
            print(f"Resized image: {image_path} to {target_size}")
            return True
    except Exception as e:
        print(f"Error resizing image {image_path}: {e}")
        return False

def main():
    if not os.path.exists(CSV_FILE):
        print(f"Error: {CSV_FILE} not found!")
        return

    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(CONTENT_DIR, exist_ok=True)

    games_content = []
    first_screenshot = None
    processed_count = 0

    with open(CSV_FILE, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Total games to process: {len(rows)}")

    for idx, row in enumerate(rows, 1):
        game_name = row['Game Name'].strip()
        store_link = row['Store Link'].strip()
        release_date = row['Release Date?'].strip()
        thoughts = row['Thoughts'].strip()
        wishlist = row['Wishlist?'].strip()
        played = row['Played'].strip()
        order_in_video = row['Order in Video'].strip()
        top_50 = row['Top 50 rank'].strip()

        if not game_name or not store_link:
            continue

        slug = slugify(game_name)
        print(f"[{idx}/{len(rows)}] Processing '{game_name}'...")

        details = get_steam_game_details(store_link)
        screenshot_url = details['screenshot_url']
        image_rel_path = ""

        if screenshot_url:
            image_filename = f"{slug}.jpg"
            image_dest = os.path.join(IMAGE_DIR, image_filename)
            image_rel_path = f"/images/reviews/{image_filename}"
            if not first_screenshot:
                first_screenshot = image_rel_path
            
            if not os.path.exists(image_dest):
                if download_image(screenshot_url, image_dest):
                    resize_image(image_dest)
                time.sleep(0.5)  # Politeness delay only after downloading

        # Build game markdown block
        game_md = f"## {idx}. [{game_name}]({store_link})\n\n"
        if image_rel_path:
            game_md += f"![{game_name}]({image_rel_path})\n\n"
        
        game_md += f"{thoughts}\n\n"
        
        # Determine release date and popular tags
        final_release_date = details['release_date'] if details['release_date'] else release_date
        popular_tags = ", ".join(details['tags']) if details['tags'] else ""

        # Details
        game_md += "#### Details:\n"
        game_md += f"- **Steam Page**: [{game_name}]({store_link})\n"
        if details['developer']:
            game_md += f"- **Developer**: {details['developer']}\n"
        if details['publisher']:
            game_md += f"- **Publisher**: {details['publisher']}\n"
        game_md += f"- **Release Date**: {final_release_date}\n"
        game_md += f"- **Game Modes**: {details['modes']}\n"
        if popular_tags:
            game_md += f"- **Popular Tags**: {popular_tags}\n"
        game_md += f"- **Played**: {played}\n"
        game_md += f"- **Wishlisted**: {wishlist}\n"
        
        game_md += "\n---\n\n"
        games_content.append(game_md)
        processed_count += 1

    # Post Front Matter
    post_filename = "feb-2025-next-fest.md"
    post_dest = os.path.join(CONTENT_DIR, post_filename)
    
    front_matter = {
        'title': "Feb. 2025 - Steam Next Fest - Roundup",
        'date': datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        'draft': False,
        'tags': ["Next Fest", "Game Review", "Steam"],
    }
    if first_screenshot:
        front_matter['image'] = first_screenshot

    md_content = "---\n"
    for k, v in front_matter.items():
        if isinstance(v, list):
            md_content += f"{k}:\n"
            for item in v:
                md_content += f"  - \"{item}\"\n"
        elif isinstance(v, bool):
            md_content += f"{k}: {str(v).lower()}\n"
        else:
            md_content += f"{k}: \"{v}\"\n"
    md_content += "---\n\n"

    md_content += "Here is my complete list of reviews and impressions for the games I checked out during the Steam Next Fest in February 2025.\n\n"
    md_content += "<!--more-->\n\n"
    md_content += "{{< youtube BtIddN_prG4 >}}\n\n"

    # Append all games
    md_content += "".join(games_content)

    with open(post_dest, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"\nDone! Processed {processed_count} games.")
    print(f"Generated Next Fest post at: {post_dest}")

if __name__ == '__main__':
    main()
