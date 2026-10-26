#!/usr/bin/env python3
"""Validate upstream rules, then publish one output without touching other files."""

import argparse
import html
import ipaddress
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

SOURCES = {
    "merge": (
        "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/refs/heads/master/rule/Loon/ProxyLite/ProxyLite.list",
        "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/refs/heads/master/rule/Loon/Global/Global.list",
        "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/refs/heads/master/rule/Clash/Proxy/Proxy.list",
        "https://raw.githubusercontent.com/Loyalsoldier/surge-rules/release/ruleset/gfw.txt",
        "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/refs/heads/master/rule/Loon/GlobalMedia/GlobalMedia.list",
    ),
    "adlite": (
        "https://raw.githubusercontent.com/deezertidal/private/refs/heads/main/rule/ADLite.list",
    ),
}
OUTPUTS = {"merge": "lq/merged_rules.txt", "adlite": "lq/adlite.list"}
WORKFLOWS = {"merge": "Merge.yml", "adlite": "Sync and Process ADLite.yml"}
DOMAIN_TYPES = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD"}
TEXT_TYPES = DOMAIN_TYPES | {"USER-AGENT", "URL-REGEX"}


def parse_rules(text, source):
    """Return original lines plus validated rules; comments are not rules."""
    lines = text.lstrip("\ufeff").splitlines()
    rules = []
    for number, original in enumerate(lines, 1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        try:
            if any(ord(c) < 32 and c != "\t" for c in line):
                raise ValueError("control character in rule")
            kind, separator, value = line.partition(",")
            if not separator or not value.strip():
                raise ValueError("expected TYPE,value")
            if kind in ("IP-CIDR", "IP-CIDR6"):
                fields = [field.strip() for field in value.split(",")]
                network = ipaddress.ip_network(fields[0], strict=False)
                if network.version != (4 if kind == "IP-CIDR" else 6):
                    raise ValueError("IP version does not match rule type")
                if any(option != "no-resolve" for option in fields[1:]):
                    raise ValueError("unsupported IP option (only no-resolve is supported)")
                rules.append((number, line, kind, network))
            elif kind in TEXT_TYPES:
                if kind in DOMAIN_TYPES and re.search(r"[\s,/:<>#]", value):
                    raise ValueError("invalid domain value or unsupported extra option")
                # Preserve USER-AGENT and URL-REGEX expressions verbatim.
                rules.append((number, line, kind, None))
            else:
                raise ValueError(f"unsupported rule type: {kind}")
        except ValueError as error:
            raise ValueError(f"{source}:{number}: {error}") from error
    if not rules:
        raise ValueError(f"{source}: no valid rules (empty or comments-only response)")
    return lines, rules


def process(sources, mode, report):
    """Read each source independently, avoiding missing-newline concatenation."""
    parsed = []
    report["sources"] = []
    for source, text in sources:
        lines, rules = parse_rules(text, source)
        counts = {"source": source, "rules": len(rules), "ipv4": 0, "ipv6": 0}
        for _, _, _, network in rules:
            if network is not None:
                counts[f"ipv{network.version}"] += 1
        report["sources"].append(counts)
        parsed.append((lines, rules))
    if not parsed:
        raise ValueError("No source files supplied")
    if mode == "adlite":
        if len(parsed) != 1:
            raise ValueError("ADLite requires exactly one source")
        lines, rules = parsed[0]
        for number, line, kind, network in rules:
            if network is not None:
                # Validate the address, but preserve upstream spelling/host bits.
                address = line.split(",")[1].strip()
                lines[number - 1] = f"{kind},{address},no-resolve"
        report["output_rules"] = len(rules)
        return "\n".join(lines) + "\n"

    others, ipv4, ipv6 = set(), [], []
    non_ip_count = 0
    for _, rules in parsed:
        for _, line, _, network in rules:
            if network is None:
                others.add(line)
                non_ip_count += 1
            else:
                (ipv4 if network.version == 4 else ipv6).append(network)
    merged4 = list(ipaddress.collapse_addresses(ipv4))
    merged6 = list(ipaddress.collapse_addresses(ipv6))
    output = sorted(others)
    for kind, networks in (("IP-CIDR", merged4), ("IP-CIDR6", merged6)):
        for network in sorted(networks, key=lambda n: (n.network_address, n.prefixlen)):
            output.append(f"{kind},{network},no-resolve")
    report.update(output_rules=len(output), non_ip_before=non_ip_count,
                  non_ip_after=len(others), ipv4_before=len(ipv4),
                  ipv4_after=len(merged4), ipv6_before=len(ipv6), ipv6_after=len(merged6))
    return "\n".join(output) + "\n"


def download(url):
    with tempfile.TemporaryDirectory(prefix="mr-download-") as directory:
        target = Path(directory) / "source.txt"
        result = subprocess.run([
            "curl", "--fail", "--silent", "--show-error", "--location",
            "--connect-timeout", "10", "--max-time", "20",
            "--retry", "3", "--retry-connrefused", "--retry-max-time", "60",
            "--max-filesize", "20971520", "--output", str(target), url,
        ], capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError(f"{url}: download failed: {result.stderr.strip()}")
        try:
            return target.read_text(encoding="utf-8-sig")
        except UnicodeError as error:
            raise ValueError(f"{url}: response is not UTF-8 text") from error


def generate(mode, report):
    def inputs():
        for url in SOURCES[mode]:
            print(f"Downloading {url}", flush=True)
            try:
                yield url, download(url)
            except subprocess.TimeoutExpired as error:
                raise RuntimeError(f"{url}: download exceeded 90 seconds") from error
    return process(inputs(), mode, report)


def git(repo, *args, check=True, env=None, input=None):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                            text=True, input=input, env=env, timeout=120)
    if check and result.returncode:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result


def fetch_head(repo):
    git(repo, "fetch", "origin", "refs/heads/main")
    return git(repo, "rev-parse", "FETCH_HEAD").stdout.strip()


def publish(repo, mode, attempts, report):
    """Use a temporary index based on latest main; never reset the checkout."""
    for attempt in range(1, attempts + 1):
        report.clear()
        report["attempt"] = attempt
        base = fetch_head(repo)
        report["base"] = base
        # Do not publish with stale processing code after a concurrent code edit.
        guard = git(repo, "diff", "--quiet", "HEAD", base, "--",
                    "scripts/sync_rules.py", "tests/test_sync_rules.py",
                    f".github/workflows/{WORKFLOWS[mode]}", check=False)
        if guard.returncode:
            raise RuntimeError("Sync code changed on main; rerun the workflow using its latest version")
        content = generate(mode, report)
        if fetch_head(repo) != base:
            print("main changed; downloading and validating again", flush=True)
            continue
        with tempfile.TemporaryDirectory(prefix="mr-publish-") as directory:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
            git(repo, "read-tree", base, env=env)
            blob = git(repo, "hash-object", "-w", "--stdin", input=content).stdout.strip()
            git(repo, "update-index", "--add", "--cacheinfo",
                f"100644,{blob},{OUTPUTS[mode]}", env=env)
            tree = git(repo, "write-tree", env=env).stdout.strip()
            if tree == git(repo, "rev-parse", f"{base}^{{tree}}").stdout.strip():
                report["result"] = "No changes; no commit created"
                return
            commit = git(repo, "-c", "user.name=GitHub Action",
                         "-c", "user.email=action@github.com", "commit-tree", tree,
                         "-p", base, "-m", f"Update {mode} rules").stdout.strip()
            # Non-fast-forward rejection protects every concurrent commit.
            pushed = git(repo, "push", "origin", f"{commit}:refs/heads/main", check=False)
            if pushed.returncode == 0:
                report.update(result="Published", commit=commit)
                return
            print(f"Push rejected (attempt {attempt}/{attempts}): {pushed.stderr.strip()}", flush=True)
    raise RuntimeError(f"Could not publish after {attempts} attempts; no update published by this run")


def summary(mode, report):
    rows = [f"### {WORKFLOWS[mode][:-4]}", "", f"Result: {report.get('result', 'Failed')}"]
    for key in ("base", "commit", "attempt", "output_rules"):
        if key in report:
            rows += ["", f"{key}: {report[key]}"]
    if report.get("sources"):
        rows += ["", "| Source | Rules | IPv4 | IPv6 |", "| --- | ---: | ---: | ---: |"]
        for source in report["sources"]:
            rows.append(f"| {source['source']} | {source['rules']} | {source['ipv4']} | {source['ipv6']} |")
    for label in ("non_ip", "ipv4", "ipv6"):
        if f"{label}_before" in report:
            rows += ["", f"{label}: {report[label + '_before']} → {report[label + '_after']}"]
    if "error" in report:
        rows += ["", "Error: <pre>" + html.escape(report["error"]) + "</pre>"]
    result = "\n".join(rows) + "\n"
    print(result, flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=SOURCES)
    parser.add_argument("--attempts", type=int, default=3)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--publish", action="store_true")
    destination.add_argument("--output", type=Path, help="Validate and write locally without publishing")
    args = parser.parse_args(argv)
    if args.attempts < 1:
        parser.error("--attempts must be positive")
    report = {}
    try:
        if args.publish:
            repo = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").stdout.strip())
            publish(repo, args.mode, args.attempts, report)
        else:
            content = generate(args.mode, report)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            report["result"] = "Validated locally; not published"
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        report.update(result="Failed; no update published by this run", error=str(error))
        return 1
    finally:
        summary(args.mode, report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
