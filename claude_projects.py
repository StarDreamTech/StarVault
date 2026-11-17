"""Merge complete Claude Code Projects messages from verified local cache bodies.

This is a partial, append-preserving archive, not an account export. HTTP headers
never enter the snapshot; only message objects and their observed revisions do.
"""
import datetime
import hashlib
import json
from pathlib import Path
import re
import urllib.parse

import archive_api
import claude_cache
import claude_desktop
import claude_project_names


FORMAT = 3
MESSAGE_EVENTS = ('channel_message', 'channel_message_updated')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def role(message):
    if message.get('server_notice'):
        return 'system'
    if message.get('author_account_id'):
        return 'user'
    author = message.get('author')
    if (message.get('author_agent_id') or message.get('author_session_id') or
            (isinstance(author, dict) and author.get('kind') in ('agent', 'helper'))):
        return 'assistant'
    return 'system'


def message_events(body, warnings, name):
    """Parse full SSE events; a malformed completed message rejects this response."""
    text = body.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    chunks = text.split('\n\n')
    if chunks[-1].strip():
        warnings.append(name + ': incomplete trailing SSE event ignored')
    result, titles = [], []
    for ordinal, chunk in enumerate(chunks[:-1]):
        event = 'message'
        data = []
        for line in chunk.split('\n'):
            key, sep, value = line.partition(':')
            if value.startswith(' '):
                value = value[1:]
            if key == 'event':
                event = value
            elif key == 'data':
                data.append(value)
        if event not in (*MESSAGE_EVENTS, 'thread_starting'):
            continue
        value = json.loads('\n'.join(data))
        if not isinstance(value, dict):
            raise ValueError('message event is not an object')
        if event == 'thread_starting':
            title, root, at = value.get('title'), value.get('thread_root_id'), value.get('at')
            if (isinstance(title, str) and title.strip() and len(title) <= 2048
                    and isinstance(root, str) and re.fullmatch(r'[A-Za-z0-9_-]+', root)
                    and type(at) is int and at >= 0):
                title.encode('utf-8')
                titles.append((ordinal, root, title.strip(), at))
            continue
        for field in ('id', 'channel_id', 'created_at', 'seq'):
            if not isinstance(value.get(field), str) or not value[field]:
                raise ValueError('invalid message field: ' + field)
        # App status updates can omit the body (null). They carry relationships,
        # not a replacement reply or evidence that the original text was deleted.
        if not isinstance(value.get('body'), str) and not (
                event == 'channel_message_updated' and value.get('body') is None):
            raise ValueError('invalid message body')
        if len(value['seq']) > 64 or not value['seq'].isascii() or not value['seq'].isdigit():
            raise ValueError('invalid message sequence')
        if value.get('thread_root_id') is not None and not isinstance(value['thread_root_id'], str):
            raise ValueError('invalid thread ID')
        encoded(value).encode('utf-8')
        result.append((ordinal, event, value))
    return result, titles


def merge_label(labels, key, label):
    if not isinstance(label, dict) or not isinstance(label.get('title'), str) or not label['title'].strip():
        return

    def order(item):
        # Navigation may contain a renamed title; a stream's initial title is
        # only a fallback. Its timestamps never compete with LevelDB sequences.
        if item.get('source') == 'session-navigation' and type(item.get('sequence')) is int:
            return (1, item['sequence'])
        observed = item.get('observed')
        if (item.get('source') == 'thread-starting' and isinstance(observed, list)
                and len(observed) == 3 and all(type(value) is int for value in observed)):
            return (0, *observed)
        return (-1,)

    if order(label) > order(labels.get(key, {})):
        labels[key] = label


def revision_order(revision):
    message = revision['message']
    timestamp = message.get('edited_at') or message['created_at']
    try:
        parsed = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        instant = parsed.timestamp()
    except (ValueError, AttributeError, OverflowError):
        instant = 0
    return (instant, *revision['observed'], encoded(message))


def merge_revision(messages, revision):
    """Retain every distinct message version, even when an older window reappears."""
    message = revision['message']
    versions = messages.setdefault(message['id'], {})
    digest = hashlib.sha256(encoded(message).encode('utf-8')).hexdigest()
    previous = versions.get(digest)
    if previous is None or revision_order(revision) > revision_order(previous):
        versions[digest] = revision


def previous_messages(path, identity):
    messages = {}
    if not path.exists():
        return messages
    # A bad existing snapshot must never be replaced by a smaller cache window.
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if not line.endswith('\n'):
                raise ValueError('Incomplete Claude Projects archive snapshot')
            row = json.loads(line)
            if (not isinstance(row, dict) or row.get('cache_identity') != identity or
                    not isinstance(row.get('cache_revisions'), list) or not row['cache_revisions']):
                raise ValueError('Invalid Claude Projects archive snapshot')
            for revision in row['cache_revisions']:
                if (not isinstance(revision, dict) or not isinstance(revision.get('message'), dict) or
                        not isinstance(revision.get('observed'), list) or len(revision['observed']) != 2 or
                        not all(isinstance(v, int) for v in revision['observed'])):
                    raise ValueError('Invalid Claude Projects message revision')
                message = revision['message']
                if (not isinstance(message.get('id'), str) or message['id'] != row.get('uuid') or
                        message.get('channel_id') != identity[2] or
                        ((message.get('thread_root_id') or '') != identity[3] and
                         row.get('cache_projection') != 'channel_timeline') or
                        (not isinstance(message.get('body'), str) and not (
                            revision.get('event') == 'channel_message_updated' and message.get('body') is None)) or
                        not isinstance(message.get('created_at'), str) or
                        len(str(message.get('seq', ''))) > 64 or
                        not str(message.get('seq', '')).isascii() or
                        not str(message.get('seq', '')).isdigit()):
                    raise ValueError('Invalid Claude Projects archived message')
                merge_revision(messages, revision)
    if not messages:
        raise ValueError('Empty Claude Projects archive snapshot; preserving existing history')
    return messages


def session_id(identity):
    return 'claude-projects-' + hashlib.sha256(encoded(identity).encode('utf-8')).hexdigest()[:32]


def current_message(versions):
    revisions = list(versions.values())
    latest = max(revisions, key=lambda revision: (*revision['observed'], encoded(revision['message'])))
    message = dict(latest['message'])
    texts = [revision for revision in revisions if isinstance(revision['message'].get('body'), str)]
    message['body'] = max(texts, key=revision_order)['message']['body'] if texts else ''
    return message


def on_main(message):
    return message.get('in_timeline') is True or (
        not message.get('thread_root_id') and message.get('in_timeline') is not False)


def count(value):
    text = str(value)
    return int(text) if len(text) < 16 and text.isascii() and text.isdigit() else None


def main_order(row):
    # seq is scoped to a discussion (many different roots have seq="0").
    # Use instants for the channel projection, keeping seq only as a tie-breaker.
    try:
        created = datetime.datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
        if created.tzinfo is None:
            created = created.replace(tzinfo=datetime.timezone.utc)
        instant = created.timestamp()
    except (ValueError, OverflowError, OSError):
        instant = float('inf')
    return (instant, int(row['project_message']['seq']), row['uuid'])


def session_items(home=None, previous_root=None, warnings=None):
    warnings = warnings if warnings is not None else []
    existing = {}
    if previous_root is not None:
        destination = Path(previous_root).absolute()
        index = archive_api.safe_path(destination.parent, destination.name + '/index.json')
        if index.exists():
            existing = json.loads(index.read_text(encoding='utf-8'))['sessions']
    groups = {}
    labels = {}
    # Upgrade existing snapshots too: a cache eviction must not strand old
    # discussions outside the channel hierarchy or shrink its main dialogue.
    if previous_root is not None:
        for sid, row in existing.items():
            if row.get('source') != 'code-projects-cache':
                continue
            snapshot = archive_api.safe_path(destination.parent,
                                            f'records/{destination.name}/{sid}/source.jsonl')
            state = archive_api.safe_path(destination.parent,
                                          f'records/{destination.name}/{sid}/project-state.jsonl')
            manifest = archive_api.safe_path(destination.parent,
                                             f'records/{destination.name}/{sid}/manifest.json')
            saved = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
            if state.exists() and (not snapshot.is_file() or saved.get('metadata', {}).get('text_only')):
                snapshot = state
            if not snapshot.is_file():
                raise ValueError('Missing Claude Projects archive snapshot; preserving existing history')
            with snapshot.open(encoding='utf-8') as stream:
                first = json.loads(next(stream, '{}'))
            identity = first.get('cache_identity')
            if (not isinstance(identity, list) or len(identity) != 4 or
                    not all(isinstance(value, str) for value in identity) or
                    session_id(identity) != sid):
                raise ValueError('Invalid Claude Projects archive identity')
            for suffix, field in (('', 'project_label'), (identity[3], 'thread_label')):
                label = row.get('claude_project', {}).get(field)
                label_key = (*identity[:3], suffix)
                merge_label(labels, label_key, label)
            for versions in previous_messages(snapshot, identity).values():
                for revision in versions.values():
                    message = revision['message']
                    key = (*identity[:3], message.get('thread_root_id') or '')
                    merge_revision(groups.setdefault(key, {}), revision)
    for product_home in claude_desktop.homes(home):
        product = 'Claude-3p' if product_home.name == 'Claude-3p' else 'Claude'
        for (channel, thread), label in claude_project_names.labels(product_home, warnings).items():
            key = (product, 'https://claude.ai', channel, thread)
            merge_label(labels, key, label)
        for response in claude_cache.iter_responses(product_home, warnings=warnings):
            url = urllib.parse.urlsplit(response['url'])
            match = re.fullmatch(r'/v1/code/channels/([^/]+)/messages/stream', url.path)
            if not match:
                # ponytail: only the observed SSE schema is supported; add JSON
                # timeline routes when an actual response establishes their shape.
                continue
            channel = match.group(1)
            try:
                events, titles = message_events(response['body'], warnings, response['path'].name)
                if any(message['channel_id'] != channel for _, _, message in events):
                    raise ValueError('channel does not match cache URL')
            except (ValueError, UnicodeError) as error:
                warnings.append(response['path'].name + ': invalid Projects response (' +
                                type(error).__name__ + ')')
                continue
            for ordinal, root, title, at in titles:
                key = (product, url.scheme + '://' + url.netloc, channel, root)
                merge_label(labels, key, {'title': title, 'source': 'thread-starting',
                    'observed': [at, response.get('response_time', response['mtime_ns']), ordinal]})
            for ordinal, event, message in events:
                identity = (product, url.scheme + '://' + url.netloc, channel,
                            message.get('thread_root_id') or '')
                messages = groups.setdefault(identity, {})
                revision = {'event': event, 'message': message,
                            'observed': [response.get('response_time', response['mtime_ns']), ordinal]}
                digest = hashlib.sha256(encoded(message).encode('utf-8')).hexdigest()
                if digest not in messages.get(message['id'], {}):
                    merge_revision(messages, revision)

    # A channel's main dialogue is an ordered projection of explicitly marked
    # timeline messages. A root can belong to both this view and a discussion.
    mains = {}
    for key, messages in groups.items():
        main = mains.setdefault((*key[:3], ''), {})
        for mid, versions in messages.items():
            if any(on_main(revision['message']) for revision in versions.values()):
                main[mid] = versions
    for key, messages in mains.items():
        if messages:
            groups[key] = messages

    for key, fresh in sorted(groups.items()):
        identity = list(key)
        sid = session_id(identity)
        messages = fresh
        rows = []
        for mid, versions in messages.items():
            revisions = sorted(versions.values(), key=revision_order)
            message = current_message(versions)
            kind = role(message)
            rows.append({'type': kind, 'uuid': mid, 'timestamp': message['created_at'],
                         'message': {'role': kind, 'content': message['body']},
                         'cache_identity': identity, 'cache_revisions': revisions,
                         'cache_projection': 'channel_timeline' if not identity[3] else 'thread',
                         'archive_visible': bool(identity[3]) or on_main(message),
                         'project_message': message})
        rows.sort(key=main_order if not identity[3] else
                  lambda row: (int(row['project_message']['seq']), row['uuid']))
        visible = [row for row in rows if row['archive_visible'] and row['type'] in ('user', 'assistant')
                   and row['message']['content'].strip()]
        if not visible and sid not in existing:
            continue
        # Use the actual root, including discussions opened by the main agent.
        root = next((row for row in visible if row['uuid'] == identity[3]), None)
        first_user = next((row for row in visible if row['type'] == 'user'), None)
        title_row = root or first_user or (visible[0] if visible else None)
        title = title_row['message']['content'].strip().split('\n')[0][:160] if title_row else 'Projects 讨论串'
        project_label = labels.get((*key[:3], ''), {})
        thread_label = labels.get(key, {}) if identity[3] else {}
        root_message = next((row['project_message'] for row in rows if row['uuid'] == identity[3]), {})
        view = 'thread' if identity[3] else 'main'
        if (identity[3] and on_main(root_message) and count(root_message.get('reply_count')) == 0
                and root_message.get('has_thread') is not True
                and not any(row['uuid'] != identity[3] for row in visible)):
            view = 'timeline_item'
        relation = {'product': identity[0], 'channel_id': identity[2],
                    'project_label': project_label, 'thread_label': thread_label,
                    'view': view, 'thread_root_id': identity[3],
                    'root_in_timeline': root_message.get('in_timeline'),
                    'status': root_message.get('thread_status') if isinstance(root_message.get('thread_status'), str) else '',
                    'reply_count': count(root_message.get('reply_count')),
                    'messages': []}
        for row in visible:
            message = row['project_message']
            links = message.get('links') if isinstance(message.get('links'), list) else []
            relation['messages'].append({
                'id': row['uuid'], 'thread_root_id': message.get('thread_root_id') or '',
                'timestamp': row['timestamp'], 'role': row['type'],
                'has_thread': message.get('has_thread') is True or (count(message.get('reply_count')) or 0) > 0,
                'linked_thread_ids': sorted({link['thread_id'] for link in links
                    if isinstance(link, dict) and link.get('kind') == 'thread' and
                    isinstance(link.get('thread_id'), str) and link['thread_id']})})
        meta = {'title': thread_label.get('title', title) if identity[3] else '主对话',
                'project': project_label.get('title') or ('未命名项目 · ' + identity[2][-8:]),
                'project_id': identity[2],
                'source': 'code-projects-cache', 'origin_kind': 'claude-desktop',
                'originator': 'Claude Code Projects', 'coverage': 'partial_cache',
                'claude_project': relation,
                'origin_metadata': {'product': identity[0], 'channel_id': identity[2],
                                    'thread_root_id': identity[3], 'cache_format': FORMAT,
                                    'coverage': 'partial_cache'}}
        data = ''.join(encoded(row) + '\n' for row in rows).encode('utf-8')
        # Cache-file timestamps are provenance, not new chat content. Touching or
        # evicting identical cache entries must not rewrite archived conversations.
        content = [[row['uuid'], row['project_message'],
                    sorted((revision['message'] for revision in row['cache_revisions']), key=encoded)] for row in rows]
        signature = ['claude-projects', FORMAT, hashlib.sha256(encoded([meta, content]).encode('utf-8')).hexdigest()]

        def prepare(directory, data=data):
            target = Path(directory) / 'source.jsonl'
            target.write_bytes(data)
            return target

        yield {'id': sid, 'meta': meta, 'origin': 'Claude Code Projects local cache',
               'signature': signature, 'prepare': prepare}
