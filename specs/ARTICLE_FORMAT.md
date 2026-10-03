# 标准文章与上传契约

适用：GAReader 当前版本。本规范是服务器端强制校验依据，不只是“建议作者排版”。

## 1. 标准究竟是什么

**上传文章＝按现有两份文件模式整理的、自包含英中对照 HTML。** 正文可搜索复制，段落成对，图表公式正确保留，来源与新增解释有区分。不是任意 HTML 网页，也不是 PDF 转图片。

已有两份文章结构不同，因此支持两个明确的 profile；不重新发明强制要求所有人填写的通用论文 ZIP／JSON 格式。不要求原文件改名，不要求两篇原稿先重写成同一种 DOM。

主上传文件只接受 `.html`（扩展名不区分大小写）且 UTF-8 可严格解码；允许 UTF-8 BOM。只有一个论文 `main` 内容根，图片须内嵌，公式须静态可渲染；不依赖旁边 assets、远程 CDN 或执行上传脚本才能读到内容。

可选附加原文 `.pdf` 和 `paragraph_map.json`。PDF、JSON 不能独立发布。网页不接受 `.zip`、目录、仅 URL、`.docx`、`.md`、单语 HTML 或随机网页。程序源码压缩包不是文章上传格式。

模板 `templates/standard_bilingual_article.html` 是未完成结构骨架，使用 IDAES 兼容 profile。其 `paper-library-template=incomplete` 标记以及 `【待替换】` 内容不能进入正式发布；新文章应由现有离线翻译整理流程补全，再上传网站。网站不生成翻译。

## 2. 必须兼容的原样输入

以下路径相对于仓库根目录：

| profile | HTML | 映射 | 原文 |
|---|---|---|---|
| `idaes-pair-v1` | `examples/idaes/article.html` | 同目录 `paragraph_map.json` | `examples/idaes/original.pdf` |
| `ammonia-pair-v2` | `examples/ammonia/article.html` | 同目录 `paragraph_map.json` | `examples/ammonia/original.pdf` |

这两个名字是适配器标识，不代表论文题材限制。未来其他论文也可以遵循相应结构；不能检查标题包含 IDAES／ammonia 才允许。识别依据是结构，不能仅凭 meta 自报或 CSS 类名单个命中。

### 2.1 IDAES 兼容结构

内容根是 `main#top`。正文单元为 `.unit.paragraph[id]`，标题为 `.unit.heading[id]`，部分条目为 `.unit.item[id]`。每个 `.pair` 直接包含一个 `.en` 和一个 `.zh`，两侧保留有效正文；`lang` 信息保留。

图片对象为 `figure.shared-figure[id]`；通常含图片、双语图注、图内文字对照表 `.figure-labels`。编号表格是 `.shared-table[id]`，不是所有 `<table>`。编号公式 `.equation[id]` 含 `.equation-math`、`.equation-number` 及 `.equation-shared-note`。参考文献 `.reference[id]` 允许完整英文条目、不要求逐条中文。

标题位于 `main > header` 内的 `.pair`，不能只寻找 h1；样例标题是 h2。正文之外的阅读器工具栏、dialog、搜索面板不是论文内容。预览占位 `img#reader-image` 不能当成丢图或第 20 幅论文图。

最小正文例子：

```html
<main id="top">
  <header><div class="pair">
    <div class="en" lang="en"><h2>English title</h2></div>
    <div class="zh" lang="zh-CN"><h2>中文题名</h2></div>
  </div></header>
  <section class="unit paragraph" id="p-001" data-source="来源页码或未提供">
    <div class="pair">
      <div class="en" lang="en"><p>One complete original paragraph.</p></div>
      <div class="zh" lang="zh-CN"><p>与左侧完整对应的一段译文。</p></div>
    </div>
  </section>
</main>
```

### 2.2 氨合成 v2 兼容结构

内容根是 `main.paper`。正文容器 `.paragraph[id]`；标题容器 `.heading-pair[id]`，其内 `.pair > .en` 和 `.pair > .zh`；节点可以是 div 或 section，不要写死为同一种元素类型。

**一个段落容器可能包含多个 `.pair`，之间插有共享公式。必须保持顺序，不把每个片段误当完整原段落，也不能将公式移到所有段落之后。**

原图容器 `.original-figure`，图注是后续兄弟 `.caption-wrap#figure-N`，图内文字表是相邻 `.table-wrap.figure-labels`。编号表的标题是 `.caption-wrap#table-*`，数据容器 `.table-wrap.source-table`，标题与表体不一定在同一父容器。

表 5 在当前成稿拆为两个显示块；附录表含 `table-B.9`。不能按表体块数量判定多了一张表或漏译。编号公式仍然是 `.equation[id]`＋数学体、编号和共享说明。参考文献 `.reference[id]`；术语和附录必须保留。

### 2.3 本次静态实测基线

本次由 HTML／JSON 重新清点，详细数字及哈希在 `reference_audit.json`。仅用于**这两个参考文件的迁移回归**，不是所有新论文必须达到的数量。

| 项目 | IDAES | 氨合成 v2 |
|---|---:|---:|
| 正文中的 `.pair` 数 | 234 | 158 |
| 段落容器 `.paragraph` 数 | 121 | 91 |
| 段落映射记录数 | 198，含标题及条目 | 91，含正文及术语条目 |
| 原图对象数 | 19 | 10 |
| 编号表数 | 5 | 9（表 5 拆块） |
| 编号公式数 | 13 | 70 |
| 正文 MathML `<math>` 数，含行内 | 145 | 750 |
| 参考文献条目数 | 41 | 35 |

`.pair` 总数不等于段落数；`math` 总数不等于编号公式数；`table` 总数包含图内文字对照、术语与检查记录。不能凭总标签数宣称内容完整。两篇原文是否逐句译对不在本次静态检查范围。

## 3. 内容层要求与检查边界

应有中英文题名、作者／来源及范围说明、正文层级、完整的英中段落对照、原有图表公式、参考文献和实际存在的附录。未知 DOI、页码、来源版本写未提供或待核实，不能强制编造。

正文不做摘要替代，不任意拆句／合并段落。共享公式只显示一份，但必须有中文“英中共用，中文栏不再重复”一类提示；数字、数学结构、编号不能因统一模板改变。原稿中明示的待核实／缺失说明保留，不把它们改成已完成。

参考文献、作者姓名、数字、符号不需要为了满足双语检查而伪造中文。AI 补充与原文、译文明显区分；已有文末术语、疑点表和历史检查记录是文章内容，应保留并标明历史性质。

服务器可以判定结构、资源、成对性和引用一致，**不能自动证明翻译正确或相对于原 PDF 无漏译**。校验通过应写“格式与资源检查通过”，不能写“论文已审核／译文完全准确”。无原文 PDF 时尤其不能声称完整性已核实。

上传最终确认复用一个勾选：“我确认上传的是按标准整理的文章，且保留了已知未完成／待核实说明。”不要另建审核工作流。模板骨架或明显占位稿必须拒绝，不因勾选就跳过硬校验。

## 4. 段落映射

不是网页上传必需品；两篇初始化需读取并保留现有映射。缺少映射时从受控 DOM 建导航和稳定块定位，只标记 source=unavailable 或保存 HTML 自带来源，不能伪造 PDF 页码。

IDAES 顶层是数组：

```json
[{"id":"p-001","kind":"paragraph","source":["PDF 2"],"en":"...","zh":"..."}]
```

氨合成顶层是对象：

```json
{
  "source_file":"原文件名.pdf",
  "source_sha256":"提供时校验，不提供不伪造",
  "paragraphs":[{
    "id":"p-001","kind":"paragraph","section":"...","source":"PDF 2",
    "source_ast_range":[1,2],"equations":[],
    "english_fragments":["..."],"chinese_fragments":["..."]
  }]
}
```

适配成内部记录时保留 id、原始片段顺序、来源字段和公式关联。映射中 ID 必须唯一并能在该篇内容找到；提供 source_sha256 且附了 PDF 时必须核对文件。映射不是整份 HTML 的全部内容，不能只按映射重建文章然后丢掉图表、图注和参考文献。

## 5. 服务器端硬校验

错误必须阻止发布、不给出新论文链接、不留下半成品数据库条目；临时文件可清理。下列错误码是建议命名，可统一实现但语义必须覆盖。

| 代码 | 拒绝情形 | 反馈要求 |
|---|---|---|
| FMT_FILE | 非合格 HTML、不可 UTF-8 解码、PDF／ZIP／链接冒充 | 指明本版只收标准自包含双语 HTML |
| FMT_PROFILE | 不是任一支持的结构、无唯一主内容根 | 说明需要哪种对照结构 |
| FMT_PAIR | 正文／标题对缺英文或中文，成对结构损坏 | 提示具体段落或标题位置 |
| FMT_ID | 标识重复、导航／映射的必要定位引用失效 | 指出冲突 ID；跨论文相同 ID 不算冲突 |
| FMT_RESOURCE | 正文图像无数据、损坏、外部依赖、引用磁盘路径 | 指出图号或资源，不联网代抓 |
| FMT_MATH | 编号公式缺编号、缺共享说明、数学体缺失或只剩未渲染代码 | 指出公式号；安全静态 MathML 可接受 |
| FMT_MAP | JSON 无法解析、结构错误、ID 不存在、PDF 哈希不符 | 不吞掉该文件假装成功 |
| FMT_TEMPLATE | 未完成模板标记、明确占位正文 | 要求补齐真实文章而非仅改后缀 |
| FMT_LIMIT | 超过大小、解码图片像素或解析复杂度限制 | 显示限制与实际量级 |
| FMT_SANITIZE_LOSS | 清理导致正文、图表或公式实质丢失 | 阻止发布，报告不能支持的结构 |
| FMT_DUPLICATE | 相同原始 HTML 已有记录 | 指向可访问的已有论文，不增加记录 |

建议默认上限：HTML 50 MiB、可选 PDF 100 MiB、映射 JSON 5 MiB、单请求总计 160 MiB；解码后单图 20 MiB、单图 40 百万像素、所有图片累计解码字节 120 MiB；DOM 节点数和嵌套深度设有界值并测试两篇真实文件不会误拒绝。限值是本版可调默认，不是行业标准。上传流式检查大小，不仅依赖客户端声明。

图片允许内嵌 PNG／JPEG／WebP 且验证类型与实际解码；不直接接受可执行 SVG、data:text/html、外部图片、任意 `file:`／`blob:` 路径。源文件带外部样式／脚本时不要加载；标准正文必须无需它们即可解析，若它们是必需内容依赖则拒绝。两份现有文件均为静态内嵌正文和 MathML，不需要执行论文脚本来得到公式。

无图、无表或无公式的其他论文可以合法上传；不要强制每篇都至少有一张图或一个公式。存在相应对象时才检查其对应结构与资源。

## 6. 安全清理不能破坏科研内容

使用可靠 HTML 解析与允许清单，不靠正则替换“script”字符串就宣称安全。禁止执行任何导入代码。保留原稿只读副本，生成受控内容另存。

统一去掉上传文件的 head 脚本、任意 style、运行工具栏、事件属性、外部可自动加载资源、form、iframe、object、embed、base、meta refresh、危险 URL 等。由应用自己的受信 CSS／JS 建阅读器，并为正文加作用域，隔离上传 class／id 对主站控件的影响。保留内部 ID 映射，必要时命名空间化并重写锚点。

MathML 需安全保留本样例实际用到的结构：math、semantics、mrow、mi、mn、mo、mtext、mfrac、msub、msup、msubsup、mover、munder、munderover、mtable、mtr、mtd、mspace、mstyle 以及纯文本 LaTeX annotation。保留必要安全属性，禁止其中 href、事件和富内容注入；annotation-xml 等未知主动内容不直接放行。测试特殊命名空间和编码形式，不能只测试普通 script 标签。

HTML 保留 table、thead、tbody、tr、th、td、colgroup、col、合并单元格属性，以及段落、sup/sub、来源说明、details、blockquote 等需要的结构。原稿 inline width/text-align 只能经属性值允许清单转为安全等效样式，不能直接信任 CSS。若清理器无法保留某种 MathML，先修正配置并测试，不得改成公式图片或删掉公式过关。

正文 `main` 内外边界要明确：两篇原稿的来源说明、AI 补充、术语、附录和历史检查内容都在 main 中，保留；IDAES 旧阅读工具位于 main 外，应替换为站点模块。原页 footer 等来源标识也应记录或保留，不能因抽取丢失归属。

可以设置 CSP 作为纵深防护，但 CSP 不代替清理。正文预览、正式阅读、管理员预览使用同一安全链路。原始文件永远不作为主站同源的可执行 HTML 页面返回。

## 7. 迁移前后保真验收

每个适配器输出以下比对结果作为测试证据，不要只对比文件大小：

- 正文英中各片段文本，按 DOM 阅读顺序做有限空白归一化，内容字符不应删减或替换。工具栏／搜索文本排除，但论文来源和 AI 标识保留。
- 编号图、编号表、编号公式和参考文献的 ID／标签集合；氨合成表 5 的拆块关系保留。
- 每幅原图解码后字节哈希或经过明确无损规范化后的像素一致性；本版优先不重新编码图片。
- 每个 MathML 的规范化结构与 LaTeX annotation；行内数学也检查，不能只检查编号公式。
- 每张科研表格的行列、合并属性和单元格内容；避免只“表数相同”而数据错列。
- 目录与对象导航实际可跳到对应内容，真实浏览器加载图片成功、公式可见、没有正文依赖网络请求。

参考文件的静态基线可作为断言输入，但必须与导入后结果比较并做浏览器回归，才能报告迁移保真通过。不能把本包 reference_audit.json 当成已经测试过新网站。
