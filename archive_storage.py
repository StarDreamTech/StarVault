"""Manual import preferences and archive-only removal of resource copies."""
import hashlib
import json
from pathlib import Path
import re
import stat

import archive_api
import resources


TOOLS = ('codex', 'claude', 'claude-desktop', 'workbuddy', 'openclaw', 'dsh', 'chatgpt')
SNAPSHOTS = ('source.jsonl', 'source.jsonl.zst', 'source.jsonl.zstd')


def preferences(root):
    return resources.read(archive_api.safe_path(Path(root), '.import-policy.json'), {})


def text_only(root):
    # Existing archives retain their old behaviour until the user chooses text mode.
    return preferences(root).get('text_only', False) is True


def source_snapshots(root):
    value = preferences(root)
    return not value.get('text_only', False) and value.get('source_snapshots', True) is True


def save_preferences(root, tools, only_text=True, snapshots=None):
    tools = list(dict.fromkeys(tools))
    if not tools or set(tools) - set(TOOLS):
        raise ValueError('Select at least one supported conversation source')
    value = {'tools': tools, 'text_only': bool(only_text), 'manual_only': True,
             'source_snapshots': not only_text if snapshots is None else bool(snapshots)}
    resources.write(archive_api.safe_path(Path(root), '.import-policy.json'), value)
    if only_text:
        resources.save_policy(root, [])
    return value


def project_state(path, sid):
    """Retain revisions needed to merge an evicted Projects cache, without duplicate projections."""
    import claude_projects
    with path.open(encoding='utf-8') as stream:
        identity = json.loads(next(stream, '{}')).get('cache_identity')
    if not isinstance(identity, list) or len(identity) != 4 or claude_projects.session_id(identity) != sid:
        raise ValueError('Invalid Claude Projects state identity')
    claude_projects.previous_messages(path, identity)
    rows = []
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            rows.append({key: row[key] for key in ('uuid', 'cache_identity', 'cache_revisions', 'cache_projection')
                         if key in row})
    return ''.join(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n' for row in rows).encode()


def cleanup_text(root, plan=True):
    """Validate all retained text before unlinking only known archive resource objects."""
    root = archive_api._root(root)
    rows, warnings = archive_api._catalog(root)
    if warnings or not rows:
        raise ValueError('A readable conversation archive is required before cleanup')
    retained = []; changes = []; candidates = {}; states = []

    def checked(relative):
        path = archive_api.safe_path(root, relative)
        if path.exists() and not stat.S_ISREG(path.stat().st_mode):
            raise ValueError('Archive object is not a regular file: ' + relative)
        return path

    def candidate(path):
        relative = path.relative_to(root).as_posix()
        path = checked(relative)
        if path.is_file():
            s = path.stat()
            candidates[relative] = (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)

    for row in rows:
        branch, sid = row['branch'], row['session_id']
        record = f'records/{branch}/{sid}/'
        markdown = checked(row['_file'])
        manifest = checked(record + 'manifest.json')
        dialogue = checked(record + 'dialogue.jsonl')
        # Reading and hashing is intentional: a damaged archive must not lose its fallback source.
        for path in (markdown, dialogue):
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for line in stream:
                    digest.update(line)
                    if path == dialogue and line.strip():
                        if not line.endswith(b'\n') or not isinstance(json.loads(line), dict):
                            raise ValueError('Invalid retained dialogue')
            retained.append((path.relative_to(root).as_posix(), digest.hexdigest()))
        data = resources.read(manifest)
        if data.get('branch') != branch or data.get('session_id') != sid:
            raise ValueError('Manifest identity does not match its archive directory')
        metadata = data.setdefault('metadata', {})
        if metadata.get('source') == 'code-projects-cache':
            state = checked(record + 'project-state.jsonl')
            source = checked(record + 'source.jsonl')
            payload = project_state(source if source.exists() else state, sid)
            states.append((state, payload))
            metadata['project_state'] = record + 'project-state.jsonl'
        metadata.update(text_only=True, source_snapshots=False, source_retained=False)
        changes.append((manifest, data))
        for name in SNAPSHOTS:
            candidate(checked(record + name))

    # Include old snapshot formats left by previous exports, even if no longer indexed.
    records = archive_api.safe_path(root, 'records')
    for branch in records.iterdir():
        archive_api.safe_path(root, branch.relative_to(root).as_posix())
        if not branch.is_dir(): continue
        for session in branch.iterdir():
            archive_api.safe_path(root, session.relative_to(root).as_posix())
            if not session.is_dir(): continue
            if any((session / name).exists() for name in SNAPSHOTS):
                if not any(m.parent == session for m, _ in changes):
                    raise ValueError('Unindexed source snapshot; retain it until its text is recovered')
    for folder in ('images', 'attachments'):
        directory = archive_api.safe_path(root, folder)
        if not directory.exists(): continue
        for path in directory.iterdir():
            archive_api.safe_path(root, path.relative_to(root).as_posix())
            if re.fullmatch(r'[0-9a-f]{64}\.[A-Za-z0-9]+', path.name):
                candidate(path)

    estimate = sum(s[2] for s in candidates.values()) - sum(len(data) for path, data in states if not path.exists())
    result = {'cleanup_text': True, 'plan': plan, 'files': len(candidates),
              'estimated_bytes': max(0, estimate), 'sessions': len(rows),
              'retained_text_files': len(retained), 'project_states': len(states)}
    if plan: return result
    saved = preferences(root)
    save_preferences(root, saved.get('tools', list(TOOLS)), True)
    # Publish every required state before deleting even the first full snapshot.
    import vault
    for path, data in states: vault.write(path, data)
    for path, data in changes: resources.write(path, data)
    removed = 0
    for relative, signature in candidates.items():
        path = checked(relative)
        if not path.exists(): continue  # safe to resume an interrupted cleanup
        s = path.stat()
        if (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns) != signature:
            raise RuntimeError('Archive object changed during cleanup; stopped')
        path.unlink()
        removed += s.st_size
    for relative, digest in retained:
        if hashlib.sha256(checked(relative).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Retained text changed during cleanup')
    result.update(removed_bytes=removed, plan=False)
    return result
