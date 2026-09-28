# Qadam AI Windows launcher: powershell -ExecutionPolicy Bypass -File .\run.ps1
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (Test-Path -LiteralPath ".env") {
    Get-Content -LiteralPath ".env" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $name, $value = $line.Split("=", 2)
            [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), "Process")
        }
    }
}

$python = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }
$port = if ($env:PORT) { $env:PORT } else { "8000" }
if (-not $env:PORT) {
    $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($busy) {
        $port = "8765"
        Write-Host "Port 8000 is busy; using port 8765."
    }
}

Write-Host "== 1/4 Python dependencies =="
& $python -c "import fastapi, sklearn, pydantic, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install -r requirements.txt
}

Write-Host "== 2/4 Data and trained model =="
if (-not (Test-Path -LiteralPath "qadam/data/corpus/leadership.jsonl")) {
    & $python -m qadam.data.generate
}
if (-not (Test-Path -LiteralPath "qadam/data/model/leadership.joblib")) {
    & $python -m eval.train
}

Write-Host "== 3/4 Web interface =="
if (-not (Test-Path -LiteralPath "web/node_modules")) {
    & npm ci --prefix web
}
if (-not (Test-Path -LiteralPath "web/dist")) {
    & npm run build --prefix web
}

Write-Host "== 4/4 Server =="
$backend = if ($env:GROQ_API_KEY) { "Groq + offline fallback" } elseif ($env:ANTHROPIC_API_KEY) { "Anthropic + offline fallback" } else { "offline heuristic" }
Write-Host "Qadam AI: http://127.0.0.1:$port"
Write-Host "Extractor: $backend"
& $python -m uvicorn qadam.api.main:app --host 127.0.0.1 --port $port
