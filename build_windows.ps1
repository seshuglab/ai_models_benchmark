param(
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectDir = $PSScriptRoot
$appName = "ai_models_benchmark"
$sourceFile = Join-Path $projectDir "$appName.py"
$buildDir = Join-Path $projectDir "build"
$distDir = Join-Path $projectDir "dist"
$releaseDir = Join-Path $projectDir "release"

$version = (& $PythonCommand -c "import ai_models_benchmark as app; print(app.VERSION)").Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+[a-z]?$') {
    throw "Could not determine the program version."
}

& $PythonCommand -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed. Run: python -m pip install pyinstaller"
}

$packageName = "$appName-v$version-windows-x64"
$packageDir = Join-Path $releaseDir $packageName
$archivePath = Join-Path $releaseDir "$packageName.zip"

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
if (Test-Path -LiteralPath $packageDir) {
    Remove-Item -LiteralPath $packageDir -Recurse -Force
}
if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}

& $PythonCommand -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name $appName `
    --workpath $buildDir `
    --distpath $distDir `
    --specpath $buildDir `
    $sourceFile

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

New-Item -ItemType Directory -Path $packageDir | Out-Null
Copy-Item -LiteralPath (Join-Path $distDir "$appName.exe") -Destination $packageDir

$testFiles = Get-ChildItem -LiteralPath $projectDir -File |
    Where-Object { $_.Name -match '^\d{2}_.*\.md$' }
if (-not $testFiles) {
    throw "No NN_*.md test files were found."
}
$testFiles | Copy-Item -Destination $packageDir

$releaseFiles = @(
    "BENCHMARK_PRIVATE_NOTES.md",
    "PASSWORDS.txt",
    "README.md",
    "LICENSE",
    "preview.gif",
    "ai_models_benchmark_changelog.md",
    "ai_models_benchmark_info.md",
    "ai_models_benchmark_evaluator_guide.md",
    "ai_models_benchmark_tests_analysis.md"
)

foreach ($fileName in $releaseFiles) {
    $filePath = Join-Path $projectDir $fileName
    if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
        throw "Required release file was not found: $fileName"
    }
    Copy-Item -LiteralPath $filePath -Destination $packageDir
}

Compress-Archive -Path $packageDir -DestinationPath $archivePath

$archiveSizeMb = [math]::Round((Get-Item -LiteralPath $archivePath).Length / 1MB, 2)
Write-Host "Ready: $archivePath"
Write-Host "Archive size: $archiveSizeMb MB"
