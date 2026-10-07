# 教材泛化验证记录（2026-10-08）

本记录检查从真实教材内容自动规划图示的效果。开发者预写的微积分、概率、力学、化学、生物、线性变换与二分查找分镜不作为本次泛化证据。

## 资料与选择方法

固定原始 PDF 页码，再运行模型；没有根据成功结果更换页码。下表页码指 PDF 文件中的物理页码。书目、下载地址、许可页与 SHA-256 保存在 [holdout-sources.json](../examples/holdout-sources.json)。

| 领域 | 教材与来源 | 作者及版本 | PDF 页码 | 验证内容 |
| --- | --- | --- | --- | --- |
| 语言学 | [Essentials of Linguistics](https://openlibrary-repo.ecampusontario.ca/jspui/handle/123456789/497) | Catherine Anderson，McMaster，2018 | 172、173、175 | 构成成分、替换测试、树状图与证据 |
| 经济学 | [Principles of Microeconomics (UVic)](https://openlibrary-repo.ecampusontario.ca/jspui/handle/123456789/355) | UVic，改编自 OpenStax，2017 | 18、19、20 | 机会成本、显性与隐性成本、次优选择 |
| 社会学 | [Introduction to Sociology – 2nd Canadian Edition](https://openlibrary-repo.ecampusontario.ca/jspui/handle/123456789/316) | William Little，BCcampus，2016 | 212、213、214 | 社会自我、社会化阶段、概化他人 |
| 数据库设计 | [Database Design – 2nd Edition](https://openlibrary-repo.ecampusontario.ca/jspui/handle/123456789/247) | Adrienne Watt、Nelson Eng，BCcampus，2014 | 72、73、74 | 规范化、范式及教材中的表拆分示例 |

前三本用于发现并修复缺陷，因此复验不能当成未接触过的盲测分数。第四本在通用短语及关系校验完成后加入，首次运行从空输出目录开始，也揭示了原文定位问题；因此四本最终都参与了调试，不能把最终成绩称为独立盲测。后续针对原始引文覆盖的检查统一复验四本资料，只复用符合新增检查的模型场景。没有为任何一本教材加入概念词表、绘图分支、坐标、答案或专属提示词。

原始 PDF 和全部生成物留在忽略提交的 `data/holdout/`。语言学 PDF 许可页为 CC BY-SA 4.0；社会学为加拿大新增内容 CC BY 4.0、原 OpenStax 内容 CC BY 3.0；数据库设计为 CC BY 4.0，均有例外条款。数据库原页的再分发署名还要求保留 “Download this book for free at http://open.bccampus.ca”。经济学仓库摘要与所下载 PDF 的许可标注不一致：PDF 第 3 页写 CC BY 4.0。以上许可核对来自具体下载版本，不能替代对书中第三方图片的核查；本次未将教材及其改编课件推送到仓库。

## 实际运行协议

- Windows、Python 3.13、Manim 0.21.0、Ollama 0.34.4，使用已安装的 imageio-ffmpeg 和 TeX Live。
- 最终模型 `qwen3.5:9b`，本机模型摘要 `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`；通过服务声明的开关关闭可选思考。没有调用云端模型。
- 使用 Microsoft Huihui Desktop 系统配音，是真实有声视频；不标称为 AI 配音。
- `scripts/verify_textbook_generalization.py` 使用生产模块：PDF 提取 → 模型知识点提取 → 课程排序 → 独立来源理解 → 独立命题读取 → 表达设计 → 逐步讲稿 → 整页含义审稿 → SVG/Manim → 配音 → MP4/PPTX。
- 输入提示词始终为空。脚本不提供主题、例子、节点、命题、坐标、SVG 或分镜。设计模型只选择独立来源命题编号，程序构建图中的端点与谓词。
- 前三本复验只复用模型生成的知识点与独立来源理解草稿，每个目录的 `reused-inputs.json` 列出文件；没有复用已批准场景、命题、讲稿或动画。命题、设计和审稿重新运行。
- 新增引文覆盖检查后的续跑记录在 `resume-protocol.json` 与 `*-v7-focus.log`。此前媒体结果保存在 `pre-citation-focus/`；本次统一重查缓存，只复用满足新检查的场景，自动重做遗漏当前引文的片段。数据库第一次完整运行没有输入缓存；续跑会复用其模型知识点、独立来源草稿及仍合格的场景。
- 每次实际输入记录在 `input.json`；保存原文、知识点、未通过的候选、来源命题、逐项审稿、模型错误及调用指标。中断迭代不计为通过或失败。

这里测试的是选定原页的生产模块链路，不是整本书覆盖率，也没有用这个脚本测试网页上传队列或 PowerPoint 放映操作。

## 实际发现与通用修复

1. **原有自动模式可能把整份教材路由到专用模板。** 自动模式现在保留已提取主题，逐点选择通用表达；二维线性变换模板通过 `math` 显式选择。基础模式也移除了仅凭“概率”等关键词推导专属图形的分支。
2. **节点共现、句子顺序不能证明关系。** 来源命题先于设计独立提取，保留主语、谓词、宾语和事实编号；程序要求连线匹配该命题。被动句和跨句表述可以保留多条事实、否定和完整条件。图布局依据实际方向、分支及循环，SVG 与视频共享布局。
3. **相同模型审稿可能批准错误关系。** 初次社会学视频曾把共同开创某研究传统画成一位学者开创另一位学者。经济学也出现过把活动当成其成本的关系。来源定位和媒体生成通过不代表这些内容合格。现在还展开实际显示的三元断言给审稿模型，身份关系进行保守的句法顺序检查；无可信命题时使用原页注释并保留含义检查。
4. **字体变化会破坏例句。** 语言学 PDF 的普通提取曾拼接或遗漏字体变化处的词语；改用 pypdf 的 [位置提取模式](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)，重新解析并使旧缓存失效。没有用英语单词字典修补教材。
5. **强制中文和过短的字段会制造截断短语。** 节点可以保留原语言，名称长度扩展；英文按整词换行，文字按卡片尺寸缩放。悬空功能词、截断列表、未解析代词和省略号谓词被拒绝。复杂短语可在原页上作注释，不强行成为图实体。
6. **小模型和输出预算的限制可重现。** `qwen2.5:7b` 初次语言学与社会学视频能完成渲染，但人工检查发现内容错误；经济学出现无来源的数值。`qwen3.5:9b` 开启思考时曾达到来源理解的结构化输出预算，关闭可选思考另行记录，不能把这两种设置混作同一成绩。
7. **数值与缓存不能绕过校验。** 文字型 PDF 也检查新增数值，来源问题在设计前记录；批准绑定节点、关系、条件与口播的摘要，修改设计不能沿用旧批准。几何 JSON 契约失败经过有限修正后重新设计，原生关系图不依赖 TeX。
8. **同页正确规则仍可能遗漏当前反例。** 语言学“替换失败”片段曾只讲替换规则，社会学阶段与数据库 1NF 也出现核心引文未进入讲稿的情况。新增基于实际原始引文的事实覆盖要求，应用于所有领域及缓存；不靠教材标题或关键词指定反例。不能表示核心事实时重新设计为原页注释。未能文本匹配的引文仍需人工核对。
9. **分支布局可能误导读者。** 数据库规范化图中，水平分支的谓词曾被抬到另一条斜线上。布局现在根据实际箭头间距放置标签，宽间距谓词靠近对应箭头，SVG 和 Manim 共用修复。
10. **整体概念与具体字段的定位可能混淆。** 数据库续跑被审稿拒绝：中文“课程信息”错误定位到 `CourseNo`。新原页注释使用完整摘录作为位置与含义依据；原文直接出现的名称才精确定位到名称。没有把原拒绝改成批准，仍重新审核标注是否由完整来源支持。失败保存在 `citation-focus-failure.json`，修复续跑见 `database-v7-anchor.log`。
11. **真实长标签触发 PNG 兼容错误。** 语言学新标注的自适应字号为小数，PNG 兼容绘制器原先只接受整数字符串。现在读取有效小数字号并转换为像素字号，补充实际 PNG 渲染回归。原错误保存在 `citation-render-failure.json`，续跑见 `linguistics-v7-render.log`。

## 验收方法

`validation.json` 检查真实视频解码、H.264/AAC、非静音、音画时长、1280×720/30fps、逐步焦点与渲染几何、SVG/PNG 画布、PPTX 内嵌素材字节及备注对应口播。`validation-contact.png` 从每段实际视频抽取开始、中间与结束帧，用于人工查看。媒体脚本明确记录没有进行人工听辨、专业事实复核或 PowerPoint 放映验收。

`result.json` 的 `passed` 只表示上述生产契约和媒体检查通过，不能作为教学质量评分。人工检查还需把最终节点、关系、例子及讲稿回查原页；回退为原页高亮时，也不能标称为机制模拟。

### 最终运行结果

最终目录为 `data/holdout/{领域}-v7/`。四本都完成有声 MP4、SVG 与 PPTX，全部通过媒体/生产契约检查。以下为实际结果，不计中断迭代，也不以初次已能生成视频作为内容通过的依据。

| 领域 | 片段 / SVG | 关系图 | 流程图 | 原页讲解 | MP4 时长 | PPTX 页数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 语言学 | 5 | 2 | 0 | 3 | 141.767 秒 | 11 |
| 经济学 | 6 | 2 | 0 | 4 | 135.933 秒 | 13 |
| 社会学 | 6 | 1 | 1 | 4 | 156.933 秒 | 13 |
| 数据库设计 | 5 | 3 | 0 | 2 | 98.967 秒 | 11 |

合计 22 张 SVG、22 段带配音的动画、4 个完整视频、4 份课件。实际解码均为 H.264/AAC、1280×720、30fps，音画时长差小于 0.03 秒，音轨非静音；课件素材字节与独立片段一致，备注对应实际口播。14 段是原页高亮讲解，不算领域机制模拟；没有生成手工预写的案例动画，也没有把章节标题当作领域绘图路由。

### 人工查看结论

人工查看了四张完整视频抽帧联系表、对应 SVG 和讲稿，并回查所选原页。文字能够按卡片缩放，英文换行未截断单词；规范化的分支标签已靠近正确箭头。重新规划的片段保留了匹配到原始引文的事实。

**教学质量只部分通过，不能把上述 4/4 媒体通过称为教学质量 4/4。** 仍看到以下问题：

- 语言学替换测试关系图使用了 `that string`、`this replacement` 等句内指代和条件短语，缺少清楚的具体例句对象；“替换失败”讲稿把原例句的一部分误读为 `their is`。例句教学的含义验收未通过，模型审稿存在假阳性。
- 经济学“机会成本定义”主要解释隐性成本；社会学“四阶段概述”聚焦游戏阶段；数据库“1NF 定义”主要展示重复组示例。核心引文被覆盖仍不足以证明标题所称的完整范围。
- 原页缩略图和高亮可以保留出处，但小字需要放大或查看源文件。数据库没有生成可逐字段追踪表拆分的动画，社会学也没有角色扮演的实体模拟。
- 没有进行人工逐句听辨或 PowerPoint 放映验收；非静音和备注对应只验证了媒体链路。

这些问题保留在最终输出与报告中，没有人工替换模型讲稿或伪造“全部合格”的统计。后续需要单独加强外文例句保真、知识点标题与引文的范围一致性及复杂机制表示，再用新的资料验证；本轮结果证明来源驱动流程可以处理这些新领域，不能证明自动讲课已达到成品课程质量。

### 自动回归结果

最终执行 `python -m pytest -o addopts='' -q`：**206 passed，1 warning，14.18 秒**；完整日志保存到 `data/final-tests.log`。警告来自 Starlette TestClient 的 httpx 弃用提示，没有失败测试。新增回归覆盖未知实体、跨句与被动关系、条件与否定、节点角色、批准摘要、分支/循环布局、外文名称、PDF 字体切换、数值来源、缺失主题引文、标注定位与实际小数字号 PNG 渲染。

## 重现

先按清单中的 `pdf_url` 下载相同版本到 `data/holdout/`，核对哈希。安装 `.venv` 对应的测试与动画依赖，并启动本机 Ollama。

```powershell
.\.venv\Scripts\python -m pip install -e ".[test,math-animation]"
.\.venv\Scripts\python -m scripts.verify_textbook_generalization --pdf data\holdout\linguistics.pdf --pages 172,173,175 --output data\holdout\linguistics-verify --model qwen3.5:9b --no-thinking --render
.\.venv\Scripts\python -m scripts.verify_textbook_generalization --pdf data\holdout\economics.pdf --pages 18,19,20 --output data\holdout\economics-verify --model qwen3.5:9b --no-thinking --render
.\.venv\Scripts\python -m scripts.verify_textbook_generalization --pdf data\holdout\sociology.pdf --pages 212,213,214 --output data\holdout\sociology-verify --model qwen3.5:9b --no-thinking --render
.\.venv\Scripts\python -m scripts.verify_textbook_generalization --pdf data\holdout\database.pdf --pages 72,73,74 --output data\holdout\database-verify --model qwen3.5:9b --no-thinking --render
.\.venv\Scripts\python -m pytest -o addopts='' -q
```

输出文件包括 `lesson.mp4`、`lesson.pptx`、`lesson.json`、每段 `summary.svg`、`summary.png`、`clip.mp4` 与来源/审稿诊断。不同模型及服务版本可能产生不同设计；首次运行不包含本机已经生成的草稿缓存，耗时也会不同。

## 可得出的结论与边界

程序不再需要为这些教材补写学科分支；关系、条件与布局由当前来源数据组织。重复修复同一批开发资料仍可能产生适应效应，四本选页不足以证明任意教材泛化。来源语义理解和审稿依赖模型，复杂外语、表格、原图、专业符号与教材自身错误仍需人工复核。原页高亮、关系追踪和可计算机制演示是不同的能力；报告按实际输出记录，不把原页高亮算作机制推演。
