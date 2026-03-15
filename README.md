# XRPL Asset Monitor v0.4

🚀 Lightweight CLI tool for exploring issued assets on the XRP Ledger.

## Features

- Scan assets issued by a specific XRPL account
- Discover issuers across the XRPL network
- Rank assets by trustline count
- Rank issuers by discovered trustline objects
- Export results to JSON or CSV
- Real-time progress statistics
- Automatic retry for network errors
- Smart pagination stop to avoid endless scans

---

# Installation

Install dependency:

pip install xrpl-py

Create alias (optional):

alias xrpl="python3 monitor.py"

---

# Quick Start

## Scan assets from a specific issuer

xrpl scan --issuer rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz

Recommended scan for large issuers:

xrpl scan --issuer rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz \
--min-trustlines 50 \
--max-pages 10 \
--top 20

Example output:

Issuer Address                           Currency Code     Trustlines Count   Unique Holders
---------------------------------------------------------------------------------------------
rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz        USDT               125                120
rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz        USD                89                 85
rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz        EUR                67                 64

---

# Discover issuers across XRPL

Scan RippleState objects to discover issuers:

xrpl scan-network --max-pages 10 --top 20

Export JSON:

xrpl scan-network --max-pages 20 --format json --out issuers.json

---

# Top Assets

Rank assets by trustline count:

xrpl top-assets --limit 20

Example output:

Asset      Trustlines
-----------------------
SOLO       15
BTC        8
ELS        7
USD        6
CNY        5

---

# Top Issuers

Rank issuers discovered across ledger scans:

xrpl top-issuers --limit 15 --max-pages 15

---

# Parameters

| Parameter | Description | Default |
|----------|-------------|--------|
| --min-trustlines N | Only show assets with ≥ N trustlines | 0 |
| --max-pages N | Maximum ledger pages to scan | unlimited |
| --top N | Show top N results | all |
| --limit N | Objects per request | 200 |
| --format | Output format | table |
| --out file | Output file path | stdout |

---

# Output Formats

Table (default)

Issuer Address                           Trustline Objects   Discovered Currencies
-----------------------------------------------------------------------------
rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz        15                  3

---

JSON output

xrpl scan --issuer r... --format json

Example:

[
  {
    "issuer": "rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz",
    "currency": "USDT",
    "trustlines_count": 125,
    "unique_holders": 120
  }
]

---

CSV export

xrpl scan --issuer r... --format csv --out assets.csv

---

# Use Cases

DeFi research  
Discover high-adoption tokens and issuers.

XRPL ecosystem analysis  
Track asset distribution and trustline growth.

Token discovery  
Identify widely adopted XRPL assets.

Data export  
Collect data for quantitative research or analytics.

---

# Notes

- Large issuers may have thousands of trustlines
- Always use --max-pages to limit scan size
- Default rate limit avoids RPC throttling
- RPC endpoint can be customized with --rpc-url

---

# Example Workflow

Discover active issuers:

xrpl top-issuers --limit 20 --max-pages 20 > issuers.txt

Analyze a specific issuer:

xrpl scan --issuer rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz \
--min-trustlines 100 \
--max-pages 20 \
--format json > issuer_assets.json

Export network issuer list:

xrpl scan-network --max-pages 50 --format csv --out network_issuers.csv

---

# License

MIT
