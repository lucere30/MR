import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sync_custom_rules as sync


class MergeTests(unittest.TestCase):
    def test_custom_survives_upstream_removal(self):
        custom = 'lancache.steamcontent.com\n+.wanmei.com\n'
        before = yaml.safe_load(sync.merge_fakeip('+.steamcontent.com\n', custom))['payload']
        after = yaml.safe_load(sync.merge_fakeip('other.example\n', custom))['payload']
        self.assertNotIn('lancache.steamcontent.com', before)
        self.assertIn('lancache.steamcontent.com', after)
        self.assertIn('+.wanmei.com', after)
        self.assertNotIn('+.steamcontent.com', after)

    def test_domain_boundaries_and_exact_rules(self):
        result = yaml.safe_load(sync.merge_fakeip(
            '+.example.com\na.example.com\nnotexample.com\nexact.test\nchild.exact.test\n',
            '*.wild.test\n*.wild.test\n'))['payload']
        self.assertEqual(result, ['+.example.com', 'notexample.com', 'exact.test',
                                  'child.exact.test', '*.wild.test'])

    def test_bad_fakeip_rejected(self):
        for text in ['', '# empty', '<html>error</html>', 'payload:\n - example.com', '+.bad..com']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                sync.merge_fakeip(text, '+.custom.test')

    def test_espn_safe_coverage_and_ip_options(self):
        source = 'payload: ["DOMAIN,a.bamgrid.com", "DOMAIN,notbamgrid.com", "IP-CIDR,192.0.2.0/24,no-resolve"]'
        result = sync.merge_espn(source, 'DOMAIN-SUFFIX,bamgrid.com\nDOMAIN-SUFFIX,bamgrid.com')
        self.assertNotIn('DOMAIN,a.bamgrid.com', result)
        self.assertIn('DOMAIN,notbamgrid.com', result)
        self.assertIn('IP-CIDR,192.0.2.0/24,no-resolve', result)
        self.assertEqual(result.count('DOMAIN-SUFFIX,bamgrid.com'), 1)

    def test_invalid_espn_and_policy_rejected(self):
        for source in ['payload: []', '<html>error</html>', 'payload: [42]', 'payload: ["UNKNOWN,foo"]']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                sync.merge_espn(source, '')
        with self.assertRaises(ValueError):
            sync.merge_espn('payload: ["DOMAIN,espn.com"]', 'DOMAIN-SUFFIX,bamgrid.com,ESPN')

    def test_empty_custom_is_allowed(self):
        self.assertIn('example.com', sync.merge_fakeip('example.com', '# nothing'))
        self.assertIn('DOMAIN,espn.com', sync.merge_espn('payload: ["DOMAIN,espn.com"]', ''))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / 'remote.git'
        self.repo = self.root / 'repo'
        subprocess.run(['git', 'init', '--bare', str(self.remote)], check=True, capture_output=True)
        subprocess.run(['git', 'clone', str(self.remote), str(self.repo)], check=True, capture_output=True)
        self.g('checkout', '-b', 'main')
        self.g('config', 'user.name', 'Test')
        self.g('config', 'user.email', 'test@example.invalid')
        for path, content in {sync.CUSTOM['fakeip']: 'lancache.steamcontent.com\n',
                              sync.CUSTOM['espn']: 'DOMAIN-SUFFIX,bamgrid.com\n',
                              'keep.txt': 'unrelated\n'}.items():
            p = self.repo / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        self.g('add', '.')
        self.g('commit', '-m', 'Initial')
        self.g('push', 'origin', 'main')

    def g(self, *args):
        return sync.git(self.repo, *args).stdout.strip()

    def head(self):
        return self.g('ls-remote', 'origin', 'refs/heads/main').split()[0]

    def download(self, url):
        return ('+.steamcontent.com\n' if url == sync.SOURCES['fakeip']
                else 'payload: ["DOMAIN,espn.com"]\n')

    def test_publish_idempotent_and_preserves_unrelated_files(self):
        self.assertIn('Published', sync.publish(self.repo, downloader=self.download))
        first = self.head()
        self.assertIn('No changes', sync.publish(self.repo, downloader=self.download))
        self.assertEqual(self.head(), first)
        self.g('fetch', 'origin', 'main')
        self.assertEqual(self.g('show', 'FETCH_HEAD:keep.txt'), 'unrelated')
        self.assertEqual(self.g('show', 'FETCH_HEAD:custom/fakeip-filter.list'), 'lancache.steamcontent.com')

    def test_bad_second_source_publishes_neither(self):
        before = self.head()
        with self.assertRaises(ValueError):
            sync.publish(self.repo, downloader=lambda url: self.download(url)
                         if url == sync.SOURCES['fakeip'] else 'payload: []')
        self.assertEqual(self.head(), before)

    def test_concurrent_custom_edit_is_reloaded(self):
        changed = False

        def downloader(url):
            nonlocal changed
            if not changed:
                changed = True
                p = self.repo / sync.CUSTOM['fakeip']
                p.write_text(p.read_text() + '+.new-custom.example\n')
                self.g('add', str(p))
                self.g('commit', '-m', 'Concurrent custom change')
                self.g('push', 'origin', 'main')
            return self.download(url)

        sync.publish(self.repo, downloader=downloader)
        self.g('fetch', 'origin', 'main')
        result = yaml.safe_load(self.g('show', 'FETCH_HEAD:cat/fakeip-filter.yaml'))['payload']
        self.assertIn('+.new-custom.example', result)


if __name__ == '__main__':
    unittest.main()
