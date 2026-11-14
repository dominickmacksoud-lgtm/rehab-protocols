"""Claude Code PreToolUse guard for the RehabProtocols repo.

Wired up in .claude/settings.json. Reads the hook payload on stdin and prints a
"deny" decision when a tool call would break one of the rules in CLAUDE.md:

  Edit/Write   - hand-editing an auto-generated file or the slug ledger
  Bash/PowerShell
               - deleting, moving or overwriting the slug ledger or the generator
               - `git commit` while protocols.js is a --skip-pages build
               - `git commit` while rp_verify.py fails (all checks except --links,
                 which is too slow for a hook; run the full verifier by hand)

Anything it does not recognise is allowed. Self-test: python .claude/hooks/guard.py --selftest
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Repo-relative path -> why it must not be edited by hand.
GENERATED = {
    'protocol-slugs.csv': (
        'protocol-slugs.csv is the URL contract and is never hand-edited. '
        'Change protocols-import.csv and run generate-protocols.py; to carry a URL '
        'across a Protocol URL or Surgery Type change use --rekey OLDPID=NEWPID.'),
    'protocols.js': (
        'protocols.js is generated. Edit protocols-import.csv and run '
        'python generate-protocols.py.'),
    'sitemap.xml': (
        'sitemap.xml is generated. Run python generate-protocols.py.'),
    'guidelines.js': (
        'guidelines.js is generated. Edit guidelines-import.csv and run '
        'python generate-guidelines.py.'),
    'guidelines-structured-data.js': (
        'guidelines-structured-data.js is generated. Edit guidelines-import.csv and '
        'run python generate-guidelines.py.'),
    'popularity.json': (
        'popularity.json is written by ga-popularity.py in the weekly workflow. '
        'Do not edit it by hand.'),
}
GENERATED_DIR_REASON = (
    'Pages under protocols/ are generated. Edit protocols-import.csv, topics.csv or '
    'templates/ and run python generate-protocols.py.')

# Files a shell command must never delete, move or overwrite.
PRECIOUS = ('protocol-slugs.csv', 'generate-protocols.py')
DESTROY = re.compile(
    r'(?:\brm\b|\bdel\b|\bmv\b|\bmove\b|\bRemove-Item\b|\bMove-Item\b|\bRename-Item\b|'
    r'\bren\b|\bClear-Content\b|\bgit\s+rm\b|\bgit\s+mv\b)[^;&|\n]*?(?:%s)'
    % '|'.join(re.escape(p) for p in PRECIOUS), re.I)
REDIRECT = re.compile(
    r'(?<![0-9&>])>{1,2}\s*["\']?(?:\./|\.\\)?(?:%s)\b|'
    r'\b(?:Set-Content|Out-File)\b[^;&|\n]*?(?:%s)'
    % (('|'.join(re.escape(p) for p in PRECIOUS),) * 2), re.I)
GIT_COMMIT = re.compile(r'\bgit\b(?:\s+-c\s+\S+)*\s+commit\b')

VERIFY_TIMEOUT = 100


def rel_to_root(path):
    """Repo-relative posix path, or None when the path is outside this repo."""
    try:
        p = Path(path)
        if not p.is_absolute():
            p = ROOT / p
        return p.resolve().relative_to(ROOT).as_posix()
    except (ValueError, OSError):
        return None


def check_edit(tool_input):
    rel = rel_to_root(tool_input.get('file_path') or '')
    if rel is None:
        return None
    if rel in GENERATED:
        return GENERATED[rel]
    if rel.startswith('protocols/'):
        return GENERATED_DIR_REASON
    return None


def targets_this_repo(command, cwd):
    """False when the command plainly runs git somewhere else."""
    if re.search(r'\bgit\s+-C\b', command):
        return False
    where = Path(cwd) if cwd else ROOT
    for m in re.finditer(r'(?:^|[;&|]\s*)(?:cd|Set-Location|pushd)\s+("[^"]+"|\'[^\']+\'|\S+)',
                         command):
        target = m.group(1).strip('"\'')
        target = re.sub(r'^/([a-zA-Z])/', r'\1:/', target)   # /c/Users -> c:/Users
        where = Path(target) if Path(target).is_absolute() else where / target
    try:
        where.resolve().relative_to(ROOT)
        return True
    except (ValueError, OSError):
        return False


def skip_pages_build():
    """True when protocols.js has entries without a page path (a --skip-pages run)."""
    try:
        text = (ROOT / 'protocols.js').read_text(encoding='utf-8')
    except OSError:
        return False
    entries = text.count('{"url":')
    return entries > 0 and text.count('"path":"/protocols/') < entries


def pipeline_touched():
    """True when the pending commit could include generated output or its inputs."""
    try:
        out = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, text=True,
                             capture_output=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    watched = ('protocols-import.csv', 'protocols.js', 'protocol-slugs.csv', 'sitemap.xml',
               'topics.csv', 'protocol-variants.csv', 'cpg_pairings.csv', 'protocols/',
               'templates/', 'rp_', 'generate-protocols.py')
    for line in out.splitlines():
        path = line[3:].strip().strip('"')
        if path.startswith(watched):
            return True
    return False


def verify_failure():
    """Tail of rp_verify.py output when it fails, else None."""
    try:
        # Not --links: that pass alone can take two minutes on a cold disk cache.
        r = subprocess.run([sys.executable, 'rp_verify.py', '--ledger', '--sitemap',
                            '--jsonld', '--pages'], cwd=ROOT, text=True,
                           capture_output=True, timeout=VERIFY_TIMEOUT,
                           encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return None          # too slow to judge; do not block on a timeout
    except OSError:
        return None
    if r.returncode == 0:
        return None
    return '\n'.join((r.stdout or '').strip().splitlines()[-25:])


def check_shell(tool_input, cwd):
    command = tool_input.get('command') or ''
    if DESTROY.search(command) or REDIRECT.search(command):
        return ('This command would delete, move or overwrite protocol-slugs.csv or '
                'generate-protocols.py. The ledger pins every protocol URL and must never '
                'be deleted or regenerated; the generator is the only one. If the user '
                'really wants this, they must run it themselves.')
    if GIT_COMMIT.search(command) and targets_this_repo(command, cwd):
        if skip_pages_build():
            return ('protocols.js is a --skip-pages build (entries are missing their page '
                    'path and tags). Committing it strips every card link and badge. Run '
                    'python generate-protocols.py (no flags) first.')
        if pipeline_touched():
            tail = verify_failure()
            if tail:
                return ('rp_verify.py fails, so this commit is blocked. Fix the failures '
                        'and commit again.\n' + tail)
    return None


def decide(payload):
    tool = payload.get('tool_name') or ''
    tool_input = payload.get('tool_input') or {}
    if tool in ('Edit', 'Write', 'NotebookEdit'):
        return check_edit(tool_input)
    if tool in ('Bash', 'PowerShell'):
        return check_shell(tool_input, payload.get('cwd'))
    return None


def selftest():
    def shell(cmd):
        return bool(DESTROY.search(cmd) or REDIRECT.search(cmd))
    cases = [
        (check_edit({'file_path': str(ROOT / 'protocol-slugs.csv')}) is not None, True),
        (check_edit({'file_path': 'protocols.js'}) is not None, True),
        (check_edit({'file_path': str(ROOT / 'protocols' / 'x' / 'index.html')}) is not None, True),
        (check_edit({'file_path': str(ROOT / 'protocols-import.csv')}) is not None, False),
        (check_edit({'file_path': str(ROOT / 'index.html')}) is not None, False),
        (check_edit({'file_path': str(ROOT.parent / 'other' / 'protocols.js')}) is not None, False),
        (shell('rm protocol-slugs.csv'), True),
        (shell('git rm -f protocol-slugs.csv'), True),
        (shell('Remove-Item .\\protocol-slugs.csv'), True),
        (shell('echo x > protocol-slugs.csv'), True),
        (shell('mv generate-protocols.py old.py'), True),
        (shell('python generate-protocols.py --rekey a=b'), False),
        (shell('git add protocol-slugs.csv && git commit -m x'), False),
        (shell('grep foo protocol-slugs.csv'), False),
        (shell('git diff protocol-slugs.csv 2>&1'), False),
        (shell('rm link-report.json; git add protocol-slugs.csv'), False),
        (bool(GIT_COMMIT.search('git add -A && git commit -m "x"')), True),
        (bool(GIT_COMMIT.search('git -c user.name=x commit -m y')), True),
        (bool(GIT_COMMIT.search('git log --oneline')), False),
        (targets_this_repo('git commit -m x', str(ROOT)), True),
        (targets_this_repo('cd ../elsewhere && git commit -m x', str(ROOT)), False),
        (targets_this_repo('git -C ../elsewhere commit -m x', str(ROOT)), False),
        (targets_this_repo('git commit -m x', str(ROOT.parent)), False),
    ]
    bad = [i for i, (got, want) in enumerate(cases) if got != want]
    print('selftest: %d cases, %d failed %s' % (len(cases), len(bad), bad or ''))
    return 1 if bad else 0


def main():
    if '--selftest' in sys.argv:
        return selftest()
    try:
        payload = json.loads(sys.stdin.read() or '{}')
    except ValueError:
        return 0
    reason = decide(payload)
    if reason:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': reason,
        }}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
