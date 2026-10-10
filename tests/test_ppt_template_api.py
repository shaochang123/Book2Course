from xml.etree import ElementTree as ET
from test_api import make_client
from zhijiang.models import GenerationOptions, Mode, VoiceMode


def test_template_catalog_and_preview_share_allowed_ids(tmp_path):
    client, store = make_client(tmp_path)
    with client:
        catalog = client.get('/api/ppt-templates').json()
        assert [item['id'] for item in catalog] == ['classic', 'paper', 'academic', 'editorial']
        assert client.get('/api/config').json()['ppt_templates'] == catalog
        bodies = []
        for item in catalog:
            response = client.get('/api/ppt-templates/'+item['id']+'/preview')
            assert response.status_code == 200
            assert response.headers['content-type'].startswith('image/svg+xml')
            ET.fromstring(response.content); bodies.append(response.content)
        assert len(set(bodies)) == 4
        assert client.get('/api/ppt-templates/unknown/preview').status_code == 422


def test_selected_template_is_persisted_and_reaches_lesson(tmp_path, sample_pdf):
    client, store = make_client(tmp_path)
    with client:
        response = client.post('/api/jobs', files={'file': ('original.pdf', sample_pdf)},
            data={'rights_confirmed': 'true', 'ppt_template': 'academic'})
        assert response.status_code == 202
        job_id = response.json()['id']
        assert client.get('/api/jobs/'+job_id).json()['model_settings']['ppt_template'] == 'academic'
        lesson = client.get('/api/jobs/'+job_id+'/lesson').json()
        assert lesson['ppt_template'] == 'academic'
        assert lesson['deck_plan']['planner'] == 'deterministic_demo_layout'
        assert len(lesson['deck_plan']['pages']) == len(lesson['segments'])
        assert client.delete('/api/jobs/'+job_id).status_code == 204
        assert not (store.jobs_dir/job_id).exists()


def test_invalid_template_cannot_create_or_retry_a_job(tmp_path, sample_pdf):
    client, store = make_client(tmp_path)
    with client:
        response = client.post('/api/jobs', files={'file': ('original.pdf', sample_pdf)},
            data={'rights_confirmed': 'true', 'ppt_template': '../private.pptx'})
        assert response.status_code == 422
        job = store.create('original.pdf', Mode.DEMO, VoiceMode.SYSTEM, True, False, sample_pdf)
        store.fail(job['id'], '测试失败')
        response = client.post('/api/jobs/'+job['id']+'/retry', data={'ppt_template': 'unknown'})
        assert response.status_code == 422
        assert store.get(job['id'])['status'] == 'failed'


def test_retry_retains_template_and_can_change_it_without_new_source(tmp_path, sample_pdf):
    client, store = make_client(tmp_path)
    with client:
        job = store.create('original.pdf', Mode.DEMO, VoiceMode.SYSTEM, True, False,
            sample_pdf, GenerationOptions(ppt_template='paper'))
        folder = store.jobs_dir/job['id']; source = (folder/'source.pdf').read_bytes()
        store.fail(job['id'], '测试失败')
        assert client.post('/api/jobs/'+job['id']+'/retry').status_code == 202
        assert store.get_options(job['id']).ppt_template == 'paper'
        store.fail(job['id'], '测试失败')
        assert client.post('/api/jobs/'+job['id']+'/retry', data={'ppt_template': 'editorial'}).status_code == 202
        assert store.get_options(job['id']).ppt_template == 'editorial'
        assert (folder/'source.pdf').read_bytes() == source
        assert store.lesson(job['id']).deck_plan['template_id'] == 'editorial'


def test_old_options_and_lessons_default_to_classic():
    from zhijiang.models import Lesson
    from test_deck_planning import example_lesson
    assert GenerationOptions.model_validate({}).ppt_template == 'classic'
    saved = example_lesson().model_dump()
    saved.pop('ppt_template'); saved.pop('deck_plan')
    assert Lesson.model_validate(saved).ppt_template == 'classic'
