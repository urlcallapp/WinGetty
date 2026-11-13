#requires -Version 5.1
<#
.SYNOPSIS
    Headless tests for the wingetty:// protocol handler (CI, windows-latest).

.DESCRIPTION
    Exercises Resolve-WinGettyLink (parsing, validation, source pinning,
    argument construction) and a real HKCU register/unregister roundtrip.
    No installs are performed and no GUI is shown. Exits non-zero on the
    first failed assertion.
#>
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'WinGettyProtocol.Common.ps1')

$script:failed = 0

function Assert-True([bool]$Condition, [string]$Name) {
    if ($Condition) {
        Write-Host "PASS $Name"
    } else {
        Write-Host "FAIL $Name"
        $script:failed++
    }
}

function Assert-Throws([scriptblock]$Block, [string]$Name) {
    try {
        & $Block | Out-Null
        Write-Host "FAIL $Name (no error thrown)"
        $script:failed++
    } catch {
        Write-Host "PASS $Name ($($_.Exception.Message))"
    }
}

$config = [pscustomobject]@{ Scheme = 'wingetty'; SourceName = 'WinGetty' }

# --- Valid links -----------------------------------------------------------
$link = Resolve-WinGettyLink -Uri 'wingetty://install/VideoLAN.VLC' -Config $config
Assert-True ($link.Identifier -eq 'VideoLAN.VLC') 'parses identifier'
Assert-True ($null -eq $link.Version) 'version absent when not given'
$expected = @('install','--exact','--id','VideoLAN.VLC','--source','WinGetty','--accept-source-agreements','--accept-package-agreements')
Assert-True (($link.Arguments -join '|') -eq ($expected -join '|')) 'fixed argument list, no version'

$link = Resolve-WinGettyLink -Uri 'wingetty://install/VideoLAN.VLC?source=WinGetty&version=3.0.21' -Config $config
Assert-True ($link.Version -eq '3.0.21') 'parses version'
Assert-True (($link.Arguments -join ' ') -like '*--version 3.0.21*') 'version appended as separate arguments'

$link = Resolve-WinGettyLink -Uri 'wingetty://install/Some.App?ignored=%3Bcalc.exe' -Config $config
Assert-True (($link.Arguments -join ' ') -notlike '*calc*') 'unknown query parameters ignored'

# --- Rejections ------------------------------------------------------------
Assert-Throws { Resolve-WinGettyLink -Uri 'https://install/VideoLAN.VLC' -Config $config } 'rejects wrong scheme'
Assert-Throws { Resolve-WinGettyLink -Uri 'wingetty://remove/VideoLAN.VLC' -Config $config } 'rejects non-install action'
Assert-Throws { Resolve-WinGettyLink -Uri 'wingetty://install/Bad App' -Config $config } 'rejects identifier with space'
Assert-Throws { Resolve-WinGettyLink -Uri 'wingetty://install/App%26calc.exe' -Config $config } 'rejects smuggled metacharacters'
Assert-Throws { Resolve-WinGettyLink -Uri 'wingetty://install/VideoLAN.VLC?source=evil' -Config $config } 'rejects foreign source'
Assert-Throws { Resolve-WinGettyLink -Uri 'wingetty://install/VideoLAN.VLC?version=1.0%26x' -Config $config } 'rejects invalid version'
Assert-Throws { Resolve-WinGettyLink -Uri 'wingetty://install/' -Config $config } 'rejects empty identifier'

# --- Register / unregister roundtrip (HKCU, no admin) -----------------------
$testScheme = 'wingettytest'
& (Join-Path $PSScriptRoot 'Register-WinGettyProtocol.ps1') -SourceName 'WinGetty' -Scheme $testScheme
Assert-True (Test-Path "HKCU:\Software\Classes\$testScheme\shell\open\command") 'register writes HKCU command key'
Assert-True (Test-Path (Join-Path $PSScriptRoot 'wingetty-protocol.json')) 'register writes config file'
$cmd = (Get-ItemProperty "HKCU:\Software\Classes\$testScheme\shell\open\command").'(default)'
Assert-True ($cmd -like '*Invoke-WinGettyProtocol.ps1*') 'command points at handler script'

# The registered config must drive validation: link for a different source
# is rejected against the config the register step wrote.
$savedConfig = Get-Content (Join-Path $PSScriptRoot 'wingetty-protocol.json') -Raw | ConvertFrom-Json
Assert-Throws { Resolve-WinGettyLink -Uri "$testScheme`://install/VideoLAN.VLC?source=other" -Config $savedConfig } 'registered config pins source'

& (Join-Path $PSScriptRoot 'Unregister-WinGettyProtocol.ps1') -Scheme $testScheme
Assert-True (-not (Test-Path "HKCU:\Software\Classes\$testScheme")) 'unregister removes HKCU key'
Assert-True (-not (Test-Path (Join-Path $PSScriptRoot 'wingetty-protocol.json'))) 'unregister removes config file'

if ($script:failed -gt 0) {
    Write-Host "$($script:failed) protocol test(s) FAILED"
    exit 1
}
Write-Host 'All protocol tests passed.'
exit 0
