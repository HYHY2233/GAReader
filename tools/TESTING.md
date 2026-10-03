# 重现测试

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
