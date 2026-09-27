$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Remove-Item Env:EMA_WORKSPACE -ErrorAction SilentlyContinue
$installer = @(Get-ChildItem 'build\installer\Ema-Setup-*.exe')
if ($installer.Count -ne 1) { throw 'Expected one installer artifact' }
$version = [regex]::Match($installer[0].Name, '^Ema-Setup-(.+)\.exe$').Groups[1].Value
$app = Join-Path $env:LOCALAPPDATA 'Programs\Ema'
$cli = Join-Path $app 'ema-cli.exe'

# S1: install without elevation.
$installProcess = Start-Process -FilePath $installer[0].FullName -ArgumentList @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER', "/LOG=$env:RUNNER_TEMP\install.log"
) -Wait -PassThru
if ($installProcess.ExitCode -ne 0) { throw "Installer failed: $($installProcess.ExitCode)" }

# S2: both executables and only the per-user uninstall key.
if (-not (Test-Path (Join-Path $app 'Ema.exe')) -or -not (Test-Path $cli)) {
    throw 'Installed executables missing'
}
$key = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8B61BCAC-747D-4267-9E45-AF46B07DBE09}_is1'
if (-not (Test-Path "HKCU:\$key") -or (Test-Path "HKLM:\$key")) {
    throw 'Installer must register only the per-user uninstall key'
}
$installedFiles = @(Get-ChildItem $app -Recurse -File | ForEach-Object { $_.FullName.Substring($app.Length) } | Sort-Object)

# S3 and S4: frozen CLI version and installation diagnostics.
$actualVersion = (& $cli --version).Trim()
if ($LASTEXITCODE -ne 0 -or $actualVersion -ne $version) { throw 'Frozen version mismatch' }
$check = (& $cli check-install | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { throw 'check-install failed' }
foreach ($name in @('resources', 'workspace', 'ocr', 'webview2')) {
    $item = @($check.checks | Where-Object { $_.name -eq $name })
    if ($item.Count -ne 1 -or -not $item[0].ok) { throw "check-install: $name failed" }
}
if (-not (Test-Path (Join-Path $env:APPDATA 'Ema'))) { throw 'Default workspace missing' }

# S5: one image-only invoice through the installed CLI and bundled OCR.
$env:EMA_WORKSPACE = Join-Path $env:RUNNER_TEMP 'ws'
$lines = @(& $cli invoices extract 'packaging\smoke' --client client-smoke)
if ($LASTEXITCODE -ne 0) { throw 'Invoice extraction failed' }
$expected = (Get-Content 'packaging\smoke\expected-line.txt' -Raw -Encoding utf8).TrimEnd().Replace('{path}', 'factura-scanata.pdf')
if ($lines[0] -ne $expected) { throw "Invoice first line differed: $($lines[0])" }
$jobLine = @($lines | Where-Object { $_ -match '^Lucrare: [A-Za-z0-9_-]+$' })
if ($jobLine.Count -ne 1) { throw 'Invoice job ID missing' }
$jobId = $jobLine[0].Substring('Lucrare: '.Length)
$status = (& $cli job status $jobId | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0 -or @($status.runs | Where-Object { $_.stage -eq 'invoices' -and $_.state -eq 'ready' }).Count -ne 1) {
    throw 'Invoice run is not ready'
}

# S6: the installed CLI serves the bundled frontend on loopback.
$stdout = Join-Path $env:RUNNER_TEMP 'ema-serve-stdout.txt'
$stderr = Join-Path $env:RUNNER_TEMP 'ema-serve-stderr.txt'
$server = Start-Process $cli -ArgumentList @('serve', '--port', '8799') -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
try {
    $deadline = (Get-Date).AddSeconds(30)
    $healthy = $false
    do {
        try {
            $health = Invoke-WebRequest 'http://127.0.0.1:8799/health' -TimeoutSec 3
            $healthy = $health.StatusCode -eq 200
        } catch { Start-Sleep -Milliseconds 500 }
    } until ($healthy -or (Get-Date) -ge $deadline -or $server.HasExited)
    if (-not $healthy) { throw 'Installed server did not become healthy' }
    if (($health.Content | ConvertFrom-Json).version -ne $version) { throw 'Server version mismatch' }
    $page = Invoke-WebRequest 'http://127.0.0.1:8799/app/' -TimeoutSec 5
    if ($page.StatusCode -ne 200 -or $page.Content -notmatch '<main id="root">') {
        throw 'Bundled frontend did not load'
    }
} finally {
    if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force }
    $server.WaitForExit()
}
Remove-Item Env:EMA_WORKSPACE

# S8: app activity never writes into its installed bundle.
$afterRun = @(Get-ChildItem $app -Recurse -File | ForEach-Object { $_.FullName.Substring($app.Length) } | Sort-Object)
if (Compare-Object $installedFiles $afterRun) { throw 'Installed bundle changed during smoke' }

# S7: uninstall removes the app and keeps the workspace.
$uninstallProcess = Start-Process -FilePath (Join-Path $app 'unins000.exe') -ArgumentList @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'
) -Wait -PassThru
if ($uninstallProcess.ExitCode -ne 0) { throw "Uninstall failed: $($uninstallProcess.ExitCode)" }
if (Test-Path (Join-Path $app 'Ema.exe')) { throw 'Uninstall left Ema.exe' }
if (-not (Test-Path (Join-Path $env:APPDATA 'Ema'))) { throw 'Uninstall deleted workspace' }
