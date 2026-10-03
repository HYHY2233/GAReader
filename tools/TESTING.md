# 重现测试

## 定点修复 v4

实际结果见 [v4 验收](../docs/ROOT_CAUSE_V4_VERIFICATION.md)。后端 67 项、离线 DOM 6 组、纯显示计划 6 组。DOM／纯函数结果不替代真实浏览器验收。始终显式指定隔离数据目录：

```powershell
$env:PYTHONUTF8 = '1'
$env:PAPER_LIBRARY_DATA = (Resolve-Path 'test-runs/root-cause-v4/working').Path
.venv\Scripts\python.exe app/manage.py collectstatic --noinput
.venv\Scripts\python.exe app/manage.py test library --verbosity 1
.venv\Scripts\python.exe app/manage.py makemigrations --check --dry-run
node tools/reader-v2-dom-tests.cjs
node tools/annotation-display-tests.cjs
```

本轮 Playwright 使用项目锁定依赖和真实 Edge。`root-cause-*.cjs` 是对本次场景的回放工具，依赖隔离备份、真实示例、动态场景 ID 和私有凭据文件，不能直接填入正式数据。脚本在登录前核对服务器实例；所有凭据、数据库和完整 API 快照均忽略提交。

准备四个独立目录：`working` 从 v3 工作隔离备份恢复；`fresh-install` 从空目录运行正常 `launcher.py setup`；`legacy` 从已应用 0003、13 项停用的旧隔离库恢复再 setup；`old-revision` 从 v3 已完成修订演练的隔离库恢复。`root-cause-fixtures.py fresh-install`／`legacy` 在初始化之后只创建测试账号，并先断言启用标签分别为 13／0，不能用它为词表补数据。网站分别在回环端口 8057／8058／8059／8060 运行。

实际执行顺序：

```text
node tools/root-cause-before.cjs                         # 修改前的 b224921 上复现一次
node tools/root-cause-browser.cjs                        # 修改后，两篇 PDF 与 72 组布局
node tools/root-cause-tags.cjs                           # 真上传、预览、发布、后台启停
node tools/root-cause-zoom.cjs                           # 独立 Edge 配置，原生 200%，24 组
.venv/Scripts/python.exe tools/root-cause-regression-data.py
node tools/root-cause-regression.cjs                     # 真实混合来源、跨页、轮询、来源返回
node tools/root-cause-pdf-errors.cjs                     # 只临时改隔离 PDF，finally 恢复
.venv/Scripts/python.exe tools/root-cause-persistence.py before
```

随后实际停止 fresh-install／legacy 两个实例，分别重复 setup，再重新启动，执行：

```text
.venv/Scripts/python.exe tools/root-cause-persistence.py after
node tools/root-cause-restart.cjs
```

上述脚本会向隔离库创建测试论文和批注，重新完整验收应从新的隔离副本准备，不宣称可无条件重跑。最终另外复跑主浏览器与 DOM 回归。`verify-preservation.py --data-dir <已停机原目录> --archive <维护前备份> --output <私有输出>` 只读比较所有表及论文文件字节；输出仅行数与结果，不导出用户记录。

正式站启动前已完成备份比对；后续只读检查登录页、实例和已加载的静态文件。没有将测试账户、标签操作或模拟评论写入正式库。

## 可用性修复 v3

当前完整后端套件为 61 项，离线 DOM 为 6 组。所有命令在源码根目录运行，显式指定隔离目录。第一次先 `setup.cmd --data-dir test-runs/usability-v3/fresh-install`；测试使用独立测试数据库，不能将正式数据目录传给测试脚本。

```powershell
$env:PYTHONUTF8 = '1'
$env:PAPER_LIBRARY_DATA = (Resolve-Path 'test-runs/usability-v3/fresh-install').Path
.venv\Scripts\python.exe app/manage.py test library --verbosity 1
.venv\Scripts\python.exe app/manage.py makemigrations --check --dry-run
```

上述测试生成脱敏的 DOM fixture。在 `tools/` 执行 `npm ci --ignore-scripts` 后回源码根目录：

```text
node tools/reader-v2-dom-tests.cjs
```

最终输出和截图见 [v3 验收](../docs/USABILITY_V3_VERIFICATION.md)。61 项包含标签规范化、前后端上传校验、预览再校验、元信息与修订隔离、统计去重及隐藏／删除后的有效线程口径。图像超限安全用例会出现 PIL 的 DecompressionBombWarning，套件最终为 OK；不能将它删除而跳过安全检查。

### 本轮真实浏览器脚本

以下是针对本次隔离迁移副本的回放工具，**不是不带数据的通用一键测试**。它们使用 `test-runs/four-views/credentials.json`、含原有批注和跨页锚点的隔离备份及 fixture ID；这些敏感资料不随源码分发。需要先准备具有相同场景的隔离测试库和随机凭据，或按验收表逐项操作。不能把正式备份、真实账号填入测试配置。

本次实际数据准备：从四视图隔离备份恢复到全新的 `test-runs/usability-v3/working`，运行 setup 后，在添加任何测试记录之前执行 `tools/usability-data.py` 比较旧表与全部原文件；它只接受该固定隔离目录，并设置隔离管理员的测试密码。原始隔离备份文件名记录在脚本内，重新准备时应指向自己的隔离备份，不得复用正式目录。所有真实浏览器脚本在登录前核对 `/healthz/` 的实例标识，不一致立即拒绝。

本轮工作实例启动及执行顺序：

```text
start.cmd --data-dir test-runs/usability-v3/working --port 8047
node tools/usability-browser.cjs
node tools/usability-zoom.cjs
node tools/usability-library.cjs
node tools/usability-pdf.cjs
```

主脚本包含 192 组 HTML 布局、20 条密集批注、真实 25 秒轮询、断网与幂等、冲突和来源跳转。zoom 脚本使用独立 Edge 配置的原生 200%，不更改日常浏览器设置。library 脚本在隔离库发布无 PDF 的真实标准译稿副本，并在验证后隐藏它。重跑前需准备新的场景副本，脚本不会清空或重置已有数据。

停止工作实例后制作备份，再运行：

```text
backup.cmd --data-dir test-runs/usability-v3/working --output test-runs/usability-v3/backups
.venv\Scripts\python.exe tools/revision_rehearsal.py --archive "本轮隔离备份.zip" --source test-runs/usability-v3/working --target test-runs/usability-v3/restored-verified
start.cmd --data-dir test-runs/usability-v3/restored-verified --port 8048
node tools/usability-restored.cjs
node tools/usability-layout.cjs
node tools/usability-cards.cjs
```

修订演练逐行比较评论、评分、锚点、修订、标签及两类关联共 7 张表；只在恢复副本中修改译文／删除公式来验证 stale 与旧快照来源，不改只读示例。停止并重新启动同一 8048 实例后，在 PowerShell 设置 `$env:GA_RESTART='1'`，再执行 `node tools/usability-restored.cjs` 比较重启前后 API 与会话，结束后 `Remove-Item Env:GA_RESTART`。

脚本报告写入忽略目录 `evidence/usability-v3/`；浏览器会话、完整 API 快照和测试数据库写入 `test-runs/`。对外只复制经过筛选的截图和脱敏结果。`docs/usability-v3/` 是本次实际完成的验收证据，不能以其中旧 PASS 替代新的运行结果。

## 四视图与共享批注版本

所有命令从源码根目录运行，始终显式指定隔离数据目录。浏览器 UI 需要由当前环境允许的浏览器工具或操作者执行；DOM 测试没有浏览器截图、网络隔离或缩放证明力。

```powershell
$env:PAPER_LIBRARY_DATA = (Resolve-Path 'test-runs/four-views/acceptance-v2').Path
.venv\Scripts\python.exe app/manage.py test library --verbosity 1
.venv\Scripts\python.exe app/manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe app/manage.py collectstatic --noinput
```

完整 Python 套件当前为 53 项；其中 `library.test_annotations` 15 项检验真实 PDF 字符与几何、Unicode、四视图同线程、非法源锚点、失败回滚、权限、幂等、版本冲突、扫描页和修订回溯。`library.test_reader_tools` 生成无真实账户资料的 `evidence/reader-tools-fixture.html`；执行该项后，在 `tools/` 运行 `npm ci --ignore-scripts`、`npm run test:reader`，当前为 6 组离线 DOM 测试。其几何、确认框和网络结果为模拟值。

`four_views_check.py prepare --archive <旧版隔离备份> --data-dir test-runs/<全新目录>` 恢复旧库并重复初始化，逐行对比旧评论与评分；不会覆盖已存在的恢复目录。它要求备份内已有普通测试账户。`verify --data-dir test-runs/<隔离目录>` 检查正文／MathML／图像保真、四视图线程去重、来源快照链接、登录和论文权限，并生成两篇逐对象覆盖 JSON／CSV。verify 会在事务回滚内暂时隐藏论文来验证权限，运行前应停止该隔离实例。

停机制作含新批注的隔离备份，再执行：

```powershell
.venv\Scripts\python.exe tools/revision_rehearsal.py --archive "隔离备份.zip" --source test-runs/four-views/acceptance-v2 --target test-runs/four-views/全新修订演练目录
```

此脚本针对本轮隔离库中的 `reader_a` 及 IDAES／合成氨验收批注：比较恢复后的四张表，实改副本译文并删除一个公式，检查不变引用、stale 与旧快照回源。它拒绝 test-runs 之外的目录；不改 examples，不适合对任意正式备份直接运行。输出含本机路径的完整证据保留在忽略目录；公开证据已去除路径和凭据。

真实浏览器矩阵、人工操作步骤与尚未执行项目见 [本轮验收记录](../docs/FOUR_VIEWS_VERIFICATION.md)。以下为历史测试流程；旧 `browser-tests.cjs`／`restore-browser-tests.cjs` 没有代表本轮四视图矩阵，也没有在本轮重新执行。

## 原公开包流程

运行输出写入根目录 `evidence/`；发布验证摘要见 `VERIFICATION.md`。不要对正式 `var` 数据运行模拟写入测试。

2026-10-03 入口改动：`library.test_accounts` 验证正常注册、密码登录、重名与密码校验；`library.test_anonymous` 验证记住并沿用上次身份、主动更换身份、旧会话兼容、长效凭据的过期与防伪、评论及评分归属。主入口是 `/login/`，注册为 `/register/`，匿名操作为 `/anonymous/`。浏览器脚本使用的 `/account/login/` 仍兼容。新版入口尚未重新执行真实浏览器验证。

框架测试自动使用独立测试数据库及临时附件目录，可在安装完成后运行：

```text
.venv\Scripts\python.exe app\manage.py test library --verbosity 2
```

划词 Google 与顶部工具栏的离线交互测试：先执行 `python app/manage.py collectstatic --noinput` 和 `python app/manage.py test library.test_reader_tools`，生成只有合成测试正文的 `evidence/reader-tools-fixture.html`；在 `tools` 执行 `npm ci`、`npm run test:reader`。测试使用锁定的 jsdom 30.1.1，验证实际前端脚本事件、查询编码、备用链接和设置持久化；布局几何、原生弹窗状态和窗口打开接口是模拟值，不访问本机网站或 Google，也不算浏览器视觉测试。

完整端到端测试在**新的源码副本**执行，避免重置已有测试库。顺序如下：

1. `setup.cmd`，完成当前副本的首次安装。
2. `.venv\Scripts\python.exe tools\prepare-tests.py`，生成与正式库分离的测试数据和随机测试凭据。
3. `start.cmd --data-dir test-runs/integration --port 8001`，保留窗口。
4. 安装开发用 Node.js 与 Microsoft Edge；在 `tools` 执行 `npm ci`，再执行 `npm run test:browser`。Node 工具仅用于开发测试，不参与日常启动。此次使用了本机已有 Node 24.19.0、Playwright 1.62.1、Edge。
5. 停止测试网站，再执行 `.venv\Scripts\python.exe tools\maintenance-tests.py`。它验证重复安装、停机备份、独立恢复、坏 ZIP、账户管理；默认拒绝复用既有恢复目录。
6. `start.cmd --data-dir test-runs/restored --port 8002`，执行 `npm run test:restore`。
7. 停止恢复环境，再用同一入口和端口重新启动。执行 `.venv\Scripts\python.exe tools\restart-checks.py` 和 `.venv\Scripts\python.exe tools\busy-check.py`，验证真实 HTTP 持久化和 SQLite 忙等待失败。它们只使用隔离测试库已存在的会话，不读取密码。最后停止测试网站。

实际浏览器和依赖版本记录在结果 JSON 中；也可以用已有的 Playwright 环境运行这些脚本。独立安装版本以 `tools/package-lock.json` 为准。

如果要重跑完整流程，使用新的源码目录。脚本不清空既有库；请勿为方便测试删除真实数据。`test-runs/credentials.json` 是随机隔离测试凭据，只保存在本机、已被忽略，不得打包分享。正式库的账户应由用户自行设置。

备份和恢复测试会生成包含测试账户密码哈希的敏感 ZIP，只留在 `test-runs`。公开交付源码包排除了全部 `var`、备份、`.venv`、测试数据及真实配置。
