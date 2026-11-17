"""Native relationship identities and navigation metadata use disposable archives."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import archive_api
import archive_storage
import session_relations as relations
import vault


SID = '12345678-1234-1234-1234-123456789abc'
PARENT = '22345678-1234-1234-1234-123456789abc'


class SessionRelationsTest(unittest.TestCase):
    def test_codex_spawn_and_fork_keep_distinct_identities(self):
        payload = {'parent_thread_id': PARENT, 'agent_nickname': 'Explorer',
                   'source': {'subagent': {'thread_spawn': {
                       'parent_thread_id': PARENT, 'agent_role': 'researcher'}}},
                   'forked_from_id': 'another-session'}
        self.assertEqual(relations.codex(payload, SID), [
            {'kind': 'subagent', 'parent_id': PARENT, 'agent_name': 'Explorer', 'agent_type': 'researcher'},
            {'kind': 'fork', 'parent_id': 'another-session'}])
        for bad in (SID, '../other', '/private/other', 'C:\\other', {'id': PARENT}):
            self.assertEqual(relations.codex({'parent_thread_id': bad}, SID), [])
        payload['parent_thread_id'] = 'conflicting-parent'
        self.assertEqual(relations.codex(payload, SID), [{'kind': 'fork', 'parent_id': 'another-session'}])
        self.assertEqual(relations.codex({'source': {'subagent': 'review'}}, SID), [])

    def test_claude_subagents_and_nested_parent_sidecars(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'projects/project' / PARENT / 'subagents/agent-child.jsonl'
            path.parent.mkdir(parents=True)
            sid = PARENT + '--agent-child'
            self.assertEqual(relations.claude(path, sid)['session_relations'][0]['parent_id'], PARENT)
            sidecar = path.with_suffix('.meta.json')
            sidecar.write_text(json.dumps({'parentAgentId': 'research', 'agentType': 'Explore',
                                           'description': 'Read the parser\nPrivate long detail'}))
            relation = relations.claude(path, sid)['session_relations'][0]
            self.assertEqual(relation, {'kind': 'subagent', 'parent_id': PARENT + '--agent-research',
                                        'agent_type': 'Explore', 'agent_name': 'Read the parser'})
            sidecar.write_text('{bad optional metadata}')
            self.assertEqual(relations.claude(path, sid)['session_relations'][0]['parent_id'], PARENT)
            for parent in ('../outside', 'child', 'agent-child'):
                sidecar.write_text(json.dumps({'parentAgentId': parent}))
                self.assertEqual(relations.claude(path, sid)['session_relations'], [])
            self.assertEqual(relations.claude(path.with_name('ordinary.jsonl'), sid), {})

    def test_codex_export_keeps_links_in_index_manifest_and_queries(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            home, dest = root / 'codex', root / 'archive/device-codex'
            source = home / 'sessions' / ('rollout-' + SID + '.jsonl')
            source.parent.mkdir(parents=True)
            rows = [{'type': 'session_meta', 'payload': {
                'id': SID, 'cwd': '/fixture/project', 'source': {'subagent': {'thread_spawn': {
                    'parent_thread_id': PARENT, 'agent_nickname': 'Review', 'agent_role': 'reviewer'}}}}},
                {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                    'content': [{'type': 'input_text', 'text': 'Keep the original question'}]}}]
            source.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            original = source.read_bytes()
            dest.parent.mkdir()
            archive_storage.save_preferences(dest.parent, ['codex'])
            self.assertEqual(vault.export('codex', home, dest)['changed_sessions'], 1)
            row = vault.read_json(dest / 'index.json')['sessions'][SID]
            self.assertEqual(row['source'], 'subagent')
            self.assertEqual(row['session_relations'][0]['parent_id'], PARENT)
            manifest = vault.read_json(dest.parent / row['local_record'])
            self.assertEqual(manifest['metadata']['session_relations'], row['session_relations'])
            found = archive_api.search(dest.parent, '')['items'][0]
            self.assertEqual(found['session_relations'], row['session_relations'])
            self.assertEqual(vault.export('codex', home, dest)['changed_sessions'], 0)
            source.unlink()
            self.assertEqual(vault.export('codex', home, dest)['changed_sessions'], 0)
            self.assertEqual(vault.read_json(dest / 'index.json')['sessions'][SID], row)
            self.assertIn('Keep the original question', original.decode())

    def test_sidecar_only_change_updates_claude_relation_without_renaming_archive_ids(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            home, dest = root / 'claude', root / 'archive/device-claude'
            source = home / 'projects/project' / PARENT / 'subagents/agent-child.jsonl'
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps({'type': 'user', 'message': {'content': 'Research question'}}) + '\n')
            original = source.read_bytes()
            with patch('vault.metadata', return_value={}):
                self.assertEqual(vault.export('claude', home, dest)['changed_sessions'], 1)
                sid = PARENT + '--agent-child'
                initial = vault.read_json(dest / 'index.json')['sessions'][sid]
                source.with_suffix('.meta.json').write_text(json.dumps({'agentType': 'Explore', 'description': 'Parser review'}))
                self.assertEqual(vault.export('claude', home, dest)['changed_sessions'], 1)
                row = vault.read_json(dest / 'index.json')['sessions'][sid]
                self.assertEqual(row['file'], initial['file'])
                self.assertEqual(row['session_relations'][0]['agent_type'], 'Explore')
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(vault.export('claude', home, dest)['changed_sessions'], 0)


if __name__ == '__main__':
    unittest.main()
