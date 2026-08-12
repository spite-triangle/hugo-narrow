# scripts/md2hugo.py
"""md-to-hugo 确定性转换脚本。仅使用 Python 标准库。"""
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# content/posts（repo 根，含 docs/ 输入卷）
REPO_ROOT = Path(__file__).resolve().parents[4]

# frontmatter 块：以 --- 开头、--- 结尾
_FM_RE = re.compile(r'^---\n(.*?)\n---\n?', re.S)
# 单行键值：key: value，值可带可选引号
_LINE_RE = re.compile(r'^(\w+):\s*(.+?)\s*$', re.M)

# 通用容器词：名字为这些词的文件夹不作为卷名，其 .md 上浮归属最近的非常用名祖先
GENERIC_CONTAINER = {
    'chapter', 'chapters', 'group', 'groups', 'notes',
    'content', 'markdown', 'files',
}


def is_excluded_md(p):
    """是否为非内容 .md（_sidebar.md / README.md）。"""
    return p.name.lower() in ('_sidebar.md', 'readme.md')


def write_file(path, content):
    """统一写文件：UTF-8 + LF，行尾统一换行符。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = content.replace('\r\n', '\n').replace('\r', '\n')
    if not text.endswith('\n'):
        text += '\n'
    path.write_text(text, encoding='utf-8', newline='\n')


def parse_sidebar(sidebar_path, volume_name):
    """解析 _sidebar.md，返回卷名与章节列表。"""
    text = Path(sidebar_path).read_text(encoding='utf-8')
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError('empty sidebar')
    m = re.match(r'^-\s*\*\*(.+?)\*\*$', lines[0])
    volume_title = m.group(1) if m else volume_name
    chapters = []
    weight = 0
    for line in lines[1:]:
        m = re.match(r'^-\s*\[(.+?)\]\((.+?)\)\s*$', line)
        if not m:
            continue
        link = m.group(2).replace('\\', '/')
        # Skip external URLs and README links
        if link.startswith(('http://', 'https://')) or re.search(r'README\.md$', link, re.IGNORECASE):
            continue
        parts = link.split('/')
        if len(parts) > 3:
            continue  # Skip deeply nested paths (e.g., multi-level external URLs)
            raise ValueError(f'nested chapter not supported: {link}')
        weight += 1
        chapters.append({
            'weight': weight,
            'sidebar_title': m.group(1),
            'chapter_path': link,
        })
    if not chapters:
        raise ValueError('no chapters found in sidebar')
    return {'volume_title': volume_title, 'chapters': chapters}


def discover_volumes(docs_dir, generic=None):
    """返回 {卷目录: [章节 .md 路径]}（每卷按文件名字母序）。

    卷 = 离每个内容 .md 最近的、名字非通用容器词的祖先文件夹。
    通用容器词文件夹（chapter/group/...）永不作为卷名，其 .md 上浮归属到
    最近的非常用名祖先。排除 _sidebar.md / README.md。
    """
    generic = set(GENERIC_CONTAINER if generic is None else generic)
    root = Path(docs_dir).resolve()
    volumes = {}
    for md in root.rglob('*.md'):
        if is_excluded_md(md):
            continue
        d = md.parent
        while d != root and d.name.lower() in generic:
            d = d.parent
        volumes.setdefault(d, []).append(md)
    for d in volumes:
        volumes[d].sort(key=lambda p: p.stem)
    return volumes


def alphabetical_weight(chapter_path, chapter_dir=None):
    """无 sidebar 时按文件名字母序分配章节 weight（从 1 起）。"""
    src = Path(chapter_path)
    folder = Path(chapter_dir) if chapter_dir else src.parent
    names = sorted(p.stem for p in folder.glob('*.md')
                   if not is_excluded_md(p))
    return names.index(src.stem) + 1


def mtime_date(path):
    """返回文件的 mtime 日期（YYYY-MM-DD）。"""
    ts = os.path.getmtime(path)
    return datetime.datetime.fromtimestamp(ts).date().isoformat()


def git_date(path):
    """返回 git 最后一次提交该文件的日期；非 git 仓库时回退到 mtime。"""
    try:
        out = subprocess.run(
            ['git', 'log', '-1', '--format=%cd', '--date=short', '--', str(path)],
            capture_output=True, text=True, timeout=10)
        line = out.stdout.strip()
        if re.match(r'^\d{4}-\d{2}-\d{2}$', line):
            return line
    except (subprocess.SubprocessError, OSError):
        pass
    return mtime_date(path)


def escape_yaml(s):
    """转义 YAML 双引号字符串中的 \\ 与 "。"""
    return s.replace('\\', '\\\\').replace('"', '\\"')


def _parse_list(value):
    """将 YAML 列表字符串解析为 Python list；空串或 [] 返回空列表。"""
    if not value or value == '[]':
        return []
    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1]
        return [v.strip().strip('"') for v in inner.split(',') if v.strip()]
    return []


def build_frontmatter(fields):
    """由字段字典构建 --- 包裹的 YAML frontmatter。"""
    lines = ['---']
    for k, v in fields.items():
        if isinstance(v, bool):
            lines.append(f'{k}: {str(v).lower()}')
        elif v is None or v == '':
            lines.append(f'{k}: ""')
        elif isinstance(v, int):
            lines.append(f'{k}: {v}')
        elif isinstance(v, list):
            items = ', '.join(f'"{escape_yaml(str(x))}"' for x in v)
            lines.append(f'{k}: [{items}]')
        else:
            lines.append(f'{k}: "{escape_yaml(str(v))}"')
    lines.append('---')
    return '\n'.join(lines)


def read_frontmatter_fields(path):
    """正则解析 frontmatter，返回键值字典；无 frontmatter 时返回 {}。"""
    path = Path(path)
    if not path.exists():
        return {}
    text = path.read_text(encoding='utf-8')
    m = _FM_RE.match(text)
    if not m:
        return {}
    result = {}
    for mm in _LINE_RE.finditer(m.group(1)):
        k, v = mm.group(1), mm.group(2)
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        result[k] = v
    return result


def split_first_h1(text):
    """拆分首个 `# 标题`：返回 (标题文本, 移除该 H1 后的正文)。

    仅移除文档中第一个 H1 行；无 H1 时返回 (None, 原文)。
    """
    lines = text.splitlines(keepends=True)
    title = None
    body = []
    removed = False
    for line in lines:
        if not removed:
            m = re.match(r'^#\s+(.+?)\s*$', line)
            if m:
                title = m.group(1).strip()
                removed = True
                continue
        body.append(line)
    if title is None:
        return None, text
    return title, ''.join(body)


def strip_image_size(text):
    """移除 Markdown 图片 alt 内的尺寸参数。

    形如 `![alt|c,40](path)`：删除 alt 中 `|` 到 `]` 前的尺寸部分，
    保留 alt 其余内容。仅作用于方括号内，不影响无尺寸参数的图片。
    """
    return re.sub(
        r'!\[([^\]]*?)\|[^\]]*\]',
        lambda m: f'![{m.group(1)}]',
        text)


_IMG_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
_VIDEO_RE = re.compile(r'<video\b[^>]*?\bsrc="([^"]+)"[^>]*>\s*</video>', re.S)


def _within(root, p):
    return p == root or root in p.parents


def resolve_resource(rel_path, base_dir, image_root, volume_name):
    """解析资源路径：依次尝试源章节目录、image/<卷>/<name>、image/<name>、项目内递归搜索。"""
    p = os.path.normpath(rel_path.replace('\\', '/'))
    name = Path(p).name
    candidates = [
        Path(base_dir) / p,
        Path(image_root) / volume_name / name,
        Path(image_root) / name,
    ]
    allowed = [Path(base_dir).resolve(), Path(image_root).resolve()]
    for c in candidates:
        try:
            rp = c.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if rp.is_file() and any(_within(a, rp) for a in allowed):
            return rp
    # 最终回退：在 image_root 下递归搜索同名文件
    image_root_p = Path(image_root)
    if image_root_p.is_dir():
        for f in image_root_p.rglob(name):
            try:
                rp = f.resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if rp.is_file() and _within(image_root_p.resolve(), rp):
                return rp
    return None


def process_resources(text, src_dir, out_res_dir, image_root, volume_name):
    """拷贝正文引用的资源并重写路径。返回 (新正文, 已拷贝列表, 未找到列表)。

    resources 目录仅在正文实际引用到可解析资源时才创建；无资源章节不留空目录。
    """
    out_res_dir = Path(out_res_dir)
    copied = []
    warnings = []
    pending = []

    def plan_copy(src, name):
        pending.append((src, name))

    def flush():
        if not pending:
            return
        out_res_dir.mkdir(parents=True, exist_ok=True)
        for src, name in pending:
            dst = out_res_dir / name
            if not (dst.exists() and dst.stat().st_size == src.stat().st_size):
                shutil.copy2(src, dst)
                copied.append(name)

    def img_repl(m):
        alt, target = m.group(1), m.group(2)
        if target.startswith(('http://', 'https://', '#')):
            return m.group(0)
        if target.startswith('./resources/'):
            return m.group(0)
        src = resolve_resource(target, src_dir, image_root, volume_name)
        if src is None:
            warnings.append(target)
            return f'{m.group(0)}\n<!-- WARNING: resource not found: {target} -->'
        plan_copy(src, src.name)
        return f'![{alt}](./resources/{src.name})'

    new_text = _IMG_RE.sub(img_repl, text)

    def video_repl(m):
        target = m.group(1)
        src = resolve_resource(target, src_dir, image_root, volume_name)
        if src is None:
            warnings.append(target)
            return f'{m.group(0)}\n<!-- WARNING: resource not found: {target} -->'
        plan_copy(src, src.name)
        return (f'<video src="./resources/{src.name}" controls="controls" '
                f'width="100%" height="100%"></video>')

    new_text = _VIDEO_RE.sub(video_repl, new_text)
    flush()
    return new_text, copied, warnings


def convert_term_blocks(text, prompt_re=None):
    """处理 ```term 代码块：剥离主机名提示符保留 $、\\/ → /、// → # 注释。

    非 term 块原样保留。
    """
    if prompt_re is None:
        prompt_re = r'^[\w.-]+@[\w.-]+:\S+?[$#>!%]\s*'
    re_prompt = re.compile(prompt_re)

    def fix_line(line):
        line = re_prompt.sub('$ ', line)
        line = line.replace('\\/', '/')
        line = re.sub(r'\s//(?=\s|$)', ' #', line)
        return line

    out = []
    in_term = False
    for line in text.splitlines():
        m = re.match(r'^```(\S*)', line)
        if m:
            if m.group(1) == 'term':
                in_term = True
                out.append('```term')
            else:
                in_term = False
                out.append(line)
            continue
        if in_term:
            if line.startswith('```'):
                in_term = False
                out.append(line)
            else:
                out.append(fix_line(line))
        else:
            out.append(line)
    return '\n'.join(out)


def convert_math_blocks(text):
    """将 $$...$$ 数学公式块转换为 ```math 代码块，便于 Hugo 渲染器处理。"""
    return re.sub(
        r'^\$\$\s*\n(.+?)\n\$\$\s*$',
        r'```math\n\1\n```',
        text, flags=re.M | re.S)


def convert_json_comments(text):
    """将 json 代码块中的 /* .. */ 块注释替换为 // 行注释。

    非 json 代码块原样保留；行内 $...$ 和 $$...$$ 数学公式不动。
    """
    lines = text.split('\n')
    out = []
    in_json = False
    i = 0
    while i < len(lines):
        line = lines[i]
        m_block = re.match(r'^```\s*(\S*)', line)
        if m_block:
            if m_block.group(1).lower() == 'json':
                in_json = not in_json
                out.append(line)
                i += 1
                continue
            # 非 json 代码块原样输出
            out.append(line)
            i += 1
            continue

        if in_json:
            # 遇到 ``` 结束（上面已处理，此处不进入）
            block = re.match(r'^\s*/\*', line) and '/*' not in line.strip()[:4]
            if re.match(r'.*\*/\s*$', line):
                # 单行内同时包含 /* ... */ ，跳过
                out.append(line)
            elif '/*' in line:
                # 收集注释起始行，找到匹配的 */
                start = i
                end = None
                depth = line.count('/*') - line.count('*/')
                for j in range(i + 1, len(lines)):
                    depth += lines[j].count('/*') - lines[j].count('*/')
                    if depth <= 0:
                        end = j
                        break
                if end is not None:
                    # 将整个注释范围替换为 // 前缀的单行注释
                    # 取起始行的缩进和非 /* 部分的文本作为注释内容
                    indent = ''
                    for k, ch in enumerate(line):
                        if ch != ' ':
                            break
                    indent = ' ' * k
                    prefix = f'{indent}// '
                    text_part = line.rstrip()
                    # 提取 */ 后的残留部分（如果有）
                    m_end = re.search(r'\*/\s*(.*)', line)
                    if m_end and m_end.group(1).strip():
                        out.append(f'{prefix}{m_end.group(1)}')
                    else:
                        out.append(f'{prefix}/* ... */')
                    i = end + 1
                    continue
                else:
                    # 未找到匹配的 */，原样输出
                    out.append(line)
            else:
                out.append(line)
        else:
            out.append(line)
        i += 1

    return '\n'.join(out)


def fix_numbered_list(text):
    """修正错误的数字序号列表：1., 2., 3.5., ... → 正确递增序列。"""
    lines = text.split('\n')
    out = []
    expected = 1
    in_ordered = False

    for line in lines:
        # 匹配有序列表项：以数字开头，后跟 . 和可选空格
        m = re.match(r'^(\s*)\d+\.\s+', line)
        if m and not line.strip().startswith('- '):
            indent = m.group(1)
            rest = re.sub(r'^\s*\d+\.\s+', '', line)
            # 跳过 H2/H3/H4，这些不应算作列表项（# Title）
            if re.match(r'^\s*#{1,6}\s', rest):
                in_ordered = False
                expected = 1
                out.append(line)
                continue
            if not in_ordered:
                expected = 1
                in_ordered = True
            elif expected > 1 and line.strip().startswith(('-', '*', '+')):
                # 列表项之间有无序列表打断，重置
                in_ordered = False
                out.append(line)
                continue
            else:
                if re.match(r'^\s*$', rest):
                    # 空行打断有序序列
                    if in_ordered and expected > 1:
                        pass  # 保持状态但不输出前缀
                    in_ordered = False
                    expected = 1
                    out.append(line)
                    continue

                line_out = f'{indent}{expected}. {rest}'
                out.append(line_out)
                if not re.match(r'^\s*$', line):
                    expected += 1
        else:
            # 非有序列表行（包括 - / * + 开头的无序列表、代码块等）
            if in_ordered and expected > 1 and re.match(r'^\s*[\-*+]\s', line):
                in_ordered = False
                expected = 1
            elif not line.strip():
                # 空行：如果当前是连续有序列表中则保留序列，否则重置
                pass
            out.append(line)

    return '\n'.join(out)


def convert_term_blocks(text, prompt_re=None):


def _find_weight(sidebar_info, chapter_path):
    """根据章节文件路径从 sidebar 信息中查找 weight 序号。不在 sidebar 中的返回 None。"""
    name = Path(chapter_path).name
    for ch in sidebar_info['chapters']:
        if Path(ch['chapter_path']).name == name:
            return ch['weight']
    return None


def extra_weight(sidebar_info, chapter_path):
    """为不在 sidebar 中的章节分配顺序权重：按同目录下非 sidebar 章节的字母序，接在最后一个 sidebar 权重之后。

    sidebar 可能遗漏章节（以实际 chapter/ 文件夹为准），必须为这些章节也分配唯一权重，
    否则会与 max+1 冲突、Hugo 排序错乱。
    """
    src = Path(chapter_path)
    in_sidebar = {Path(ch['chapter_path']).name for ch in sidebar_info['chapters']}
    extras = sorted(p.name for p in src.parent.glob('*.md') if p.name not in in_sidebar)
    base = max((ch['weight'] for ch in sidebar_info['chapters']), default=0)
    return base + extras.index(src.name) + 1


def cmd_prepare_chapter(args):
    """处理一章：建目录、拷贝资源、重写正文、生成 index.md。"""
    src = Path(args.chapter)
    sidebar_path = getattr(args, 'sidebar', None)
    if sidebar_path:
        try:
            sidebar = parse_sidebar(sidebar_path, args.volume_name)
        except ValueError:
            sidebar = None  # sidebar 无效/无章节时回退到字母序
        if sidebar is not None:
            weight = _find_weight(sidebar, src)
            if weight is None:
                weight = extra_weight(sidebar, src)
        else:
            weight = alphabetical_weight(src, getattr(args, 'chapter_dir', None))
    else:
        weight = alphabetical_weight(src, getattr(args, 'chapter_dir', None))
    text = src.read_text(encoding='utf-8')
    title, body = split_first_h1(text)
    title = title or src.stem
    date = git_date(src) if args.date_source == 'git' else mtime_date(src)
    body = strip_image_size(body)
    chapter_dir = Path(args.out) / args.volume_name / src.stem
    index_path = chapter_dir / 'index.md'
    existing_fields = read_frontmatter_fields(index_path)
    existing_desc = existing_fields.get('description', '')
    existing_tags = existing_fields.get('tags', '')
    existing_cats = existing_fields.get('categories', '')
    body, _copied, warnings = process_resources(
        body, src.parent, chapter_dir / 'resources',
        args.image_root, args.volume_name)
    body = convert_term_blocks(body, args.prompt_regex)
    body = convert_math_blocks(body)
    body = convert_json_comments(body)
    body = fix_numbered_list(body)
    front = build_frontmatter({
        'title': title, 'date': date, 'draft': False,
        'description': existing_desc, 'weight': weight,
        'tags': _parse_list(existing_tags),
        'categories': _parse_list(existing_cats),
    })
    write_file(index_path, front + '\n\n' + body)
    for w in warnings:
        print(f'WARNING: {w}', file=sys.stderr)


def cmd_prepare_volume(args):
    """生成卷级别的 _index.md 骨架（title + 卷概述占位）。"""
    sidebar_path = getattr(args, 'sidebar', None)
    title = args.volume_name
    if sidebar_path:
        try:
            title = parse_sidebar(sidebar_path, args.volume_name)['volume_title']
        except ValueError:
            pass  # sidebar 无效/无章节时回退到卷文件夹名
    out_dir = Path(args.out) / args.volume_name
    index_path = out_dir / '_index.md'
    existing_fields = read_frontmatter_fields(index_path)
    existing_desc = existing_fields.get('description', '')
    existing_tags = existing_fields.get('tags', '')
    existing_cats = existing_fields.get('categories', '')
    front = build_frontmatter({
        'title': title, 'description': existing_desc,
        'tags': _parse_list(existing_tags),
        'categories': _parse_list(existing_cats),
    })
    body = (f'{_OVERVIEW_START}\n'
            f'（卷内容简介待 subagent 生成）\n'
            f'{_OVERVIEW_END}')
    write_file(index_path, front + '\n\n' + body)


def cmd_fill_description(args):
    """填写 frontmatter 的 description / tags / categories 字段，空则写入并返回 True。"""
    path = Path(args.file)
    fields = read_frontmatter_fields(path)
    text = path.read_text(encoding='utf-8')
    changed = False

    # description
    desc = getattr(args, 'description', None)
    if desc and not fields.get('description', ''):
        new_line = f'description: "{escape_yaml(desc)}"'
        text = re.sub(r'^description:.*$', new_line, text, count=1, flags=re.M)
        changed = True

    # tags (comma-separated → YAML list)
    tags = getattr(args, 'tags', None)
    if tags and fields.get('tags', '') in ('', '[]'):
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]
        items = ', '.join(f'"{escape_yaml(t)}"' for t in tag_list)
        new_line = f'tags: [{items}]'
        text = re.sub(r'^tags:.*$', new_line, text, count=1, flags=re.M)
        changed = True

    # categories (comma-separated → YAML list)
    cats = getattr(args, 'categories', None)
    if cats and fields.get('categories', '') in ('', '[]'):
        cat_list = [c.strip() for c in cats.split(',') if c.strip()]
        items = ', '.join(f'"{escape_yaml(c)}"' for c in cat_list)
        new_line = f'categories: [{items}]'
        text = re.sub(r'^categories:.*$', new_line, text, count=1, flags=re.M)
        changed = True

    if changed:
        write_file(path, text)
    return changed


def _is_empty_field(v):
    """frontmatter 字段是否视为缺失：空串、""、[] 均算缺失。"""
    if v is None:
        return True
    v = v.strip()
    return not v.strip('"').strip() or v == '[]'


def missing_metadata(path):
    """返回缺失的元数据字段列表（description/tags/categories）。"""
    fields = read_frontmatter_fields(path)
    return [k for k in ('description', 'tags', 'categories')
            if _is_empty_field(fields.get(k, ''))]


_OVERVIEW_START = '<!-- VOLUME_OVERVIEW_START -->'
_OVERVIEW_END = '<!-- VOLUME_OVERVIEW_END -->'


def volume_overview_missing(path):
    """_index.md 卷简介是否缺失：无占位标记、标记间为空、或仍为待生成占位。"""
    text = Path(path).read_text(encoding='utf-8')
    m = re.search(re.escape(_OVERVIEW_START) + r'(.*?)' + re.escape(_OVERVIEW_END),
                  text, re.S)
    if not m:
        return True
    body = m.group(1).strip()
    return not body or '待 subagent 生成' in body


def check_volume(volume_dir, sidebar_path=None, chapter_dir=None,
                 chapter_files=None):
    """核对单卷输出：结构完整性、资源引用、元数据、卷简介。

    sidebar_path 为 None 时跳过 sidebar 章节 weight 顺序校验。
    chapter_files 提供源章节文件列表（优先于 chapter_dir 枚举）。
    返回 (fails, missing)：fails 为结构性问题，missing 为未生成的
    description/tags/categories 与卷简介，均为不带卷前缀的裸行。
    """
    volume = Path(volume_dir)
    fails = []
    missing = []

    # 1. 源章节 ↔ 输出子目录 双向核对
    src_stems = None
    if chapter_files is not None:
        src_stems = {Path(p).stem for p in chapter_files}
    elif chapter_dir:
        src_stems = {p.stem for p in Path(chapter_dir).glob('*.md')
                     if not is_excluded_md(p)}
    for stem in sorted(src_stems or ()):
        if not (volume / stem / 'index.md').exists():
            fails.append(f'missing index.md for chapter {stem}')
    out_indexes = {}
    for d in volume.iterdir():
        if not d.is_dir() or d.name.startswith('_'):
            continue
        idx = d / 'index.md'
        if idx.exists():
            out_indexes[d.name] = idx
    if src_stems is not None:
        for stem in sorted(out_indexes):
            if stem not in src_stems:
                fails.append(f'orphan chapter dir {stem} (not in source chapter folder)')

    # 2. 每章：资源引用 + 元数据 + 空 resources 目录
    for stem, index in sorted(out_indexes.items()):
        text = index.read_text(encoding='utf-8')
        for ref in re.findall(r'\./resources/([^\s)\"\'<>]+)', text):
            if not (volume / stem / 'resources' / ref).exists():
                fails.append(f'missing resource {ref} in {stem}')
        res_dir = volume / stem / 'resources'
        if res_dir.is_dir() and not any(res_dir.iterdir()):
            fails.append(f'empty resources dir in {stem}')
        for field in missing_metadata(index):
            missing.append(f'{stem} {field}')

    # 3. 卷 _index.md：存在性 + 元数据 + 简介
    idx = volume / '_index.md'
    if not idx.exists():
        fails.append('missing _index.md')
    else:
        for field in missing_metadata(idx):
            missing.append(f'_index.md {field}')
        if volume_overview_missing(idx):
            missing.append('_index.md overview')

    # 4. sidebar 章节 weight 顺序（仅在有 sidebar 时启用）
    if sidebar_path:
        try:
            sidebar = parse_sidebar(sidebar_path, volume.name)
        except ValueError as e:
            fails.append(f'sidebar parse error: {e}')
            sidebar = None
        if sidebar is not None:
            weights = []
            for ch in sidebar['chapters']:
                name = Path(ch['chapter_path']).stem
                idx = volume / name / 'index.md'
                if idx.exists():
                    weights.append((int(read_frontmatter_fields(idx).get('weight', 0)), name))
            expected = [(ch['weight'], Path(ch['chapter_path']).stem)
                        for ch in sidebar['chapters']]
            if weights != expected:
                fails.append(f'weight order mismatch {weights} != {expected}')

    return fails, missing


def cmd_verify(args):
    """校验输出卷：结构、资源引用、元数据、卷简介。"""
    fails, missing = check_volume(args.volume, getattr(args, 'sidebar', None),
                                  getattr(args, 'chapter_dir', None),
                                  getattr(args, 'chapter_files', None))
    for line in fails:
        print(f'FAIL: {line}', file=sys.stderr)
    for line in missing:
        print(f'MISSING: {line}', file=sys.stderr)
    if not fails and not missing:
        print('verify: OK')
    return not fails and not missing


def build_parser():
    p = argparse.ArgumentParser(prog='md2hugo')
    sub = p.add_subparsers(dest='command', required=True)
    sp = sub.add_parser('prepare-chapter')
    sp.add_argument('--sidebar', default=None,
                    help='_sidebar.md（可选，无则按文件名字母序分配 weight）')
    sp.add_argument('--chapter-dir', default=None,
                    help='卷的源章节目录（可选，无 sidebar 时用于全局字母序）')
    sp.add_argument('--chapter', required=True)
    sp.add_argument('--volume-name', required=True)
    sp.add_argument('--image-root', required=True)
    sp.add_argument('--out', required=True)
    sp.add_argument('--date-source', choices=['mtime', 'git'], default='mtime')
    sp.add_argument('--prompt-regex', default=None)
    sp.set_defaults(func=cmd_prepare_chapter)

    sp = sub.add_parser('prepare-volume')
    sp.add_argument('--sidebar', default=None,
                    help='_sidebar.md（可选，无则卷 title 取卷文件夹名）')
    sp.add_argument('--readme', default=None)
    sp.add_argument('--volume-name', required=True)
    sp.add_argument('--out', required=True)
    sp.set_defaults(func=cmd_prepare_volume)

    sp = sub.add_parser('fill-description')
    sp.add_argument('--file', required=True)
    sp.add_argument('--description', default=None)
    sp.add_argument('--tags', default=None)
    sp.add_argument('--categories', default=None)
    sp.set_defaults(func=cmd_fill_description)

    sp = sub.add_parser('verify')
    sp.add_argument('--volume', required=True)
    sp.add_argument('--sidebar', default=None,
                    help='_sidebar.md（可选，无则跳过 weight 顺序校验）')
    sp.add_argument('--chapter-dir', default=None)
    sp.add_argument('--chapter-files', nargs='*', default=None,
                    help='源章节文件列表（可选，优先于 --chapter-dir）')
    sp.set_defaults(func=cmd_verify)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    main(sys.argv[1:])
