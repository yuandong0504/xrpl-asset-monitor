#!/usr/bin/env python3
"""
XRPL Issuer / Trustline Scanner (v0.1)

Scans trust lines for a given issuer account on XRPL and aggregates by currency.

Features:
- issuer-only scan
- aggregate by issuer/currency
- trustlines count
- unique holders
- CSV / JSON output
- retry + simple rate limiting

Example:
    python monitor.py scan --issuer rEXAMPLE... --limit 200 --output json
    python monitor.py scan --issuer rEXAMPLE... --limit 500 --format csv --out results.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Set, Tuple

from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountLines


DEFAULT_RPC_URL = "https://s1.ripple.com:51234/"
DEFAULT_LIMIT = 200
MAX_LIMIT = 400  # safer upper bound for public servers
DEFAULT_RATE_LIMIT_SECONDS = 0.35
DEFAULT_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 1.5


@dataclass
class AssetStats:
    issuer: str
    currency: str
    trustlines_count: int
    unique_holders: int


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def sleep_rate_limit(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def is_hex_currency(code: str) -> bool:
    return len(code) == 40 and all(c in "0123456789ABCDEFabcdef" for c in code)


def normalize_currency(code: str) -> str:
    """
    XRPL currency codes can be:
    - 3-char standard codes (e.g. USD)
    - 160-bit hex currency codes (40 hex chars)

    For hex currency codes, keep raw if decode is not clean.
    """
    if not is_hex_currency(code):
        return code

    try:
        raw = bytes.fromhex(code)
        text = raw.rstrip(b"\x00").decode("ascii", errors="ignore").strip()
        return text if text else code.upper()
    except Exception:
        return code.upper()


def make_client(url: str) -> JsonRpcClient:
    return JsonRpcClient(url)


def request_with_retry(
    client: JsonRpcClient,
    request_obj: AccountLines,
    retries: int,
    backoff: float,
    rate_limit_seconds: float,
) -> Dict[str, Any]:
    last_err: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            sleep_rate_limit(rate_limit_seconds)
            response = client.request(request_obj)
            result = response.result

            if "error" in result:
                raise RuntimeError(
                    f"XRPL error: {result.get('error')} - {result.get('error_message', '')}"
                )

            return result
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                wait_s = backoff ** attempt
                eprint(f"[warn] request failed (attempt {attempt}/{retries}): {exc}")
                eprint(f"[warn] retrying in {wait_s:.2f}s ...")
                time.sleep(wait_s)
            else:
                break

    raise RuntimeError(f"request failed after {retries} attempts: {last_err}")


def fetch_account_lines(
    client: JsonRpcClient,
    issuer: str,
    limit: int,
    retries: int,
    backoff: float,
    rate_limit_seconds: float,
) -> List[Dict[str, Any]]:
    """
    Fetch all trust lines for a given issuer using pagination via marker.
    """
    marker: Optional[Any] = None
    all_lines: List[Dict[str, Any]] = []

    while True:
        req = AccountLines(
            account=issuer,
            ledger_index="validated",
            limit=limit,
            marker=marker,
        )

        result = request_with_retry(
            client=client,
            request_obj=req,
            retries=retries,
            backoff=backoff,
            rate_limit_seconds=rate_limit_seconds,
        )

        lines = result.get("lines", [])
        all_lines.extend(lines)

        marker = result.get("marker")
        if not marker:
            break

    return all_lines


def aggregate_lines(issuer: str, lines: List[Dict[str, Any]]) -> List[AssetStats]:
    grouped_holders: Dict[Tuple[str, str], Set[str]] = {}
    grouped_counts: Dict[Tuple[str, str], int] = {}

    for line in lines:
        currency_raw = line.get("currency", "UNKNOWN")
        currency = normalize_currency(currency_raw)

        # For account_lines on issuer account, each line's "account" is the counterparty holder.
        holder = line.get("account", "")

        key = (issuer, currency)
        grouped_counts[key] = grouped_counts.get(key, 0) + 1

        if key not in grouped_holders:
            grouped_holders[key] = set()

        if holder:
            grouped_holders[key].add(holder)

    results: List[AssetStats] = []
    for (issuer_addr, currency), count in grouped_counts.items():
        holders = grouped_holders.get((issuer_addr, currency), set())
        results.append(
            AssetStats(
                issuer=issuer_addr,
                currency=currency,
                trustlines_count=count,
                unique_holders=len(holders),
            )
        )

    return results


def sort_results(rows: List[AssetStats], sort_by: str) -> List[AssetStats]:
    if sort_by == "trustlines":
        return sorted(
            rows,
            key=lambda x: (-x.trustlines_count, -x.unique_holders, x.currency),
        )
    if sort_by == "holders":
        return sorted(
            rows,
            key=lambda x: (-x.unique_holders, -x.trustlines_count, x.currency),
        )
    if sort_by == "currency":
        return sorted(rows, key=lambda x: (x.currency, x.issuer))
    return rows


def print_table(rows: List[AssetStats]) -> None:
    if not rows:
        print("No results.")
        return

    headers = ["Issuer Address", "Currency Code", "Trustlines Count", "Unique Holders"]
    widths = [34, 20, 18, 16]

    fmt = (
        f"{{:<{widths[0]}}}  "
        f"{{:<{widths[1]}}}  "
        f"{{:>{widths[2]}}}  "
        f"{{:>{widths[3]}}}"
    )

    print(fmt.format(*headers))
    print("-" * (sum(widths) + 6))
    for row in rows:
        print(
            fmt.format(
                row.issuer,
                row.currency,
                row.trustlines_count,
                row.unique_holders,
            )
        )


def write_json(rows: List[AssetStats], out_path: Optional[str]) -> None:
    data = [asdict(r) for r in rows]
    text = json.dumps(data, indent=2, ensure_ascii=False)

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[ok] wrote JSON to {out_path}")
    else:
        print(text)


def write_csv(rows: List[AssetStats], out_path: Optional[str]) -> None:
    if not out_path:
        raise ValueError("--out is required when --format csv is used")

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["issuer_address", "currency_code", "trustlines_count", "unique_holders"]
        )
        for row in rows:
            writer.writerow(
                [row.issuer, row.currency, row.trustlines_count, row.unique_holders]
            )

    print(f"[ok] wrote CSV to {out_path}")


def run_scan(args: argparse.Namespace) -> int:
    if not args.issuer:
        eprint("[error] v0.1 requires --issuer")
        return 2

    if args.limit <= 0:
        eprint("[error] --limit must be > 0")
        return 2

    if args.limit > MAX_LIMIT:
        eprint(f"[warn] --limit capped from {args.limit} to {MAX_LIMIT}")
        args.limit = MAX_LIMIT

    client = make_client(args.rpc_url)

    eprint(f"[info] rpc_url={args.rpc_url}")
    eprint(f"[info] issuer={args.issuer}")
    eprint(f"[info] limit={args.limit}")
    eprint("[info] fetching trust lines...")

    try:
        lines = fetch_account_lines(
            client=client,
            issuer=args.issuer,
            limit=args.limit,
            retries=args.retries,
            backoff=args.retry_backoff,
            rate_limit_seconds=args.rate_limit,
        )
    except Exception as exc:
        eprint(f"[error] failed to fetch account lines: {exc}")
        return 1

    eprint(f"[info] fetched {len(lines)} trust lines")

    rows = aggregate_lines(args.issuer, lines)
    rows = sort_results(rows, args.sort)

    if args.format == "table":
        print_table(rows)
        return 0

    if args.format == "json":
        write_json(rows, args.out)
        return 0

    if args.format == "csv":
        try:
            write_csv(rows, args.out)
        except Exception as exc:
            eprint(f"[error] failed to write CSV: {exc}")
            return 1
        return 0

    eprint(f"[error] unsupported format: {args.format}")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="monitor.py",
        description="XRPL Issuer / Trustline Scanner (v0.1)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser(
        "scan",
        help="Scan trust-line assets for a given issuer",
    )
    scan.add_argument(
        "--issuer",
        type=str,
        help="Issuer account address (required in v0.1)",
    )
    scan.add_argument(
        "--issuer-only",
        action="store_true",
        help="Accepted for compatibility; v0.1 already operates in issuer-only mode",
    )
    scan.add_argument(
        "--sort",
        choices=["trustlines", "holders", "currency"],
        default="trustlines",
        help="Sort output field",
    )
    scan.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Page size per request (default: {DEFAULT_LIMIT})",
    )
    scan.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format",
    )
    scan.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output file path (required for csv, optional for json)",
    )
    scan.add_argument(
        "--rpc-url",
        type=str,
        default=DEFAULT_RPC_URL,
        help="XRPL JSON-RPC URL",
    )
    scan.add_argument(
        "--rate-limit",
        type=float,
        default=DEFAULT_RATE_LIMIT_SECONDS,
        help=f"Seconds to sleep before each request (default: {DEFAULT_RATE_LIMIT_SECONDS})",
    )
    scan.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"Max retry attempts (default: {DEFAULT_RETRIES})",
    )
    scan.add_argument(
        "--retry-backoff",
        type=float,
        default=DEFAULT_RETRY_BACKOFF,
        help=f"Exponential retry backoff base (default: {DEFAULT_RETRY_BACKOFF})",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scan":
        return run_scan(args)

    eprint(f"[error] unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
