"""Portable archive checks use synthetic files and never touch source applications."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import archive_api
import archive_transfer


class ArchiveTransferTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name).resolve()
        self.archive = self.base / '旧电脑档案'
        self.output = self.base / '移动硬盘'
        self.output.mkdir()
        self.branch, self.sid = 'old-codex', 'conversation'
        self.markdown = 'old-codex/sessions/项目/conversation.md'
        self.record = 'records/old-codex/conversation/'
        self.put('old-codex/index.json', {'tool': 'codex', 'sessions': {'conversation': {
            'id': self.sid, 'tool': 'codex', 'file': 'sessions/项目/conversation.md',
            'local_record': self.record + 'manifest.json', 'title': '迁移测试', 'assets': []}}})
        self.put(self.markdown, '# 原始文字\n\n保存我的 AI 聊天记录。\n')
        self.put(self.record + 'manifest.json', {'branch': self.branch, 'session_id': self.sid,
                                                'metadata': {'text_only': True, 'source_retained': False}})
        self.put(self.record + 'dialogue.jsonl', '{"role":"user","text":"原始文字"}\n')
        self.image = 'images/' + hashlib.sha256(b'image').hexdigest() + '.png'
        self.put(self.image, b'image')
        self.put('.import-policy.json', {'tools': ['codex'], 'text_only': True, 'manual_only': True})
        self.put('.local/config.json', {'private': 'not portable'})
        self.put('config.json', {'private': 'not portable'})
        self.put('old-codex/.git/config', 'not portable')
        self.put('old-codex/.export-cache.json', {'paths': 'old machine'})
        self.put('attachments/unknown.txt', 'not an archive object')

    def put(self, name, content):
        path = self.archive / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, dict): content = json.dumps(content, ensure_ascii=False)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return path

    def hashes(self):
        return {p.relative_to(self.archive).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.archive.rglob('*') if p.is_file()}

    def test_plan_is_read_only_and_round_trip_preserves_text_relationships_and_resources(self):
        before = self.hashes()
        plan = archive_transfer.transfer(self.archive, plan=True)
        self.assertTrue(plan['plan'])
        self.assertEqual(plan['sessions'], 1)
        self.assertEqual(plan['resources'], 1)
        self.assertEqual(list(self.output.iterdir()), [])
        result = archive_transfer.transfer(self.archive, self.output)
        copied = Path(result['destination'])
        self.assertEqual(archive_api.search(copied)['total'], 1)
        for name in (self.markdown, self.record + 'manifest.json', self.record + 'dialogue.jsonl', self.image):
            self.assertEqual((copied / name).read_bytes(), (self.archive / name).read_bytes())
        for name in ('.local', 'config.json', 'old-codex/.git', 'old-codex/.export-cache.json', 'attachments/unknown.txt'):
            self.assertFalse((copied / name).exists(), name)
        policy = json.loads((copied / '.import-policy.json').read_bytes())
        self.assertTrue(policy['manual_only'])
        self.assertTrue(policy['text_only'])
        self.assertEqual(self.hashes(), before)
        again = archive_transfer.transfer(self.archive, self.output)
        self.assertNotEqual(again['destination'], result['destination'])

    def test_existing_skill_versions_and_source_snapshots_remain_usable(self):
        digest = 'a' * 64
        relative = f'skills/objects/{digest}.zip'
        self.put('skills/index.json', {'format_version': 1, 'items': [{
            'id': 'skill', 'name': 'example', 'version': digest, 'archive': relative,
            'versions': [{'version': digest, 'archive': relative}]}]})
        self.put(relative, b'already archived skill bytes')
        self.put(self.record + 'source.jsonl', '{"type":"session"}\n')
        self.put(self.record + 'project-state.jsonl', '{"cache_identity":[]}\n')
        result = archive_transfer.transfer(self.archive, self.output)
        copied = Path(result['destination'])
        self.assertEqual(result['skills'], 1)
        for name in (relative, self.record + 'source.jsonl', self.record + 'project-state.jsonl'):
            self.assertEqual((copied / name).read_bytes(), (self.archive / name).read_bytes())

    def test_changes_during_copy_do_not_publish_a_partial_folder(self):
        copy = archive_transfer.shutil.copyfileobj
        changed = False
        def change_source(source, target, length):
            nonlocal changed
            copy(source, target, length)
            if not changed:
                changed = True
                path = self.archive / self.markdown
                path.write_bytes(path.read_bytes() + b'changed')
        with patch('archive_transfer.shutil.copyfileobj', side_effect=change_source):
            with self.assertRaisesRegex(RuntimeError, '变化'):
                archive_transfer.transfer(self.archive, self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_missing_required_records_unsafe_paths_and_links_block_transfer(self):
        (self.archive / self.record / 'dialogue.jsonl').unlink()
        with self.assertRaises(FileNotFoundError): archive_transfer.transfer(self.archive, plan=True)
        self.put(self.record + 'dialogue.jsonl', '{}\n')
        image = self.archive / self.image
        image.unlink()
        image.symlink_to(self.archive / self.markdown)
        with self.assertRaisesRegex(ValueError, 'links'): archive_transfer.transfer(self.archive, self.output)
        image.unlink()
        self.put('old-codex/index.json', {'tool': 'codex', 'sessions': {'conversation': {'file': '../outside.md'}}})
        with self.assertRaisesRegex(ValueError, '索引'): archive_transfer.transfer(self.archive, plan=True)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_destination_cannot_be_inside_source_and_insufficient_space_keeps_archive(self):
        before = self.hashes()
        with self.assertRaisesRegex(ValueError, '之外'):
            archive_transfer.transfer(self.archive, self.archive)
        with patch('archive_transfer.shutil.disk_usage', return_value=type('Space', (), {'free': 0})()):
            with self.assertRaisesRegex(RuntimeError, '空间不足'):
                archive_transfer.transfer(self.archive, self.output)
        self.assertEqual(self.hashes(), before)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_invalid_skill_index_cannot_silently_omit_saved_versions(self):
        self.put('skills/index.json', {'format_version': 1, 'items': [{'archive': 'outside.zip'}]})
        with self.assertRaisesRegex(ValueError, 'Skill'):
            archive_transfer.transfer(self.archive, self.output)
        self.assertEqual(list(self.output.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
