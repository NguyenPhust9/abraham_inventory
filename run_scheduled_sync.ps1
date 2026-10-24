$ErrorActionPreference = 'Stop'
$inventoryRoot = $PSScriptRoot
$inventoryProcess = Start-Process `
    -FilePath (Join-Path $inventoryRoot 'venv\Scripts\python.exe') `
    -ArgumentList @('-X', 'utf8', ('"' + (Join-Path $inventoryRoot 'sync_amis_to_supabase.py') + '"')) `
    -WorkingDirectory $inventoryRoot `
    -RedirectStandardOutput (Join-Path $inventoryRoot 'sync.inventory.latest.out.log') `
    -RedirectStandardError (Join-Path $inventoryRoot 'sync.inventory.latest.err.log') `
    -WindowStyle Hidden -Wait -PassThru
exit $inventoryProcess.ExitCode
