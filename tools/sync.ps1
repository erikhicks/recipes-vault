<#
.SYNOPSIS
    Rebuild the recipe bundle from the Obsidian vault and publish it.

.DESCRIPTION
    One command per clipping session: parse the vault, refresh data/recipes.json,
    commit with a message describing what actually changed, and push. GitHub
    Pages redeploys on its own from the pushed commit.

.PARAMETER Vault
    Path to the Recipes folder in the vault. Defaults to the built-in path, or
    the RECIPE_VAULT environment variable if it's set.

.PARAMETER NoPush
    Build and commit, but stop short of pushing.

.PARAMETER Check
    Parse and report only. Writes nothing, commits nothing.

.EXAMPLE
    .\tools\sync.ps1
.EXAMPLE
    .\tools\sync.ps1 -Check
#>
[CmdletBinding()]
param(
    [string]$Vault,
    [switch]$NoPush,
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo

try {
    $buildArgs = @("$repo\tools\build.py")
    if ($Vault) { $buildArgs += @("--vault", $Vault) }
    if ($Check) { $buildArgs += "--check" }

    & py @buildArgs
    if ($LASTEXITCODE -ne 0) { throw "build.py failed with exit code $LASTEXITCODE" }
    if ($Check) { return }

    if (-not (Test-Path "$repo\.git")) {
        Write-Host "`nNot a git repository yet - built the data but stopped there." -ForegroundColor Yellow
        Write-Host "Run 'git init' and add a remote, then re-run this script."
        return
    }

    git add -A
    if (-not (git status --porcelain)) {
        Write-Host "`nNothing changed. Site is already up to date." -ForegroundColor Green
        return
    }

    $messageFile = Join-Path $repo ".build-message"
    if (Test-Path $messageFile) {
        git commit --file $messageFile --cleanup=strip
    } else {
        git commit -m "Sync recipes"
    }
    if ($LASTEXITCODE -ne 0) { throw "git commit failed" }

    if ($NoPush) {
        Write-Host "`nCommitted. Skipping push (-NoPush)." -ForegroundColor Green
        return
    }

    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    if (-not (git remote)) {
        Write-Host "`nCommitted, but there's no git remote to push to." -ForegroundColor Yellow
        return
    }

    git push origin $branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed" }

    $url = (git remote get-url origin) -replace '\.git$', ''
    if ($url -match 'github\.com[:/]([^/]+)/(.+)$') {
        Write-Host "`nPushed. Live in a minute or two at https://$($Matches[1]).github.io/$($Matches[2])/" -ForegroundColor Green
    } else {
        Write-Host "`nPushed." -ForegroundColor Green
    }
} finally {
    Pop-Location
}
