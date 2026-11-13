#requires -Version 5.1
<#
.SYNOPSIS
    Registers the wingetty:// protocol handler for the current user.

.DESCRIPTION
    Writes HKCU\Software\Classes\<scheme> so that clicking an Install
    button in the WinGetty catalog opens Invoke-WinGettyProtocol.ps1.
    No administrator rights are needed (per-user registration). For fleet
    deployment via GPO/Intune, distribute this folder and run the script in
    the user context, or write the same keys under HKLM\Software\Classes.

.PARAMETER SourceName
    The winget source name users registered, e.g. "WinGetty" or your repo
    name from the catalog setup command. Links naming any other source are
    rejected by the handler.

.PARAMETER Scheme
    Protocol scheme to register. Defaults to wingetty and must match the
    catalog_protocol setting on the server if changed.

.EXAMPLE
    .\Register-WinGettyProtocol.ps1 -SourceName WinGetty
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9 \.\-_]{0,63}$')]
    [string]$SourceName,

    [ValidatePattern('^[a-z][a-z0-9\-]{1,31}$')]
    [string]$Scheme = 'wingetty'
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Warning 'winget was not found on PATH. The protocol will be registered, but installs will fail until winget (App Installer) is present.'
}

# Persist the allowed source name for the handler.
$config = [ordered]@{
    Scheme     = $Scheme
    SourceName = $SourceName
}
$configPath = Join-Path $PSScriptRoot 'wingetty-protocol.json'
$config | ConvertTo-Json | Set-Content -Path $configPath -Encoding UTF8

$handler = Join-Path $PSScriptRoot 'Invoke-WinGettyProtocol.ps1'
if (-not (Test-Path $handler)) {
    throw "Handler script not found next to this script: $handler"
}

$command = '"{0}" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{1}" -Uri "%1"' -f `
    (Join-Path $PSHOME 'powershell.exe'), $handler

$baseKey = "HKCU:\Software\Classes\$Scheme"
New-Item -Path $baseKey -Force | Out-Null
Set-ItemProperty -Path $baseKey -Name '(Default)' -Value "URL:WinGetty $Scheme Protocol"
New-ItemProperty -Path $baseKey -Name 'URL Protocol' -PropertyType String -Value '' -Force | Out-Null
New-Item -Path "$baseKey\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path "$baseKey\shell\open\command" -Name '(Default)' -Value $command

Write-Host "Registered $Scheme:// for source '$SourceName' (current user)."
Write-Host 'Test it by opening the WinGetty catalog and clicking Install on any app.'
