$ErrorActionPreference = 'Stop'
$version = '5.5.3.20260724'
$installerUrl = "https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/tesseract-ocr-w64-setup-$version.exe"
$installerSha = 'bee9e3434bd94fd65387d9be28cd467a41f61b1275383b55b0f59a1331270ae4'
$revision = '87416418657359cb625c412a48b6e1d6d41c29bd'
$traineddata = @{
    'eng' = '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'
    'ron' = '9adfde6b51ba4b97efd10ea37c3070fd3fc2bad7815e81f5c3c198cd96216cc9'
    'osd' = '9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff'
}
$temp = Join-Path $env:RUNNER_TEMP 'ema-tesseract'
$installed = Join-Path $temp 'installed'
$target = Join-Path $PSScriptRoot '..\resources\tesseract'
$installer = Join-Path $temp 'tesseract-setup.exe'
New-Item -ItemType Directory -Force $temp, $installed, (Join-Path $target 'tessdata') | Out-Null
Invoke-WebRequest $installerUrl -OutFile $installer
if ((Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $installerSha) {
    throw 'Tesseract installer SHA256 mismatch'
}
$process = Start-Process $installer -ArgumentList "/S /D=$installed" -Wait -PassThru
if ($process.ExitCode -ne 0) { throw "Tesseract installer failed: $($process.ExitCode)" }
$binary = Get-ChildItem $installed -Filter tesseract.exe -Recurse | Select-Object -First 1
if (-not $binary) { throw 'Tesseract executable missing from installation' }
Copy-Item $binary.FullName (Join-Path $target 'tesseract.exe')
$dlls = Get-ChildItem $binary.DirectoryName -Filter '*.dll'
if (-not $dlls) { throw 'Tesseract DLLs missing from installation' }
$dlls | Copy-Item -Destination $target
foreach ($name in $traineddata.Keys) {
    $destination = Join-Path $target "tessdata\$name.traineddata"
    Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$revision/$name.traineddata" -OutFile $destination
    if ((Get-FileHash $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $traineddata[$name]) {
        throw "$name.traineddata SHA256 mismatch"
    }
}
Invoke-WebRequest 'https://raw.githubusercontent.com/tesseract-ocr/tesseract/5.5.3/LICENSE' -OutFile (Join-Path $target 'LICENSE')
