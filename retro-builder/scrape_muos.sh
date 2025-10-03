#!/bin/bash
# Complete muOS scraping solution using Skyscraper
# Handles artwork (box/preview) and text metadata generation

SKYSCRAPER="/tmp/ss/Skyscraper"
OUTPUT_DIR="muOS_Complete"
ROMS_DIR="$OUTPUT_DIR/Roms"
MUOS_DIR="$OUTPUT_DIR/MUOS"
ARTWORK_DIR="$MUOS_DIR/info/catalogue"
CACHE_DIR="$HOME/.skyscraper"

# ScreenScraper credentials
SS_USER="rcdriver434"
SS_PASS="1Y7WoTLOBzTBtjRa"

# Platform mappings (muOS folder -> Skyscraper platform)
declare -A PLATFORM_MAP=(
    ["N64"]="n64"
    ["PS"]="psx"
    ["DC"]="dreamcast"
    ["ARCADE"]="arcade"
    ["GB"]="gb"
    ["GBC"]="gbc"
    ["GBA"]="gba"
    ["FC"]="nes"
    ["SFC"]="snes"
    ["MD"]="megadrive"
    ["NEOGEO"]="neogeo"
    ["ATARI"]="atari2600"
    ["PCE"]="pcengine"
    ["MS"]="mastersystem"
    ["GG"]="gamegear"
)

# muOS catalogue names (MUST match folder.json exactly!)
declare -A CATALOGUE_NAMES=(
    ["N64"]="Nintendo 64"
    ["PS"]="Sony PlayStation"
    ["DC"]="SEGA Dreamcast"
    ["ARCADE"]="Arcade"
    ["GB"]="Nintendo Game Boy"
    ["GBC"]="Nintendo Game Boy Color"
    ["GBA"]="Nintendo Game Boy Advance"
    ["FC"]="Nintendo Famicom"
    ["SFC"]="Nintendo Super Famicom"
    ["MD"]="SEGA Mega Drive"
    ["NEOGEO"]="SNK Neo Geo"
    ["ATARI"]="Atari 2600"
    ["PCE"]="PC Engine"
    ["MS"]="SEGA Master System"
    ["GG"]="SEGA Game Gear"
)

echo "======================================"
echo "muOS Complete Scraper for RG40XXV"
echo "======================================"
echo ""

# Check if Skyscraper exists
if [ ! -f "$SKYSCRAPER" ]; then
    echo "Error: Skyscraper not found at $SKYSCRAPER"
    exit 1
fi

# Check if artwork configs exist
if [ ! -f "artwork_box.xml" ] || [ ! -f "artwork_preview.xml" ]; then
    echo "Error: artwork_box.xml or artwork_preview.xml not found"
    echo "Please ensure both artwork configuration files are in the current directory"
    exit 1
fi

# Create Skyscraper config directory if needed
mkdir -p "$CACHE_DIR"

# Function to scrape a system
scrape_system() {
    local muos_system=$1
    local sky_platform=$2
    local catalogue_name=$3
    local system_roms="$ROMS_DIR/$muos_system"

    if [ ! -d "$system_roms" ]; then
        echo "  No ROM directory for $muos_system, skipping..."
        return
    fi

    # Count ROMs
    rom_count=$(find "$system_roms" -maxdepth 1 -type f \( -name "*.zip" -o -name "*.chd" -o -name "*.z64" -o -name "*.n64" -o -name "*.gba" -o -name "*.gb" -o -name "*.gbc" -o -name "*.nes" -o -name "*.sfc" -o -name "*.smc" -o -name "*.md" -o -name "*.smd" -o -name "*.gg" -o -name "*.sms" \) 2>/dev/null | wc -l)

    if [ "$rom_count" -eq 0 ]; then
        echo "  No ROMs found in $system_roms, skipping..."
        return
    fi

    echo ""
    echo "========================================="
    echo "Processing: $catalogue_name"
    echo "System: $muos_system -> Platform: $sky_platform"
    echo "ROMs found: $rom_count"
    echo "========================================="

    # Create muOS catalogue directories
    CATALOGUE_PATH="$ARTWORK_DIR/$catalogue_name"
    mkdir -p "$CATALOGUE_PATH/box"
    mkdir -p "$CATALOGUE_PATH/preview"
    mkdir -p "$CATALOGUE_PATH/text"

    # Step 1: Cache resources from ScreenScraper
    echo ""
    echo "Step 1/3: Caching resources from ScreenScraper..."
    echo "-----------------------------------------"

    $SKYSCRAPER \
        -p "$sky_platform" \
        -s screenscraper \
        -u "$SS_USER:$SS_PASS" \
        -i "$system_roms" \
        --flags unattend,skipped,nobrackets \
        --verbosity 1 \
        --maxfails 3

    # Step 2: Generate box artwork
    echo ""
    echo "Step 2/3: Generating box artwork..."
    echo "-----------------------------------------"

    $SKYSCRAPER \
        -p "$sky_platform" \
        -i "$system_roms" \
        -g "$CATALOGUE_PATH" \
        -o "$CATALOGUE_PATH/box" \
        -a "$(pwd)/artwork_box.xml" \
        -f emulationstation \
        --flags unattend,nobrackets,nosubdirs,videos \
        --verbosity 1

    # Step 3: Generate preview screenshots
    echo ""
    echo "Step 3/3: Generating preview screenshots..."
    echo "-----------------------------------------"

    $SKYSCRAPER \
        -p "$sky_platform" \
        -i "$system_roms" \
        -g "$CATALOGUE_PATH" \
        -o "$CATALOGUE_PATH/preview" \
        -a "$(pwd)/artwork_preview.xml" \
        -f emulationstation \
        --flags unattend,nobrackets,nosubdirs,videos \
        --verbosity 1

    # Step 4: Extract text metadata from gamelist
    echo ""
    echo "Step 4/4: Generating text metadata..."
    echo "-----------------------------------------"

    if [ -f "$CATALOGUE_PATH/gamelist.xml" ]; then
        # Parse the gamelist XML and create text files
        python3 - <<EOF
import xml.etree.ElementTree as ET
import os
from pathlib import Path

gamelist_path = "$CATALOGUE_PATH/gamelist.xml"
text_dir = "$CATALOGUE_PATH/text"
roms_dir = "$system_roms"

try:
    tree = ET.parse(gamelist_path)
    root = tree.getroot()

    text_count = 0
    for game in root.findall('.//game'):
        # Get game path and description
        path_elem = game.find('path')
        desc_elem = game.find('desc')
        name_elem = game.find('name')
        developer_elem = game.find('developer')
        publisher_elem = game.find('publisher')
        genre_elem = game.find('genre')
        releasedate_elem = game.find('releasedate')
        players_elem = game.find('players')
        rating_elem = game.find('rating')

        if path_elem is not None and path_elem.text:
            # Extract filename without extension
            rom_filename = os.path.basename(path_elem.text)
            text_filename = os.path.splitext(rom_filename)[0] + '.txt'
            text_path = os.path.join(text_dir, text_filename)

            # Build text content
            content_lines = []

            # Add game name as header if available
            if name_elem is not None and name_elem.text:
                content_lines.append(name_elem.text)
                content_lines.append("=" * len(name_elem.text))
                content_lines.append("")

            # Add metadata if available
            metadata = []
            if developer_elem is not None and developer_elem.text:
                metadata.append(f"Developer: {developer_elem.text}")
            if publisher_elem is not None and publisher_elem.text:
                metadata.append(f"Publisher: {publisher_elem.text}")
            if genre_elem is not None and genre_elem.text:
                metadata.append(f"Genre: {genre_elem.text}")
            if releasedate_elem is not None and releasedate_elem.text:
                # Format date if it's in YYYYMMDD format
                date_str = releasedate_elem.text[:4]  # Just year
                metadata.append(f"Year: {date_str}")
            if players_elem is not None and players_elem.text:
                metadata.append(f"Players: {players_elem.text}")
            if rating_elem is not None and rating_elem.text:
                rating = float(rating_elem.text)
                stars = "★" * int(rating * 5) + "☆" * (5 - int(rating * 5))
                metadata.append(f"Rating: {stars}")

            if metadata:
                content_lines.extend(metadata)
                content_lines.append("")

            # Add description
            if desc_elem is not None and desc_elem.text:
                content_lines.append("Description:")
                content_lines.append("-" * 12)
                content_lines.append(desc_elem.text.strip())
            elif not metadata:
                # If no description and no metadata, add a placeholder
                content_lines.append("No description available.")

            # Write text file
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(content_lines))

            text_count += 1

    print(f"  Generated {text_count} text files")

except Exception as e:
    print(f"  Warning: Could not process gamelist.xml: {e}")
EOF
    else
        echo "  No gamelist.xml found, skipping text generation"
    fi

    # Clean up gamelist.xml as it's not needed for muOS
    rm -f "$CATALOGUE_PATH/gamelist.xml"

    echo ""
    echo "✓ Completed $catalogue_name"
}

# Main processing loop
echo ""
echo "Starting scraping process..."
echo ""

for muos_system in "${!PLATFORM_MAP[@]}"; do
    sky_platform="${PLATFORM_MAP[$muos_system]}"
    catalogue_name="${CATALOGUE_NAMES[$muos_system]}"

    if [ -n "$sky_platform" ] && [ -n "$catalogue_name" ]; then
        scrape_system "$muos_system" "$sky_platform" "$catalogue_name"
    fi
done

echo ""
echo "======================================"
echo "Scraping completed!"
echo "======================================"
echo ""
echo "Results saved to:"
echo "  Artwork: $ARTWORK_DIR"
echo ""
echo "Directory structure:"
echo "  $ARTWORK_DIR/"
echo "    └── [System Name]/"
echo "        ├── box/       (box artwork)"
echo "        ├── preview/   (screenshots)"
echo "        └── text/      (game descriptions)"
echo ""
echo "To verify results:"
echo "  find $ARTWORK_DIR -type f | wc -l"
echo ""