"""Synthetic Chromium Session Storage only; never reads a real account."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

import claude_project_names as names


def integer(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result) + bytes([value])


def item(title='演示项目', thread=''):
    return {'kind': 'epitaxy-thread' if thread else 'epitaxy-project',
            'key': ('epitaxy-thread:' if thread else 'epitaxy-project:') + 'chan_demo' + ('/' + thread if thread else ''),
            'href': '/epitaxy/project/chan_demo' + ('?thread=' + thread if thread else ''),
            'title': title}


def storage_rows(title='演示项目'):
    return [(b'namespace-fixture-https://claude.ai/', b'13'),
            (b'map-13-cmdk-navigation-history:fixture:org',
             json.dumps([item(title), item('正式讨论串标题', 'cmsg_demo')]).encode('utf-16-le')),
            (b'namespace-other-https://example.invalid/', b'14'),
            (b'map-14-cmdk-navigation-history:fixture:org', json.dumps([item('错误来源')]).encode('utf-16-le')),
            (b'map-13-unrelated-secret', b'not-conversation-data')]


def log(rows, sequence=1):
    batch = struct.pack('<QI', sequence, len(rows))
    for key, value in rows:
        batch += b'\1' + integer(len(key)) + key + integer(len(value)) + value
    assert len(batch) < 32761
    return struct.pack('<IHB', names._checksum(b'\1' + batch), len(batch), 1) + batch


def table(rows):
    def entries(values):
        block = b''.join(integer(0) + integer(len(k)) + integer(len(v)) + k + v for k, v in values)
        return block + struct.pack('<II', 0, 1)

    def block(data, compressed=False):
        if compressed:
            # One valid Snappy literal. Reader also handles overlapping copies.
            size = len(data)
            size_bytes = max(1, ((size - 1).bit_length() + 7) // 8)
            data = integer(size) + bytes([(59 + size_bytes) << 2]) + (size - 1).to_bytes(size_bytes, 'little') + data
        data += bytes([int(compressed)])
        return data + struct.pack('<I', names._checksum(data))

    values = [(key + ((number + 1) << 8 | 1).to_bytes(8, 'little'), value)
              for number, (key, value) in enumerate(rows)]
    raw = entries(sorted(values))
    data = block(raw, True)
    index_offset = len(data)
    index = entries([(values[-1][0], integer(0) + integer(len(data) - 5))])
    data += block(index)
    footer = integer(0) + integer(0) + integer(index_offset) + integer(len(index))
    return data + footer.ljust(40, b'\0') + bytes.fromhex('57fb808b247547db')


class ProjectNamesTest(unittest.TestCase):
    def test_log_and_compressed_table_recover_only_claude_navigation(self):
        for suffix, build in (('log', log), ('ldb', table)):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp) / 'Claude'
                root = home / 'Session Storage'
                root.mkdir(parents=True)
                path = root / ('000001.' + suffix)
                data = build(storage_rows())
                path.write_bytes(data)
                before = path.stat().st_mtime_ns
                warnings = []
                found = names.labels(home, warnings)
                self.assertEqual(warnings, [])
                self.assertEqual(len(found), 2)
                self.assertEqual(found[('chan_demo', '')]['title'], '演示项目')
                self.assertEqual(found[('chan_demo', 'cmsg_demo')]['title'], '正式讨论串标题')
                self.assertNotIn('not-conversation-data', str(found))
                self.assertEqual(path.read_bytes(), data)
                self.assertEqual(path.stat().st_mtime_ns, before)
        self.assertEqual(names._snappy(b'\x05\x00a\x01\x01'), b'aaaaa')

    def test_corrupt_files_and_partial_tail_cannot_replace_verified_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = home / 'Session Storage'
            root.mkdir()
            good = log(storage_rows())
            (root / '000001.log').write_bytes(good + log(storage_rows('尾部未完成'), 100)[:-10])
            corrupted = bytearray(table(storage_rows('校验损坏')))
            corrupted[3] ^= 1
            (root / '000002.ldb').write_bytes(corrupted)
            warnings = []
            self.assertEqual(names.labels(home, warnings)[('chan_demo', '')]['title'], '演示项目')
            self.assertEqual(len(warnings), 1)

    def test_sequence_orders_titles_and_navigation_identity_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = home / 'Session Storage'
            root.mkdir()
            (root / '000001.log').write_bytes(log(storage_rows('新昵称'), 100))
            rows = storage_rows('旧昵称')
            (root / '000002.log').write_bytes(log(rows))
            bad = item('伪造关联')
            bad['href'] = 'https://example.invalid/epitaxy/project/chan_demo'
            (root / '000003.log').write_bytes(log([(rows[1][0], json.dumps([bad]).encode('utf-16-le'))], 200))
            self.assertEqual(names.labels(home, [])[('chan_demo', '')]['title'], '新昵称')


if __name__ == '__main__':
    unittest.main()
