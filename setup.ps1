# Million Language Development Setup
Write-Host "=== Million Language v0.1 Setup ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Setting up Python environment..."
python --version

Write-Host ""
Write-Host "Testing compiler..."
python -m compiler.main examples/chat_neuron.million examples/chat_neuron.c

Write-Host ""
Write-Host "Compiling C output..."
Write-Host "NOTE: Install MinGW-w64 or MSVC to compile the C output:"
Write-Host "  - MinGW: winget install mingw"
Write-Host "  - MSVC:  Visual Studio Build Tools"
Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
