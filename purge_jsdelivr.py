#!/usr/bin/env python3
"""
purge_jsdelivr.py — clear jsDelivr's CDN cache so aggregation updates propagate.

jsDelivr caches `@<branch>` files for hours, so after the aggregate is rebuilt
the viewer keeps getting stale data until the cache is purged. This is called
by the CI: once before building (purge the SOURCES so the rebuild fetches fresh
inputs) and once after committing (purge THIS aggregate's output so consumers
see the update immediately).

Usage:
  purge_jsdelivr.py sources <sources.json>     # purge every github source's feed files
  purge_jsdelivr.py self <owner/repo> <ref>    # purge the aggregate's own hgtfs/ output
"""
import json
import sys
import urllib.request

FILES = ["agency", "routes", "stops", "network_edges", "route_operators",
         "historical_sources", "events", "calendar", "feed_info"]


def purge(path):
    url = "https://purge.jsdelivr.net/" + path.lstrip("/")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hgtfs-purge"})
        with urllib.request.urlopen(req, timeout=45) as r:
            r.read()
        print("purged", path)
    except Exception as e:                       # a missing file / transient error is harmless
        print("skip  ", path, "-", e)


def gh_base(repo, ref, path):
    path = (path or "").strip("/")
    return f"gh/{repo}@{ref}/" + (path + "/" if path else "")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    mode = sys.argv[1]
    if mode == "sources":
        cfg = json.load(open(sys.argv[2]))
        for s in cfg.get("sources", []):
            if s.get("type", "github") != "github":
                continue                          # zip/local sources aren't on jsDelivr
            base = gh_base(s["repo"], s.get("ref", "main"), s.get("path", ""))
            for k in FILES:
                purge(base + f"{k}.txt")
            purge(base + "route_operators.csv")   # some feeds ship this as .csv
    elif mode == "self":
        repo, ref = sys.argv[2], sys.argv[3]
        base = gh_base(repo, ref, "hgtfs")
        for k in FILES:
            purge(base + f"{k}.txt")
        purge(f"gh/{repo}@{ref}/hgtfs.zip")
    else:
        sys.exit("unknown mode: " + mode)


if __name__ == "__main__":
    main()
