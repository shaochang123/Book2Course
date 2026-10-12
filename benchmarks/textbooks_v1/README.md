# 教材 Benchmark v1

使用真实生产流程测试多领域教材，不提供专用讲稿、图形坐标或预先选好的素材。

## 测试矩阵

| 领域 | 教材选章 | 原 PDF 起始页 | 页数 | 输入类型 |
| --- | --- | ---: | --- | --- |
| 计算机与数据库 | Database Design：实体关系模型 | 39 | 2、6、12 | 文字、纯图像 |
| 地质学 | Physical Geology：应力、应变、褶皱与断层 | 416 | 2、6、12 | 文字、纯图像 |
| 心理学 | Beginning Psychology：经典与操作性条件作用 | 340 | 2、6、12 | 文字、纯图像 |
| 商业管理 | Fundamentals of Business：定价与产品生命周期 | 323 | 2、6、12 | 文字、纯图像 |

共 24 个案例。原书均为英文，输出使用中文。页码为原 PDF 的物理页序号；选页内仍保留原版印刷页码。图像版来自对应文字版，180 DPI、JPEG 85，没有隐藏文字层。它是清晰的模拟扫描，不能代表拍照、污渍、手写和严重倾斜。

来源、许可、原书 SHA256、选页、配置在 [spec.json](spec.json)。数据库教材曾在旧验收中测试过其他章节，本轮采用新的实体关系章节；另外三本书为本轮新输入。未声称模型训练数据从未出现这些公开教材。

## 运行

```powershell
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python scripts/benchmark_textbooks.py prepare
.\.venv\Scripts\python scripts/benchmark_textbooks.py run
.\.venv\Scripts\python scripts/benchmark_textbooks.py audit
.\.venv\Scripts\python scripts/benchmark_textbooks.py recover
.\.venv\Scripts\python scripts/benchmark_textbooks.py report
.\.venv\Scripts\python scripts/benchmark_textbooks.py package
.\.venv\Scripts\python scripts/benchmark_textbooks.py package --include-media
```

需要本机 Ollama 和 Windows 中文系统语音。默认读取环境中的本机模型，拒绝远程配置及云模型标签，不调用 DeepSeek API。所有案例统一关闭可选深度推理，以 `auto`、`warn`、`academic`、自动配图和系统语音完成生成。原始语音、图片、PPT、完整视频均正常产生，未使用测试配音或模拟模型。

`prepare` 下载匹配指纹的公开版本，制作成对选页并验证文字层。原书下载总量约 326 MiB，请保留 `data/textbook-benchmark/sources/` 以供复用。`run` 为每个案例创建新任务；再次运行会跳过已经测过的案例，继续未完成项。`--cases database-02-text,database-02-ocr` 可选子集，`--model` 可指定实际本机标签。改变模型、配置或应用提交应使用新的 `--root data/另一个运行目录`。不要并发运行同一目录，也不要在生成途中修改应用代码。

`audit` 重新检查保留的生成物，更新媒体指标，不重新调用模型或更改首次生成状态。`package` 提供轻量输入与结果 ZIP；`--include-media` 另生成包含最终 PPT/MP4 的完整复查 ZIP，保持 HTML 媒体链接可用。两种包均不收录模型请求记录、数据库、密钥或大体积完整原书。

修复应用中的导出故障后，`recover` 会使用失败任务保留的课程和原始配音，在独立的 `recoveries/` 目录重新导出，不调用模型或语音服务，也不修改首轮状态。没有完整课程或音频的任务标为无法仅靠导出恢复。若上次在单个任务中途被中断且没有测量结果，脚本拒绝把重跑伪装成首次尝试；保留该目录并使用新目录进行完整运行。

生产流程不设置生成 token 或总时长上限；2、6、12 页是测试样本规模。运行期间固定应用版本，避免把修复前后结果混成一个成功率。外层首次失败仍记为失败，恢复或再次尝试另列。

## 验收与解释

- **工程**：解析页数和 OCR 标志、完整生成状态、模型调用及 token、各阶段耗时、PPT ZIP/SVG、备注、外框、视频和音频解码、PPT 与实际视频帧一致性。
- **教学**：[rubric.json](rubric.json) 的锚点关键词只检测提及，不能判定事实、单位、条件或连线正确。人工抽查原文、口播和实际视频帧另行记录。
- **OCR**：相对文字版提取结果的词项 F1 是辅助相似度指标，忽略语序；参考提取本身也可能拼接单词，不能直接称为识别准确率。
- **动画**：记录逐步呈现与实际画面变化；这些指标不能证明连续数学/物理模拟正确。本轮为普通直接生成模式。

每个样本只运行一次外层生成，内部模型修复调用计入耗时和 token，输出审计耗时另列。任务不复用课程检查点，但模型驻留、OCR 权重和文件缓存可能复用，不能视为全冷启动；未控制热状态和其他系统负载。没有据此计算 pass@3、重复稳定性或所有教材的成功概率；配对与嵌套页数也并非相互独立的随机样本。人工抽查需注明检查了哪些口播和实际视频帧；同一评估者查阅原文与输出，不是独立盲评。

## 本机交付与许可

结果位于 Git 忽略的 `data/textbook-benchmark/`：`INTRODUCTION.md`、`REPORT.md`、`REPORT.html`、`results.csv`、`results.json`、人工抽查、输入集 ZIP 及每项生成物。原始状态、模型记录和首次失败会保留。

测试为非商业评估。各书与衍生选页保留原始许可和署名，不改为项目 MIT 许可；教材图片中另有许可的内容以原书注明为准。版本化源码只包含公开定义、来源清单和测试代码，不含教材 PDF、生成结果、模型记录、缓存或密钥。
