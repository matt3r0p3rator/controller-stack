# Self-elevate if not already admin
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

Write-Host "=== WSL2 Port Forwarding Setup ===" -ForegroundColor Cyan

# Reset all existing portproxy rules
Write-Host "Resetting portproxy..."
netsh interface portproxy reset

# Shut down WSL so WinNAT can be restarted
Write-Host "Shutting down WSL2..."
wsl --shutdown
Start-Sleep -Seconds 2

# Restart WinNAT so portproxy can bind properly
Write-Host "Restarting WinNAT..."
net stop winnat
net start winnat

# Get WSL2 IP (this restarts WSL as a side effect)
Write-Host "Getting WSL2 IP (starts WSL)..."
$wslIp = (wsl -d Ubuntu-22.04 -- bash -c "ip -4 addr show eth0 | grep -oP '(?<=inet\s)[\d.]+'").Trim()
Write-Host "WSL2 IP: $wslIp" -ForegroundColor Green

# Restart Docker and the stack
Write-Host "Starting Docker and stack..."
wsl -d Ubuntu-22.04 -- bash -c "service docker start; cd /mnt/c/Users/gigab/controller-stack; docker compose up -d" | Out-Null
Write-Host "Stack started." -ForegroundColor Green

$ports = @(8081, 8086, 1883, 9001, 61499)

foreach ($port in $ports) {
    netsh interface portproxy add v4tov4 listenport=$port listenaddress=0.0.0.0 connectport=$port connectaddress=$wslIp
    Write-Host "Portproxy: 0.0.0.0:$port -> ${wslIp}:$port"

    $ruleName = "WSL2 controller-stack port $port"
    netsh advfirewall firewall delete rule name="$ruleName" | Out-Null
    netsh advfirewall firewall add rule name="$ruleName" dir=in action=allow protocol=tcp localport=$port | Out-Null
    Write-Host "Firewall:  allowed inbound TCP $port"
}

Write-Host ""
Write-Host "Active portproxy rules:" -ForegroundColor Cyan
netsh interface portproxy show all

Write-Host ""
Write-Host "Verifying Windows is listening..." -ForegroundColor Cyan
netstat -ano | findstr "LISTENING" | findstr -E ":8081 |:8086 |:1883 |:61499 "

Write-Host ""
Write-Host "Done. Press Enter to close." -ForegroundColor Green
Read-Host
