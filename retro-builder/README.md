# muOS ROM Organizer

A Python script to automatically organize ROMs and artwork for muOS devices, specifically the Anbernic RG40XXV (although it would be easy to use it for other devices with a few tweaks). I recently gave a friend an Anbernic RG35XX, which I manually configured with MuOS and a curated list of games for her.  The RG35XX was stolen out of a car, and I decided to gift her an RG40XXV as an upgrade/replacement - but I did not want to do all the manual setup and configuration again, particularly getting the images and descriptions. As far as why I wanted this, rather than a premade set of ROMs like "Tiny Best Set Go!" - my friend is new to gaming, and I wanted to give her a very curated list of titles she'd enjoy, rather than overwhelming her with a device that had 5,000 ROMs already loaded.

This was heavily written by LLMs, so the code is a bit overly complex, but this did work great for my needs to set her up with a system that had a small set of carefully selected games on MuOS (all with correct artwork, descriptions, etc).  The really nice thing was that I was able to use my Google Sheet as part of the gift - the original sheet had the columns in the CSV plus a game category, a description, and a brief reason why I chose to include it.  So if I ever wanted to add games, all I'd need to do is update my spreadsheet, save to a CSV, and then rerun the script!

## What It Does

The script takes a CSV list of games and:
- Finds matching ROM files from your local collection
- Downloads missing ROMs from Myrient archives (optional)
- Scrapes game artwork and descriptions using Skyscraper
- Formats artwork and descriptions into the correct resolution, aspect ratio, and structure
- Organizes everything into the muOS directory structure
- Copies required BIOS files

## Requirements

### Dependencies
- Python 3.7+
- [Skyscraper](https://github.com/muldjord/skyscraper) - Command-line game scraper
- PIL/Pillow for image processing: `pip install Pillow`
- requests library: `pip install requests`

### Skyscraper Setup
1. Download from: https://github.com/muldjord/skyscraper/releases
2. Extract the binary to a local path, then update that path in the script
3. Create a free ScreenScraper account: https://www.screenscraper.fr
4. Use credentials with `--ss-user` and `--ss-pass` flags

### muOS
- muOS documentation: https://muos.dev
- Installation guide: https://muos.dev/installation
- Artwork requirements: https://muos.dev/installation/artwork

## CSV Format

Create a CSV file with these columns:
```
System,Game Name,Category,Reason,Description,Notes,rom_path
```

- **System**: Console name (e.g., "Nintendo 64", "PlayStation", "Game Boy Advance")
- **Game Name**: Title of the game as it appears in ROM databases
- **Category**: Optional categorization for your collection
- **Reason**: Optional notes about why this game was selected
- **Description**: Optional game description
- **Notes**: Optional additional notes
- **rom_path**: Optional path to a specific ROM file or URL to download from (this is useful if the name of the game isn't correctly matching to the ROM and you want to manually override)

Example:
```csv
System,Game Name,Category,Reason,Description,Notes,rom_path
Nintendo 64,Super Mario 64,Platformer,Classic,3D platformer,,
PlayStation,Crash Bandicoot,Platformer,Nostalgia,PS1 mascot platformer,,/home/user/roms/crash.chd
Game Boy Advance,Pokemon Ruby,RPG,Popular,Pokemon Gen 3,,https://example.com/pokemon_ruby.zip
```

## Usage

Basic usage:
```bash
python muos-build.py games.csv --rom-dirs ~/ROMs --output muOS_Complete
```

With ScreenScraper credentials and ROM downloading:
```bash
python muos-build.py games.csv \
    --rom-dirs ~/ROMs ~/MoreROMs \
    --ss-user YOUR_USERNAME \
    --ss-pass YOUR_PASSWORD \
    --download-missing \
    --output muOS_Complete
```

### Command-line Options

- `csv_file`: Path to your games CSV file
- `--rom-dirs`: One or more directories containing ROM files
- `--output`: Output directory for muOS structure (default: muOS_Complete)
- `--ss-user`: ScreenScraper username for better scraping
- `--ss-pass`: ScreenScraper password
- `--download-missing`: Download missing ROMs from Myrient
- `--no-media`: Skip artwork scraping
- `--no-copy`: Don't copy ROM files, just create structure

## Output Structure

The script creates a muOS-compatible directory structure:
```
muOS_Complete/
├── Roms/
│   ├── FC/          (NES games)
│   ├── SFC/         (SNES games)
│   ├── PS/          (PlayStation games)
│   └── ...
├── BIOS/            (System BIOS files)
└── MUOS/
    └── info/
        └── catalogue/
            ├── Nintendo NES - Famicom/
            │   ├── box/      (320x240 cover art)
            │   ├── preview/  (515x275 screenshots)
            │   └── text/     (game descriptions)
            └── ...
```

## After Running

1. Copy the contents of the output directory to your muOS SD card
2. Merge with existing muOS folders if updating
3. Boot your device and enjoy

## Troubleshooting

- If Skyscraper times out, it will continue with other systems
- Missing artwork usually means the ROM name doesn't match the database
- Some systems (like MAME/Arcade) require ROMs to be provided locally
- BIOS files are automatically detected and copied from your ROM directories

## Resources

- [muOS Official Site](https://muos.dev)
- [Anbernic RG40XXV](https://anbernic.com/products/rg40xxv)
- [ScreenScraper](https://www.screenscraper.fr)
- [Myrient ROM Archive](https://myrient.erista.me)
- [No-Intro ROM Sets](https://no-intro.org)