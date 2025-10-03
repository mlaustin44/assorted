#!/usr/bin/env python3
"""
Universal muOS ROM Organizer
Builds complete muOS file structure using ScreenScraper API for ROM identification
Supports all systems and automatically downloads box art
"""

import csv
import os
import shutil
import re
import hashlib
import json
import time
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import argparse
from urllib.parse import quote
import zipfile
from html.parser import HTMLParser
import subprocess
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL not available. Install with: pip install Pillow")

SKYSCRAPER_PATH = "/tmp/ss/Skyscraper"

# muOS folder name mappings (based on folder.json)
# Note: muOS uses lowercase folder names but we'll use uppercase for compatibility
SYSTEM_TO_MUOS_FOLDER = {
    'Nintendo 64': 'N64',
    'N64': 'N64',
    'PlayStation': 'PS',
    'PS1': 'PS',
    'PSX': 'PS',
    'Dreamcast': 'DC',
    'Arcade': 'ARCADE',
    'MAME': 'ARCADE',
    'FBA': 'ARCADE',
    'Game Boy': 'GB',
    'Game Boy Color': 'GBC',
    'Game Boy Advance': 'GBA',
    'GBA': 'GBA',
    'NES': 'FC',  # Famicom folder
    'Nintendo Entertainment System': 'FC',
    'SNES': 'SFC',  # Super Famicom folder
    'Super Nintendo': 'SFC',
    'Genesis': 'MD',  # Mega Drive folder
    'Mega Drive': 'MD',
    'Sega Genesis': 'MD',
    'Neo Geo': 'NEOGEO',
    'Atari 2600': 'ATARI',
    'TurboGrafx-16': 'PCE',  # PC Engine folder
    'PC Engine': 'PCE',
    'Master System': 'MS',
    'Sega Master System': 'MS',
    'Game Gear': 'GG',
    'Neo Geo Pocket': 'NGP',
    'WonderSwan': 'WS',
    'PlayStation Portable': 'PSP'
}

# ScreenScraper system IDs
SYSTEM_TO_SCREENSCRAPER_ID = {
    'NES': 3,
    'FC': 3,
    'SNES': 4,
    'SFC': 4,
    'N64': 14,
    'GB': 9,
    'GBC': 10,
    'GBA': 12,
    'MD': 1,
    'Genesis': 1,
    'MS': 2,
    'GG': 21,
    'PCE': 31,
    'NEOGEO': 142,
    'ARCADE': 75,
    'PS': 57,
    'DC': 23,
    'ATARI': 26,
    'NGP': 25,
    'WS': 45,
    'PSP': 61
}

class SkyscraperWrapper:
    """Wrapper for Skyscraper to handle artwork scraping"""

    def __init__(self, username: str = None, password: str = None,
                 dev_id: str = None, dev_pass: str = None):
        self.username = username
        self.password = password
        self.skyscraper_path = Path(SKYSCRAPER_PATH)
        self.cache_dir = Path.home() / '.skyscraper'
        self.processed_systems = set()  # Track which systems we've scraped

        # Platform mappings for Skyscraper
        self.platform_map = {
            'N64': 'n64',
            'PS': 'psx',
            'DC': 'dreamcast',
            'ARCADE': 'arcade',
            'GB': 'gb',
            'GBC': 'gbc',
            'GBA': 'gba',
            'FC': 'nes',
            'SFC': 'snes',
            'MD': 'megadrive',
            'NEOGEO': 'neogeo',
            'ATARI': 'atari2600',
            'PCE': 'pcengine',
            'MS': 'mastersystem',
            'GG': 'gamegear',
        }

        # muOS catalogue names - MUST match muOS exactly from:
        # https://github.com/MustardOS/internal/tree/main/share/info/assign
        self.catalogue_names = {
            'N64': 'Nintendo N64',
            'PS': 'Sony PlayStation',
            'DC': 'Sega Dreamcast',
            'ARCADE': 'Arcade',
            'GB': 'Nintendo Game Boy',
            'GBC': 'Nintendo Game Boy Color',
            'GBA': 'Nintendo Game Boy Advance',
            'FC': 'Nintendo NES - Famicom',
            'SFC': 'Nintendo SNES - SFC',
            'MD': 'Sega Mega Drive - Genesis',
            'NEOGEO': 'SNK Neo Geo',
            'ATARI': 'Atari 2600',
            'PCE': 'NEC PC Engine',
            'MS': 'Sega Master System',
            'GG': 'Sega Game Gear',
        }
        
    def scrape_system_artwork(self, system_dir: Path, muos_system: str, output_dir: Path) -> bool:
        """Scrape artwork for a system using Skyscraper"""
        # Skip if already processed this system
        if muos_system in self.processed_systems:
            return True

        # Check if Skyscraper exists
        if not self.skyscraper_path.exists():
            print(f"  Skyscraper not found at {self.skyscraper_path}")
            return False

        # Get platform name for Skyscraper
        sky_platform = self.platform_map.get(muos_system)
        catalogue_name = self.catalogue_names.get(muos_system)

        if not sky_platform or not catalogue_name:
            return False

        print(f"\n  Scraping artwork for {catalogue_name}...")

        # Create output directories
        catalogue_dir = output_dir / 'MUOS' / 'info' / 'catalogue' / catalogue_name
        box_dir = catalogue_dir / 'box'
        preview_dir = catalogue_dir / 'preview'
        text_dir = catalogue_dir / 'text'

        try:
            # Step 1: Cache resources from ScreenScraper
            print(f"    Caching resources from ScreenScraper...")
            cache_cmd = [
                str(self.skyscraper_path),
                '-p', sky_platform,
                '-s', 'screenscraper',
                '-i', str(system_dir.absolute()),
                '--flags', 'unattend,skipped,nobrackets',
                '--verbosity', '1',
                '--maxfails', '3'
            ]

            # Add credentials if available
            if self.username and self.password:
                cache_cmd.extend(['-u', f"{self.username}:{self.password}"])

            # Debug: print command
            # print(f"    Debug: Running {' '.join(cache_cmd[:5])}...")

            # Longer timeout for caching - some systems have many games
            result = subprocess.run(cache_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else result.stdout if result.stdout else 'No output'
                print(f"    ⚠ Cache step failed: {error_msg[:500]}")

            # Step 2: Generate artwork (if artwork configs exist)
            artwork_box_config = Path.cwd() / 'artwork_box.xml'
            artwork_preview_config = Path.cwd() / 'artwork_preview.xml'

            if artwork_box_config.exists():
                print(f"    Generating box artwork...")
                box_dir.mkdir(parents=True, exist_ok=True)

                gen_cmd = [
                    str(self.skyscraper_path),
                    '-p', sky_platform,
                    '-i', str(system_dir.absolute()),
                    '-d', str(Path.home() / '.skyscraper' / 'cache' / sky_platform),
                    '-g', str(catalogue_dir.absolute()),
                    '-a', str(artwork_box_config.absolute()),
                    '-f', 'emulationstation',
                    '--flags', 'unattend,nobrackets',
                    '--verbosity', '0'
                ]
                result = subprocess.run(gen_cmd, capture_output=True, text=True, timeout=180)
                if result.returncode != 0:
                    print(f"    ⚠ Box art generation failed: {result.stderr[:200] if result.stderr else 'Unknown error'}")
                else:
                    # Move generated cover images to box directory
                    # Skyscraper puts covers in covers/ subdirectory
                    covers_dir = catalogue_dir / 'covers'
                    if covers_dir.exists():
                        for img in covers_dir.glob('*'):
                            if img.is_file():
                                dest = box_dir / img.name
                                img.rename(dest)
                        covers_dir.rmdir()

                    # Also check for media/covers in case of different output
                    media_covers = catalogue_dir / 'media' / 'covers'
                    if media_covers.exists():
                        for img in media_covers.glob('*'):
                            if img.is_file():
                                dest = box_dir / img.name
                                img.rename(dest)
                        if media_covers.parent.exists() and not any(media_covers.parent.iterdir()):
                            media_covers.parent.rmdir()

                    # Extract actual cover art from cache if PIL is available
                    if PIL_AVAILABLE:
                        self.extract_covers_from_cache(sky_platform, system_dir, box_dir)

            if artwork_preview_config.exists():
                print(f"    Generating preview screenshots...")
                preview_dir.mkdir(parents=True, exist_ok=True)

                preview_cmd = [
                    str(self.skyscraper_path),
                    '-p', sky_platform,
                    '-i', str(system_dir.absolute()),
                    '-d', str(Path.home() / '.skyscraper' / 'cache' / sky_platform),
                    '-g', str(catalogue_dir.absolute()),
                    '-a', str(artwork_preview_config.absolute()),
                    '-f', 'emulationstation',
                    '--flags', 'unattend,nobrackets',
                    '--verbosity', '0'
                ]
                result = subprocess.run(preview_cmd, capture_output=True, text=True, timeout=180)
                if result.returncode != 0:
                    print(f"    ⚠ Preview generation failed: {result.stderr[:200] if result.stderr else 'Unknown error'}")
                else:
                    # Move generated screenshot images to preview directory
                    # Skyscraper puts screenshots in screenshots/ subdirectory
                    screenshots_dir = catalogue_dir / 'screenshots'
                    if screenshots_dir.exists():
                        for img in screenshots_dir.glob('*'):
                            if img.is_file():
                                dest = preview_dir / img.name
                                img.rename(dest)
                        screenshots_dir.rmdir()

                    # Also check for media/screenshots in case of different output
                    media_screenshots = catalogue_dir / 'media' / 'screenshots'
                    if media_screenshots.exists():
                        for img in media_screenshots.glob('*'):
                            if img.is_file():
                                dest = preview_dir / img.name
                                img.rename(dest)
                        if media_screenshots.parent.exists() and not any(media_screenshots.parent.iterdir()):
                            media_screenshots.parent.rmdir()

                    # Extract preview screenshots from cache with proper resizing
                    if PIL_AVAILABLE:
                        self.extract_previews_from_cache(sky_platform, system_dir, preview_dir)

            # Extract text descriptions from cache to muOS text format
            # Text files go in catalogue/[Full System Name]/text/
            text_meta_dir = catalogue_dir / 'text'
            text_meta_dir.mkdir(parents=True, exist_ok=True)
            self.extract_texts_from_cache(sky_platform, system_dir, text_meta_dir)

            # Clean up gamelist.xml and other Skyscraper artifacts
            gamelist_file = catalogue_dir / 'gamelist.xml'
            if gamelist_file.exists():
                gamelist_file.unlink()

            # Clean up any remaining media directories
            for subdir in ['media', 'covers', 'marquees', 'wheels', 'videos']:
                path = catalogue_dir / subdir
                if path.exists() and path.is_dir():
                    import shutil
                    shutil.rmtree(path)

            # Mark system as processed
            self.processed_systems.add(muos_system)
            print(f"    ✓ Artwork scraped for {catalogue_name}")
            return True

        except subprocess.TimeoutExpired:
            print(f"    ⚠ Skyscraper timed out for {catalogue_name}")
        except Exception as e:
            print(f"    ✗ Error scraping {catalogue_name}: {e}")

        return False
    
    def extract_covers_from_cache(self, platform: str, system_dir: Path, output_dir: Path):
        """Extract actual cover art from Skyscraper cache and resize for muOS"""
        if not PIL_AVAILABLE:
            return

        cache_dir = Path.home() / '.skyscraper' / 'cache' / platform
        db_file = cache_dir / 'db.xml'
        quickid_file = cache_dir / 'quickid.xml'

        if not db_file.exists() or not quickid_file.exists():
            print(f"      No cache files found for {platform}")
            return

        import xml.etree.ElementTree as ET
        try:
            # First, parse quickid.xml to get ROM filepath to ID mapping
            quickid_tree = ET.parse(quickid_file)
            quickid_root = quickid_tree.getroot()

            # Build a map of resource ID to ROM name
            rom_id_map = {}
            for quickid in quickid_root.findall('quickid'):
                filepath = quickid.get('filepath')
                resource_id = quickid.get('id')
                if filepath and resource_id:
                    rom_filename = Path(filepath).name
                    # Check if this ROM exists in our system directory
                    rom_path = system_dir / rom_filename
                    if rom_path.exists():
                        rom_id_map[resource_id] = rom_filename

            if not rom_id_map:
                print(f"      No matching ROMs found in cache for {platform}")
                return

            # Now parse db.xml to get the resource information
            db_tree = ET.parse(db_file)
            db_root = db_tree.getroot()

            # Build a map of resource IDs to their data
            resources = {}
            for resource in db_root.findall('resource'):
                res_id = resource.get('id')
                res_type = resource.get('type')
                if res_id and res_type:
                    if res_id not in resources:
                        resources[res_id] = {}
                    resources[res_id][res_type] = resource.text

            # Now process each ROM and extract its cover
            covers_found = 0
            for resource_id, rom_filename in rom_id_map.items():
                rom_stem = Path(rom_filename).stem

                # Find the cover for this resource ID
                if resource_id in resources and 'cover' in resources[resource_id]:
                    cover_rel_path = resources[resource_id]['cover']
                    if cover_rel_path:
                        cover_path = cache_dir / cover_rel_path
                        if cover_path.exists():
                            # Resize and save the cover
                            output_path = output_dir / f"{rom_stem}.png"
                            if self.resize_image_with_padding(cover_path, output_path, 320, 240):
                                covers_found += 1
                                print(f"      ✓ Extracted cover for {rom_stem}")

            if covers_found > 0:
                print(f"      Extracted {covers_found} cover images from cache")
            else:
                print(f"      No covers could be extracted from cache")

        except Exception as e:
            print(f"      Error extracting covers: {e}")

    def resize_image_with_padding(self, input_path: Path, output_path: Path,
                                   target_width: int, target_height: int,
                                   bg_color: tuple = (0, 0, 0)) -> bool:
        """Resize image to fit within target dimensions, adding padding to maintain aspect ratio"""
        try:
            from PIL import Image

            # Open the image
            img = Image.open(input_path)

            # Convert RGBA to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create a new RGB image with black background
                rgb_img = Image.new('RGB', img.size, bg_color)
                # Paste the image using its alpha channel as mask
                if img.mode == 'RGBA' or img.mode == 'LA':
                    rgb_img.paste(img, mask=img.split()[-1])  # Use alpha channel
                else:
                    rgb_img.paste(img)
                img = rgb_img

            # Calculate scaling to fit within target dimensions
            scale_x = target_width / img.width
            scale_y = target_height / img.height
            scale = min(scale_x, scale_y)

            # Calculate new dimensions
            new_width = int(img.width * scale)
            new_height = int(img.height * scale)

            # Resize the image with antialiasing
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Create a new image with the target dimensions and black background
            final_img = Image.new('RGB', (target_width, target_height), bg_color)

            # Calculate position to center the resized image
            x_offset = (target_width - new_width) // 2
            y_offset = (target_height - new_height) // 2

            # Paste the resized image onto the background
            final_img.paste(img_resized, (x_offset, y_offset))

            # Save the final image
            final_img.save(output_path, 'PNG', optimize=True)
            return True

        except Exception as e:
            print(f"        Error resizing image: {e}")
            return False

    def extract_previews_from_cache(self, platform: str, system_dir: Path, output_dir: Path):
        """Extract preview screenshots from Skyscraper cache and resize for muOS"""
        if not PIL_AVAILABLE:
            return

        cache_dir = Path.home() / '.skyscraper' / 'cache' / platform
        db_file = cache_dir / 'db.xml'
        quickid_file = cache_dir / 'quickid.xml'

        if not db_file.exists() or not quickid_file.exists():
            return

        import xml.etree.ElementTree as ET
        try:
            # Parse quickid.xml to get ROM filepath to ID mapping
            quickid_tree = ET.parse(quickid_file)
            quickid_root = quickid_tree.getroot()

            # Build a map of resource ID to ROM name
            rom_id_map = {}
            for quickid in quickid_root.findall('quickid'):
                filepath = quickid.get('filepath')
                resource_id = quickid.get('id')
                if filepath and resource_id:
                    rom_filename = Path(filepath).name
                    # Check if this ROM exists in our system directory
                    rom_path = system_dir / rom_filename
                    if rom_path.exists():
                        rom_id_map[resource_id] = rom_filename

            if not rom_id_map:
                return

            # Parse db.xml to get the resource information
            db_tree = ET.parse(db_file)
            db_root = db_tree.getroot()

            # Build a map of resource IDs to their data
            resources = {}
            for resource in db_root.findall('resource'):
                res_id = resource.get('id')
                res_type = resource.get('type')
                if res_id and res_type:
                    if res_id not in resources:
                        resources[res_id] = {}
                    resources[res_id][res_type] = resource.text

            # Process each ROM and extract its screenshot
            previews_found = 0
            for resource_id, rom_filename in rom_id_map.items():
                rom_stem = Path(rom_filename).stem

                # Find the screenshot for this resource ID
                if resource_id in resources and 'screenshot' in resources[resource_id]:
                    screenshot_rel_path = resources[resource_id]['screenshot']
                    if screenshot_rel_path:
                        screenshot_path = cache_dir / screenshot_rel_path
                        if screenshot_path.exists():
                            # Resize and save the preview with padding
                            output_path = output_dir / f"{rom_stem}.png"
                            if self.resize_image_with_padding(screenshot_path, output_path, 515, 275):
                                previews_found += 1

            if previews_found > 0:
                print(f"      Extracted {previews_found} preview images from cache")

        except Exception as e:
            print(f"      Error extracting previews: {e}")

    def extract_texts_from_cache(self, platform: str, system_dir: Path, output_dir: Path):
        """Extract game descriptions from Skyscraper cache in muOS meta format"""
        cache_dir = Path.home() / '.skyscraper' / 'cache' / platform
        db_file = cache_dir / 'db.xml'
        quickid_file = cache_dir / 'quickid.xml'

        if not db_file.exists() or not quickid_file.exists():
            return

        import xml.etree.ElementTree as ET
        try:
            # Parse quickid.xml to get ROM filepath to ID mapping
            quickid_tree = ET.parse(quickid_file)
            quickid_root = quickid_tree.getroot()

            # Build a map of resource ID to ROM name
            rom_id_map = {}
            for quickid in quickid_root.findall('quickid'):
                filepath = quickid.get('filepath')
                resource_id = quickid.get('id')
                if filepath and resource_id:
                    rom_filename = Path(filepath).name
                    # Check if this ROM exists in our system directory
                    rom_path = system_dir / rom_filename
                    if rom_path.exists():
                        rom_id_map[resource_id] = rom_filename

            if not rom_id_map:
                return

            # Parse db.xml to get the resource information
            db_tree = ET.parse(db_file)
            db_root = db_tree.getroot()

            # Build a map of resource IDs to their data
            resources = {}
            for resource in db_root.findall('resource'):
                res_id = resource.get('id')
                res_type = resource.get('type')
                if res_id and res_type:
                    if res_id not in resources:
                        resources[res_id] = {}
                    resources[res_id][res_type] = resource.text

            # Process each ROM and extract its description
            texts_found = 0
            for resource_id, rom_filename in rom_id_map.items():
                rom_stem = Path(rom_filename).stem

                # Get just the description for this game (muOS format)
                if resource_id in resources:
                    game_data = resources[resource_id]

                    # muOS meta files contain ONLY the description text
                    description = game_data.get('description', '')

                    # Only save if we have a description
                    if description:
                        output_path = output_dir / f"{rom_stem}.txt"
                        try:
                            with open(output_path, 'w', encoding='utf-8') as f:
                                f.write(description)
                            texts_found += 1
                        except Exception as e:
                            print(f"      Error saving meta for {rom_stem}: {e}")

            if texts_found > 0:
                print(f"      Extracted {texts_found} game descriptions to text")

        except Exception as e:
            print(f"      Error extracting texts: {e}")

    def process_system_complete(self, system_dir: Path, muos_system: str, output_dir: Path):
        """Process all artwork for a system after all ROMs are collected"""
        return self.scrape_system_artwork(system_dir, muos_system, output_dir)

    

class MuOSOrganizer:
    """Main organizer class that builds muOS file structure"""
    
    def __init__(self, csv_path: str, rom_dirs: List[str], output_dir: str,
                 ss_user: str = None, ss_pass: str = None, download_missing: bool = False):
        self.csv_path = Path(csv_path)
        self.rom_dirs = [Path(d) for d in rom_dirs]
        self.output_dir = Path(output_dir)
        self.scraper = SkyscraperWrapper(ss_user, ss_pass)
        self.download_missing = download_missing
        
        # Statistics
        self.stats = {
            'found': 0,
            'missing': 0,
            'identified': 0,
            'media_downloaded': 0,
            'roms_downloaded': 0
        }
        
        # Myrient base URLs for different systems
        self.myrient_urls = {
            'NES': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Nintendo%20Entertainment%20System%20(Headerless)/',
            'Nintendo Entertainment System': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Nintendo%20Entertainment%20System%20(Headerless)/',
            'FC': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Nintendo%20Entertainment%20System%20(Headerless)/',
            'SNES': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Super%20Nintendo%20Entertainment%20System/',
            'Super Nintendo': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Super%20Nintendo%20Entertainment%20System/',
            'SFC': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Super%20Nintendo%20Entertainment%20System/',
            'N64': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Nintendo%2064%20(BigEndian)/',
            'Nintendo 64': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Nintendo%2064%20(BigEndian)/',
            'GB': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Game%20Boy/',
            'Game Boy': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Game%20Boy/',
            'GBC': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Game%20Boy%20Color/',
            'Game Boy Color': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Game%20Boy%20Color/',
            'GBA': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Game%20Boy%20Advance/',
            'Game Boy Advance': 'https://myrient.erista.me/files/No-Intro/Nintendo%20-%20Game%20Boy%20Advance/',
            'Genesis': 'https://myrient.erista.me/files/No-Intro/Sega%20-%20Mega%20Drive%20-%20Genesis/',
            'Mega Drive': 'https://myrient.erista.me/files/No-Intro/Sega%20-%20Mega%20Drive%20-%20Genesis/',
            'Sega Genesis': 'https://myrient.erista.me/files/No-Intro/Sega%20-%20Mega%20Drive%20-%20Genesis/',
            'MD': 'https://myrient.erista.me/files/No-Intro/Sega%20-%20Mega%20Drive%20-%20Genesis/',
            'Master System': 'https://myrient.erista.me/files/No-Intro/Sega%20-%20Master%20System%20-%20Mark%20III/',
            'Sega Master System': 'https://myrient.erista.me/files/No-Intro/Sega%20-%20Master%20System%20-%20Mark%20III/',
            'MS': 'https://myrient.erista.me/files/No-Intro/Sega%20-%20Master%20System%20-%20Mark%20III/',
            'Game Gear': 'https://myrient.erista.me/files/No-Intro/Sega%20-%20Game%20Gear/',
            'GG': 'https://myrient.erista.me/files/No-Intro/Sega%20-%20Game%20Gear/',
            'PlayStation': 'https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation/',
            'PS1': 'https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation/',
            'PSX': 'https://myrient.erista.me/files/Redump/Sony%20-%20PlayStation/',
            'Dreamcast': 'https://myrient.erista.me/files/Redump/Sega%20-%20Dreamcast/',
            # Note: MAME/Arcade ROMs must be provided locally - no public Myrient source
            'Neo Geo': 'https://myrient.erista.me/files/No-Intro/SNK%20-%20Neo%20Geo%20Pocket%20Color/',
            'NEOGEO': 'https://myrient.erista.me/files/No-Intro/SNK%20-%20Neo%20Geo%20Pocket%20Color/',
            'TurboGrafx-16': 'https://myrient.erista.me/files/No-Intro/NEC%20-%20PC%20Engine%20-%20TurboGrafx-16/',
            'PC Engine': 'https://myrient.erista.me/files/No-Intro/NEC%20-%20PC%20Engine%20-%20TurboGrafx-16/',
            'PCE': 'https://myrient.erista.me/files/No-Intro/NEC%20-%20PC%20Engine%20-%20TurboGrafx-16/',
            'Atari 2600': 'https://myrient.erista.me/files/No-Intro/Atari%20-%202600/',
            'ATARI': 'https://myrient.erista.me/files/No-Intro/Atari%20-%202600/',
        }
        
    def organize(self, download_media: bool = True, copy_roms: bool = True):
        """Main organization process"""
        print("=" * 60)
        print("muOS Universal ROM Organizer")
        print("=" * 60)
        
        # Create output structure
        self.output_dir.mkdir(parents=True, exist_ok=True)
        roms_dir = self.output_dir / 'Roms'
        roms_dir.mkdir(exist_ok=True)
        
        # Read CSV
        games_list = self.read_csv()
        print(f"\nLoaded {len(games_list)} games from CSV")
        
        # Find all ROM files in source directories AND output directory
        available_roms = self.scan_rom_directories()

        # Also scan output directory for existing ROMs
        output_rom_count = self.scan_output_directory(available_roms, roms_dir)
        print(f"Found {len(available_roms)} ROM files in source directories")
        if output_rom_count > 0:
            print(f"Found {output_rom_count} existing ROMs in output directory")
        
        # Process each game
        print("\nProcessing games...")
        print("-" * 60)
        
        for game in games_list:
            self.process_game(game, available_roms, roms_dir, download_media, copy_roms)
        
        # Copy BIOS files if found
        self.copy_bios_files()

        # Scrape artwork for all systems using Skyscraper
        if download_media:
            print("\n" + "=" * 60)
            print("Scraping artwork with Skyscraper...")
            print("=" * 60)

            # Process each system that has ROMs
            systems_processed = set()
            for system_dir in roms_dir.iterdir():
                if system_dir.is_dir() and system_dir.name not in systems_processed:
                    # Check if system has any ROMs
                    rom_count = len(list(system_dir.glob('*')))
                    if rom_count > 0:
                        print(f"\nProcessing artwork for {system_dir.name} ({rom_count} ROMs)...")
                        self.scraper.scrape_system_artwork(system_dir, system_dir.name, self.output_dir)
                        systems_processed.add(system_dir.name)

        # Print summary
        self.print_summary()
        
        # Save report
        self.save_report(games_list)
    
    def read_csv(self) -> List[Dict]:
        """Read games from CSV file"""
        games = []
        
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            # Detect delimiter
            first_line = f.readline()
            f.seek(0)
            delimiter = '\t' if '\t' in first_line else ','
            
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                # Handle different CSV formats
                game = {
                    'name': row.get('Game Name', row.get('Game', row.get('Name', row.get('name', '')))),
                    'system': row.get('System', row.get('system', '')),
                    'category': row.get('Category', row.get('Category/Set', '')),
                    'notes': row.get('Notes', ''),
                    'rom_path': row.get('rom_path', row.get('ROM Path', row.get('Rom Path', row.get('path', ''))))
                }
                if game['name'] and game['system']:
                    games.append(game)
        
        return games
    
    def scan_output_directory(self, roms_by_system: Dict[str, List[Path]], roms_dir: Path) -> int:
        """Scan output directory for already existing ROMs"""
        if not roms_dir.exists():
            return 0

        output_rom_count = 0
        for system_dir in roms_dir.iterdir():
            if not system_dir.is_dir():
                continue

            system_name = system_dir.name
            if system_name not in roms_by_system:
                roms_by_system[system_name] = []

            for rom_file in system_dir.iterdir():
                if rom_file.is_file() and self.is_rom_file(rom_file):
                    roms_by_system[system_name].append(rom_file)
                    output_rom_count += 1

        return output_rom_count

    def scan_rom_directories(self) -> Dict[str, List[Path]]:
        """Scan all ROM directories and build index by system"""
        roms_by_system = {}
        total_files = 0
        
        for rom_dir in self.rom_dirs:
            if not rom_dir.exists():
                print(f"Warning: Directory does not exist: {rom_dir}")
                continue
            
            print(f"Scanning: {rom_dir}")
            # Scan recursively with depth limit
            for rom_file in rom_dir.rglob('*'):
                # Skip if too deep (more than 6 levels)
                try:
                    depth = len(rom_file.relative_to(rom_dir).parts)
                    if depth > 6:
                        continue
                except:
                    continue
                    
                if rom_file.is_file() and self.is_rom_file(rom_file):
                    total_files += 1
                    # Try to determine system from path
                    system = self.detect_system_from_path(rom_file)
                    if system not in roms_by_system:
                        roms_by_system[system] = []
                    roms_by_system[system].append(rom_file)
        
        # Debug output
        print(f"Found {total_files} ROM files across {len(roms_by_system)} systems")
        for system, roms in roms_by_system.items():
            if len(roms) > 0:
                print(f"  {system}: {len(roms)} files")
        
        return roms_by_system
    
    def is_rom_file(self, file_path: Path) -> bool:
        """Check if file is likely a ROM"""
        rom_extensions = {
            '.zip', '.7z', '.rar',  # Archives
            '.nes', '.sfc', '.smc', '.gb', '.gbc', '.gba',  # Nintendo
            '.md', '.smd', '.gen', '.sms', '.gg',  # Sega
            '.pce', '.iso', '.cue', '.bin', '.chd',  # CD systems
            '.n64', '.z64', '.v64', '.ndd',  # N64
            '.cdi', '.gdi',  # Dreamcast
            '.pbp', '.cso',  # PSP
            '.img', '.ccd', '.mdf', '.nrg',  # More CD formats
            '.rom', '.32x', '.sg',  # Other formats
        }
        
        # Special case for BIOS files we want to ignore
        if file_path.name.startswith('bios') or file_path.name == 'PSXONPSP660.bin':
            return False
            
        return file_path.suffix.lower() in rom_extensions
    
    def detect_system_from_path(self, rom_path: Path) -> str:
        """Try to detect system from file path"""
        path_str = str(rom_path).upper()
        
        # Look for system folder markers in path
        # Check for actual folder names, not just substring matches
        path_parts = [p.upper() for p in rom_path.parts]
        
        # Direct folder name matches
        if 'ARCADE' in path_parts:
            return 'ARCADE'
        elif 'N64' in path_parts or 'NINTENDO64' in path_parts:
            return 'N64'
        elif 'PS' in path_parts or 'PS1' in path_parts or 'PSX' in path_parts or 'PLAYSTATION' in path_parts:
            return 'PS'
        elif 'DC' in path_parts or 'DREAMCAST' in path_parts:
            return 'DC'
        elif 'GBA' in path_parts:
            return 'GBA'
        elif 'GBC' in path_parts:
            return 'GBC'
        elif 'GB' in path_parts and 'GBA' not in path_parts and 'GBC' not in path_parts:
            return 'GB'
        elif 'FC' in path_parts or 'NES' in path_parts:
            return 'FC'
        elif 'SFC' in path_parts or 'SNES' in path_parts:
            return 'SFC'
        elif 'MD' in path_parts or 'GENESIS' in path_parts or 'MEGADRIVE' in path_parts:
            return 'MD'
        elif 'NEOGEO' in path_parts:
            return 'NEOGEO'
        elif 'ATARI' in path_parts:
            return 'ATARI'
        elif 'PCE' in path_parts or 'PCENGINE' in path_parts or 'TURBOGRAFX' in path_parts:
            return 'PCE'
        elif 'MS' in path_parts:
            return 'MS'
        elif 'GG' in path_parts:
            return 'GG'
        
        # Check file extension as fallback
        ext = rom_path.suffix.lower()
        if ext in ['.n64', '.z64', '.v64']:
            return 'N64'
        elif ext == '.nes':
            return 'FC'
        elif ext in ['.sfc', '.smc']:
            return 'SFC'
        elif ext == '.gb':
            return 'GB'
        elif ext == '.gbc':
            return 'GBC'
        elif ext == '.gba':
            return 'GBA'
        elif ext in ['.md', '.smd', '.gen']:
            return 'MD'
        elif ext in ['.sms']:
            return 'MS'
        elif ext == '.gg':
            return 'GG'
        elif ext == '.pce':
            return 'PCE'
        elif ext in ['.chd', '.iso', '.cue', '.bin'] and '/PS/' in path_str:
            return 'PS'
        
        # Default to unknown
        return 'UNKNOWN'
    
    def find_rom_for_game(self, game_name: str, system: str,
                         available_roms: Dict[str, List[Path]]) -> Optional[Path]:
        """Find ROM file matching the game"""
        # Map system name to muOS folder
        muos_system = SYSTEM_TO_MUOS_FOLDER.get(system, system)

        # Get candidate ROMs ONLY for the correct system
        candidates = []

        # Handle special case for games with slash (e.g., "Pokemon Blue/Red")
        # Try to find any of the versions
        game_variants = []
        if '/' in game_name:
            # Split and create variants
            base, variants = game_name.rsplit(' ', 1) if ' ' in game_name else ('', game_name)
            if '/' in variants:
                for variant in variants.split('/'):
                    if base:
                        game_variants.append(f"{base} {variant}")
                    else:
                        game_variants.append(variant)
        game_variants.append(game_name)  # Also try the original
        
        # Strict system matching - only look in ROMs from the correct system folder
        if system in ['Nintendo 64', 'N64']:
            candidates.extend(available_roms.get('N64', []))
        elif system in ['PlayStation', 'PS1', 'PSX']:
            candidates.extend(available_roms.get('PS', []))
        elif system in ['Arcade', 'ARCADE', 'MAME']:
            candidates.extend(available_roms.get('ARCADE', []))
        elif system in ['Neo Geo', 'NEOGEO']:
            candidates.extend(available_roms.get('NEOGEO', []))
        elif system in ['Genesis', 'Mega Drive', 'Sega Genesis']:
            candidates.extend(available_roms.get('MD', []))
        elif system in ['NES', 'Nintendo Entertainment System']:
            candidates.extend(available_roms.get('FC', []))
        elif system in ['SNES', 'Super Nintendo']:
            candidates.extend(available_roms.get('SFC', []))
        elif system in ['Game Boy', 'GB']:
            candidates.extend(available_roms.get('GB', []))
        elif system in ['Game Boy Color', 'GBC']:
            candidates.extend(available_roms.get('GBC', []))
        elif system in ['Game Boy Advance', 'GBA']:
            candidates.extend(available_roms.get('GBA', []))
        else:
            # For other systems, ONLY use the mapped folder name
            candidates.extend(available_roms.get(muos_system, []))
        
        if not candidates:
            return None

        # Try different matching strategies for each variant
        best_match = None
        best_score = 0

        for variant_name in game_variants:
            # Normalize game name for matching
            game_normalized = self.normalize_name(variant_name)

            for rom_path in candidates:
                # Double-check that this ROM is actually from the right system
                # This prevents cross-system matches
                detected_system = self.detect_system_from_path(rom_path)
                if detected_system != muos_system and detected_system != 'UNKNOWN':
                    # Skip ROMs that are clearly from a different system
                    continue

                rom_normalized = self.normalize_name(rom_path.stem)

                # Calculate match score
                score = 0

                # Exact match
                if game_normalized == rom_normalized:
                    score = 1.0
                # Contains match
                elif game_normalized in rom_normalized:
                    score = 0.8
                elif rom_normalized in game_normalized:
                    score = 0.7
                # Word-based match
                else:
                    game_words = set(game_normalized.split())
                    rom_words = set(rom_normalized.split())
                    if game_words and rom_words:
                        common_words = game_words & rom_words
                        if common_words:
                            # Score based on percentage of matching words
                            score = len(common_words) / max(len(game_words), len(rom_words))

                if score > best_score:
                    best_score = score
                    best_match = rom_path

                # If we found an exact match, stop looking
                if score >= 1.0:
                    return best_match

        # Only return if we have a reasonable match
        if best_match and best_score >= 0.5:
            return best_match

        return None
    
    def normalize_name(self, name: str) -> str:
        """Normalize name for matching"""
        # Remove common tags and clean up
        name = re.sub(r'\[.*?\]', '', name)  # Remove [tags]
        name = re.sub(r'\(.*?\)', '', name)  # Remove (tags)
        name = re.sub(r'\{.*?\}', '', name)  # Remove {tags}
        
        # Remove special characters
        name = name.replace(':', '').replace('-', ' ').replace('_', ' ')
        name = name.replace("'", '').replace('&', 'and').replace('!', '')
        name = name.replace('.', '').replace(',', '')
        
        # Remove common words
        stop_words = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for'}
        words = name.lower().split()
        words = [w for w in words if w not in stop_words]
        
        return ' '.join(words).strip()

    def download_rom_from_myrient(self, game_name: str, system: str, system_dir: Path) -> Optional[Path]:
        """Try to download missing ROM from Myrient"""
        if system not in self.myrient_urls:
            print(f"  No Myrient URL configured for {system}")
            return None

        base_url = self.myrient_urls[system]

        # For N64, handle special cases in game names
        if system == 'Nintendo 64':
            # Clean up game names for N64
            search_name = game_name.replace('Star Fox 64', 'Star Fox 64')
            search_name = search_name.replace('SOTN', 'Symphony of the Night')
        else:
            search_name = game_name

        # Try different naming patterns - N64 uses specific format
        if system == 'Nintendo 64':
            search_patterns = [
                f"{search_name} (USA).zip",
                f"{search_name} (USA) (Rev 1).zip",
                f"{search_name} (USA) (Rev 2).zip",
                f"{search_name} (Europe).zip",
                f"{search_name} (Japan).zip",
                f"{search_name} (World).zip",
            ]
        else:
            search_patterns = [
                f"{search_name} (USA)",
                f"{search_name} (World)",
                f"{search_name} (Europe)",
                f"{search_name} (USA, Europe)",
                search_name,
            ]
            # Add extensions for non-N64
            extensions = {
                'NES': ['.zip', '.nes'],
                'SNES': ['.zip', '.sfc', '.smc'],
                'GB': ['.zip', '.gb'],
                'GBC': ['.zip', '.gbc'],
                'GBA': ['.zip', '.gba'],
                'Genesis': ['.zip', '.md', '.bin'],
                'PlayStation': ['.chd', '.cue'],
                'Dreamcast': ['.chd', '.gdi'],
                'Arcade': ['.zip'],
            }.get(system, ['.zip'])

            # Create full patterns with extensions
            full_patterns = []
            for pattern in search_patterns:
                for ext in extensions:
                    full_patterns.append(f"{pattern}{ext}")
            search_patterns = full_patterns

        print(f"  Searching Myrient for {game_name}...")

        for pattern in search_patterns:
            # URL encode the filename properly
            rom_url = base_url + quote(pattern).replace('%28', '(').replace('%29', ')')

            try:
                # Try to download directly without HEAD request first
                print(f"  Trying: {pattern}")
                response = requests.get(rom_url, stream=True, timeout=10, allow_redirects=True)

                if response.status_code == 200:
                    # File exists, download it
                    dest_file = system_dir / pattern

                    if dest_file.exists():
                        print(f"  Already exists: {pattern}")
                        return dest_file

                    total_size = int(response.headers.get('content-length', 0))

                    with open(dest_file, 'wb') as f:
                        downloaded = 0
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)

                    print(f"  Downloaded: {pattern}")
                    return dest_file

            except Exception as e:
                continue

        return None

    def process_game(self, game: Dict, available_roms: Dict[str, List[Path]],
                     roms_dir: Path, download_media: bool, copy_roms: bool):
        """Process a single game"""
        game_name = game['name']
        system = game['system']
        rom_path = game.get('rom_path', '')

        # Get muOS system folder
        muos_system = SYSTEM_TO_MUOS_FOLDER.get(system, system)
        system_dir = roms_dir / muos_system
        system_dir.mkdir(exist_ok=True)

        # First check if a specific ROM path/URL was provided
        if rom_path:
            rom_file = self.handle_specific_rom_path(rom_path, game_name, system_dir)
            if rom_file:
                print(f"✓ {game_name} ({system}) -> {rom_file.name} (from provided path)")
                self.stats['found'] += 1
                if download_media:
                    self.download_game_media(rom_file, game_name, system, system_dir)
                return
            else:
                print(f"✗ {game_name} ({system}) - Failed to get ROM from provided path: {rom_path}")

        # Find ROM file normally (including in output directory)
        rom_file = self.find_rom_for_game(game_name, system, available_roms)

        # If ROM is already in output directory, we're done
        if rom_file and rom_file.parent == system_dir:
            print(f"✓ {game_name} ({system}) -> Already in output")
            self.stats['found'] += 1
            # Still try to download media if needed
            if download_media:
                self.download_game_media(rom_file, game_name, system, system_dir)
            return

        if not rom_file:
            # Try to download from Myrient if enabled
            if self.download_missing:
                rom_file = self.download_rom_from_myrient(game_name, system, system_dir)
                if rom_file:
                    print(f"✓ {game_name} ({system}) -> Downloaded from Myrient")
                    self.stats['found'] += 1
                else:
                    print(f"✗ {game_name} ({system}) - ROM not found locally or on Myrient")
                    self.stats['missing'] += 1
            else:
                print(f"✗ {game_name} ({system}) - ROM not found")
                self.stats['missing'] += 1
            
            if not rom_file:
                return
        else:
            print(f"✓ {game_name} ({system}) -> {rom_file.name}")
            self.stats['found'] += 1
            
            # Copy/link ROM if requested
            if copy_roms:
                dest_rom = system_dir / rom_file.name
                if not dest_rom.exists():
                    if rom_file.stat().st_size < 1_000_000_000:  # Copy if <1GB
                        shutil.copy2(rom_file, dest_rom)
                    else:  # Symlink large files
                        dest_rom.symlink_to(rom_file)
        
        # Try to get game info from ScreenScraper
        if download_media and rom_file:
            self.download_game_media(rom_file, game_name, system, system_dir)
    
    def handle_specific_rom_path(self, rom_path: str, game_name: str, system_dir: Path) -> Optional[Path]:
        """Handle a specific ROM path or URL provided in CSV
        Returns Path to the ROM file in the system directory, or None if failed"""

        try:
            # Check if it's a URL
            if rom_path.startswith(('http://', 'https://')):
                print(f"  Downloading from URL: {rom_path}")

                # Extract filename from URL or use game name
                from urllib.parse import urlparse, unquote
                url_path = urlparse(rom_path).path
                if url_path:
                    filename = unquote(url_path.split('/')[-1])
                    if not filename or not any(filename.endswith(ext) for ext in ['.zip', '.chd', '.7z', '.rar', '.z64', '.n64', '.iso', '.cue', '.gba', '.gb', '.gbc', '.nes', '.sfc', '.smc', '.md', '.smd', '.gg', '.sms']):
                        # Generate filename from game name if URL doesn't have a good one
                        filename = f"{game_name}.zip"
                else:
                    filename = f"{game_name}.zip"

                dest_file = system_dir / filename

                # Download the file
                response = requests.get(rom_path, stream=True, timeout=30)
                if response.status_code == 200:
                    total_size = int(response.headers.get('content-length', 0))

                    with open(dest_file, 'wb') as f:
                        downloaded = 0
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    percent = (downloaded / total_size) * 100
                                    print(f"\r  Downloading: {percent:.1f}% ({downloaded}/{total_size} bytes)", end='', flush=True)

                    print()  # New line after progress
                    return dest_file
                else:
                    print(f"  Failed to download: HTTP {response.status_code}")
                    if response.status_code == 404:
                        print(f"    File not found at URL")
                    return None

            else:
                # It's a local file path
                source_path = Path(rom_path).expanduser()

                if not source_path.exists():
                    print(f"  File not found: {source_path}")
                    return None

                if not source_path.is_file():
                    print(f"  Path is not a file: {source_path}")
                    return None

                # Copy to system directory
                dest_file = system_dir / source_path.name

                if dest_file.exists():
                    print(f"  Already exists: {dest_file.name}")
                    return dest_file

                print(f"  Copying from: {source_path}")
                shutil.copy2(source_path, dest_file)
                return dest_file

        except requests.exceptions.RequestException as e:
            print(f"  Error downloading: {e}")
        except Exception as e:
            print(f"  Error handling ROM path: {e}")

        return None

    def download_game_media(self, rom_file: Path, game_name: str,
                           system: str, system_dir: Path):
        """Skip per-game media download - we'll scrape per-system instead"""
        # Media will be scraped in batch per system using Skyscraper
        return
    
    def download_rom_from_myrient(self, game_name: str, system: str, system_dir: Path) -> Optional[Path]:
        """Try to download missing ROM from Myrient by browsing directory"""
        if system not in self.myrient_urls:
            print(f"  No Myrient URL configured for {system}")
            return None
        
        base_url = self.myrient_urls[system]
        print(f"  Searching Myrient for {game_name} at {base_url}")
        
        try:
            # Fetch the directory listing
            response = requests.get(base_url, timeout=15)
            if response.status_code != 200:
                print(f"  Could not access Myrient directory: {response.status_code}")
                return None
            
            # Parse HTML to find all ROM links
            html_content = response.text
            
            # Simple HTML parsing to find links
            # Look for href="..." patterns that end in .zip, .chd, etc.
            import re
            link_pattern = r'href="([^"]+\.(?:zip|chd|7z|rar))"'
            all_links = re.findall(link_pattern, html_content, re.IGNORECASE)
            
            if not all_links:
                print(f"  No ROM files found in directory listing")
                return None
            
            print(f"  Found {len(all_links)} ROM files in directory")
            
            # Normalize game name for matching
            game_normalized = self.normalize_name(game_name).lower()
            game_words = set(game_normalized.split())
            
            # Find best matching ROM
            best_match = None
            best_score = 0
            
            for link in all_links:
                # Decode URL encoding
                from urllib.parse import unquote
                link_decoded = unquote(link)
                
                # Get just the filename
                filename = link_decoded.split('/')[-1]
                filename_no_ext = filename.rsplit('.', 1)[0]
                
                # Normalize filename for comparison
                filename_normalized = self.normalize_name(filename_no_ext).lower()
                filename_words = set(filename_normalized.split())
                
                # Calculate match score
                score = 0
                
                # Exact match (without region/version tags)
                if game_normalized == filename_normalized:
                    score = 1.0
                # Game name is contained in filename
                elif game_normalized in filename_normalized:
                    score = 0.9
                # All game words are in filename
                elif game_words and game_words.issubset(filename_words):
                    score = 0.8
                # Partial word match
                elif game_words and filename_words:
                    common_words = game_words & filename_words
                    if len(common_words) >= len(game_words) * 0.6:  # 60% word match
                        score = len(common_words) / len(game_words) * 0.7
                
                # Prefer USA region
                if '(USA)' in filename:
                    score *= 1.2
                elif '(World)' in filename:
                    score *= 1.1
                elif '(Europe)' in filename:
                    score *= 1.05
                
                if score > best_score:
                    best_score = score
                    best_match = link
            
            # Download best match if score is good enough
            if best_match and best_score >= 0.6:
                from urllib.parse import unquote
                filename = unquote(best_match.split('/')[-1])
                
                # Construct full URL
                if best_match.startswith('http'):
                    rom_url = best_match
                else:
                    rom_url = base_url + best_match
                
                dest_file = system_dir / filename
                
                if dest_file.exists():
                    print(f"  Already exists: {filename}")
                    return dest_file
                
                print(f"  Best match: {filename} (score: {best_score:.2f})")
                print(f"  Downloading from: {rom_url}")
                
                # Download the file
                download_response = requests.get(rom_url, stream=True, timeout=30)
                if download_response.status_code == 200:
                    total_size = int(download_response.headers.get('content-length', 0))
                    
                    with open(dest_file, 'wb') as f:
                        downloaded = 0
                        for chunk in download_response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    percent = (downloaded / total_size) * 100
                                    print(f"\r  Downloading: {percent:.1f}% ({downloaded}/{total_size} bytes)", end='', flush=True)
                    
                    print(f"\n  ✓ Downloaded: {filename}")
                    self.stats['roms_downloaded'] += 1
                    return dest_file
                else:
                    print(f"  Failed to download: {download_response.status_code}")
            else:
                if best_match:
                    print(f"  Best match '{unquote(best_match)}' score too low: {best_score:.2f}")
                else:
                    print(f"  No matching ROM found for '{game_name}'")
                    
        except requests.exceptions.RequestException as e:
            print(f"  Error accessing Myrient: {e}")
        except Exception as e:
            print(f"  Unexpected error: {e}")
            import traceback
            traceback.print_exc()

        return None

    def copy_bios_files(self):
        """Copy BIOS files if found"""
        bios_dir = self.output_dir / 'BIOS'
        bios_dir.mkdir(exist_ok=True)

        # muOS BIOS requirements (only the essential ones)
        bios_files = {
            # PlayStation - muOS needs these specific files
            'bios_CD_U.bin': 'PS1 USA BIOS',
            'bios_CD_E.bin': 'PS1 Europe BIOS',
            'bios_CD_J.bin': 'PS1 Japan BIOS',
            'PSXONPSP660.bin': 'PS1 BIOS for PSXONPSP',

            # PC Engine CD
            'syscard3.pce': 'PC Engine CD BIOS',

            # Sega systems
            'bios_MD.bin': 'Mega Drive BIOS',
            'bios.gg': 'Game Gear BIOS',
            'bios_E.sms': 'Master System Europe BIOS',
            'bios_U.sms': 'Master System USA BIOS',
            'bios_J.sms': 'Master System Japan BIOS',

            # Nintendo handhelds (for enhanced features)
            'gb_bios.bin': 'Game Boy BIOS',
            'gbc_bios.bin': 'Game Boy Color BIOS',
            'gba_bios.bin': 'Game Boy Advance BIOS',

            # Neo Geo
            'neogeo.zip': 'Neo Geo BIOS',

            # Dreamcast
            'dc_boot.bin': 'Dreamcast boot BIOS',
            'dc_flash.bin': 'Dreamcast flash BIOS',

            # Famicom Disk System
            'disksys.rom': 'Famicom Disk System BIOS'
        }

        copied_count = 0

        # Search recursively but with depth limit to avoid slowness
        for rom_dir in self.rom_dirs:
            print(f"Searching for BIOS files in {rom_dir}...")

            # Use rglob to search recursively but limit depth
            for bios_file, description in bios_files.items():
                # Search for this specific BIOS file
                search_pattern = f"**/{bios_file}"
                matches = list(rom_dir.glob(search_pattern))

                # Also check common BIOS subdirectories
                for bios_subdir in ['BIOS', 'bios', 'Bios']:
                    pattern = f"**/{bios_subdir}/{bios_file}"
                    matches.extend(rom_dir.glob(pattern))

                if matches:
                    source = matches[0]  # Use first match
                    dest = bios_dir / bios_file
                    if not dest.exists():
                        shutil.copy2(source, dest)
                        print(f"  ✓ Copied {description}: {bios_file}")
                        copied_count += 1
                    else:
                        print(f"  → {description} already exists: {bios_file}")

        if copied_count > 0:
            print(f"\nCopied {copied_count} BIOS files to {bios_dir}")
        else:
            print(f"\nNo new BIOS files found to copy")
    
    def print_summary(self):
        """Print organization summary"""
        print("\n" + "=" * 60)
        print("Summary:")
        print(f"  ROMs found locally: {self.stats['found'] - self.stats['roms_downloaded']}")
        print(f"  ROMs downloaded from Myrient: {self.stats['roms_downloaded']}")
        print(f"  Total ROMs ready: {self.stats['found']}")
        print(f"  ROMs still missing: {self.stats['missing']}")
        print(f"  Games identified via ScreenScraper: {self.stats['identified']}")
        print(f"  Media files downloaded: {self.stats['media_downloaded']}")
        print(f"\nOutput directory: {self.output_dir}")
        print("\nTo use with muOS:")
        print(f"1. Copy contents of {self.output_dir} to your SD card")
        print("2. Merge with existing muOS folders")
        print("=" * 60)
    
    def save_report(self, games_list: List[Dict]):
        """Save detailed report"""
        report_path = self.output_dir / 'organization_report.txt'
        
        with open(report_path, 'w') as f:
            f.write("muOS ROM Organization Report\n")
            f.write("=" * 60 + "\n\n")
            
            f.write(f"Total games in list: {len(games_list)}\n")
            f.write(f"ROMs found: {self.stats['found']}\n")
            f.write(f"ROMs missing: {self.stats['missing']}\n")
            f.write(f"Games identified: {self.stats['identified']}\n")
            f.write(f"Media downloaded: {self.stats['media_downloaded']}\n\n")
            
            f.write("Missing ROMs:\n")
            f.write("-" * 40 + "\n")

            # Scan once for efficiency
            available_roms = self.scan_rom_directories()

            for game in games_list:
                rom_file = self.find_rom_for_game(
                    game['name'],
                    game['system'],
                    available_roms
                )
                if not rom_file:
                    f.write(f"{game['name']} ({game['system']})\n")

def main():
    parser = argparse.ArgumentParser(
        description='Universal muOS ROM Organizer with ScreenScraper support'
    )
    parser.add_argument('csv_file', help='CSV file with game list')
    parser.add_argument('--rom-dirs', nargs='+', required=True,
                       help='ROM directories to search (can specify multiple)')
    parser.add_argument('--output', '-o', default='muOS_Complete',
                       help='Output directory for muOS structure')
    parser.add_argument('--ss-user', help='ScreenScraper username')
    parser.add_argument('--ss-pass', help='ScreenScraper password')
    parser.add_argument('--no-media', action='store_true',
                       help='Skip downloading box art and screenshots')
    parser.add_argument('--no-copy', action='store_true',
                       help='Don\'t copy ROMs, just create structure')
    parser.add_argument('--download-missing', action='store_true',
                       help='Download missing ROMs from Myrient')
    
    args = parser.parse_args()
    
    print("muOS Universal ROM Organizer")
    print("Using ScreenScraper.fr database")
    if args.download_missing:
        print("Missing ROMs will be downloaded from Myrient")
    print("-" * 60)
    
    if not args.ss_user:
        print("\nNote: No ScreenScraper credentials provided.")
        print("For better identification and media download, register free at:")
        print("https://www.screenscraper.fr")
        print("Then use --ss-user and --ss-pass options\n")
    
    # Run organizer
    organizer = MuOSOrganizer(
        args.csv_file,
        args.rom_dirs,
        args.output,
        args.ss_user,
        args.ss_pass,
        args.download_missing
    )
    
    organizer.organize(
        download_media=not args.no_media,
        copy_roms=not args.no_copy
    )

if __name__ == '__main__':
    main()
