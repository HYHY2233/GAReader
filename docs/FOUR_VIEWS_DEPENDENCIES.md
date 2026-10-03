# 本地 PDF 依赖与审查记录

核对日期：2026-10-03。以下记录版本、来源和具体限制，不构成完整渗透测试或零漏洞保证。

| 组件 | 固定版本 | 用途与来源 |
| --- | --- | --- |
| pdfjs-dist | 6.3.289 | 浏览器原版渲染；[官方版本](https://github.com/mozilla/pdf.js/releases/tag/v6.3.289)、[官方接入说明](https://mozilla.github.io/pdf.js/getting_started/) |
| pypdfium2 | 5.13.0 | 服务端 PDF 字符、页框、旋转、页标签及字形几何提取；[官方版本](https://github.com/pypdfium2-team/pypdfium2/releases/tag/5.13.0)、[API 文档](https://pypdfium2.readthedocs.io/en/stable/python_api.html) |
| jsdom | 30.1.1 | 开发用 DOM 交互测试，不能代替真实浏览器验收 |
| Playwright | 1.62.1 | 原有开发依赖；本轮未获额外授权时不以独立 Playwright 控制浏览器 |

Python 和开发依赖分别锁在 requirements.lock、tools/package-lock.json。PDF.js 的库、worker、CMaps、标准字体、WASM／JS 解码回退、相关许可证均随源码提供，共 200 个资产加 vendor-manifest.json；运行时没有 CDN 请求。Apache-2.0 主许可、CMaps、Foxit／Liberation 字体及 OpenJPEG、JBIG2、QCMS 等子组件许可保留在对应目录。pypdfium2／PDFium 的许可随官方 Python 安装包安装，不将虚拟环境重新打包进源码。

重建前在 `tools/` 执行 `npm ci --ignore-scripts`，再用 Python 运行 `tools/vendor_pdfjs.py`。脚本核对版本，复制所需资产并记录每个文件 SHA-256 与 npm integrity；QuickJS 的 PDF 脚本运行时不分发。PDF.js text layer CSS 摘自同版本官方样式，保留归属说明。

本次检查 [PDF.js 官方安全公告](https://github.com/mozilla/pdf.js/security/advisories)，并核对实际依赖安装审计、同版本 worker、禁用 eval/XFA、鉴权端点、CSP、PDF 文件哈希、上传大小限制、子进程超时和坐标／引用验证。安装时 npm audit 报告 0 个已知漏洞；这只是当次依赖库报告，不能证明没有未披露漏洞。PDFium 子进程有资源边界和时限，仍以当前操作系统用户权限执行，没有新增操作系统级恶意文件沙箱。

字符选择参考 [W3C Web Annotation Data Model](https://www.w3.org/TR/annotation-model/#text-position-selector) 的 code point 与 [start,end) 语义，但采用应用自己的 schema；该规范不会提供自动跨语言对齐。HTML 绘制参考 [CSS Custom Highlight API](https://developer.mozilla.org/en-US/docs/Web/API/CSS_Custom_Highlight_API)，配合列表和键盘入口，未宣称完整 WCAG 合规。
