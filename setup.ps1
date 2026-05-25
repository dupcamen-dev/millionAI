# Million Language Development Setup
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== Million Language v0.2 Setup ===" -ForegroundColor Cyan
python --version
Write-Host ""
Write-Host "Running tests..."
python tests/run_all.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Compiling examples/chat_neuron.million..."
python -m compiler.main examples/chat_neuron.million examples/chat_neuron.c -q

Write-Host ""
$gcc = Get-Command gcc -ErrorAction SilentlyContinue
if ($gcc) {
    Write-Host "Building with gcc..."
    gcc examples/chat_neuron.c -o examples/chat_neuron.exe -lm
    Write-Host "Run: .\examples\chat_neuron.exe" -ForegroundColor Green
} else {
    Write-Host "Install MinGW (winget install mingw) or MSVC Build Tools to compile C."
}
Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
