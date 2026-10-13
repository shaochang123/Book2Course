import json
from pathlib import Path

import pytest
from zhijiang.config import Settings


def test_benchmark_resumes_identical_production_after_commit_but_rejects_code_change(tmp_path,monkeypatch):
    import scripts.benchmark_textbooks as benchmark
    repo=tmp_path/'repo';(repo/'zhijiang').mkdir(parents=True)
    production=repo/'zhijiang/module.py';production.write_text('version = 1\n',encoding='utf-8')
    spec=repo/'spec.json';spec.write_text(json.dumps({'prompt':'Explain the provided source.',
        'preset':{'voice_mode':'system','content_checks':'warn'},'sources':[]}),encoding='utf-8')
    rubric=repo/'rubric.json';rubric.write_text('{}',encoding='utf-8')
    root=tmp_path/'results';root.mkdir()
    (root/'dataset.json').write_text(json.dumps({'cases':[],
        'spec_sha256':benchmark.digest(spec),'rubric_sha256':benchmark.digest(rubric)}),encoding='utf-8')
    monkeypatch.setattr(benchmark,'REPO',repo);monkeypatch.setattr(benchmark,'SPEC',spec)
    monkeypatch.setattr(benchmark,'RUBRIC',rubric)
    monkeypatch.setattr(benchmark,'report',lambda *args: {})
    monkeypatch.setattr(Settings,'from_env',classmethod(lambda cls:Settings(data_dir=root/'tasks',
        llm_provider='ollama',llm_base_url='http://127.0.0.1:11434',llm_model='test-local')))
    revision=['commit-a']
    monkeypatch.setattr(benchmark.subprocess,'check_output',lambda *args,**kwargs: revision[0])
    benchmark.run(root)
    revision[0]='commit-b';benchmark.run(root)
    config=json.loads((root/'run.json').read_text(encoding='utf-8'))
    assert config['git_commit']=='commit-a' and config['resume_revisions'][0]['git_commit']=='commit-b'
    production.write_text('version = 2\n',encoding='utf-8')
    with pytest.raises(ValueError,match='Production code changed'):benchmark.run(root)
    with pytest.raises(ValueError,match='DeepSeek is excluded'):
        benchmark.run(root,'deepseek-example:cloud',allow_ollama_cloud=True)
    with pytest.raises(ValueError,match='explicitly enable'):
        benchmark.run(root,'example:cloud')
    cloud_root=tmp_path/'cloud';cloud_root.mkdir()
    (cloud_root/'dataset.json').write_bytes((root/'dataset.json').read_bytes())
    benchmark.run(cloud_root,'example:cloud',allow_ollama_cloud=True)
    cloud_config=json.loads((cloud_root/'run.json').read_text(encoding='utf-8'))
    assert cloud_config['remote_model'] and cloud_config['public_input_transmission_consent']
