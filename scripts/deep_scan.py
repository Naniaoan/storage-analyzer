#!/usr/bin/env python3
"""Bounded, read-only directory evidence. No classification or deletion.
Usage: deep_scan.py PATH [PATH ...] [--seconds 45] [--max-files 150000]
Output: direct-child allocation, largest files, package manifests, sampled ZIP
member names, newest mtimes, errors and coverage. Never follows symlinks.
Allocated bytes are null if the platform does not expose st_blocks.
"""
import argparse
import collections
import datetime
import heapq
import json
import os
import re
import stat
import time
import zipfile
from pathlib import Path


def inspect(path, seconds=45, max_files=150000, large_mib=50, stale_days=180):
    root = Path(os.path.abspath(os.path.expanduser(path)))
    start = time.monotonic()
    deadline = start + seconds
    errors, children, largest, archives, packages = [], {}, [], [], []
    site_origins = []
    counts = collections.Counter()
    seen = set()
    total = {'logical_bytes': 0, 'allocated_bytes': 0}
    allocated_known = True
    limited = False
    latest = 0
    oldest = None
    month_counts = collections.Counter()
    newest_files = []
    newest_content_files = []
    content_latest = 0
    excluded_metadata_files = 0
    observed_epoch = time.time()
    stale_cutoff = observed_epoch - stale_days * 86400
    old_bytes = 0
    old_files = 0

    def error(p, e):
        counts['errors'] += 1
        if len(errors) < 30:
            errors.append({'path': str(p), 'error': str(e)[:300]})

    def add_package(p):
        try:
            if p.stat().st_size > 1024 * 1024:
                return
            j = json.loads(p.read_text(encoding='utf-8'))
            packages.append({'path': str(p), 'name': j.get('name'),
                             'version': j.get('version'), 'description': j.get('description'),
                             'requested': j.get('dependencies', {}) if p.parent.name != 'node_modules' else {}})
        except (OSError, ValueError) as e:
            error(p, e)

    if root.is_symlink():
        return {'path': str(root), 'status': 'skipped_symlink', 'errors': []}
    if not root.exists():
        return {'path': str(root), 'status': 'missing', 'errors': []}
    root = root.resolve()
    stack = [root]
    while stack:
        if time.monotonic() > deadline or counts['files'] >= max_files:
            limited = True
            break
        p = stack.pop()
        try:
            st = p.lstat()
            if stat.S_ISLNK(st.st_mode):
                counts['skipped_symlinks'] += 1
                continue
            if p != root and st.st_dev != root.stat().st_dev:
                counts['skipped_mounts'] += 1
                continue
            if stat.S_ISDIR(st.st_mode):
                with os.scandir(p) as entries:
                    for entry in entries:
                        if time.monotonic() > deadline or len(stack) >= max_files:
                            limited = True
                            break
                        stack.append(Path(entry.path))
                # Generic shallow manifests, including npx requested dependencies
                # and their actual installed versions, without reading arbitrary content.
                rel = p.relative_to(root)
                if len(rel.parts) <= 2 and (p / 'package.json').is_file() and (p / 'package.json').stat().st_size <= 1024 * 1024:
                    manifest = p / 'package.json'
                    if not manifest.is_symlink():
                        add_package(manifest)
                        try:
                            j = json.loads(manifest.read_text())
                            for name in list(j.get('dependencies', {}))[:30]:
                                dep = p / 'node_modules' / name / 'package.json'
                                if dep.is_file() and not dep.is_symlink() and root in dep.resolve().parents:
                                    add_package(dep)
                        except (OSError, ValueError) as e:
                            error(manifest, e)
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            counts['files'] += 1
            key = (st.st_dev, st.st_ino)
            if key in seen:
                counts['hardlinks_deduplicated'] += 1
                continue
            seen.add(key)
            allocated = st.st_blocks * 512 if hasattr(st, 'st_blocks') else None
            if allocated is None:
                allocated_known = False
            rel = p.relative_to(root) if p != root else Path(p.name)
            child = children.setdefault(rel.parts[0], {'logical_bytes': 0, 'allocated_bytes': 0,
                                                       'files': 0, 'latest_mtime': 0, 'old_files': 0, 'old_allocated_bytes': 0})
            for obj in (total, child):
                obj['logical_bytes'] += st.st_size
                obj['allocated_bytes'] += allocated or 0
            child['files'] += 1
            child['latest_mtime'] = max(child['latest_mtime'], st.st_mtime)
            latest = max(latest, st.st_mtime)
            oldest = st.st_mtime if oldest is None else min(oldest, st.st_mtime)
            month_counts[datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m')] += 1
            heapq.heappush(newest_files, (st.st_mtime, str(p)))
            if len(newest_files) > 10:
                heapq.heappop(newest_files)
            if p.name in ('.DS_Store', 'desktop.ini', 'Thumbs.db') or p.name.startswith('._'):
                excluded_metadata_files += 1
            else:
                content_latest = max(content_latest, st.st_mtime)
                heapq.heappush(newest_content_files, (st.st_mtime, str(p)))
                if len(newest_content_files) > 5:
                    heapq.heappop(newest_content_files)
            if st.st_mtime < stale_cutoff:
                old_files += 1
                old_bytes += allocated or 0
                child['old_files'] += 1
                child['old_allocated_bytes'] += allocated or 0
            if p.name == 'index.txt' and 'CacheStorage' in p.parts and st.st_size <= 1024 * 1024 and len(site_origins) < 100:
                try:
                    origins = sorted({m.decode('ascii') for m in re.findall(rb'https?://[a-zA-Z0-9._:-]+', p.read_bytes())})
                    if origins:
                        site_origins.append({'path': str(p.parent), 'origins': origins, 'source': 'CacheStorage index metadata; origin hint, not payload inventory'})
                except OSError as e:
                    error(p, e)
            suffix = p.suffix.lower() or '(none)'
            counts['extension:' + suffix] += 1
            row = (st.st_size, str(p), allocated)
            if st.st_size >= large_mib * 1024**2:
                heapq.heappush(largest, row)
                if len(largest) > 30:
                    heapq.heappop(largest)
            if suffix == '.zip':
                heapq.heappush(archives, (st.st_mtime, str(p)))
                if len(archives) > 3:
                    heapq.heappop(archives)
        except OSError as e:
            error(p, e)
    zip_samples = []
    for _, p in sorted(archives, reverse=True):
        # Reading only central-directory member names; no extraction / payload execution.
        # Avoid parsing arbitrarily huge archives after the traversal deadline.
        if time.monotonic() > deadline or os.path.getsize(p) > 100 * 1024**2:
            zip_samples.append({'path': p, 'status': 'not_sampled_size_or_time_limit'})
            continue
        try:
            with zipfile.ZipFile(p) as z:
                names = z.namelist()
                zip_samples.append({'path': p, 'status': 'ok', 'members': len(names), 'sample': names[:12]})
        except (OSError, zipfile.BadZipFile) as e:
            error(p, e)
    if not allocated_known:
        total['allocated_bytes'] = None
        for child in children.values():
            child['allocated_bytes'] = None
            child['old_allocated_bytes'] = None
    return {'path': str(root), 'observed_at': datetime.datetime.now().astimezone().isoformat(),
            'status': 'partial' if limited or errors or counts['skipped_mounts'] else 'ok',
            'limit_reached': limited, 'seconds': round(time.monotonic() - start, 2),
            'limits': {'seconds': seconds, 'max_files': max_files, 'large_mib': large_mib},
            'measurement': 'regular files only; no symlinks/mount traversal; hardlinks counted once; not unique APFS physical bytes',
            **total, 'latest_mtime': latest, 'counts': dict(counts),
            'activity': {'root_mtime': root.stat().st_mtime, 'oldest_file_mtime': oldest,
                         'latest_file_mtime': latest or None,
                         'latest_content_file_mtime': content_latest or None,
                         'days_since_content_change': round((observed_epoch-content_latest)/86400,1) if content_latest else None,
                         'excluded_metadata_files': excluded_metadata_files,
                         'latest_content_files': [{'mtime':t,'path':p} for t,p in sorted(newest_content_files,reverse=True)],
                         'mtime_month_counts': dict(sorted(month_counts.items())),
                         'latest_files': [{'mtime': t, 'path': p} for t,p in sorted(newest_files, reverse=True)],
                         'stale_threshold_days': stale_days, 'old_files': old_files,
                         'old_allocated_bytes': old_bytes if allocated_known else None,
                         'days_since_latest_file_change': round((observed_epoch-latest)/86400,1) if latest else None,
                         'interpretation': 'file modification history within scan coverage; not last launch/access, install time or deletion permission'},
            'children': sorted([{'name': n, 'path': str(root if root.is_file() else root/n), **v} for n, v in children.items()],
                               key=lambda v: v['allocated_bytes'] if v['allocated_bytes'] is not None else v['logical_bytes'], reverse=True),
            'large_files': [{'path': p, 'logical_bytes': n, 'allocated_bytes': a}
                            for n, p, a in sorted(largest, reverse=True)],
            'packages': packages, 'site_origins': site_origins, 'zip_samples': zip_samples, 'errors': errors,
            'process_check': 'not_checked; use lsof / process inspection for concrete cleanup paths'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('paths', nargs='+')
    p.add_argument('--seconds', type=float, default=45)
    p.add_argument('--max-files', type=int, default=150000)
    p.add_argument('--large-mib', type=float, default=50)
    p.add_argument('--stale-days', type=float, default=180, help='age signal, not a deletion rule')
    args = p.parse_args()
    if args.seconds <= 0 or args.max_files <= 0 or args.large_mib < 0 or args.stale_days < 0:
        p.error('limits must be positive (large-mib may be zero)')
    print(json.dumps({'inspections': [inspect(x, args.seconds, args.max_files, args.large_mib, args.stale_days)
                                       for x in args.paths]}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
