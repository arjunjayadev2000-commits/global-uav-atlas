# Unresolved items

Generated: 2026-08-02T15:47:03+00:00

Open items: **29**. The machine-readable copy is `output/unresolved_records.csv`; this file is the narrative version.

## source_unreachable (12)

Blockers observed: network: baykartech.com; network: elbitsystems.com; network: en.wikipedia.org; network: enterprise.dji.com; network: uasdoc.faa.gov; network: www.avinc.com; network: www.defense.gov; network: www.drdo.gov.in; network: www.easa.europa.eu; network: www.ga-asi.com; network: www.gov.uk; network: www.iai.co.il

Suggested action(s):
- Re-run discovery from an environment whose egress policy permits this host.

<details><summary>Affected subjects (first 60)</summary>

- **AeroVironment official product pages** — host www.avinc.com refused by network egress policy: HTTPSConnectionPool(host='www.avinc.com', port=443): Max retries exceeded with url: /uas (Caused by ProxyEr
- **Baykar official product pages** — host baykartech.com refused by network egress policy: HTTPSConnectionPool(host='baykartech.com', port=443): Max retries exceeded with url: /en/uav/ (Caused by P
- **DJI official product pages** — host enterprise.dji.com refused by network egress policy: HTTPSConnectionPool(host='enterprise.dji.com', port=443): Max retries exceeded with url: /products (Ca
- **DRDO unmanned aerial systems** — host www.drdo.gov.in refused by network egress policy: HTTPSConnectionPool(host='www.drdo.gov.in', port=443): Max retries exceeded with url: /drdo/aeronautical-
- **Drones for EU operations (class-marked UAS)** — host www.easa.europa.eu refused by network egress policy: HTTPSConnectionPool(host='www.easa.europa.eu', port=443): Max retries exceeded with url: /en/domains/c
- **Elbit Systems official product pages** — host elbitsystems.com refused by network egress policy: HTTPSConnectionPool(host='elbitsystems.com', port=443): Max retries exceeded with url: /products/uas/ (C
- **FAA UAS Declaration of Compliance list** — host uasdoc.faa.gov refused by network egress policy: HTTPSConnectionPool(host='uasdoc.faa.gov', port=443): Max retries exceeded with url: /api/v1/products?page
- **General Atomics Aeronautical Systems official product pages** — host www.ga-asi.com refused by network egress policy: HTTPSConnectionPool(host='www.ga-asi.com', port=443): Max retries exceeded with url: /remotely-piloted-air
- **Israel Aerospace Industries official product pages** — host www.iai.co.il refused by network egress policy: HTTPSConnectionPool(host='www.iai.co.il', port=443): Max retries exceeded with url: /p/unmanned-aerial-syst
- **UK Ministry of Defence remotely piloted air systems** — host www.gov.uk refused by network egress policy: HTTPSConnectionPool(host='www.gov.uk', port=443): Max retries exceeded with url: /government/collections/remot
- **US Department of Defense unmanned systems programme pages** — host www.defense.gov refused by network egress policy: HTTPSConnectionPool(host='www.defense.gov', port=443): Max retries exceeded with url: / (Caused by ProxyE
- **Wikipedia list-of-UAV index pages** — host en.wikipedia.org refused by network egress policy: HTTPSConnectionPool(host='en.wikipedia.org', port=443): Max retries exceeded with url: /w/api.php?format

</details>

## possible_duplicate (9)

Suggested action(s):
- Confirm with a manufacturer or programme-office source whether these are one platform or officially separate variants.

<details><summary>Affected subjects (first 60)</summary>

- **DJI Matrice 200 <-> DJI Matrice 200 V2** — one name adds a model designation ['v2'] - possibly the same aircraft (0.887, tokens 0.75)
- **DJI Matrice 210 <-> DJI Matrice 210 V2** — one name adds a model designation ['v2'] - possibly the same aircraft (0.887, tokens 0.75)
- **DJI Matrice 210 RTK <-> DJI Matrice 210 RTK V2** — one name adds a model designation ['v2'] - possibly the same aircraft (0.920, tokens 0.80)
- **DJI Phantom 4 Pro <-> DJI Phantom 4 Pro V2.0** — one name adds a model designation ['0', 'v2'] - possibly the same aircraft (0.830, tokens 0.67)
- **Matrice 200 <-> Matrice 200 V2** — one name adds a model designation ['v2'] - possibly the same aircraft (0.834, tokens 0.67)
- **Matrice 210 <-> Matrice 210 V2** — one name adds a model designation ['v2'] - possibly the same aircraft (0.834, tokens 0.67)
- **Matrice 210 RTK <-> DJI Matrice 210 RTK V2** — one name adds a model designation ['v2'] - possibly the same aircraft (0.766, tokens 0.60)
- **Matrice 210 RTK <-> Matrice 210 RTK V2** — one name adds a model designation ['v2'] - possibly the same aircraft (0.887, tokens 0.75)
- **Phantom 4 Pro <-> Phantom 4 Pro V2.0** — one name adds a model designation ['0', 'v2'] - possibly the same aircraft (0.781, tokens 0.60)

</details>

## country_of_origin (4)

Suggested action(s):
- Consult a tier 1 manufacturer or defence-ministry page for design origin.

<details><summary>Affected subjects (first 60)</summary>

- **Aquila 2** — no origin evidence in any source
- **Aquila 3** — no origin evidence in any source
- **CUBEE** — no origin evidence in any source
- **Hunter** — sources of comparable credibility disagree: Israel (0.80), Multinational (0.80)

</details>

## image_missing (3)

Blockers observed: network egress policy blocks the image provider

Suggested action(s):
- Run the image pass from a network that permits Wikimedia Commons, or sideload a licensed file. Search: https://commons.wikimedia.org/w/index.php?search=DJI%20Matrice%20400%20UAV&title=Special:MediaSearch&type=image
- Run the image pass from a network that permits Wikimedia Commons, or sideload a licensed file. Search: https://commons.wikimedia.org/w/index.php?search=DJI%20Matrice%204E%20UAV&title=Special:MediaSearch&type=image
- Run the image pass from a network that permits Wikimedia Commons, or sideload a licensed file. Search: https://commons.wikimedia.org/w/index.php?search=DJI%20Mini%205%20Pro%20UAV&title=Special:MediaSearch&type=image

<details><summary>Affected subjects (first 60)</summary>

- **DJI Matrice 400** — image search unavailable: host commons.wikimedia.org refused by network egress policy: HTTPSConnectionPool(host='commons.wikimedia.org', port=443): Max retries 
- **DJI Matrice 4E** — image search unavailable: host commons.wikimedia.org refused by network egress policy (proxy refused CONNECT (403/407))
- **DJI Mini 5 Pro** — image search unavailable: host commons.wikimedia.org refused by network egress policy (proxy refused CONNECT (403/407))

</details>

## pipeline_blocker (1)

Blockers observed: network egress policy

Suggested action(s):
- Re-run `python run.py --images` where commons.wikimedia.org and upload.wikimedia.org are reachable, or sideload files with `python run.py --sideload-images`.

<details><summary>Affected subjects (first 60)</summary>

- **Image acquisition unavailable in this environment** — Wikimedia Commons and all other configured image hosts were refused by the network egress policy (HTTP 403 at the proxy). No image bytes could be retrieved. Eve

</details>
