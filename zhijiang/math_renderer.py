"""Manim interpreter for the verified, finite set of 2-D teaching operations.

Run in a child process. BOOK2COURSE_SCENE points to scene/timing JSON; no model
output is imported as Python or interpreted as executable LaTeX.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np
import sympy as sp
from manim import (ApplyMatrix, Arrow, Create, DashedLine, Dot, FadeIn, FadeOut,
                   GREEN_C, Line, MathTex, NumberPlane, ORANGE, Polygon, Rotate,
                   Rectangle, Scene, Text, Transform, TransformMatchingTex, VGroup, WHITE,
                   config, linear)

from zhijiang.math_planning import TITLES, symbolic_facts, verify_scene
from zhijiang.models import MathScenePlan

BG = "#081623"
ACCENT = "#6DE2C0"
BLUE = "#78BAFF"
MUTED = "#AEC4D0"


class TeachingScene(Scene):
    def construct(self):
        data = json.loads(Path(os.environ["BOOK2COURSE_SCENE"]).read_text(encoding="utf-8"))
        self.plan = MathScenePlan.model_validate(data["plan"])
        verify_scene(self.plan)
        self.f = symbolic_facts(self.plan.parameters)
        self.p = self.plan.parameters
        self.camera.background_color = BG
        self.formula = None
        self.caption = None
        self.elapsed = 0.0
        self.geometry_records = []
        self.path_records = []
        # Cairo has no per-mobject clipping region. Foreground masks keep the
        # infinite projection line and transformed grid out of the text bands.
        self.add(Rectangle(width=config.frame_width, height=1.25, fill_color=BG,
                           fill_opacity=1, stroke_width=0).move_to([0, 3.375, 0]).set_z_index(10),
                 Rectangle(width=config.frame_width, height=1.8, fill_color=BG,
                           fill_opacity=1, stroke_width=0).move_to([0, -3.1, 0]).set_z_index(10))
        title = Text(TITLES[self.plan.kind], font="Microsoft YaHei", font_size=28, color=ACCENT)
        if title.width > 12.7:
            title.scale_to_fit_width(12.7)
        title.move_to([0, 3.55, 0])
        title.set_z_index(20)
        question = Text(self.plan.question, font="Microsoft YaHei", font_size=23, color=WHITE)
        if question.width > 12.6:
            question.scale_to_fit_width(12.6)
        question.move_to([0, 3.02, 0])
        question.set_z_index(20)
        source = Text(f"教学示例 · 原理来源：PDF 第 {self.plan.evidence.page} 页 · 计算已核验",
                      font="Microsoft YaHei", font_size=15, color=MUTED).move_to([0, -3.68, 0])
        source.set_z_index(20)
        self.add(title, question, source)
        self.add_sound(str(Path(data["audio"]).resolve()))
        setup = getattr(self, "setup_" + self.plan.kind)
        setup()
        for beat, timing in zip(self.plan.beats, data["timing"]):
            caption = Text(timing["label"], font="Microsoft YaHei", font_size=22, color=MUTED)
            if caption.width > 12.4:
                caption.scale_to_fit_width(12.4)
            caption.move_to([0, -3.18, 0])
            caption.set_z_index(20)
            if self.caption is not None:
                self.remove(self.caption)
            self.caption = caption
            self.add(caption)
            # Record the actual rendered clock; reserve a pause after every operation.
            start = self.renderer.time
            duration = timing["duration"]
            self.cues = timing.get("cues", [])
            self.rt = max(0.3, min(1.8, min((cue["speech_seconds"] for cue in self.cues), default=duration)*0.13))
            getattr(self, "do_" + beat.action)()
            self.record_geometry(beat.action)
            used = self.renderer.time - start
            if used > duration + 0.08:
                raise RuntimeError(f"动画动作超过配音时间：{beat.action} ({used:.2f}>{duration:.2f})")
            self.wait(max(1 / config.frame_rate, timing["start"] + duration - self.renderer.time))
        self.wait(0.6)
        Path(data["geometry_output"]).write_text(json.dumps(self.geometry_records, ensure_ascii=False, indent=2), encoding="utf-8")

    def cue(self, index):
        """Keep the intermediate state until the next recorded spoken operation."""
        if index < len(self.cues):
            seconds = self.cues[index]["start"]-self.renderer.time
            if seconds > 0:
                self.wait(seconds)

    def record_geometry(self, action):
        records = []
        def check(obj, plane, expected, name):
            actual = plane.p2c(obj.get_center() if np.linalg.norm([float(x) for x in expected]) < 1e-9 else obj.get_end())[:2]
            target = np.asarray(expected, dtype=float).flatten()
            if not np.allclose(actual, target, atol=1e-6):
                raise RuntimeError(f"渲染几何与数学计算不一致：{action}/{name}: {actual} != {target}")
            records.append({"object": name, "actual": actual.tolist(), "expected": target.tolist(), "passed": True})
        if action == "add_then_transform":
            check(self.lsum, self.left, self.f["A_sum"], "A(v+w)")
        elif action == "transform_then_add":
            check(self.rsum, self.right, self.f["sum_images"], "Av+Aw")
        elif action == "homogeneity":
            check(self.lv, self.left, self.f["image_scaled"], "A(cv)")
            check(self.rv, self.right, self.f["scaled_image"], "cAv")
        elif action in ("basis_images", "matrix_columns"):
            check(self.e1, self.axes, self.f["e1_image"], "Ae1")
            check(self.e2, self.axes, self.f["e2_image"], "Ae2")
        elif action in ("transform_combination", "plane_transform"):
            check(self.v, self.axes, self.f["Av"], "Av")
            if action == "plane_transform":
                vertices = [self.axes.p2c(point)[:2] for point in self.box.get_vertices()]
                area = abs(sum(vertices[i][0]*vertices[(i+1)%4][1]-vertices[(i+1)%4][0]*vertices[i][1]
                               for i in range(4)))/2
                if not np.isclose(area, float(self.f["area"]), atol=1e-6):
                    raise RuntimeError("渲染多边形面积与计算结果不一致。")
                records.append({"object": "unit_square_area", "actual": float(area),
                                "expected": float(self.f["area"]), "passed": True})
        elif action == "project":
            check(self.v, self.axes, self.f["Pv"], "Pv")
        elif action == "eigen_parallel":
            check(self.u, self.axes, self.f["parallel_image"], "Pu")
        elif action == "eigen_perpendicular":
            check(self.n, self.axes, self.f["perpendicular_image"], "Pn")
        elif action == "rotate_then_stretch":
            check(self.lv, self.left, self.f["SRv"], "SRv")
        elif action == "stretch_then_rotate":
            check(self.rv, self.right, self.f["RSv"], "RSv")
        self.geometry_records.append({"action": action, "rendered_seconds": self.renderer.time, "checks": records,
                                      "continuous_paths": self.path_records})
        self.path_records = []

    def tex(self, key):
        return sp.latex(self.f[key])

    def equation(self, text):
        equation = MathTex(text, font_size=31, color=WHITE)
        if equation.width > 12.2:
            equation.scale_to_fit_width(12.2)
        if equation.height > 0.85:
            equation.scale_to_fit_height(0.85)
        equation.move_to([0, -2.45, 0])
        equation.set_z_index(20)
        if self.formula is None:
            self.play(FadeIn(equation), run_time=self.rt)
        else:
            self.play(TransformMatchingTex(self.formula, equation), run_time=self.rt)
        self.formula = equation

    def plane(self, center=(0, 0.3), split=False, extent_override=None):
        # Equal x/y units are essential for true Euclidean rotation.
        names = {"linearity": ("v", "w", "Av", "Aw", "A_sum"),
                 "basis": ("v", "Av", "e1_image", "e2_image"),
                 "plane": ("v", "Av", "e1_image", "e2_image"),
                 "projection": ("v", "Pv"),
                 "composition": ("v", "SRv", "RSv")}[self.plan.kind]
        points = [[float(value) for value in self.f[key]] for key in names]
        extent = max(2.5, max(abs(value) for point in points for value in point)*1.15) if split else max(
            1.8, max(abs(point[1]) for point in points)*1.15, max(abs(point[0]) for point in points)*0.575)
        if extent_override is not None:
            extent = extent_override
        step = max(1, math.ceil(extent/6))
        if split:
            plane = NumberPlane(x_range=[-extent, extent, step], y_range=[-extent, extent, step],
                x_length=4.7, y_length=4.7,
                background_line_style={"stroke_color": "#325068", "stroke_width": 1, "stroke_opacity": 0.45},
                axis_config={"stroke_color": "#698CA5", "stroke_width": 2})
        else:
            plane = NumberPlane(x_range=[-2*extent, 2*extent, step], y_range=[-extent, extent, step],
                x_length=10, y_length=5,
                background_line_style={"stroke_color": "#325068", "stroke_width": 1, "stroke_opacity": 0.45},
                axis_config={"stroke_color": "#698CA5", "stroke_width": 2})
        plane.move_to([*center, 0])
        plane.add_coordinates(font_size=16)
        self.add(plane)
        return plane

    def vector(self, plane, value, color=ACCENT, tail=(0, 0)):
        coordinates = np.asarray([float(x) for x in value])
        start = plane.c2p(*tail)
        end = plane.c2p(*(coordinates + tail))
        if np.linalg.norm(end-start) < 1e-8:
            return Dot(end, color=color, radius=0.065)
        return Arrow(start, end, buff=0, stroke_width=5, color=color,
                     max_tip_length_to_length_ratio=0.14)

    def square(self, plane, matrix=None, color=BLUE):
        matrix = np.eye(2) if matrix is None else np.asarray(matrix, dtype=float)
        points = [plane.c2p(*(matrix @ np.asarray(point))) for point in ((0, 0), (1, 0), (1, 1), (0, 1))]
        return Polygon(*points, color=color, fill_color=color, fill_opacity=0.25, stroke_width=3)

    def clear_objects(self, *groups):
        self.play(*[FadeOut(group) for group in groups], run_time=self.rt)

    def setup_linearity(self):
        self.left = self.plane((-3.25, 0.25), True)
        self.right = self.plane((3.25, 0.25), True)
        self.lv, self.lw = self.vector(self.left, self.f["v"], GREEN_C), self.vector(self.left, self.f["w"], ORANGE)
        self.rv, self.rw = self.vector(self.right, self.f["v"], GREEN_C), self.vector(self.right, self.f["w"], ORANGE)
        self.add(Text("先相加，再变换", font="Microsoft YaHei", font_size=18, color=BLUE).move_to([-3.25, 2.7, 0]),
                 Text("先变换，再相加", font="Microsoft YaHei", font_size=18, color=BLUE).move_to([3.25, 2.7, 0]))

    def do_vectors(self):
        self.play(Create(self.lv), Create(self.lw), Create(self.rv), Create(self.rw), run_time=self.rt)
        self.equation(r"v="+self.tex("v")+r",\quad w="+self.tex("w"))

    def do_add_then_transform(self):
        self.lsum = self.vector(self.left, self.f["sum"], BLUE)
        v, w = [float(x) for x in self.f["v"]], [float(x) for x in self.f["w"]]
        self.construction = VGroup(DashedLine(self.left.c2p(*v), self.left.c2p(*np.add(v, w)), color=ORANGE),
                                  DashedLine(self.left.c2p(*w), self.left.c2p(*np.add(v, w)), color=GREEN_C))
        self.play(Create(self.construction), Create(self.lsum), run_time=self.rt)
        self.equation(r"v+w="+self.tex("sum"))
        self.cue(1)
        self.play(Transform(self.lsum, self.vector(self.left, self.f["A_sum"], BLUE)),
                  self.construction.animate.set_opacity(0.25), self.lv.animate.set_opacity(0.25),
                  self.lw.animate.set_opacity(0.25), run_time=self.rt)
        self.equation(r"A(v+w)="+self.tex("A_sum"))

    def do_transform_then_add(self):
        self.play(Transform(self.rv, self.vector(self.right, self.f["Av"], GREEN_C)),
                  Transform(self.rw, self.vector(self.right, self.f["Aw"], ORANGE)), run_time=self.rt)
        self.equation(r"Av="+self.tex("Av")+r",\quad Aw="+self.tex("Aw"))
        self.cue(1)
        self.rsum = self.vector(self.right, self.f["sum_images"], BLUE)
        first, second, total = [[float(value) for value in self.f[key]] for key in ("Av", "Aw", "sum_images")]
        self.rconstruction = VGroup(DashedLine(self.right.c2p(*first), self.right.c2p(*total), color=ORANGE),
                                   DashedLine(self.right.c2p(*second), self.right.c2p(*total), color=GREEN_C))
        self.play(Create(self.rsum), Create(self.rconstruction), run_time=self.rt)
        self.equation(r"Av+Aw="+self.tex("Av")+"+"+self.tex("Aw")+"="+self.tex("sum_images")+r"=A(v+w)")

    def do_homogeneity(self):
        self.equation(r"c="+sp.latex(sp.Rational(str(self.p.scalar)))+r",\quad A(cv)=c(Av)")
        self.clear_objects(self.lv, self.lw, self.rv, self.rw, self.lsum, self.rsum, self.construction, self.rconstruction)
        extent = max(2.5, max(abs(float(value)) for value in self.f["scaled_image"])*1.15)
        self.remove(self.left, self.right)
        self.left = self.plane((-3.25, 0.25), True, extent)
        self.right = self.plane((3.25, 0.25), True, extent)
        self.lv = self.vector(self.left, self.p.scalar*self.f["v"], GREEN_C)
        self.rv = self.vector(self.right, self.f["v"], GREEN_C)
        self.play(Create(self.lv), Create(self.rv), run_time=self.rt)
        self.play(Transform(self.lv, self.vector(self.left, self.f["image_scaled"], GREEN_C)),
                  Transform(self.rv, self.vector(self.right, self.f["Av"], GREEN_C)), run_time=self.rt)
        self.play(Transform(self.rv, self.vector(self.right, self.f["scaled_image"], GREEN_C)), run_time=self.rt)
        self.equation(r"A(cv)=c(Av)="+self.tex("scaled_image"))

    def do_translation_counterexample(self):
        self.clear_objects(self.lv, self.rv)
        zero = Dot(self.left.c2p(0, 0), color=WHITE)
        displaced = Dot(self.left.c2p(*self.p.shift), color=ORANGE)
        self.play(FadeIn(zero), run_time=self.rt)
        self.play(Transform(zero, displaced), run_time=self.rt)
        self.equation(r"T(v)=v+"+self.tex("shift")+r",\quad T(0)="+self.tex("shift")+r"\ne0")

    def setup_basis(self):
        self.axes = self.plane()
        self.e1 = self.vector(self.axes, [1, 0], GREEN_C)
        self.e2 = self.vector(self.axes, [0, 1], ORANGE)

    def do_basis_vectors(self):
        self.play(Create(self.e1), Create(self.e2), run_time=self.rt)
        self.equation(r"e_1=\begin{bmatrix}1\\0\end{bmatrix},\quad e_2=\begin{bmatrix}0\\1\end{bmatrix}")

    def do_basis_images(self):
        self.play(Transform(self.e1, self.vector(self.axes, self.f["e1_image"], GREEN_C)),
                  Transform(self.e2, self.vector(self.axes, self.f["e2_image"], ORANGE)), run_time=self.rt)
        self.equation(r"T(e_1)="+self.tex("e1_image")+r",\quad T(e_2)="+self.tex("e2_image"))

    def do_matrix_columns(self):
        self.equation(r"A=\left[T(e_1)\ \ T(e_2)\right]="+self.tex("A"))

    def do_decompose(self):
        self.play(Transform(self.e1, self.vector(self.axes, [1, 0], GREEN_C)),
                  Transform(self.e2, self.vector(self.axes, [0, 1], ORANGE)), run_time=self.rt)
        x, y = self.p.vector
        self.xpart = self.vector(self.axes, [x, 0], GREEN_C)
        self.ypart = self.vector(self.axes, [0, y], ORANGE, tail=(x, 0))
        self.v = self.vector(self.axes, self.f["v"], BLUE)
        self.play(Create(self.xpart), Create(self.ypart), Create(self.v), run_time=self.rt)
        self.equation(r"v="+self.tex("v")+r"="+sp.latex(sp.Rational(str(x)))+r"e_1+"+sp.latex(sp.Rational(str(y)))+r"e_2")

    def do_transform_combination(self):
        x, y = self.p.vector
        first = np.asarray(self.f["e1_image"], dtype=float).flatten()*x
        second = np.asarray(self.f["e2_image"], dtype=float).flatten()*y
        self.play(Transform(self.e1, self.vector(self.axes, self.f["e1_image"], GREEN_C)),
                  Transform(self.e2, self.vector(self.axes, self.f["e2_image"], ORANGE)),
                  Transform(self.xpart, self.vector(self.axes, first, GREEN_C)),
                  Transform(self.ypart, self.vector(self.axes, second, ORANGE, tail=first)),
                  Transform(self.v, self.vector(self.axes, self.f["Av"], BLUE)), run_time=self.rt)
        self.equation(r"Av="+self.tex("A")+self.tex("v")+r"="+self.tex("Av"))

    def setup_plane(self):
        self.axes = self.plane()
        self.material = VGroup(self.axes.background_lines.copy(), self.axes.faded_lines.copy()).set_color(ACCENT).set_opacity(0.55)
        self.box = self.square(self.axes)
        self.v = self.vector(self.axes, self.f["v"], ORANGE)

    def do_plane_start(self):
        self.play(FadeIn(self.material), Create(self.box), Create(self.v), run_time=self.rt)
        self.equation(r"A="+self.tex("A")+r",\quad \mathrm{Area}_{\mathrm{before}}=1")

    def do_plane_transform(self):
        origin = self.axes.c2p(0, 0)
        self.play(ApplyMatrix(np.asarray(self.p.matrix), VGroup(self.material, self.box, self.v),
                              about_point=origin), run_time=self.rt)
        self.equation(r"v="+self.tex("v")+r"\longmapsto Av="+self.tex("Av"))

    def do_area(self):
        self.equation(r"\mathrm{Area}_{\mathrm{after}}=|\det A|="+self.tex("area"))

    def setup_projection(self):
        self.axes = self.plane()
        self.v = self.vector(self.axes, self.f["v"], BLUE)
        u = np.asarray(self.f["parallel"], dtype=float).flatten()
        self.line = Line(self.axes.c2p(*(-5*u)), self.axes.c2p(*(5*u)), color=ACCENT, stroke_width=4)

    def do_projection_start(self):
        self.play(Create(self.line), Create(self.v), run_time=self.rt)
        self.equation(r"P="+self.tex("P"))

    def do_project(self):
        start = self.axes.c2p(*[float(x) for x in self.f["v"]])
        end = self.axes.c2p(*[float(x) for x in self.f["Pv"]])
        self.normal = DashedLine(start, end, color=ORANGE)
        self.endpoint = Dot(start, color=BLUE)
        self.play(Create(self.normal), FadeIn(self.endpoint), run_time=self.rt)
        samples = []
        initial = np.array([float(value) for value in self.f["v"]])
        parallel = np.array([float(value) for value in self.f["parallel"]])
        def observe(endpoint):
            point = self.axes.p2c(endpoint.get_center())[:2]
            error = abs(float((point-initial).dot(parallel)))
            if error > 1e-6:
                raise RuntimeError("投影路径未沿法线移动。")
            samples.append({"point": point.tolist(), "normal_path_error": error})
        self.endpoint.add_updater(observe)
        self.play(Transform(self.v, self.vector(self.axes, self.f["Pv"], BLUE)),
                  self.endpoint.animate(suspend_mobject_updating=False).move_to(end), run_time=self.rt)
        self.endpoint.remove_updater(observe)
        self.path_records.append({"operation": "normal_projection", "samples": samples, "passed": True})
        self.equation(r"Pv="+self.tex("Pv")+r",\quad P^2=P")

    def do_eigen_parallel(self):
        self.u = self.vector(self.axes, self.f["parallel"], GREEN_C)
        self.play(Create(self.u), run_time=self.rt)
        self.play(Transform(self.u, self.vector(self.axes, self.f["parallel_image"], GREEN_C)), run_time=self.rt)
        self.equation(r"Pu=u,\quad \lambda_{\parallel}=1")

    def do_eigen_perpendicular(self):
        self.n = self.vector(self.axes, self.f["perpendicular"], ORANGE)
        self.ghost_n = self.n.copy().set_opacity(0.3)
        self.play(Create(self.n), FadeIn(self.ghost_n), run_time=self.rt)
        self.play(Transform(self.n, Dot(self.axes.c2p(0, 0), color=ORANGE)), run_time=self.rt)
        self.equation(r"Pn=0=0n,\quad n\ne0,\quad\lambda_{\perp}=0")

    def do_change_basis(self):
        self.equation(r"Q=[u\ n],\quad Q^{-1}PQ="+self.tex("diagonal_projection"))

    def setup_composition(self):
        self.left = self.plane((-3.25, 0.25), True)
        self.right = self.plane((3.25, 0.25), True)
        self.lv = self.vector(self.left, self.f["v"], GREEN_C)
        self.rv = self.vector(self.right, self.f["v"], ORANGE)
        self.lbox = self.square(self.left, color=GREEN_C)
        self.rbox = self.square(self.right, color=ORANGE)
        self.add(Text("先 R 旋转，再 S 伸缩", font="Microsoft YaHei", font_size=18, color=GREEN_C).move_to([-3.25, 2.7, 0]),
                 Text("先 S 伸缩，再 R 旋转", font="Microsoft YaHei", font_size=18, color=ORANGE).move_to([3.25, 2.7, 0]))

    def do_composition_start(self):
        self.play(Create(self.lv), Create(self.rv), Create(self.lbox), Create(self.rbox), run_time=self.rt)
        self.equation(r"R="+self.tex("R")+r",\quad S="+self.tex("S"))

    def do_rotate_then_stretch(self):
        objects = VGroup(self.lv, self.lbox)
        self.rotate_checked(objects, self.lv, self.left)
        self.equation(r"Rv="+self.tex("Rv"))
        self.cue(1)
        self.play(ApplyMatrix(np.asarray(self.f["S"], dtype=float), objects,
                              about_point=self.left.c2p(0, 0)), run_time=self.rt)
        self.equation(r"v\overset{R}{\longmapsto}Rv\overset{S}{\longmapsto}SRv="+self.tex("SRv"))

    def do_stretch_then_rotate(self):
        objects = VGroup(self.rv, self.rbox)
        self.play(ApplyMatrix(np.asarray(self.f["S"], dtype=float), objects,
                              about_point=self.right.c2p(0, 0)), run_time=self.rt)
        self.equation(r"Sv="+self.tex("Sv"))
        self.cue(1)
        self.rotate_checked(objects, self.rv, self.right)
        self.equation(r"v\overset{S}{\longmapsto}Sv\overset{R}{\longmapsto}RSv="+self.tex("RSv"))

    def do_compare_order(self):
        self.equation(r"SRv="+self.tex("SRv")+r"\ne RSv="+self.tex("RSv"))

    def rotate_checked(self, objects, vector, plane):
        length = np.linalg.norm(plane.p2c(vector.get_end())[:2])
        samples = []
        def observe(arrow):
            point = plane.p2c(arrow.get_end())[:2]
            error = abs(float(np.linalg.norm(point)-length))
            if error > 1e-6:
                raise RuntimeError("旋转中间帧未保持向量长度。")
            samples.append({"point": point.tolist(), "length_error": error})
        vector.add_updater(observe)
        self.play(Rotate(objects, angle=np.deg2rad(self.p.rotation_degrees),
                         about_point=plane.c2p(0, 0), suspend_mobject_updating=False),
                  run_time=self.rt, rate_func=linear)
        vector.remove_updater(observe)
        self.path_records.append({"operation": "angle_interpolation", "samples": samples, "passed": True})
