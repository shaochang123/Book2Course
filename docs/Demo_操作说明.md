# 智讲 Agent Demo 操作说明

## 提交文件

可直接播放的真实模型产品 Demo 是 `demo/zhijiang_ollama_demo.mp4`，配套来源为 `examples/binary_search_original.pdf`，结构化课程结果为 `demo/zhijiang_ollama_lesson.json`。另提供无需模型的 `demo/zhijiang_demo.mp4` 作为确定性工程演示。提交包由 `scripts/build_submission.py` 生成，内含两项必需材料：产品说明书及独立 AI Coding 附件、产品 Demo 视频。讲义为本届原创内容；主视频的讲稿由本机 Ollama `qwen2.5:7b` 生成，声音来自 Windows 中文系统语音，**不是 AI 配音**。

## 本地网站复现流程

1. 按仓库 README 安装依赖，运行 `python -m uvicorn zhijiang.main:app --host 127.0.0.1 --port 8765`，打开 `http://127.0.0.1:8765`。
2. 上传 `examples/binary_search_original.pdf`，保持“确定性演示模式”与“Windows 中文系统语音”。勾选资料使用权确认并点击“生成一节课”。
3. 观察任务从 PDF 解析、知识提取、课程规划、讲稿与分镜、来源核验、配音直到视频合成。完成后播放 MP4，展开讲稿片段，核对第 1、2 页的原文摘录。
4. 试用“下载 MP4”与“删除本地任务与资料”。删除后原 PDF 与结果从本地任务目录移除。

复制 `.env.local.example` 为 `.env.local`，确认本机 Ollama 运行且装有 `qwen2.5:7b`，重启网站即可选“本机 Ollama 真实 AI 模式”。本机调用不发送资料到外部服务；如果改用远程模型或远程语音服务，页面才会要求额外同意。该模式结果仍需人工检查，切勿把演示模式的确定性脚本描述为真实模型输出。

## 验收记录

开发机：Windows、Python 3.13.9。2026 年 9 月 25 日运行 `python -m pytest`，**18 项通过**。本机 Ollama 真实模式从原创示例生成 3 个讲解片段，页码引文可核对；视频时长 **2 分 21 秒**，1280×720，H.264 视频和 AAC 中文系统语音，FFmpeg 完整解码返回 0。确定性演示另生成 6 段、2 分 13 秒的视频；浏览器视频元素报告该演示视频时长 133.044 秒且已加载。未做线上模型效果声明。

## 提交前核对

- 两项材料都上传：产品说明书（含独立 AI Coding 附件）与产品 Demo。
- AI Coding 工具名称为 OpenAI Codex，其需求、架构、编码、测试、调试和文档用途有独立过程记录。
- 示例 PDF 为本届原创；依赖、FFmpeg 和系统语音来源已列示。
- 演示视频、页面与文字中的“演示模式 / AI 模式 / 系统语音 / AI 配音”标签一致。
- 以赛事平台要求的格式，在 2026 年 10 月 23 日 24:00（中国时间）前完成提交。
