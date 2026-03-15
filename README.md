# XRPL Issuer / Trustline Scanner

A lightweight CLI tool for exploring issued assets on the XRP Ledger.

The tool can:

- scan assets for a single issuer
- discover issuers across the XRPL network
- aggregate trustlines by currency
- export results to JSON or CSV


## Why this tool exists

XRPL explorers like XRPSCAN and Bithomp are useful for browsing tokens, but they are not designed for:

- command-line analysis
- automated research workflows
- batch export of issuer asset data

This tool provides a simple CLI interface for inspecting issuer assets and discovering token issuers directly from XRPL.


## Installation

    pip install -r requirements.txt


## Scan a single issuer

Example:

    python3 monitor.py scan --issuer rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq --max-pages 3

Example output:

    Issuer Address                      Currency Code           Trustlines Count    Unique Holders
    ----------------------------------------------------------------------------------------------
    rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq  EUR                                  309               309
    rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq  USD                                  291               291


Filter small assets:

    python3 monitor.py scan \
      --issuer r... \
      --min-trustlines 50


Limit output:

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


## Discover issuers across XRPL

The tool can scan RippleState objects from the ledger to discover issuers.

Example:

    python3 monitor.py scan-network --max-pages 3


Example output:

    Issuer Address                      Trustline Objects    Discovered Currencies
    -------------------------------------------------------------------------------
    rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq                  600                        2
    rxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx                  520                        4


Export issuer list:

    python3 monitor.py scan-network \
      --format json \
      --out issuers.json


## Current Features

- issuer trustline scanning
- network issuer discovery
- asset aggregation by currency
- trustline holder counts
- filtering with `--min-trustlines`
- result limiting with `--top`
- pagination control with `--max-pages`
- JSON / CSV export


## License

MIT
