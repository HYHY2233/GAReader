# 可用性修复 v3：实际应用验收

验收日期：2026-10-03。基线为 `5afc70259bd2042f908346e52010a32c7b1dd7c0`，实现位于 `fix/usability-v3`，功能提交为 `1ebda16` 和 `5c39cfe`。本记录针对 Django 应用及两篇真实标准论文，不使用指令包的静态原型作为验收证据。

## 变更摘要

- 新建／编辑／回复、当前线程、批注汇总使用三个独立宿主；保存与轮询不会打开汇总。草稿按实例、账户、论文、标签页、来源及操作隔离，关闭保留，明确丢弃才删除；断网重试继续使用同一幂等标识。
- 本源卡片先显示批注内容，再显示真实署名和时间；跨源及旧修订卡片明确来源，并逐段保留可点击的原始选区。精确选字、段落对应和未定位各自呈现。
- 以实际 HTML Range 或 PDF 页坐标计算 SVG 连线；拥挤时使用可用键盘操作的线程选择器。1366 窗口、手机与浏览器 200% 均能使用单条批注。
- 点击对象直接进入来源视图／修订，可返回原视图和逻辑阅读位置；临时来源高亮不修改页内显示偏好。PDF 导航等待真实页面渲染完成，并取消过期导航。
- 默认首页同时展示最近上传和所有现有分类；明确筛选时显示去重后的列表。标签独立管理，新上传要求分类及 1—5 个有效标签，预览发布再次校验；修改元信息不产生内容修订。
- 有效线程计数、删除／隐藏后的引用撤销、差量轮询保持焦点、无 JS 首页、减少动效同时完成。

主要文件：`app/static/reader-composer.js`、`annotation-presentation.js`、`reader-geometry.js`、`reader-navigation.js`、`reader-annotations.js`，以及 `app/library/models.py`、`forms.py`、`views.py`、`annotation_views.py`、`admin.py` 和真实迁移 `0003_tags_and_category_order.py`。沿用 Django、SQLite、原生 JS/CSS 和既有 PDF.js。

## 测试范围与证据

Windows 上使用真实 Microsoft Edge 154.0.4258.53 与 Playwright 1.62.1。浏览器验收经用户明确允许，全部测试写入隔离的 `test-runs/usability-v3/`。正式数据没有写入测试账户、论文、评分或批注。

| 验证 | 结果 | 证据 |
|---|---|---|
| Django 完整回归、数据库约束和上传安全 | PASS，61 项 | [最终输出](usability-v3/backend-results.txt) |
| 模型与迁移一致性 | PASS，无缺失迁移 | 同上 |
| 离线 DOM 回归 | PASS，6 组；属于模拟测试 | [DOM 结果](usability-v3/reader-dom-results.json) |
| 主要真实浏览器流程 | PASS，12 组 | [浏览器结果](usability-v3/browser-results.json) |
| 实际上传、标签后台、隐藏权限与返回 | PASS，3 组 | [论文库流程](usability-v3/library-results.json) |
| 中文、英文、PDF、对象的本源卡片 | PASS，4 组 | [卡片结果](usability-v3/card-results.json) |
| PDF 实际文字层与源矩形重合 | PASS，50/100/300% × 4 旋转，共 12 组 | [PDF 结果](usability-v3/pdf-results.json) |
| HTML 视口／字号／主题组合 | PASS，192 组 | 浏览器结果中的 E4 |
| PDF 四种视口与明暗主题 | PASS，16 组 | [补充布局结果](usability-v3/layout-followup-results.json) |
| 浏览器原生 200% | PASS，独立 Edge 配置的原生缩放值为 2 | [原生缩放结果](usability-v3/native-zoom-results.json) |
| 旧修订回源、返回新修订 | PASS，实际改动隔离副本译文／公式 | [修订浏览器结果](usability-v3/revision-browser-results.json) |
| 旧库升级无损 | PASS，6 张表原字段及 90 个原文件字节不变 | [迁移结果](usability-v3/migration-preservation.json) |
| 全新／重复安装及实际旧库升级 | PASS | [安装与升级输出摘录](usability-v3/maintenance-output.txt) |
| 备份、恢复、修订演练 | PASS，7 张表逐行一致，旧快照与源锚点不变 | [维护结果](usability-v3/maintenance.json) |
| 实际停止后重启 | PASS，会话、讨论、评分和修订返回值一致 | [重启结果](usability-v3/restart-results.json) |
| 正式库升级后的原数据核对 | PASS，2 个账户、2 篇论文原字段及原文件保留 | [正式库保留结果](usability-v3/local-upgrade-preservation.json) |

浏览器主报告的 `failedRequests` 包含主动断网产生的 `ERR_INTERNET_DISCONNECTED` 和取消旧导航的 `ERR_ABORTED`，是对应测试的预期结果；应用脚本错误与外网请求数组为空。Google 的查询编码、点击触发和弹窗备用入口由离线 DOM 回归检验；本轮没有实际向 Google 发送论文选区。

原生 200% 使用独立浏览器配置设置默认缩放并回读为 2，不是 CSS zoom 或页面 pinch。外窗口 1366，实际 CSS 视口 668，DPR 2，正文 40px，整页宽 668；截图通过 CDP 获取实际视口。

## 逐项验收与复现步骤

下列步骤均在隔离站点操作；需要双账户、旧修订和密集批注的场景使用测试副本。每项状态均为本轮实际结果。

| 项目 | 状态 | 复现步骤及核对点 |
|---|---|---|
| A1 | PASS | 选中同语言文字→新建→等待刷新；仅编辑器出现，汇总隐藏，页面不跳。见主浏览器 A1。 |
| A2 | PASS | 已有多条讨论时新建、保存、回复、编辑；保存仅更新当前线程。见主浏览器 A2。 |
| A3 | PASS | 打开汇总后直接回正文选字新建；汇总关闭，编辑器没有其他线程。见补充布局 A3。 |
| A4 | PASS | 组合输入事件、Esc、切视图、刷新、断网提交／恢复重试；双账户制造真实 409 后核对最新内容，草稿不丢且无重复。见主浏览器 A4。 |
| A5 | PASS | 关闭页内显示，使用文内搜索、汇总及跨源临时定位；搜索不消失、开关保持关闭。见主浏览器 A5、DOM。 |
| A6 | PASS | 取消新建后检查记录不增加；保存只清当前草稿；复制标签页及跨论文草稿互不覆盖。见主浏览器 A6、补充布局。 |
| B1 | PASS | 分别访问中文／英文／PDF／对象原选区；可见卡片首元素为正文，底部为服务器作者和格式化时间。见卡片结果。 |
| B2 | PASS | 双语中文→中文、双语英文→英文保持本源；PDF 与 HTML 互转为跨源，旧修订单独标明。见主浏览器 B2、修订结果。 |
| B3 | PASS | 查看跨源卡片的来源、可点击原文对象、正文、署名；长引用可换行展开。见主浏览器 B3。 |
| B4 | PASS | 调整字号 12/18/32/40、滚动、窗口 1366/1440/1920、重新加载图片、展开回复；比较真实 Range 与 SVG 端点。见主浏览器与补充布局 B4。 |
| B5 | PASS | 检查段落对应、不显示源表示及 stale／unmapped；不冒充本源精确选字、不画假连线。见主浏览器 B5、修订结果。 |
| B6 | PASS | 同处创建 20 条重叠讨论，使用键盘选择；不重叠遮正文、不生成长尾空白。见主浏览器 B6。 |
| B7 | PASS | 使用跨两页 PDF 选区，逐片回源；分别在 12 组缩放／旋转下检查真实文字层与按页矩形重合，不跨页涂空白。见主浏览器 B7、PDF 结果。 |
| B8 | PASS | 在 1366×768 及 390×844 新建、阅读单条批注；不自动打开全表。见主浏览器 B8、手机截图。 |
| C1 | PASS | 从跨源对象进入正确论文／修订／视图／线程／片段，然后返回；恢复视图和逻辑阅读位置。见主浏览器 C1。 |
| C2 | PASS | 重复来源访问、返回、浏览器后退前进，再直接打开多片段来源 URL；无嵌套阅读器、递归 return 或自动汇总。见主浏览器 C2、PDF 结果。 |
| C3 | PASS | 延迟 PDF 请求并快速切换视图，等待最终渲染；旧操作不得覆盖新视图。见主浏览器 C3、PDF 实际渲染检查。 |
| C4 | PASS | 访问旧修订、缺失 PDF、越权论文、隐藏来源；明确失败或进入正确快照，草稿保留。见后端权限测试、论文库和修订结果。 |
| D1 | PASS | 打开默认首页，点击分类锚点；最近上传和所有配置分类仍同时存在，无 tablist。见主浏览器 D1。 |
| D2 | PASS | 检查紧凑行、长中文题名、查看全部和空分类的一行状态。见主浏览器 D2、首页截图。 |
| D3 | PASS | 同篇显示在多个分区，修改标签／评论后核对首次时间不变、总数按论文去重。见后端测试、论文库 D6/D7/D8。 |
| D4 | PASS | 直接提交无标签、未知／停用 ID、重复和超过 5 项的请求；前后端均校验，重复先去重。见后端及论文库 D4。 |
| D5 | PASS | 上传真实标准 HTML，预览期间在管理后台停用标签，确认发布被阻止；返回改元信息无需重传，再发布无 PDF 论文。见论文库 D5。 |
| D6 | PASS | 从旧隔离备份迁移，逐行比较原字段及文件哈希；旧文章无标签仍可读；全新安装也成功。见迁移、维护及安装日志摘要。 |
| D7 | PASS | 关键词＋标签＋分类进入平铺列表；交叉分类不重复，双评分统计不因关联倍增。见后端及论文库结果。 |
| D8 | PASS | 带关键词、标签、排序和页码进入文章再返回；条件和滚动恢复。见论文库结果。 |
| E1 | PASS | 删除无回复根批注后检查列表、文中标记及计数；有可见回复时保留占位，隐藏根不泄露选区。见后端及论文库 E1。 |
| E2 | PASS | 双账户修改讨论并实际等待超过 25 秒；未变卡片节点、焦点、展开状态保留；隐藏来源撤销引用而草稿保留。见主浏览器 E2、论文库结果。 |
| E3 | PASS | 执行完整账户、双评分独立保存／撤回、权限及标准上传安全回归。见 61 项后端输出。 |
| E4 | PASS | 两篇论文在四种视口、明暗、12/18/32/40 正文和三种 HTML 视图；另测 PDF 视口及原生 200%。见 192＋16 组布局及缩放结果。 |
| E5 | PASS | 分别启用系统减少动效和应用开关，禁用 JS 打开首页；正文仍由服务器输出且可读。见主浏览器 E5。 |
| E6 | PASS | 阻断非本地资源后阅读和加载 PDF；无远程字体／遥测请求。断网提交保留草稿。见主浏览器 external=[] 和 PDF 布局结果。 |
| E7 | PASS | 实际全新 setup、重复 setup、启动、备份、独立恢复、修改副本修订、停止／重启后比较。见安装摘要、维护和重启结果。 |

## 实际截图

| 场景 | 截图 |
|---|---|
| 展开首页／筛选 | [1366 首页](usability-v3/home-sections-1366.png) · [搜索标签](usability-v3/home-search-tags.png) |
| 三种独立交互 | [单独编辑器](usability-v3/compose-only.png) · [本源卡片](usability-v3/inline-same-source.png) · [跨源卡片](usability-v3/inline-foreign-source.png) · [显式汇总](usability-v3/old-revision-overview.png) |
| 来源与拥挤布局 | [返回位置](usability-v3/source-return.png) · [20 条讨论](usability-v3/dense-twenty.png) · [旧修订来源](usability-v3/old-revision-source.png) |
| PDF | [跨页对象](usability-v3/pdf-crosspage.png) · [真实文字层对齐](usability-v3/pdf-transform-alignment.png) |
| 小屏与外观 | [手机编辑](usability-v3/mobile-compose.png) · [40px](usability-v3/large-font-40.png) · [减少动效](usability-v3/reduced-motion.png) |
| 原生浏览器缩放 | [首页 200%](usability-v3/home-native-200.png) · [200%＋40px＋暗色](usability-v3/reader-native-200-font40.png) · [200% 编辑器](usability-v3/compose-native-200.png) |
| 权限改变 | [隐藏来源后保留草稿](usability-v3/hidden-source-draft.png) |

## 范围之外

本轮规定的 33 项均为 PASS。50 人并发压力、真实手机软键盘和硬件中文输入法候选窗、其他浏览器、局域网部署及 HTTPS 为 NOT_RUN；手机检查是实际浏览器的窄视口，中文输入法检查使用浏览器 composition 事件。它们不由上述结果推断。Google 搜索结果页的外部服务可用性未验证。

复现命令、隔离数据依赖见 [测试说明](../tools/TESTING.md)，安装／回退见 [v3 升级说明](USABILITY_V3_UPGRADE.md)。源码包包含筛选后的上述实际证据，排除失败调试截图、完整本机路径、数据库、密码、会话、备份及运行配置。
