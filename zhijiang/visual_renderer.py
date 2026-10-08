"""Trusted Manim interpreter for a subject-independent parametric scene graph."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from manim import (Scene, Text, Circle, Dot, Line, Arrow, Polygon, VMobject,
                   VGroup, ValueTracker, Rectangle, linear, config, MathTex, DecimalNumber, RIGHT)

from zhijiang.models import VisualScenePlan
from zhijiang.visual_planning import object_geometry, states, verify_visual_scene, CHECKERS, evaluate, VisualSceneError, expression_tex, check_domain_state


class GeneralTeachingScene(Scene):
    def get_moving_and_static_mobjects(self, animations):
        # Cairo normally flattens moving families once at animation start.
        # Our stable containers replace children each frame, so that snapshot
        # retains obsolete children even if the container has an updater.
        # Capture current families from their roots on every frame instead.
        return list(self.mobjects), []

    def construct(self):
        data = json.loads(Path(os.environ['BOOK2COURSE_SCENE']).read_text(encoding='utf-8'))
        plan = VisualScenePlan.model_validate(data['plan'])
        verify_visual_scene(plan)
        config.background_color = '#081623'
        self.camera.background_color = '#081623'
        params = dict(plan.parameters)
        from zhijiang.visual_coordinates import EuclideanViewport
        viewport=EuclideanViewport(plan.x_range,plan.y_range,10.6,4.3,(0,.35))
        def point(x, y):
            return np.array([*viewport.point(x,y),0])
        text_templates = {}
        # Keep authored object order in both SVG and movie, independently of
        # hash/set iteration and of show/hide insertion order. Coincident
        # strokes (e.g. an arc on a circle) otherwise disappear nondeterministically.
        object_layers={obj.id:5+i/(len(plan.objects)+1) for i,obj in enumerate(plan.objects)}
        def make(obj):
            g = object_geometry(obj, params)
            pts = [point(*p) for p in g['points']]
            if obj.kind in {'dot', 'circle'}:
                radius = g['radius']*viewport.scale
                if obj.kind=='dot': radius=min(0.1,max(0.035,radius))
                value = (Dot(radius=radius, color=obj.color) if obj.kind == 'dot' else
                         Circle(radius=radius, color=obj.color, fill_opacity=0.16)).move_to(pts[0])
            elif obj.kind in {'line','arrow'}:
                if np.linalg.norm(pts[-1]-pts[0]) < 1e-6:
                    value = Dot(pts[0], radius=0.01, color=obj.color)
                else:
                    value = (Arrow(pts[0],pts[-1],buff=0,color=obj.color) if obj.kind == 'arrow' else
                             Line(pts[0],pts[-1],color=obj.color))
            elif obj.kind == 'polygon':
                value = Polygon(*pts,color=obj.color,fill_opacity=0.2)
            elif obj.kind in {'curve','parametric_curve'}:
                value = VMobject(color=obj.color).set_points_as_corners(pts)
            else:
                if obj.id not in text_templates:
                    text_templates[obj.id] = Text(obj.text,font='Microsoft YaHei',font_size=25,color=obj.color)
                value = text_templates[obj.id].copy().move_to(pts[0])
            return value.set_z_index(object_layers[obj.id])
        if plan.axes:
            axes = VGroup(Line(point(plan.x_range[0],0),point(plan.x_range[1],0),color='#698CA5'),
                          Line(point(0,plan.y_range[0]),point(0,plan.y_range[1]),color='#698CA5'))
            for axis, bounds in [('x',plan.x_range),('y',plan.y_range)]:
                for i in range(6):
                    v = bounds[0]+i*(bounds[1]-bounds[0])/5
                    label = Text(f'{v:.2g}',font_size=15,color='#A7C0CC')
                    label.move_to(point(v,0)+[0,-0.19,0] if axis=='x' else point(0,v)+[-0.25,0,0])
                    label.set_z_index(15)
                    self.add(label)
            self.add(axes)
        # Geometry may continue outside the coordinate window; mask text areas.
        self.add(Rectangle(width=15,height=1.5,fill_color='#081623',fill_opacity=1,stroke_width=0).move_to([0,3.25,0]).set_z_index(10),
                 Rectangle(width=15,height=2.2,fill_color='#081623',fill_opacity=1,stroke_width=0).move_to([0,-2.9,0]).set_z_index(10))
        title = Text(plan.domain,font='Microsoft YaHei',font_size=30,color='#6DE2C0').move_to([0,3.6,0]).set_z_index(20)
        question = Text(plan.question,font='Microsoft YaHei',font_size=26).move_to([0,3.12,0]).set_z_index(20)
        if question.width>12: question.scale_to_fit_width(12)
        footer = Text(f'PDF 第 {plan.evidence.page} 页 · '+('教学示例 / 示意模型' if plan.teaching_example else '来源讲解'),
                      font='Microsoft YaHei',font_size=17,color='#A7C0CC').move_to([0,-3.65,0]).set_z_index(20)
        self.add(title,question,footer)
        # Keep a stable container identity while allowing a collapsed dot to
        # become an Arrow/Line with the correct geometry methods again.
        objects = {obj.id: VGroup(make(obj)).set_z_index(object_layers[obj.id]) for obj in plan.objects}
        visible = {obj.id for obj in plan.objects if obj.visible}
        self.add(*(objects[obj.id] for obj in plan.objects if obj.id in visible))
        caption = None
        report = []
        for i,(before,after,target_visible) in enumerate(states(plan)):
            beat,timing = plan.beats[i],data['timing'][i]
            if caption: self.remove(caption)
            caption = VGroup()
            words = beat.narration
            # Spoken script stays complete; screen uses a short operation cue.
            cue = Text(words[:42]+('…' if len(words)>42 else ''),font='Microsoft YaHei',font_size=24)
            if cue.width>12: cue.scale_to_fit_width(12)
            cue.move_to([0,-2.95,0]); caption.add(cue)
            formulas = plan.verification['states'][i]['calculations']
            dynamic_numbers=[]
            formula_row=VGroup()
            for c in formulas[:2]:
                number=DecimalNumber(evaluate(c['expression'],before),num_decimal_places=3,font_size=26,color='#6DE2C0')
                group=VGroup(Text(c['label'],font='Microsoft YaHei',font_size=22),
                             MathTex(expression_tex(c['expression'])+'=',font_size=28),number).arrange(RIGHT,buff=.12)
                formula_row.add(group); dynamic_numbers.append((number,c['expression']))
            for key in list(beat.parameters)[:2]:
                number=DecimalNumber(before[key],num_decimal_places=3,font_size=24,color='#FFA458')
                formula_row.add(VGroup(Text(key+'=',font_size=22),number).arrange(RIGHT,buff=.05))
                dynamic_numbers.append((number,key))
            if len(formula_row):
                formula_row.arrange(RIGHT,buff=.3)
                if formula_row.width>12: formula_row.scale_to_fit_width(12)
                formula_row.move_to([0,-2.43,0]); caption.add(formula_row)
            caption.set_z_index(20); self.add(caption)
            for key in visible-target_visible: self.remove(objects[key])
            for key in target_visible-visible: self.add(objects[key])
            visible = target_visible
            tracker = ValueTracker(0)
            path = []
            def update(_mob, dt=0):
                alpha = tracker.get_value()
                params.update({key:before[key]+alpha*(after[key]-before[key]) for key in before})
                check_domain_state(plan,params)
                if plan.geometry_constraints:
                    from zhijiang.visual_geometry_checks import check_geometry_constraints,check_geometry_visibility
                    measured_geometry={obj.id:object_geometry(obj,params) for obj in plan.objects}
                    check_geometry_visibility(plan,measured_geometry,visible)
                    check_geometry_constraints(plan,measured_geometry,params)
                for check in plan.checks:
                    if not CHECKERS[check.checker](evaluate(check.expression,params),check.expected,check.tolerance):
                        raise VisualSceneError('实际连续过程违反声明的领域关系：'+check.expression)
                for obj in plan.objects:
                    if obj.id in visible: objects[obj.id].submobjects=[make(obj)]
                for number,expression in dynamic_numbers:
                    number.set_value(evaluate(expression,params)).set_z_index(20)
                path.append({'alpha':float(alpha),'parameters':dict(params)})
            controller = VMobject(); controller.add_updater(update); self.add(controller)
            duration = timing['duration']
            fps=float(config.frame_rate)
            target_frame=round((timing['start']+duration)*fps)
            def wait_to_boundary():
                frames=target_frame-round(float(self.time)*fps)
                if frames>0: self.wait((frames-0.01)/fps)
            if before != after:
                motion_frames=max(6,round(duration*fps*0.55))
                self.play(tracker.animate.set_value(1),run_time=(motion_frames-0.01)/fps,rate_func=linear)
                wait_to_boundary()
            else:
                update(controller); wait_to_boundary()
            controller.remove_updater(update); self.remove(controller)
            params.update(after)
            for obj in plan.objects:
                if obj.id in visible: objects[obj.id].submobjects=[make(obj)]
            checks=[]
            for obj in plan.objects:
                if obj.id not in visible: continue
                g=object_geometry(obj,params); expected=[point(*p) for p in g['points']]
                shape=objects[obj.id][0]
                if obj.kind in {'dot','circle','label'}:
                    actual=[shape.get_center()]; targets=expected[:1]
                elif obj.kind=='polygon':
                    actual=list(shape.get_vertices()); targets=expected
                elif obj.kind in {'line','arrow'} and np.linalg.norm(expected[-1]-expected[0])<1e-6:
                    # A line can legitimately collapse at a single teaching step.
                    # Its dot fallback represents both coincident endpoints.
                    actual=[shape.get_center(),shape.get_center()];targets=[expected[0],expected[-1]]
                else:
                    actual=[shape.get_start(),shape.get_end()]; targets=[expected[0],expected[-1]]
                error=max(float(np.linalg.norm(a-b)) for a,b in zip(actual,targets))
                if len(actual)!=len(targets) or error>1e-6:
                    raise VisualSceneError('实际图形坐标与分镜数据不一致：'+obj.id)
                checks.append({'object':obj.id,'maximum_coordinate_error':error,'passed':True})
            report.append({'step':i+1,'rendered_seconds':float(self.time),'samples':path,
                           'geometry':{obj.id:object_geometry(obj,params) for obj in plan.objects},
                           'checks':checks,'passed':True})
        self.wait(0.6)
        Path(data['geometry_output']).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
