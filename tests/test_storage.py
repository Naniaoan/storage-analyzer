import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from deep_scan import inspect
from build_report import prepare_report

class StorageTests(unittest.TestCase):
    def test_site_origin_is_scoped_and_symlinks_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root/'CacheStorage'/'hash'
            cache.mkdir(parents=True)
            (cache/'index.txt').write_bytes(b'https://example.test/cache')
            (root/'index.txt').write_bytes(b'https://unrelated.test')
            (root/'link').symlink_to(cache, target_is_directory=True)
            result = inspect(root)
            self.assertEqual(result['site_origins'][0]['origins'], ['https://example.test'])
            self.assertEqual(len(result['site_origins']), 1)
            self.assertGreaterEqual(result['counts']['skipped_symlinks'], 1)

    def test_unverified_source_disables_cleanup(self):
        data = {'green':[{'path':'/example/cache','trash_paths':['/example/cache'], 'commands':[{'cmd':'untrusted'}]}]}
        result = prepare_report(data)
        self.assertEqual(result['report_validation']['status'], 'invalid')
        self.assertNotIn('trash_paths', result['green'][0])
        self.assertNotIn('commands', result['green'][0])

    def test_keep_blocks_overlapping_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan = {'scan_id':'fixture', 'system':{}, 'generated_at':'fixture', 'scan_seconds':1, 'finished_at_epoch':time.time()}
            raw = json.dumps(scan).encode()
            source = root/'scan.json'
            source.write_bytes(raw)
            data = {k:scan[k] for k in ('system','generated_at','scan_seconds')}
            data.update(source_scan={'path':str(source),'sha256':hashlib.sha256(raw).hexdigest(),'scan_id':'fixture'},
                green=[{'path':str(root/'cache'),'trash_paths':[str(root/'cache')]}],
                red=[{'path':str(root/'cache'/'keep'),'user_decision':'keep'}])
            result = prepare_report(data)
            self.assertEqual(result['report_validation']['status'], 'snapshot_verified')
            self.assertFalse(result['green'][0].get('trash_paths'))
            self.assertIn('cleanup_guard_note',result['green'][0])

if __name__ == '__main__':
    unittest.main()
