#!/usr/bin/env python3
"""
generate_uk_guide.py
--------------------
Automated generator for TVStream Live's lightweight public TV guide feed.
Fetches public UK XMLTV feeds (Freeview and OpenEPG for sports channels),
filters down to the channels used by Master TV Guide, AppHub, NOW TV, and Max,
trims to a rolling 36-hour window, and outputs a compact JSON file
suitable for fast Apple TV loading.

Dependencies: Standard Python library only (urllib, gzip, xml.etree, json, datetime).
"""

import sys
import os
import json
import gzip
import io
import urllib.request
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET

# Source XMLTV feeds
FEEDS = [
    ("Freeview", "https://raw.githubusercontent.com/dp247/Freeview-EPG/master/epg.xml"),
    ("OpenEPG", "https://www.open-epg.com/files/unitedkingdom2.xml")
]

# Simulcast UHD channels absent from both XMLTV feeds above. epg.pw exposes
# these schedules through a public, unauthenticated per-channel JSON API.
# IDs are epg.pw channel IDs, not NOW TV service_key values.
EPG_PW_CHANNELS = {
    "sky sports uhd1": 471315,
    "sky sports uhd2": 471314,
    "tnt sports ultimate": 400476,
    # Premier Sports 1/2 HD — no public XMLTV feed carries them; epg.pw IDs
    # verified 2026-09-11 (current-day listings returned for both).
    "premier sports 1": 219100,
    "premier sports 2": 219104,
    # Sky One (relaunched Feb 2026): OpenEPG declares it but carries no
    # listings; epg.pw "Sky One HD" verified 2026-09-11.
    "sky one": 524289,
    # Same situation for these Sky Sports channels (declared, empty in
    # OpenEPG). epg.pw lists them as "SkySp … HD"; IDs verified 2026-09-11
    # against the week's real schedule (Solheim Cup, US Open, NFL, St Leger).
    "sky sports golf": 12022,
    "sky sports tennis": 212145,
    "sky sports action": 12024,
    "sky sports racing": 12200,
}

# Output filename
OUTPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "uk_guide.json"

# Canonical channels and their search aliases
TARGET_CHANNELS = {
    # Freeview terrestrial
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

    # Ireland — Saorview
    "rte one": ["rteone", "rté one", "rte one"],
    "rte two": ["rte2", "rté2", "rte two"],
    "rte news": ["rtenews", "rté news"],
    "virgin media one": ["virginmediaone", "virgin media one"],
    "virgin media two": ["virginmediatwo", "virgin media two"],
    "virgin media three": ["virginmediathree", "virgin media three"],
    "tg4": ["tg4"],

    # TNT Sports (Max / discovery+ / NOW TV)
    "tnt sports 1": ["tnt sports 1", "tnt sport 1", "bt sport 1", "bt sports 1"],
    "tnt sports 2": ["tnt sports 2", "tnt sport 2", "bt sport 2", "bt sports 2"],
    "tnt sports 3": ["tnt sports 3", "tnt sport 3", "bt sport 3", "bt sports 3"],
    "tnt sports 4": ["tnt sports 4", "tnt sport 4", "bt sport 4", "bt sports 4"],
    "tnt sports ultimate": ["tnt sports ultimate", "tnt sport ultimate", "tnt sports uhd", "tnt sport uhd", "tnt sports uhd 4k"],

    # Sky Sports (NOW TV)
    "sky sports main event": ["sky sports main event", "sky sport main event"],
    "sky sports premier league": ["sky sports premier league", "sky sport premier league", "sky sports pl", "sky sport pl"],
    "sky sports football": ["sky sports football", "sky sport football"],
    "sky sports cricket": ["sky sports cricket", "sky sport cricket"],
    "sky sports golf": ["sky sports golf", "sky sport golf"],
    "sky sports f1": ["sky sports f1", "sky sport f1", "sky sports formula 1"],
    "sky sports tennis": ["sky sports tennis", "sky sport tennis"],
    "sky sports action": ["sky sports action", "sky sport action"],
    "sky sports+": ["sky sports +", "sky sports+", "sky sport +", "sky sport plus", "sky sports plus"],
    "sky sports racing": ["sky sports racing", "sky sport racing", "at the races"],
    "sky sports mix": ["sky sports mix", "sky sport mix"],
    "sky sports uhd1": ["sky sports uhd1", "sky sports uhd 1", "sky sport uhd1", "sky sport uhd 1"],
    "sky sports uhd2": ["sky sports uhd2", "sky sports uhd 2", "sky sport uhd2", "sky sport uhd 2"],

    # Premier Sports
    "premier sports 1": ["premier sports 1", "premier sport 1"],
    "premier sports 2": ["premier sports 2", "premier sport 2"],

    # NOW TV entertainment / news / cinema / kids (keys = NowTVChannel.name
    # lowercased, which is how ExternalEPGService.nowAndNext(name:) looks
    # them up). Covered by OpenEPG's unitedkingdom2.xml (display names carry
    # a ".uk" suffix and an HD twin); Freeview only has Sky Arts / Sky News.
    # Verified 2026-09-11 that each alias matches only its own channel.
    "sky sports news": ["sky sports news"],
    "sky one": ["sky one"],
    "sky atlantic": ["sky atlantic"],
    "sky witness": ["sky witness"],
    "u&alibi": ["u&alibi"],
    "u&gold": ["u&gold"],
    "sky comedy": ["sky comedy"],
    "comedy central": ["comedy central uk", "comedy central hd"],
    "mtv": ["mtv hd", "mtv.uk"],
    "sky docs": ["sky documentaries", "sky docs"],
    "sky crime": ["sky crime"],
    "sky nature": ["sky nature"],
    "sky history": ["sky history"],
    "sky sci-fi": ["sky sci-fi", "sky scifi"],
    "sky arts": ["sky arts"],
    "sky cinema premiere": ["sky cinema premiere"],
    "sky cinema action": ["sky cinema action"],
    "sky cinema family": ["sky cinema family"],
    "sky cinema comedy": ["sky cinema comedy"],
    "sky cinema sci-fi/horror": ["sky cinema sci fi & horror", "sky cinema sci-fi & horror", "sky cinema sci-fi/horror"],
    "sky cinema thriller": ["sky cinema thriller"],
    "sky cinema greats": ["sky cinema greats"],
    "sky cinema drama": ["sky cinema drama"],
    "sky news": ["sky news"],
    "sky kids": ["sky kids"],
    "cartoon network": ["cartoon network"],
    "boomerang": ["boomerang"],
    "nickelodeon": ["nickelodeon"],
    "nicktoons": ["nicktoons"],
    "nick jr": ["nick jr"],
    "cartoonito": ["cartoonito"],
    # Not in any public XMLTV feed found so far: Sky Cinema Bridget Jones /
    # Minions (pop-up channels). Premier Sports 1/2 come from epg.pw below.
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
    except Exception:
        return None

def fetch_feed(name, url):
    print(f"Fetching XMLTV feed '{name}' from: {url}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TVStreamLive-GuideBuilder/1.0 (Macintosh; AppleTV)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            compressed_data = response.read()
        try:
            return gzip.decompress(compressed_data)
        except Exception:
            return compressed_data
    except Exception as e:
        print(f"Warning: Error fetching feed '{name}': {e}", file=sys.stderr)
        return None


def fetch_epg_pw_channel(canonical_name, channel_id, window_start, window_end):
    """Fetch a public epg.pw schedule and normalize it to guide programmes."""
    url = f"https://epg.pw/api/epg.json?channel_id={channel_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "TVStreamLive-GuideBuilder/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            items = (json.loads(response.read()).get("epg_list") or [])
    except Exception as exc:
        print(f"Warning: Error fetching epg.pw '{canonical_name}': {exc}", file=sys.stderr)
        return []

    programmes = []
    for index, item in enumerate(items):
        raw_start = item.get("start_date")
        if not raw_start:
            continue
        try:
            start_dt = datetime.fromisoformat(raw_start.replace("Z", "+00:00")).astimezone(timezone.utc)
            if index + 1 < len(items) and items[index + 1].get("start_date"):
                raw_stop = items[index + 1]["start_date"]
                stop_dt = datetime.fromisoformat(raw_stop.replace("Z", "+00:00")).astimezone(timezone.utc)
            else:
                stop_dt = start_dt + timedelta(hours=4)
        except (TypeError, ValueError):
            continue
        if stop_dt < window_start or start_dt > window_end:
            continue
        programmes.append({
            "title": item.get("title") or "Unknown",
            "desc": item.get("desc") or "",
            "start": int(start_dt.timestamp()),
            "stop": int(stop_dt.timestamp()),
        })
    return programmes

def main():
    now_utc = datetime.now(timezone.utc)
    window_start = now_utc - timedelta(hours=2)
    window_end = now_utc + timedelta(hours=36)

    channels_data = {k: [] for k in TARGET_CHANNELS.keys()}
    total_programmes = 0

    for feed_name, feed_url in FEEDS:
        raw_xml = fetch_feed(feed_name, feed_url)
        if not raw_xml:
            continue

        print(f"Parsing '{feed_name}' XML ({len(raw_xml):,} bytes)...")
        # Every channel element that matches a canonical name is collected
        # (a feed usually carries an HD and an SD twin, and sometimes a
        # regional or +1 variant); programmes are gathered per channel id
        # and one variant is chosen at the end of the feed using the same
        # preference as before (an HD/London variant beats the first match)
        # but only among variants that actually carry listings. Choosing the
        # HD id up front silently produced empty channels when a feed
        # declared the HD twin but only populated the SD one (OpenEPG's
        # Nickelodeon, 2026-09-11); choosing purely by listing count would
        # pick siblings such as "E4 Extra" / "E4+1" over "E4".
        channel_id_to_canonical = {}
        display_name_for_id = {}
        declaration_index = {}
        feed_channel_progs = {}   # canonical -> {ch_id: [programmes]}

        try:
            tree = ET.iterparse(io.BytesIO(raw_xml), events=("end",))
            feed_programmes = 0

            for event, elem in tree:
                if elem.tag == "channel":
                    ch_id = elem.attrib.get("id", "")
                    display_name = (elem.findtext("display-name") or "").lower()

                    for canonical, aliases in TARGET_CHANNELS.items():
                        if any(a in display_name for a in aliases):
                            channel_id_to_canonical[ch_id] = canonical
                            display_name_for_id[ch_id] = display_name
                            declaration_index[ch_id] = len(declaration_index)
                            feed_channel_progs.setdefault(canonical, {}).setdefault(ch_id, [])
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
                                feed_channel_progs[canonical_name][ch_id].append(prog)

                    elem.clear()

            for canonical_name, by_id in feed_channel_progs.items():
                populated = [cid for cid in by_id if by_id[cid]]
                if not populated:
                    continue
                best_id = max(
                    populated,
                    key=lambda cid: (
                        "hd" in display_name_for_id.get(cid, "")
                        or "london" in display_name_for_id.get(cid, ""),
                        -declaration_index[cid],
                    ),
                )
                channels_data[canonical_name].extend(by_id[best_id])
                feed_programmes += len(by_id[best_id])

            print(f"Parsed {feed_programmes} programmes from '{feed_name}'.")
            total_programmes += feed_programmes

        except Exception as e:
            print(f"Warning: Error parsing '{feed_name}': {e}", file=sys.stderr)

    for canonical_name, channel_id in EPG_PW_CHANNELS.items():
        programmes = fetch_epg_pw_channel(canonical_name, channel_id, window_start, window_end)
        if programmes:
            # epg.pw is authoritative for these simulcast UHD services. Replace
            # any coincidental fuzzy XMLTV match instead of merging two feeds.
            channels_data[canonical_name] = programmes
            total_programmes += len(programmes)
            print(f"Parsed {len(programmes)} programmes from epg.pw for '{canonical_name}'.")

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
    print(f"Generated '{OUTPUT_FILE}': {len(final_channels)} channels, {total_programmes} programmes, {file_size_kb:.1f} KB")

if __name__ == "__main__":
    main()
