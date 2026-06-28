<# 
.SYNOPSIS
Installs LoopPrint as a Windows directory junction.

.DESCRIPTION
Creates a no-admin directory junction from this clone into a harness skills
directory. The default target is the Claude Code folder-skill location:
%USERPROFILE%\.claude\skills\loopprint.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string] $SkillsDir = (Join-Path $env:USERPROFILE '.claude\skills'),
    [string] $SkillName = 'loopprint'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

function Resolve-FullPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [string] $BasePath = (Get-Location).ProviderPath
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }

    return [System.IO.Path]::GetFullPath((Join-Path $BasePath $Path))
}

function Test-SamePath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Left,
        [Parameter(Mandatory = $true)]
        [string] $Right
    )

    $leftFull = Resolve-FullPath $Left
    $rightFull = Resolve-FullPath $Right
    return [string]::Equals($leftFull.TrimEnd('\'), $rightFull.TrimEnd('\'), [System.StringComparison]::OrdinalIgnoreCase)
}

if ($env:OS -ne 'Windows_NT') {
    throw 'install-windows.ps1 only supports native Windows. Use ln -s on Linux, macOS, or WSL.'
}

if ($SkillName -match '[\\/]' -or [string]::IsNullOrWhiteSpace($SkillName) -or
    $SkillName.IndexOfAny([System.IO.Path]::GetInvalidFileNameChars()) -ge 0) {
    throw 'SkillName must be a single directory name, not a path.'
}

$repoRoot = Resolve-FullPath (Join-Path $PSScriptRoot '..')
$skillFile = Join-Path $repoRoot 'SKILL.md'
if (-not (Test-Path -LiteralPath $skillFile -PathType Leaf)) {
    throw "Could not find SKILL.md at '$skillFile'. Run this script from a LoopPrint clone."
}

$skillsRoot = Resolve-FullPath $SkillsDir
$installPath = Join-Path $skillsRoot $SkillName

if (-not (Test-Path -LiteralPath $skillsRoot -PathType Container)) {
    if ($PSCmdlet.ShouldProcess($skillsRoot, 'Create skills directory')) {
        New-Item -ItemType Directory -Path $skillsRoot | Out-Null
    }
}

if (Test-Path -LiteralPath $installPath) {
    $item = Get-Item -LiteralPath $installPath -Force
    $isJunction = $item.LinkType -eq 'Junction'

    if ($isJunction -and (Test-SamePath ([string] $item.Target) $repoRoot)) {
        Write-Host "LoopPrint is already installed:"
        Write-Host "  $installPath -> $repoRoot"
        exit 0
    }

    if ($isJunction) {
        throw "Install path already exists as a junction to '$($item.Target)'. Remove it first: rmdir `"$installPath`""
    }

    throw "Install path already exists and is not a junction: '$installPath'. Choose -SkillName or -SkillsDir, or move the existing directory."
}

$created = $false
if ($PSCmdlet.ShouldProcess($installPath, "Create junction to $repoRoot")) {
    New-Item -ItemType Junction -Path $installPath -Value $repoRoot | Out-Null
    $created = $true
}

if ($created) {
    Write-Host 'LoopPrint Windows install complete:'
    Write-Host "  clone:  $repoRoot"
    Write-Host "  skill:  $installPath"
    Write-Host ''
    Write-Host 'Verify in your harness by listing skills or invoking /loopprint.'
}
