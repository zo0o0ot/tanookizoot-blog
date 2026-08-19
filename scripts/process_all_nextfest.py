import os
import csv
import re
import urllib.request
import urllib.parse
import html
import time
import argparse
from datetime import datetime, timezone
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
IMAGE_DIR = os.path.join(PROJECT_ROOT, "static/images/reviews")
CONTENT_DIR = os.path.join(PROJECT_ROOT, "content/blogs")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def extract_youtube_id(url_or_id):
    if not url_or_id:
        return ""
    url_or_id = url_or_id.strip()
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
        return url_or_id
    
    m = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', url_or_id)
    if m:
        return m.group(1)
    
    m = re.search(r'[?&]v=([a-zA-Z0-9_-]{11})', url_or_id)
    if m:
        return m.group(1)
    
    m = re.search(r'embed/([a-zA-Z0-9_-]{11})', url_or_id)
    if m:
        return m.group(1)
    
    return url_or_id

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
        req.add_header('Cookie', 'birthtime=283996801; lastagecheckage=1-0-1990; wants_mature_content=1')
        with urllib.request.urlopen(req, timeout=10) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
        
        html_unescaped = html.unescape(html_content).replace(r'\/', '/')
        
        # 1. Screenshot URL
        pattern = r'https://[a-zA-Z0-9.-]+\.steamstatic\.com/store_item_assets/steam/apps/\d+/(?:[a-zA-Z0-9_]+/)?ss_[a-f0-9]+\.1920x1080\.jpg'
        matches = re.findall(pattern, html_unescaped)
        if not matches:
            pattern_alt = r'https://[a-zA-Z0-9.-]+\.steamstatic\.com/store_item_assets/steam/apps/\d+/(?:[a-zA-Z0-9_]+/)?ss_[a-f0-9]+(?:\.[a-zA-Z0-9_]+)?\.jpg'
            matches = re.findall(pattern_alt, html_unescaped)
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
            img_resized = img.resize(target_size, Image.Resampling.LANCZOS)
            img_resized.save(image_path, "JPEG", quality=85, optimize=True)
            print(f"Resized image: {image_path} to {target_size}")
            return True
    except Exception as e:
        print(f"Error resizing image {image_path}: {e}")
        return False

def process_nextfest(csv_file, video_url, month="June", year="2025", title=None, output_file=None):
    if not os.path.isabs(csv_file):
        csv_file = os.path.join(SCRIPT_DIR, csv_file) if not os.path.exists(csv_file) else os.path.abspath(csv_file)

    if not os.path.exists(csv_file):
        print(f"Error: CSV file '{csv_file}' not found!")
        return False

    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(CONTENT_DIR, exist_ok=True)

    video_id = extract_youtube_id(video_url)
    post_title = title if title else f"{month} {year} - Steam Next Fest - Roundup"
    
    if not output_file:
        slug_month = month.lower().replace('.', '')
        post_filename = f"{slug_month}-{year}-next-fest.md"
        post_dest = os.path.join(CONTENT_DIR, post_filename)
    else:
        post_dest = os.path.abspath(output_file) if os.path.isabs(output_file) else os.path.join(PROJECT_ROOT, output_file)

    games_content = []
    first_screenshot = None
    processed_count = 0

    with open(csv_file, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Total games to process in '{os.path.basename(csv_file)}': {len(rows)}")

    for idx, row in enumerate(rows, 1):
        game_name = row.get('Game Name', '').strip()
        store_link = row.get('Store Link', '').strip()
        release_date = row.get('Release Date?', '').strip()
        thoughts = row.get('Thoughts', '').strip()
        wishlist = row.get('Wishlist?', '').strip() or 'Yes'
        played = row.get('Played', '').strip() or 'Yes'

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
                time.sleep(0.5)  # Politeness delay after download

        # Build game markdown block
        game_md = f"## {idx}. [{game_name}]({store_link})\n\n"
        if image_rel_path:
            game_md += f"![{game_name}]({image_rel_path})\n\n"
        
        game_md += f"{thoughts}\n\n"
        
        # Determine release date and popular tags
        final_release_date = details['release_date'] if details['release_date'] else (release_date if release_date else "Coming Soon")
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
    front_matter = {
        'title': post_title,
        'date': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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

    month_name = month.capitalize().replace('.', '')
    md_content += f"Here is my complete list of reviews and impressions for the games I checked out during the Steam Next Fest in {month_name} {year}.\n\n"
    md_content += "<!--more-->\n\n"
    if video_id:
        md_content += f"{{{{< youtube {video_id} >}}}}\n\n"

    # Append all games
    md_content += "".join(games_content)

    with open(post_dest, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"\nDone! Successfully processed {processed_count} games.")
    print(f"Generated Next Fest post at: {post_dest}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Process Steam Next Fest CSV and generate Hugo post.")
    parser.add_argument("--csv", default=os.path.join(SCRIPT_DIR, "2025 June Next Fest List - Sheet1.csv"), help="Path to Next Fest CSV file")
    parser.add_argument("--video", default="fQ-VrTd11k0", help="YouTube Video ID or URL")
    parser.add_argument("--month", default="June", help="Month of Next Fest (e.g. June, Feb)")
    parser.add_argument("--year", default="2025", help="Year of Next Fest (e.g. 2025)")
    parser.add_argument("--title", default=None, help="Post title override")
    parser.add_argument("--output", default=None, help="Output markdown path override")

    args = parser.parse_args()
    process_nextfest(
        csv_file=args.csv,
        video_url=args.video,
        month=args.month,
        year=args.year,
        title=args.title,
        output_file=args.output
    )

if __name__ == '__main__':
    main()
