# 扩展学科教材 Benchmark v2

保留 [v1](../textbooks_v1/README.md) 的 24 项实测结果。本套新增 8 个学科／学段，每个 2、6、12 页 × 原生文字／纯图像 PDF，共 48 项：初中数学、高中数学、大学数学、语文诗词赏析、英语语法、化学、生物、物理。

七份外部公开教材保留原页图形、公式和习题；语文为公版唐诗与原创赏析组成的补充读本，明确区别于出版社教材。数学主题选相似多边形、三角形解法和中值定理，避开此前角度、分数、勾股、抛物线、对数、泰勒和极坐标测试。选页仍有不同教材版本、源书错误和跨章节边界，记录在本地介绍中。

评价答案不传给 Agent，也不人为编排模型的图形和分镜。先冻结 `spec.json`、`rubric.json`，再用真实生产流程、本机 Ollama 和系统语音测试。禁止 DeepSeek；默认本地模型，经用户授权的公开选页云模型对照须显式添加 `--allow-ollama-cloud`，使用独立结果目录并保留实际远程标记。输入、计量、实际视频帧、失败记录及修复后复测均放在 Git 忽略的 `data/` 中。

```powershell
.venv\Scripts\python.exe scripts/build_poetry_reader.py
.venv\Scripts\python.exe scripts/benchmark_textbooks.py prepare --suite benchmarks/textbooks_v2 --root data/textbook-benchmark-v2
.venv\Scripts\python.exe scripts/benchmark_textbooks.py run --suite benchmarks/textbooks_v2 --root data/textbook-benchmark-v2
.venv\Scripts\python.exe scripts/benchmark_textbooks.py package --suite benchmarks/textbooks_v2 --root data/textbook-benchmark-v2 --include-media
```

语文源 PDF 先按上面命令生成，其余按固定 SHA-256 下载。CC 授权书籍不改为项目 MIT 许可；CK-12 署名与 `http://www.ck12.org/saythanks`、原图署名随审阅包保留。NC 素材用于非商业本地评估。

生成完成、关键词出现、SVG 数量和像素变化均不能证明知识与学科动画正确。人工需核对来源、条件、数字、例句、诗中事实与解释、图形对象及变化。首次结果与实际改进后的重新生成分开；不得把恢复导出当作内容修复。测量过程中不修改生产代码或并行占用模型。
