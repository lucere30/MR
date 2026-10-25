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


def load_process_map(path):
    """Load reviewed exact UA-pattern mappings, never infer executable names."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("mappings"), list):
        raise ValueError(f"{path}: invalid Windows process mapping format")
    mappings = {}
    for entry in data["mappings"]:
        names = entry.get("process_names")
        patterns = entry.get("user_agents")
        sources = entry.get("sources")
        if not entry.get("application") or not entry.get("verified_on") or not sources or not isinstance(sources, list) or not all(isinstance(url, str) and url.startswith("https://") for url in sources):
            raise ValueError(f"{path}: mapping must include application, verification date and evidence URLs")
        if not names or not isinstance(names, list) or not all(isinstance(name, str) and name.lower().endswith(".exe") and not any(char in name for char in '*?[]/\\:') and name == name.strip() for name in names):
            raise ValueError(f"{path}: process_names must contain literal Windows executable basenames")
        if not patterns or not isinstance(patterns, list) or not all(isinstance(pattern, str) and pattern.strip() and ',' not in pattern for pattern in patterns):
            raise ValueError(f"{path}: user_agents must contain exact source UA patterns without policies")
        for pattern in patterns:
            if pattern in mappings:
                raise ValueError(f"{path}: duplicate UA mapping: {pattern}")
            mappings[pattern] = entry
    return mappings


def convert(text, source, process_map=None):
    values = defaultdict(set)
    counts = Counter()
    skipped = []
    process_supplements = []
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
            # The literal UA pattern must be reviewed in the mapping table.
            # Do not fnmatch against arbitrary UA rules or invent .exe names.
            mapping = (process_map or {}).get(rest.strip()) if kind == "USER-AGENT" else None
            if mapping:
                process_supplements.append({
                    "line": number, "rule": line,
                    "application": mapping["application"],
                    "process_names": mapping["process_names"],
                    "sources": mapping["sources"],
                    "verified_on": mapping["verified_on"],
                    "equivalent": False,
                    "note": "Optional Windows desktop process match; covers the process connections, not HTTP User-Agent matching",
                })
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
        "windows_process_supplements": process_supplements,
    }


def generate(source_dir, output_dir, report_path, process_map=None):
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
        data, report = convert(path.read_text(encoding="utf-8-sig"), path.as_posix(), process_map)
        outputs[name] = data
        supplements = report["windows_process_supplements"]
        if supplements:
            process_name = path.stem + "_windows_process.json"
            if process_name in outputs:
                raise ValueError(f"Duplicate output filename: {process_name}")
            names = sorted({name for item in supplements for name in item["process_names"]})
            outputs[process_name] = {"version": 2, "rules": [{"process_name": names}]}
            report["windows_process_output"] = (output_dir / process_name).as_posix()
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
        if report["windows_process_supplements"]:
            print(f"{report['windows_process_output']}: {len(report['windows_process_supplements'])} UA rules have optional Windows process alternatives (not equivalent)")
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("lq"))
    parser.add_argument("--output", type=Path, default=Path("singbox"))
    parser.add_argument("--report", type=Path, default=Path("singbox/reports/conversion-report.json"))
    parser.add_argument("--process-map", type=Path, default=Path(__file__).with_name("windows_process_map.json"))
    args = parser.parse_args()
    try:
        generate(args.source, args.output, args.report, load_process_map(args.process_map))
    except (ValueError, OSError) as error:
        print(f"Conversion failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
