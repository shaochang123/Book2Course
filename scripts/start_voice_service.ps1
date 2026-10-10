$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv-tts/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw '请先按文档创建 .venv-tts 并安装 requirements-tts.txt。'
}
Push-Location -LiteralPath $taskRoot
try {
    & $taskPython -X utf8 -m uvicorn zhijiang.qwen_tts_service:app --host 127.0.0.1 --port 8766
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
