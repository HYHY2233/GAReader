# 重现测试

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
