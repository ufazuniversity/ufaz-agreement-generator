"""
UFAZ IT — Device Issuance Agreement generator
=============================================

With a CSV file (a Batch), produces one filled Device Issuance Agreement PDF per
row.  Without one, opens the Form to fill in agreements one at a time on screen:
in the terminal, or with --web in the browser.  All use the fillable PDF template
bundled with the package.

Usage
-----
    generate                          open the Form
    generate --web                    open the Form in the browser
    generate receivers.csv
    generate receivers.csv -o output --lock
    generate receivers.csv --config config.json

Run  generate --help  for all options.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from .agreement import build_header_map, fill_pdf, pdf_filename, row_to_fields
from .web import serve

# .form is imported in main(), only when the terminal Form is asked for: a server that serves
# the Form in the browser (app.py) needs neither it nor textual (see README, "in Docker").

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE / "template" / "UFAZ_IT_Device_Issuance_Agreement_Fillable.pdf"
DEFAULT_CONFIG = HERE / "config.json"


# ---------------------------------------------------------------------------
# Reading input rows
# ---------------------------------------------------------------------------
def read_rows(path: Path) -> tuple[list[str], list[dict]]:
    if path.suffix.lower() not in (".csv", ".txt"):
        sys.exit(f"Unsupported input file type: {path.suffix} (use .csv)")
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096); f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample.strip() else csv.excel
            delimiter = dialect.delimiter
        except csv.Error:  # rows with uneven field counts confuse the sniffer; trust the header line
            dialect, delimiter = csv.excel, max(",;\t", key=sample.split("\n", 1)[0].count)
        reader = csv.DictReader(f, dialect=dialect, delimiter=delimiter)
        headers = reader.fieldnames or []
        data = [r for r in reader if any((r.get(h) or "").strip() for h in headers)]
        return headers, data


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------
def run_batch(args: argparse.Namespace, cfg: dict) -> int:
    headers, rows = read_rows(args.input)
    hmap = build_header_map(headers)
    if "receiver_name" not in hmap:
        sys.exit(f"Could not find a receiver-name column. Headers found: {headers}")
    unused = [h for h in headers if h and h not in hmap.values()]
    if unused:
        print(f"Note: ignoring unrecognised column(s): {', '.join(unused)}")

    ok = 0
    for i, row in enumerate(rows, start=1):
        values, warnings = row_to_fields(row, hmap, cfg, i)
        name = values.get("receiver_name", f"row{i}")
        out_path = args.output / pdf_filename(values, i)
        for w in warnings:
            print(f"  ! row {i} ({name}): {w}")
        if args.dry_run:
            print(f"  would write {out_path.name}")
            continue
        try:
            fill_pdf(args.template, values, out_path, args.lock)
            print(f"  ✓ {out_path.name}")
            ok += 1
        except Exception as e:  # keep going with the rest of the batch
            print(f"  ✗ row {i} ({name}): {e}")

    if not args.dry_run:
        print(f"\nDone — {ok} of {len(rows)} agreement(s) written to {args.output.resolve()}")
    return 0 if ok == len(rows) or args.dry_run else 1


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def load_settings(config: Path | None, start: int | None) -> dict:
    """The settings from `config`, else ./config.json if present, else the bundled defaults."""
    config = config or (Path("config.json") if Path("config.json").exists() else DEFAULT_CONFIG)
    if not config.exists():
        sys.exit(f"Config not found: {config}")
    cfg = json.loads(config.read_text(encoding="utf-8"))
    cfg["_seq_start"] = start if start is not None else cfg.get("agreement_no_start", 1)
    cfg["_now"] = datetime.now()
    return cfg


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate filled UFAZ Device Issuance Agreements from a CSV file, "
                                             "or fill them in one at a time on screen when no file is given.")
    ap.add_argument("input", type=Path, nargs="?", help="CSV file — one receiver per row (leave out to open the form)")
    ap.add_argument("-o", "--output", type=Path, default=Path("output"), help="output folder (default: ./output)")
    ap.add_argument("-t", "--template", type=Path, default=DEFAULT_TEMPLATE, help="fillable PDF template (default: the bundled one)")
    ap.add_argument("-c", "--config", type=Path, default=None,
                    help="JSON with issuer defaults (default: ./config.json if present, else the bundled one)")
    ap.add_argument("--lock", action="store_true", help="make the fields read-only in the generated PDFs")
    ap.add_argument("--start", type=int, default=None, help="first sequence number for auto-generated agreement numbers")
    ap.add_argument("--dry-run", action="store_true", help="show what would be generated without writing PDFs (CSV only)")
    ap.add_argument("--web", action="store_true", help="open the form in the browser; each PDF downloads there instead of going to -o")
    ap.add_argument("--host", default="127.0.0.1", help="with --web: address to listen on (default: 127.0.0.1, this computer only)")
    ap.add_argument("--port", type=int, default=5001, help="with --web: port to listen on (default: 5001)")
    args = ap.parse_args(argv)

    if args.web and args.input is not None:
        sys.exit("--web opens the form in the browser; leave out the CSV file")
    if args.input is None:
        if args.dry_run:
            sys.exit("--dry-run needs a CSV file; the form writes each agreement when you generate it")
        if not args.web and not (sys.stdin.isatty() and sys.stdout.isatty()):
            sys.exit("No CSV file given, and there is no terminal to open the form in. Usage: generate receivers.csv")
    elif not args.input.exists():
        sys.exit(f"Input file not found: {args.input}")
    if not args.template.exists():
        sys.exit(f"Template not found: {args.template}")

    cfg = load_settings(args.config, args.start)

    if args.web:
        serve(cfg, args.template, args.lock, args.host, args.port)
        return 0
    if args.input is None:
        from .form import AgreementForm
        AgreementForm(cfg, args.template, args.output, args.lock).run()
        return 0
    return run_batch(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
