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
    'bitget': 'https://raw.githubusercontent.com/uhovohu/clash/main/Rules/bitget.yaml',
}
CUSTOM = {'fakeip': 'custom/fakeip-filter.list', 'espn': 'custom/espn.list',
          'bitget': 'custom/bitget.list'}
BITGET_EXCLUDE = 'custom/bitget-exclude.list'
OUTPUTS = {'fakeip': 'cat/fakeip-filter.yaml', 'espn': 'lq/espn.list',
           'bitget': 'lq/bitget.list'}
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


def bitget_rule(rule, source):
    """Convert only exact and +. patterns; never broaden wildcard semantics."""
    if not isinstance(rule, str) or rule != rule.strip():
        raise ValueError(f'{source}: expected a domain string')
    kind, domain = ('DOMAIN-SUFFIX', rule[2:]) if rule.startswith('+.') else ('DOMAIN', rule)
    if (not domain or len(domain) > 253
            or not all(LABEL.fullmatch(label) for label in domain.split('.'))):
        raise ValueError(f'{source}: unsupported domain pattern: {rule!r}')
    return f'{kind},{domain.lower()}'


def bitget_custom_rules(text, source):
    result = []
    for rule in lines(text):
        fields = rule.split(',')
        if len(fields) != 2 or fields[0] not in {'DOMAIN', 'DOMAIN-SUFFIX'}:
            raise ValueError(f'{source}: expected DOMAIN or DOMAIN-SUFFIX without a policy')
        prefix = '+.' if fields[0] == 'DOMAIN-SUFFIX' else ''
        normalized = bitget_rule(prefix + fields[1], source)
        # DOMAIN,+.example.com is not an exact rule; reject ambiguous input.
        if normalized.split(',')[0] != fields[0]:
            raise ValueError(f'{source}: domain syntax does not match rule type')
        result.append(normalized)
    return result


def merge_bitget(upstream, custom, exclusions):
    data = yaml.safe_load(upstream)
    if (not isinstance(data, dict) or not isinstance(data.get('payload'), list)
            or not data['payload']):
        raise ValueError('Bitget upstream must contain a nonempty domain payload')
    # Validate every upstream entry before applying the exclusions.
    upstream_rules = [bitget_rule(rule, SOURCES['bitget']) for rule in data['payload']]
    excluded = bitget_custom_rules(exclusions, BITGET_EXCLUDE)
    excluded_exact = {r.split(',')[1] for r in excluded if r.startswith('DOMAIN,')}
    excluded_suffix = {r.split(',')[1] for r in excluded if r.startswith('DOMAIN-SUFFIX,')}
    retained = []
    for rule in upstream_rules:
        kind, domain = rule.split(',')
        labels = domain.split('.')
        covered = any('.'.join(labels[i:]) in excluded_suffix for i in range(len(labels)))
        if not covered and not (kind == 'DOMAIN' and domain in excluded_exact):
            retained.append(rule)
    # Exclusions apply to upstream only; explicit custom additions override them.
    additions = bitget_custom_rules(custom, CUSTOM['bitget'])
    rules = remove_covered_domains(list(dict.fromkeys(retained + additions)), {})
    content = (f'# Upstream: {SOURCES["bitget"]}\n'
               '# Edit custom/bitget.list for additions; custom/bitget-exclude.list for upstream exclusions.\n'
               '# Generated domain rules; assign the policy in your client subscription.\n'
               + '\n'.join(rules) + '\n')
    parse_rules(content, OUTPUTS['bitget'])
    return content


def generate(read_custom, downloader=download):
    # Fully validate all sources before exposing any outputs to publication.
    return {
        OUTPUTS['fakeip']: merge_fakeip(downloader(SOURCES['fakeip']), read_custom(CUSTOM['fakeip'])),
        OUTPUTS['espn']: merge_espn(downloader(SOURCES['espn']), read_custom(CUSTOM['espn'])),
        OUTPUTS['bitget']: merge_bitget(downloader(SOURCES['bitget']), read_custom(CUSTOM['bitget']),
                                        read_custom(BITGET_EXCLUDE)),
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
                return f'Published {len(outputs)} rulesets: {commit}'
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
            result = f'Validated {len(outputs)} rulesets locally'
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
