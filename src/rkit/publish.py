"""One Git writer, explicit ownership, no force pushes or edits to sources."""
import json
from pathlib import Path
import subprocess
import tempfile

from .build import fingerprint
from .config import managed_path, safe_file
from .fetch import digest


def git(root, *args, check=True):
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, timeout=120)
    if check and result.returncode:
        raise ValueError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result


def apply(root, directory):
    """Validate ALL bytes and preconditions before touching a disposable checkout."""
    root, directory = Path(root), Path(directory)
    plan = json.loads((directory / "plan.json").read_text())
    if fingerprint(root) != plan["fingerprint"]:
        raise ValueError("build inputs no longer match; rebuild before publication")
    files = {}
    for path in set(plan["files"]) | set(plan["delete"]):
        if path != "manifest.json" and not managed_path(path):
            raise ValueError(f"refusing to modify non-generated path: {path}")
        file = safe_file(root, path)
        actual = digest(file.read_bytes()) if file.exists() else None
        if path not in plan["preconditions"] or actual != plan["preconditions"][path]:
            raise ValueError(f"output changed since build: {path}")
    if set(plan["files"]) & set(plan["delete"]):
        raise ValueError("path is both written and deleted")
    for path, sha in plan["files"].items():
        data = safe_file(directory / "files", path).read_bytes()
        if digest(data) != sha:
            raise ValueError(f"staged output changed: {path}")
        files[path] = data
    for path, data in files.items():
        file = safe_file(root, path)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
    for path in plan["delete"]:
        safe_file(root, path).unlink(missing_ok=True)
    return plan


def publish(root, directory):
    root, directory = Path(root).resolve(), Path(directory).resolve()
    base = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "fetch", "origin", "main")
    if git(root, "rev-parse", "FETCH_HEAD").stdout.strip() != base:
        raise ValueError("main advanced; discard stale build and run on latest main")
    with tempfile.TemporaryDirectory(prefix="rkit-publish-") as temp:
        checkout = Path(temp) / "checkout"
        git(root, "worktree", "add", "--detach", str(checkout), base)
        try:
            plan = apply(checkout, directory)
            paths = sorted(set(plan["files"]) | {p for p in plan["delete"] if plan["preconditions"][p] is not None})
            git(checkout, "add", "--", *paths)
            diff = git(checkout, "diff", "--cached", "--quiet", check=False)
            if diff.returncode == 0:
                return False
            if diff.returncode != 1:
                raise ValueError("cannot inspect generated changes")
            git(checkout, "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                "commit", "-m", "chore: build rkit subscriptions")
            # Normal fast-forward push is the final race guard. A rejected push changes nothing remotely.
            git(checkout, "push", "origin", "HEAD:refs/heads/main")
            return True
        finally:
            git(root, "worktree", "remove", "--force", str(checkout))
