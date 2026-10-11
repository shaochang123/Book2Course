"""Exercise real Git ignore/index/push history, without real credentials."""
from pathlib import Path
import json
import subprocess
import sys

import pytest

from scripts.check_git_privacy import audit, git, ignored, local_secrets, outgoing_commits

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/check_git_privacy.py'


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.name', 'Privacy test')
    git(tmp_path, 'config', 'user.email', 'privacy-test@example.invalid')
    (tmp_path/'.gitignore').write_bytes((ROOT/'.gitignore').read_bytes())
    (tmp_path/'README.md').write_text('Authored documentation.\n', encoding='utf-8')
    git(tmp_path, 'add', '.gitignore', 'README.md')
    git(tmp_path, 'commit', '-qm', 'Initial source')
    return tmp_path


@pytest.mark.parametrize('path', ['.env','.env.local','.env.production','nested/.env.test',
    '.venv-tts/config.json','data/jobs/task/lesson.json','output/course/lesson.pptx',
    'demo/example.json','submission/archive.zip','docs/XZB2.pdf','docs/images/result.png',
    'nested/cache/file.json','nested/.cache/file.json','credentials.json','private.pem',
    'voice.wav','movie.mp4','model.safetensors','jobs/task/source.pdf','model-calls.json'])
def test_sensitive_and_generated_paths_are_ignored(repository,path):
    assert path in ignored(repository,[path])


@pytest.mark.parametrize('path', ['.env.local.example','README.md','zhijiang/agents.py',
    'zhijiang/assets/visuals/biology/cell.svg','zhijiang/assets/visuals/biology/new.png',
    'examples/finance_exhibits_original.json','examples/binary_search_original.pdf'])
def test_authored_sources_and_empty_templates_remain_versioned(repository,path):
    assert path not in ignored(repository,[path])


def test_force_added_generated_output_is_rejected_but_stays_on_disk(repository):
    path=repository/'demo';path.mkdir();(path/'lesson.json').write_text('{}')
    git(repository,'add','-f','demo/lesson.json')
    assert ('demo/lesson.json','ignored/private/generated file is tracked') in audit(repository,None,[])
    assert (path/'lesson.json').is_file()


def test_embedded_key_and_local_credential_are_rejected_without_printing_values(repository):
    provider=('sk-'+'a'*40).encode()
    local=b'localcredential1234567890'
    (repository/'.env.local').write_bytes(b'APP_API_KEY='+local+b'\n')
    (repository/'config.py').write_bytes(b'api_key="'+provider+b'"\n# '+local+b'\n')
    git(repository,'add','config.py')
    assert local_secrets(repository)==[local]
    assert ('config.py','possible credential; value omitted') in audit(repository,None,[local])
    result=subprocess.run([sys.executable,str(SCRIPT),'--repo',str(repository)],capture_output=True)
    assert result.returncode==1
    assert provider not in result.stdout+result.stderr and local not in result.stdout+result.stderr


def test_empty_template_and_source_code_pass(repository):
    (repository/'.env.local.example').write_text('APP_API_KEY=\n')
    git(repository,'add','.env.local.example')
    assert audit(repository,None,[])==[]


def test_context_token_count_is_not_treated_as_a_credential(repository):
    (repository/'.env.local').write_text('ZHIJIANG_OLLAMA_CONTEXT_TOKENS=16384\n')
    assert local_secrets(repository)==[]


def test_nonempty_unquoted_key_in_example_template_is_blocked(repository):
    (repository/'.env.local.example').write_text('APP_API_KEY=unquotedcredential123456789\n')
    git(repository,'add','.env.local.example')
    assert ('.env.local.example','possible credential; value omitted') in audit(repository,None,[])


def test_quoted_json_key_with_custom_credential_is_blocked(repository):
    (repository/'settings.json').write_text(json.dumps({'api_key':'arbitrary'+'private'+'credential'}))
    git(repository,'add','settings.json')
    assert ('settings.json','possible credential; value omitted') in audit(repository,None,[])


def test_pre_push_checks_intermediate_commits_even_if_head_removed_secret(repository):
    base=git(repository,'rev-parse','HEAD').decode().strip()
    (repository/'config.py').write_text('api_key="'+'sk-'+'a'*40+'"\n')
    git(repository,'add','config.py');git(repository,'commit','-qm','Accidental credential')
    bad=git(repository,'rev-parse','HEAD').decode().strip()
    git(repository,'rm','config.py');git(repository,'commit','-qm','Remove from final tree')
    head=git(repository,'rev-parse','HEAD').decode().strip()
    assert audit(repository,head,[])==[]
    line=f'refs/heads/main {head} refs/heads/main {base}'
    assert bad in outgoing_commits(repository,[line])
    result=subprocess.run([sys.executable,str(SCRIPT),'--repo',str(repository),'--pre-push'],
                          input=line.encode()+b'\n',capture_output=True)
    assert result.returncode==1 and b'possible credential' in result.stderr


def test_new_branch_and_deleted_branch_pushes(repository):
    head=git(repository,'rev-parse','HEAD').decode().strip();zero='0'*40
    assert head in outgoing_commits(repository,[f'refs/heads/new {head} refs/heads/new {zero}'])
    assert outgoing_commits(repository,[f'(delete) {zero} refs/heads/old {head}'])==[]
