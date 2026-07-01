#!/usr/bin/env python3
"""
HGTFS Aggregator — merge many HGTFS archives into one global feed
=================================================================

Completely static: no server, no database. It reads ONE descriptor
(`sources.json`), pulls each source HGTFS archive (from a GitHub repo, a .zip
URL, or a local folder), namespaces every identifier by its source so IDs never
collide across feeds (US `n00001` -> `us:n00001`, Italy `ITHS00001` ->
`it:ITHS00001`), concatenates the tables, and writes a single aggregated HGTFS
archive to `./hgtfs/` (+ `hgtfs.zip`).

The output is loadable straight into the HGTFS viewer for a global view of the
evolution of railways:  <viewer>?repo=hgtfs/aggregate

Run:  python3 aggregate.py [sources.json]     (stdlib only; needs network for
remote sources). A GitHub Action re-runs it and commits the result.

Scope: the structural / network files that a global time-map needs — agency,
routes, stops, network_edges, route_operators, historical_sources, events,
calendar. The schedule triple (trips / stop_times / shapes) is deliberately NOT
aggregated: the viewer draws network_edges directly and those files are huge.
"""

import csv
import io
import json
import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "hgtfs")

# HGTFS files we aggregate (structural subset). route_operators may ship as .csv.
FILES = ["agency", "routes", "stops", "network_edges",
         "route_operators", "historical_sources", "events", "calendar"]

# columns whose values are identifiers and must be namespaced per source.
# NB: direction_id / location_type / route_type etc. are NOT ids — excluded.
ID_COLS = {"agency_id", "route_id", "stop_id", "trip_id", "service_id",
           "shape_id", "source_id", "event_id",
           "from_stop_id", "to_stop_id", "parent_station"}

UA = {"User-Agent": "hgtfs-aggregate"}


# ---------------------------------------------------------------- load sources
def fetch_bytes(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def read_rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def basename_kind(name):
    b = name.lower().rsplit("/", 1)[-1]
    for k in FILES:
        if b == k + ".txt" or b == k + ".csv":
            return k
    return None


def tables_from_zip(zbytes, tables):
    z = zipfile.ZipFile(io.BytesIO(zbytes))
    for n in z.namelist():
        k = basename_kind(n)
        if k and k not in tables:
            tables[k] = read_rows(z.read(n).decode("utf-8", "replace"))


def load_source(src):
    """Return {kind: [rows]} for one source. type: github | zip | local.
    A local path may be a directory or a .zip file (vendored sources are zipped
    so the viewer's feed-file matcher doesn't pick them up as loose feeds)."""
    typ = src.get("type", "github")
    tables = {}
    if typ == "zip":
        tables_from_zip(fetch_bytes(src["url"]), tables)
    elif typ == "local":
        base = src["path"] if os.path.isabs(src["path"]) else os.path.join(HERE, src["path"])
        if base.endswith(".zip") and os.path.isfile(base):
            with open(base, "rb") as f:
                tables_from_zip(f.read(), tables)
        else:
            for k in FILES:
                for ext in ("txt", "csv"):
                    p = os.path.join(base, f"{k}.{ext}")
                    if os.path.exists(p):
                        with open(p, encoding="utf-8") as f:
                            tables[k] = read_rows(f.read())
                        break
    else:  # github via jsDelivr CDN
        repo, ref = src["repo"], src.get("ref", "main")
        path = src.get("path", "").strip("/")
        pref = f"https://cdn.jsdelivr.net/gh/{repo}@{ref}/" + (path + "/" if path else "")
        for k in FILES:
            for ext in ("txt", "csv"):
                try:
                    tables[k] = read_rows(fetch_bytes(pref + f"{k}.{ext}").decode("utf-8", "replace"))
                    break
                except Exception:
                    pass
    return tables


# ---------------------------------------------------------------- namespace ids
def namespace(rows, sid, sep):
    out = []
    for r in rows:
        out.append({k: (f"{sid}{sep}{v}" if (k in ID_COLS and v not in (None, "")) else v)
                    for k, v in r.items()})
    return out


# ---------------------------------------------------------------- write helpers
def union_header(rows):
    header = []
    for r in rows:
        for c in r:
            if c not in header:
                header.append(c)
    return header


def write_table(kind, rows):
    if not rows:
        return 0
    header = union_header(rows)
    with open(os.path.join(OUT, kind + ".txt"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def date_span(agg):
    lo, hi = None, None
    cols = ("date_opened", "date_opened_min", "date_opened_max", "date_closed",
            "date", "end_date", "start_date")
    for kind in agg:
        for r in agg[kind]:
            for c in cols:
                v = (r.get(c) or "")[:8]
                if len(v) >= 4 and v[:4].isdigit():
                    v = (v + "0101")[:8]
                    lo = v if lo is None or v < lo else lo
                    hi = v if hi is None or v > hi else hi
    return lo or "18000101", hi or "20000101"


# ---------------------------------------------------------------- build
def build(sources_path):
    cfg = json.load(open(sources_path))
    sep = cfg.get("id_separator", ":")
    os.makedirs(OUT, exist_ok=True)
    agg = {k: [] for k in FILES}

    for src in cfg["sources"]:
        sid = src["id"]
        tables = load_source(src)
        got = []
        for k, rows in tables.items():
            agg[k].extend(namespace(rows, sid, sep))
            got.append(f"{k}={len(rows)}")
        print(f"· {sid:4} {src.get('name','')[:48]:48}  {', '.join(got) or 'nothing loaded'}")
        # guarantee a credit for every source, even if it ships no historical_sources
        agg["historical_sources"].append({
            "source_id": f"{sid}{sep}_source",
            "source_name": src.get("name", sid),
            "source_url": src.get("url") or (f"https://github.com/{src['repo']}" if src.get("repo") else ""),
            "source_type": "5",
            "source_notes": f"Aggregated HGTFS source '{sid}'.",
        })

    # write structural tables
    counts = {k: write_table(k, agg[k]) for k in FILES}

    # single synthesized feed_info spanning all sources
    lo, hi = date_span(agg)
    fi = cfg.get("feed", {})
    with open(os.path.join(OUT, "feed_info.txt"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["feed_publisher_name", "feed_publisher_url", "feed_lang",
                    "feed_start_date", "feed_end_date", "feed_version"])
        w.writerow([fi.get("publisher_name", "HGTFS Aggregate"),
                    fi.get("publisher_url", "https://hgtfs.github.io/"),
                    fi.get("lang", "en"), lo, hi,
                    fi.get("version", "hgtfs-aggregate")])

    # zip the archive — deterministic (fixed timestamps, sorted) so CI only
    # commits when the data actually changes, not on every rebuild.
    zpath = os.path.join(HERE, "hgtfs.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(OUT)):
            if name.endswith(".txt"):
                zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                with open(os.path.join(OUT, name), "rb") as fh:
                    z.writestr(zi, fh.read())

    n_src = len(cfg["sources"])
    print(f"\nAggregated {n_src} source(s) -> {OUT}/  span {lo[:4]}–{hi[:4]}")
    for k in FILES + ["feed_info"]:
        if k == "feed_info":
            print(f"  feed_info.txt        1")
        elif counts.get(k):
            print(f"  {k+'.txt':20} {counts[k]:>7}")
    print(f"  hgtfs.zip written ({os.path.getsize(zpath)//1024} KB)")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "sources.json"))
