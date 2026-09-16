<#
.SYNOPSIS
    QuantDinger Local Test Runner for Windows PowerShell.
.DESCRIPTION
    Runs focused unit tests for Forex Top-Down SMC, Risk Controls, MT5 Mocking,
    and PostgreSQL connection verification.
.PARAMETER Target
    Test category to run: 'forex' (default), 'smc', 'order', 'risk', 'db', 'all'
.PARAMETER CheckDB
    Flag to run live PostgreSQL connection verification.
.PARAMETER VerboseOutput
    Show detailed pytest output (-v).
#>
param (
    [ValidateSet('forex', 'smc', 'order', 'risk', 'db', 'all')]
    [string]$Target = 'forex',
    [switch]$CheckDB,
    [switch]$VerboseOutput
)

$ErrorActionPreference = 'Continue'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BackendDir = Join-Path $ScriptDir 'backend_api_python'
$ForexTestsDir = Join-Path $BackendDir 'tests\forex_smc'
$ConfigFile = Join-Path $ForexTestsDir 'pytest.ini'

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "   QuantDinger Local Test Runner - Forex SMC Engine     " -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Target: $Target | CheckDB: $CheckDB | Python: 3.14" -ForegroundColor Gray

if ($CheckDB) {
    $env:RUN_DB_TESTS = '1'
    Write-Host "[INFO] Live PostgreSQL connection check enabled." -ForegroundColor Magenta
} else {
    $env:RUN_DB_TESTS = '0'
}

$TestTarget = ''
$ExtraArgs = @('-c', $ConfigFile, '-o', 'filterwarnings=ignore')

switch ($Target) {
    'forex' { $TestTarget = $ForexTestsDir }
    'smc'   { $TestTarget = Join-Path $ForexTestsDir 'test_smc_indicators.py' }
    'order' { $TestTarget = Join-Path $ForexTestsDir 'test_mt5_adapter_mock.py' }
    'risk'  { $TestTarget = Join-Path $ForexTestsDir 'test_circuit_breaker.py' }
    'db'    { 
        $env:RUN_DB_TESTS = '1'
        $TestTarget = Join-Path $ForexTestsDir 'test_postgres_connection.py' 
    }
    'all'   { 
        $TestTarget = Join-Path $BackendDir 'tests'
        $ExtraArgs = @()
    }
}

$PytestArgs = @('-m', 'pytest', $TestTarget) + $ExtraArgs
if ($VerboseOutput) {
    $PytestArgs += '-v'
} else {
    $PytestArgs += '-q'
}

Write-Host "`n[RUNNING] python $($PytestArgs -join ' ')" -ForegroundColor Cyan
$Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

python @PytestArgs
$ExitCode = $LASTEXITCODE
$Stopwatch.Stop()

if ($ExitCode -eq 0) {
    Write-Host "`n========================================================" -ForegroundColor Green
    Write-Host "  ALL TESTS PASSED! Execution time: $($Stopwatch.Elapsed.TotalSeconds.ToString('0.00'))s" -ForegroundColor Green
    Write-Host "========================================================" -ForegroundColor Green
} else {
    Write-Host "`n========================================================" -ForegroundColor Red
    Write-Host "  TESTS FAILED! Exit code: $ExitCode" -ForegroundColor Red
    Write-Host "========================================================" -ForegroundColor Red
    exit $ExitCode
}
