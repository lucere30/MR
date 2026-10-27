#!/usr/bin/env python3
"""Refresh upstream snapshots while retaining separately maintained custom rules."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import yaml

from sync_rules import download, fetch_head, git, parse_rules, remove_covered_domains

SOURCES = {
    'fakeip': 'https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-ruleset/fakeip-filter.list',
    'espn': 'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/refs/heads/master/rule/Clash/Espn/Espn_No_Resolve.yaml',
}
CUSTOM = {'fakeip': 'custom/fakeip-filter.list', 'espn': 'custom/espn.list'}
OUTPUTS = {'fakeip': 'cat/fakeip-filter.yaml', 'espn': 'lq/espn.list'}
GUARDS = ('scripts/sync_custom_rules.py', 'scripts/sync_rules.py',
          'tests/test_sync_custom_rules.py', '.github/workflows/Sync Custom Rules.yml')
LABEL = re.compile(r'[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?\Z', re.I)


def lines(text):
    return [line.strip() for line in text.lstrip('\ufeff').splitlines()
            if line.strip() and not line.lstrip().startswith('#')]


def domains(text, source, allow_empty=False):
    rules = lines(text)
    if not rules and not allow_empty:
        raise ValueError(f'{source}: empty domain list')
    for rule in rules:
        body = rule[2:] if rule.startswith('+.') else rule.lstrip('.')
        if (len(body) > 253 or rule.startswith('..') or not body
                or any(label != '*' and not LABEL.fullmatch(label) for label in body.split('.'))):
            raise ValueError(f'{source}: invalid domain pattern: {rule!r}')
    return rules


def merge_fakeip(upstream, custom):
    rules = list(dict.fromkeys(domains(upstream, SOURCES['fakeip'])
                               + domains(custom, CUSTOM['fakeip'], allow_empty=True)))
    # Only plain domains and +. suffixes participate in coverage removal.
    # Wildcard patterns are preserved rather than interpreted as suffixes.
    suffixes = {r[2:] for r in rules if r.startswith('+.') and '*' not in r}
    result = []
    for rule in rules:
        body = rule[2:] if rule.startswith('+.') else rule
        labels = body.split('.')
        eligible = '*' not in body and not body.startswith('.')
        start = 1 if rule.startswith('+.') else 0
        covered = eligible and any('.'.join(labels[i:]) in suffixes
                                   for i in range(start, len(labels)))
        if not covered:
            result.append(rule)
    content = (f'# Generated from {SOURCES["fakeip"]}\n'
               '# Edit custom/fakeip-filter.list; this file is regenerated.\n'
               '# Mihomo: behavior: domain, format: yaml\npayload:\n'
               + ''.join(f'  - {json.dumps(rule)}\n' for rule in result))
    if yaml.safe_load(content) != {'payload': result}:
        raise ValueError('Fake-IP YAML round-trip failed')
    return content


def merge_espn(upstream, custom):
    data = yaml.safe_load(upstream)
    if (not isinstance(data, dict) or not isinstance(data.get('payload'), list)
            or not data['payload'] or not all(isinstance(r, str) for r in data['payload'])):
        raise ValueError('ESPN upstream must contain a nonempty string payload')
    upstream_rules = [r[1] for r in parse_rules('\n'.join(data['payload']), SOURCES['espn'])[1]]
    custom_rules = lines(custom)
    if custom_rules:
        custom_rules = [r[1] for r in parse_rules('\n'.join(custom_rules), CUSTOM['espn'])[1]]
    rules = remove_covered_domains(list(dict.fromkeys(upstream_rules + custom_rules)), {})
    content = (f'# Upstream: {SOURCES["espn"]}\n'
               '# Edit custom/espn.list; this file is regenerated.\n'
               '# Assign the ESPN policy in your client subscription.\n'
               + '\n'.join(rules) + '\n')
    parse_rules(content, OUTPUTS['espn'])
    return content


def generate(read_custom, downloader=download):
    # Fully validate both sources before exposing any outputs to publication.
    return {
        OUTPUTS['fakeip']: merge_fakeip(downloader(SOURCES['fakeip']), read_custom(CUSTOM['fakeip'])),
        OUTPUTS['espn']: merge_espn(downloader(SOURCES['espn']), read_custom(CUSTOM['espn'])),
    }


def publish(repo, attempts=3, downloader=download):
    for attempt in range(1, attempts + 1):
        base = fetch_head(repo)
        if git(repo, 'diff', '--quiet', 'HEAD', base, '--', *GUARDS, check=False).returncode:
            raise RuntimeError('Sync code changed on main; rerun using the latest version')
        # Read custom rules from the latest remote commit, never a stale checkout.
        outputs = generate(lambda path: git(repo, 'show', f'{base}:{path}').stdout, downloader)
        if fetch_head(repo) != base:
            continue
        with tempfile.TemporaryDirectory(prefix='mr-custom-') as directory:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / 'index'))
            git(repo, 'read-tree', base, env=env)
            for path, content in outputs.items():
                blob = git(repo, 'hash-object', '-w', '--stdin', input=content).stdout.strip()
                git(repo, 'update-index', '--add', '--cacheinfo', f'100644,{blob},{path}', env=env)
            tree = git(repo, 'write-tree', env=env).stdout.strip()
            if tree == git(repo, 'rev-parse', f'{base}^{{tree}}').stdout.strip():
                return 'No changes; no commit created'
            commit = git(repo, '-c', 'user.name=GitHub Action', '-c', 'user.email=action@github.com',
                         'commit-tree', tree, '-p', base, '-m', 'Update upstream and custom rules').stdout.strip()
            pushed = git(repo, 'push', 'origin', f'{commit}:refs/heads/main', check=False)
            if pushed.returncode == 0:
                return f'Published both rulesets: {commit}'
            print(f'Push rejected ({attempt}/{attempts}); reloading latest sources', flush=True)
    raise RuntimeError('Could not publish after retries; no forced push was attempted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempts', type=int, default=3)
    dest = parser.add_mutually_exclusive_group(required=True)
    dest.add_argument('--publish', action='store_true')
    dest.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error('--attempts must be positive')
    try:
        if args.publish:
            repo = Path(git(Path.cwd(), 'rev-parse', '--show-toplevel').stdout.strip())
            result = publish(repo, args.attempts)
        else:
            outputs = generate(lambda path: Path(path).read_text(encoding='utf-8'))
            for path, content in outputs.items():
                target = args.output_dir / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding='utf-8')
            result = 'Validated both rulesets locally'
    except (ValueError, RuntimeError, OSError, yaml.YAMLError, subprocess.TimeoutExpired) as error:
        result = f'Failed; publication skipped: {error}'
        code = 1
    else:
        code = 0
    print(result)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write('### Sync Custom Rules\n\n' + result + '\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
