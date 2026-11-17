"""Read Claude's saved project/thread navigation labels without opening the app.

Only Session Storage's Claude-origin cmdk-navigation-history records leave this
reader. LevelDB is read in place; no database is opened for writing or copied.
Historical names can survive sign-out tombstones, so absence is never deletion.
"""
import json
import os
from pathlib import Path
import re
import struct
from urllib.parse import parse_qs, urlsplit

import claude_cache


MAX_BYTES = 32 * 1024 * 1024
_FILE = re.compile(r'[0-9]+\.(?:ldb|log)\Z')
_NAV = re.compile(rb'map-([0-9]+)-cmdk-navigation-history:[A-Za-z0-9:_-]+\Z')
_PROJECT = re.compile(r'/epitaxy/project/([A-Za-z0-9_-]+)/?\Z')


def _varint(data, offset):
    value = 0
    for shift in range(0, 64, 7):
        if offset >= len(data):
            raise ValueError('truncated integer')
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError('oversized integer')


def _crc_table():
    table = []
    for value in range(256):
        for _ in range(8):
            value = (value >> 1) ^ (0x82f63b78 if value & 1 else 0)
        table.append(value)
    return table


_CRC = _crc_table()


def _checksum(data):
    value = 0xffffffff
    for byte in data:
        value = _CRC[(value ^ byte) & 255] ^ (value >> 8)
    value ^= 0xffffffff
    return (((value >> 15) | (value << 17)) + 0xa282ead8) & 0xffffffff


def _snappy(data):
    size, offset = _varint(data, 0)
    if size > MAX_BYTES:
        raise ValueError('decoded block exceeds limit')
    result = bytearray()
    while offset < len(data):
        tag = data[offset]
        offset += 1
        kind = tag & 3
        if kind == 0:
            length = (tag >> 2) + 1
            if length > 60:
                count = length - 60
                if offset + count > len(data):
                    raise ValueError('truncated literal length')
                length = int.from_bytes(data[offset:offset + count], 'little') + 1
                offset += count
            if offset + length > len(data) or len(result) + length > size:
                raise ValueError('invalid literal')
            result.extend(data[offset:offset + length])
            offset += length
        else:
            count = (1, 2, 4)[kind - 1]
            if offset + count > len(data):
                raise ValueError('truncated copy')
            distance = int.from_bytes(data[offset:offset + count], 'little')
            length = 1 + (tag >> 2)
            if kind == 1:
                distance |= (tag & 224) << 3
                length = 4 + ((tag >> 2) & 7)
            offset += count
            if not 0 < distance <= len(result) or len(result) + length > size:
                raise ValueError('invalid copy')
            for _ in range(length):
                result.append(result[-distance])
    if len(result) != size:
        raise ValueError('incomplete decoded block')
    return bytes(result)


def _entries(data):
    if len(data) < 4:
        raise ValueError('missing block restart table')
    count = struct.unpack_from('<I', data, len(data) - 4)[0]
    end = len(data) - 4 * (count + 1)
    if count < 1 or end < 0:
        raise ValueError('invalid block restart table')
    restarts = struct.unpack_from('<' + 'I' * count, data, end)
    if restarts[0] != 0 or any(a >= b for a, b in zip(restarts, restarts[1:])):
        raise ValueError('invalid block restarts')
    offset, key = 0, b''
    while offset < end:
        start = offset
        shared, offset = _varint(data, offset)
        length, offset = _varint(data, offset)
        size, offset = _varint(data, offset)
        if (shared > len(key) or offset + length + size > end
                or (start in restarts and shared != 0)):
            raise ValueError('invalid block entry')
        key = key[:shared] + data[offset:offset + length]
        offset += length
        yield key, data[offset:offset + size]
        offset += size
    if offset != end or any(n >= end and not (n == end == 0) for n in restarts):
        raise ValueError('invalid block boundary')


def _table(data):
    if len(data) < 48 or data[-8:] != bytes.fromhex('57fb808b247547db'):
        raise ValueError('invalid table footer')
    footer = data[-48:-8]
    _, offset = _varint(footer, 0)
    _, offset = _varint(footer, offset)
    index, offset = _varint(footer, offset)
    size, _ = _varint(footer, offset)

    def block(start, length):
        if start + length + 5 > len(data) - 48:
            raise ValueError('invalid block handle')
        raw = data[start:start + length + 1]
        if _checksum(raw) != struct.unpack_from('<I', data, start + length + 1)[0]:
            raise ValueError('block checksum mismatch')
        if raw[-1] not in (0, 1):
            raise ValueError('unsupported block compression')
        return _snappy(raw[:-1]) if raw[-1] else raw[:-1]

    for _, handle in _entries(block(index, size)):
        start, offset = _varint(handle, 0)
        length, offset = _varint(handle, offset)
        if offset != len(handle):
            raise ValueError('invalid index handle')
        yield from _entries(block(start, length))


def _log(data):
    fragments = None
    for start in range(0, len(data), 32768):
        block = data[start:start + 32768]
        offset = 0
        while offset + 7 <= len(block):
            checksum, size, kind = struct.unpack_from('<IHB', block, offset)
            offset += 7
            if checksum == size == kind == 0:
                break
            if offset + size > len(block):
                # An app can be in the middle of writing its last record.
                if start + len(block) == len(data):
                    return
                raise ValueError('invalid log fragment')
            body = block[offset:offset + size]
            offset += size
            if kind not in (1, 2, 3, 4) or _checksum(bytes([kind]) + body) != checksum:
                raise ValueError('log checksum mismatch')
            if kind in (1, 2):
                if fragments is not None:
                    raise ValueError('incomplete log record')
                fragments = bytearray(body)
            elif fragments is None:
                raise ValueError('missing log fragment')
            else:
                fragments.extend(body)
            if len(fragments) > MAX_BYTES:
                raise ValueError('log record exceeds limit')
            if kind not in (1, 4):
                continue
            if len(fragments) < 12:
                raise ValueError('invalid write batch')
            sequence, count = struct.unpack_from('<QI', fragments)
            position = 12
            for number in range(count):
                if position >= len(fragments) or fragments[position] not in (0, 1):
                    raise ValueError('invalid write operation')
                operation = fragments[position]
                position += 1
                size, position = _varint(fragments, position)
                key = fragments[position:position + size]
                position += size
                value = b''
                if operation == 1:
                    size, position = _varint(fragments, position)
                    value = fragments[position:position + size]
                    position += size
                if position > len(fragments) or sequence + number >= 1 << 56:
                    raise ValueError('invalid write batch boundary')
                yield bytes(key) + ((sequence + number) << 8 | operation).to_bytes(8, 'little'), bytes(value)
            if position != len(fragments):
                raise ValueError('unexpected write batch data')
            fragments = None


def labels(home, warnings):
    """Return only validated, nonempty project/thread titles and their sequence."""
    home = Path(home)
    root = home / 'Session Storage'
    if not root.is_dir():
        return {}
    rows = []
    try:
        root.resolve().relative_to(home.resolve())
        for path in sorted(root.iterdir()):
            if not _FILE.fullmatch(path.name):
                continue
            try:
                before = path.lstat()
                if not claude_cache._regular(before) or before.st_size > MAX_BYTES:
                    continue
                flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
                with os.fdopen(os.open(path, flags), 'rb') as stream:
                    if claude_cache._stamp(os.fstat(stream.fileno())) != claude_cache._stamp(before):
                        raise ValueError('storage changed before reading')
                    data = stream.read(MAX_BYTES + 1)
                    if claude_cache._stamp(os.fstat(stream.fileno())) != claude_cache._stamp(before):
                        raise ValueError('storage changed while reading')
                if (len(data) != before.st_size or
                        claude_cache._stamp(before) != claude_cache._stamp(path.lstat())):
                    raise ValueError('storage changed while reading')
                # Finish validation before accepting any entries from this file.
                rows.extend(list(_table(data) if path.suffix == '.ldb' else _log(data)))
            except (OSError, ValueError, IndexError, struct.error):
                warnings.append('Claude project labels ' + path.name + ': unavailable or invalid; preserving saved names')
    except (OSError, ValueError):
        warnings.append('Claude project label storage unavailable; preserving saved names')
        return {}
    maps = {value for key, value in rows if len(key) >= 8
            and key[:-8].startswith(b'namespace-') and key[:-8].endswith(b'-https://claude.ai/')
            and value.isdigit() and key[-8] == 1}
    result = {}
    for key, value in rows:
        match = _NAV.fullmatch(key[:-8]) if len(key) >= 8 else None
        if not match or match[1] not in maps or key[-8] != 1 or not value:
            continue
        try:
            items = json.loads(value.decode('utf-16-le'))
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or item.get('kind') not in ('epitaxy-project', 'epitaxy-thread'):
                    continue
                title, href = item.get('title'), item.get('href')
                if not isinstance(title, str) or not title.strip() or len(title) > 2048 or not isinstance(href, str):
                    continue
                url = urlsplit(href)
                project = _PROJECT.fullmatch(url.path)
                if not project or url.scheme or url.netloc or url.fragment:
                    continue
                thread = parse_qs(url.query).get('thread', [''])[0]
                channel = project[1]
                identity = (channel, thread)
                expected = item['kind'] + ':' + channel + ('/' + thread if thread else '')
                if item.get('key') != expected or (item['kind'] == 'epitaxy-thread') != bool(thread):
                    continue
                sequence = int.from_bytes(key[-8:], 'little') >> 8
                label = {'title': title.strip(), 'sequence': sequence, 'source': 'session-navigation'}
                if sequence > result.get(identity, {}).get('sequence', -1):
                    result[identity] = label
        except (ValueError, UnicodeError):
            continue
    return result
