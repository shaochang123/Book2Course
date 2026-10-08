# 演示与复现操作说明

当前入口见[使用指南](使用指南.md)，实测证据见[验证与验收](验证与验收.md)。`demo/` 中的已有视频为九月首版输出，不代表当前图示、OCR 或泛化效果；本轮文档整理不重建这些媒体。

## 1. 当前网页演示

1. 从仓库根目录启动 `python -m uvicorn zhijiang.main:app --host 127.0.0.1 --port 8765`。
2. 打开网页，上传 `examples/binary_search_original.pdf`，选择演示模式和系统语音，确认资料使用权。
3. 观察进度、完成后的课程目标与逐段讲稿，展开原文页码和摘录。
4. 播放视频，下载 MP4 和 PPTX，核对讲者备注和来源。
5. 真实 AI 演示需要先启动本机模型并填入实际模型名；可用 `auto` 展示当前按内容规划的图示。
6. 使用真实发生的失败任务展示错误和“使用原 PDF 重新生成”；不制造假的成功或审核记录。
7. 演示本地删除和终端 `Ctrl+C` 关闭服务。

当前不演示项目列表、知识点编辑、讲稿修改或人工审核，因为没有这些操作入口。参考文档 UI 是设计示意，不能用作运行截图。

## 2. 原创样例重新生成

```powershell
.\.venv\Scripts\python scripts\generate_sample_pdf.py
.\.venv\Scripts\python scripts\build_demo.py
.\.venv\Scripts\python scripts\build_ollama_demo.py
```

第一个命令重建原创 PDF；第二个使用确定性规则；第三个调用当前本机 Ollama。运行前确认模型配置与系统中文语音。脚本会覆盖 `demo/` 对应文件；更新这些文件后要记录实际模型、提交、来源和媒体检查，不沿用九月时长。

九月已有 `zhijiang_ollama_demo.mp4` 的文本由 `qwen2.5:7b` 生成，配音为 Windows 系统语音，4 段、约 3 分 18 秒。备用 `zhijiang_demo.mp4` 为确定性规则，6 段、约 2 分 13 秒。历史细节见[归档操作说明](archive/2026-09/Demo_操作说明.md)。二者不标称 AI 配音。

## 3. 不预写分镜的教材验证

根据[来源清单](../examples/holdout-sources.json)取得相同版本、核对哈希，保存到忽略提交的 `data/holdout/`。使用空提示词运行生产模块：

```powershell
.\.venv\Scripts\python -m scripts.verify_textbook_generalization --pdf data\holdout\linguistics.pdf --pages 172,173,175 --output data\holdout\linguistics-verify --model qwen3.5:9b --no-thinking --render
```

该命令使用实际已安装的本机模型和系统配音。其他三领域页码、命令、失败记录、缓存协议与教学缺陷见[教材验证](generalization-validation-2026-10.md)。它检验选页的模型/渲染链路，不检验网页队列，也不是整书或独立盲测。

## 4. 技术检查与录屏

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\verify_teaching_artifacts.py --job-dir data\jobs\你的任务ID
```

录屏从真实页面开始。长生成过程可剪辑等待时间，但保留任务 ID、模式、模型和实际状态，并注明剪辑。展示输入、讲稿、页码、真实视频播放与下载；把技术检查、人工内容复核、未测试项分别说明。不要把开发者预写的场景用于声称模型对未知教材的泛化。

## 5. 当前文档与历史包

```powershell
.\.venv\Scripts\python scripts\build_documents.py
```

导出当前项目说明到 `output/pdf/`。文档源文件为[产品说明书](产品说明书.md)，不调用模型、不生成课程。

九月 `submission/` 包保持历史版本。旧 `build_submission.py` 固定读取归档说明与九月媒体，不作为当前发布入口，见[归档说明](archive/2026-09/README.md)。
