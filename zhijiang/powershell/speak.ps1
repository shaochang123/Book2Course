param(
    [Parameter(Mandatory=$true)][string]$TextPath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][string]$VoiceName
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SelectVoice($VoiceName)
    $speaker.SetOutputToWaveFile($OutputPath)
    $content = [System.IO.File]::ReadAllText($TextPath, [System.Text.Encoding]::UTF8)
    $speaker.Speak($content)
} finally {
    $speaker.Dispose()
}
