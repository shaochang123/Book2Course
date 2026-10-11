"""Check staged files and outgoing commits without printing secret values."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ZERO = re.compile(r'^0+$')
PROVIDER_KEY = re.compile(
    rb'\b(?:sk-(?:proj-|svcacct-|ant-api\d{2}-)?[A-Za-z0-9_-]{24,}'
    rb'|(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{30,}'
    rb'|AIza[0-9A-Za-z_-]{30,}|AKIA[0-9A-Z]{16})\b')
PRIVATE_KEY = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----')
ASSIGNMENT = re.compile(
    rb'''(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)["']?\s*[:=]\s*["']([^"'\r\n]{16,})["']''')


def git(repo: Path, *args: str, input: bytes | None = None) -> bytes:
    return subprocess.run(['git', '-C', str(repo), *args], input=input,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout


def placeholder(value: bytes) -> bool:
    text = value.strip().lower()
    return (text in {b'ollama', b'secret', b'test-secret', b'test-key', b'api-key'}
            or any(marker in text for marker in (b'example', b'placeholder', b'dummy', b'your-', b'your_', b'changeme'))
            or text.startswith((b'<', b'${')))


def env_secrets(content: bytes) -> list[bytes]:
    values = []
    for line in content.splitlines():
        name, separator, value = line.partition(b'=')
        if separator and re.search(rb'(?i)(?:^|_)(?:API_KEY|APIKEY|ACCESS_TOKEN|AUTH_TOKEN|BEARER_TOKEN|TOKEN|CLIENT_SECRET|SECRET|SECRET_KEY|PASSWORD)$', name.strip()) and not name.lstrip().startswith(b'#'):
            value = value.strip().strip(b'\'"')
            if value and not placeholder(value):
                values.append(value)
    return values


def local_secrets(repo: Path) -> list[bytes]:
    """Detect accidental copies of this machine's configured API credentials."""
    values = []
    for path in repo.glob('.env*'):
        if not path.is_file() or path.name.endswith('.example'):
            continue
        values.extend(env_secrets(path.read_bytes()))
    return values


def has_secret(content: bytes, known: list[bytes]) -> bool:
    return (any(value in content for value in known)
            or bool(PROVIDER_KEY.search(content) or PRIVATE_KEY.search(content))
            or any(not placeholder(match.group(1)) for match in ASSIGNMENT.finditer(content)))


def ignored(repo: Path, paths: list[str]) -> set[str]:
    if not paths:
        return set()
    result = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--no-index', '-z', '--stdin'],
                            input=b'\0'.join(path.encode('utf-8') for path in paths)+b'\0',
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode not in (0, 1):
        raise RuntimeError('Git ignore check failed.')
    return {path.decode('utf-8') for path in result.stdout.split(b'\0') if path}


def blobs(repo: Path, ids: set[str]) -> dict[str, bytes]:
    if not ids:
        return {}
    raw = git(repo, 'cat-file', '--batch', input=('\n'.join(sorted(ids))+'\n').encode('ascii'))
    result = {}; offset = 0
    for _ in ids:
        end = raw.index(b'\n', offset)
        oid, kind, size = raw[offset:end].split()
        if kind != b'blob':
            raise ValueError('Expected a Git blob.')
        offset = end+1; size = int(size)
        result[oid.decode('ascii')] = raw[offset:offset+size]
        offset += size+1
    return result


def audit(repo: Path, revision: str | None, known: list[bytes]) -> list[tuple[str, str]]:
    raw = (git(repo, 'ls-tree', '-r', '-z', revision) if revision
           else git(repo, 'ls-files', '--stage', '-z'))
    files = {}
    for record in raw.split(b'\0'):
        if not record:
            continue
        metadata, path = record.split(b'\t', 1)
        if revision:
            mode, _, oid = metadata.split()
        else:
            mode, oid, state = metadata.split()
        if not revision and state != b'0':
            raise ValueError('Unmerged index cannot be checked.')
        if mode != b'160000':
            files[path.decode('utf-8')] = oid.decode('ascii')
    paths = list(files)
    blocked = ignored(repo, paths)
    findings = [(path, 'ignored/private/generated file is tracked') for path in sorted(blocked)]
    content = blobs(repo, {oid for path, oid in files.items() if path not in blocked})
    for path in paths:
        if path not in blocked:
            value = content[files[path]]
            if has_secret(value, known) or (Path(path).name.startswith('.env') and env_secrets(value)):
                findings.append((path, 'possible credential; value omitted'))
    return findings


def outgoing_commits(repo: Path, lines: list[str]) -> list[str]:
    commits = set()
    for line in lines:
        fields = line.split()
        if len(fields) != 4 or not all(re.fullmatch(r'[0-9a-fA-F]{40,64}', value) for value in (fields[1], fields[3])):
            raise ValueError('Invalid Git pre-push input.')
        _, local, _, remote = fields
        if ZERO.fullmatch(local):
            continue
        commits.add(local)
        if ZERO.fullmatch(remote):
            args = (local, '--not', '--remotes')
        else:
            args = (f'{remote}..{local}',)
        commits.update(git(repo, 'rev-list', *args).decode('ascii').splitlines())
    return sorted(commits)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--pre-push', action='store_true')
    args = parser.parse_args()
    repo = args.repo.resolve()
    known = local_secrets(repo)
    findings = set()
    revisions = outgoing_commits(repo, sys.stdin.read().splitlines()) if args.pre_push else [None]
    for revision in revisions:
        findings.update(audit(repo, revision, known))
    if findings:
        for path, reason in sorted(findings):
            print(f'BLOCKED: {path!r}: {reason}', file=sys.stderr)
        print('Remove generated/private files from Git, or remove embedded credentials. Local files may remain.', file=sys.stderr)
        return 1
    print('Git privacy check passed: no ignored tracked files or detected credentials.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError):
        print('Git privacy check could not complete; push blocked. No secret values were printed.', file=sys.stderr)
        raise SystemExit(1)
