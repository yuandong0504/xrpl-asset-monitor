## XRPL Issuer / Trustline Scanner

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

```bash
pip install -r requirements.txt
### Run a scan

```bash
python3 monitor.py scan --issuer rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh
### Replace the issuer address with any valid XRPL issuer account.
