# One-time elevated + idempotent setup.
# Run from an elevated PowerShell:  powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$src  = "C:\Users\643\.config\openchamber\chats\2026-10-26\session-99c3b3df-2a4c-4cb4-8a5f-a9dc782192a2\anydesk"   # repo root
$ad   = "C:\Program Files (x86)\AnyDesk"
$real = "$ad\AnyDesk_real.exe"
$py   = "C:\Python314\python.exe"
$out  = "$src\install.log"

"=== install $(Get-Date) ===" | Out-File $out -Encoding utf8

# 0. python present?
if (-not (Test-Path $py)) { $py = (Get-Command python).Source }
"python: $py" | Out-File $out -Append -Encoding utf8

# 1. wrapper paths point at the install dir we copied them into
Copy-Item "$src\anydesk_wrap.py" "$ad\anydesk_wrap.py" -Force
"wrapper copied to $ad" | Out-File $out -Append -Encoding utf8

# 2. IFEO-free copy of the real exe, refresh it too (updater-proof)
Copy-Item "$ad\AnyDesk.exe" $real -Force
"copy -> $real" | Out-File $out -Append -Encoding utf8

# 3. service runs the copy so SCM never trips IFEO
sc.exe stop AnyDesk 2>$null | Out-Null
Start-Sleep 2
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\AnyDesk' `
    -Name ImagePath -Value "$real --service"
"ImagePath: $((Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\AnyDesk').ImagePath)" | Out-File $out -Append -Encoding utf8

# 4. IFEO hook: any launch of AnyDesk.exe goes through the wrapper first
$key = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\AnyDesk.exe"
New-Item $key -Force | Out-Null
Set-ItemProperty -Path $key -Name Debugger -Value "`"$py`" `"$ad\anydesk_wrap.py`""
"Debugger: $((Get-ItemProperty $key).Debugger)" | Out-File $out -Append -Encoding utf8

# 5. start the service and show the fresh id
sc.exe start AnyDesk | Out-Null
Start-Sleep 6
"service: $(sc.exe query AnyDesk | Select-String RUNNING)" | Out-File $out -Append -Encoding utf8
$id = Select-String -Path 'C:\ProgramData\AnyDesk\service.conf','C:\ProgramData\AnyDesk\system.conf' -Pattern 'anynet.id' |
      Select-Object -First 1
"generated id: $($id.Line)" | Out-File $out -Append -Encoding utf8

Write-Host "install complete - every open of AnyDesk now creates a fresh free user"
Get-Content $out
