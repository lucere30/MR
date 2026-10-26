import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sync_rules as sync


class DomainCoverageTests(unittest.TestCase):
    def test_suffix_covers_descendants_and_exact_apex_regardless_of_order(self):
        lines = ["DOMAIN-SUFFIX,a.b.example.com", "DOMAIN,www.example.com",
                 "DOMAIN-SUFFIX,b.example.com", "DOMAIN,example.com",
                 "DOMAIN-SUFFIX,example.com", "DOMAIN,notexample.com",
                 "DOMAIN-SUFFIX,otherexample.com", "DOMAIN,example.com.other"]
        report = {}
        result = sync.remove_covered_domains(lines, report)
        self.assertEqual(result, lines[4:])
        self.assertEqual(report["suffix_coverage_removed"], 2)
        self.assertEqual(report["domain_coverage_removed"], 2)
        self.assertEqual(report["coverage_removed_total"], 4)
        self.assertEqual(sync.remove_covered_domains(result, {}), result)

    def test_exact_domain_does_not_cover_any_other_rule(self):
        lines = ["DOMAIN,example.com", "DOMAIN,sub.example.com",
                 "DOMAIN-SUFFIX,sub.example.com", "DOMAIN-SUFFIX,example.net"]
        self.assertEqual(sync.remove_covered_domains(lines, {}), [lines[0], *lines[2:]])

    def test_preserves_non_candidates_and_duplicate_suffixes(self):
        lines = ["# DOMAIN,a.example.com", "", "DOMAIN-SUFFIX,example.com",
                 "DOMAIN-SUFFIX,example.com", "DOMAIN-KEYWORD,example.com",
                 "URL-REGEX,^https://a.example.com/", "USER-AGENT,*example.com*",
                 "IP-CIDR,192.0.2.0/24,no-resolve", "DOMAIN,Example.com",
                 "DOMAIN,a.example.com.", "DOMAIN-SUFFIX,.example.com",
                 "DOMAIN,*.example.com", "DOMAIN,_srv.example.com",
                 "DOMAIN,中文.example.com", "DOMAIN,a.example.com,Proxy",
                 "DOMAIN-SUFFIX,com", "DOMAIN,192.0.2.1"]
        self.assertEqual(sync.remove_covered_domains(lines, {}), lines)

    def test_policy_or_unusual_suffix_is_never_used_for_coverage(self):
        for suffix in ["example.com,Proxy", ".example.com", "Example.com", "*.example.com"]:
            lines = [f"DOMAIN-SUFFIX,{suffix}", "DOMAIN,a.example.com"]
            self.assertEqual(sync.remove_covered_domains(lines, {}), lines)

    def test_each_rule_set_is_independent(self):
        sync.remove_covered_domains(["DOMAIN-SUFFIX,example.com"], {})
        other = ["DOMAIN,a.example.com"]
        self.assertEqual(sync.remove_covered_domains(other, {}), other)

    def test_both_sync_modes_apply_coverage_and_report_it(self):
        text = ("# keep\nDOMAIN,a.example.com\nDOMAIN-SUFFIX,example.com\n"
                "DOMAIN-SUFFIX,b.example.com\nIP-CIDR,192.0.2.0/24\n")
        for mode in ("merge", "adlite"):
            report = {}
            result = sync.process([("input", text)], mode, report)
            self.assertNotIn("DOMAIN,a.example.com", result)
            self.assertNotIn("DOMAIN-SUFFIX,b.example.com", result)
            self.assertIn("IP-CIDR,192.0.2.0/24,no-resolve", result)
            self.assertEqual(report["coverage_removed_total"], 2)
            self.assertEqual(report["output_rules"], 2)
            if mode == "adlite":
                self.assertTrue(result.startswith("# keep\nDOMAIN-SUFFIX,example.com\n"))

    def test_randomized_against_pairwise_oracle_and_matching_behavior(self):
        rng = random.Random(20261026)

        def matches(lines, host):
            for line in lines:
                kind, domain = line.split(",")
                if host == domain or (kind == "DOMAIN-SUFFIX" and host.endswith("." + domain)):
                    return True
            return False

        for _ in range(60):
            names = [".".join([rng.choice(["a", "b", "c"])
                               for _ in range(rng.randrange(4))] + ["example", "com"])
                     for _ in range(30)]
            lines = [rng.choice(["DOMAIN,", "DOMAIN-SUFFIX,"]) + name for name in names]
            suffixes = [line.split(",")[1] for line in lines if line.startswith("DOMAIN-SUFFIX,")]
            expected = []
            for line in lines:
                kind, name = line.split(",")
                if not any(name.endswith("." + suffix) or
                           (kind == "DOMAIN" and name == suffix) for suffix in suffixes):
                    expected.append(line)
            result = sync.remove_covered_domains(lines, {})
            self.assertEqual(result, expected)
            for host in names + ["x." + name for name in names] + ["notexample.com"]:
                self.assertEqual(matches(lines, host), matches(result, host), host)


class ProcessingTests(unittest.TestCase):
    def test_merge_preserves_sorting_and_collapses_each_ip_family(self):
        report = {}
        result = sync.process([
            ("one", "DOMAIN,z.example\nIP-CIDR,10.0.0.1/25\nDOMAIN,a.example"),
            ("two", "DOMAIN,a.example\nIP-CIDR,10.0.0.128/25,no-resolve\n"
             "IP-CIDR6,2001:db8::/33\nIP-CIDR6,2001:db8:8000::/33\n"
             "USER-AGENT,*Spotify*\nURL-REGEX,^https?://example\\.com/a{1,3}"),
        ], "merge", report)
        self.assertEqual(result, "DOMAIN,a.example\nDOMAIN,z.example\n"
                         "URL-REGEX,^https?://example\\.com/a{1,3}\nUSER-AGENT,*Spotify*\n"
                         "IP-CIDR,10.0.0.0/24,no-resolve\nIP-CIDR6,2001:db8::/32,no-resolve\n")
        self.assertEqual((report["non_ip_before"], report["non_ip_after"]), (5, 4))
        self.assertEqual((report["ipv4_before"], report["ipv4_after"]), (2, 1))
        self.assertEqual([s["rules"] for s in report["sources"]], [3, 6])

    def test_adlite_is_idempotent_and_preserves_comments_order_and_duplicates(self):
        original = ("\ufeff  # example 1.2.3.0/24\r\n\r\nDOMAIN-SUFFIX,a.example\r\n"
                    "IP-CIDR,10.0.0.1/24,no-resolve,no-resolve\r\n"
                    "IP-CIDR6,2001:db8::/32\r\nDOMAIN-SUFFIX,a.example\r\n")
        result = sync.process([("adlite", original)], "adlite", {})
        self.assertEqual(result, "  # example 1.2.3.0/24\n\nDOMAIN-SUFFIX,a.example\n"
                         "IP-CIDR,10.0.0.1/24,no-resolve\nIP-CIDR6,2001:db8::/32,no-resolve\n"
                         "DOMAIN-SUFFIX,a.example\n")
        self.assertEqual(sync.process([("adlite", result)], "adlite", {}), result)

    def test_merge_ignores_bom_and_indented_comments(self):
        self.assertEqual(sync.process([("a", "\ufeff  # comment\r\n\tDOMAIN,a.example\r\n")],
                                      "merge", {}), "DOMAIN,a.example\n")

    def test_invalid_sources_fail_with_source_and_line(self):
        for rule in ["404: Not Found", "<html>Bad Gateway</html>", "IP-CIDR,999.0.0.0/24",
                     "IP-CIDR,2001:db8::/32", "IP-CIDR6,1.2.3.0/24",
                     "IP-CIDR,1.2.3.0/24,DIRECT", "IP-CIDR,1.2.3.0/24,",
                     "DOMAIN,", "DOMAIN,a.example,Proxy", "DOMAIN,a example",
                     "UNKNOWN,a.example", "DOMAIN,a\x00.example"]:
            with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "bad-source:2:"):
                sync.process([("bad-source", "# header\n" + rule)], "merge", {})

    def test_empty_source_is_not_silently_omitted(self):
        for bad in ["", " \n# only comments\n"]:
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "empty-source"):
                sync.process([("good", "DOMAIN,a.example"), ("empty-source", bad)], "merge", {})

    def test_empty_input_list_fails(self):
        with self.assertRaises(ValueError):
            sync.process([], "merge", {})

    def test_failure_preserves_output_and_writes_action_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            target, summary = Path(directory) / "rules", Path(directory) / "summary"
            target.write_text("previous valid content")
            with patch.object(sync, "download", return_value="<html>error</html>"), \
                    patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}), \
                    contextlib.redirect_stdout(io.StringIO()):
                status = sync.main(["adlite", "--output", str(target)])
            self.assertEqual(status, 1)
            self.assertEqual(target.read_text(), "previous valid content")
            self.assertIn("Failed", summary.read_text())
            self.assertIn(sync.SOURCES["adlite"][0], summary.read_text())
            self.assertIn("expected TYPE,value", summary.read_text())

    def test_summary_escapes_remote_error_text(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "summary"
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(target)}), \
                    contextlib.redirect_stdout(io.StringIO()):
                sync.summary("merge", {"error": "<html>bad & response</html>"})
            self.assertIn("&lt;html&gt;bad &amp; response&lt;/html&gt;", target.read_text())


class DownloadTests(unittest.TestCase):
    @contextlib.contextmanager
    def server(self, statuses, body=b"DOMAIN,a.example\n"):
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(self.path)
                status = statuses[min(len(calls) - 1, len(statuses) - 1)]
                self.send_response(status)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/rules", calls
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_404_fails_even_with_rule_shaped_body(self):
        with self.server([404]) as (url, calls):
            with self.assertRaisesRegex(RuntimeError, "download failed"):
                sync.download(url)
            self.assertEqual(len(calls), 1)

    def test_transient_server_error_retries(self):
        with self.server([503, 200]) as (url, calls):
            self.assertEqual(sync.download(url), "DOMAIN,a.example\n")
            self.assertEqual(len(calls), 2)

    def test_non_utf8_fails(self):
        with self.server([200], b"\xff\xfe") as (url, _):
            with self.assertRaisesRegex(ValueError, "not UTF-8"):
                sync.download(url)

    def test_empty_success_response_fails_validation(self):
        with self.server([200], b"") as (url, _):
            with self.assertRaisesRegex(ValueError, "no valid rules"):
                sync.process([(url, sync.download(url))], "merge", {})

    def test_timeout_identifies_source(self):
        with patch.object(sync, "download", side_effect=subprocess.TimeoutExpired("curl", 90)), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "https://.*90 seconds"):
            sync.generate("merge", {})


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.remote, self.writer, self.repo = root / "remote.git", root / "writer", root / "runner"
        self.command(root, "init", "--bare", str(self.remote))
        self.command(root, "init", "-b", "main", str(self.writer))
        self.command(self.writer, "config", "user.name", "Test")
        self.command(self.writer, "config", "user.email", "test@example.com")
        for name, value in {"lq/merged_rules.txt": "DOMAIN,old.example\n",
                            "lq/adlite.list": "DOMAIN,ad.example\n",
                            "unrelated.txt": "keep", "scripts/sync_rules.py": "original code"}.items():
            path = self.writer / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        self.command(self.writer, "add", ".")
        self.command(self.writer, "commit", "-m", "initial")
        self.command(self.writer, "remote", "add", "origin", str(self.remote))
        self.command(self.writer, "push", "origin", "main")
        self.command(root, "clone", "--branch", "main", str(self.remote), str(self.repo))
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)
        self.initial = self.head()

    def command(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def head(self):
        return self.command(self.remote, "rev-parse", "main")

    def output(self, path):
        return self.command(self.remote, "show", f"main:{path}")

    def advance(self, path="unrelated.txt", content="concurrent edit"):
        self.command(self.writer, "pull", "--ff-only", "origin", "main")
        (self.writer / path).write_text(content)
        self.command(self.writer, "add", path)
        self.command(self.writer, "commit", "-m", "concurrent update")
        self.command(self.writer, "push", "origin", "main")

    def test_only_target_file_changes_and_local_edits_are_preserved(self):
        (self.repo / "unrelated.txt").write_text("local staged edit")
        self.command(self.repo, "add", "unrelated.txt")
        (self.repo / "lq/adlite.list").write_text("local unstaged edit")
        before = self.command(self.repo, "status", "--porcelain")
        report = {}
        with patch.object(sync, "download", return_value="DOMAIN,new.example\n"):
            sync.publish(self.repo, "merge", 3, report)
        changed = self.command(self.remote, "diff", "--name-only", self.initial, "main")
        self.assertEqual(changed, "lq/merged_rules.txt")
        self.assertEqual(self.output("unrelated.txt"), "keep")
        self.assertEqual(self.command(self.repo, "status", "--porcelain"), before)
        self.assertEqual(report["result"], "Published")

    def test_unchanged_output_does_not_commit(self):
        report = {}
        with patch.object(sync, "download", return_value="DOMAIN,old.example\n"):
            sync.publish(self.repo, "merge", 3, report)
        self.assertEqual(self.head(), self.initial)
        self.assertIn("No changes", report["result"])

    def test_one_bad_source_prevents_all_publication(self):
        with patch.object(sync, "download", side_effect=["DOMAIN,good.example", "404: Not Found"]), \
                self.assertRaises(ValueError):
            sync.publish(self.repo, "merge", 3, {})
        self.assertEqual(self.head(), self.initial)

    def test_remote_change_before_commit_redownloads(self):
        real_generate = sync.generate
        calls = []

        def generate(mode, report):
            calls.append(mode)
            if len(calls) == 1:
                self.advance()
            return real_generate(mode, report)

        with patch.object(sync, "generate", side_effect=generate), \
                patch.object(sync, "download", return_value="DOMAIN,new.example\n") as downloaded:
            sync.publish(self.repo, "merge", 3, {})
        self.assertEqual(len(calls), 2)
        self.assertEqual(downloaded.call_count, 10)
        self.assertEqual(self.output("unrelated.txt"), "concurrent edit")

    def test_actual_push_race_retries_with_fresh_sources(self):
        real_git = sync.git
        push_calls = []

        def git(repo, *args, **kwargs):
            if args[0] == "push":
                push_calls.append(args)
                if len(push_calls) == 1:
                    self.advance()
            return real_git(repo, *args, **kwargs)

        with patch.object(sync, "git", side_effect=git), \
                patch.object(sync, "download", side_effect=["DOMAIN,first.example", "DOMAIN,latest.example"]) as downloaded:
            sync.publish(self.repo, "adlite", 3, {})
        self.assertEqual(len(push_calls), 2)
        self.assertEqual(downloaded.call_count, 2)
        self.assertEqual(self.output("lq/adlite.list"), "DOMAIN,latest.example")
        self.assertEqual(self.output("unrelated.txt"), "concurrent edit")

    def test_push_failures_stop_at_limit(self):
        real_git = sync.git

        def git(repo, *args, **kwargs):
            if args[0] == "push":
                return subprocess.CompletedProcess(args, 1, "", "permission denied")
            return real_git(repo, *args, **kwargs)

        with patch.object(sync, "git", side_effect=git), \
                patch.object(sync, "download", return_value="DOMAIN,new.example") as downloaded, \
                self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
            sync.publish(self.repo, "adlite", 3, {})
        self.assertEqual(downloaded.call_count, 3)
        self.assertEqual(self.head(), self.initial)

    def test_concurrent_code_change_aborts_stale_run(self):
        self.advance("scripts/sync_rules.py", "new processing code")
        updated = self.head()
        with patch.object(sync, "download") as downloaded, self.assertRaisesRegex(RuntimeError, "code changed"):
            sync.publish(self.repo, "merge", 3, {})
        downloaded.assert_not_called()
        self.assertEqual(self.head(), updated)


if __name__ == "__main__":
    unittest.main()
