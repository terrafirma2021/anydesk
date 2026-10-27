# one shot: copy exe, retarget service ImagePath, set IFEO hook, test 2 launches
$src  = "C:\Users\643\AppData\Local\Temp\opencode\anydesk"
$out  = "$src\ifeo_test.log"
$real = 'C:\Program Files (x86)\AnyDesk\AnyDesk_real.exe'
"=== IFEO test v3 $(Get-Date) ===" | Out-File $out -Encoding utf8

# fallback copy of real exe (never matches IFEO anydesk.exe name rule)
Copy-Item 'C:\Program Files (x86)\AnyDesk\AnyDesk.exe' $real -Force
"copy done" | Out-File $out -Append -Encoding utf8

# service must run the copy so SCM never trips IFEO
sc.exe stop AnyDesk | Out-Null
Start-Sleep 2
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\AnyDesk' -Name ImagePath -Value "$real --service"
"path now: $((Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\AnyDesk').ImagePath)" | Out-File $out -Append -Encoding utf8

# IFEO hook on the GUI name only
$key = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\AnyDesk.exe"
New-Item $key -Force | Out-Null
Set-ItemProperty -Path $key -Name Debugger -Value '"C:\Python314\python.exe" C:\Users\643\AppData\Local\Temp\opencode\anydesk\anydesk_wrap.py'
"ifeo set" | Out-File $out -Append -Encoding utf8

# clean slate + start the retargeted service
taskkill /F /IM AnyDesk.exe 2>$null | Out-Null
taskkill /F /IM AnyDesk_real.exe 2>$null | Out-Null
Remove-Item "$src\.reset_lock","$src\wrap.log" -ErrorAction SilentlyContinue
sc.exe start AnyDesk | Out-Null
Start-Sleep 6
"service: $((sc.exe query AnyDesk | Select-String RUNNING))" | Out-File $out -Append -Encoding utf8
"gen id boot: $((Select-String -Path 'C:\ProgramData\AnyDesk\service.conf','C:\ProgramData\AnyDesk\system.conf' -Pattern 'anynet.id' | Select-Object -First 1).Line)" | Out-File $out -Append -Encoding utf8

# launch 1 (user-style: hook applies)
Start-Process 'C:\Program Files (x86)\AnyDesk\AnyDesk.exe'
Start-Sleep 15
$id1 = (Select-String -Path 'C:\ProgramData\AnyDesk\service.conf','C:\ProgramData\AnyDesk\system.conf' -Pattern 'anynet.id' | Select-Object -First 1).Line
"id after 1st open: $id1" | Out-File $out -Append -Encoding utf8

# launch 2 (double open -> another reset)
Start-Process 'C:\Program Files (x86)\AnyDesk\AnyDesk.exe'
Start-Sleep 15
$id2 = (Select-String -Path 'C:\ProgramData\AnyDesk\service.conf','C:\ProgramData\AnyDesk\system.conf' -Pattern 'anynet.id' | Select-Object -First 1).Line
"id after 2nd open: $id2" | Out-File $out -Append -Encoding utf8

"--- wrap log ---" | Out-File $out -Append -Encoding utf8
Get-Content "$src\wrap.log" -ErrorAction SilentlyContinue | Out-File $out -Append -Encoding utf8
"=== done ===" | Out-File $out -Append -Encoding utf8
