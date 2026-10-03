# 四视图与共享批注实际验收

日期：2026-10-03。源码基线：`fae4a83b9661103023959b47a5fcd07c13a08758`，本地开发分支 `feature/four-views-annotations`。实现提交：`f8d5b3b92cf866de8bdae4df4e03c06f600ab7b8`；后续交付提交仅补充本报告、证据与文件清单。本报告区分真实浏览器、服务端检查和 DOM 模拟，不以指令包 preview 截图作为证据。

环境：本机 Windows 11、Python 3.12.14、Django 5.2.17、Node 24.19.0、jsdom 30.1.1；原版渲染为 PDF.js 6.3.289，提取为 pypdfium2 5.13.0。真实浏览器使用 Codex 内置浏览器的 Chromium 渲染器及 CUA 工具；没有验证其他浏览器或用户另一台笔记本。测试地址 `http://127.0.0.1:8047/`，隔离目录 `test-runs/four-views/acceptance-v2`，恢复目录 `restored-v2`，译文修订演练目录 `revision-rehearsal-v2`（均在 `test-runs/four-views/` 下）。正式数据和 GitHub 未改动。

## 实际结果

| 项目 | 结果 | 证据与边界 |
| --- | --- | --- |
| Python 回归 | PASS | 53 项全通过；末次增加非法 PDF 片段校验后，相关 15 项再通过。含账户、匿名身份、分类／检索、权限、评分、全文评论、上传和保真 |
| 前端 DOM 交互 | PASS | 6 组通过；字号／偏好、划词、Unicode、混选拒绝、草稿、失败保存／防双击、Google 显式触发、查找独立高亮。属于模拟测试 |
| 旧数据迁移 | PASS | 旧版 2 条全文评论与 4 条评分逐行不变；重复升级保持两篇论文和两个初始修订，无重复导入 |
| 一致备份与恢复 | PASS | 8 条评论（含回复）、4 条评分、5 个锚点、2 个修订逐行一致；PDF／图像／清单哈希、四视图同线程、旧来源 URL 与权限在恢复库通过 |
| 内容保真 | PASS | 两篇真实 HTML 正文文本、MathML、图像地址在加入阅读定位属性前后相同；导入保真检查同时覆盖原图字节及科学对象 |
| HTML 布局矩阵 | PASS | 两篇 × 1366×768／1440×900／1920×1080／390×844 × 12／18／24／32／40 px × 三 HTML 视图，共 120 组真实页面 DOM 尺寸检查；字号准确、控件字号不随正文放大、无全局横向溢出 |
| 真实原版 PDF | PASS | 两篇实际文件分别 31／12 物理页，canvas＋文字层＋批注层，无原生 PDF iframe。暗色下纸页保持白色 |
| PDF 缩放／旋转 | PASS | 两篇 × 50／100／200／300% × 0／90／180／270°，32 组；原文选区与投影 quads 中心偏差在 3 CSS px 内，局部横向滚动不撑破全页 |
| 真实中文划词／跨用户回复 | PASS | 账户 A 的 8 字中文批注刷新后存在；匿名读者 B 看到同线程并实际回复，不能编辑 A 的正文；三 HTML 模式和 PDF 列表共享 ID |
| 真实 PDF 划词及跨页 | PASS | 两篇各实际拖选英文创建；合成氨另从物理页 1 拖到页 2，服务端保存两个独立页面片段，恢复后仍保留 |
| 真实公式对象批注 | PASS | 在 IDAES 公式处用 Alt+A 新建并保存完整对象批注；未拆分 MathML；有真实截图 |
| 页内关闭与主题持久化 | PASS | 真实页面关闭后隐藏轨道，换暗色、刷新、打开列表仍保持关闭；关闭时划词工具和新建编辑器可用 |
| 切视图草稿 | PASS | 真实页面输入后切英文，正文草稿未变；离线 DOM 测试另覆盖关闭、失败保存与重试 |
| 内容修订与回源 | PASS | 实际维护命令：CSS 不建修订，文字修改建立新快照，未变英文 exact、改写中文 stale、删除公式 stale；旧文件字节及源锚点不变，旧快照端点可访问 |
| 扫描页／无 PDF／重复引用／特殊字符 | PASS | 服务端实际小型 PDF 与 Unicode 合成样本测试；未把这些合成样本当两篇论文的浏览器实测 |
| 200% 浏览器页面缩放 | NOT_RUN | 内置浏览器快捷键尝试未改变视口／缩放比例，不能把字号调大或缩窄视口当此项通过 |
| 屏蔽外网后的完整浏览器流程 | NOT_RUN | 当前浏览器接口没有网络隔离能力；本地资源与 CSP 已检查，但不能代替断网实测 |
| reduced-motion 实际系统设置 | NOT_RUN | CSS 已配置禁用非必要动画；当前工具未提供系统媒体偏好模拟 |
| 草稿确认框后续点击／手机抽屉交互截图 | NOT_RUN | 原生草稿确认框触发后，内置浏览器自动输入暂停，工具无法接管该确认框；未把 DOM 模拟写成实际通过 |
| 回源链接自动滚动／PDF 自适应轨道变化 | NOT_RUN | 后期针对加载顺序和容器 resize 做了修正，服务端／语法通过，但确认框阻塞后未重跑最后一轮浏览器操作 |
| 实际 Google 结果内容、50 人压力、内网部署 | NOT_RUN | 检索 URL 与显式点击逻辑已测；没有外发论文查询，也未配置内网或进行压力测试 |

本轮最后一次完整测试中的大图警告来自“拒绝超限图片”的预期用例，测试通过。布局矩阵是在首次验收副本运行，随后补充了译者独有说明单元、首页视觉与附件完整性校验；核心字号布局没有更改。PDF 矩阵与公式截图使用更新后的验收副本。不能据这些结果宣称全部 ACCEPTANCE 条目都已完成。

## 两篇 PDF 的逐单元覆盖

| 论文 | 内容单元 | exact | block | object | page | unmapped | 完整英文表示 exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| IDAES | 304 | 0 | 128 | 0 | 108 | 68 | 129 |
| 柔性合成氨 | 239 | 0 | 81 | 0 | 20 | 138 | 84 |

表中前五类是**内容单元到 PDF 的保守覆盖**。完整英文表示是另一统计层，不可与内容单元数量相加；同一单元可能有多个英文片段。选中的英文子串还可由严格 quote＋相邻上下文唯一匹配获得 exact。中文通常只投影到段落或页；未提供经人工审核的跨语言词组或 PDF 对象边界，因此 aligned_exact 与对象区域精确定位没有伪造。

逐项文件：[IDAES JSON](verification/four-views/idaes-coverage.json)、[CSV](verification/four-views/idaes-coverage.csv)；[合成氨 JSON](verification/four-views/ammonia-coverage.json)、[CSV](verification/four-views/ammonia-coverage.csv)。报告列出 unit ID、对象类型、物理页、方法、未定位原因和输入地图核对状态。它是定位覆盖报告，不是翻译／学术内容审校。

普通英文段落、PDF 题名／摘要、跨页选择与公式对象有真实浏览器检查。双栏与跨页段落、图注、表格、公式、参考文献包含在全量报告中；目前没有由人逐项核准的 PDF 区域标注。重复短句的消歧由实际提取的小型 PDF 测试覆盖，不宣称对两篇论文所有重复短句都人工审核。

## 证据与操作复现

- [120 组布局记录](verification/four-views/layout-matrix.json)、[32 组 PDF 几何记录](verification/four-views/pdf-transform-matrix.json)、[迁移](verification/four-views/migration.json)、[恢复／修订](verification/four-views/maintenance.json)、[恢复后权限](verification/four-views/restored-verification.json)。
- [首页浅色宽屏](verification/four-views/library-1920-light.jpg)、[中文暗色阅读](verification/four-views/idaes-zh-dark.jpg)、[IDAES 公式对象](verification/four-views/idaes-formula-object.jpg)、[IDAES PDF](verification/four-views/idaes-pdf-100-0.jpg)、[合成氨 PDF 旋转](verification/four-views/ammonia-pdf-100-90.jpg)。全部来自实际应用，未使用演示原型。
- 自动测试和隔离演练入口见 [tools/TESTING.md](../tools/TESTING.md)，正式维护见 [升级回退说明](FOUR_VIEWS_UPGRADE.md)。恢复备份、数据库、随机测试密码和本机密钥不在公开证据中。

继续浏览器验收时，使用新的隔离浏览器会话：登录测试账户，打开每篇论文；依次设置 200% 浏览器缩放、系统 reduced-motion；仅阻断外网而保留 localhost，刷新后读 HTML／PDF、新建回复并定位；关闭页内显示后保存新批注，确认没有擅自开启；在 390px 宽度打开底部抽屉并检查原生选择。逐项保存实际截图及结果后再将相应 NOT_RUN 改为 PASS，不能仅修改文字。
