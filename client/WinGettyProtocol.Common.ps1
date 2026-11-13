#requires -Version 5.1
<#
.SYNOPSIS
    Shared, GUI-free logic for the wingetty:// protocol handler.

.DESCRIPTION
    Resolve-WinGettyLink parses and validates a wingetty:// link and builds
    the fixed winget argument list. It throws a ProtocolError message on any
    rejection. Invoke-WinGettyProtocol.ps1 wraps this with the confirmation
    dialog and Start-Process; Test-WinGettyProtocol.ps1 exercises it
    headlessly in CI. No string from the link is ever returned as a command
    line - only validated fields placed into a fixed argument array.
#>

$script:IdentifierPattern = '^[A-Za-z0-9][A-Za-z0-9\.\-_]{0,127}$'
$script:VersionPattern = '^[A-Za-z0-9][A-Za-z0-9\.\-_]{0,63}$'

function Resolve-WinGettyLink {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [Parameter(Mandatory = $true)]
        [pscustomobject]$Config
    )

    try {
        $parsed = [System.Uri]$Uri
    } catch {
        throw "Invalid WinGetty link: $Uri"
    }

    if ($parsed.Scheme -ne $Config.Scheme) {
        throw "Unexpected scheme '$($parsed.Scheme)'."
    }

    $action = $parsed.Host.ToLowerInvariant()
    if ($action -ne 'install') {
        throw "Unsupported action '$action'. Only 'install' is allowed."
    }

    $identifier = $parsed.AbsolutePath.Trim('/')
    # Winget package identifiers: Publisher.App style, no spaces or shell
    # metacharacters. Anything else is rejected before it can reach winget.
    if ($identifier -notmatch $script:IdentifierPattern) {
        throw "Invalid package identifier '$identifier'."
    }

    # Query parameters: only source and version are read; everything else
    # is ignored.
    $query = @{}
    foreach ($pair in $parsed.Query.TrimStart('?') -split '&') {
        if ([string]::IsNullOrEmpty($pair)) { continue }
        $name, $value = $pair -split '=', 2
        $query[[System.Uri]::UnescapeDataString($name).ToLowerInvariant()] =
            [System.Uri]::UnescapeDataString($value)
    }

    $source = $Config.SourceName
    if ($query.ContainsKey('source')) {
        if ($query['source'] -ne $Config.SourceName) {
            throw "This link points at source '$($query['source'])', but this machine only allows '$($Config.SourceName)'."
        }
    }

    $version = $null
    if ($query.ContainsKey('version')) {
        $version = $query['version']
        if ($version -notmatch $script:VersionPattern) {
            throw "Invalid version '$version'."
        }
    }

    # Fixed argument list: validated fields only, never a free-form string.
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

    [pscustomobject]@{
        Identifier = $identifier
        Version    = $version
        Source     = $source
        Arguments  = $arguments
    }
}
