import math

import pytest

from tests.test_math_construction import compile, program
from zhijiang.mathematical_planning import review_step_states
from zhijiang.visual_planning import verify_visual_scene


def test_review_states_match_accumulated_controls_values_and_actual_image_order():
    p=program([{'id':'f','op':'function','expr':['exp(x)'],'domain':[-1,1]},
        {'id':'m','op':'point_on_function','refs':['f'],'expr':['u']}],
        [{'lhs':'ycoord(m)','rhs':'value(f,u)'}],changes=[{'u':.4},{},{'u':.7}])
    for operation in p.operations:operation.measurements={'实际函数值':'ycoord(m)'}
    scene=compile(p);scene.verification=verify_visual_scene(scene)
    states=review_step_states(scene,svg_image_offset=2)
    assert [s['step'] for s in states]==[1,2,3]
    assert [s['svg_image_position'] for s in states]==[3,4,5]
    assert [s['end_parameters']['u'] for s in states]==[.4,.4,.7]
    assert states[1]['calculations'][0]['value']==pytest.approx(math.exp(.4))
    assert states[1]['narration']==scene.beats[1].narration
    assert all(s['svg_image_position'] is None for s in review_step_states(scene))
