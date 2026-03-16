#!/usr/bin/env python3
"""
XRPL Issuer / Trustline Scanner v0.8

Key improvements
- unified pager for account_lines / ledger_data
- streaming aggregation (no need to keep all trustlines in memory for scan)
- progress stats with elapsed / avg page / ETA
- --max-pages 0 means unlimited
- optional resume state for long scans
- jsonl output support
- whale top-holder preview
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountLines, LedgerData

DEFAULT_RPC_URL = "https://s1.ripple.com:51234/"
DEFAULT_LIMIT = 200
MAX_LIMIT = 400
DEFAULT_RATE_LIMIT_SECONDS = 0.15
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


class ProgressTracker:
    def __init__(self, label: str, max_pages: Optional[int]) -> None:
        self.label = label
        self.max_pages = max_pages
        self.start = time.time()

    def format_line(self, page: int, added: int, total: int, extra: str = "") -> str:
        elapsed = max(time.time() - self.start, 1e-9)
        avg_page = elapsed / page
        eta_text = "ETA ?"
        if self.max_pages:
            remaining_pages = max(self.max_pages - page, 0)
            eta_s = remaining_pages * avg_page
            eta_text = f"ETA {format_duration(eta_s)}"
        pieces = [
            f"[info] {self.label} page {page}",
            f"+{added}",
            f"total {total:,}",
            f"elapsed {format_duration(elapsed)}",
            f"avg/page {avg_page:.2f}s",
            eta_text,
        ]
        if extra:
            pieces.append(extra)
        return " | ".join(pieces)


class PagerStoppedEarly(Exception):
    pass


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def format_duration(seconds: float) -> str:
    seconds = max(int(round(seconds)), 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}h {m:02d}m {s:02d}s"
    return f"{m:02d}m {s:02d}s"


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


def load_resume_state(path: Optional[str], expected_kind: str, expected_account: Optional[str] = None) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("kind") != expected_kind:
        raise ValueError(f"resume state kind mismatch: expected {expected_kind}, got {data.get('kind')}")
    if expected_account and data.get("account") and data.get("account") != expected_account:
        raise ValueError("resume state account does not match current --issuer")
    return data


def save_resume_state(path: Optional[str], payload: Dict[str, Any]) -> None:
    if not path:
        return
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def clear_resume_state(path: Optional[str]) -> None:
    if path:
        p = Path(path)
        if p.exists():
            p.unlink()


def xrpl_pager(
    *,
    client: JsonRpcClient,
    request_factory: Callable[[Optional[Any], int], Any],
    result_key: str,
    limit: int,
    retries: int,
    backoff: float,
    rate_limit_seconds: float,
    max_pages: Optional[int],
    resume_state_path: Optional[str] = None,
    resume_kind: Optional[str] = None,
    resume_account: Optional[str] = None,
    progress_label: str = "scan",
) -> Iterator[Tuple[int, List[Dict[str, Any]], Dict[str, Any]]]:
    state = load_resume_state(resume_state_path, resume_kind, resume_account) if resume_kind else {}
    marker = state.get("marker")
    page = int(state.get("pages", 0))
    item_total = int(state.get("items_total", 0))
    tracker = ProgressTracker(progress_label, max_pages)

    if page:
        print(f"[info] resumed {progress_label}: page={page} | items_total={item_total:,}", flush=True)

    while True:
        if max_pages is not None and page >= max_pages:
            raise PagerStoppedEarly()

        req = request_factory(marker, limit)
        result = request_with_retry(
            client=client,
            request_obj=req,
            retries=retries,
            backoff=backoff,
            rate_limit_seconds=rate_limit_seconds,
        )
        items = result.get(result_key, []) or []
        next_marker = result.get("marker")
        page += 1
        item_total += len(items)

        save_resume_state(
            resume_state_path,
            {
                "kind": resume_kind,
                "account": resume_account,
                "marker": next_marker,
                "pages": page,
                "items_total": item_total,
                "updated_at": int(time.time()),
            },
        )

        yield page, items, result

        marker = next_marker
        if not marker:
            break


def sort_asset_results(rows: List[AssetStats], sort_by: str) -> List[AssetStats]:
    if sort_by == "trustlines":
        return sorted(rows, key=lambda x: (-x.trustlines_count, -x.unique_holders, x.currency))
    if sort_by == "holders":
        return sorted(rows, key=lambda x: (-x.unique_holders, -x.trustlines_count, x.currency))
    if sort_by == "currency":
        return sorted(rows, key=lambda x: (x.currency, x.issuer))
    return rows


def filter_asset_results(rows: List[AssetStats], min_trustlines: int, top: Optional[int]) -> List[AssetStats]:
    filtered = [row for row in rows if row.trustlines_count >= min_trustlines]
    return filtered[:top] if top is not None else filtered


def filter_issuer_results(rows: List[IssuerSummary], min_trustlines: int, top: Optional[int]) -> List[IssuerSummary]:
    filtered = [row for row in rows if row.trustline_objects >= min_trustlines]
    return filtered[:top] if top is not None else filtered


def print_asset_table(rows: List[AssetStats]) -> None:
    if not rows:
        print("No results.")
        return
    headers = ["Issuer Address", "Currency Code", "Trustlines Count", "Unique Holders"]
    widths = [42, 20, 18, 16]
    fmt = f"{{:<{widths[0]}}} {{:<{widths[1]}}} {{:>{widths[2]}}} {{:>{widths[3]}}}"
    print(fmt.format(*headers))
    print("-" * (sum(widths) + 6))
    for row in rows:
        print(fmt.format(row.issuer, row.currency, row.trustlines_count, row.unique_holders))


def print_issuer_table(rows: List[IssuerSummary]) -> None:
    if not rows:
        print("No results.")
        return
    headers = ["Issuer Address", "Trustline Objects", "Discovered Currencies"]
    widths = [42, 20, 22]
    fmt = f"{{:<{widths[0]}}} {{:>{widths[1]}}} {{:>{widths[2]}}}"
    print(fmt.format(*headers))
    print("-" * (sum(widths) + 4))
    for row in rows:
        print(fmt.format(row.issuer, row.trustline_objects, row.discovered_currencies))


def write_json(rows: Sequence[Any], out_path: Optional[str]) -> None:
    data = [asdict(r) for r in rows]
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        print(f"[ok] wrote JSON to {out_path}")
    else:
        print(text)


def write_jsonl(rows: Sequence[Any], out_path: Optional[str]) -> None:
    if not out_path:
        raise ValueError("--out is required when --format jsonl is used")
    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
    print(f"[ok] wrote JSONL to {out_path}")


def write_asset_csv(rows: Sequence[AssetStats], out_path: Optional[str]) -> None:
    if not out_path:
        raise ValueError("--out is required when --format csv is used")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["issuer_address", "currency_code", "trustlines_count", "unique_holders"])
        for row in rows:
            writer.writerow([row.issuer, row.currency, row.trustlines_count, row.unique_holders])
    print(f"[ok] wrote CSV to {out_path}")


def write_issuer_csv(rows: Sequence[IssuerSummary], out_path: Optional[str]) -> None:
    if not out_path:
        raise ValueError("--out is required when --format csv is used")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["issuer_address", "trustline_objects", "discovered_currencies"])
        for row in rows:
            writer.writerow([row.issuer, row.trustline_objects, row.discovered_currencies])
    print(f"[ok] wrote CSV to {out_path}")


def validate_positive_or_unlimited(value: Optional[int], name: str) -> Optional[int]:
    if value is None:
        return None
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    if value == 0:
        return None
    return value


def validate_common_args(args: argparse.Namespace, *, supports_top: bool = True, supports_min: bool = True) -> int:
    try:
        if args.limit <= 0:
            raise ValueError("--limit must be > 0")
        if args.limit > MAX_LIMIT:
            eprint(f"[warn] --limit capped from {args.limit} to {MAX_LIMIT}")
            args.limit = MAX_LIMIT
        args.max_pages = validate_positive_or_unlimited(getattr(args, "max_pages", None), "--max-pages")
        if supports_min and getattr(args, "min_trustlines", 0) < 0:
            raise ValueError("--min-trustlines must be >= 0")
        if supports_top and getattr(args, "top", None) is not None and args.top <= 0:
            raise ValueError("--top must be > 0")
        if args.retries <= 0:
            raise ValueError("--retries must be > 0")
        if args.retry_backoff <= 1.0:
            raise ValueError("--retry-backoff must be > 1.0")
        if args.rate_limit < 0:
            raise ValueError("--rate-limit must be >= 0")
    except ValueError as exc:
        eprint(f"[error] {exc}")
        return 2
    return 0


def rows_from_asset_counters(issuer: str, counts: Counter[str], holders: Dict[str, Set[str]]) -> List[AssetStats]:
    rows: List[AssetStats] = []
    for currency, count in counts.items():
        rows.append(
            AssetStats(
                issuer=issuer,
                currency=currency,
                trustlines_count=count,
                unique_holders=len(holders.get(currency, set())),
            )
        )
    return rows


def render_asset_output(rows: List[AssetStats], fmt: str, out: Optional[str]) -> int:
    if fmt == "table":
        print_asset_table(rows)
        return 0
    if fmt == "json":
        write_json(rows, out)
        return 0
    if fmt == "jsonl":
        write_jsonl(rows, out)
        return 0
    if fmt == "csv":
        write_asset_csv(rows, out)
        return 0
    eprint(f"[error] unsupported format: {fmt}")
    return 2


def render_issuer_output(rows: List[IssuerSummary], fmt: str, out: Optional[str]) -> int:
    if fmt == "table":
        print_issuer_table(rows)
        return 0
    if fmt == "json":
        write_json(rows, out)
        return 0
    if fmt == "jsonl":
        write_jsonl(rows, out)
        return 0
    if fmt == "csv":
        write_issuer_csv(rows, out)
        return 0
    eprint(f"[error] unsupported format: {fmt}")
    return 2


def run_scan(args: argparse.Namespace) -> int:
    rc = validate_common_args(args)
    if rc != 0:
        return rc

    client = make_client(args.rpc_url)
    counts: Counter[str] = Counter()
    holders: Dict[str, Set[str]] = defaultdict(set)
    progress = ProgressTracker("scan", args.max_pages)

    print(f"[info] RPC: {args.rpc_url}")
    print(f"[info] issuer: {args.issuer}")
    print(f"[info] page size: {args.limit}")
    print(f"[info] max pages: {args.max_pages or 'unlimited'}")
    print(f"[info] min trustlines: {args.min_trustlines}")

    try:
        for page, lines, _ in xrpl_pager(
            client=client,
            request_factory=lambda marker, limit: AccountLines(
                account=args.issuer,
                ledger_index="validated",
                limit=limit,
                marker=marker,
            ),
            result_key="lines",
            limit=args.limit,
            retries=args.retries,
            backoff=args.retry_backoff,
            rate_limit_seconds=args.rate_limit,
            max_pages=args.max_pages,
            resume_state_path=args.resume,
            resume_kind="account_lines",
            resume_account=args.issuer,
            progress_label="scan",
        ):
            for line in lines:
                currency = normalize_currency(line.get("currency", "UNKNOWN"))
                counts[currency] += 1
                holder = line.get("account")
                if holder:
                    holders[currency].add(holder)
            qualified = sum(1 for count in counts.values() if count >= args.min_trustlines)
            print(
                progress.format_line(
                    page,
                    len(lines),
                    sum(counts.values()),
                    extra=f"qualified assets {qualified} | asset types {len(counts)}",
                ),
                flush=True,
            )
    except PagerStoppedEarly:
        print(f"[info] reached max-pages={args.max_pages}, stopping early", flush=True)
    except KeyboardInterrupt:
        print("\n[warn] scan interrupted by user")
        return 130
    except Exception as exc:
        eprint(f"[error] failed to fetch trustlines: {exc}")
        return 1

    rows = rows_from_asset_counters(args.issuer, counts, holders)
    rows = sort_asset_results(rows, args.sort)
    rows = filter_asset_results(rows, args.min_trustlines, args.top)
    print(f"[ok] scan complete | trustlines={sum(counts.values()):,} | assets={len(counts)}")
    clear_resume_state(args.resume)
    return render_asset_output(rows, args.format, args.out)


def run_issuer_health(args: argparse.Namespace) -> int:
    rc = validate_common_args(args, supports_top=False, supports_min=False)
    if rc != 0:
        return rc

    client = make_client(args.rpc_url)
    asset_counts: Counter[str] = Counter()
    progress = ProgressTracker("issuer-health", args.max_pages)

    print(f"[info] scanning issuer ecosystem: {args.issuer} | limit={args.limit}")
    try:
        for page, lines, _ in xrpl_pager(
            client=client,
            request_factory=lambda marker, limit: AccountLines(
                account=args.issuer,
                ledger_index="validated",
                limit=limit,
                marker=marker,
            ),
            result_key="lines",
            limit=args.limit,
            retries=args.retries,
            backoff=args.retry_backoff,
            rate_limit_seconds=args.rate_limit,
            max_pages=args.max_pages,
            resume_state_path=args.resume,
            resume_kind="account_lines",
            resume_account=args.issuer,
            progress_label="issuer-health",
        ):
            for line in lines:
                asset_counts[normalize_currency(line.get("currency", "UNKNOWN"))] += 1
            print(
                progress.format_line(
                    page,
                    len(lines),
                    sum(asset_counts.values()),
                    extra=f"tokens {len(asset_counts)}",
                ),
                flush=True,
            )
    except PagerStoppedEarly:
        print(f"[info] reached max-pages={args.max_pages}, stopping early", flush=True)
    except KeyboardInterrupt:
        print("\n[warn] scan interrupted by user")
        return 130
    except Exception as exc:
        eprint(f"[error] issuer-health failed: {exc}")
        return 1

    clear_resume_state(args.resume)
    real_tokens = sorted(((c, n) for c, n in asset_counts.items() if n >= 1000), key=lambda x: -x[1])
    minor_tokens = sorted(((c, n) for c, n in asset_counts.items() if 10 <= n < 1000), key=lambda x: -x[1])
    noise_tokens = sorted(((c, n) for c, n in asset_counts.items() if n < 10), key=lambda x: -x[1])
    total = len(asset_counts)
    health_score = round(len(real_tokens) / total, 3) if total else 0.0

    print("\nIssuer Ecosystem Health\n")
    print(f"Issuer: {args.issuer}")
    print(f"Total tokens discovered: {total}\n")
    print("Real Tokens (>=1000 trustlines)")
    print("--------------------------------")
    for c, n in real_tokens:
        print(f"{c:<15} {n}")
    print("\nMinor Tokens (10-999 trustlines)")
    print("--------------------------------")
    for c, n in minor_tokens:
        print(f"{c:<15} {n}")
    print("\nNoise Tokens (<10 trustlines)")
    print("-----------------------------")
    for c, n in noise_tokens:
        print(f"{c:<15} {n}")
    print("\nEcosystem Health Score")
    print("----------------------")
    print(health_score)
    return 0


def run_whale_concentration(args: argparse.Namespace) -> int:
    rc = validate_common_args(args, supports_top=False, supports_min=False)
    if rc != 0:
        return rc

    client = make_client(args.rpc_url)
    target_token = normalize_currency(args.token)
    balances: List[Tuple[str, float]] = []
    progress = ProgressTracker("whale", args.max_pages)
    total_lines = 0

    print(
        f"[info] scanning holders for {target_token}:{args.issuer} | limit={args.limit} | rate-limit={args.rate_limit}s",
        flush=True,
    )
    try:
        for page, lines, _ in xrpl_pager(
            client=client,
            request_factory=lambda marker, limit: AccountLines(
                account=args.issuer,
                ledger_index="validated",
                limit=limit,
                marker=marker,
            ),
            result_key="lines",
            limit=args.limit,
            retries=args.retries,
            backoff=args.retry_backoff,
            rate_limit_seconds=args.rate_limit,
            max_pages=args.max_pages,
            resume_state_path=args.resume,
            resume_kind="account_lines",
            resume_account=args.issuer,
            progress_label="whale",
        ):
            matched = 0
            total_lines += len(lines)
            for line in lines:
                currency = normalize_currency(line.get("currency", ""))
                if currency != target_token:
                    continue
                holder = line.get("account", "")
                try:
                    balance = abs(float(line.get("balance", 0)))
                except (TypeError, ValueError):
                    continue
                if balance > 0:
                    balances.append((holder, balance))
                    matched += 1
            print(
                progress.format_line(
                    page,
                    len(lines),
                    total_lines,
                    extra=f"matched {target_token} +{matched} | holders {len(balances):,}",
                ),
                flush=True,
            )
    except PagerStoppedEarly:
        print(f"[info] reached max-pages={args.max_pages}, stopping early", flush=True)
    except KeyboardInterrupt:
        print("\n[warn] scan interrupted by user")
        return 130
    except Exception as exc:
        eprint(f"[error] whale-concentration failed: {exc}")
        return 1

    clear_resume_state(args.resume)
    if not balances:
        print("No holders found.")
        return 0

    balances.sort(key=lambda x: x[1], reverse=True)
    total_balance = sum(balance for _, balance in balances)

    def concentration(n: int) -> float:
        top_sum = sum(balance for _, balance in balances[:n])
        return round((top_sum / total_balance) * 100, 2) if total_balance else 0.0

    print("\nWhale Concentration Report")
    print(f"Token: {target_token}")
    print(f"Issuer: {args.issuer}")
    print(f"Total holders scanned: {len(balances):,}")
    print(f"Total token balance   : {total_balance:,.6f}")
    print(f"Top 10 holders  : {concentration(10)}%")
    print(f"Top 50 holders  : {concentration(50)}%")
    print(f"Top 100 holders : {concentration(100)}%")
    print(f"Top 500 holders : {concentration(500)}%")

    preview_n = max(args.top_holders, 0)
    if preview_n:
        print(f"\nTop {preview_n} holders")
        print("-" * 72)
        for idx, (holder, balance) in enumerate(balances[:preview_n], start=1):
            pct = (balance / total_balance * 100) if total_balance else 0.0
            print(f"{idx:>4}. {holder:<36} {balance:>18,.6f}  {pct:>7.3f}%")
    return 0


def fetch_ripple_state_issuers(args: argparse.Namespace) -> List[IssuerSummary]:
    client = make_client(args.rpc_url)
    issuer_counts: Counter[str] = Counter()
    issuer_currencies: Dict[str, Set[str]] = defaultdict(set)
    progress = ProgressTracker("network", args.max_pages)
    state_objects = 0

    try:
        for page, state, _ in xrpl_pager(
            client=client,
            request_factory=lambda marker, limit: LedgerData(
                ledger_index="validated",
                limit=limit,
                marker=marker,
                binary=False,
            ),
            result_key="state",
            limit=args.limit,
            retries=args.retries,
            backoff=args.retry_backoff,
            rate_limit_seconds=args.rate_limit,
            max_pages=args.max_pages,
            resume_state_path=args.resume,
            resume_kind="ledger_data",
            progress_label="network",
        ):
            ripple_state_count = 0
            for item in state:
                if item.get("LedgerEntryType") != "RippleState":
                    continue
                ripple_state_count += 1
                state_objects += 1
                low_limit = item.get("LowLimit", {})
                high_limit = item.get("HighLimit", {})
                low_issuer = low_limit.get("issuer")
                high_issuer = high_limit.get("issuer")
                low_currency = normalize_currency(low_limit.get("currency", "UNKNOWN"))
                high_currency = normalize_currency(high_limit.get("currency", "UNKNOWN"))
                if low_issuer:
                    issuer_counts[low_issuer] += 1
                    issuer_currencies[low_issuer].add(low_currency)
                if high_issuer:
                    issuer_counts[high_issuer] += 1
                    issuer_currencies[high_issuer].add(high_currency)
            eprint(
                progress.format_line(
                    page,
                    ripple_state_count,
                    state_objects,
                    extra=f"issuers {len(issuer_counts)}",
                )
            )
    except PagerStoppedEarly:
        eprint(f"[info] reached max-pages={args.max_pages}, stopping early")
    except KeyboardInterrupt:
        raise

    clear_resume_state(args.resume)
    rows = [
        IssuerSummary(
            issuer=issuer,
            trustline_objects=count,
            discovered_currencies=len(issuer_currencies.get(issuer, set())),
        )
        for issuer, count in issuer_counts.items()
    ]
    rows.sort(key=lambda x: (-x.trustline_objects, -x.discovered_currencies, x.issuer))
    return rows


def run_scan_network(args: argparse.Namespace) -> int:
    rc = validate_common_args(args)
    if rc != 0:
        return rc
    eprint(f"[info] rpc_url={args.rpc_url}")
    eprint(f"[info] limit={args.limit}")
    eprint(f"[info] max_pages={args.max_pages or 'unlimited'}")
    try:
        rows = fetch_ripple_state_issuers(args)
    except KeyboardInterrupt:
        eprint("\n[warn] scan interrupted by user")
        return 130
    except Exception as exc:
        eprint(f"[error] failed to scan network issuers: {exc}")
        return 1
    rows = filter_issuer_results(rows, args.min_trustlines, args.top)
    return render_issuer_output(rows, args.format, args.out)


def run_top_issuers(args: argparse.Namespace) -> int:
    print("[info] ranking issuers...")
    args.top = args.limit
    return run_scan_network(args)


def run_top_assets(args: argparse.Namespace) -> int:
    rc = validate_common_args(args, supports_top=False, supports_min=False)
    if rc != 0:
        return rc

    client = make_client(args.rpc_url)
    assets: Counter[str] = Counter()
    progress = ProgressTracker("top-assets", args.max_pages)

    print("[info] scanning assets across network...")
    try:
        for page, state, _ in xrpl_pager(
            client=client,
            request_factory=lambda marker, limit: LedgerData(
                ledger_index="validated",
                limit=limit,
                marker=marker,
                binary=False,
            ),
            result_key="state",
            limit=args.limit,
            retries=args.retries,
            backoff=args.retry_backoff,
            rate_limit_seconds=args.rate_limit,
            max_pages=args.max_pages,
            resume_state_path=args.resume,
            resume_kind="ledger_data",
            progress_label="top-assets",
        ):
            added = 0
            for obj in state:
                if obj.get("LedgerEntryType") != "RippleState":
                    continue
                low_limit = obj.get("LowLimit", {})
                currency_raw = low_limit.get("currency", "")
                if currency_raw:
                    assets[normalize_currency(currency_raw)] += 1
                    added += 1
            print(progress.format_line(page, added, sum(assets.values()), extra=f"assets {len(assets)}"), flush=True)
    except PagerStoppedEarly:
        print(f"[info] reached max-pages={args.max_pages}, stopping early", flush=True)
    except KeyboardInterrupt:
        print("\n[warn] scan interrupted by user")
        return 130
    except Exception as exc:
        eprint(f"[error] top-assets failed: {exc}")
        return 1

    clear_resume_state(args.resume)
    ranked = sorted(assets.items(), key=lambda x: x[1], reverse=True)
    print("\nAsset Trustlines")
    print("-----------------------")
    for asset, count in ranked[: args.show_limit]:
        print(f"{asset:10} {count}")
    return 0


def add_common_rpc_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rpc-url", type=str, default=DEFAULT_RPC_URL, help="XRPL JSON-RPC URL")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"Page size per request (default: {DEFAULT_LIMIT})")
    p.add_argument("--max-pages", type=int, default=0, help="Stop after this many pages; 0 means unlimited")
    p.add_argument("--rate-limit", type=float, default=DEFAULT_RATE_LIMIT_SECONDS, help=f"Seconds to sleep before each request (default: {DEFAULT_RATE_LIMIT_SECONDS})")
    p.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help=f"Max retry attempts (default: {DEFAULT_RETRIES})")
    p.add_argument("--retry-backoff", type=float, default=DEFAULT_RETRY_BACKOFF, help=f"Exponential retry backoff base (default: {DEFAULT_RETRY_BACKOFF})")
    p.add_argument("--resume", type=str, default=None, help="Path to resume state file for long scans")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="monitor.py", description="XRPL Issuer / Trustline Scanner v0.8")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Scan trust-line assets for a given issuer")
    scan.add_argument("--issuer", type=str, required=True, help="Issuer account address")
    scan.add_argument("--sort", choices=["trustlines", "holders", "currency"], default="trustlines", help="Sort output field")
    scan.add_argument("--min-trustlines", type=int, default=0, help="Only include assets with at least this many trustlines")
    scan.add_argument("--top", type=int, default=None, help="Only show the top N results after sorting/filtering")
    scan.add_argument("--format", choices=["table", "json", "jsonl", "csv"], default="table", help="Output format")
    scan.add_argument("--out", type=str, default=None, help="Output file path (required for csv/jsonl, optional for json)")
    add_common_rpc_args(scan)

    network = subparsers.add_parser("scan-network", help="Discover issuers from RippleState objects across XRPL")
    network.add_argument("--min-trustlines", type=int, default=0, help="Only include issuers with at least this many discovered trustline objects")
    network.add_argument("--top", type=int, default=20, help="Only show the top N issuers after filtering")
    network.add_argument("--format", choices=["table", "json", "jsonl", "csv"], default="table", help="Output format")
    network.add_argument("--out", type=str, default=None, help="Output file path (required for csv/jsonl, optional for json)")
    add_common_rpc_args(network)

    parser_health = subparsers.add_parser("issuer-health", help="Analyze issuer ecosystem health")
    parser_health.add_argument("--issuer", required=True)
    add_common_rpc_args(parser_health)

    parser_whale = subparsers.add_parser("whale-concentration", help="Analyze whale concentration for a token")
    parser_whale.add_argument("--issuer", required=True)
    parser_whale.add_argument("--token", required=True)
    parser_whale.add_argument("--top-holders", type=int, default=10, help="Show top N holders in the report")
    add_common_rpc_args(parser_whale)

    top_assets = subparsers.add_parser("top-assets", help="Show top assets by trustlines")
    top_assets.add_argument("--show-limit", type=int, default=20, help="Number of assets to display")
    add_common_rpc_args(top_assets)

    top_issuers = subparsers.add_parser("top-issuers", help="Show top issuers by trustlines")
    top_issuers.add_argument("--min-trustlines", type=int, default=0, help="Only include issuers with at least this many discovered trustline objects")
    top_issuers.add_argument("--format", choices=["table", "json", "jsonl", "csv"], default="table", help="Output format")
    top_issuers.add_argument("--out", type=str, default=None, help="Output file path (required for csv/jsonl, optional for json)")
    top_issuers.add_argument("--top", type=int, default=None, help=argparse.SUPPRESS)
    top_issuers.add_argument("--show-limit", type=int, default=10, help="Number of issuers to display")
    add_common_rpc_args(top_issuers)
    top_issuers.set_defaults(limit=DEFAULT_LIMIT)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scan":
        return run_scan(args)
    if args.command == "scan-network":
        return run_scan_network(args)
    if args.command == "issuer-health":
        return run_issuer_health(args)
    if args.command == "whale-concentration":
        return run_whale_concentration(args)
    if args.command == "top-assets":
        return run_top_assets(args)
    if args.command == "top-issuers":
        args.limit = DEFAULT_LIMIT
        args.top = args.show_limit
        return run_top_issuers(args)
    eprint(f"[error] unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
