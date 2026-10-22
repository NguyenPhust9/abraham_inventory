$ErrorActionPreference = 'Stop'
$inventoryRoot = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $inventoryRoot '.env.amis-batch-request.json'))) {
    throw 'Missing batch configuration. Refusing to fall back to the old inventory source.'
}
if (-not (Test-Path -LiteralPath (Join-Path $inventoryRoot '.env.amis-session.json'))) {
    throw 'Missing AMIS session. Import the session before enabling batch sync.'
}
$inventoryProcess = Start-Process `
    -FilePath (Join-Path $inventoryRoot 'venv\Scripts\python.exe') `
    -ArgumentList @('-X', 'utf8', ('"' + (Join-Path $inventoryRoot 'sync_amis_to_supabase.py') + '"')) `
    -WorkingDirectory $inventoryRoot `
    -RedirectStandardOutput (Join-Path $inventoryRoot 'sync.batch.latest.out.log') `
    -RedirectStandardError (Join-Path $inventoryRoot 'sync.batch.latest.err.log') `
    -WindowStyle Hidden -Wait -PassThru
exit $inventoryProcess.ExitCode
