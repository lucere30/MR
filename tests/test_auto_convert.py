"""Exercise publishing against disposable local Git remotes; never contact GitHub."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("publisher", Path(__file__).resolve().parents[1] / "scripts/auto_convert.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        # Expected failure scenarios must not emit GitHub ::error:: annotations.
        output = patch("sys.stdout", new=io.StringIO())
        output.start()
        self.addCleanup(output.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.remote = self.root / "remote.git"
        self.seed = self.root / "seed"
        self.worker = self.root / "worker"
        self.command(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.command(self.root, "clone", str(self.remote), str(self.seed))
        for name in ("scripts", "tests", "lq", "cat", "singbox"):
            (self.seed / name).mkdir()
        (self.seed / "lq/rules.list").write_text("old-source")
        (self.seed / "cat/retained.yaml").write_text("keep-clash")
        (self.seed / "singbox/retained.json").write_text("keep-singbox")
        for _, test, script, directory in publisher.FORMATS:
            (self.seed / "tests" / test).write_text("import unittest\nclass Smoke(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n")
            suffix = "yaml" if directory == "cat" else "json"
            # Deterministic fixture converters let these tests target publication,
            # not duplicate each real converter's separate test suite.
            (self.seed / "scripts" / script).write_text(
                "import argparse\nfrom pathlib import Path\np=argparse.ArgumentParser()\np.add_argument('--output')\np.add_argument('--report')\na=p.parse_args()\nout=Path(a.output)\nout.mkdir(parents=True,exist_ok=True)\n"
                f"(out/'rules.{suffix}').write_text(Path('lq/rules.list').read_text())\n")
        self.commit_seed()
        self.command(self.root, "clone", str(self.remote), str(self.worker))
        self.env = patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(self.root / "summary.md")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def command(self, cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()

    def commit_seed(self):
        self.command(self.seed, "add", ".")
        self.command(self.seed, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "fixture update")
        self.command(self.seed, "push", "origin", "HEAD:main")

    def remote_file(self, path):
        return self.command(self.remote, "show", "main:" + path)

    def test_success_noop_and_no_deletions(self):
        self.assertEqual(publisher.publish(self.worker), 0)
        self.assertEqual(self.remote_file("cat/rules.yaml"), "old-source")
        self.assertEqual(self.remote_file("singbox/rules.json"), "old-source")
        self.assertEqual(self.remote_file("cat/retained.yaml"), "keep-clash")
        self.assertEqual(self.remote_file("singbox/retained.json"), "keep-singbox")
        head = self.command(self.remote, "rev-parse", "main")
        self.assertEqual(publisher.publish(self.worker), 0)
        self.assertEqual(self.command(self.remote, "rev-parse", "main"), head)

    def test_each_switch_skips_disabled_tests_and_preserves_published_files(self):
        # Disabled converters must not execute even if their tests are broken.
        for name, test, _, directory in publisher.FORMATS:
            (self.seed / "tests" / test).write_text("raise RuntimeError('disabled test must not execute')\n")
        self.commit_seed()
        head = self.command(self.remote, "rev-parse", "main")
        with patch.object(publisher, "fetch_head", side_effect=AssertionError("both disabled must not fetch")):
            self.assertEqual(publisher.publish(self.worker, enabled=[]), 0)
        self.assertEqual(self.command(self.remote, "rev-parse", "main"), head)
        for enabled, test, _, directory in publisher.FORMATS:
            self.command(self.seed, "pull", "--ff-only", "origin", "main")
            for name, filename, _, _ in publisher.FORMATS:
                content = "import unittest\nclass Smoke(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n" if name == enabled else "raise RuntimeError('disabled')\n"
                (self.seed / "tests" / filename).write_text(content)
            other = "singbox" if directory == "cat" else "cat"
            other_suffix = "json" if other == "singbox" else "yaml"
            (self.seed / other / f"rules.{other_suffix}").write_text("preserve-disabled")
            self.commit_seed()
            self.assertEqual(publisher.publish(self.worker, enabled=[enabled]), 0)
            self.assertEqual(self.remote_file(f"{other}/rules.{other_suffix}"), "preserve-disabled")

    def test_failed_singbox_does_not_publish_partial_output_or_block_clash(self):
        script = self.seed / "scripts/loon_to_singbox.py"
        script.write_text(script.read_text() + "raise SystemExit(1)\n")
        (self.seed / "singbox/rules.json").write_text("previous-valid")
        self.commit_seed()
        self.assertEqual(publisher.publish(self.worker), 1)
        self.assertEqual(self.remote_file("cat/rules.yaml"), "old-source")
        self.assertEqual(self.remote_file("singbox/rules.json"), "previous-valid")

    def test_failed_clash_tests_do_not_block_singbox(self):
        (self.seed / "tests/test_loon_to_clash.py").write_text("raise RuntimeError('broken Clash test')\n")
        (self.seed / "cat/rules.yaml").write_text("previous-clash")
        self.commit_seed()
        self.assertEqual(publisher.publish(self.worker), 1)
        self.assertEqual(self.remote_file("cat/rules.yaml"), "previous-clash")
        self.assertEqual(self.remote_file("singbox/rules.json"), "old-source")

    def test_remote_update_at_push_regenerates_both_outputs(self):
        original_git = publisher.git
        pushes = []

        def racing_git(repo, *args, **kwargs):
            if args and args[0] == "push":
                pushes.append(True)
                if len(pushes) == 1:
                    (self.seed / "lq/rules.list").write_text("new-source")
                    self.commit_seed()
            return original_git(repo, *args, **kwargs)

        with patch.object(publisher, "git", side_effect=racing_git):
            self.assertEqual(publisher.publish(self.worker), 0)
        self.assertEqual(len(pushes), 2)
        self.assertEqual(self.remote_file("lq/rules.list"), "new-source")
        self.assertEqual(self.remote_file("cat/rules.yaml"), "new-source")
        self.assertEqual(self.remote_file("singbox/rules.json"), "new-source")

    def test_independent_formats_retry_racing_publications_without_overwriting_each_other(self):
        other_worker = self.root / "other-worker"
        self.command(self.root, "clone", str(self.remote), str(other_worker))
        original_git = publisher.git
        for first, second, directory, suffix in (
            ("Clash", "sing-box", "cat", "yaml"),
            ("sing-box", "Clash", "singbox", "json"),
        ):
            with self.subTest(first=first):
                self.command(self.seed, "pull", "--ff-only", "origin", "main")
                source = f"source-for-{first}"
                (self.seed / "lq/rules.list").write_text(source)
                self.commit_seed()
                raced = False

                def racing_git(repo, *args, **kwargs):
                    nonlocal raced
                    if args and args[0] == "push" and not raced:
                        raced = True
                        # The other workflow wins immediately before this push.
                        self.assertEqual(publisher.publish(other_worker, enabled=[second]), 0)
                    return original_git(repo, *args, **kwargs)

                with patch.object(publisher, "git", side_effect=racing_git):
                    self.assertEqual(publisher.publish(self.worker, enabled=[first]), 0)
                self.assertTrue(raced)
                self.assertEqual(self.remote_file("cat/rules.yaml"), source)
                self.assertEqual(self.remote_file("singbox/rules.json"), source)
                self.assertEqual(self.remote_file("cat/retained.yaml"), "keep-clash")
                self.assertEqual(self.remote_file("singbox/retained.json"), "keep-singbox")
                self.assertEqual(
                    self.command(self.remote, "diff-tree", "--no-commit-id", "--name-only", "-r", "main"),
                    f"{directory}/rules.{suffix}",
                )

    def test_push_failure_stops_after_retry_limit(self):
        original_git = publisher.git
        pushes = []

        def failing_git(repo, *args, **kwargs):
            if args and args[0] == "push":
                pushes.append(True)
                return subprocess.CompletedProcess(args, 1, "", "simulated push failure")
            return original_git(repo, *args, **kwargs)

        head = self.command(self.remote, "rev-parse", "main")
        with patch.object(publisher, "git", side_effect=failing_git):
            self.assertEqual(publisher.publish(self.worker, attempts=3), 1)
        self.assertEqual(len(pushes), 3)
        self.assertEqual(self.command(self.remote, "rev-parse", "main"), head)
        self.assertEqual(self.command(self.worker, "worktree", "list", "--porcelain").count("worktree "), 1)

    def test_remote_change_during_conversion_restarts_before_committing(self):
        original_convert = publisher.convert_formats
        conversions = []

        def racing_conversion(worktree, staging, enabled=None):
            result = original_convert(worktree, staging, enabled)
            conversions.append(True)
            if len(conversions) == 1:
                (self.seed / "lq/rules.list").write_text("updated-during-conversion")
                self.commit_seed()
            return result

        with patch.object(publisher, "convert_formats", side_effect=racing_conversion):
            self.assertEqual(publisher.publish(self.worker), 0)
        self.assertEqual(len(conversions), 2)
        self.assertEqual(self.remote_file("cat/rules.yaml"), "updated-during-conversion")
        self.assertEqual(self.remote_file("singbox/rules.json"), "updated-during-conversion")


if __name__ == "__main__":
    unittest.main()
