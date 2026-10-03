# 资料来源

`examples/` 保留了开发时使用的两篇用户提供的示例论文。每篇含自包含双语 HTML、原文 PDF 和段落映射 JSON。复制过程中保持文件字节不变，原始哈希与结构基线见 `reference_audit.json`。

| 示例 | 路径 | 用途 |
| --- | --- | --- |
| IDAES 过程建模框架与模型库 | `examples/idaes/` | `idaes-pair-v1` 格式、图表与 MathML 的导入回归 |
| 柔性合成氨过程的仿真与模型预测控制 | `examples/ammonia/` | `ammonia-pair-v2` 格式、复杂公式与跨段表格的导入回归 |

示例论文的作者、出版来源、参考文献和原文权利声明保留在文件中；译文的来源与补充说明也保留在 HTML 中。程序仓库公开不改变这些资料各自的授权范围。格式与内容指纹检查不代表译文经过重新人工审校。

历史交接文档、个人环境信息、中间翻译稿和运行数据不属于本公开源码包。

技术文档：[Django 5.2](https://docs.djangoproject.com/en/5.2/)、[Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/)、[WhiteNoise](https://whitenoise.readthedocs.io/en/stable/django.html)、[MDN Window.open](https://developer.mozilla.org/en-US/docs/Web/API/Window/open)。
