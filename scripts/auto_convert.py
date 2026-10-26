#!/usr/bin/env python3
"""Publish independently validated formats from the latest main, without deletions."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

FORMATS = (
    ("Clash", "test_loon_to_clash.py", "loon_to_clash.py", "cat"),
    ("sing-box", "test_loon_to_singbox.py", "loon_to_singbox.py", "singbox"),
)


def git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result


def fetch_head(repo):
    git(repo, "fetch", "origin", "refs/heads/main")
    return git(repo, "rev-parse", "FETCH_HEAD").stdout.strip()


def convert_formats(worktree, staging, enabled=None):
    enabled = {item[0] for item in FORMATS} if enabled is None else set(enabled)
    successful = []
    failed = []
    for name, test, script, directory in FORMATS:
        if name not in enabled:
            print(f"{name}: disabled; skipping tests, conversion and publication", flush=True)
            continue
        print(f"::group::{name}: tests and conversion", flush=True)
        try:
            if not (worktree / "tests" / test).is_file():
                raise RuntimeError(f"Missing tests/{test}")
            subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", test, "-v"], cwd=worktree, check=True)
            output = staging / directory
            command = [sys.executable, f"scripts/{script}", "--output", str(output)]
            if directory == "singbox":
                command += ["--report", str(output / "reports/conversion-report.json")]
            subprocess.run(command, cwd=worktree, check=True)
            files = sorted(path for path in output.rglob("*") if path.is_file())
            if not files:
                raise RuntimeError("Converter produced no files")
            # Only this successful format's staged files are copied. No cleanup.
            for path in files:
                target = worktree / directory / path.relative_to(output)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            git(worktree, "add", "--", directory)
            successful.append(name)
        except (subprocess.CalledProcessError, RuntimeError, OSError) as error:
            failed.append(name)
            print(f"{name} failed; existing published files are retained: {error}", flush=True)
        finally:
            print("::endgroup::", flush=True)
    return successful, failed


def finish(base, successful, failed, changed, disabled=()):
    message = f"Source commit: {base}\nValidated formats: {', '.join(successful) or 'none'}\nFailed formats: {', '.join(failed) or 'none'}\nResult: {'published updates' if changed else 'no output changes'}\n"
    message += f"Disabled formats: {', '.join(disabled) or 'none'}\n"
    print(message, flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("### Auto Convert\n\n" + message.replace("\n", "\n\n"))
    if failed:
        print(f"::error::Failed formats: {', '.join(failed)}. Valid formats were processed independently.", flush=True)
    return int(bool(failed))


def publish(repo, attempts=3, enabled=None):
    enabled = {item[0] for item in FORMATS} if enabled is None else set(enabled)
    disabled = [item[0] for item in FORMATS if item[0] not in enabled]
    if not enabled:
        return finish("not fetched (both formats disabled)", [], [], False, disabled)
    for attempt in range(1, attempts + 1):
        print(f"Publication attempt {attempt}/{attempts}", flush=True)
        try:
            base = fetch_head(repo)
            with tempfile.TemporaryDirectory(prefix="mr-convert-") as temporary:
                worktree = Path(temporary) / "checkout"
                git(repo, "worktree", "add", "--detach", str(worktree), base)
                try:
                    successful, failed = convert_formats(worktree, Path(temporary) / "outputs", enabled)
                    # A remote change requires fresh inputs AND fresh converter code.
                    if fetch_head(repo) != base:
                        print("Remote main changed; regenerating from its latest commit.", flush=True)
                        continue
                    changed = git(worktree, "diff", "--cached", "--quiet", check=False).returncode
                    if changed not in (0, 1):
                        raise RuntimeError("Cannot inspect staged changes")
                    if not changed:
                        return finish(base, successful, failed, False, disabled)
                    # Never publish deletions or changes outside generated directories.
                    if git(worktree, "diff", "--cached", "--diff-filter=D", "--name-only").stdout.strip():
                        raise RuntimeError("Refusing to publish file deletions")
                    git(worktree, "-c", "user.name=GitHub Action", "-c", "user.email=action@github.com", "commit", "-m", "chore: Auto Convert")
                    result = git(worktree, "push", "origin", "HEAD:refs/heads/main", check=False)
                    if result.returncode == 0:
                        return finish(base, successful, failed, True, disabled)
                    print(f"Push failed; fetching and regenerating before retry: {result.stderr.strip()}", flush=True)
                finally:
                    # Remove only the disposable worktree, never repository outputs.
                    git(repo, "worktree", "remove", "--force", str(worktree))
        except (RuntimeError, OSError) as error:
            print(f"Attempt {attempt} failed: {error}", flush=True)
    print(f"::error::Could not publish a consistent snapshot after {attempts} attempts.", flush=True)
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--clash", choices=("true", "false"), default="true")
    parser.add_argument("--singbox", choices=("true", "false"), default="true")
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be positive")
    repo = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").stdout.strip())
    enabled = [name for name, flag in (("Clash", args.clash), ("sing-box", args.singbox)) if flag == "true"]
    return publish(repo, args.attempts, enabled)


if __name__ == "__main__":
    sys.exit(main())
