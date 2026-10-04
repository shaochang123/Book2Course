"""Rebuild the aligned, editable bilingual README workflow SVGs."""
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = {
    "zh": {
        "title": "从 PDF 到跨学科教学课件", "subtitle": "来源可追溯 · 场景可扩展 · 配音与画面共用时间线",
        "input": ["01 资料输入", "上传有使用权的 PDF", "选择模型、语音与动画模式"],
        "extract": ["02 内容识别", "提取文字 / 本机 OCR", "保留原文与 PDF 页码"],
        "plan": ["03 教学规划", "独立理解原文，再规划分镜", "图、口播绑定事实；标注类比"],
        "decision": ["选择场景执行路径", "按模式与环境分流"],
        "basic": ["基础图示", "概念 / 公式 / 流程模板", "说明使用基础模式的原因"],
        "verify": ["数学计算核验 · SymPy", "矩阵、向量、投影与面积", "绑定口播，拒绝错误结果"],
        "general": ["按内容选择教学表达", "过程 / 关系 / 比较 / 原图", "定量内容：参数与几何推演", "逐字来源 / 关系 / 计算检查"],
        "render": ["配音与同步渲染", "实际语音时长 → 动作与停顿", "场景：Manim + TeX", "基础：Pillow"],
        "assets": ["同一组教学素材", "SVG 摘要 + 分段 MP4", "来源、讲稿与核验 JSON"],
        "video": ["完整教学 MP4", "合并分段视频与同步配音", "网页播放与下载"],
        "ppt": ["演示用 PPTX", "内嵌 SVG 与原比例 MP4", "来源页码与逐步讲者备注"],
        "yes": "专用线性变换", "no": "basic / 环境回退", "middle": "通用场景 · 学科不限", "failure": "检查失败：修正或报错",
        "foot": "auto：专用或通用场景；visual：通用；math：专用；basic：基础。领域事实和教学质量需对应验收。",
    },
    "en": {
        "title": "From PDF to lessons across subjects", "subtitle": "Source references · Extensible scenes · Shared speech and animation timing",
        "input": ["01 Source input", "Upload a permitted PDF", "Model, voice and mode"],
        "extract": ["02 Content recognition", "Text extraction / local OCR", "Keep excerpts and page refs"],
        "plan": ["03 Teaching plan", "Read source before planning", "Bind visuals/speech to facts"],
        "decision": ["Choose scene executor", "Mode and environment"],
        "basic": ["Basic diagrams", "Concept / formula / process", "Explain the selected fallback"],
        "verify": ["Math checks · SymPy", "Products / area / projections", "Bind speech; reject bad math"],
        "general": ["Teaching representation", "Process / relations / source", "Quantitative: geometry steps", "Source, relation, math checks"],
        "render": ["Narration and rendering", "Speech cues → motion", "Scenes: Manim + TeX", "Basic: Pillow"],
        "assets": ["Shared teaching assets", "SVG summary + narrated MP4", "Sources, scripts, check JSON"],
        "video": ["Full lesson MP4", "Join clips with narration", "Web playback and download"],
        "ppt": ["Presentation PPTX", "SVG and original-ratio MP4", "Page refs and speaker notes"],
        "yes": "Linear transformations", "no": "Basic / env fallback", "middle": "General / any subject", "failure": "Failed checks: revise or fail",
        "foot": "auto: specialist/general; visual: general; math: specialist; basic: basic. Validate domain facts and teaching quality.",
    },
}


def build(language):
    words = COPY[language]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1010" viewBox="0 0 1200 1010" role="img" aria-labelledby="title desc">',
             f'<title id="title">{escape(words["title"])}</title><desc id="desc">{escape(words["subtitle"]+". "+words["foot"])}</desc>',
             '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 Z" fill="#6EE1CD"/></marker></defs>',
             '<rect width="1200" height="1010" fill="#091723"/>']
    def text(x, y, value, size=18, color="#D4E6EB", anchor="start"):
        parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-family="Microsoft YaHei,Arial,sans-serif" font-size="{size}" text-anchor="{anchor}">{escape(value)}</text>')
    def arrow(path):
        parts.append(f'<path d="{path}" fill="none" stroke="#6EE1CD" stroke-width="2.8" stroke-linejoin="round" marker-end="url(#arrow)"/>')
    def box(key, x, y, height=110):
        parts.append(f'<rect x="{x}" y="{y}" width="280" height="{height}" rx="12" fill="#183947" stroke="#58A99F" stroke-width="1.5"/>')
        for i, line in enumerate(words[key]):
            text(x+16, y+29+i*25, line, 21 if i==0 else 17, "#6EE1CD" if i==0 else "#D4E6EB")
    text(45, 53, words["title"], 31, "#F4FAFD")
    text(45, 84, words["subtitle"], 17, "#ADC2CD")
    box("input",45,130); box("extract",460,130); box("plan",875,130)
    arrow("M 325 185 H 460"); arrow("M 740 185 H 875")
    arrow("M 1015 240 V 270 H 600 V 300")
    parts.append('<path d="M 600 300 L 775 365 L 600 430 L 425 365 Z" fill="#102A36" stroke="#58A99F" stroke-width="2"/>')
    text(600,358,words["decision"][0],19,anchor="middle")
    text(600,385,words["decision"][1],19,anchor="middle")
    arrow("M 425 365 H 185 V 485"); text(210,344,words["no"],16,"#ADC2CD")
    arrow("M 775 365 H 1015 V 485"); text(875,344,words["yes"],16,"#ADC2CD")
    arrow("M 600 430 V 485"); text(620,465,words["middle"],16,"#ADC2CD")
    box("basic",45,485,135); box("verify",875,485,135); box("general",460,485,135)
    arrow("M 185 620 V 660 H 540 V 695"); arrow("M 1015 620 V 660 H 660 V 695")
    arrow("M 600 620 V 695")
    box("render",460,695,135)
    text(1015,688,words["failure"],16,"#F2AC99",anchor="middle")
    arrow("M 600 830 V 855")
    box("assets",460,855); box("video",45,855); box("ppt",875,855)
    arrow("M 460 910 H 325"); arrow("M 740 910 H 875")
    text(45,992,words["foot"],16,"#ADC2CD")
    parts.append('</svg>')
    (ROOT/'docs'/f'workflow.{language}.svg').write_text('\n'.join(parts)+'\n',encoding='utf-8')


if __name__ == "__main__":
    for language in COPY:
        build(language)
