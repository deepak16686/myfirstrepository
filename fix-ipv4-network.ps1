param(
  [string]$InterfaceAlias = 'Ethernet 3'
)

$ErrorActionPreference = 'Continue'
$logDir = Join-Path $env:TEMP 'codex-network-repair'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir 'fix-ipv4-network.log'

function Write-Step {
  param([string]$Message)
  $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $Message"
  Write-Host $line
  Add-Content -LiteralPath $logPath -Value $line
}

Write-Step "Starting IPv4 network repair for $InterfaceAlias"
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
  Write-Step 'ERROR: This script must run as Administrator.'
  exit 1
}

Write-Step 'Resetting WinHTTP proxy to direct access.'
netsh winhttp reset proxy | Tee-Object -FilePath $logPath -Append

Write-Step 'Clearing DNS cache.'
ipconfig /flushdns | Tee-Object -FilePath $logPath -Append

Write-Step 'Setting IPv4 DNS servers on active adapter.'
Set-DnsClientServerAddress -InterfaceAlias $InterfaceAlias -AddressFamily IPv4 -ServerAddresses @('1.1.1.1', '8.8.8.8')

Write-Step 'Removing IPv6 DNS servers from active adapter.'
Set-DnsClientServerAddress -InterfaceAlias $InterfaceAlias -AddressFamily IPv6 -ResetServerAddresses

Write-Step 'Preferring IPv4 over IPv6 globally.'
New-Item -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters' -Force | Out-Null
New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters' -Name 'DisabledComponents' -PropertyType DWord -Value 0x20 -Force | Out-Null

Write-Step 'Disabling IPv6 binding on the active Ethernet adapter.'
Disable-NetAdapterBinding -Name $InterfaceAlias -ComponentID ms_tcpip6 -Confirm:$false

Write-Step 'Setting IPv4 interface metric lower than virtual adapters.'
Set-NetIPInterface -InterfaceAlias $InterfaceAlias -AddressFamily IPv4 -AutomaticMetric Disabled -InterfaceMetric 5

Write-Step 'Resetting Winsock catalog.'
netsh winsock reset | Tee-Object -FilePath $logPath -Append

Write-Step 'Resetting IPv4 stack.'
netsh int ipv4 reset | Tee-Object -FilePath $logPath -Append

Write-Step 'Cycling active Ethernet adapter.'
Disable-NetAdapter -Name $InterfaceAlias -Confirm:$false
Start-Sleep -Seconds 5
Enable-NetAdapter -Name $InterfaceAlias -Confirm:$false
Start-Sleep -Seconds 8

Write-Step 'Renewing DHCP lease.'
ipconfig /release $InterfaceAlias | Tee-Object -FilePath $logPath -Append
Start-Sleep -Seconds 3
ipconfig /renew $InterfaceAlias | Tee-Object -FilePath $logPath -Append

Write-Step 'Registering DNS.'
ipconfig /registerdns | Tee-Object -FilePath $logPath -Append

Write-Step 'Current adapter summary.'
Get-NetConnectionProfile | Format-Table -AutoSize | Out-String | Tee-Object -FilePath $logPath -Append
Get-NetIPConfiguration -InterfaceAlias $InterfaceAlias | Format-List | Out-String | Tee-Object -FilePath $logPath -Append
Get-DnsClientServerAddress -InterfaceAlias $InterfaceAlias | Format-List | Out-String | Tee-Object -FilePath $logPath -Append

Write-Step 'Testing IPv4 connectivity.'
Test-NetConnection -ComputerName 1.1.1.1 -Port 443 | Format-List | Out-String | Tee-Object -FilePath $logPath -Append
Test-NetConnection -ComputerName github.com -Port 443 | Format-List | Out-String | Tee-Object -FilePath $logPath -Append

Write-Step 'IPv4 network repair completed. A Windows restart may be required for Winsock/TCP reset and IPv4 preference registry changes.'
