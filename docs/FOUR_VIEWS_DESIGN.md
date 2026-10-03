# 四视图与共享批注设计

本版继续使用 Django、SQLite、模板与本地 JavaScript。HTML 三视图来自同一份清理后的双语正文；原版视图由本地 PDF.js 渲染同一论文附带的实际 PDF。没有新增外部代理、OCR、AI 对话、通知或专题模块。

## 数据关系

```text
Paper ── Rating（原有两项评分）
  ├── current_revision → PaperRevision
  ├── PaperRevision（每份内容快照不可变）
  └── Comment（全文评论或共享讨论，只保存一份正文）
         ├── parent → Comment（一层回复）
         └── AnnotationAnchor（仅定位讨论根节点）
                    ├── revision → 来源快照
                    └── source → 原选区 segments
```

原全文评论不补造锚点。新批注复用作者、回复、删除占位、隐藏和幂等机制；Comment.version 用于编辑冲突检测。所有评分仍绑定 Paper，切视图不会增加评分或复制讨论。

PaperRevision 保存内容哈希、PDF SHA-256、定位清单哈希及标题。目录包含原 HTML、清理正文、用于阅读的正文、图片、PDF、原段落地图、representation-manifest.json、alignment.json、pdf-index.json。先建立临时快照并完成校验，再原子切换数据库引用；不覆盖旧目录。内容身份取决于清理正文、图片、PDF 和地图，单纯改变样式不产生修订。

## 定位规则

已有稳定 ID 经清理后使用 p- 前缀；没有 ID 的对象采用内容哈希生成 ID。同一个双语 pair／对象构成内容单元，允许同语言有多个 representation／fragment。修订 ID 与论文 ID 限定作用域，页码或段落序号不是身份。

HTML source 保存 representation_id、unit_id、语言、quote、原始引用、prefix／suffix、[start,end)、text_hash 和规范化版本。索引单位是 Unicode code point，不是 JavaScript UTF-16 单元。NFC 与明确的空白折叠规则建立规范文本到 DOM／PDF 字符的逆向映射；不做 NFKC、大小写折叠、删除科学标点或按译文字数比例匹配。emoji、组合字符、希腊文、上下标和跨 inline 节点由专项测试覆盖。复杂 MathML 选区改用公式对象批注。

PDF source 另存文件 SHA、0 起始物理页 index、PDF 提供的页标签、提取器版本和 PDF user space 的四边形数组。坐标不随屏幕缩放保存。标签与文内印刷的页码不一定相同；没有 PDF 页标签时不能据此推断印刷页码。服务端以实际文字和几何唯一匹配校验，重新生成标准 quads，拒绝越界／含糊选区。跨页分别存片段，多行不合并成跨双栏的大矩形。

| 来源与目标 | 保证与降级 |
| --- | --- |
| HTML → 同语言 | 原 ID＋位置＋quote 校验；必要时使用引用与上下文唯一重定位 |
| HTML → 另一语言 | 同单元段落／对象；本版没有人工审核的短语对齐，因此不会产生 aligned_exact |
| 英文 HTML ↔ PDF | 同 PDF 来源且整段文字唯一匹配，或所选引用和邻接上下文唯一匹配时可精确；否则保守降级 |
| 中文 → PDF | 通过已核对的英文内容关联，显示 block／page／unmapped，不假装英文短语精确 |
| 译者独有说明 → 英文／PDF | unmapped，列表保留并可回到来源 |
| 内容改变／对象删除／源 PDF 更换 | 不能确认原选区时 stale，保留旧引用与旧快照 |

已有 paragraph_map 只提供线索。IDAES 的页提示在对应英文核对通过后才用于页级定位；柔性合成氨的 AST 索引不能当 PDF 坐标。自动生成的全段 PDF 几何仍报告 block，逐对象覆盖报告与选区 exact 投影分开统计。本版未审核图表／公式的 PDF 对象区域，这些对象只能使用已有的页级证据或未定位状态。

## 阅读与协作

CSS Custom Highlight API 可用时绘制原选字，不向科学正文插入嵌套 span；其他定位和回退使用独立几何层。批注列表、键盘对象入口及聚合标记同时存在，不把纯颜色高亮当唯一入口。宽屏页边轨道按文档位置避让；展开侧栏时不重复渲染同一讨论。手机使用底部抽屉。

字体、主题、页内显示开关保存在账户＋设备层。阅读位置独立保存单元 ID／页码。批注草稿按账户＋论文＋线程或选区隔离。请求成功前不清除；幂等键防重复创建，编辑版本防静默覆盖。切视图只重新计算投影；活动页面每 25 秒增量取回更新，自己的提交立即刷新。

## 权限与本地资源

正文、原引用、清单、快照、PDF 和图像均验证当前用户的论文访问权限。来源链接包含论文／修订／线程身份，不包含登录令牌。隐藏根讨论不返回引用和坐标；评论文本使用 textContent／模板转义。服务端校验 JSON 深度、片段数量、长度、ID、哈希、字符边界和有限坐标。

PDF.js 使用同版本本地 worker、CMaps、字体和 WASM；不运行 PDF 脚本、XFA 或原生 PDF 注释动作。采用完整同源鉴权读取，没有实现 Range；大文件先完整下载并核验 SHA。PDFium 提取在有时限的子进程执行，超过页数／文字限制或提取失败时明确降级。CSP 限定同源脚本／连接，仅为本地解码器开放 WASM 编译；不开放 JavaScript unsafe-eval。

部署仍仅回环 HTTP。50 人并发、内网 HTTPS 与浏览器全量兼容性没有在本轮证明，不能由功能测试推断。依赖及审查范围见 [第三方资源记录](FOUR_VIEWS_DEPENDENCIES.md)。
