#!/usr/bin/env python3
"""Run a supplied maintenance script through the caller's AWS SSM identity.

No SSH key, server password, or persistent AWS access key is required. AWS CLI
v2 must already be signed in (aws login --profile evidenceguard-prod15).
"""
import argparse
import json
import locale
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ACCOUNT = "083151142234"
REGION = "ap-southeast-1"
INSTANCE = "i-010907ed19e2cc23a"


def aws_environment(*, system_proxy=True):
    """Use an explicitly configured proxy first, otherwise Windows' existing proxy.

    Only the child process environment changes. No global proxy or TLS changes.
    """
    env = dict(os.environ, AWS_PAGER="", AWS_CLI_AUTO_PROMPT="off", PYTHONIOENCODING="utf-8")
    if system_proxy and os.name == "nt" and not any(env.get(k) for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")):
        proxies = urllib.request.getproxies()
        for scheme in ("http", "https"):
            if proxies.get(scheme, "").startswith(("http://", "https://")):
                env[scheme.upper() + "_PROXY"] = proxies[scheme]
        env.setdefault("NO_PROXY", "127.0.0.1,localhost,::1")
    return env


def aws_executable():
    found = shutil.which("aws")
    if found:
        return found
    for root in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", "")):
        for suffix in ("Programs/Amazon/AWSCLIV2/aws.exe", "Amazon/AWSCLIV2/aws.exe"):
            candidate = Path(root) / suffix
            if candidate.is_file():
                return str(candidate)
    raise RuntimeError("Install AWS CLI v2 from the official AWS website first")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="evidenceguard-prod15")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path)
    group.add_argument("--command")
    group.add_argument("--resume", help="Read an existing command outcome without sending it again")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-system-proxy", action="store_true", help="Do not inherit the Windows proxy; explicit proxy environment variables still apply")
    args = parser.parse_args()
    script = args.file.read_text(encoding="utf-8") if args.file else args.command
    if not 1 <= args.timeout <= 3600:
        parser.error("timeout must be 1..3600 seconds")
    cmd = [aws_executable(), "--profile", args.profile, "--region", REGION, "--no-cli-pager", "--output", "json"]
    env = aws_environment(system_proxy=not args.no_system_proxy)

    def aws(*parts, allow_missing=False):
        result = subprocess.run(cmd + list(parts), capture_output=True, env=env)
        def decode(value):
            try: return value.decode('utf-8')
            except UnicodeDecodeError: return value.decode(locale.getpreferredencoding(False),errors='replace')
        result.stdout, result.stderr = decode(result.stdout), decode(result.stderr)
        if result.returncode:
            if allow_missing and "InvocationDoesNotExist" in result.stderr:
                return None
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout)

    identity = aws("sts", "get-caller-identity")
    if identity["Account"] != ACCOUNT:
        raise RuntimeError("Wrong AWS account; nothing was sent")
    payload = {"DocumentName": "AWS-RunShellScript", "InstanceIds": [INSTANCE],
               "Comment": "EvidenceGuard authorized maintenance",
               "Parameters": {"commands": [script], "executionTimeout": [str(args.timeout)]}}
    if args.resume:
        import uuid
        command_id = str(uuid.UUID(args.resume))
    else:
        with tempfile.TemporaryDirectory(prefix="eg-ssm-") as directory:
            request = Path(directory) / "request.json"
            request.write_text(json.dumps(payload), encoding="utf-8")
            sent = aws("ssm", "send-command", "--cli-input-json", "file://" + str(request))
        command_id = sent["Command"]["CommandId"]
    print("SSM command: " + command_id, file=sys.stderr, flush=True)
    deadline = time.monotonic() + args.timeout + 45
    while time.monotonic() < deadline:
        result = aws("ssm", "get-command-invocation", "--command-id", command_id, "--instance-id", INSTANCE, allow_missing=True)
        if result and result["Status"] not in {"Pending", "InProgress", "Delayed"}:
            if args.json:
                print(json.dumps(result, ensure_ascii=False))
            else:
                print(result.get("StandardOutputContent", ""), end="")
                print(result.get("StandardErrorContent", ""), file=sys.stderr, end="")
            return 0 if result["Status"] == "Success" else 1
        time.sleep(2)
    raise RuntimeError("SSM wait timed out; inspect command " + command_id + " before repeating mutations")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
