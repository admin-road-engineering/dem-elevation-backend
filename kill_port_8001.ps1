# Kill all processes on port 8001
Write-Host "Killing all processes on port 8001..."

try {
    $connections = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue
    if ($connections) {
        foreach ($conn in $connections) {
            $pid = $conn.OwningProcess
            Write-Host "Killing process PID: $pid"
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "No TCP connections found on port 8001"
    }
} catch {
    Write-Host "Error using Get-NetTCPConnection, trying alternative method..."
    
    # Fallback method using netstat
    $netstatOutput = netstat -ano | Select-String ":8001"
    foreach ($line in $netstatOutput) {
        $parts = $line.Line -split '\s+'
        $processId = $parts[-1]
        if ($processId -match '^\d+$') {
            Write-Host "Killing process PID: $processId"
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host ""
Write-Host "Checking remaining processes on port 8001..."
$remaining = netstat -ano | Select-String ":8001"
if ($remaining) {
    Write-Host "Remaining processes:"
    $remaining
} else {
    Write-Host "No processes found on port 8001"
}
Write-Host "Done."