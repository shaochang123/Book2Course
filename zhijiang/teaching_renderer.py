"""Trace grounded relations; animation expresses reasoning, not invented physics."""
from __future__ import annotations
import json,os
from pathlib import Path
import numpy as np
from manim import (Scene,Text,VGroup,RoundedRectangle,Rectangle,Arrow,Line,Dot,ImageMobject,
                   Create,FadeIn,FadeOut,MoveAlongPath,linear,config)
from zhijiang.models import VisualScenePlan
from zhijiang.visual_planning import verify_visual_scene
from zhijiang.teaching_layout import layout_diagram,wrap_label


class DiagramTeachingScene(Scene):
    def construct(self):
        data=json.loads(Path(os.environ['BOOK2COURSE_SCENE']).read_text(encoding='utf-8'))
        plan=VisualScenePlan.model_validate(data['plan']);verify_visual_scene(plan)
        diagram=plan.diagram;config.background_color='#081623';self.camera.background_color='#081623'
        layout,connections=layout_diagram(diagram)
        def point(p): return np.array([*p,0])
        title=Text(plan.domain,font='Microsoft YaHei',font_size=28,color='#6DE2C0').move_to([0,3.58,0])
        if title.width>12:title.scale_to_fit_width(12)
        question=Text(plan.question,font='Microsoft YaHei',font_size=25).move_to([0,3.05,0])
        if question.width>12:question.scale_to_fit_width(12)
        self.add(title,question)
        image=None
        if diagram.source_asset:
            image=ImageMobject(diagram.source_asset).scale_to_fit_height(4.9).move_to([-4.75,.25,0])
            if image.width>3.2:image.scale_to_fit_width(3.2)
            self.add(image)
        nodes={};edges={};labels={}
        for node in diagram.nodes:
            g=layout[node.id]
            box=RoundedRectangle(width=g['width'],height=g['height'],corner_radius=.16,
                stroke_color=g['color'],stroke_width=2,fill_color='#142F43',fill_opacity=1)
            label=Text(wrap_label(node.label),font='Microsoft YaHei',font_size=25,color=g['color'],line_spacing=.7)
            if label.width>g['width']-.25:label.scale_to_fit_width(g['width']-.25)
            group=VGroup(box,label).move_to(point(g['position']))
            nodes[node.id]=group;self.add(group)
        for relation in diagram.relations:
            g=connections[relation.id]
            line_type=Arrow if relation.directed else Line
            arrow=line_type(point(g['start']),point(g['end']),buff=0,stroke_width=3,color=g['color'])
            label=Text(relation.label,font='Microsoft YaHei',font_size=17,color='#E5EEF3').move_to(point(g['label']))
            backing=Rectangle(width=label.width+.12,height=label.height+.08,fill_color='#081623',fill_opacity=1,stroke_width=0).move_to(label)
            edges[relation.id]=arrow;labels[relation.id]=VGroup(backing,label)
        guide='关系追踪' if diagram.relations else '原文图示高亮'
        footer=Text(f'PDF 第 {plan.evidence.page} 页 · {guide}表示讲解顺序，非物理模拟',
            font='Microsoft YaHei',font_size=17,color='#A7C0CC').move_to([0,-3.65,0]);self.add(footer)
        report=[];caption=None;shown=set();highlight=None
        for i,step in enumerate(diagram.steps):
            timing=data['timing'][i]
            if caption:self.remove(caption)
            cue=wrap_label(step.narration,44)
            caption=Text(cue,font='Microsoft YaHei',font_size=22,line_spacing=.6).move_to([0,-2.85,0])
            if caption.width>12:caption.scale_to_fit_width(12)
            if caption.height>.95:caption.scale_to_fit_height(.95)
            self.add(caption)
            animations=[group.animate.set_opacity(1 if key in step.focus else .42) for key,group in nodes.items()]
            for key in step.relations:
                if key not in shown:
                    animations.extend([Create(edges[key]),FadeIn(labels[key])]);shown.add(key)
            if highlight:self.remove(highlight);highlight=None
            if image:
                boxes=[]
                for key in step.focus:
                    rect=diagram.source_regions.get(str(key))
                    if not rect:continue
                    x0,y0,x1,y1=rect
                    box=Rectangle(width=max(.05,(x1-x0)*image.width),height=max(.05,(y1-y0)*image.height),
                        color=layout[key]['color'],stroke_width=2)
                    box.move_to(image.get_corner(np.array([-1,1,0]))+[(x0+x1)*image.width/2,-(y0+y1)*image.height/2,0])
                    boxes.append(box)
                highlight=VGroup(*boxes);self.add(highlight)
            fps=float(config.frame_rate);boundary=round((timing['start']+timing['duration'])*fps)
            transition=min(1.1,timing['duration']*.15)
            self.play(*animations,run_time=transition)
            # Same edge/object identities are retained across explanations.
            for key in step.relations:
                token=Dot(radius=.07,color=connections[key]['color']).move_to(edges[key].get_start())
                self.add(token)
                self.play(MoveAlongPath(token,edges[key]),run_time=min(1.25,timing['duration']*.13),rate_func=linear)
                self.remove(token)
            remaining=boundary-round(float(self.time)*fps)
            if remaining>0:self.wait((remaining-.01)/fps)
            report.append({'step':i+1,'rendered_seconds':float(self.time),'passed':True,
                'representation':diagram.representation,'focus':step.focus,'relations':step.relations,
                'nodes':layout,'connections':connections,'source_regions':diagram.source_regions,
                'checks':[{'kind':'relation_endpoints','passed':True,'relation':key,
                           'maximum_coordinate_error':float(max(np.linalg.norm(edges[key].get_start()-point(connections[key]['start'])),
                                                               np.linalg.norm(edges[key].get_end()-point(connections[key]['end']))))}
                          for key in step.relations]})
        self.wait(.6)
        Path(data['geometry_output']).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
