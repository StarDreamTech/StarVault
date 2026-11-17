"""Text-only imports and cleanup never mutate original application files."""
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import archive_storage as storage
import resources
import vault


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')


class StorageTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'archive'
        self.home = self.base / 'original-dsh'
        self.home.mkdir()
        self.source = self.home / 'sessions/project/session-fixture/session.jsonl'
        self.source.parent.mkdir(parents=True)
        self.rows = [
            {'type': 'session', 'id': 'fixture', 'cwd': str(self.base)},
            {'type': 'user/message', 'time': 1000000000000, 'data': {'content': [
                {'type': 'text', 'text': 'Keep this original question'},
                {'type': 'image', 'url': 'data:image/png;base64,' + base64.b64encode(PNG).decode()}], 'source': {'kind': 'user'}}},
            {'type': 'tool/call', 'data': {'command': 'NEVER_EXECUTE'}},
        ]
        self.source.write_text(''.join(json.dumps(r) + '\n' for r in self.rows))
        self.dest = self.root / 'device-dsh'
        self.silence = contextlib.redirect_stdout(io.StringIO())
        self.silence.__enter__()
        self.addCleanup(self.silence.__exit__, None, None, None)

    def export(self):
        with patch('vault.metadata', return_value={}):
            return vault.export('dsh', self.home, self.dest)

    def record(self):
        return next((self.root / 'records').glob('*/*/manifest.json')).parent

    def original(self):
        return self.source.read_bytes(), self.source.stat().st_mtime_ns

    def test_cleanup_preserves_text_and_originals_and_is_repeatable(self):
        self.export()
        record = self.record()
        extra = record / 'source.jsonl.zst'
        extra.write_bytes(b'old redundant format')
        attachment = self.root / 'attachments' / ('a' * 64 + '.blend')
        attachment.parent.mkdir(); attachment.write_bytes(b'COPIED MODEL')
        note = attachment.with_name('notes.txt'); note.write_text('not an object')
        original = self.original()
        texts = {p: p.read_bytes() for p in (record / 'dialogue.jsonl', next(self.dest.glob('sessions/**/*.md')))}
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        plan = storage.cleanup_text(self.root)
        self.assertGreater(plan['estimated_bytes'], 0)
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})
        result = storage.cleanup_text(self.root, plan=False)
        self.assertEqual(result['files'], 4)
        self.assertFalse((record / 'source.jsonl').exists())
        self.assertFalse(extra.exists()); self.assertFalse(attachment.exists())
        self.assertTrue(note.exists())
        self.assertEqual(texts, {p: p.read_bytes() for p in texts})
        self.assertEqual(original, self.original())
        self.assertEqual(storage.cleanup_text(self.root, plan=False)['removed_bytes'], 0)
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.assertFalse((record / 'source.jsonl').exists())

    def test_text_mode_skips_resources_on_first_and_changed_import(self):
        self.root.mkdir()
        storage.save_preferences(self.root, ['dsh'])
        self.export()
        record = self.record()
        self.assertFalse((record / 'source.jsonl').exists())
        self.assertFalse((self.root / 'images').exists())
        self.assertIn('Keep this original question', (record / 'dialogue.jsonl').read_text())
        self.assertEqual(self.export()['changed_sessions'], 0)
        with self.source.open('a') as stream:
            stream.write(json.dumps({'type': 'user/message', 'data': {'content': [{'type': 'text', 'text': 'new question'}], 'source': {'kind': 'user'}}}) + '\n')
        original = self.original()
        self.assertEqual(self.export()['changed_sessions'], 1)
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.assertFalse((record / 'source.jsonl').exists())
        self.assertFalse((self.root / 'images').exists())
        self.assertEqual(original, self.original())

    def test_selected_images_do_not_require_a_full_snapshot_and_policy_is_not_read_per_row(self):
        self.root.mkdir()
        storage.save_preferences(self.root, ['dsh'], only_text=False, snapshots=False)
        resources.save_policy(self.root, ['images'])
        original = self.original()
        with patch('vault.resources.policy', wraps=resources.policy) as policy:
            self.assertEqual(self.export()['changed_sessions'], 1)
        self.assertLess(policy.call_count, len(self.rows))
        self.assertTrue(any((self.root / 'images').iterdir()))
        self.assertFalse((self.record() / 'source.jsonl').exists())
        self.assertEqual(self.export()['changed_sessions'], 0)
        storage.save_preferences(self.root, ['dsh'], only_text=False, snapshots=True)
        self.assertEqual(self.export()['changed_sessions'], 1)
        self.assertTrue((self.record() / 'source.jsonl').is_file())
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.assertEqual(original, self.original())

    def test_switching_to_text_only_reuses_unchanged_text_without_deleting_existing_copies(self):
        self.export()
        record = self.record()
        original = self.original()
        retained = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in self.root.rglob('*') if p.is_file()}
        storage.save_preferences(self.root, ['dsh'])
        with patch('vault.export_session', side_effect=AssertionError('Unchanged conversations must be reused')):
            self.assertEqual(self.export()['changed_sessions'], 0)
        for path, (data, stamp) in retained.items():
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(path.stat().st_mtime_ns, stamp)
        self.assertTrue((record / 'source.jsonl').is_file())
        self.assertEqual(original, self.original())

    def test_image_replacement_preserves_boundaries_invalid_data_and_all_surrounding_text(self):
        self.dest.mkdir(parents=True)
        encoded = base64.b64encode(PNG)
        name = hashlib.sha256(PNG).hexdigest() + '.png'
        marker = ('vault-image:' + name).encode()
        raw = b'prefix data:image/png;base64,' + encoded + b' middle ' + encoded + b' suffix'
        found = set()
        self.assertEqual(vault.extract_images(raw, self.dest, found, copy=False),
                         b'prefix ' + marker + b' middle ' + marker + b' suffix')
        self.assertEqual(found, {name})
        for raw in (b'word' + encoded, b'data:image/png;base64,iVBORw0KGgo' + b'A' * 42,
                    b'unchanged text /tmp/image.png'):
            self.assertEqual(vault.extract_images(raw, self.dest, set(), copy=False), raw)
        self.assertFalse((self.root / 'images').exists())

    def test_bad_text_stops_cleanup_before_any_deletions(self):
        self.export(); record = self.record()
        (record / 'dialogue.jsonl').write_bytes(b'{damaged}\n')
        with self.assertRaises(ValueError): storage.cleanup_text(self.root, plan=False)
        self.assertTrue((record / 'source.jsonl').exists())
        self.assertTrue(any((self.root / 'images').iterdir()))

    def test_text_import_does_not_make_a_temporary_source_snapshot(self):
        self.root.mkdir()
        storage.save_preferences(self.root, ['dsh'])
        original = self.original()
        with patch('vault.prepare_jsonl', side_effect=AssertionError('No full temporary snapshot')):
            self.assertEqual(self.export()['changed_sessions'], 1)
        self.assertEqual(original, self.original())
        self.assertFalse(any(self.root.rglob('source.jsonl')))
        self.assertFalse(list(self.root.glob('.session-*')))

    def test_same_size_replacement_with_restored_mtime_is_detected(self):
        self.root.mkdir()
        storage.save_preferences(self.root, ['dsh'])
        self.export()
        before = self.source.stat()
        replacement = self.source.with_suffix('.replacement')
        replacement.write_bytes(self.source.read_bytes().replace(b'original question', b'replaced question'))
        os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
        replacement.replace(self.source)
        self.assertEqual(self.source.stat().st_size, before.st_size)
        self.assertEqual(self.source.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(self.export()['changed_sessions'], 1)
        self.assertIn('replaced question', (self.record() / 'dialogue.jsonl').read_text())
        self.assertEqual(self.export()['changed_sessions'], 0)

    def test_concurrent_text_source_change_keeps_the_previous_archive(self):
        self.root.mkdir()
        storage.save_preferences(self.root, ['dsh'])
        self.export()
        self.source.write_text(self.source.read_text().replace('original question', 'modified question'))
        previous = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        finish = resources.finish
        def change_after_parsing(*args, **kwargs):
            result = finish(*args, **kwargs)
            with self.source.open('a') as stream:
                stream.write('{}\n')
            return result
        with patch('resources.finish', side_effect=change_after_parsing):
            with self.assertRaisesRegex(RuntimeError, '正在变化'):
                self.export()
        self.assertEqual({p: p.read_bytes() for p in previous}, previous)
        self.assertEqual(self.export()['changed_sessions'], 1)

    def test_direct_text_export_matches_snapshot_export_and_rejects_broken_records(self):
        self.root.mkdir()
        storage.save_preferences(self.root, ['dsh'])
        self.export()
        record = self.record()
        markdown = next(self.dest.glob('sessions/**/*.md'))
        texts = {p: p.read_bytes() for p in (record / 'dialogue.jsonl', markdown)}
        items = vault.session_items
        def snapshots(*args, **kwargs):
            for item in items(*args, **kwargs):
                yield {**item, 'direct_text': False}
        with patch('vault.session_items', side_effect=snapshots), patch('vault.metadata', return_value={}):
            vault.export('dsh', self.home, self.dest, force=True)
        self.assertEqual({p: p.read_bytes() for p in texts}, texts)
        self.source.write_bytes(b'{broken completed record}\n')
        previous = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaises((ValueError, RuntimeError)):
            self.export()
        self.assertEqual({p: p.read_bytes() for p in previous}, previous)

    def test_snapshot_link_cannot_delete_original(self):
        self.export(); record = self.record()
        original = self.original()
        (record / 'source.jsonl').unlink()
        (record / 'source.jsonl').symlink_to(self.source)
        with self.assertRaises(ValueError): storage.cleanup_text(self.root, plan=False)
        self.assertEqual(original, self.original())
        self.assertTrue(any((self.root / 'images').iterdir()))

    def test_unindexed_snapshot_is_preserved_and_blocks_cleanup(self):
        self.export()
        orphan = self.root / 'records/device-dsh/unindexed/source.jsonl'
        orphan.parent.mkdir(); orphan.write_text('only remaining history')
        with self.assertRaisesRegex(ValueError, 'Unindexed'): storage.cleanup_text(self.root, plan=False)
        self.assertTrue((self.record() / 'source.jsonl').exists())
        self.assertEqual(orphan.read_text(), 'only remaining history')

    def test_interrupted_cleanup_can_resume_without_losing_text(self):
        self.export(); record = self.record()
        dialogue = (record / 'dialogue.jsonl').read_bytes()
        unlink = Path.unlink
        def interrupt(path, *args, **kwargs):
            if path.parent.name == 'images': raise OSError('simulated interruption')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', interrupt), self.assertRaisesRegex(OSError, 'interruption'):
            storage.cleanup_text(self.root, plan=False)
        storage.cleanup_text(self.root, plan=False)
        self.assertEqual((record / 'dialogue.jsonl').read_bytes(), dialogue)
        self.assertEqual(self.export()['changed_sessions'], 0)

    def test_selected_import_never_invokes_other_sources_or_git(self):
        cfg = self.base / 'config'; cfg.mkdir()
        (cfg / 'config.json').write_text(json.dumps({'device': 'device', 'dsh_home': str(self.home)}))
        with patch('vault.LOCAL', cfg), patch('vault.git', side_effect=AssertionError('No Git during local import')):
            vault.main(['import-local', '--archive', str(self.root), '--tools', 'dsh'])
        self.assertEqual([p.name for p in self.root.iterdir() if p.is_dir() and p.name != 'records'], ['device-dsh'])
        self.assertTrue(storage.text_only(self.root))
        self.assertEqual(storage.preferences(self.root)['tools'], ['dsh'])
        with self.assertRaises(ValueError): storage.save_preferences(self.root, ['unknown'])

    def test_sync_in_manual_mode_does_not_scan_or_copy(self):
        self.export(); storage.save_preferences(self.root, ['dsh'])
        cfg = {'archive': str(self.root), 'device': 'device', 'repo': 'unused'}
        with patch('vault.LOCAL', self.base / 'config'), patch('vault.private_repo'), \
                patch('vault.checkout', return_value=(self.dest, 'device-dsh')), \
                patch('vault.git', return_value=SimpleNamespace(stdout='', returncode=0)), \
                patch('vault.export') as export, patch('vault.collect_skills') as skills, patch('resources.migrate') as migrate:
            vault.sync(cfg, ['dsh'], True)
        export.assert_not_called(); skills.assert_not_called(); migrate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
