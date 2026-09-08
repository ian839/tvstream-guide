#!/usr/bin/env python3
"""
generate_uk_guide.py
--------------------
Automated generator for TVStream Live's lightweight public TV guide feed.
Fetches the public UK Freeview XMLTV feed, filters down to the channels
used by Master TV Guide and AppHub, trims to a rolling 36-hour window,
and outputs a compact JSON file (<100 KB) suitable for fast Apple TV loading.

Dependencies: Standard Python library only (urllib, gzip, xml.etree, json, datetime).
"""

import sys
import os
import json
import gzip
import urllib.request
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET

# Source XMLTV feed (updated every 12 hours with 7 days of UK Freeview schedules)
XMLTV_URL = "https://raw.githubusercontent.com/dp247/Freeview-EPG/master/epg.xml"

# Output filename
OUTPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "uk_guide.json"

# Canonical channels and their search aliases
TARGET_CHANNELS = {
    "bbc one": ["bbc one", "bbc 1", "bbcone"],
    "bbc two": ["bbc two", "bbc 2", "bbctwo"],
    "itv1": ["itv1", "itv 1", "itv hd"],
    "channel 4": ["channel 4", "channel4", "c4 hd"],
    "channel 5": ["channel 5", "channel5", "5 hd"],
    "itv2": ["itv2", "itv 2"],
    "bbc three": ["bbc three", "bbc 3", "bbcthree"],
    "film4": ["film4", "film 4"],
    "bbc four": ["bbc four", "bbc 4", "bbcfour"],
    "itv3": ["itv3", "itv 3"],
    "5usa": ["5usa", "5 usa"],
    "itv4": ["itv4", "itv 4"],
    "e4": ["e4"],
    "5star": ["5star", "5 star"],
    "more4": ["more4", "more 4"],
    "itvbe": ["itvbe", "itv be"],
    "5select": ["5select", "5 select"],
    "4seven": ["4seven", "4 seven"],
    "bbc news": ["bbc news", "bbc news hd"],
    "cbbc": ["cbbc"],
    "cbeebies": ["cbeebies"],
    "bbc scotland": ["bbc scotland"],
    "bbc alba": ["bbc alba"],
    "bbc parliament": ["bbc parliament"],
}

def parse_xmltv_date(raw_str):
    """
    Parses XMLTV date format: 'YYYYMMDDHHMMSS +0000' or 'YYYYMMDDHHMMSS'
    Returns datetime in UTC timezone.
    """
    if not raw_str:
        return None
    cleaned = raw_str.strip()
    try:
        if " " in cleaned:
            dt_part, tz_part = cleaned.split(" ", 1)
            dt = datetime.strptime(dt_part[:14], "%Y%m%d%H%M%S")
            sign = 1 if tz_part.startswith("+") else -1
            hours = int(tz_part[1:3])
            mins = int(tz_part[3:5])
            tz_offset = timezone(sign * timedelta(hours=hours, minutes=mins))
            return dt.replace(tzinfo=tz_offset).astimezone(timezone.utc)
        else:
            return datetime.strptime(cleaned[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except Exception as e:
        return None

def main():
    now_utc = datetime.now(timezone.utc)
    window_start = now_utc - timedelta(hours=2)
    window_end = now_utc + timedelta(hours=36)

    print(f"[{now_utc.isoformat()}] Fetching XMLTV feed from: {XMLTV_URL}")
    req = urllib.request.Request(
        XMLTV_URL,
        headers={"User-Agent": "TVStreamLive-GuideBuilder/1.0"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            compressed_data = response.read()
    except Exception as e:
        print(f"Error fetching XMLTV feed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Downloaded {len(compressed_data):,} bytes. Decompressing...")
    try:
        decompressed_data = gzip.decompress(compressed_data)
    except Exception:
        decompressed_data = compressed_data

    print(f"Parsing XML ({len(decompressed_data):,} bytes)...")

    channels_data = {k: [] for k in TARGET_CHANNELS.keys()}
    channel_id_to_canonical = {}

    try:
        import io
        tree = ET.iterparse(io.BytesIO(decompressed_data), events=("end",))
        programme_count = 0

        for event, elem in tree:
            if elem.tag == "channel":
                ch_id = elem.attrib.get("id", "")
                display_name = (elem.findtext("display-name") or "").lower()

                # Find matching canonical channel
                for canonical, aliases in TARGET_CHANNELS.items():
                    # We prefer national / London feeds if multiple regional variants exist
                    if any(a in display_name for a in aliases):
                        # Avoid clobbering an already matched London/main feed with another regional variant
                        if canonical not in channel_id_to_canonical.values() or "london" in display_name:
                            channel_id_to_canonical[ch_id] = canonical
                        break
                elem.clear()

            elif elem.tag == "programme":
                ch_id = elem.attrib.get("channel", "")
                canonical_name = channel_id_to_canonical.get(ch_id)

                if canonical_name:
                    start_dt = parse_xmltv_date(elem.attrib.get("start"))
                    stop_dt = parse_xmltv_date(elem.attrib.get("stop"))

                    if start_dt and stop_dt and stop_dt >= window_start and start_dt <= window_end:
                        title_el = elem.find("title")
                        desc_el = elem.find("desc")

                        title = title_el.text.strip() if title_el is not None and title_el.text else ""
                        desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""

                        if title:
                            prog = {
                                "title": title,
                                "desc": desc,
                                "start": int(start_dt.timestamp()),
                                "stop": int(stop_dt.timestamp())
                            }
                            channels_data[canonical_name].append(prog)
                            programme_count += 1

                elem.clear()

    except Exception as e:
        print(f"Error during XML parse: {e}", file=sys.stderr)
        sys.exit(1)

    final_channels = {}
    for ch_name, progs in channels_data.items():
        if progs:
            sorted_progs = sorted(progs, key=lambda x: x["start"])
            deduped = []
            seen_starts = set()
            for p in sorted_progs:
                if p["start"] not in seen_starts:
                    seen_starts.add(p["start"])
                    deduped.append(p)
            final_channels[ch_name] = deduped

    payload = {
        "updatedAt": int(now_utc.timestamp()),
        "channels": final_channels
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))

    file_size_kb = os.path.getsize(OUTPUT_FILE) / 1024.0
    print(f"Generated '{OUTPUT_FILE}': {len(final_channels)} channels, {programme_count} programmes, {file_size_kb:.1f} KB")

if __name__ == "__main__":
    main()
