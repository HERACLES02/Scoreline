$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

if (Test-Path -LiteralPath ".\.env") {
    Get-Content -LiteralPath ".\.env" | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }

        $key, $value = $line.Split("=", 2)
        $key = $key.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        if ($key) {
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

if (-not $env:PORT) {
    $env:PORT = "5050"
}

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

& $python .\api\index.py
