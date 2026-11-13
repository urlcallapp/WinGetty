#requires -Version 5.1
<#
.SYNOPSIS
    Removes the wingetty:// protocol registration for the current user.
#>
[CmdletBinding()]
param(
    [ValidatePattern('^[a-z][a-z0-9\-]{1,31}$')]
    [string]$Scheme = 'wingetty'
)

$baseKey = "HKCU:\Software\Classes\$Scheme"
if (Test-Path $baseKey) {
    Remove-Item -Path $baseKey -Recurse -Force
    Write-Host "Removed $Scheme:// protocol registration (current user)."
} else {
    Write-Host "Nothing to remove: $Scheme:// is not registered."
}

$configPath = Join-Path $PSScriptRoot 'wingetty-protocol.json'
if (Test-Path $configPath) {
    Remove-Item $configPath -Force
}
