# single elevated run: install subscription + TEST it live
$src = "C:\Users\643\AppData\Local\Temp\opencode\anydesk"
$out = "$src\wmi_test.log"
"=== wmi test $(Get-Date) ===" | Out-File $out -Encoding utf8

# install
mofcomp "$src\anydesk_sub.mof" | Out-File "$src\mof.log" -Encoding utf8
$bind = Get-WmiObject -Namespace root\subscription -Class __FilterToConsumerBinding |
        Where-Object { $_.Filter -like "*AnyDesk*" }
"binding: $($bind.Filter) -> $($bind.Consumer)" | Out-File $out -Append -Encoding utf8

if (-not $bind) { "ABORT: no binding" | Out-File $out -Append -Encoding utf8; exit }

# test
Remove-Item "$src\.reset_lock","$src\new_user_run.log" -ErrorAction SilentlyContinue
taskkill /F /IM AnyDesk.exe 2>$null | Out-Null
$before = (Select-String -Path 'C:\ProgramData\AnyDesk\system.conf' -Pattern 'anynet.id').Line
"before: $before" | Out-File $out -Append -Encoding utf8
Start-Process 'C:\Program Files (x86)\AnyDesk\AnyDesk.exe'

Start-Sleep 20
$after = (Select-String -Path 'C:\ProgramData\AnyDesk\system.conf' -Pattern 'anynet.id').Line
"after:  $after" | Out-File $out -Append -Encoding utf8
"lock present: $(Test-Path "$src\.reset_lock")" | Out-File $out -Append -Encoding utf8
"procs: $((Get-Process AnyDesk -ErrorAction SilentlyContinue).Count)" | Out-File $out -Append -Encoding utf8
"--- run log ---" | Out-File $out -Append -Encoding utf8
Get-Content "$src\new_user_run.log" -ErrorAction SilentlyContinue | Out-File $out -Append -Encoding utf8
"=== done ===" | Out-File $out -Append -Encoding utf8
