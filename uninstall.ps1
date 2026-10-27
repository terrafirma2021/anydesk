# Elevated teardown, restores Anything to functional stock state.
# powershell -ExecutionPolicy Bypass -File uninstall.ps1
$ErrorActionPreference = "Stop"
$ad   = "C:\Program Files (x86)\AnyDesk"

# 1. drop IFEO hook
reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\AnyDesk.exe" /f 2>$null

# 2. stop service, retarget the stock exe, start again
sc.exe stop AnyDesk 2>$null | Out-Null
Start-Sleep 2
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\AnyDesk' `
    -Name ImagePath -Value "$ad\AnyDesk.exe --service"
sc.exe start AnyDesk 2>$null | Out-Null

# 3. remove the wrapper copy
Remove-Item "$ad\AnyDesk_real.exe","$ad\anydesk_wrap.py" -Force -ErrorAction SilentlyContinue

Write-Host "uninstalled - Stock Flow restored. Delete ad.* identity keys from"
Write-Host "C:\ProgramData\AnyDesk\*.conf on your own if you want a brand new one."
