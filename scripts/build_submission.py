"""把说明书、独立 AI Coding 报告和 Demo 打成可审阅的参赛材料包。"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "submission"
FONT = Path("C:/Windows/Fonts/simhei.ttf")


def inline_markdown(value: str) -> str:
    value = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r"\1（\2）", value)
    value = value.replace("**", "").replace("`", "")
    return escape(value)


def export_pdf(source: Path, target: Path) -> None:
    if not FONT.is_file():
        raise SystemExit("导出参赛 PDF 需要本机 Windows 黑体字体。")
    pdfmetrics.registerFont(TTFont("SimHeiSubmission", str(FONT)))
    base = dict(fontName="SimHeiSubmission", textColor=colors.HexColor("#173344"),
                alignment=TA_LEFT, wordWrap="CJK", spaceAfter=9)
    styles = {
        "title": ParagraphStyle("title", fontSize=22, leading=32, spaceBefore=4,
                                spaceAfter=25, textColor=colors.HexColor("#0A534D"), **{k: v for k, v in base.items() if k not in ("spaceAfter", "textColor")}),
        "section": ParagraphStyle("section", fontSize=15, leading=23, spaceBefore=21,
                                  spaceAfter=12, keepWithNext=True,
                                  textColor=colors.HexColor("#0A7767"),
                                  **{k: v for k, v in base.items() if k not in ("spaceAfter", "textColor")}),
        "body": ParagraphStyle("body", fontSize=10.3, leading=18, **base),
        "bullet": ParagraphStyle("bullet", fontSize=10.2, leading=18, leftIndent=15,
                                 firstLineIndent=-12, **base),
        "code": ParagraphStyle("code", fontSize=9.4, leading=15, leftIndent=12,
                               backColor=colors.HexColor("#EAF3F0"), **base),
    }
    story = []
    in_code = False
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code = not in_code
            story.append(Spacer(1, 5))
            continue
        if not line:
            story.append(Spacer(1, 5))
            continue
        if in_code:
            story.append(Paragraph(inline_markdown(line), styles["code"]))
        elif line.startswith("# "):
            story.append(Paragraph(inline_markdown(line[2:]), styles["title"]))
            story.append(HRFlowable(width="100%", thickness=1.3, color=colors.HexColor("#74CDB2")))
            story.append(Spacer(1, 10))
        elif line.startswith("## "):
            story.append(Paragraph(inline_markdown(line[3:]), styles["section"]))
        elif line.startswith("- "):
            story.append(Paragraph("• " + inline_markdown(line[2:]), styles["bullet"]))
        elif re.match(r"^\d+\. ", line):
            story.append(Paragraph(inline_markdown(line), styles["bullet"]))
        else:
            story.append(Paragraph(inline_markdown(line), styles["body"]))

    def decorate(canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(colors.HexColor("#B8D3CE"))
        canvas.line(48, height - 46, width - 48, height - 46)
        canvas.setFont("SimHeiSubmission", 8.7)
        canvas.setFillColor(colors.HexColor("#58757A"))
        canvas.drawString(48, height - 37, "智讲 Agent  /  Book2Course")
        canvas.drawRightString(width - 48, 37, f"第 {doc.page} 页")
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(target), pagesize=A4,
        leftMargin=52, rightMargin=52, topMargin=65, bottomMargin=58,
        title=source.stem, author="智讲 Agent 项目组",
    )
    document.build(story, onFirstPage=decorate, onLaterPages=decorate)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    mapping = {
        "01_智讲Agent_产品说明书.pdf": ROOT / "docs" / "产品说明书.md",
        "01A_智讲Agent_AI_Coding全过程.pdf": ROOT / "docs" / "AI_Coding_全过程.md",
        "附件_演示操作说明.pdf": ROOT / "docs" / "Demo_操作说明.md",
        "附件_第三方来源与许可.pdf": ROOT / "docs" / "第三方来源与许可.md",
    }
    for filename, source in mapping.items():
        export_pdf(source, OUT / filename)
    demo = ROOT / "demo" / "zhijiang_ollama_demo.mp4"
    lesson = ROOT / "demo" / "zhijiang_ollama_lesson.json"
    fallback = ROOT / "demo" / "zhijiang_demo.mp4"
    sample = ROOT / "examples" / "binary_search_original.pdf"
    if not all(path.is_file() for path in (demo, lesson, fallback, sample)):
        raise SystemExit("缺少原创样例或 Demo；请先运行两个 Demo 生成脚本。")
    checklist = (
        "智讲 Agent 参赛材料清单\n"
        "一、产品说明书：01_智讲Agent_产品说明书.pdf；AI Coding 全过程为独立附件。\n"
        "二、产品 Demo：02_智讲Agent_产品Demo_AI文本生成.mp4；原创来源为附件_原创演示讲义.pdf。\n"
        "模型讲稿与引文为附件_课程与来源.json；另附无需模型的确定性演示视频。\n"
        "补充：演示操作说明、第三方来源与许可。\n"
        "主 Demo 的文本由本机 Ollama qwen2.5:7b 生成，视频使用 Windows 系统语音，不标称 AI 配音。\n"
        "备用演示内容由确定性规则生成，不标称 AI 生成。\n"
        "提交截止：2026-10-23 24:00（中国时间），以赛事平台显示为准。\n"
    )
    archive = OUT / "智讲Agent_参赛材料.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as package:
        for filename in mapping:
            package.write(OUT / filename, filename)
        package.write(demo, "02_智讲Agent_产品Demo_AI文本生成.mp4")
        package.write(lesson, "附件_课程与来源.json")
        package.write(fallback, "附件_确定性演示视频.mp4")
        package.write(sample, "附件_原创演示讲义.pdf")
        package.writestr("README_提交清单.txt", checklist)
    print(archive)
    for name in mapping:
        print(f"{name}: {(OUT / name).stat().st_size} bytes")
    print(f"ZIP: {archive.stat().st_size} bytes")


if __name__ == "__main__":
    main()
