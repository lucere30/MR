"""Bounded downloads, one immutable snapshot per URL per build."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import subprocess
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def download(url):
    with tempfile.TemporaryDirectory(prefix="rkit-fetch-") as directory:
        path = Path(directory) / "source"
        result = subprocess.run([
            "curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
            "--proto-redir", "=https", "--connect-timeout", "10", "--max-time", "30",
            "--retry", "2", "--retry-max-time", "70", "--max-filesize", "20971520",
            "--output", str(path), url,
        ], text=True, capture_output=True, timeout=100)
        if result.returncode:
            raise ValueError(f"{url}: download failed: {result.stderr.strip()}")
        data = path.read_bytes()
        if len(data) > 20971520:
            raise ValueError(f"{url}: source exceeds 20 MiB")
        data.decode("utf-8-sig")
        return data


def snapshots(urls, *, cache_dir=None, offline=False, fetcher=download):
    def fetch(url):
        path = Path(cache_dir) / (digest(url.encode()) + ".txt") if cache_dir else None
        try:
            if offline:
                if path is None:
                    raise ValueError("offline build requires --cache-dir")
                return path.read_bytes()
            data = fetcher(url)
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            return data
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            return error
    with ThreadPoolExecutor(max_workers=4) as pool:
        ordered = sorted(set(urls))
        return dict(zip(ordered, pool.map(fetch, ordered)))
