#!/usr/bin/env bash
# Uses the caller's AWS login. Does not create credentials or change IAM/network rules.
set -euo pipefail

usage() {
  cat <<'HELP'
Usage: bash scripts/cloud_session.sh [check|connect] [AWS_PROFILE_NAME]
  check    Verify AWS account and this instance's SSM connection (default).
  connect  Open a Session Manager shell after the same checks.
Requires AWS CLI v2 and an authorized AWS login. connect also requires
the official Session Manager plugin. No SSH key or source-IP rule is used.
HELP
}

mode="${1:-check}"
case "$mode" in
  -h|--help) usage; exit 0 ;;
  check|connect) ;;
  *) usage >&2; exit 2 ;;
esac
if (( $# > 2 )); then usage >&2; exit 2; fi
if ! command -v aws >/dev/null 2>&1; then
  echo 'AWS CLI v2 is missing. Install it from https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html' >&2
  exit 1
fi

export AWS_PAGER="" AWS_CLI_AUTO_PROMPT=off
aws_cmd=(aws --region ap-southeast-1 --no-cli-pager)
if [[ -n "${2:-}" ]]; then aws_cmd+=(--profile "$2"); fi
instance_id=i-010907ed19e2cc23a
expected_account=083151142234

if ! account_id="$("${aws_cmd[@]}" sts get-caller-identity --query Account --output text)"; then
  echo 'AWS login is unavailable or expired. Sign in with your assigned identity; do not use an SSH key as an AWS credential.' >&2
  exit 1
fi
if [[ "$account_id" != "$expected_account" ]]; then
  echo "Wrong AWS account. Expected $expected_account; no session was opened." >&2
  exit 1
fi
if ! status="$("${aws_cmd[@]}" ssm get-connection-status --target "$instance_id" --query Status --output text)"; then
  echo 'Unable to query SSM. Check IAM permission for this instance and the selected region.' >&2
  exit 1
fi
if [[ "$status" != connected ]]; then
  echo "SSM is not ready ($status). Keep the existing SSH fallback; check the instance role and agent." >&2
  exit 1
fi
echo "SSM Connected: $instance_id (ap-southeast-1). This check is not a successful shell session."
if [[ "$mode" == connect ]]; then
  if ! command -v session-manager-plugin >/dev/null 2>&1; then
    echo 'Session Manager plugin is missing. See https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html' >&2
    exit 1
  fi
  exec "${aws_cmd[@]}" ssm start-session --target "$instance_id" --reason 'EvidenceGuard team maintenance'
fi
