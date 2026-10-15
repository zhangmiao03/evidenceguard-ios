[CmdletBinding()]
param(
    [ValidateSet('connect','login','status','port-forward')][string]$Action = 'connect',
    [string]$Profile = 'evidenceguard-prod15',
    [ValidateRange(1024,65535)][int]$LocalPort = 8795
)
$ErrorActionPreference = 'Stop'
$awsCommand = Get-Command aws -ErrorAction SilentlyContinue
$awsPath = if ($awsCommand) { $awsCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs\Amazon\AWSCLIV2\aws.exe' }
$pluginDir = Join-Path $env:LOCALAPPDATA 'Programs\Amazon\SessionManagerPlugin'
if (Test-Path -LiteralPath $pluginDir) { $env:PATH = $pluginDir + [IO.Path]::PathSeparator + $env:PATH }
if (-not (Test-Path -LiteralPath $awsPath)) { throw 'Install AWS CLI v2 first: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html' }
$awsOptions = @('--profile',$Profile,'--region','ap-southeast-1','--no-cli-pager')
if ($Action -eq 'login') {
    & $awsPath @awsOptions login --remote
    exit $LASTEXITCODE
}
$identityJson = & $awsPath @awsOptions sts get-caller-identity --output json
if ($LASTEXITCODE -ne 0) { throw 'AWS login expired. Run: .\scripts\cloud_session.ps1 -Action login' }
$identity = $identityJson | ConvertFrom-Json
if ($identity.Account -ne '083151142234') { throw 'Wrong AWS account. No server operation was performed.' }
if ($Action -eq 'status') {
    & $awsPath @awsOptions ssm describe-instance-information --filters 'Key=InstanceIds,Values=i-010907ed19e2cc23a' --query 'InstanceInformationList[].{Instance:InstanceId,Status:PingStatus,OS:PlatformName,Version:PlatformVersion}' --output table
} elseif ($Action -eq 'port-forward') {
    $parameters = '{"portNumber":["8795"],"localPortNumber":["' + $LocalPort + '"]}'
    & $awsPath @awsOptions ssm start-session --target i-010907ed19e2cc23a --document-name AWS-StartPortForwardingSession --parameters $parameters
} else {
    & $awsPath @awsOptions ssm start-session --target i-010907ed19e2cc23a
}
exit $LASTEXITCODE
