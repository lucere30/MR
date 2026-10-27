from pathlib import Path
import subprocess
from unittest.mock import patch

from test_pipeline import Project
from rkit.build import stage
from rkit.publish import git, publish
import rkit.publish as publisher


class PublishTests(Project):
    def setUp(self):
        super().setUp()
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "user.email", "test@example.test")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "source")
        self.remote = Path(self.temp.name) / "remote.git"
        subprocess.run(["git", "init", "--bare", str(self.remote)], check=True, capture_output=True)
        git(self.root, "remote", "add", "origin", str(self.remote))
        git(self.root, "push", "origin", "main")

    def prepare(self):
        self.counter += 1
        directory = Path(self.temp.name) / f"publish{self.counter}"
        stage(self.run_build(), directory)
        return directory

    def head(self):
        return git(self.remote, "rev-parse", "main").stdout.strip()

    def advance_remote(self):
        directory = Path(self.temp.name) / "other"
        subprocess.run(["git", "clone", "-b", "main", str(self.remote), str(directory)], check=True, capture_output=True)
        (directory / "note.txt").write_text("concurrent edit")
        git(directory, "add", "note.txt")
        git(directory, "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "concurrent edit")
        git(directory, "push", "origin", "main")

    def test_publish_one_commit_and_no_change_no_commit(self):
        before = self.head()
        self.write("unrelated.txt", "untracked private content")
        self.assertTrue(publish(self.root, self.prepare()))
        first = self.head()
        self.assertNotEqual(before, first)
        self.assertNotIn("unrelated.txt", git(self.remote, "ls-tree", "-r", "--name-only", "main").stdout)
        git(self.root, "fetch", "origin", "main")
        git(self.root, "merge", "--ff-only", "FETCH_HEAD")
        self.assertFalse(publish(self.root, self.prepare()))
        self.assertEqual(first, self.head())

    def test_remote_advance_before_publish_refuses_stale_snapshot(self):
        directory = self.prepare()
        self.advance_remote()
        head = self.head()
        with self.assertRaisesRegex(ValueError, "main advanced"):
            publish(self.root, directory)
        self.assertEqual(head, self.head())

    def test_remote_advance_at_push_does_not_overwrite(self):
        directory = self.prepare()
        real_git = publisher.git
        def racing_git(root, *args, **kwargs):
            if args[0] == "push":
                self.advance_remote()
            return real_git(root, *args, **kwargs)
        with patch.object(publisher, "git", side_effect=racing_git):
            # Avoid patch recursion when advancing the remote through the local helper.
            def advance():
                other = Path(self.temp.name) / "other-race"
                subprocess.run(["git", "clone", "-b", "main", str(self.remote), str(other)], check=True, capture_output=True)
                (other / "note.txt").write_text("race")
                real_git(other, "add", "note.txt")
                real_git(other, "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "race")
                real_git(other, "push", "origin", "main")
            self.advance_remote = advance
            with self.assertRaisesRegex(ValueError, "git push failed"):
                publish(self.root, directory)
        self.assertEqual(git(self.remote, "show", "main:note.txt").stdout, "race")
        self.assertNotIn("cat/x.yaml", git(self.remote, "ls-tree", "-r", "--name-only", "main").stdout)

    def test_uncommitted_inputs_cannot_be_published_as_committed_snapshot(self):
        self.write("custom/local.list", "DOMAIN,local.test")
        before = self.head()
        with self.assertRaisesRegex(ValueError, "inputs no longer match"):
            publish(self.root, self.prepare())
        self.assertEqual(self.head(), before)
