#!/usr/bin/env python3
"""Preview/apply source-only updates from an installed skill. Never pushes."""
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

def sources(root):
    found = {}
    main = root / 'SKILL.md'
    if main.is_file() and not main.is_symlink():
        found[Path('SKILL.md')] = main
    for folder in ('scripts', 'references', 'assets'):
        base = root / folder
        if base.is_symlink():
            continue
        for p in base.rglob('*'):
            if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts:
                continue
            if p.suffix not in ('.py', '.md', '.html', '.css', '.js'):
                continue
            if root.resolve() not in p.resolve().parents:
                continue
            found[p.relative_to(root)] = p
    return found

def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--source', type=Path, default=Path.home()/'.codex/skills/storage-analyzer')
    a.add_argument('--apply', action='store_true')
    opts = a.parse_args()
    src = opts.source.expanduser().resolve()
    if not (src/'SKILL.md').is_file():
        a.error('source must contain SKILL.md')
    current, existing = sources(src), sources(ROOT)
    count = 0
    for rel, p in sorted(current.items()):
        target = ROOT / rel
        if target.exists() and p.read_bytes() == target.read_bytes():
            continue
        if target.is_symlink():
            a.error('refusing to replace a symlink: '+str(rel))
        print(('COPY ' if opts.apply else 'WOULD COPY ') + str(rel))
        if opts.apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
        count += 1
    for rel in sorted(set(existing)-set(current)):
        print('REVIEW REMOVED SOURCE (not deleted): '+str(rel))
    print(str(count)+' file(s) changed; no commit or push performed.')

if __name__ == '__main__':
    main()
