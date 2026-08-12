#!/usr/bin/env python3
"""批量准备所有卷：生成卷骨架与章节 index.md，并报告校验结果。

- 以"文件夹分组 markdown"发现卷（复用 md2hugo.discover_volumes），
  通用容器词文件夹（chapter/group/...）不作为卷名，其 .md 上浮到父卷。
- sidebar 可选：存在时用它生成章节权重；不存在时按文件名字母序。
- 幂等：已完成章节（描述非空且非"待"）与已存在的 _index.md 跳过，--force 强制重跑。
- 复用 md2hugo 模块函数，无 subprocess。
"""
import argparse
import sys
from pathlib import Path

from md2hugo import (check_volume, cmd_prepare_chapter, cmd_prepare_volume,
                     discover_volumes, read_frontmatter_fields)

_SCRIPT_DIR = Path(__file__).resolve().parent


def find_repo_root(start):
    """向上查找含 docs/ 目录的仓库根。"""
    p = Path(start).resolve()
    for d in [p, *p.parents]:
        if (d / 'docs').is_dir():
            return d
    return None


def common_parent(files):
    """章节文件共享的公共父目录；不唯一（散落多处）时返回 None。"""
    parents = {Path(f).parent for f in files}
    return next(iter(parents)) if len(parents) == 1 else None


def chapter_done(index_path):
    """章节是否已生成且描述非空（视为完成，可跳过）。"""
    if not Path(index_path).exists():
        return False
    desc = read_frontmatter_fields(index_path).get('description', '')
    desc = desc.strip().strip('"').strip()
    return bool(desc) and '待' not in desc


def prepare_volume(vol_dir, out_dir, force):
    """生成卷 _index.md 骨架；已存在且非 force 时跳过。返回是否生成。"""
    out_dir = Path(out_dir)
    if (out_dir / vol_dir.name / '_index.md').exists() and not force:
        return False
    sidebar = vol_dir / '_sidebar.md'
    readme = vol_dir / 'README.md'
    cmd_prepare_volume(argparse.Namespace(
        sidebar=str(sidebar) if sidebar.exists() else None,
        readme=str(readme) if readme.exists() else None,
        volume_name=vol_dir.name, out=str(out_dir)))
    return True


def prepare_chapter(vol_dir, ch_file, out_dir, image_root, force, chapter_dir):
    """准备一章 index.md；已完成且非 force 时跳过。返回是否生成。"""
    index_path = Path(out_dir) / vol_dir.name / ch_file.stem / 'index.md'
    if chapter_done(index_path) and not force:
        return False
    sidebar = vol_dir / '_sidebar.md'
    cmd_prepare_chapter(argparse.Namespace(
        sidebar=str(sidebar) if sidebar.exists() else None,
        chapter_dir=str(chapter_dir) if chapter_dir else None,
        chapter=str(ch_file),
        volume_name=vol_dir.name,
        image_root=str(image_root),
        out=str(out_dir),
        date_source='mtime', prompt_regex=None))
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(prog='batch_prepare')
    parser.add_argument('--docs', default=None,
                        help='docs 输入根（默认 <repo>/docs）')
    parser.add_argument('--out', default=None,
                        help='输出根（默认 <repo>）')
    parser.add_argument('--image-root', default=None,
                        help='image 资源根（默认 <docs>/image）')
    parser.add_argument('--volumes', nargs='*', default=None,
                        help='要处理的卷名（默认全部）')
    parser.add_argument('--force', action='store_true',
                        help='强制重跑已完成章节/卷骨架')
    args = parser.parse_args(argv)

    repo = find_repo_root(_SCRIPT_DIR)
    if repo is None:
        print('ERROR: cannot find repo root (no docs/ directory)', file=sys.stderr)
        return 2
    docs = Path(args.docs) if args.docs else repo / 'docs'
    out = Path(args.out) if args.out else repo
    image_root = Path(args.image_root) if args.image_root else docs / 'image'

    volumes = discover_volumes(docs)
    if args.volumes:
        wanted = set(args.volumes)
        volumes = {d: fs for d, fs in volumes.items() if d.name in wanted}
        for name in sorted(wanted - {d.name for d in volumes}):
            print(f'WARNING: volume {name} not found', file=sys.stderr)

    vol_count = 0
    ch_count = 0
    any_fail = False
    for vol_dir, chapter_files in volumes.items():
        if prepare_volume(vol_dir, out, args.force):
            vol_count += 1
        chapter_dir = common_parent(chapter_files)
        for ch_file in sorted(chapter_files):
            if prepare_chapter(vol_dir, ch_file, out, image_root,
                               args.force, chapter_dir):
                ch_count += 1
        sidebar = vol_dir / '_sidebar.md'
        fails, missing = check_volume(
            out / vol_dir.name,
            str(sidebar) if sidebar.exists() else None,
            chapter_files=chapter_files)
        for line in fails:
            print(f'FAIL {vol_dir.name}: {line}', file=sys.stderr)
            any_fail = True
        for line in missing:
            print(f'MISSING {vol_dir.name}: {line}', file=sys.stderr)

    print(f'Prepared: {vol_count} volume skeletons, {ch_count} chapters.')
    return 1 if any_fail else 0


if __name__ == '__main__':
    sys.exit(main())
