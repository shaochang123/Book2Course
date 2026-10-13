"""Reproducible Chinese reader: public-domain poems and original reading notes.

This is an authored supplemental reader, not a commercially published textbook.
These notes are input material; benchmark grading anchors live in another file.
"""
from pathlib import Path
import argparse

POEMS = [
    ('鹿柴', '王维', ['空山不见人，但闻人语响。', '返景入深林，复照青苔上。'],
     '诗中的观察顺序从听觉转到视觉。前两句不见人却听见人语，人的声音没有把山林写成热闹场所，反而让空山的幽静更具体。这里的“不见”只限定眼前所见，不能据此断言山中无人。',
     '后两句写夕阳的光进入深林，照到青苔。“返景”可理解为夕照的光，不是青苔反射出的光。赏析可沿“人声—林光—青苔”的视角移动，辨认声音与局部亮色怎样衬托幽静；不能把这种阅读理解说成诗人有意进行光学实验。'),
    ('山居秋暝', '王维', ['空山新雨后，天气晚来秋。', '明月松间照，清泉石上流。', '竹喧归浣女，莲动下渔舟。', '随意春芳歇，王孙自可留。'],
     '首联设置雨后、秋日、傍晚的情境。颔联并列写月光与清泉：月光穿过松间，泉水流过石上。动静结合来自这些具体景物，不能把月光画在水下、把泉流解释为降雨仍未停止。',
     '颈联先写竹林喧声、莲叶摇动，再让浣女和渔舟出现，读者由声响和变化理解人的活动。尾联表达愿意停留的态度；“春芳歇”与眼前秋景形成联系。赏析应区分诗中动作和读者想象，不能添造浣女与渔人之间的对话。'),
    ('枫桥夜泊', '张继', ['月落乌啼霜满天，江枫渔火对愁眠。', '姑苏城外寒山寺，夜半钟声到客船。'],
     '前两句把月落、乌啼、霜意、江枫和渔火组织成夜泊所见所闻，中心是客船中难眠的旅人。可以分析冷色景物与渔火亮色的并置，但“霜满天”属于诗意表达，不能当作天空悬浮着大量冰霜颗粒的科学描述。',
     '后两句从视觉与近处声响转向远寺钟声。钟声到达客船，不是客船向寺庙发声。“愁”由原诗明确给出，但具体愁事没有交代；可以提出羁旅情绪的阅读解释，不应虚构家人离世等确定原因。'),
    ('江雪', '柳宗元', ['千山鸟飞绝，万径人踪灭。', '孤舟蓑笠翁，独钓寒江雪。'],
     '前两句用“千山”“万径”打开广阔空间，又用“绝”“灭”写鸟与人踪的缺席。后两句收束到孤舟与垂钓者，形成从大环境到小人物的构图。“千”“万”是诗歌中的概括，不能逐字画成固定一千座山、一万条路。',
     '“孤”“独”反复凸显人物处境，蓑衣、斗笠和寒江提供具体形象。可讨论清寒、孤寂以及人物独立的意味，但诗中没有给出鱼的数量，也没有写老人垂钓成功。人物形象与作者心境的联系是一种阐释，不能把垂钓者直接确认为作者的自画像。'),
    ('春望', '杜甫', ['国破山河在，城春草木深。', '感时花溅泪，恨别鸟惊心。', '烽火连三月，家书抵万金。', '白头搔更短，浑欲不胜簪。'],
     '开篇以山河仍在和国事破败形成对照，春草茂盛没有单独带来欢快。颔联把花、鸟和感时恨别联系起来：自然景物进入诗人的情感观察，而不是花具有人的生理泪腺、鸟遭遇了同一段离别。',
     '颈联由时局转到音讯，家书珍贵的原因与战乱中的隔绝有关。“抵万金”是价值的夸张，不是实际兑换价格。尾联用搔首、白发难以承簪的细节收束忧思。讲解应保留时局、离别、个体形象之间的层次，不能把全诗概括成普通的春游观景。'),
    ('夜雨寄北', '李商隐', ['君问归期未有期，巴山夜雨涨秋池。', '何当共剪西窗烛，却话巴山夜雨时。'],
     '前两句写归期未定的当下：夜雨持续，秋池水涨。后两句用“何当”打开未来相聚的愿望，因此共剪西窗烛还不是已经发生的事情。画面与口播应区分现在的孤独夜雨和设想中的相聚，不可把两者当作同时发生的实景。',
     '末句设想将来回忆今日夜雨，形成现在、未来、未来回望现在的时间层次。“君”的具体身份在诗中文字中未明确，本读本不把某种身份争议判为唯一答案。可以讨论思念与盼归，不应添造确定日期、烛数、人物动作的细节。'),
]


def build(destination):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from textwrap import wrap
    pdfmetrics.registerFont(TTFont('ReaderCN', 'C:/Windows/Fonts/msyh.ttc', subfontIndex=0))
    destination = Path(destination); destination.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(destination), pagesize=(595, 842), invariant=1)
    c.setTitle('唐诗阅读与赏析：原创补充读本'); c.setAuthor('Book2Course')
    for n, (title, author, poem, observation, interpretation) in enumerate(POEMS):
        for analysis in (False, True):
            c.setFillColorRGB(.08,.16,.24); c.setFont('ReaderCN', 23)
            c.drawString(48, 776, title + ('：赏析' if analysis else ''))
            c.setFont('ReaderCN', 15); c.drawString(48, 742, '唐 · ' + author)
            y = 675; c.setFont('ReaderCN', 18)
            for line in poem: c.drawString(48, y, line); y -= 34
            c.setFont('ReaderCN', 14); y -= 36
            paragraphs = [observation, interpretation] if analysis else [
                '阅读时先辨认诗中直接出现的景物、声音、人物与时间。再联系诗句，解释具体表达怎样形成情境和情绪。',
                '把诗中陈述、夸张表达和赏析解释分开。下一页给出原诗可支持的一种阅读路径；阐释允许讨论，不代表唯一答案。']
            for paragraph in paragraphs:
                for line in wrap(paragraph, width=34): c.drawString(48,y,line); y -= 25
                y -= 20
            c.setFont('ReaderCN', 9)
            c.drawString(48, 54, '原诗公版；电子文本参考 https://www.gutenberg.org/ebooks/52323')
            c.drawString(48, 38, '赏析笔记与排版：Book2Course，CC BY 4.0；原创补充读本，2026；第 '+str(n*2+int(analysis)+1)+' 页')
            c.showPage()
    c.save()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('data/textbook-benchmark-v2/sources/chinese-poetry.pdf'))
    build(parser.parse_args().output)
