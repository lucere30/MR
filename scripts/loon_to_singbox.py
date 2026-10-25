#!/usr/bin/env python3
"""Convert lq/*.list and lq/*.txt to sing-box source rule sets (Python stdlib)."""

import argparse
from collections import Counter, defaultdict
import ipaddress
import json
from pathlib import Path
import sys


FIELDS = {
    "DOMAIN": "domain",
    "DOMAIN-SUFFIX": "domain_suffix",
    "DOMAIN-KEYWORD": "domain_keyword",
    "IP-CIDR": "ip_cidr",
    "IP-CIDR6": "ip_cidr",
}
UNSUPPORTED = {"USER-AGENT", "URL-REGEX"}


def convert(text, source):
    values = defaultdict(set)
    counts = Counter()
    skipped = []
    no_resolve = 0
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith(("#", ";", "//")):
            continue
        kind, separator, rest = line.partition(",")
        kind = kind.strip().upper()
        if not separator or not rest.strip():
            raise ValueError(f"{source}:{number}: malformed rule: {line}")
        if kind in UNSUPPORTED:
            skipped.append({"line": number, "rule": line, "reason": "No equivalent sing-box headless rule field"})
            continue
        if kind not in FIELDS:
            raise ValueError(f"{source}:{number}: unsupported rule type {kind}")
        parts = [part.strip() for part in rest.split(",")]
        value, options = parts[0], parts[1:]
        is_ip = kind in {"IP-CIDR", "IP-CIDR6"}
        if not value or (options and (not is_ip or any(option.lower() != "no-resolve" for option in options))):
            raise ValueError(f"{source}:{number}: empty value or unsupported policy/options: {line}")
        if is_ip:
            network = ipaddress.ip_network(value, strict=False)
            expected = 6 if kind == "IP-CIDR6" else 4
            if network.version != expected:
                raise ValueError(f"{source}:{number}: wrong IP version: {line}")
            value = str(network)
            no_resolve += bool(options)
        elif any(character.isspace() for character in value):
            raise ValueError(f"{source}:{number}: whitespace in domain value: {line}")
        values[FIELDS[kind]].add(value)
        counts[kind] += 1
    if not values:
        raise ValueError(f"{source}: no convertible rules; refusing to publish an empty rule set")
    # Separate rules retain OR semantics between all source rule types.
    rules = [{field: sorted(entries)} for field, entries in sorted(values.items())]
    return {"version": 2, "rules": rules}, {
        "source": source,
        "converted_lines": sum(counts.values()),
        "unique_entries": sum(len(entries) for entries in values.values()),
        "types": dict(sorted(counts.items())),
        "no_resolve_lines": no_resolve,
        "skipped": skipped,
    }


def generate(source_dir, output_dir, report_path):
    files = sorted(path for path in source_dir.iterdir() if path.is_file() and path.suffix in {".list", ".txt"})
    if not files:
        raise ValueError(f"No .list or .txt files in {source_dir}")
    outputs = {}
    reports = []
    # Validate the entire input before changing any generated output.
    for path in files:
        name = path.stem + ".json"
        if name in outputs:
            raise ValueError(f"Duplicate output filename: {name}")
        data, report = convert(path.read_text(encoding="utf-8-sig"), path.as_posix())
        outputs[name] = data
        reports.append(report)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in outputs.items():
        (output_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # This directory is reserved for generated rule-set JSON files.
    for path in output_dir.glob("*.json"):
        if path.name not in outputs:
            path.unlink()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"files": reports}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for report in reports:
        print(f"{report['source']}: {report['converted_lines']} converted, {len(report['skipped'])} skipped")
        if report["skipped"]:
            print(f"::warning::{report['source']}: skipped {len(report['skipped'])} USER-AGENT/URL-REGEX rules; see {report_path}")
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("lq"))
    parser.add_argument("--output", type=Path, default=Path("singbox"))
    parser.add_argument("--report", type=Path, default=Path("singbox/reports/conversion-report.json"))
    args = parser.parse_args()
    try:
        generate(args.source, args.output, args.report)
    except (ValueError, OSError) as error:
        print(f"Conversion failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
