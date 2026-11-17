"""Confirmed native session relationships; unknown identities stay unknown."""
import json
from pathlib import Path

import archive_api


def identifier(value, current=''):
    if not isinstance(value, str) or not value or len(value) > 256 or value == current:
        return ''
    try:
        return archive_api.component(value)
    except ValueError:
        return ''


def label(value):
    return value.split('\n', 1)[0].strip()[:160] if isinstance(value, str) else ''


def codex(payload, current):
    """Read explicit spawn/fork identities, never derive a parent from a title."""
    source = payload.get('source')
    subagent = source.get('subagent') if isinstance(source, dict) else None
    spawn = subagent.get('thread_spawn') if isinstance(subagent, dict) else None
    spawn = spawn if isinstance(spawn, dict) else {}
    parents = {identifier(value, current) for value in (
        payload.get('parent_thread_id'), spawn.get('parent_thread_id')) if value is not None}
    relations = []
    # Conflicting or malformed explicit parents must not choose an arbitrary one.
    if len(parents) == 1 and '' not in parents:
        relations.append({'kind': 'subagent', 'parent_id': parents.pop(),
                          'agent_name': label(payload.get('agent_nickname') or spawn.get('agent_nickname')),
                          'agent_type': label(payload.get('agent_role') or spawn.get('agent_role'))})
    fork = identifier(payload.get('forked_from_id'), current)
    if fork:
        relations.append({'kind': 'fork', 'parent_id': fork})
    return relations


def claude(path, current):
    """Claude Code owns <session>/subagents/agent-<id>.jsonl and its sidecar."""
    path = Path(path)
    if path.parent.name != 'subagents' or not path.stem.startswith('agent-'):
        return {}
    owner = identifier(path.parent.parent.name)
    if not owner:
        return {}
    sidecar = path.with_suffix('.meta.json')
    meta = {}
    try:
        with sidecar.open('rb') as stream:
            raw = stream.read(65537)
        if len(raw) <= 65536:
            value = json.loads(raw)
            if isinstance(value, dict):
                meta = value
    except (OSError, ValueError):
        pass  # The optional description is not required to archive the transcript.
    parent = owner
    if meta.get('parentAgentId') not in (None, '', 'main'):
        agent = identifier(meta['parentAgentId'])
        parent = owner + '--' + (agent if agent.startswith('agent-') else 'agent-' + agent) if agent else ''
    parent = identifier(parent, current)
    return {'source': 'subagent', 'session_relations': ([{
        'kind': 'subagent', 'parent_id': parent,
        'agent_name': label(meta.get('description')), 'agent_type': label(meta.get('agentType')),
    }] if parent else [])}
