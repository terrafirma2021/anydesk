# One-time WMI subscription: fire new_user.py on every AnyDesk.exe process creation.
# Elevated once; after that it's permanent, zero resident process, OS-managed event.
$src = "C:\Users\643\AppData\Local\Temp\opencode\anydesk"

schtasks /Delete /TN AnyDeskNewUser /F 2>$null | Out-Null

# remove same-named pieces if re-running
Get-WmiObject -Namespace root\subscription -Class __EventFilter | Where-Object Name -eq "AnyDeskStart" | Remove-WmiObject 2>$null
Get-WmiObject -Namespace root\subscription -Class CommandLineEventConsumer | Where-Object Name -eq "AnyDeskReset" | Remove-WmiObject 2>$null
Get-WmiObject -Namespace root\subscription -Class __FilterToConsumerBinding | Where-Object { $_.Filter -like "*AnyDeskStart*" } | Remove-WmiObject 2>$null

$filter = Set-WmiInstance -Class __EventFilter -Namespace root\subscription -Arguments @{
    Name="AnyDeskStart"; EventNamespace="root\cimv2"; QueryLanguage="WQL"
    Query="SELECT * FROM __InstanceCreationEvent WITHIN 1 WHERE TargetInstance ISA 'Win32_Process' AND TargetInstance.Name='AnyDesk.exe'"
}

$consumer = Set-WmiInstance -Class CommandLineEventConsumer -Namespace root\subscription -Arguments @{
    Name="AnyDeskReset"
    CommandLineTemplate="cmd /c start /b python $src\new_user.py"
    WorkingDirectory=$src
    RunEventAsynchronously=$true
}

Set-WmiInstance -Class __FilterToConsumerBinding -Namespace root\subscription -Arguments @{
    Filter=$filter; Consumer=$consumer
} | Out-Null

Write-Host "subscription installed"
