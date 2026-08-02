# Data sources and the evidence policy

## Credibility tiers

Every source carries a tier, stored in `sources.credibility_tier`. The tier drives
field precedence in the metadata agent, evidence weight in the country
classifier, and the verification status of every record that depends on it.

| Tier | What belongs there | How it may be used |
| ---: | --- | --- |
| 1 | Manufacturer official pages, defence ministries, armed forces, civil aviation authorities (FAA, EASA), government procurement documents, official programme offices, official public-domain image repositories | Authoritative. One tier-1 source plus a resolved origin makes a record *Probable*; two independent sources make it *Verified*. |
| 2 | FlightGlobal, IISS, SIPRI, NATO publications, congressional/parliamentary research services, established aerospace institutions, reputable academic publications | Authoritative for corroboration; treated identically to tier 1 for the verification threshold. |
| 3 | Wikimedia Commons, Wikipedia (discovery only), open-source aviation catalogues, established specialist databases | Good for discovery and cross-checking. A record supported only by tier 3 is at best *Probable*, and only when two independent tier-3 datasets agree. |
| 4 | Forums, social media, unverified blogs | **Leads only.** `source_verification_agent.evaluate_record` hard-codes the rule: a record supported only by tier-4 material can never leave *Needs Verification*, regardless of how many tier-4 sources agree. |

### Aggregators

`sources.is_aggregator = 1` marks a source that republishes other datasets. An
aggregator satisfies the "every canonical platform must have at least one
supporting source" requirement but is excluded from the independent-source count
in both `source_verification_agent` and `country_classifier_agent`, and its
origin evidence is weighted at half. Without this, a single observation
republished twice would masquerade as corroboration.

## The seed package

`data/seed/Global_UAV_Database_2026.*` was supplied as the project seed:
591 canonical records over 647 source records, compiled 2 August 2026. It is
imported in two layers — the source-record layer (its own raw evidence) and the
canonical layer (curated aggregate: aliases, model codes, specifications) — and
the package itself is registered as an **aggregator**.

Its four underlying datasets are registered separately with their own tiers:

| Dataset | Tier | Records in seed | Notes recorded with the source |
| --- | ---: | ---: | --- |
| EASA Drones for EU Operations | 1 | 146 | Official EU class-marking list. Technical data are voluntarily supplied by manufacturers and the list is not exhaustive. |
| Bard Drone Databook 2019 | 2 | 193 | Historical military/government UAS baseline. Operational status and origin may need updating. |
| Curated UAV Seed 2026 | 3 | 149 | Cross-domain starter registry prioritising current, widely documented systems. |
| OpenDroneList | 3 | 159 | Community-maintained catalogue of commercial models. Manufacturer verification recommended. |

The seed's own README states the scope limit plainly, and this project keeps it:
no authoritative, complete worldwide registry of every UAV, FPV design, one-off
research airframe, cancelled prototype, local modification, white-label
commercial model or battlefield-built drone exists.

## Live sources

Configured in `data/seed/source_registry.json`. Adding a source is a data change,
not a code change.

| id | Publisher | Tier | Format | Purpose |
| --- | --- | ---: | --- | --- |
| `opendronelist` | Dronetag | 3 | CSV | Civilian/commercial model discovery and cross-checking. |
| `easa_drones_eu` | EASA | 1 | HTML table | Class-marked UAS placed on the EU market. |
| `faa_uas_doc` | FAA | 1 | JSON | US Remote ID declarations of compliance. |
| `wikipedia_uav_lists` | Wikimedia Foundation | 3 | MediaWiki API | Discovery leads only — names found here need tier 1–2 corroboration before promotion. |
| `wikimedia_commons_images` | Wikimedia Foundation | 3 | MediaWiki API | Primary image provider. |
| `manufacturer_sites` (6 entries) | GA-ASI, Baykar, IAI, DJI, AeroVironment, Elbit | 1 | HTML | Product-line evidence straight from the builder. |
| `government_sources` (3 entries) | US DoD, UK MoD, DRDO | 1 | HTML | Programme corroboration and origin evidence. |

### Country of origin from regulators

Regulatory registers are the strongest *completeness* source for civilian
aircraft and the weakest *origin* source. The declared address is the
manufacturer's registered seat. Discoveries from `crawlers/regulatory.py`
therefore carry `origin_is_registration_only`, leave `raw_country` blank, and
stash the declared country in `payload.registered_country`, where it may populate
`production_country` but never `country_id`.

## Reachability in the environment that produced this build

The build environment's egress policy permits only GitHub and PyPI hosts. Every
other configured source returned HTTP 403 at the proxy. Recorded outcome:

| Source | Host | Result |
| --- | --- | --- |
| OpenDroneList | `raw.githubusercontent.com` | **reachable** — crawled live, contributed new candidates |
| Wikimedia Commons (images) | `commons.wikimedia.org` | blocked (403 at proxy) |
| Wikipedia list pages | `en.wikipedia.org` | blocked (403 at proxy) |
| EASA | `www.easa.europa.eu` | blocked (403 at proxy) |
| FAA | `uasdoc.faa.gov` | blocked (403 at proxy) |
| Manufacturer sites (6) | various | blocked (403 at proxy) |
| Government sources (3) | various | blocked (403 at proxy) |

Each refusal is recorded as a `source_unreachable` unresolved item naming the
host, and as a `strategy_failed` entry in `logs/audit.jsonl`. The pipeline treats
these as isolated failures: the reachable source still ran, and the atlas still
built. Re-running `python run.py --all --resume` from a network that permits
these hosts picks up exactly where this build stopped.

## Image sourcing policy

Priority order, highest first:

1. Wikimedia Commons with a compatible licence
2. Government public-domain imagery (`*.mil`, DVIDS, NASA, defense.gov, USGS, NOAA)
3. Manufacturer media kits with explicit reuse permission
4. Official press images with clear licence terms
5. Other Creative Commons repositories

**Accepted licences:** CC0, public domain / PD-*, CC BY, CC BY-SA, plain
"Attribution"/"Attribution-ShareAlike", and US federal government works.

**Rejected, always:** all-rights-reserved, fair-use/non-free tags, NonCommercial
(unless `UAV_ALLOW_NC_LICENSES=1`), NoDerivatives (the atlas resizes every image,
which is a derivative), and anything with no licence statement or no source page
to attribute back to.

**Rejected by content filter:** logos, insignia, roundels, patches, flags,
diagrams, schematics, silhouettes, maps, charts, screenshots, 3D renders,
artist's impressions and concept art (the last only permitted when the record is
itself explicitly a concept or prototype and no real image exists), SVG/PDF/GIF
files, images narrower than 500 px, and any image that is an exact or perceptual
duplicate of one already used for a different platform.

## Compliance

- `robots.txt` is consulted before every fetch and honoured (`UAV_RESPECT_ROBOTS=1`).
- Requests are rate limited per host (default 1 req/s) with a descriptive user
  agent identifying the project.
- No authentication is bypassed; no anti-bot system is evaded; no private or
  restricted source is scraped. A 403 is reported, not routed around.
- All network calls have hard timeouts and a response size ceiling.
- Filenames and URLs are sanitised; image paths are traversal-safe by
  construction (`app.utils.safe_join`).
- No image is downloaded without a defensible reuse basis, and attribution is
  preserved end to end in `output/photo_attribution.csv` and the PDF appendix.
- Secrets are read from the environment only; `.env` is gitignored and CI checks
  that no credential patterns are committed.
