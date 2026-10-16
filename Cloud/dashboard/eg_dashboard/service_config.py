"""Validate and preserve the current app entrypoint when adding the observer."""
from pathlib import PurePosixPath
import re
import shlex


def parse_command(value, root, port):
    match = re.search(r'argv\[\]=(.*?)\s*;\s*ignore_errors=', value)
    if not match:
        raise ValueError('Unrecognised systemd ExecStart; inspect before deployment')
    argv = shlex.split(match[1])
    if not argv or any(any(c in arg for c in ('\n', '\r', '$', '%', ';')) for arg in argv):
        raise ValueError('Unexpected execution argument')
    executable = PurePosixPath(argv[0])
    if executable.name != 'uvicorn' or executable.parent.name != 'bin' or not executable.is_relative_to(root):
        raise ValueError('Unexpected backend executable')
    entrypoints = [i for i, arg in enumerate(argv) if arg in ('evidenceguard.app:app', 'eg_dashboard.bootstrap:app')]
    if len(entrypoints) != 1 or entrypoints[0] != 1:
        raise ValueError('Unexpected application entrypoint')
    def option(name):
        if argv.count(name) != 1: raise ValueError('Missing or repeated option: ' + name)
        index = argv.index(name) + 1
        if index >= len(argv): raise ValueError('Option missing value: ' + name)
        return argv[index]
    source = option('--app-dir')
    if not PurePosixPath(source).is_relative_to(root) or '..' in PurePosixPath(source).parts or not source.endswith('/Cloud/server'):
        raise ValueError('Unexpected application directory')
    if option('--host') != '127.0.0.1' or option('--port') != str(port):
        raise ValueError('Unexpected binding; preserve and inspect current service')
    argv[entrypoints[0]] = 'eg_dashboard.bootstrap:app'
    # Double quoting is understood by systemd, not evaluated by a shell.
    rendered = ' '.join('"' + arg.replace('\\', '\\\\').replace('"', '\\"') + '"' for arg in argv)
    return source, str(executable.parent.parent), rendered
