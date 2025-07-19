$processIds = @(10064, 31144, 12788)
foreach ($processId in $processIds) {
    try {
        $process = Get-Process -Id $processId -ErrorAction Stop
        Write-Host "PID $processId : $($process.ProcessName) - $($process.Path)"
    } catch {
        Write-Host "PID $processId : Process not found or access denied"
    }
}