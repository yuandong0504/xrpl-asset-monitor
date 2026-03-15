# XRPL Asset Monitor

A lightweight CLI tool for exploring issued assets on the XRP Ledger.

This tool helps developers and researchers inspect XRPL token activity from the command line.

Capabilities:

- Scan assets issued by a specific account
- Discover issuers across the XRPL network
- Rank assets by trustline count
- Rank issuers by trustline objects
- Export results for analysis


--------------------------------------------------

WHY THIS TOOL EXISTS

XRPL explorers like XRPSCAN and Bithomp are useful for browsing tokens, but they are not designed for:

- command-line workflows
- automation
- bulk analysis
- quick issuer discovery

This tool provides a simple CLI interface for exploring XRPL token activity.


--------------------------------------------------

INSTALLATION

Clone the repository and install dependencies:

pip install -r requirements.txt

(Optional) create a shell alias:

alias xrpl="python3 ~/xrpl-asset-monitor/monitor.py"


--------------------------------------------------

COMMANDS


1. Scan assets from a single issuer

xrpl scan --issuer rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh

Example output:

Issuer Address                      Currency Code          Trustlines Count   Unique Holders
----------------------------------------------------------------------------------------------
rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh CNY                                  59               59
rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh USD                                  39               39
rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh RLUSD                                 6                6


Filter assets:

xrpl scan --issuer r... --min-trustlines 50

Limit output:

xrpl scan --issuer r... --top 10


--------------------------------------------------

2. Discover issuers across XRPL

Scan RippleState objects to discover asset issuers.

xrpl scan-network --max-pages 5

Example output:

Issuer Address                      Trustline Objects    Discovered Currencies
-----------------------------------------------------------------------------
rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz                  4                     1
rUQXurByxmKni4aLpuWMYMxxV5GWT1Azw2                  2                     1


--------------------------------------------------

3. Top assets across the network

Rank currencies by number of discovered trustlines.

xrpl top-assets --limit 20

Example output:

Asset      Trustlines
-----------------------
SOLO       15
BTC        8
ELS        7
USD        6
CNY        5


NOTE

Results are based on a partial ledger scan.
Increase max-pages to analyze more ledger data.


--------------------------------------------------

4. Top issuers

Rank issuers by trustline objects discovered in the ledger.

xrpl top-issuers --limit 10 --max-pages 10

Example output:

Issuer Address                      Trustline Objects
-----------------------------------------------------
rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz   4
rUQXurByxmKni4aLpuWMYMxxV5GWT1Azw2   2


--------------------------------------------------

NOTES

XRPL uses two currency formats:

Standard codes
USD, EUR, BTC

160-bit currency codes
hex encoded tokens

The tool attempts to decode hex codes when possible.


--------------------------------------------------

USE CASES

Possible applications:

- XRPL token research
- issuer discovery
- DeFi asset analysis
- token index building
- XRPL ecosystem monitoring


--------------------------------------------------

LICENSE

MIT
