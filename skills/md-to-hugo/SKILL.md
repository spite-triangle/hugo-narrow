---
name: md-to-hugo
description: Convert Docsify-style markdown doc volumes (with _sidebar.md, README.md, chapter/*.md, and image/ resources) into Hugo-standard documentation structure (_index.md + <chapter>/index.md + <chapter>/resources/). Use whenever the user asks to convert, migrate, or transform markdown articles/docs into a Hugo project structure, mentions "卷"/"docs 转换"/"_sidebar"/"hugo 文档结构", or wants to build a Hugo doc site from existing markdown notes. Trigger even if they don't name the skill explicitly.
---

# md-to-hugo

将 Docsify 风格的 markdown 文档卷转换为 hugo 文档结构。

## 重要约定

- **卷 = 按文件夹分组 markdown**：某文件夹直接（或经通用容器词子文件夹）包含内容 markdown，即为卷。卷名 = 该文件夹原始名称（英文），如 `compiler`、`http`，不翻译、不中文化。输出目录为 `<out>/compiler/`。
- **通用容器词不作为卷名**：文件夹名若为 `chapter`、`group`、`notes`、`content`、`markdown`、`files` 等通用容器词，其内容 markdown 上浮归属最近的非常用名祖先卷。
- **`_sidebar.md` 可选**：有则用首行 `- **编译原理**` 作 `_index.md` 的 `title`（中文卷名）并按链接顺序生成章节 weight；无则 `title` 用卷文件夹名、weight 按文件名字母序。
- 章节文件夹名 = 内容 `.md` 文件名去扩展名（英文），如 `introduction`、`runtime`。

## 工作方式

- **脚本**（`scripts/md2hugo.py`）负责所有确定性转换：卷发现（`discover_volumes`）、sidebar 解析（可选）、frontmatter 生成、正文重写（图片/视频/term）、资源拷贝、校验。
- **批量骨架**（`scripts/batch_prepare.py`）可一次性为所有卷生成卷骨架与全部章节 `index.md`（幂等：已完成章节跳过），适合先铺骨架再由 subagent 逐卷填描述与标签。
- **subagent** 负责需要理解力的部分：概括章节与卷的 description、生成卷概述、处理脚本 warning。

## 主流程

1. **解析参数**：从用户消息提取 卷路径、输出根、并行数（默认 1）、`--date-source`（默认 mtime）、`--prompt-regex`（可选）。未提供输出根时先询问用户。
2. **解析卷**：用脚本 `discover_volumes` 按"文件夹分组 markdown"发现卷（通用容器词子文件夹上浮归父卷），得到卷目录与章节 `.md` 列表。有 `_sidebar.md` 时读它（用脚本，检测嵌套目录）得到章节顺序。`--volume-name` 取卷文件夹名（如 `compiler`, 英文、数字、下划线）；`title` 有 sidebar 时取首行去 `**`（如 `编译原理`），无则取卷文件夹名，两者用途不同。
3. **卷骨架**：调用
   `python scripts/md2hugo.py prepare-volume --volume-name <卷文件夹名> --out <输出根> [--sidebar <卷>/_sidebar.md] [--readme <卷>/README.md]`
4. **逐章编排**：
   - 调用
     `python scripts/md2hugo.py prepare-chapter --chapter <卷>/<章节目录>/<章节>.md --volume-name <卷名> --image-root <docs根>/image --out <输出根> [--sidebar <卷>/_sidebar.md] [--chapter-dir <卷>/chapter] [--date-source ...]`
     - `--chapter-dir`：无 sidebar 时用于按文件名字母序分配全局 weight（卷内章节集中于一个目录时传它）。
   - 阅读 `<输出根>/<卷名>/<章节>/index.md` 的转换结果，用 `fill-description` 写入 description、tags、categories（从正文概括）：
     `python scripts/md2hugo.py fill-description --file <输出根>/<卷名>/<章节>/index.md --description "<概括>" --tags "<标签1>, <标签2>" --categories "<分类1>, <分类2>"`
     - description：一行 10-50 字
     - tags：1-3 个逗号分隔关键词
     - categories：1-2 个逗号分隔大类
     - 利用 subagent 分析总结 `description`, `tags` 和 `categories` 不能随意编造， **一次`subagent`最多阅读 `8` 篇文章, 同时只运行一个`subagent`**
   - 审查正文质量，处理 `<!-- WARNING: resource not found: ... -->`（手动修正资源路径或报告用户）。
5. **卷概述与描述**：
   - 利用 `subagent` 进行总结，**一个`subagent`一次最多处理 `3` 卷，同时只运行一个`subagent`**
   - 阅读 README，概括 description、tags、categories，用 `fill-description` 写入 `_index.md`：
     `python scripts/md2hugo.py fill-description --file <输出根>/<卷名>/_index.md --description "<概括>" --tags "<标签1>, <标签2>" --categories "<分类1>, <分类2>"`
   - 将 `_index.md` body 中 `VOLUME_OVERVIEW_START/END` 之间的占位替换为卷内容简介。从 README 提取第一个非标题、非 HTML 的段落概括。**不要**生成章节列表、**不要**统计章节数量、**不要**使用"本卷""本章""该系列""本文档"等字样——仅用一段话简洁描述该卷涵盖的知识领域即可。
   - `description`, `tags` 和 `categories` 必须真实反映文档内容，不能随意编造
6. **校验**：运行 `python scripts/md2hugo.py verify --volume <输出根>/<卷名> [--sidebar <卷>/_sidebar.md] [--chapter-dir <卷>/chapter | --chapter-files <章节文件...>]`，报告结果。
   - 章节以实际发现的章节 `.md` 为准（不以 sidebar 目录为准，sidebar 可能遗漏），与输出子目录双向核对。
   - `FAIL:` 结构性问题：缺 index.md、孤儿章节目录、缺资源、空 resources 目录、weight 顺序错（weight 校验仅在有 sidebar 时启用）。
   - `MISSING:` 未生成的元数据：各章节与 `_index.md` 的 description / tags / categories，以及 `_index.md` 卷简介。凡出现 MISSING 的行都要由 subagent 补齐后再复跑校验。

## 转换规则速览

- 图片 `![alt|c,40](path)`：去尺寸参数、拷贝到 `./resources/`、路径改写。
- 视频 `<video src>`：拷贝到 `./resources/`，`src` 路径重写为 `./resources/<basename>`，`controls="controls" width="100%" height="100%"`。
- 仅当正文实际引用到图片/视频等资源时才创建章节 `./resources/` 文件夹；无资源章节不留空文件夹。
- `term` 代码块：保持 `term` 标记，精简提示符为 `$ `，`\/`→`/`，`// 注释`→`# 注释`。
- `$$...$$` 数学公式块 → ` ```math ... ``` `：便于 Hugo 与数学渲染器配合。
- 第一个 H1 用作 title 并从正文移除。
- 详见 `references/conversion-rules.md`。
