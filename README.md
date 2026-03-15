# XRPL Issuer / Trustline Scanner

A lightweight CLI tool for exploring issued assets on XRPL.

v0.1 focuses on **issuer-only trust-line asset scanning**.

It aggregates trust lines by **issuer + currency** and outputs:

- issuer address
- currency code
- trustlines count
- unique holders

---

## Quick Scan Demo

### Install

    pip install -r requirements.txt

### Run a scan

    python3 monitor.py scan --issuer rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh

Replace the issuer address with any valid XRPL issuer account.

### Export JSON

    python3 monitor.py scan \
      --issuer rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh \
      --format json \
      --out results.json

### Export CSV

    python3 monitor.py scan \
      --issuer rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh \
      --format csv \
      --out results.csv

### Example Output

    Issuer Address                      Currency Code           Trustlines Count    Unique Holders
    ----------------------------------------------------------------------------------------------
    rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh  CNY                                   59                59
    rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh  USD                                   39                39
    rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh  RLUSD                                  6                 6
 
## Usage

Scan an issuer:

    python3 monitor.py scan --issuer r...

Filter small assets:

    python3 monitor.py scan \
      --issuer r... \
      --min-trustlines 50

Limit results:

    python3 monitor.py scan \
      --issuer r... \
      --top 10

## Notes

- v0.1 uses XRPL `account_lines`
- v0.1 is issuer-only scanning
- future versions may add:
  - DEX data
  - volume
  - activity tracking
