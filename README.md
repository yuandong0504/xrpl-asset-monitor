# XRPL Asset Monitor v0.4

🚀 Lightweight CLI tool for exploring issued assets on the XRP Ledger

---

## Features

- Scan assets issued by an account
- Discover issuers across the XRPL network
- Rank top assets by trustlines
- Rank top issuers
- Export JSON or CSV
- Live scan statistics
- Smart pagination controls

---

## Installation

```bash
pip install xrpl-py
alias xrpl="python3 monitor.py"
```

---

## Quick Start

### Scan assets issued by an account

⚠️ Always use `--max-pages` to avoid scanning the entire ledger.

```bash
xrpl scan \
  --issuer rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz \
  --max-pages 10
```

Filter high-liquidity assets:

```bash
xrpl scan \
  --issuer rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz \
  --min-trustlines 50 \
  --max-pages 10 \
  --top 20
```

Export JSON:

```bash
xrpl scan \
  --issuer rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz \
  --max-pages 10 \
  --format json \
  --out issuer_assets.json
```

---

## Discover issuers across XRPL

```bash
xrpl scan-network \
  --max-pages 20 \
  --top 20
```

Export JSON:

```bash
xrpl scan-network \
  --max-pages 20 \
  --format json \
  --out issuers.json
```

---

## Top assets across network

```bash
xrpl top-assets \
  --limit 20
```

---

## Top issuers across network

```bash
xrpl top-issuers \
  --limit 20 \
  --max-pages 20
```

---

## Parameters

| Parameter | Description | Example |
|-----------|-------------|--------|
| `--issuer` | Issuer address | `--issuer r...` |
| `--min-trustlines` | Minimum trustlines required | `--min-trustlines 50` |
| `--max-pages` | Maximum ledger pages to scan | `--max-pages 10` |
| `--limit` | Objects per request | `--limit 200` |
| `--top` | Show only top N results | `--top 20` |
| `--format` | Output format | `json` / `csv` |
| `--out` | Output file | `--out data.json` |

---

## Example Output

```
Issuer Address                           Currency     Trustlines   Holders
---------------------------------------------------------------------------
rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz        USD          120          118
rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz        EUR           85           83
rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz        BTC           64           61
```

---

## Performance Notes

XRPL can contain millions of trustlines.

Without page limits a scan may run for a long time.

Recommended settings:

| Use Case | Suggested Setting |
|--------|----------------|
| Quick analysis | `--max-pages 10` |
| Research | `--max-pages 50` |
| Deep scan | `--max-pages 200` |

---

## XRPL Research Playbook

This tool can be used to explore the XRP Ledger ecosystem and uncover useful insights.

---

### 1 Discover the most adopted tokens

```bash
xrpl top-assets --limit 20
```

What this shows

- Tokens with the largest number of holders
- Assets with real adoption on XRPL

Example insight

```
Asset      Trustlines
-----------------------
SOLO       1998
BTC        842
USD        620
```

Interpretation

Higher trustline counts indicate stronger adoption.

---

### 2 Identify major issuers

```bash
xrpl top-issuers --limit 20 --max-pages 20
```

What this shows

- Projects issuing widely adopted assets
- Infrastructure providers
- Stablecoin issuers

Useful for discovering major XRPL ecosystem players.

---

### 3 Investigate a specific project

```bash
xrpl scan --issuer <issuer_address> --max-pages 10
```

What this reveals

- Tokens issued by a project
- Number of holders for each token
- Which assets are actually used

Example finding

```
Currency   Trustlines
---------------------
SOLO       1998
SOL           2
```

Interpretation

SOLO has real adoption while SOL appears inactive.

---

### 4 Discover new tokens across the network

```bash
xrpl scan-network --max-pages 20
```

What this does

- Scans XRPL ledger data
- Finds issuers and currencies across the network
- Helps detect emerging tokens

Useful for ecosystem monitoring.

---

### 5 Detect inactive tokens

Run:

```bash
xrpl scan --issuer <issuer>
```

Interpretation guide

```
Trustlines < 10      likely inactive token
Trustlines 10–100    niche asset
Trustlines > 1000    significant adoption
```

---

### 6 Study XRPL ecosystem growth

Combine multiple commands:

```bash
xrpl scan-network
xrpl top-assets
xrpl top-issuers
```

This helps answer questions like:

- Which assets dominate XRPL adoption?
- Which issuers control the largest ecosystems?
- How quickly is XRPL expanding?

---

### 7 Analyze issuer ecosystem health

```bash
xrpl issuer-health --issuer <issuer_address>
```

Optional (faster scan):

```bash
xrpl issuer-health \
  --issuer <issuer_address> \
  --max-pages 20
```

What this shows

- Real tokens issued by the project
- Minor tokens with limited usage
- Noise / spam tokens
- An overall Ecosystem Health Score

Example insight

```
Real tokens : 1
Minor tokens: 3
Noise tokens: 28

Ecosystem Health Score: 0.92
```

Interpretation

A healthy issuer ecosystem typically has:

- One dominant real token
- A few minor variants
- Many low-usage noise tokens

This pattern appears frequently on XRPL and can help identify impersonation attempts or token spam.

---

### 8 Analyze whale concentration

```bash
xrpl whale-concentration \
  --issuer <issuer_address> \
  --token <currency_code>
```

Optional (limit scan size):

```bash
xrpl whale-concentration \
  --issuer <issuer_address> \
  --token SOLO \
  --max-pages 50
```

What this shows

- Token distribution among holders
- Concentration of supply in top wallets

Example output

```
Whale Concentration Report

Token: SOLO
Issuer: rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz
Total holders scanned: 198,717

Top 10 holders  : 38.42%
Top 50 holders  : 52.17%
Top 100 holders : 61.33%
Top 500 holders : 78.90%
```

Interpretation

- High concentration → supply controlled by a few wallets
- Low concentration → broader token distribution

This helps evaluate whether a token ecosystem is decentralized or dominated by whales.

## Use Cases

- DeFi research  
- Token issuer discovery  
- Liquidity analysis  
- Trustline distribution tracking  
- XRPL data export for quantitative analysis

---
## Case Study: Detecting Token Impersonation on XRPL

This tool can reveal token impersonation patterns that are difficult to detect through typical web explorers.

### Example: Sologenic issuer analysis

Run a deep scan of the Sologenic issuer:

```bash
xrpl scan \
  --issuer rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz \
  --max-pages 999
```

Example result (simplified):

```
Currency   Trustlines
-------------------------
SOLO       198717
SOL           775
sol           202
Sol            22
SOL@            5
SLO             4
T?LO            4
SO<O            1
SOLOO           1
```

### Interpretation

Although 32 currency codes exist under the same issuer address, only one token shows real adoption:

```
SOLO → 198,717 trustlines
```

All other variants have extremely small holder counts.

Examples include:

```
SOL
sol
Sol
SOL@
SLO
SOLOO
```

These are likely:

- user mistakes
- token impersonation attempts
- experimental tokens
- abandoned assets

### Insight

Deep issuer scans allow researchers to identify:

- impersonation tokens
- abandoned assets
- naming collisions
- user confusion patterns

This type of analysis is difficult to perform using standard XRPL web explorers, which typically display assets individually rather than analyzing the full issuer ecosystem.

### Why this matters

XRPL allows issuers to create many currency codes under a single account.

Large issuers may accumulate dozens of token variations over time.

Analyzing trustline distribution helps identify which assets have real adoption and which are noise or impersonation attempts.

## License

MIT
