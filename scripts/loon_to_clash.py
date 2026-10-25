#!/usr/bin/env python3
"""Preserve Loon rule order/content in Clash payload YAML, with safe validation."""

import argparse
import json
from pathlib import Path
import sys

import yaml

SAFE_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def convert(text, source):
    rules = []
    for raw in text.lstrip("\ufeff").split("\n"):
        # Same whitespace normalization as the original tr + awk pipeline.
        line = " ".join(raw.replace("\r", "").split())
        if not line or line.startswith("#"):
            continue
        rules.append(line)
    if not rules:
        raise ValueError(f"{source}: no rules; refusing to publish an empty payload")
    expected = {"payload": rules}
    # Keep the original bytes for ordinary rules; quote only when YAML needs it.
    output = "payload:\n" + "".join(f"  - {line}\n" for line in rules)
    try:
        parsed = yaml.load(output, Loader=SAFE_LOADER)
    except yaml.YAMLError:
        parsed = None
    if parsed != expected:
        output = "payload:\n" + "".join(f"  - {json.dumps(line, ensure_ascii=False)}\n" for line in rules)
    parsed = yaml.load(output, Loader=SAFE_LOADER)
    if parsed != expected or not all(isinstance(line, str) and line for line in parsed["payload"]):
        raise ValueError(f"{source}: YAML round-trip changed rule content")
    return output


def generate(source_dir, output_dir):
    files = sorted(path for path in source_dir.iterdir() if path.is_file() and path.suffix in {".list", ".txt"})
    if not files:
        raise ValueError(f"No .list or .txt files in {source_dir}")
    outputs = {}
    for path in files:
        name = path.stem + ".yaml"
        if name in outputs:
            raise ValueError(f"Duplicate output filename: {name}")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            outputs[name] = convert(stream.read(), path.as_posix())
    # Do not change any existing files until every input has passed validation.
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        (output_dir / name).write_text(content, encoding="utf-8")
        print(f"Created and validated {output_dir / name}")
    # Old files are deliberately retained, even when their source disappears.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("lq"))
    parser.add_argument("--output", type=Path, default=Path("cat"))
    args = parser.parse_args()
    try:
        generate(args.source, args.output)
    except (ValueError, OSError, yaml.YAMLError) as error:
        print(f"Clash conversion failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
