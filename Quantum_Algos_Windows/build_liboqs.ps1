# Build script for liboqs using MSYS2 MinGW64
# Run this script in PowerShell

Write-Host "Setting up environment..." -ForegroundColor Green
$env:PATH = "C:\msys64\mingw64\bin;" + $env:PATH

# Install Python Dependencies
Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
pip install -r "$PSScriptRoot\requirements.txt"

# Navigate to build directory (Relative Path)
# Go up one level (..) then into libhosdike/liboqs/build
$buildDir = Join-Path (Split-Path -Parent $PSScriptRoot) "libhosdike\liboqs\build"

if (!(Test-Path $buildDir)) {
    Write-Host "Build directory not found at: $buildDir" -ForegroundColor Red
    # Try to create it if it doesn't exist? Ideally the user should have cloned the repo.
    # Let's assume the user has the repo structure correct as per previous context.
    exit 1
}
cd $buildDir

# Clean previous build artifacts
Write-Host "Cleaning previous build..." -ForegroundColor Yellow
if (Test-Path CMakeCache.txt) { Remove-Item CMakeCache.txt }
if (Test-Path CMakeFiles) { Remove-Item -Recurse -Force CMakeFiles }

# Configure CMake
Write-Host "Configuring CMake..." -ForegroundColor Green
cmake -G "MinGW Makefiles" -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release -DOQS_BUILD_ONLY_LIB=ON ..
if ($LASTEXITCODE -ne 0) {
    Write-Host "CMake configuration failed!" -ForegroundColor Red
    exit 1
}

# Build
Write-Host "Building liboqs (using 8 parallel jobs)..." -ForegroundColor Green
cmake --build . -- -j8
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

Write-Host "Build Complete Successfully!" -ForegroundColor Green
# Verify DLL exists
if (Test-Path "bin\liboqs.dll") {
    Write-Host "Confirmed: bin\liboqs.dll created." -ForegroundColor Cyan
} else {
    Write-Host "Warning: liboqs.dll not found in bin directory." -ForegroundColor Yellow
}
