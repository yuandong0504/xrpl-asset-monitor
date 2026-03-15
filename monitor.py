#!/usr/bin/env python3
"""
XRPL Issuer / Trustline Scanner v0.4 (Fixed & Optimized)
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
from xrpl.models.requests import AccountLines, LedgerData

DEFAULT_RPC_URL = "https://s1.ripple.com:51234/"
DEFAULT_LIMIT = 200
MAX_LIMIT = 400
DEFAULT_RATE_LIMIT_SECONDS = 0.35
DEFAULT_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 1.5

@dataclass
class AssetStats:
    issuer: str
    currency: str
    trustlines_count: int
    unique_holders: int

@dataclass
class IssuerSummary:
    issuer: str
    trustline_objects: int
    discovered_currencies: int

def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)

def sleep_rate_limit(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)

def is_hex_currency(code: str) -> bool:
    return len(code) == 40 and all(c in "0123456789ABCDEFabcdef" for c in code)

def normalize_currency(code: str) -> str:
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
    request_obj: Any,
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
    max_pages: Optional[int] = None,
    min_trustlines: int = 0,  # 新增参数
) -> List[Dict[str, Any]]:
    marker: Optional[str] = None
    all_lines: List[Dict[str, Any]] = []
    page = 0
    stats: Dict[str, int] = {}  # 实时统计每个货币的信任线数量

    print(f"[info] 开始扫描，目标min_trustlines={min_trustlines}")
    
    while True:
        page += 1
        req = AccountLines(
            account=issuer,
            ledger_index="validated",
            limit=limit,
            marker=marker
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
        
        # 实时统计
        for line in lines:
            currency_raw = line.get("currency", "UNKNOWN")
            currency = normalize_currency(currency_raw)
            stats[currency] = stats.get(currency, 0) + 1
        
        total_lines = len(all_lines)
        qualified_assets = sum(1 for count in stats.values() if count >= min_trustlines)
        
        print(f"[info] page {page}: {len(lines)} lines (总计 {total_lines:,}) | "
              f"合格资产: {qualified_assets} (>= {min_trustlines}) | "
              f"资产种类: {len(stats)}")
        
        # 🔥 智能停止条件
        marker = result.get("marker")
        if max_pages and page >= max_pages:
            print(f"[info] 达到最大页数 {max_pages}，提前停止")
            break
        if not marker:
            print("[info] 无更多分页，扫描完成")
            break
        
        # 🚀 如果找到足够合格资产，提前停止（避免无限抓取）
        if qualified_assets >= 10 and total_lines > 2000:  # 可调整阈值
            print(f"[info] 已找到 {qualified_assets} 个合格资产，自动停止分页")
            break

    print(f"[ok] 扫描完成！总信任线: {len(all_lines):,}，合格资产: {qualified_assets}")
    return all_lines

def aggregate_lines(issuer: str, lines: List[Dict[str, Any]]) -> List[AssetStats]:
    grouped_holders: Dict[Tuple[str, str], Set[str]] = {}
    grouped_counts: Dict[Tuple[str, str], int] = {}

    for line in lines:
        currency_raw = line.get("currency", "UNKNOWN")
        currency = normalize_currency(currency_raw)
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

def sort_asset_results(rows: List[AssetStats], sort_by: str) -> List[AssetStats]:
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

def filter_asset_results(
    rows: List[AssetStats],
    min_trustlines: int,
    top: Optional[int],
) -> List[AssetStats]:
    filtered = [row for row in rows if row.trustlines_count >= min_trustlines]
    if top is not None:
        filtered = filtered[:top]
    return filtered

def write_asset_json(rows: List[AssetStats], out_path: Optional[str]) -> None:
    data = [asdict(r) for r in rows]
    text = json.dumps(data, indent=2, ensure_ascii=False)
    
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[ok] wrote JSON to {out_path}")
    else:
        print(text)

def write_asset_csv(rows: List[AssetStats], out_path: Optional[str]) -> None:
    if not out_path:
        raise ValueError("--out is required when --format csv is used")
    
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["issuer_address", "currency_code", "trustlines_count", "unique_holders"])
        for row in rows:
            writer.writerow([row.issuer, row.currency, row.trustlines_count, row.unique_holders])
    print(f"[ok] wrote CSV to {out_path}")

def fetch_ripple_state_issuers(
    client: JsonRpcClient,
    limit: int,
    retries: int,
    backoff: float,
    rate_limit_seconds: float,
    max_pages: Optional[int] = None,
) -> List[IssuerSummary]:
    marker: Optional[str] = None
    page = 0
    issuer_counts: Dict[str, int] = {}
    issuer_currencies: Dict[str, Set[str]] = {}

    while True:
        page += 1
        req = LedgerData(
            ledger_index="validated",
            limit=limit,
            marker=marker,
            binary=False,
        )
        
        result = request_with_retry(
            client=client,
            request_obj=req,
            retries=retries,
            backoff=backoff,
            rate_limit_seconds=rate_limit_seconds,
        )
        
        state_objects = 0
        for item in result.get("state", []):
            if item.get("LedgerEntryType") != "RippleState":
                continue

            state_objects += 1
            low_limit = item.get("LowLimit", {})
            high_limit = item.get("HighLimit", {})

            low_issuer = low_limit.get("issuer")
            high_issuer = high_limit.get("issuer")
            low_currency = normalize_currency(low_limit.get("currency", "UNKNOWN"))
            high_currency = normalize_currency(high_limit.get("currency", "UNKNOWN"))

            if low_issuer:
                issuer_counts[low_issuer] = issuer_counts.get(low_issuer, 0) + 1
                issuer_currencies.setdefault(low_issuer, set()).add(low_currency)

            if high_issuer:
                issuer_counts[high_issuer] = issuer_counts.get(high_issuer, 0) + 1
                issuer_currencies.setdefault(high_issuer, set()).add(high_currency)

        eprint(
            f"[info] network page {page}: processed {state_objects} RippleState objects "
            f"(issuers so far: {len(issuer_counts)})"
        )

        marker = result.get("marker")
        if max_pages is not None and page >= max_pages:
            eprint(f"[info] reached max_pages={max_pages}, stopping early")
            break
        if not marker:
            break

    rows: List[IssuerSummary] = []
    for issuer, count in issuer_counts.items():
        rows.append(
            IssuerSummary(
                issuer=issuer,
                trustline_objects=count,
                discovered_currencies=len(issuer_currencies.get(issuer, set())),
            )
        )
    rows.sort(key=lambda x: (-x.trustline_objects, -x.discovered_currencies, x.issuer))
    return rows

def filter_issuer_results(
    rows: List[IssuerSummary],
    min_trustlines: int,
    top: Optional[int],
) -> List[IssuerSummary]:
    filtered = [row for row in rows if row.trustline_objects >= min_trustlines]
    if top is not None:
        filtered = filtered[:top]
    return filtered

def print_issuer_table(rows: List[IssuerSummary]) -> None:
    if not rows:
        print("No results.")
        return

    headers = ["Issuer Address", "Trustline Objects", "Discovered Currencies"]
    widths = [42, 20, 22]  # 增加地址宽度到42字符（完整显示大部分地址）
    
    fmt = (
        f"{{:<{widths[0]}}} "
        f"{{:>{widths[1]}}} "
        f"{{:>{widths[2]}}}"
    )
    
    print(fmt.format(*headers))
    print("-" * (sum(widths) + 4))
    for row in rows:
        # 完整显示地址，不截断
        addr_display = row.issuer
        print(fmt.format(addr_display, row.trustline_objects, row.discovered_currencies))

def print_asset_table(rows: List[AssetStats]) -> None:
    if not rows:
        print("No results.")
        return

    headers = ["Issuer Address", "Currency Code", "Trustlines Count", "Unique Holders"]
    widths = [42, 20, 18, 16]  # 增加地址宽度
    
    fmt = (
        f"{{:<{widths[0]}}} "
        f"{{:<{widths[1]}}} "
        f"{{:>{widths[2]}}} "
        f"{{:>{widths[3]}}}"
    )
    
    print(fmt.format(*headers))
    print("-" * (sum(widths) + 6))
    for row in rows:
        # 完整显示地址
        addr_display = row.issuer
        print(fmt.format(addr_display, row.currency, row.trustlines_count, row.unique_holders))


def write_issuer_json(rows: List[IssuerSummary], out_path: Optional[str]) -> None:
    data = [asdict(r) for r in rows]
    text = json.dumps(data, indent=2, ensure_ascii=False)
    
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[ok] wrote JSON to {out_path}")
    else:
        print(text)

def write_issuer_csv(rows: List[IssuerSummary], out_path: Optional[str]) -> None:
    if not out_path:
        raise ValueError("--out is required when --format csv is used")
    
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["issuer_address", "trustline_objects", "discovered_currencies"])
        for row in rows:
            writer.writerow([row.issuer, row.trustline_objects, row.discovered_currencies])
    print(f"[ok] wrote CSV to {out_path}")

def run_top_assets(args: argparse.Namespace) -> int:
    """Rank assets by number of trustlines discovered."""
    client = make_client(args.rpc_url)
    marker: Optional[str] = None
    page = 0
    assets: Dict[str, int] = {}

    print("[info] scanning assets across network...")
    
    while True:
        page += 1
        req = LedgerData(
            ledger_index="validated",
            limit=200,
            marker=marker,
            binary=False,
        )
        
        result = request_with_retry(
            client=client,
            request_obj=req,
            retries=args.retries,
            backoff=args.retry_backoff,
            rate_limit_seconds=args.rate_limit,
        )

        for obj in result.get("state", []):
            if obj.get("LedgerEntryType") != "RippleState":
                continue
            
            # 修复：安全访问嵌套字典
            low_limit = obj.get("LowLimit", {})
            currency_raw = low_limit.get("currency", "")
            if currency_raw:
                currency = normalize_currency(currency_raw)
                assets[currency] = assets.get(currency, 0) + 1

        marker = result.get("marker")
        print(f"[info] page {page}")
        
        if not marker or page >= 5:
            break

    ranked = sorted(assets.items(), key=lambda x: x[1], reverse=True)
    
    print("\nAsset Trustlines")
    print("-----------------------")
    for asset, count in ranked[:args.limit]:
        print(f"{asset:10} {count}")
    
    return 0

def validate_common_args(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        eprint("[error] --limit must be > 0")
        return 2
    
    if args.max_pages is not None and args.max_pages <= 0:
        eprint("[error] --max-pages must be > 0")
        return 2
    
    if args.min_trustlines < 0:
        eprint("[error] --min-trustlines must be >= 0")
        return 2
    
    if args.top is not None and args.top <= 0:
        eprint("[error] --top must be > 0")
        return 2
    
    if args.limit > MAX_LIMIT:
        eprint(f"[warn] --limit capped from {args.limit} to {MAX_LIMIT}")
        args.limit = MAX_LIMIT
    
    return 0

def run_scan(args: argparse.Namespace) -> int:
    if not args.issuer:
        eprint("[error] requires --issuer")
        return 2

    rc = validate_common_args(args)
    if rc != 0:
        return rc

    client = make_client(args.rpc_url)
    
    eprint(f"[info] rpc_url={args.rpc_url}")
    eprint(f"[info] issuer={args.issuer}")
    eprint(f"[info] limit={args.limit}")
    if args.max_pages:
        eprint(f"[info] max_pages={args.max_pages}")
    if args.min_trustlines:
        eprint(f"[info] min_trustlines={args.min_trustlines}")
    if args.top:
        eprint(f"[info] top={args.top}")
    eprint("[info] fetching trust lines...")

    try:
        # 在 run_scan 函数中修改调用
        lines = fetch_account_lines(
            client=client,
            issuer=args.issuer,
            limit=args.limit,
            retries=args.retries,
            backoff=args.retry_backoff,
            rate_limit_seconds=args.rate_limit,
            max_pages=args.max_pages,
            min_trustlines=args.min_trustlines,  # 传入参数
        )

    except Exception as exc:
        eprint(f"[error] failed to fetch account lines: {exc}")
        return 1

    eprint(f"[info] fetched {len(lines)} trust lines total")

    rows = aggregate_lines(args.issuer, lines)
    rows = sort_asset_results(rows, args.sort)
    rows = filter_asset_results(rows, args.min_trustlines, args.top)

    if args.format == "table":
        print_asset_table(rows)
        return 0
    
    if args.format == "json":
        write_asset_json(rows, args.out)
        return 0
    
    if args.format == "csv":
        try:
            write_asset_csv(rows, args.out)
        except Exception as exc:
            eprint(f"[error] failed to write CSV: {exc}")
            return 1
        return 0

    eprint(f"[error] unsupported format: {args.format}")
    return 2

def run_scan_network(args: argparse.Namespace) -> int:
    rc = validate_common_args(args)
    if rc != 0:
        return rc

    client = make_client(args.rpc_url)
    
    eprint(f"[info] rpc_url={args.rpc_url}")
    eprint(f"[info] limit={args.limit}")
    if args.max_pages:
        eprint(f"[info] max_pages={args.max_pages}")
    if args.min_trustlines:
        eprint(f"[info] min_trustlines={args.min_trustlines}")
    if args.top:
        eprint(f"[info] top={args.top}")
    eprint("[info] scanning network for issuers via RippleState...")

    try:
        rows = fetch_ripple_state_issuers(
            client=client,
            limit=args.limit,
            retries=args.retries,
            backoff=args.retry_backoff,
            rate_limit_seconds=args.rate_limit,
            max_pages=args.max_pages,
        )
    except Exception as exc:
        eprint(f"[error] failed to scan network issuers: {exc}")
        return 1

    rows = filter_issuer_results(rows, args.min_trustlines, args.top)

    if args.format == "table":
        print_issuer_table(rows)
        return 0
    
    if args.format == "json":
        write_issuer_json(rows, args.out)
        return 0
    
    if args.format == "csv":
        try:
            write_issuer_csv(rows, args.out)
        except Exception as exc:
            eprint(f"[error] failed to write CSV: {exc}")
            return 1
        return 0

    eprint(f"[error] unsupported format: {args.format}")
    return 2

def run_top_issuers(args: argparse.Namespace) -> int:
    """Top issuers by trustline count, reuse scan-network."""
    print("[info] ranking issuers...")
    args.top = args.limit  # 设置top限制
    return run_scan_network(args)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="monitor.py",
        description="XRPL Issuer / Trustline Scanner v0.4",
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # scan
    scan = subparsers.add_parser(
        "scan",
        help="Scan trust-line assets for a given issuer",
    )
    scan.add_argument("--issuer", type=str, required=True, help="Issuer account address")
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
        "--max-pages",
        type=int,
        default=None,
        help="Stop after this many pages",
    )
    scan.add_argument(
        "--min-trustlines",
        type=int,
        default=0,
        help="Only include assets with at least this many trustlines",
    )
    scan.add_argument(
        "--top",
        type=int,
        default=None,
        help="Only show the top N results after sorting/filtering",
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

    # scan-network
    network = subparsers.add_parser(
        "scan-network",
        help="Discover issuers from RippleState objects across XRPL",
    )
    network.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Page size per request (default: {DEFAULT_LIMIT})",
    )
    network.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Stop after this many ledger_data pages",
    )
    network.add_argument(
        "--min-trustlines",
        type=int,
        default=0,
        help="Only include issuers with at least this many discovered trustline objects",
    )
    network.add_argument(
        "--top",
        type=int,
        default=20,
        help="Only show the top N issuers after filtering",
    )
    network.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format",
    )
    network.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output file path (required for csv, optional for json)",
    )
    network.add_argument(
        "--rpc-url",
        type=str,
        default=DEFAULT_RPC_URL,
        help="XRPL JSON-RPC URL",
    )
    network.add_argument(
        "--rate-limit",
        type=float,
        default=DEFAULT_RATE_LIMIT_SECONDS,
        help=f"Seconds to sleep before each request (default: {DEFAULT_RATE_LIMIT_SECONDS})",
    )
    network.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"Max retry attempts (default: {DEFAULT_RETRIES})",
    )
    network.add_argument(
        "--retry-backoff",
        type=float,
        default=DEFAULT_RETRY_BACKOFF,
        help=f"Exponential retry backoff base (default: {DEFAULT_RETRY_BACKOFF})",
    )

    # top-assets
    top_assets = subparsers.add_parser(
        "top-assets",
        help="Show top assets by trustlines",
    )
    top_assets.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of assets to display",
    )
    top_assets.add_argument(
        "--rpc-url",
        type=str,
        default=DEFAULT_RPC_URL,
        help="XRPL JSON-RPC URL",
    )
    top_assets.add_argument(
        "--rate-limit",
        type=float,
        default=DEFAULT_RATE_LIMIT_SECONDS,
        help=f"Seconds to sleep before each request (default: {DEFAULT_RATE_LIMIT_SECONDS})",
    )
    top_assets.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"Max retry attempts (default: {DEFAULT_RETRIES})",
    )
    top_assets.add_argument(
        "--retry-backoff",
        type=float,
        default=DEFAULT_RETRY_BACKOFF,
        help=f"Exponential retry backoff base (default: {DEFAULT_RETRY_BACKOFF})",
    )

    # top-issuers
    top_issuers = subparsers.add_parser(
        "top-issuers",
        help="Show top issuers by trustlines",
    )
    top_issuers.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of issuers to display (also sets --top)",
    )
    top_issuers.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Stop after this many ledger_data pages",
    )
    top_issuers.add_argument(
        "--min-trustlines",
        type=int,
        default=0,
        help="Only include issuers with at least this many discovered trustline objects",
    )
    top_issuers.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format",
    )
    top_issuers.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output file path (required for csv, optional for json)",
    )
    top_issuers.add_argument(
        "--rpc-url",
        type=str,
        default=DEFAULT_RPC_URL,
        help="XRPL JSON-RPC URL",
    )
    top_issuers.add_argument(
        "--rate-limit",
        type=float,
        default=DEFAULT_RATE_LIMIT_SECONDS,
        help=f"Seconds to sleep before each request (default: {DEFAULT_RATE_LIMIT_SECONDS})",
    )
    top_issuers.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"Max retry attempts (default: {DEFAULT_RETRIES})",
    )
    top_issuers.add_argument(
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
    elif args.command == "scan-network":
        return run_scan_network(args)
    elif args.command == "top-assets":
        return run_top_assets(args)
    elif args.command == "top-issuers":
        return run_top_issuers(args)
    else:
        eprint(f"[error] unknown command: {args.command}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
