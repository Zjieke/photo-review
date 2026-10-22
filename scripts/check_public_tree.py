"""Check staged source (or committed history) without reading ignored runtime data."""
import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_SIZE = 1024 * 1024
PRIVATE = re.compile(
    r'(^|/)(outputs|models|model-env|feature-deps|video-previews|__pycache__|\.venv[^/]*)(/|$)'
    r'|\.(sqlite3|db|log|safetensors|gguf|zip|tgz|whl|jpg|jpeg|png|mov|mp4)([.-]|$)'
    r'|(^|/)\.env($|\.)|(^|/)lan-access-password\.txt$|\.app/'
    r'|^work/[^/]+\.(json|jsonl|txt|lock|tmp)$', re.I)
PATTERNS = {
    'personal absolute path': re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'GitHub credential': re.compile(r'gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}'),
    'cloud credential': re.compile(r'AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{32,}'),
    'private key': re.compile(r'-----BEGIN [A-Z ]*PRIVATE' + r' KEY-----'),
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def inspect(name, data):
    problems = []
    if PRIVATE.search(name):
        problems.append('private/runtime file path')
    if len(data) > MAX_SIZE:
        problems.append('source file exceeds 1 MiB; inspect before publishing')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        problems.append('unexpected binary file')
    else:
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                problems.append(label)
    return [f'{name}: {problem}' for problem in problems]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', action='store_true', help='also inspect every committed blob')
    args = parser.parse_args()
    names = git('ls-files', '-z').decode().split('\0')
    problems = []
    checked = 0
    for name in filter(None, names):
        # Scan the actual index payload, not a newer working copy of that file.
        problems.extend(inspect(name, git('show', ':' + name)))
        checked += 1
    if not checked:
        raise SystemExit('No staged source files. Stage only the intended public files first.')
    if args.history:
        for line in git('rev-list', '--objects', '--all').decode().splitlines():
            oid, _, name = line.partition(' ')
            if git('cat-file', '-t', oid).strip() == b'blob':
                problems.extend(inspect(name or oid, git('cat-file', 'blob', oid)))
    if problems:
        # Never print matched credential values or file contents.
        raise SystemExit('\n'.join(sorted(set(problems))))
    print(f'PASS: {checked} staged source files; no runtime files, common secrets or personal paths'
          + ('; committed history checked' if args.history else ''))


if __name__ == '__main__':
    main()
