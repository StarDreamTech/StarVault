"""Copy only indexed StarVault archive data into a new portable folder."""
import datetime
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import uuid

import archive_api
import archive_storage
import skills_backup


RECORD_FILES = ('manifest.json', 'dialogue.jsonl', 'operations.jsonl', 'project-state.jsonl',
                'source.jsonl', 'source.jsonl.zst', 'source.jsonl.zstd')
README = ('# 星匣 · 可迁移档案\n\n'
          '把整个文件夹带到新电脑，安装星匣后选择“备份与迁移 → 打开已有档案”，再选择本文件夹。\n\n'
          '也可直接阅读各来源 sessions/ 中的 Markdown。请保留文件夹内部结构，图片使用相对路径关联。\n\n'
          '这里保存的是已收集的聊天档案和已有资源，不会自动补齐原应用中未保存的内容。\n'
          '这是检索阅读档案，不会把会话恢复为原 AI 客户端中可继续聊天的记录。\n')


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inventory(root):
    root = archive_api._root(root)
    rows, warnings = archive_api._catalog(root)
    if warnings:
        raise ValueError('档案索引存在读取问题，请修复后重试：' + '; '.join(warnings[:3]))
    if not rows:
        raise ValueError('档案中还没有聊天记录，请先收集本机记录或打开已有档案。')
    files = {}

    def include(relative, required=True):
        path = archive_api.safe_path(root, relative)
        if not required and not path.exists():
            return
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('档案内容不是普通文件：' + relative)
        files[relative] = stamp(info)

    indexes = {branch: archive_api._index(root, branch) for branch in {row['branch'] for row in rows}}
    for branch in indexes:
        include(branch + '/index.json')
        include(branch + '/README.md', False)
    for row in rows:
        branch, sid = row['branch'], row['session_id']
        include(row['_file'])
        record = f'records/{branch}/{sid}/'
        index = indexes[branch]['sessions'].get(sid)
        if not isinstance(index, dict) or archive_api._row(branch, sid, index, indexes[branch].get('tool', '')) != row:
            raise RuntimeError('档案索引在检查期间发生变化，请重试。')
        has_record = 'local_record' in index or archive_api.safe_path(root, record + 'manifest.json').exists()
        for name in RECORD_FILES:
            include(record + name, has_record and name in ('manifest.json', 'dialogue.jsonl'))
        if has_record:
            manifest = archive_api._json(root, record + 'manifest.json')
            if not isinstance(manifest, dict) or manifest.get('branch') != branch or manifest.get('session_id') != sid:
                raise ValueError('会话清单与索引身份不一致：' + sid)
    resources = 0
    for folder in ('images', 'attachments'):
        directory = archive_api.safe_path(root, folder)
        if directory.exists():
            for path in directory.iterdir():
                if re.fullmatch(r'[0-9a-f]{64}\.[A-Za-z0-9]+', path.name):
                    include(folder + '/' + path.name)
                    resources += 1
    skills = skills_backup._read_index(root)
    if skills['items']:
        include('skills/index.json')
        for item in skills['items']:
            if not isinstance(item, dict) or not isinstance(item.get('versions'), list) or not item['versions']:
                raise ValueError('Skill 备份索引缺少版本信息')
            for version in item['versions']:
                if not isinstance(version, dict):
                    raise ValueError('Skill 备份版本无效')
                digest = version.get('version', '')
                relative = version.get('archive')
                if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest) or relative != f'skills/objects/{digest}.zip':
                    raise ValueError('Skill 备份路径无效')
                include(relative)
    result = {'transfer_archive': True, 'plan': True, 'sessions': len(rows), 'files': len(files),
              'bytes': sum(value[2] for value in files.values()), 'resources': resources,
              'skills': len(skills['items']), 'tools': sorted({row['tool'] for row in rows})}
    return root, files, result


def transfer(root, destination=None, plan=False):
    root, files, result = inventory(root)
    if plan:
        return result
    if destination is None:
        raise ValueError('请选择保存档案的位置。')
    parent = Path(destination).expanduser().resolve(strict=True)
    if not parent.is_dir() or parent == root or root in parent.parents:
        raise ValueError('请选择当前档案之外的文件夹作为保存位置。')
    if shutil.disk_usage(parent).free < result['bytes'] + 16 * 1024**2:
        raise RuntimeError('保存位置空间不足，当前档案保持不变。')
    name = 'StarVault-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    target = parent / name
    policy = archive_storage.preferences(root)
    with tempfile.TemporaryDirectory(prefix='.starvault-transfer-', dir=parent) as temporary:
        staged = Path(temporary) / name
        staged.mkdir(mode=0o700)
        for relative, expected in files.items():
            source = archive_api.safe_path(root, relative)
            flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
            with os.fdopen(os.open(source, flags), 'rb') as incoming:
                if stamp(os.fstat(incoming.fileno())) != expected:
                    raise RuntimeError('档案在导出期间发生变化，请完成收集后重试。')
                output = staged / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open('xb') as stream:
                    shutil.copyfileobj(incoming, stream, 1024 * 1024)
                if stamp(os.fstat(incoming.fileno())) != expected or output.stat().st_size != expected[2]:
                    raise RuntimeError('档案在导出期间发生变化，请重试。')
        for relative, expected in files.items():
            if stamp(archive_api.safe_path(root, relative).stat()) != expected:
                raise RuntimeError('档案在导出期间发生变化，请重试。')
        # Do not bring application configuration, Git settings or automatic jobs.
        (staged / 'README.md').write_text(README, encoding='utf-8')
        archive_storage.save_preferences(staged, result['tools'], policy.get('text_only', False))
        copied, warnings = archive_api._catalog(staged)
        if warnings or len(copied) != result['sessions']:
            raise ValueError('导出档案校验失败，当前档案保持不变。')
        staged.rename(target)
    return {**result, 'plan': False, 'destination': str(target)}
