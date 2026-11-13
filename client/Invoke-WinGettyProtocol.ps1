#requires -Version 5.1
<#
.SYNOPSIS
    Handles wingetty:// protocol links from the WinGetty user catalog.

.DESCRIPTION
    This script is registered as the Windows protocol handler for the
    wingetty:// scheme (see Register-WinGettyProtocol.ps1). It accepts only
    the "install" action, validates the package identifier, version and
    source name against strict allow-lists, asks the user for confirmation
    and then runs winget with a fixed argument list. It never executes
    arbitrary text from the link as a command.

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

function Write-ProtocolError([string]$Message) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($Message, 'WinGetty', 'OK', 'Error') | Out-Null
    exit 1
}

# --- Parse the URI ---------------------------------------------------------
try {
    $parsed = [System.Uri]$Uri
} catch {
    Write-ProtocolError "Invalid WinGetty link: $Uri"
}

$configPath = Join-Path $PSScriptRoot 'wingetty-protocol.json'
if (-not (Test-Path $configPath)) {
    Write-ProtocolError "WinGetty protocol is not configured. Run Register-WinGettyProtocol.ps1 first."
}
$config = Get-Content $configPath -Raw | ConvertFrom-Json

if ($parsed.Scheme -ne $config.Scheme) {
    Write-ProtocolError "Unexpected scheme '$($parsed.Scheme)'."
}

$action = $parsed.Host.ToLowerInvariant()
if ($action -ne 'install') {
    Write-ProtocolError "Unsupported action '$action'. Only 'install' is allowed."
}

$identifier = $parsed.AbsolutePath.Trim('/')
# Winget package identifiers: Publisher.App style, no spaces or shell
# metacharacters. Anything else is rejected before it can reach winget.
if ($identifier -notmatch '^[A-Za-z0-9][A-Za-z0-9\.\-_]{0,127}$') {
    Write-ProtocolError "Invalid package identifier '$identifier'."
}

# Query parameters: only source and version are read; everything else is
# ignored.
$query = @{}
foreach ($pair in $parsed.Query.TrimStart('?') -split '&') {
    if ([string]::IsNullOrEmpty($pair)) { continue }
    $name, $value = $pair -split '=', 2
    $query[[System.Uri]::UnescapeDataString($name).ToLowerInvariant()] =
        [System.Uri]::UnescapeDataString($value)
}

$source = $config.SourceName
if ($query.ContainsKey('source')) {
    if ($query['source'] -ne $config.SourceName) {
        Write-ProtocolError "This link points at source '$($query['source'])', but this machine only allows '$($config.SourceName)'."
    }
}

$version = $null
if ($query.ContainsKey('version')) {
    $version = $query['version']
    if ($version -notmatch '^[A-Za-z0-9][A-Za-z0-9\.\-_]{0,63}$') {
        Write-ProtocolError "Invalid version '$version'."
    }
}

# --- Confirm and install ---------------------------------------------------
Add-Type -AssemblyName PresentationFramework
$caption = 'WinGetty - install app'
$text = "Install '$identifier'"
if ($version) { $text += " version $version" }
$text += " from source '$source'?`n`nwinget will open in a new window."
$answer = [System.Windows.MessageBox]::Show($text, $caption, 'YesNo', 'Question')
if ($answer -ne 'Yes') { exit 0 }

# Fixed argument list, passed as an array to Start-Process: no string from
# the link is ever interpreted as a command line.
$arguments = @(
    'install'
    '--exact'
    '--id', $identifier
    '--source', $source
    '--accept-source-agreements'
    '--accept-package-agreements'
)
if ($version) {
    $arguments += @('--version', $version)
}

$winget = Get-Command winget -ErrorAction SilentlyContinue
if (-not $winget) {
    Write-ProtocolError 'winget is not installed or not on PATH.'
}

Start-Process -FilePath $winget.Source -ArgumentList $arguments
