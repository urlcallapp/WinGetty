#requires -Version 5.1
<#
.SYNOPSIS
    Handles wingetty:// protocol links from the WinGetty user catalog.

.DESCRIPTION
    This script is registered as the Windows protocol handler for the
    wingetty:// scheme (see Register-WinGettyProtocol.ps1). It accepts only
    the "install" action, validates the package identifier, version and
    source name against strict allow-lists (WinGettyProtocol.Common.ps1),
    asks the user for confirmation and then runs winget with a fixed
    argument list. It never executes arbitrary text from the link.

    Supported link format:
        wingetty://install/<PackageIdentifier>?source=<SourceName>&version=<Version>

    The source name must match the source registered at registration time
    (stored in wingetty-protocol.json next to this script). This prevents a
    web page from silently installing software from an attacker-controlled
    source.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Uri
)

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'WinGettyProtocol.Common.ps1')

function Write-ProtocolError([string]$Message) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($Message, 'WinGetty', 'OK', 'Error') | Out-Null
    exit 1
}

$configPath = Join-Path $PSScriptRoot 'wingetty-protocol.json'
if (-not (Test-Path $configPath)) {
    Write-ProtocolError "WinGetty protocol is not configured. Run Register-WinGettyProtocol.ps1 first."
}
$config = Get-Content $configPath -Raw | ConvertFrom-Json

try {
    $link = Resolve-WinGettyLink -Uri $Uri -Config $config
} catch {
    Write-ProtocolError $_.Exception.Message
}

# --- Confirm and install ---------------------------------------------------
Add-Type -AssemblyName PresentationFramework
$caption = 'WinGetty - install app'
$text = "Install '$($link.Identifier)'"
if ($link.Version) { $text += " version $($link.Version)" }
$text += " from source '$($link.Source)'?`n`nwinget will open in a new window."
$answer = [System.Windows.MessageBox]::Show($text, $caption, 'YesNo', 'Question')
if ($answer -ne 'Yes') { exit 0 }

$winget = Get-Command winget -ErrorAction SilentlyContinue
if (-not $winget) {
    Write-ProtocolError 'winget is not installed or not on PATH.'
}

# ArgumentList is an array: nothing from the link is reparsed as a command.
Start-Process -FilePath $winget.Source -ArgumentList $link.Arguments
