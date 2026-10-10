import json
from pathlib import Path
import pytest
from scripts.verify_math_web import snapshot_diagnostics


def test_retries_never_overwrite_previous_diagnostic_snapshot(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    job=Path('data/jobs/example');job.mkdir(parents=True)
    source=job/'visual-planning.json';source.write_text('{"attempt":1}',encoding='utf-8')
    folder=Path('result')
    snapshot_diagnostics('example',folder)
    source.write_text('{"attempt":2}',encoding='utf-8')
    snapshot_diagnostics('example',folder)
    assert json.loads((folder/'job-diagnostics/visual-planning.json').read_text())=={'attempt':1}
    later=list((folder/'job-diagnostics-history').glob('*/visual-planning.json'))
    assert len(later)==1 and json.loads(later[0].read_text())=={'attempt':2}
    snapshot_diagnostics('example',folder)
    assert len(list((folder/'job-diagnostics-history').iterdir()))==1


def test_snapshot_rejects_job_path_escape(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError,match='Invalid diagnostic job path'):
        snapshot_diagnostics('../',Path('result'))
