# 转换规则详情

## 卷发现（discover_volumes）

- **卷 = 按文件夹分组 markdown**：某文件夹直接（或经通用容器词子文件夹）包含内容 markdown，即为卷。`_sidebar.md`、`README.md` 不计入内容 markdown。
- **通用容器词不作为卷名**：文件夹名属于默认名单 `{chapter, chapters, group, groups, notes, content, markdown, files}` 时，其内容 markdown 上浮归属最近的非常用名祖先卷。名单可通过 `--generic` 覆盖。
- 卷名 = 卷文件夹原始名称（英文原文）。章节 = 该卷名下的内容 `.md` 文件，文件名去扩展名即章节文件夹名。

## 元数据

| 字段 | 来源 |
|---|---|
| 卷 title | 有 `_sidebar.md`：首行 `- **编译原理**`（去 `**`，仅作展示用中文名）；无：卷文件夹名 |
| 输出卷文件夹名 | 源卷文件夹名（英文原文），如 `compiler`、`http`。**不翻译、不中文化。** |
| 章节 title | 正文第一个 `# H1`；无 H1 用文件名 |
| 章节 date | 源文件 mtime（默认）或 git 提交日期 |
| 章节 weight | 有 sidebar：按 sidebar 链接顺序，第一章=1；README 目录条目不计数；不在 sidebar 中的章节（以实际发现为准）按文件名字母序接在最后一个 sidebar 权重之后（max+1 依次）。无 sidebar：按文件名字母序从 1 起 |
| 章节文件夹名 | 章节 md 文件名（去扩展名，英文原文） |
| 章节 description | subagent 从正文概括一行（10-40 字）；fill-description 写入，幂等（非空跳过） |
| 章节 tags | subagent 从正文提取 1-3 个关键词，逗号分隔传 `--tags`；fill-description 写入为 `["k1", "k2"]` |
| 章节 categories | subagent 归纳 1-2 个大类，逗号分隔传 `--categories`；fill-description 写入为 `["c1", "c2"]` |

## 正文重写

- 移除第一个 `# H1`（已用作 title）。
- 图片：`![alt|c,40](path)` → `![alt](./resources/<basename>)`，`|c,40` 等 alt 内尺寸参数移除。
- 视频：`<video src="path"></video>` → 拷贝到 `./resources/`，保留 `<video>` 标签，`src` 重写为 `./resources/<basename>`。
- term 代码块：
  - 语言标记保持 `term`。
  - 提示符精简：`user@host:path$ ` → `$ `。
  - `\/` → `/`（仅此转义；Windows 路径 `%USERPROFILE%\.dotnet\tools` 保留反斜杠）。
  - 行内 `// 注释` → `# 注释`（`\s//(?=\s|$)`，不误伤 `https://`）。
- `$$...$$` 数学公式块 → ` ```math ... ``` `（仅块级公式，行内 `$...$` 原样保留）。
- JSON 代码块中的注释：将 `/* .. */` 块注释替换为 `//` 行注释。先以语言标记识别 `json` 代码块（不处理 inline JSON），在块内进行逐行扫描——遇到 `/*` 时记录行号，直到找到匹配的 `*/`，将该范围内的每行用 `//` 前缀替换掉整个注释内容；若 `*/` 与 `/*` 在同一行则直接删去或改为单行注释。注意保留 JSON 本身的引号和键值对不变。
- 数字序号（如 `1.`、`2.`、`3.5.`）：检查列表中每个以数字加点开头的序号，确保其按正确顺序递增（1, 2, 3, ...）。发现跳号或重复时修正为正确的序列数。
- 其余（nasm/cool/cpp 代码块、`> [!note]`/`> [!tip]`、`$...$` 行内公式）原样保留。


## 资源

- 相对路径依次尝试：源章节目录 → `<image-root>/<卷名>/<basename>` → `<image-root>/<basename>` → 在 `image-root` 下递归搜索同名文件。
- 路径 `normpath` + `resolve()` 校验，仅允许位于输入根内。
- 找不到时插入 `<!-- WARNING: resource not found: <path> -->`，不阻断。
- 章节 `./resources/` 目录仅在正文实际引用到可解析资源时创建；无资源章节不创建。

## 校验（verify）

`verify --volume <输出卷> [--sidebar <卷>/_sidebar.md] [--chapter-dir <卷>/chapter | --chapter-files <章节文件...>]`

- 章节以实际发现的章节 `.md` 为准（不以 sidebar 目录为准，sidebar 可能遗漏），与输出子目录双向核对：
  - 源有而输出缺 → `FAIL: missing index.md for chapter <名>`
  - 输出有而源缺 → `FAIL: orphan chapter dir <名> (not in source chapter folder)`
- 每章 `./resources/<name>` 引用缺失 → `FAIL: missing resource <name> in <章>`
- 已存在的空 `resources/` 目录 → `FAIL: empty resources dir in <章>`（无资源章节不应留空目录）
- 元数据缺失（description/tags/categories 为空、`""`、`[]` 均算缺失）→ `MISSING: <章名或 _index.md> <字段>`
- `_index.md` 卷简介缺失（无占位标记、标记间为空、或仍含「待 subagent 生成」）→ `MISSING: _index.md overview`
- sidebar 章节 weight 顺序与 sidebar 顺序不符 → `FAIL: weight order mismatch`（仅在有 sidebar 时启用；无 sidebar 不校验）
- 任一 FAIL 返回非 0；MISSING 仅报告，待 subagent 补齐后复跑。

## 批量骨架（batch_prepare.py）

`python scripts/batch_prepare.py [--docs <docs根>] [--out <输出根>] [--image-root <image根>] [--volumes 卷...] [--force]`

- 用 `discover_volumes` 按"文件夹分组 markdown"发现卷并枚举章节（默认全部卷；通用容器词子文件夹上浮归父卷）。
- sidebar 存在时用于生成章节权重；不存在时按文件名字母序。
- 幂等：已完成章节（description 非空且非「待」）与已存在的 `_index.md` 跳过；`--force` 强制重跑。
- 每卷生成后运行 check_volume，输出 `FAIL <卷>: ...` / `MISSING <卷>: ...` 汇总行。
- 有任一 FAIL 退出码 1，否则 0；MISSING 不计数失败。

## 幂等

- `prepare-chapter`/`prepare-volume` 重跑保留已有非空 description。
- `_index.md` 卷概述占位 `<!-- VOLUME_OVERVIEW_START -->` / `<!-- VOLUME_OVERVIEW_END -->` 已填充则保留。
- 资源已存在且字节一致则跳过拷贝。
