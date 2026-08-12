# scripts/test_md2hugo.py
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import md2hugo

class TestCli(unittest.TestCase):
    def test_help_exits_zero(self):
        with self.assertRaises(SystemExit) as ctx:
            md2hugo.main(['--help'])
        self.assertEqual(ctx.exception.code, 0)

    def test_write_file_uses_lf(self):
        p = Path(__file__).resolve().parent / '_tmp_write_test.md'
        try:
            md2hugo.write_file(p, 'a\r\nb\n')
            data = p.read_bytes()
            self.assertNotIn(b'\r', data)
            self.assertEqual(data, b'a\nb\n')
        finally:
            p.unlink(missing_ok=True)

    def test_repo_root_points_to_content_posts(self):
        self.assertTrue((md2hugo.REPO_ROOT / 'docs' / 'compiler').exists())

    def _write_fixture_sidebar(self, d):
        (d / '_sidebar.md').write_text(
            '- **编译原理**\n'
            '- [目录](compiler/README.md)\n'
            '- [第一章 简介](compiler/chapter/introduction.md)\n'
            '- [第二章 cool](compiler/chapter/cool.md)\n',
            encoding='utf-8')
        return d / '_sidebar.md'

    def test_parse_sidebar(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            side = self._write_fixture_sidebar(Path(td))
            info = md2hugo.parse_sidebar(side, 'compiler')
            self.assertEqual(info['volume_title'], '编译原理')
            self.assertEqual(len(info['chapters']), 2)
            self.assertEqual(info['chapters'][0]['weight'], 1)
            self.assertEqual(info['chapters'][0]['sidebar_title'], '第一章 简介')
            self.assertEqual(info['chapters'][1]['weight'], 2)

    def test_parse_sidebar_rejects_nested(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / '_sidebar.md'
            p.write_text('- **v**\n- [x](v/a/b/c.md)\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                md2hugo.parse_sidebar(p, 'v')

    def test_mtime_date_format(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'f.md'
            p.write_text('x', encoding='utf-8')
            d = md2hugo.mtime_date(p)
            self.assertRegex(d, r'^\d{4}-\d{2}-\d{2}$')

    def test_build_frontmatter(self):
        fm = md2hugo.build_frontmatter({
            'title': '简介', 'date': '2025-08-09', 'draft': False,
            'description': '', 'weight': 1, 'tags': [], 'categories': []})
        self.assertIn('title: "简介"', fm)
        self.assertIn('description: ""', fm)
        self.assertIn('draft: false', fm)
        self.assertIn('weight: 1', fm)
        self.assertIn('tags: []', fm)
        self.assertIn('categories: []', fm)
        self.assertTrue(fm.startswith('---\n') and fm.endswith('---'))

    def test_escape_yaml(self):
        self.assertEqual(md2hugo.escape_yaml('a"b\\c'), 'a\\"b\\\\c')

    def test_fill_description_writes_and_skips(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'index.md'
            md2hugo.write_file(p, md2hugo.build_frontmatter(
                {'title': 't', 'date': '2025-01-01', 'draft': False,
                 'description': '', 'weight': 1}) + '\nbody')
            import argparse
            args = argparse.Namespace(file=str(p), description='一行描述')
            self.assertTrue(md2hugo.cmd_fill_description(args))
            self.assertIn('description: "一行描述"',
                          Path(p).read_text(encoding='utf-8'))
            # 已有非空 description 时跳过
            args2 = argparse.Namespace(file=str(p), description='另一行')
            self.assertFalse(md2hugo.cmd_fill_description(args2))

    def test_split_first_h1(self):
        text = '# 简介\n\n# 编译器\n\n正文\n'
        title, body = md2hugo.split_first_h1(text)
        self.assertEqual(title, '简介')
        self.assertNotIn('# 简介', body)
        self.assertIn('# 编译器', body)

    def test_split_first_h1_no_h1(self):
        title, body = md2hugo.split_first_h1('普通正文\n')
        self.assertIsNone(title)
        self.assertEqual(body, '普通正文\n')

    def test_strip_image_size(self):
        text = '![alt|c,40](../../image/compiler/p.png) 保留 ![alt](x.png)'
        out = md2hugo.strip_image_size(text)
        self.assertEqual(out, '![alt](../../image/compiler/p.png) 保留 ![alt](x.png)')

    def test_convert_term_blocks(self):
        text = ('```term\n'
                'triangle@LEARN:~$ dotnet tool install --global \\/v\\/pk  // 安装到默认路径\n'
                'triangle@LEARN:~$ ls\n'
                'file1 file2\n'
                '```\n'
                '\n'
                '```cool\nclass Main {}\n```\n')
        out = md2hugo.convert_term_blocks(text)
        self.assertIn('```term', out)
        self.assertIn('$ dotnet tool install --global /v/pk  # 安装到默认路径', out)
        self.assertIn('$ ls\nfile1 file2', out)
        self.assertNotIn('triangle@LEARN', out)
        self.assertIn('```cool\nclass Main {}\n```', out)

    def test_convert_term_preserves_https_comment(self):
        text = '```term\nuser@host:~$ curl https://example.com/a  // 下载\n```\n'
        out = md2hugo.convert_term_blocks(text)
        self.assertIn('$ curl https://example.com/a  # 下载', out)

    def test_resolve_resource(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img = root / 'image' / 'compiler'
            img.mkdir(parents=True)
            (img / 'a.png').write_bytes(b'x')
            found = md2hugo.resolve_resource(
                '../../image/compiler/a.png', root / 'compiler' / 'chapter',
                root / 'image', 'compiler')
            self.assertEqual(found, img / 'a.png')
            missing = md2hugo.resolve_resource(
                'nope.png', root / 'compiler' / 'chapter',
                root / 'image', 'compiler')
            self.assertIsNone(missing)

    def test_process_resources_copies_and_rewrites(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img = root / 'image' / 'compiler'
            img.mkdir(parents=True)
            (img / 'pic.png').write_bytes(b'pngdata')
            (img / 'v.mp4').write_bytes(b'mp4data')
            src_dir = root / 'compiler' / 'chapter'
            src_dir.mkdir(parents=True)
            text = ('![a](../../image/compiler/pic.png)\n'
                    '<video src="../../image/compiler/v.mp4" controls></video>\n'
                    '![missing](../../image/compiler/nope.png)\n')
            out_res = root / 'out' / 'res'
            new_text, copied, warnings = md2hugo.process_resources(
                text, src_dir, out_res, root / 'image', 'compiler')
            self.assertEqual(set(copied), {'pic.png', 'v.mp4'})
            self.assertEqual(warnings, ['../../image/compiler/nope.png'])
            self.assertIn('![a](./resources/pic.png)', new_text)
            self.assertIn('<video src="./resources/v.mp4"', new_text)
            self.assertIn('WARNING: resource not found', new_text)
            self.assertTrue((out_res / 'pic.png').exists())
            self.assertTrue((out_res / 'v.mp4').exists())

    def test_process_resources_video_html_tag(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img = root / 'image' / 'compiler'
            img.mkdir(parents=True)
            (img / 'v.mp4').write_bytes(b'm')
            text = '<video src="../../image/compiler/v.mp4" controls></video>\n'
            out_res = root / 'out' / 'res'
            new_text, _, _ = md2hugo.process_resources(
                text, root / 'compiler' / 'chapter', out_res,
                root / 'image', 'compiler')
            self.assertIn('<video src="./resources/v.mp4"', new_text)

    def test_process_resources_no_resources_no_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src_dir = root / 'compiler' / 'chapter'
            src_dir.mkdir(parents=True)
            text = '# 标题\n\n纯文本，无任何资源引用。\n'
            out_res = root / 'out' / 'compiler' / 'introduction' / 'resources'
            new_text, copied, warnings = md2hugo.process_resources(
                text, src_dir, out_res, root / 'image', 'compiler')
            self.assertEqual(copied, [])
            self.assertEqual(warnings, [])
            self.assertFalse(out_res.exists())

    def test_process_resources_only_missing_no_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src_dir = root / 'compiler' / 'chapter'
            src_dir.mkdir(parents=True)
            text = '![x](../../image/compiler/nope.png)\n'
            out_res = root / 'out' / 'res'
            new_text, copied, warnings = md2hugo.process_resources(
                text, src_dir, out_res, root / 'image', 'compiler')
            self.assertEqual(copied, [])
            self.assertEqual(warnings, ['../../image/compiler/nope.png'])
            self.assertFalse(out_res.exists())

    def _fill_metadata(self, path, desc, tags, cats):
        import argparse
        md2hugo.cmd_fill_description(argparse.Namespace(
            file=str(path), description=desc, tags=tags, categories=cats))

    def _fill_overview(self, path, text):
        content = Path(path).read_text(encoding='utf-8')
        content = content.replace('（卷内容简介待 subagent 生成）', text)
        md2hugo.write_file(path, content)

    def _make_fixture_volume(self, root, name='compiler'):
        vol = root / name
        chapter = vol / 'chapter'
        chapter.mkdir(parents=True)
        (vol / 'README.md').write_text('# 编译原理\n\n一些说明\n', encoding='utf-8')
        (vol / '_sidebar.md').write_text(
            f'- **编译原理**\n- [目录]({name}/README.md)\n'
            f'- [第一章 简介]({name}/chapter/introduction.md)\n', encoding='utf-8')
        (chapter / 'introduction.md').write_text(
            '# 简介\n\n# 编译器\n\n这是正文。\n\n'
            '![a|c,40](../../image/compiler/parse.png)\n\n'
            '```term\nuser@host:~$ echo hi // 注释\n```\n',
            encoding='utf-8')
        img = root / 'image' / name
        img.mkdir(parents=True)
        (img / 'parse.png').write_bytes(b'png')
        return vol

    def test_prepare_chapter(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = self._make_fixture_volume(root)
            out = root / 'out'
            args = argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'),
                chapter=str(vol / 'chapter' / 'introduction.md'),
                volume_name='compiler', image_root=str(root / 'image'),
                out=str(out), date_source='mtime',
                prompt_regex=None)
            md2hugo.cmd_prepare_chapter(args)
            index = out / 'compiler' / 'introduction' / 'index.md'
            self.assertTrue(index.exists())
            text = index.read_text(encoding='utf-8')
            self.assertIn('title: "简介"', text)
            self.assertIn('weight: 1', text)
            self.assertIn('description: ""', text)
            self.assertIn('这是正文', text)
            self.assertIn('![a](./resources/parse.png)', text)
            self.assertIn('```term', text)
            self.assertNotIn('|c,40', text)
            self.assertTrue((out / 'compiler' / 'introduction' /
                             'resources' / 'parse.png').exists())

    def test_prepare_chapter_no_resources_skips_dir(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = root / 'compiler'
            chapter = vol / 'chapter'
            chapter.mkdir(parents=True)
            (vol / '_sidebar.md').write_text(
                '- **编译原理**\n- [简介](compiler/chapter/introduction.md)\n',
                encoding='utf-8')
            (chapter / 'introduction.md').write_text(
                '# 简介\n\n只有文本，无图片无视频。\n', encoding='utf-8')
            out = root / 'out'
            args = argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'),
                chapter=str(chapter / 'introduction.md'),
                volume_name='compiler', image_root=str(root / 'image'),
                out=str(out), date_source='mtime', prompt_regex=None)
            md2hugo.cmd_prepare_chapter(args)
            self.assertTrue(
                (out / 'compiler' / 'introduction' / 'index.md').exists())
            self.assertFalse(
                (out / 'compiler' / 'introduction' / 'resources').exists())

    def test_prepare_chapter_keeps_description(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = self._make_fixture_volume(root)
            out = root / 'out'
            ck = argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'),
                chapter=str(vol / 'chapter' / 'introduction.md'),
                volume_name='compiler', image_root=str(root / 'image'),
                out=str(out), date_source='mtime',
                prompt_regex=None)
            md2hugo.cmd_prepare_chapter(ck)
            index = out / 'compiler' / 'introduction' / 'index.md'
            md2hugo.cmd_fill_description(
                argparse.Namespace(file=str(index), description='已填描述'))
            md2hugo.cmd_prepare_chapter(ck)
            self.assertIn('description: "已填描述"',
                          index.read_text(encoding='utf-8'))

    def test_prepare_volume(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = self._make_fixture_volume(root)
            out = root / 'out'
            args = argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'), readme=str(vol / 'README.md'),
                volume_name='compiler', out=str(out))
            md2hugo.cmd_prepare_volume(args)
            index = out / 'compiler' / '_index.md'
            text = index.read_text(encoding='utf-8')
            self.assertIn('title: "编译原理"', text)
            self.assertIn('description: ""', text)
            self.assertIn('<!-- VOLUME_OVERVIEW_START -->', text)
            self.assertIn('<!-- VOLUME_OVERVIEW_END -->', text)

    def test_verify_ok_and_fail(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = self._make_fixture_volume(root)
            out = root / 'out'
            ck = argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'),
                chapter=str(vol / 'chapter' / 'introduction.md'),
                volume_name='compiler', image_root=str(root / 'image'),
                out=str(out), date_source='mtime',
                prompt_regex=None)
            md2hugo.cmd_prepare_chapter(ck)
            md2hugo.cmd_prepare_volume(argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'), readme=str(vol / 'README.md'),
                volume_name='compiler', out=str(out)))
            # 补齐元数据与卷简介，否则 verify 会报 MISSING
            self._fill_metadata(out / 'compiler' / 'introduction' / 'index.md',
                                '第一章简介', '编译器', '编译原理')
            self._fill_metadata(out / 'compiler' / '_index.md',
                                '编译原理卷', '编译器', '编译原理')
            self._fill_overview(out / 'compiler' / '_index.md', '本卷介绍编译原理。')
            vk = argparse.Namespace(
                volume=str(out / 'compiler'), sidebar=str(vol / '_sidebar.md'),
                chapter_dir=str(vol / 'chapter'))
            self.assertTrue(md2hugo.cmd_verify(vk))
            # 破坏引用：删除 resources 文件
            (out / 'compiler' / 'introduction' / 'resources' /
             'parse.png').unlink()
            self.assertFalse(md2hugo.cmd_verify(vk))

    def test_verify_reports_empty_resources_dir(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = root / 'compiler'
            chapter = vol / 'chapter'
            chapter.mkdir(parents=True)
            (vol / '_sidebar.md').write_text(
                '- **编译原理**\n- [简介](compiler/chapter/introduction.md)\n',
                encoding='utf-8')
            (chapter / 'introduction.md').write_text(
                '# 简介\n\n纯文本，无资源。\n', encoding='utf-8')
            out = root / 'out'
            ck = argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'),
                chapter=str(chapter / 'introduction.md'),
                volume_name='compiler', image_root=str(root / 'image'),
                out=str(out), date_source='mtime', prompt_regex=None)
            md2hugo.cmd_prepare_chapter(ck)
            md2hugo.cmd_prepare_volume(argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'), readme=None,
                volume_name='compiler', out=str(out)))
            self._fill_metadata(out / 'compiler' / 'introduction' / 'index.md',
                                '第一章简介', '编译器', '编译原理')
            self._fill_metadata(out / 'compiler' / '_index.md',
                                '编译原理卷', '编译器', '编译原理')
            self._fill_overview(out / 'compiler' / '_index.md',
                                '本卷介绍编译原理。')
            vk = argparse.Namespace(
                volume=str(out / 'compiler'), sidebar=str(vol / '_sidebar.md'),
                chapter_dir=str(chapter))
            # 正常生成：无 resources 目录，verify OK
            self.assertTrue(md2hugo.cmd_verify(vk))
            # 人为制造历史遗留空目录，verify FAIL
            res = out / 'compiler' / 'introduction' / 'resources'
            res.mkdir(parents=True)
            self.assertFalse(md2hugo.cmd_verify(vk))

    def test_idempotent_rerun(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = self._make_fixture_volume(root)
            snapshots = []
            for run in range(2):
                out = root / f'out{run}'
                ck = argparse.Namespace(
                    sidebar=str(vol / '_sidebar.md'),
                    chapter=str(vol / 'chapter' / 'introduction.md'),
                    volume_name='compiler', image_root=str(root / 'image'),
                    out=str(out), date_source='mtime',
                    prompt_regex=None)
                md2hugo.cmd_prepare_chapter(ck)
                md2hugo.cmd_prepare_volume(
                    argparse.Namespace(
                        sidebar=str(vol / '_sidebar.md'),
                        readme=str(vol / 'README.md'),
                        volume_name='compiler', out=str(out)))
                index = out / 'compiler' / 'introduction' / 'index.md'
                md2hugo.cmd_fill_description(
                    argparse.Namespace(file=str(index), description='稳定描述'))
                snapshots.append(
                    {p.relative_to(out): p.read_bytes()
                     for p in out.rglob('*') if p.is_file()})
            self.assertEqual(snapshots[0], snapshots[1])

    def test_compiler_volume_end_to_end(self):
        import tempfile
        import argparse
        vol = md2hugo.REPO_ROOT / 'docs' / 'compiler'
        self.assertTrue((vol / 'chapter').is_dir())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'out'
            md2hugo.cmd_prepare_volume(argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'), readme=str(vol / 'README.md'),
                volume_name='compiler', out=str(out)))
            chapters = sorted(
                (vol / 'chapter').glob('*.md'))
            self.assertGreaterEqual(len(chapters), 10)
            for ch in chapters:
                ck = argparse.Namespace(
                    sidebar=str(vol / '_sidebar.md'), chapter=str(ch),
                    volume_name='compiler',
                    image_root=str(md2hugo.REPO_ROOT / 'docs' / 'image'),
                    out=str(out), date_source='mtime',
                    prompt_regex=None)
                md2hugo.cmd_prepare_chapter(ck)
            # 补齐每章元数据与卷简介，使 verify 通过
            for ch in chapters:
                self._fill_metadata(
                    out / 'compiler' / ch.stem / 'index.md',
                    f'{ch.stem} 章节简介', '编译器', '编译原理')
            self._fill_metadata(out / 'compiler' / '_index.md',
                                '编译原理卷', '编译器', '编译原理')
            self._fill_overview(out / 'compiler' / '_index.md',
                                '本卷介绍编译原理。')
            vk = argparse.Namespace(
                volume=str(out / 'compiler'), sidebar=str(vol / '_sidebar.md'),
                chapter_dir=str(vol / 'chapter'))
            self.assertTrue(md2hugo.cmd_verify(vk))
            # 抽查：weight 覆盖 1..n 且连续
            weights = sorted(
                int(md2hugo.read_frontmatter_fields(
                    p).get('weight', -1))
                for p in (out / 'compiler').glob('*/index.md'))
            self.assertEqual(weights, list(range(1, len(weights) + 1)))

    def test_build_frontmatter_with_tags(self):
        fm = md2hugo.build_frontmatter({
            'title': 't', 'date': '2025-01-01', 'draft': False,
            'description': '', 'weight': 1,
            'tags': ['编译器', '词法分析'],
            'categories': ['编译原理']})
        self.assertIn('tags: ["编译器", "词法分析"]', fm)
        self.assertIn('categories: ["编译原理"]', fm)

    def test_fill_tags_and_categories(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'index.md'
            md2hugo.write_file(p, md2hugo.build_frontmatter({
                'title': 't', 'date': '2025-01-01', 'draft': False,
                'description': '', 'weight': 1,
                'tags': [], 'categories': []}) + '\nbody')
            import argparse
            args = argparse.Namespace(
                file=str(p), description='文章描述',
                tags='编译器, 词法分析', categories='编译原理')
            self.assertTrue(md2hugo.cmd_fill_description(args))
            content = Path(p).read_text(encoding='utf-8')
            self.assertIn('description: "文章描述"', content)
            self.assertIn('tags: ["编译器", "词法分析"]', content)
            self.assertIn('categories: ["编译原理"]', content)

    def test_fill_tags_skips_when_set(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'index.md'
            md2hugo.write_file(p, md2hugo.build_frontmatter({
                'title': 't', 'date': '2025-01-01', 'draft': False,
                'description': '已有', 'weight': 1,
                'tags': ['已有标签'], 'categories': ['已有分类']}) + '\nbody')
            import argparse
            args = argparse.Namespace(
                file=str(p), description='新描述',
                tags='新标签', categories='新分类')
            self.assertFalse(md2hugo.cmd_fill_description(args))

    def test_convert_math_blocks(self):
        text = ('普通文字\n\n'
                '$$\n'
                '\\text{op}(e_1,\\dotsm, e_n)\n'
                '$$\n\n'
                '继续文字\n')
        out = md2hugo.convert_math_blocks(text)
        self.assertIn('```math', out)
        self.assertIn('\\text{op}(e_1,\\dotsm, e_n)', out)
        self.assertNotIn('$$', out)

    def test_convert_math_blocks_keeps_inline(self):
        # 行内 $...$ 不转换
        text = '这是一个 $E=mc^2$ 公式\n'
        out = md2hugo.convert_math_blocks(text)
        self.assertIn('$E=mc^2$', out)

    def test_convert_term_other_prompt(self):
        # 非 $ 提示符（root #、zsh %、etc.）
        text = '```term\nroot@server:/# apt install gcc  // 安装编译器\n```\n'
        out = md2hugo.convert_term_blocks(text)
        self.assertIn('$ apt install gcc  # 安装编译器', out)
        self.assertNotIn('root@server', out)

    def test_missing_metadata_empty_and_filled(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'index.md'
            md2hugo.write_file(p, md2hugo.build_frontmatter({
                'title': 't', 'date': '2025-01-01', 'draft': False,
                'description': '', 'weight': 1,
                'tags': [], 'categories': []}) + '\nbody')
            self.assertEqual(set(md2hugo.missing_metadata(p)),
                             {'description', 'tags', 'categories'})
            self._fill_metadata(p, '一行描述', 'a, b', 'c')
            self.assertEqual(md2hugo.missing_metadata(p), [])

    def test_volume_overview_missing_placeholder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / '_index.md'
            # 无占位标记
            md2hugo.write_file(p, '---\ntitle: "v"\n---\n\n正文\n')
            self.assertTrue(md2hugo.volume_overview_missing(p))
            # 仍是待生成占位
            md2hugo.write_file(p,
                '---\ntitle: "v"\n---\n\n'
                '<!-- VOLUME_OVERVIEW_START -->\n'
                '（卷内容简介待 subagent 生成）\n'
                '<!-- VOLUME_OVERVIEW_END -->\n')
            self.assertTrue(md2hugo.volume_overview_missing(p))
            # 已填充
            md2hugo.write_file(p,
                '---\ntitle: "v"\n---\n\n'
                '<!-- VOLUME_OVERVIEW_START -->\n'
                '本卷介绍编译原理。\n'
                '<!-- VOLUME_OVERVIEW_END -->\n')
            self.assertFalse(md2hugo.volume_overview_missing(p))

    def test_verify_reports_missing_metadata(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = self._make_fixture_volume(root)
            out = root / 'out'
            ck = argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'),
                chapter=str(vol / 'chapter' / 'introduction.md'),
                volume_name='compiler', image_root=str(root / 'image'),
                out=str(out), date_source='mtime', prompt_regex=None)
            md2hugo.cmd_prepare_chapter(ck)
            md2hugo.cmd_prepare_volume(argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'), readme=str(vol / 'README.md'),
                volume_name='compiler', out=str(out)))
            fails, missing = md2hugo.check_volume(
                out / 'compiler', vol / '_sidebar.md', vol / 'chapter')
            self.assertEqual(fails, [])
            for line in ('introduction description', 'introduction tags',
                         'introduction categories', '_index.md description',
                         '_index.md overview'):
                self.assertIn(line, missing)
            self.assertFalse(md2hugo.cmd_verify(
                argparse.Namespace(volume=str(out / 'compiler'),
                                   sidebar=str(vol / '_sidebar.md'),
                                   chapter_dir=str(vol / 'chapter'))))

    def test_verify_cross_check_chapter_dir(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = self._make_fixture_volume(root)
            out = root / 'out'
            ck = argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'),
                chapter=str(vol / 'chapter' / 'introduction.md'),
                volume_name='compiler', image_root=str(root / 'image'),
                out=str(out), date_source='mtime', prompt_regex=None)
            md2hugo.cmd_prepare_chapter(ck)
            # 造一个源中不存在的孤儿输出目录
            ghost = out / 'compiler' / 'ghost' / 'index.md'
            ghost.parent.mkdir(parents=True)
            md2hugo.write_file(ghost, md2hugo.build_frontmatter({
                'title': 'g', 'date': '2025-01-01', 'draft': False,
                'weight': 99}))
            fails, _ = md2hugo.check_volume(
                out / 'compiler', vol / '_sidebar.md', vol / 'chapter')
            self.assertTrue(
                any('orphan chapter dir ghost' in f for f in fails), fails)

    def test_verify_detects_ungenerated_source_chapter(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = self._make_fixture_volume(root)
            # 源中新增章节但未 prepare
            (vol / 'chapter' / 'extra.md').write_text(
                '# 额外\n\n正文\n', encoding='utf-8')
            out = root / 'out'
            ck = argparse.Namespace(
                sidebar=str(vol / '_sidebar.md'),
                chapter=str(vol / 'chapter' / 'introduction.md'),
                volume_name='compiler', image_root=str(root / 'image'),
                out=str(out), date_source='mtime', prompt_regex=None)
            md2hugo.cmd_prepare_chapter(ck)
            fails, _ = md2hugo.check_volume(
                out / 'compiler', vol / '_sidebar.md', vol / 'chapter')
            self.assertTrue(
                any('missing index.md for chapter extra' in f for f in fails),
                fails)

    def test_extra_weight_sequential(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = self._make_fixture_volume(root)
            # 两个不在 sidebar 中的章节：按字母序接在最后
            (vol / 'chapter' / 'zeta.md').write_text(
                '# Z\n\n正文\n', encoding='utf-8')
            (vol / 'chapter' / 'alpha.md').write_text(
                '# A\n\n正文\n', encoding='utf-8')
            out = root / 'out'
            for name in ('zeta', 'alpha'):
                ck = argparse.Namespace(
                    sidebar=str(vol / '_sidebar.md'),
                    chapter=str(vol / 'chapter' / f'{name}.md'),
                    volume_name='compiler', image_root=str(root / 'image'),
                    out=str(out), date_source='mtime', prompt_regex=None)
                md2hugo.cmd_prepare_chapter(ck)
            for name, expected in (('alpha', 2), ('zeta', 3)):
                fields = md2hugo.read_frontmatter_fields(
                    out / 'compiler' / name / 'index.md')
                self.assertEqual(int(fields['weight']), expected)

    def test_batch_prepare_importable(self):
        import batch_prepare
        root = batch_prepare.find_repo_root(Path(__file__).resolve().parent)
        self.assertIsNotNone(root)
        self.assertTrue((root / 'docs' / 'compiler').is_dir())
        # 无模块级副作用：发现卷目录正常（返回 {卷目录: [章节 .md]}）
        docs = root / 'docs'
        volumes = batch_prepare.discover_volumes(docs)
        names = [d.name for d in volumes]
        self.assertIn('compiler', names)
        self.assertTrue(volumes[root / 'docs' / 'compiler'])

    def test_discover_volumes_generic_absorb(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # compiler/chapter/*.md 与 compiler 直接 md → 卷 compiler
            ch = root / 'compiler' / 'chapter'
            ch.mkdir(parents=True)
            (ch / 'zeta.md').write_text('# Z\n', encoding='utf-8')
            (ch / 'alpha.md').write_text('# A\n', encoding='utf-8')
            (root / 'compiler' / 'direct.md').write_text('# D\n', encoding='utf-8')
            # compiler/notes/b.md：notes 是通用词 → 仍归 compiler
            notes = root / 'compiler' / 'notes'
            notes.mkdir()
            (notes / 'b.md').write_text('# B\n', encoding='utf-8')
            # group 是通用词 → 上浮到根（作为根卷）
            grp = root / 'group'
            grp.mkdir()
            (grp / 'c.md').write_text('# C\n', encoding='utf-8')
            # _sidebar.md / README.md 不计入章节
            (root / 'compiler' / '_sidebar.md').write_text('- **x**\n', encoding='utf-8')
            (root / 'compiler' / 'README.md').write_text('# R\n', encoding='utf-8')

            volumes = md2hugo.discover_volumes(root)
            comp = volumes.get((root / 'compiler').resolve())
            self.assertIsNotNone(comp)
            self.assertEqual([p.stem for p in comp],
                             ['alpha', 'b', 'direct', 'zeta'])
            # group 上浮：根目录成为卷，含 c
            self.assertIn((root / 'group' / 'c.md').resolve(),
                          volumes[root.resolve()])

    def test_prepare_chapter_no_sidebar_alpha(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = root / 'compiler'
            ch = vol / 'chapter'
            ch.mkdir(parents=True)
            (ch / 'zeta.md').write_text('# Z\n\n正文\n', encoding='utf-8')
            (ch / 'alpha.md').write_text('# A\n\n正文\n', encoding='utf-8')
            out = root / 'out'
            for name in ('zeta', 'alpha'):
                md2hugo.cmd_prepare_chapter(argparse.Namespace(
                    sidebar=None, chapter=str(ch / f'{name}.md'),
                    volume_name='compiler', image_root=str(root / 'image'),
                    out=str(out), date_source='mtime',
                    prompt_regex=None, chapter_dir=str(ch)))
            for name, expected in (('alpha', 1), ('zeta', 2)):
                fields = md2hugo.read_frontmatter_fields(
                    out / 'compiler' / name / 'index.md')
                self.assertEqual(int(fields['weight']), expected)

    def test_prepare_volume_no_sidebar_title_folder(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = root / 'compiler'
            ch = vol / 'chapter'
            ch.mkdir(parents=True)
            (ch / 'a.md').write_text('# A\n', encoding='utf-8')
            out = root / 'out'
            md2hugo.cmd_prepare_volume(argparse.Namespace(
                sidebar=None, readme=None,
                volume_name='compiler', out=str(out)))
            index = out / 'compiler' / '_index.md'
            text = index.read_text(encoding='utf-8')
            self.assertIn('title: "compiler"', text)
            self.assertIn('<!-- VOLUME_OVERVIEW_START -->', text)

    def test_verify_no_sidebar_ok(self):
        import tempfile
        import argparse
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vol = root / 'compiler'
            ch = vol / 'chapter'
            ch.mkdir(parents=True)
            (ch / 'a.md').write_text(
                '# A\n\n正文。\n\n![p](../../image/compiler/p.png)\n',
                encoding='utf-8')
            img = root / 'image' / 'compiler'
            img.mkdir(parents=True)
            (img / 'p.png').write_bytes(b'png')
            out = root / 'out'
            ck = argparse.Namespace(
                sidebar=None, chapter=str(ch / 'a.md'),
                volume_name='compiler', image_root=str(root / 'image'),
                out=str(out), date_source='mtime',
                prompt_regex=None, chapter_dir=str(ch))
            md2hugo.cmd_prepare_chapter(ck)
            md2hugo.cmd_prepare_volume(argparse.Namespace(
                sidebar=None, readme=None,
                volume_name='compiler', out=str(out)))
            self._fill_metadata(out / 'compiler' / 'a' / 'index.md',
                                'A 章简介', 't', 'c')
            self._fill_metadata(out / 'compiler' / '_index.md',
                                'compiler 卷', 't', 'c')
            self._fill_overview(out / 'compiler' / '_index.md', '简介。')
            vk = argparse.Namespace(
                volume=str(out / 'compiler'), sidebar=None,
                chapter_dir=None, chapter_files=[str(ch / 'a.md')])
            self.assertTrue(md2hugo.cmd_verify(vk))


if __name__ == '__main__':
    unittest.main()
