#!/usr/bin/env python3
"""
generate_all_guides.py
----------------------
Automated multi-country TV guide generator for TVStream Live.
Fetches public, actively-maintained EPG feeds for:
  - United Kingdom (uk_guide.json)
  - Ireland (ie_guide.json, also mirrored in uk_guide.json)
  - Australia (au_guide.json)
  - New Zealand (nz_guide.json)
  - United States (us_guide.json)
  - Canada (ca_guide.json)

Trims each to a rolling 36-hour window and outputs compact, optimized JSON (<150 KB each)
for rapid loading on Apple TV devices.

Dependencies: Standard Python 3 library only (urllib, gzip, xml.etree, json, datetime).
"""

import sys
import os
import json
import gzip
import io
import time
import urllib.request
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET

# Feeds
UK_IE_FEED_URL = "https://raw.githubusercontent.com/dp247/Freeview-EPG/master/epg.xml"
AU_FEED_URL = "https://i.mjh.nz/au/Sydney/epg.xml.gz"
NZ_FEED_URL = "https://i.mjh.nz/nz/epg.xml.gz"
US_FEED_URL = "https://raw.githubusercontent.com/acidjesuz/EPGTalk/master/US_guide.xml.gz"
CA_FEED_URL = "https://raw.githubusercontent.com/acidjesuz/EPGTalk/master/guide.xml.gz"

UK_CHANNELS = {
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

IE_CHANNELS = {
    "rte one": ["rteone.ie", "rté one", "rte one", "rteone"],
    "rte two": ["rte2.ie", "rté2", "rte two", "rte2"],
    "rte news": ["rtenews.ie", "rté news", "rtenews"],
    "rte jr": ["rtekidsjr.ie", "rté kidsjr", "rte kids jr", "rte jr"],
    "virgin media one": ["virginmediaone.ie", "virgin media one", "virginmediaone"],
    "virgin media two": ["virginmediatwo.ie", "virgin media two", "virginmediatwo"],
    "virgin media three": ["virginmediathree.ie", "virgin media three", "virginmediathree"],
    "virgin media four": ["virginmediafour.ie", "virgin media four", "virginmediafour"],
    "tg4": ["tg4.ie", "tg4"],
}

AU_CHANNELS = {
    "abc tv": ["mjh-abc-nsw", "abc tv"],
    "abc kids": ["mjh-abc-kids", "abc kids"],
    "abc family": ["mjh-abc-tv-plus", "abc family"],
    "abc news": ["mjh-abc-news", "abc news"],
    "seven": ["mjh-seven-syd", "seven"],
    "7two": ["mjh-7two-syd", "7two"],
    "7mate": ["mjh-7mate-syd", "7mate"],
    "7flix": ["mjh-7flix-syd", "7flix"],
    "channel 9": ["mjh-channel-9-nsw", "channel 9"],
    "9gem": ["mjh-gem-nsw", "9gem"],
    "9go!": ["mjh-go-nsw", "9go"],
    "9life": ["mjh-life-nsw", "9life"],
    "9rush": ["mjh-rush-nsw", "9rush"],
    "10": ["mjh-10-nsw"],
    "10 bold": ["mjh-10bold-nsw", "10 drama"],
    "10 peach": ["mjh-10peach-nsw", "10 comedy"],
    "sbs": ["mjh-sbs-sbst", "sbs"],
    "sbs viceland": ["mjh-sbs-2syd", "sbs2"],
    "sbs food": ["mjh-sbs-3syd", "sbs food"],
    "sbs world movies": ["mjh-sbs-4syd", "sbs world movies"],
    "nitv": ["mjh-sbs-5nsw", "nitv"],
}

NZ_CHANNELS = {
    "tvnz 1": ["mjh-tvnz-1", "tvnz 1"],
    "tvnz 2": ["mjh-tvnz-2", "tvnz 2"],
    "duke": ["mjh-tvnz-duke", "duke"],
    "three": ["mjh-three", "three"],
    "threeplus1": ["mjh-three-plus1", "threeplus1", "three +1"],
    "bravo": ["mjh-bravo", "bravo"],
    "bravo plus 1": ["mjh-bravo-plus1", "bravo plus 1"],
    "sky open": ["mjh-prime", "sky open", "prime"],
    "whakaata maori": ["mjh-maori-tv", "whakaata maori", "maori tv"],
    "eden": ["mjh-eden", "eden"],
    "rush": ["mjh-rush-nz", "rush"],
}

US_CHANNELS = {
    "abc": ["i187.20456.gracenote.com", "us - abc", "abc east"],
    "nbc": ["i188.20452.gracenote.com", "us - nbc", "nbc east"],
    "cbs": ["i189.20454.gracenote.com", "us - cbs", "cbs east"],
    "fox": ["i190.20361.gracenote.com", "us - fox", "fox east"],
    "cnn": ["i202.58646.schedulesdirect.org", "cnn hd", "cnn"],
    "espn": ["i206.32645.schedulesdirect.org", "espn hd", "espn"],
    "espn2": ["i209.12444.schedulesdirect.org", "espn 2 hd", "espn2"],
    "fox sports 1": ["i219.82547.schedulesdirect.org", "fox sports 1 us hd", "fox sports 1"],
    "usa network": ["i242.58452.schedulesdirect.org", "usa network east hd", "usa network"],
    "tnt": ["i245.11164.schedulesdirect.org", "tnt"],
    "tbs": ["i247.67890.schedulesdirect.org", "tbs hd", "tbs"],
    "fx": ["i248.58574.schedulesdirect.org", "fx east hd", "fx"],
    "amc": ["i254.10021.schedulesdirect.org", "amc"],
    "cnbc": ["i355.10139.schedulesdirect.org", "cnbc"],
}

CA_CHANNELS = {
    "cbc": ["i210.46245.schedulesdirect.org", "ca - cbc toronto", "cbc"],
    "ctv": ["i212.44784.schedulesdirect.org", "ca - ctv toronto", "ctv"],
    "citytv": ["i214.10125.schedulesdirect.org", "citytv"],
    "global": ["i234.17406.schedulesdirect.org", "ca - global news montreal", "global"],
    "ctv2": ["i209.10116.schedulesdirect.org", "ca - ctv 2", "ctv 2"],
    "tsn1": ["i400.11182.schedulesdirect.org", "tsn 1"],
    "tsn2": ["i401.18990.schedulesdirect.org", "tsn 2"],
    "sportsnet ontario": ["i405.62111.schedulesdirect.org", "sportsnet ontario"],
    "sportsnet one": ["i409.68858.schedulesdirect.org", "sportsnet one"],
    "sportsnet 360": ["i410.49952.schedulesdirect.org", "sportsnet 360"],
    "ctv news": ["i501.17615.schedulesdirect.org", "ctv news"],
    "cbc news": ["i502.10094.schedulesdirect.org", "ca - cbc news", "cbc news"],
}

def parse_xmltv_date(raw_str):
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

def fetch_feed_data(url, label):
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "TVStreamLive-GuideBuilder/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read()
    except Exception as e:
        print(f"[{label}] Download failed: {e}", file=sys.stderr)
        return None

    try:
        data = gzip.decompress(raw)
    except Exception:
        data = raw

    elapsed = time.time() - t0
    print(f"[{label}] Downloaded {len(raw):,} bytes (decompressed: {len(data):,} bytes) in {elapsed:.2f}s")
    return data

def extract_channels_from_xml(xml_bytes, target_map, window_hours=36):
    now_utc = datetime.now(timezone.utc)
    window_start = now_utc - timedelta(hours=2)
    window_end = now_utc + timedelta(hours=window_hours)

    channel_id_to_key = {}
    channels_data = {k: [] for k in target_map}

    try:
        tree = ET.iterparse(io.BytesIO(xml_bytes), events=("end",))
        for event, elem in tree:
            if elem.tag == "channel":
                cid = elem.attrib.get("id", "")
                dname = (elem.findtext("display-name") or "").strip().lower()
                cid_lower = cid.lower()

                for key, aliases in target_map.items():
                    if any(a == cid_lower or a == dname or a in dname for a in aliases):
                        if key not in channel_id_to_key.values() or "london" in dname:
                            channel_id_to_key[cid] = key
                        break
                elem.clear()

            elif elem.tag == "programme":
                cid = elem.attrib.get("channel", "")
                key = channel_id_to_key.get(cid)
                if key:
                    s_dt = parse_xmltv_date(elem.attrib.get("start"))
                    e_dt = parse_xmltv_date(elem.attrib.get("stop"))
                    if s_dt and e_dt and e_dt >= window_start and s_dt <= window_end:
                        t = elem.findtext("title")
                        d = elem.findtext("desc")
                        if t and t.strip():
                            channels_data[key].append({
                                "title": t.strip(),
                                "desc": d.strip() if d else "",
                                "start": int(s_dt.timestamp()),
                                "stop": int(e_dt.timestamp())
                            })
                elem.clear()

    except Exception as e:
        print(f"XML parse error: {e}", file=sys.stderr)
        return {}

    final_channels = {}
    for key, progs in channels_data.items():
        if progs:
            progs_sorted = sorted(progs, key=lambda x: x["start"])
            deduped = []
            seen = set()
            for p in progs_sorted:
                if p["start"] not in seen:
                    seen.add(p["start"])
                    deduped.append(p)
            final_channels[key] = deduped

    return final_channels

def save_guide_json(output_path, channels_dict):
    now_utc = datetime.now(timezone.utc)
    payload = {
        "updatedAt": int(now_utc.timestamp()),
        "channels": channels_dict
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    size_kb = os.path.getsize(output_path) / 1024.0
    return size_kb

def main():
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(output_dir, exist_ok=True)

    print("==================================================")
    print(f"Starting Multi-Country TV Guide Generation at {datetime.now(timezone.utc).isoformat()}")
    print("==================================================")

    results = []

    # 1. UK & Ireland
    uk_ie_xml = fetch_feed_data(UK_IE_FEED_URL, "UK & Ireland")
    if uk_ie_xml:
        ie_channels = extract_channels_from_xml(uk_ie_xml, IE_CHANNELS)
        ie_path = os.path.join(output_dir, "ie_guide.json")
        ie_size = save_guide_json(ie_path, ie_channels)
        results.append(("Ireland (IE)", "ie_guide.json", len(ie_channels), ie_size))

        combined_uk_ie_targets = {**UK_CHANNELS, **IE_CHANNELS}
        uk_channels = extract_channels_from_xml(uk_ie_xml, combined_uk_ie_targets)
        uk_path = os.path.join(output_dir, "uk_guide.json")
        uk_size = save_guide_json(uk_path, uk_channels)
        results.append(("United Kingdom (UK)", "uk_guide.json", len(uk_channels), uk_size))
    else:
        print("ERROR: Failed to fetch UK & Ireland feed.", file=sys.stderr)

    # 2. Australia (AU)
    au_xml = fetch_feed_data(AU_FEED_URL, "Australia")
    if au_xml:
        au_channels = extract_channels_from_xml(au_xml, AU_CHANNELS)
        au_path = os.path.join(output_dir, "au_guide.json")
        au_size = save_guide_json(au_path, au_channels)
        results.append(("Australia (AU)", "au_guide.json", len(au_channels), au_size))

    # 3. New Zealand (NZ)
    nz_xml = fetch_feed_data(NZ_FEED_URL, "New Zealand")
    if nz_xml:
        nz_channels = extract_channels_from_xml(nz_xml, NZ_CHANNELS)
        nz_path = os.path.join(output_dir, "nz_guide.json")
        nz_size = save_guide_json(nz_path, nz_channels)
        results.append(("New Zealand (NZ)", "nz_guide.json", len(nz_channels), nz_size))

    # 4. United States (US)
    us_xml = fetch_feed_data(US_FEED_URL, "United States")
    if us_xml:
        us_channels = extract_channels_from_xml(us_xml, US_CHANNELS)
        us_path = os.path.join(output_dir, "us_guide.json")
        us_size = save_guide_json(us_path, us_channels)
        results.append(("United States (US)", "us_guide.json", len(us_channels), us_size))

    # 5. Canada (CA)
    ca_xml = fetch_feed_data(CA_FEED_URL, "Canada")
    if ca_xml:
        ca_channels = extract_channels_from_xml(ca_xml, CA_CHANNELS)
        ca_path = os.path.join(output_dir, "ca_guide.json")
        ca_size = save_guide_json(ca_path, ca_channels)
        results.append(("Canada (CA)", "ca_guide.json", len(ca_channels), ca_size))

    print("\n==================================================")
    print("Generation Summary:")
    print("--------------------------------------------------")
    print(f"{'Region':<22} | {'Filename':<15} | {'Channels':<9} | {'File Size'}")
    print("--------------------------------------------------")
    for region, filename, channels, size in results:
        print(f"{region:<22} | {filename:<15} | {channels:<9} | {size:.1f} KB")
    print("==================================================")

if __name__ == "__main__":
    main()
