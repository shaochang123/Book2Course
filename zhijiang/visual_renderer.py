"""Trusted Manim interpreter for a subject-independent parametric scene graph."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from manim import (Scene, Text, Circle, Dot, Line, Arrow, DoubleArrow, Polygon, VMobject,
                   VGroup, ValueTracker, Rectangle, linear, config, MathTex, DecimalNumber, RIGHT)

from zhijiang.models import VisualScenePlan
from zhijiang.visual_planning import object_geometry, states, verify_visual_scene, CHECKERS, evaluate, VisualSceneError, expression_tex, check_domain_state
from zhijiang.math_construction import resolve_parameters, validate_actual_claims


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
        params = resolve_parameters(plan,plan.parameters)
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
                    value = ((DoubleArrow if obj.double_tip else Arrow)(pts[0],pts[-1],buff=0,color=obj.color) if obj.kind == 'arrow' else
                             Line(pts[0],pts[-1],color=obj.color))
            elif obj.kind == 'polygon':
                value = Polygon(*pts,color=obj.color,fill_opacity=0.2)
            elif obj.kind in {'curve','parametric_curve'}:
                value = VMobject(color=obj.color).set_points_as_corners(pts)
            else:
                if obj.id not in text_templates:
                    anchored=obj.id in (plan.mathematical_model or {}).get('point_labels',{}).values()
                    text_templates[obj.id] = Text(obj.text,font='Microsoft YaHei',font_size=20 if anchored else 25,color=obj.color)
                value = text_templates[obj.id].copy().move_to(pts[0])
            if obj.reference:value.set_opacity(.45)
            return value.set_z_index(object_layers[obj.id])
        if plan.axes:
            axes = VGroup()
            axis_visible={'x':plan.y_range[0]<=0<=plan.y_range[1],
                          'y':plan.x_range[0]<=0<=plan.x_range[1]}
            if axis_visible['x']:axes.add(Line(point(plan.x_range[0],0),point(plan.x_range[1],0),color='#698CA5'))
            if axis_visible['y']:axes.add(Line(point(0,plan.y_range[0]),point(0,plan.y_range[1]),color='#698CA5'))
            for axis, bounds in [('x',plan.x_range),('y',plan.y_range)]:
                if not axis_visible[axis]:continue
                for i in range(1,5):
                    v = bounds[0]+i*(bounds[1]-bounds[0])/5
                    label = Text(f'{v:.2g}',font_size=15,color='#A7C0CC')
                    label.move_to(point(v,0)+[0,-0.19,0] if axis=='x' else point(0,v)+[-0.25,0,0])
                    label.set_z_index(15)
                    self.add(label)
            self.add(axes)
        # Geometry may continue outside the coordinate window; mask text areas.
        self.add(Rectangle(width=15,height=1.5,fill_color='#081623',fill_opacity=1,stroke_width=0).move_to([0,3.25,0]).set_z_index(10),
                 Rectangle(width=15,height=2.2,fill_color='#081623',fill_opacity=1,stroke_width=0).move_to([0,-2.9,0]).set_z_index(10))
        title = Text(plan.domain,font='Microsoft YaHei',font_size=28,color='#6DE2C0').move_to([0,3.72,0]).set_z_index(20)
        if title.width>12:title.scale_to_fit_width(12)
        import math
        columns=max(50,math.ceil(len(plan.question)/3))
        question = Text('\n'.join(plan.question[start:start+columns] for start in range(0,len(plan.question),columns)),
            font='Microsoft YaHei',font_size=19).move_to([0,3.17,0]).set_z_index(20)
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
        legend=None
        for i,(before,after,target_visible) in enumerate(states(plan)):
            beat,timing = plan.beats[i],data['timing'][i]
            if legend:self.remove(legend)
            if plan.mathematical_model:
                from zhijiang.math_identity import legend_entries
                labels=[Text(label,font='Microsoft YaHei',font_size=18,color=colour)
                    for label,colour in legend_entries(plan,target_visible)]
                if labels:
                    legend=VGroup(*labels).arrange(RIGHT,buff=.3).move_to([0,2.66,0]).set_z_index(20)
                    if legend.width>12:legend.scale_to_fit_width(12)
                    self.add(legend)
            if caption: self.remove(caption)
            caption = VGroup()
            words = beat.narration
            plotted=[obj for obj in plan.objects if obj.kind=='curve' and obj.id in target_visible] if plan.mathematical_model else []
            if len(plotted)>6:raise VisualSceneError('单画面最多同时显示六条函数及公式，请分步显示。')
            # Spoken script stays complete; screen uses a short operation cue.
            cue = Text(words[:42]+('…' if len(words)>42 else ''),font='Microsoft YaHei',font_size=24)
            if cue.width>12: cue.scale_to_fit_width(12)
            cue.move_to([0,-1.99 if plotted else -2.95,0]); caption.add(cue)
            if plotted:
                roles=plan.mathematical_model.get('roles',{})
                for index,obj in enumerate(plotted):
                    row=VGroup(Text(roles.get(obj.id,obj.id),font='Microsoft YaHei',font_size=18,color=obj.color),
                        MathTex('y='+expression_tex(plan.mathematical_model.get('display_expressions',{}).get(obj.id,obj.expression)),font_size=23,color=obj.color)).arrange(RIGHT,buff=.1)
                    if row.width>5.7:row.scale_to_fit_width(5.7)
                    row.move_to([-3 if index%2==0 else 3,-2.33-(index//2)*.29,0])
                    caption.add(row)
            formulas = plan.verification['states'][i]['calculations']
            dynamic_numbers=[]
            formula_row=VGroup()
            for c in formulas[:2]:
                number=DecimalNumber(evaluate(c['expression'],resolve_parameters(plan,before)),num_decimal_places=3,font_size=26,color='#6DE2C0')
                # Full expressions stay in scene data and PPT notes. The screen
                # uses the measured quantity and its live value, avoiding tall
                # fractions/absolute bars colliding with the source footer.
                group=VGroup(Text(c['label']+' ≈',font='Microsoft YaHei',font_size=22),number).arrange(RIGHT,buff=.12)
                formula_row.add(group); dynamic_numbers.append((number,c['expression']))
            for key in list(plan.parameters if plan.mathematical_model else beat.parameters)[:4]:
                number=DecimalNumber(before[key],num_decimal_places=3,font_size=24,color='#FFA458')
                formula_row.add(VGroup(Text(key+'=',font_size=22),number).arrange(RIGHT,buff=.05))
                dynamic_numbers.append((number,key))
            if len(formula_row):
                formula_row.arrange(RIGHT,buff=.3)
                if formula_row.width>12: formula_row.scale_to_fit_width(12)
                formula_row.move_to([0,-3.3 if plotted else -2.43,0]); caption.add(formula_row)
            caption.set_z_index(20); self.add(caption)
            for key in visible-target_visible: self.remove(objects[key])
            for key in target_visible-visible: self.add(objects[key])
            visible = target_visible
            tracker = ValueTracker(0)
            path = []
            def update(_mob, dt=0):
                alpha = tracker.get_value()
                params.clear()
                params.update(resolve_parameters(plan,{key:before[key]+alpha*(after[key]-before[key]) for key in before}))
                check_domain_state(plan,params)
                if plan.geometry_constraints:
                    from zhijiang.visual_geometry_checks import check_geometry_constraints,check_geometry_visibility
                    measured_geometry={obj.id:object_geometry(obj,params) for obj in plan.objects}
                    check_geometry_visibility(plan,measured_geometry,visible)
                    check_geometry_constraints(plan,measured_geometry,params)
                if plan.mathematical_model:
                    from zhijiang.visual_geometry_checks import check_geometry_visibility
                    measured_geometry={obj.id:object_geometry(obj,params) for obj in plan.objects}
                    check_geometry_visibility(plan,measured_geometry,visible)
                    validate_actual_claims(plan,measured_geometry,params,step_index=i+1,endpoint=alpha>=1-1e-9)
                for check in plan.checks:
                    if not CHECKERS[check.checker](evaluate(check.expression,params),check.expected,check.tolerance):
                        raise VisualSceneError('实际连续过程违反声明的领域关系：'+check.expression)
                for obj in plan.objects:
                    if obj.id in visible: objects[obj.id].submobjects=[make(obj)]
                for number,expression in dynamic_numbers:
                    number.set_value(evaluate(expression,params)).set_z_index(20)
                path.append({'alpha':float(alpha),'parameters':dict(params)})
            # Source statements are literal, reviewed inputs, not model TeX.
            # Read and show each one before moving the mathematical objects.
            fps=float(config.frame_rate)
            for panel in timing.get('fact_panels',[]):
                from zhijiang.teaching_layout import wrap_label
                background=Rectangle(width=16,height=9,fill_color='#081623',fill_opacity=1,stroke_width=0).set_z_index(30)
                heading=Text('教材说明',font='Microsoft YaHei',font_size=30,color='#6DE2C0').move_to([0,2.5,0]).set_z_index(31)
                statement=Text(wrap_label(panel['display_text'],44),font='Microsoft YaHei',font_size=26,line_spacing=.9).set_z_index(31)
                if statement.width>12:statement.scale_to_fit_width(12)
                if statement.height>4:statement.scale_to_fit_height(4)
                pages=Text('PDF 第 '+ '、'.join(map(str,panel['source_pages']))+' 页 · AI整理的来源说明',
                    font='Microsoft YaHei',font_size=18,color='#A7C0CC').move_to([0,-2.7,0]).set_z_index(31)
                card=VGroup(background,heading,statement,pages)
                self.add(card)
                end_frame=round((timing['start']+panel['start']+panel['duration'])*fps)
                remaining=end_frame-round(float(self.time)*fps)
                if remaining>0:self.wait((remaining-.01)/fps)
                self.remove(card)
            controller = VMobject(); controller.add_updater(update); self.add(controller)
            duration = timing['duration']
            fps=float(config.frame_rate)
            target_frame=round((timing['start']+duration)*fps)
            def wait_to_boundary():
                frames=target_frame-round(float(self.time)*fps)
                if frames>0: self.wait((frames-0.01)/fps)
            if before != after:
                motion_frames=max(6,round((duration-timing.get('source_seconds',0))*fps*0.55))
                self.play(tracker.animate.set_value(1),run_time=(motion_frames-0.01)/fps,rate_func=linear)
                tracker.set_value(1);update(controller)
                controller.remove_updater(update)
                wait_to_boundary()
            else:
                update(controller);controller.remove_updater(update);wait_to_boundary()
            controller.remove_updater(update); self.remove(controller)
            params.clear()
            params.update(resolve_parameters(plan,after))
            if plan.mathematical_model:
                validate_actual_claims(plan,{obj.id:object_geometry(obj,params) for obj in plan.objects},params,step_index=i+1,endpoint=True)
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
