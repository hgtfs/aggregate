# hgtfs/aggregate — a global HGTFS feed of rail history

A **completely static aggregator** that merges many [HGTFS](https://hgtfs.github.io/)
archives into one feed, for a global view of the evolution of railways.

Everything is driven by a single descriptor — [`sources.json`](sources.json).
[`aggregate.py`](aggregate.py) (Python stdlib only) reads it, pulls each source
archive, **namespaces every identifier by its source** so IDs never collide
(US `n00001` → `us:n00001`, Italy `ITHS00001` → `it:ITHS00001`), concatenates
the tables, and writes the aggregated archive to [`hgtfs/`](hgtfs/) (+ `hgtfs.zip`).

## Load it

Point the HGTFS viewer at this repo:

```
<viewer-url>?repo=hgtfs/aggregate
```

The viewer fetches the aggregated files straight from GitHub via jsDelivr.

## What's in it

Currently aggregates:

| id | source | how it's pulled |
|----|--------|-----------------|
| `us` | [United States — RRMMA, 1840–1870](https://github.com/openhistorymap/us_trains) | live from GitHub |
| `it` | Italy — historical railway network, 1839–1930 | vendored in [`sources/it/`](sources/it) (not yet published as its own repo) |

Span **1827–2013** · ~1,000 operators · ~7,500 stops · ~4,000 dated network edges.

## Add a source

Append an entry to `sources.json` and re-run — no code changes:

```jsonc
{
  "id": "fr",                       // short, unique — becomes the ID prefix "fr:"
  "name": "France — …",
  "type": "github",                 // github | zip | local
  "repo": "org/repo", "ref": "main", "path": "hgtfs"
  // type "zip":   "url": "https://…/feed.zip"
  // type "local": "path": "sources/fr"
}
```

Any HGTFS archive works as long as it carries the standard files. IDs are
rewritten automatically, so two feeds that both use `001` (or `FS`, or
`baltimore_and_ohio`) stay distinct.

## What is aggregated

The **structural / network** files a global time-map needs:

`agency` · `routes` · `stops` · `network_edges` · `route_operators` ·
`historical_sources` · `events` · `calendar`, plus a synthesized `feed_info`
spanning all sources, and one `historical_sources` credit row per source.

The **schedule triple** (`trips` / `stop_times` / `shapes`) is **not**
aggregated on purpose: the viewer draws `network_edges` directly, and those
files are huge. Add them to `FILES` in `aggregate.py` if you need a full feed.

## Regenerate

```bash
python3 aggregate.py            # uses sources.json; needs network for remote sources
```

A GitHub Action ([`.github/workflows/aggregate.yml`](.github/workflows/aggregate.yml))
re-runs this weekly, on changes to `sources.json` / `sources/**` / `aggregate.py`,
and on demand, committing the refreshed `hgtfs/` back to the repo — so the global
feed tracks its upstream sources automatically.

## Notes

- Namespacing covers every id column (`agency_id`, `route_id`, `stop_id`,
  `trip_id`, `service_id`, `shape_id`, `source_id`, `event_id`, `from_stop_id`,
  `to_stop_id`, `parent_station`); non-id `*_id` fields like `direction_id` are
  left alone. Empty values stay empty.
- Each source's own `route_type`, colours and date precision are preserved as-is
  (e.g. US uses `1405` Steam railway, Italy uses `2` Rail).
- Operator ids that a source references but does not define (e.g. Italy's
  `UNKNOWN_*` / `SARD_OP` pseudo-operators) are passed through unchanged; the
  viewer renders them as dashed "unresolved operator" entries.
