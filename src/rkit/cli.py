"""Small local/CI interface: check, build, publish."""
import argparse
import os
from pathlib import Path
import sys

import yaml

from .build import build, stage, validate_local
from .config import load
from .publish import publish


def summary(report):
    lines = ["## rkit build", "", "| Ruleset | Result | Rules | Omitted by target |", "|---|---|---:|---|"]
    for name, data in report["successful"].items():
        omissions = ", ".join(f"{t}: {len(v['omitted'])}" for t, v in data["targets"].items())
        lines.append(f"| {name} | built | {data['output_rules']} | {omissions} |")
    for name, error in report["failed"].items():
        lines.append(f"| {name} | FAILED (previous output retained) | — | {error.replace('|', '/').replace(chr(10), ' ')} |")
    lines += ["", "Disabled targets: " + (", ".join(report["disabled"]) or "none")]
    text = "\n".join(lines) + "\n"
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    b = commands.add_parser("build")
    b.add_argument("--output", type=Path, required=True)
    b.add_argument("--cache-dir", type=Path)
    b.add_argument("--offline", action="store_true")
    p = commands.add_parser("publish")
    p.add_argument("--stage", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            validate_local(args.root.resolve(), load(args.root))
            print("Configuration and editable rules validated.")
        elif args.command == "build":
            result = build(args.root, cache_dir=args.cache_dir, offline=args.offline)
            stage(result, args.output)
            summary(result["report"])
            return int(bool(result["report"]["failed"]))
        else:
            changed = publish(args.root, args.stage)
            print("Published generated updates." if changed else "No generated changes.")
        return 0
    except (ValueError, OSError, yaml.YAMLError) as error:
        print(f"rkit: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
