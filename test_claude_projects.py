"""Projects cache integration: synthetic SSE only, never a real app export."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import vault


CHANNEL = '11111111-1111-4111-8111-111111111111'
OTHER_CHANNEL = '22222222-2222-4222-8222-222222222222'
ROOT = 'cmsg_' + '1' * 46
ANSWER = 'cmsg_' + '2' * 46


def message(mid=ROOT, body='Fixture question', role='user', seq='1', **fields):
    row = {'id': mid, 'channel_id': CHANNEL, 'thread_root_id': ROOT,
           'seq': seq, 'created_at': '2026-11-01T12:00:00Z', 'body': body}
    if role == 'user':
        row['author_account_id'] = 'fixture-account'
    elif role == 'assistant':
        row['author_agent_id'] = 'fixture-agent'
        row['author_session_id'] = 'fixture-session'
    row.update(fields)
    return row


def event(row, kind='channel_message'):
    return ('event: ' + kind + '\ndata: ' + json.dumps(row) + '\n\n').encode('utf-8')


def response(home, data, name='fixture_0', mtime=100, channel=CHANNEL, response_time=None):
    value = {'path': home / 'Cache/Cache_Data' / name,
             'url': 'https://claude.ai/v1/code/channels/' + channel + '/messages/stream',
             'body': data, 'signature': [name, mtime], 'mtime_ns': mtime}
    if response_time is not None:
        value['response_time'] = response_time
    return value


class ClaudeProjectsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / 'Claude'
        self.home.mkdir()
        self.dest = self.root / 'backup/device-claude-desktop'
        self.responses = {self.home: []}
        self.reader = patch('claude_cache.iter_responses', side_effect=self.read_responses)
        self.reader.start()
        self.addCleanup(self.reader.stop)

    def read_responses(self, home, warnings=None):
        return iter(self.responses.get(Path(home), []))

    def export(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return vault.export('claude-desktop', self.home, self.dest)

    def sessions(self):
        return json.loads((self.dest / 'index.json').read_text(encoding='utf-8'))['sessions']

    def snapshot(self, row):
        return self.dest.parent / 'records' / self.dest.name / row['id'] / 'source.jsonl'

    def markdown(self, row):
        return (self.dest / row['file']).read_text(encoding='utf-8')

    def files(self):
        return {path.relative_to(self.dest.parent).as_posix():
                (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.dest.parent.rglob('*') if path.is_file()}

    def test_saved_project_and_thread_names_upgrade_without_changing_identity(self):
        self.responses[self.home] = [response(self.home, event(message(in_timeline=True, has_thread=True)))]
        self.export()
        original_ids = set(self.sessions())
        labels = {(CHANNEL, ''): {'title': '项目昵称', 'sequence': 100, 'source': 'session-navigation'},
                  (CHANNEL, ROOT): {'title': '讨论串正式标题', 'sequence': 100, 'source': 'session-navigation'}}
        with patch('claude_project_names.labels', return_value=labels):
            self.export()
        self.assertEqual(set(self.sessions()), original_ids)
        for row in self.sessions().values():
            self.assertEqual(row['project'], '项目昵称')
            self.assertEqual(row['title'], '主对话' if row['claude_project']['view'] == 'main' else '讨论串正式标题')
        original = self.files()
        self.responses[self.home] = []
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.assertEqual(self.files(), original)
        stale = {(CHANNEL, ''): dict(labels[(CHANNEL, '')], title='过期昵称', sequence=10)}
        with patch('claude_project_names.labels', return_value=stale):
            self.assertEqual(self.export()['changed_sessions'], 0)
        newer = {(CHANNEL, ''): dict(labels[(CHANNEL, '')], title='修改后的昵称', sequence=200)}
        with patch('claude_project_names.labels', return_value=newer):
            self.assertEqual(self.export()['changed_sessions'], len(original_ids))
            self.assertEqual(self.export()['changed_sessions'], 0)
        self.assertTrue(all(row['project'] == '修改后的昵称' for row in self.sessions().values()))

    def test_text_cleanup_preserves_projects_across_cache_eviction_and_new_replies(self):
        import archive_storage
        self.responses[self.home] = [response(self.home, event(message(in_timeline=True, has_thread=True)))]
        self.export()
        ids = set(self.sessions())
        archive_storage.cleanup_text(self.dest.parent, plan=False)
        self.assertFalse(list((self.dest.parent / 'records').glob('*/*/source.jsonl')))
        self.assertTrue(list((self.dest.parent / 'records').glob('*/*/project-state.jsonl')))
        self.responses[self.home] = []
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.responses[self.home] = [response(self.home, event(message(ANSWER, 'A new answer', role='assistant', seq='2')), mtime=200)]
        self.export()
        self.assertEqual(set(self.sessions()), ids)
        thread = next(row for row in self.sessions().values() if row['claude_project']['view'] == 'thread')
        self.assertIn('Fixture question', self.markdown(thread))
        self.assertIn('A new answer', self.markdown(thread))
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.assertFalse(list((self.dest.parent / 'records').glob('*/*/source.jsonl')))
        archive_storage.save_preferences(self.dest.parent, ['claude-desktop'], False)
        self.export()
        self.assertEqual(self.export()['changed_sessions'], 0)
        thread = next(row for row in self.sessions().values() if row['claude_project']['view'] == 'thread')
        self.assertIn('A new answer', self.markdown(thread))

    def test_thread_starting_title_is_preserved_but_saved_navigation_name_wins(self):
        def starting(title, at):
            return event({'thread_root_id': ROOT, 'title': title, 'at': at}, 'thread_starting')

        self.responses[self.home] = [response(self.home, event(message()) + starting('初始讨论标题', 100))]
        self.export()
        row, = self.sessions().values()
        self.assertEqual(row['title'], '初始讨论标题')
        self.assertTrue(row['project'].startswith('未命名项目 · '))
        # A newer file containing an older event must not roll back the title.
        self.responses[self.home] = [response(self.home, starting('旧启动标题', 90), mtime=200)]
        self.assertEqual(self.export()['changed_sessions'], 0)
        # No title from a response with a corrupt completed message may be saved.
        self.responses[self.home] = [response(self.home, starting('损坏响应标题', 300) + event({'id': ROOT}))]
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.responses[self.home] = [response(self.home, starting('新启动标题', 400))]
        labels = {(CHANNEL, ROOT): {'title': '导航中重命名的讨论', 'sequence': 1, 'source': 'session-navigation'}}
        with patch('claude_project_names.labels', return_value=labels):
            self.assertEqual(self.export()['changed_sessions'], 1)
        row, = self.sessions().values()
        self.assertEqual(row['title'], '导航中重命名的讨论')
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.responses[self.home] = []
        self.assertEqual(self.export()['changed_sessions'], 0)

    def test_overlap_deduplicates_and_repeat_does_not_rewrite(self):
        question = message(attachments=[{'file_id': 'file-fixture', 'filename': 'chart.png',
                                         'mime_type': 'image/png', 'size_bytes': 128}])
        answer = message(ANSWER, 'Fixture complete answer', 'assistant', '2')
        self.responses[self.home] = [
            response(self.home, event(question) + event(answer)),
            response(self.home, event(question) + event(answer), name='overlap_0', mtime=200),
        ]
        result = self.export()
        self.assertEqual(result['changed_sessions'], 1)
        row, = self.sessions().values()
        self.assertEqual(row['messages'], 2)
        self.assertEqual(row['source'], 'code-projects-cache')
        self.assertEqual(row['originator'], 'Claude Code Projects')
        self.assertEqual(row['coverage'], 'partial_cache')
        body = self.markdown(row).split('\n## ', 1)[1]
        self.assertEqual(body.count('Fixture question'), 1)
        self.assertEqual(body.count('Fixture complete answer'), 1)
        snapshot = self.snapshot(row).read_text(encoding='utf-8')
        self.assertIn('file-fixture', snapshot)
        self.assertIn('chart.png', snapshot)
        original = self.files()
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.assertEqual(self.files(), original)

    def test_new_cache_window_and_eviction_keep_old_messages(self):
        self.responses[self.home] = [response(self.home, event(message()))]
        self.export()
        row, = self.sessions().values()
        original_sid = row['id']
        answer = message(ANSWER, 'Later answer only in new window', 'assistant', '2')
        self.responses[self.home] = [response(self.home, event(answer), name='later_0', mtime=300)]
        self.assertEqual(self.export()['changed_sessions'], 1)
        row, = self.sessions().values()
        self.assertEqual(row['id'], original_sid)
        self.assertEqual(row['messages'], 2)
        self.assertIn('Fixture question', self.markdown(row))
        self.assertIn('Later answer only in new window', self.markdown(row))
        original = self.files()
        self.responses[self.home] = []
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.assertEqual(self.files(), original)

    def test_edit_version_wins_over_newer_cache_file_with_old_content(self):
        old = message(body='Original question before edit')
        new = message(body='Revised question after edit', edited_at='2026-11-02T12:00:00Z')
        self.responses[self.home] = [response(self.home, event(old))]
        self.export()
        self.responses[self.home] = [response(self.home, event(new, 'channel_message_updated'),
                                              name='edit_0', mtime=300)]
        self.export()
        row, = self.sessions().values()
        self.assertIn('Revised question after edit', self.markdown(row))
        self.assertNotIn('Original question before edit', self.markdown(row))
        snapshot = self.snapshot(row).read_text(encoding='utf-8')
        self.assertIn('Original question before edit', snapshot)
        self.assertIn('Revised question after edit', snapshot)
        self.responses[self.home] = [response(self.home, event(old), name='stale_0', mtime=900)]
        self.export()
        row, = self.sessions().values()
        self.assertIn('Revised question after edit', self.markdown(row))
        self.assertNotIn('Original question before edit', self.markdown(row))

    def test_http_response_time_orders_metadata_independently_of_file_mtime(self):
        working = message(thread_status='working')
        resolved = message(thread_status='resolved')
        self.responses[self.home] = [
            response(self.home, event(working), name='working_0', mtime=900, response_time=1000),
            response(self.home, event(resolved, 'channel_message_updated'),
                     name='resolved_0', mtime=100, response_time=2000),
        ]
        first, = vault.session_items('claude-desktop', self.home)
        directory = self.root / 'first-read'
        directory.mkdir()
        before = first['prepare'](directory).read_bytes()
        row, = map(json.loads, before.splitlines())
        self.assertEqual(row['cache_revisions'][-1]['message']['thread_status'], 'resolved')
        self.responses[self.home] = [
            response(self.home, event(resolved, 'channel_message_updated'),
                     name='resolved_0', mtime=1, response_time=2000),
            response(self.home, event(working), name='working_0', mtime=10**18, response_time=1000),
        ]
        second, = vault.session_items('claude-desktop', self.home)
        directory = self.root / 'second-read'
        directory.mkdir()
        after = second['prepare'](directory).read_bytes()
        self.assertEqual(second['signature'], first['signature'])
        self.assertEqual(after, before)

    def test_reobserving_archived_old_metadata_does_not_rewrite_or_regress(self):
        working = message(thread_status='working')
        resolved = message(thread_status='resolved')
        self.responses[self.home] = [
            response(self.home, event(working), name='working_0', mtime=100, response_time=1000),
            response(self.home, event(resolved, 'channel_message_updated'),
                     name='resolved_0', mtime=200, response_time=2000),
        ]
        self.assertEqual(self.export()['changed_sessions'], 1)
        row, = self.sessions().values()
        archived, = map(json.loads, self.snapshot(row).read_text(encoding='utf-8').splitlines())
        self.assertEqual(archived['cache_revisions'][-1]['message']['thread_status'], 'resolved')
        before = self.files()
        # An old payload can reappear in a later response as well as a touched file.
        self.responses[self.home] = [
            response(self.home, event(working), name='reobserved_0', mtime=10**18, response_time=3000),
        ]
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.assertEqual(self.files(), before)

    def test_bad_completed_event_cannot_replace_good_snapshot(self):
        self.responses[self.home] = [response(self.home, event(message()))]
        self.export()
        original = self.files()
        unsafe_prefix = event(message(ANSWER, 'Must not publish corrupt response prefix', 'assistant', '2'))
        self.responses[self.home] = [response(self.home, unsafe_prefix + b'event: channel_message\ndata: {bad json}\n\n',
                                              name='bad_0', mtime=400)]
        result = self.export()
        self.assertEqual(result['changed_sessions'], 0)
        self.assertTrue(result.get('warnings'))
        self.assertEqual(self.files(), original)

    def test_incomplete_tail_and_progress_are_not_final_messages(self):
        complete = event(message())
        progress = event({'session_id': 'fixture-session', 'thread_root_id': ROOT,
                          'text': 'Growing partial answer'}, 'session_partial_reply')
        tail = event(message(ANSWER, 'Unfinished tail answer', 'assistant', '2'))[:-1]
        self.responses[self.home] = [response(self.home, complete + progress + tail)]
        result = self.export()
        row, = self.sessions().values()
        self.assertEqual(row['messages'], 1)
        self.assertIn('Fixture question', self.markdown(row))
        self.assertNotIn('Growing partial answer', self.markdown(row))
        self.assertNotIn('Unfinished tail answer', self.markdown(row))
        self.assertTrue(result.get('warnings'))

    def test_notices_do_not_impersonate_users_or_assistant_answers(self):
        notice = message(ANSWER, 'Fixture server lifecycle notice', 'assistant', '2', server_notice=True)
        self.responses[self.home] = [response(self.home, event(message()) + event(notice))]
        self.export()
        row, = self.sessions().values()
        self.assertEqual(row['messages'], 1)
        self.assertNotIn('Fixture server lifecycle notice', self.markdown(row))
        self.assertIn('Fixture server lifecycle notice', self.snapshot(row).read_text(encoding='utf-8'))

    def test_helper_author_without_session_id_is_still_an_assistant(self):
        helper = message(ANSWER, 'Fixture helper answer', None, '2', author={'kind': 'helper'})
        self.responses[self.home] = [response(self.home, event(message()) + event(helper))]
        self.export()
        row, = self.sessions().values()
        self.assertEqual(row['messages'], 2)
        self.assertIn('Fixture helper answer', self.markdown(row))

    def test_channel_main_preserves_order_links_and_discussion_identity(self):
        other_root = 'cmsg_' + '3' * 46
        main = message(in_timeline=True, reply_count='1', thread_status='working')
        reply = message(ANSWER, 'Discussion answer only', 'assistant', '3', in_timeline=False)
        next_main = message(other_root, 'Main agent opens another discussion', 'assistant', '4',
                            thread_root_id=other_root, in_timeline=True, reply_count='0',
                            links=[{'kind': 'thread', 'thread_id': ROOT, 'href': '/untrusted-link'}])
        self.responses[self.home] = [response(self.home, event(next_main) + event(reply) + event(main))]
        self.assertEqual(self.export()['changed_sessions'], 3)
        sessions = list(self.sessions().values())
        channel, = [row for row in sessions if row['claude_project']['view'] == 'main']
        thread, = [row for row in sessions if row['claude_project']['thread_root_id'] == ROOT]
        self.assertEqual(channel['title'], '主对话')
        self.assertEqual(channel['messages'], 2)
        self.assertNotIn('Discussion answer only', self.markdown(channel))
        self.assertIn('Discussion answer only', self.markdown(thread))
        self.assertEqual(thread['claude_project']['reply_count'], 1)
        self.assertEqual([row['id'] for row in channel['claude_project']['messages']], [ROOT, other_root])
        self.assertEqual(channel['claude_project']['messages'][1]['linked_thread_ids'], [ROOT])
        self.assertNotIn('href', json.dumps(channel['claude_project']))
        standalone, = [row for row in sessions if row['claude_project']['view'] == 'timeline_item']
        self.assertEqual(standalone['claude_project']['thread_root_id'], other_root)
        before = self.files()
        self.responses[self.home] = []
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.assertEqual(self.files(), before)

        moved = dict(main, in_timeline=False)
        self.responses[self.home] = [response(self.home, event(moved, 'channel_message_updated'), response_time=400)]
        self.export()
        sessions = self.sessions()
        self.assertNotIn('Fixture question', self.markdown(sessions[channel['id']]))
        self.assertIn('Fixture question', self.markdown(sessions[thread['id']]))

    def test_null_body_updates_keep_text_and_partial_replies_do_not_become_content(self):
        original = message(body='Question\u2028with a Unicode separator', in_timeline=True,
                           thread_status='working')
        updated = message(body=None, in_timeline=True, reply_count='2', thread_status='needs_input')
        answer = message(ANSWER, 'Complete discussion reply', 'assistant', '2', in_timeline=False)
        self.responses[self.home] = [response(self.home, event(original), response_time=100)]
        self.export()
        original_thread = next(row['id'] for row in self.sessions().values()
                               if row['claude_project']['view'] == 'thread')
        self.responses[self.home] = [response(self.home, event(updated, 'channel_message_updated') +
                                              event(answer), response_time=200)]
        self.assertEqual(self.export()['changed_sessions'], 2)
        sessions = self.sessions()
        thread = sessions[original_thread]
        self.assertEqual(thread['claude_project']['status'], 'needs_input')
        self.assertEqual(thread['messages'], 2)
        self.assertIn(original['body'], self.markdown(thread))
        self.assertIn('Complete discussion reply', self.markdown(thread))
        channel = next(row for row in sessions.values() if row['claude_project']['view'] == 'main')
        self.assertEqual(channel['messages'], 1)
        self.assertIn(original['body'], self.markdown(channel))
        before = self.files()
        self.assertEqual(self.export()['changed_sessions'], 0)
        self.assertEqual(self.files(), before)

    def test_main_sequence_is_thread_local_and_timestamps_order_across_timezones(self):
        early_id = 'cmsg_' + '9' * 46
        late_id = 'cmsg_' + '1' * 46
        early = message(early_id, 'First main question', seq='0', thread_root_id=early_id,
                        in_timeline=True, reply_count='0', created_at='2026-11-12T10:00:00+08:00')
        late = message(late_id, 'Later main answer', 'assistant', '0', thread_root_id=late_id,
                       in_timeline=True, reply_count='0', created_at='2026-11-12T03:00:00Z')
        self.responses[self.home] = [response(self.home, event(late) + event(early))]
        self.export()
        main = next(row for row in self.sessions().values() if row['claude_project']['view'] == 'main')
        self.assertEqual([m['id'] for m in main['claude_project']['messages']], [early_id, late_id])
        self.assertLess(self.markdown(main).index('First main question'), self.markdown(main).index('Later main answer'))

    def test_old_thread_snapshot_upgrades_without_live_cache(self):
        self.responses[self.home] = [response(self.home, event(message(in_timeline=True)))]
        self.export()
        sessions = self.sessions()
        thread = next(row for row in sessions.values() if row['claude_project']['view'] == 'thread')
        channel = next(row for row in sessions.values() if row['claude_project']['view'] == 'main')
        # Simulate a v1 thread archive: no channel projection or index relations.
        self.snapshot(channel).unlink()
        sessions.pop(channel['id'])
        thread.pop('claude_project')
        (self.dest / 'index.json').write_text(json.dumps({'sessions': sessions}), encoding='utf-8')
        (self.dest / '.export-cache.json').write_text('{}', encoding='utf-8')
        rows = [json.loads(line) for line in self.snapshot(thread).read_text(encoding='utf-8').split('\n') if line]
        for row in rows:
            row.pop('cache_projection')
            row.pop('project_message')
        self.snapshot(thread).write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
        self.responses[self.home] = []
        self.assertEqual(self.export()['changed_sessions'], 2)
        self.assertIn(thread['id'], self.sessions())
        self.assertEqual(len(self.sessions()), 2)

    def test_product_channel_and_thread_identity_do_not_collide(self):
        sibling = self.home.with_name('Claude-3p')
        sibling.mkdir()
        other_thread = 'cmsg_' + '3' * 46
        self.responses[self.home] = [
            response(self.home, event(message())),
            response(self.home, event(message(channel_id=OTHER_CHANNEL)),
                     name='channel_0', channel=OTHER_CHANNEL),
            response(self.home, event(message(other_thread, thread_root_id=other_thread)),
                     name='thread_0'),
        ]
        self.responses[sibling] = [response(sibling, event(message()))]
        def labels(home, warnings):
            return {(CHANNEL, ''): {'title': Path(home).name + ' 项目',
                    'source': 'session-navigation', 'sequence': 10}}
        with patch('claude_project_names.labels', side_effect=labels):
            self.assertEqual(self.export()['changed_sessions'], 4)
        self.assertEqual(len(self.sessions()), 4)
        self.assertTrue(all(row['messages'] == 1 for row in self.sessions().values()))
        for row in self.sessions().values():
            relation = row['claude_project']
            expected = relation['product'] + ' 项目' if relation['channel_id'] == CHANNEL else '未命名项目 · ' + OTHER_CHANNEL[-8:]
            self.assertEqual(row['project'], expected)

    def test_snapshot_symlink_is_rejected_without_touching_external_data(self):
        self.responses[self.home] = [response(self.home, event(message()))]
        self.export()
        row, = self.sessions().values()
        source = self.snapshot(row)
        outside = self.root / 'outside.jsonl'
        outside.write_bytes(source.read_bytes())
        external_before = outside.read_bytes()
        source.unlink()
        source.symlink_to(outside)
        answer = message(ANSWER, 'New answer must not escape archive', 'assistant', '2')
        self.responses[self.home] = [response(self.home, event(answer), mtime=200)]
        with self.assertRaises((ValueError, RuntimeError)):
            self.export()
        self.assertEqual(outside.read_bytes(), external_before)
        self.assertNotIn('New answer must not escape archive', self.markdown(row))

    def test_missing_existing_snapshot_cannot_shrink_archive_to_new_window(self):
        self.responses[self.home] = [response(self.home, event(message()))]
        self.export()
        row, = self.sessions().values()
        before = self.markdown(row)
        self.snapshot(row).unlink()
        answer = message(ANSWER, 'Only answer remains in live cache', 'assistant', '2')
        self.responses[self.home] = [response(self.home, event(answer), mtime=200)]
        with self.assertRaises((ValueError, RuntimeError)):
            self.export()
        self.assertEqual(self.markdown(row), before)
        self.assertFalse(self.snapshot(row).exists())

    def test_empty_existing_snapshot_cannot_shrink_archive_to_new_window(self):
        self.responses[self.home] = [response(self.home, event(message()))]
        self.export()
        row, = self.sessions().values()
        before = self.markdown(row)
        self.snapshot(row).write_bytes(b'')
        answer = message(ANSWER, 'Only answer remains in live cache', 'assistant', '2')
        self.responses[self.home] = [response(self.home, event(answer), mtime=200)]
        with self.assertRaises((ValueError, RuntimeError)):
            self.export()
        self.assertEqual(self.markdown(row), before)
        self.assertEqual(self.snapshot(row).read_bytes(), b'')


if __name__ == '__main__':
    unittest.main()
