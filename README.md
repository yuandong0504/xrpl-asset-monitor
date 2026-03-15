# XRPL Issuer / Trustline Scanner

A lightweight CLI tool for exploring issued assets on the XRP Ledger.

This tool scans trust lines for a given issuer account and aggregates assets by currency.

It outputs:

- issuer address
- currency code
- trustlines count
- unique holders


## Why this tool

Existing XRPL explorers (XRPSCAN, Bithomp) allow browsing tokens, but they are not designed for:

- quick CLI analysis
- batch export of issuer assets
- automated research workflows

Developers and researchers often need a simple way to inspect issuer assets directly from the command line.


## Example

Scan an issuer:

    python3 monitor.py scan --issuer rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq --max-pages 3


Example output:

    Issuer Address                      Currency Code           Trustlines Count    Unique Holders
    ----------------------------------------------------------------------------------------------
    rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq  EUR                                  309               309
    rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq  USD                                  291               291


## Installation

    pip install -r requirements.txt


## Usage

Scan issuer assets:

    python3 monitor.py scan --issuer r...

Filter small assets:

    python3 monitor.py scan \
      --issuer r... \
      --min-trustlines 50

Limit results:

    python3 monitor.py scan \
      --issuer r... \
      --top 10

Export JSON:

    python3 monitor.py scan \
      --issuer r... \
      --format json \
      --out results.json

Export CSV:

    python3 monitor.py scan \
      --issuer r... \
      --format csv \
      --out results.csv


## Current Features

- issuer trustline scanning
- asset aggregation by currency
- trustline holder counts
- CSV / JSON export
- filtering (`--min-trustlines`)
- top results (`--top`)
- pagination control (`--max-pages`)


## Roadmap

Possible future improvements:

- network-wide issuer discovery
- XRPL DEX activity integration
- asset analytics


## License

MIT
