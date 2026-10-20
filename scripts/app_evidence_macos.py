#!/usr/bin/env python3
"""Read-only application ownership clues, never an uninstall decision.
Usage: app_evidence_macos.py DATA_PATH [DATA_PATH ...] [--check-open-files]
Checks declared app roots (or --app-root), target-local bundle metadata, HTML
titles and vendor hosts. No credentials, message bodies or launch execution.
"""
import argparse
import datetime
import html
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit


def bundle(path):
    p = path / 'Contents/Info.plist'
    if p.is_symlink() or p.stat().st_size > 1024 * 1024:
        raise ValueError('bundle metadata skipped: symlink or >1MiB')
    j = plistlib.loads(p.read_bytes())
    return {'path': str(path), 'bundle_id': j.get('CFBundleIdentifier'),
            'name': j.get('CFBundleDisplayName') or j.get('CFBundleName'),
            'version': j.get('CFBundleShortVersionString')}


def inventory(roots, suffixes=('.app',)):
    rows, errors = [], []
    for root in roots:
        if not root.exists():
            continue
        try:
            for p in root.iterdir():
                candidates = [p] if p.suffix in suffixes else ([q for q in p.iterdir() if q.suffix in suffixes] if p.is_dir() and not p.is_symlink() else [])
                for app in candidates:
                    if app.is_symlink():
                        continue
                    try:
                        rows.append(bundle(app))
                    except (OSError, ValueError, plistlib.InvalidFileException) as e:
                        errors.append({'path': str(app), 'error': str(e)[:200]})
        except OSError as e:
            errors.append({'path': str(root), 'error': str(e)[:200]})
    return {'apps': rows, 'checked_roots': [str(p) for p in roots], 'errors': errors,
            'scope': 'listed roots plus one directory level; absence is not proof of uninstallation'}


def evidence(path, apps, seconds=20, max_files=30000, check_open=False, components=(), processes=()):
    root = Path(os.path.abspath(os.path.expanduser(path)))
    if root.is_symlink():
        return {'path': str(root), 'status': 'skipped_symlink'}
    if not root.is_dir():
        return {'path': str(root), 'status': 'missing_or_not_directory'}
    root = root.resolve()
    deadline = time.monotonic() + seconds
    embedded, titles, hosts, errors = [], [], set(), []
    files = 0
    stopped = False
    identity = set()
    metadata = root / '.com.apple.containermanagerd.metadata.plist'
    if metadata.is_file() and not metadata.is_symlink():
        try:
            ident = plistlib.loads(metadata.read_bytes()).get('MCMMetadataIdentifier')
            if isinstance(ident, str):
                identity.add(ident)
        except (OSError, ValueError, plistlib.InvalidFileException) as e:
            errors.append({'path': str(metadata), 'error': str(e)[:200]})
    def err(e):
        if len(errors) < 20:
            errors.append({'path': str(getattr(e, 'filename', root)), 'error': str(e)[:200]})
    for base, dirs, names in os.walk(root, followlinks=False, onerror=err):
        if time.monotonic() > deadline or files >= max_files:
            stopped = True
            break
        kept = []
        for name in dirs:
            p = Path(base)/name
            if p.is_symlink():
                continue
            if p.suffix == '.app':
                try:
                    item = bundle(p)
                    embedded.append(item)
                    if item['bundle_id']:
                        identity.add(item['bundle_id'])
                except (OSError, ValueError, plistlib.InvalidFileException) as e:
                    err(e)
            elif name not in ('node_modules', '.git'):
                kept.append(name)
        dirs[:] = kept
        for name in names:
            if time.monotonic() > deadline or files >= max_files:
                stopped = True
                break
            files += 1
            p = Path(base)/name
            if p.is_symlink():
                continue
            try:
                if p.suffix.lower() in ('.html', '.htm') and len(titles) < 24:
                    with p.open('rb') as f:
                        text = f.read(128 * 1024).decode('utf-8', errors='replace')
                    m = re.search(r'<title[^>]*>(.*?)</title>', text, re.I|re.S)
                    if m:
                        title = html.unescape(re.sub('<[^>]*>', '', m.group(1))).strip()[:160]
                        if title and title not in [v['title'] for v in titles]:
                            titles.append({'path': str(p), 'title': title})
                elif name in ('resource_manifest.json', 'package.json') and p.stat().st_size < 1024*1024:
                    # Only vendor hostname from declared manifests; never output URL tokens or model configs.
                    j = json.loads(p.read_text())
                    def urls(v):
                        if isinstance(v, dict):
                            for x in v.values():urls(x)
                        elif isinstance(v, list):
                            for x in v:urls(x)
                        elif isinstance(v, str) and v.startswith(('https://','http://')):
                            host = urlsplit(v).hostname
                            if host:hosts.add(host)
                    urls(j)
            except (OSError, ValueError) as e:
                err(e)
    matches = []
    for app in apps:
        reason = None
        if app.get('bundle_id') in identity or app.get('bundle_id') == root.name:
            reason = 'exact_bundle_id'
        elif root.name.casefold() in (str(app.get('name','')).casefold(), Path(app['path']).stem.casefold()):
            reason = 'exact_name_candidate_not_proof'
        if reason:
            matches.append({**app, 'match_reason': reason})
    running = [p for p in processes if p['executable'].startswith(str(root) + '/') or any(p['executable'].startswith(app['path'] + '/') for app in matches)]
    related = []
    for component in components:
        bid = component.get('bundle_id') or ''
        if any(bid == ident or bid.startswith(ident + '.') for ident in identity) or root.name.casefold() in (str(component.get('name') or '').casefold(), Path(component['path']).stem.casefold()):
            related.append({**component, 'relationship':'candidate; shared use must be verified, not deletion permission'})
    startup = []
    for folder in [Path.home()/'Library/LaunchAgents',Path('/Library/LaunchAgents'),Path('/Library/LaunchDaemons')]:
        for p in folder.glob('*.plist'):
            try:
                if p.is_symlink() or p.stat().st_size > 1024*1024:continue
                j=plistlib.loads(p.read_bytes())
                executable=j.get('Program') or next(iter(j.get('ProgramArguments',[])), '')
                if isinstance(executable,str) and (executable.startswith(str(root) + '/') or any(executable.startswith(x['path'] + '/') for x in matches)):
                    startup.append({'plist':str(p),'label':j.get('Label'),'executable':executable})
            except (OSError,ValueError,plistlib.InvalidFileException):
                continue
    opened = {'status': 'not_checked'}
    if check_open:
        if sys.platform != 'darwin' or not shutil.which('lsof'):
            opened = {'status': 'unavailable'}
        else:
            try:
                r = subprocess.run(['lsof','-Fpc','+D',str(root)],capture_output=True,text=True,timeout=15)
                if r.returncode == 0 and r.stdout.strip():
                    opened = {'status':'in_use','processes':r.stdout.splitlines()[:60]}
                elif r.returncode == 1 and not r.stdout.strip() and not r.stderr.strip():
                    opened = {'status':'not_observed_in_use'}
                else:
                    opened = {'status':'unknown','error':r.stderr[:500]}
            except (OSError,subprocess.TimeoutExpired) as e:
                opened = {'status':'unknown','error':str(e)[:200]}
    return {'path':str(root),'observed_at':datetime.datetime.now().astimezone().isoformat(),
            'status':'partial' if stopped or errors else 'ok','limit_reached':stopped,
            'container_bundle_ids':sorted(identity), 'matching_installed_apps':matches,
            'installation_status':'matching_app_found_in_checked_roots' if matches else 'not_found_in_checked_roots',
            'embedded_app_copies':embedded,'html_title_hints':titles,'vendor_hosts':sorted(hosts),
            'running_matching_apps':running,'open_files':opened,'related_system_components':related,'related_startup_items':startup,'errors':errors,'files_examined':files,
            'shared_dependencies':'not_verified; separately inspect plugins/drivers/input methods/related products before deleting',
            'decision':'evidence_only; no automatic safe-to-delete classification'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('paths',nargs='*')
    p.add_argument('--scan-json',help='select application/user-dotdir candidates from current scan')
    p.add_argument('--min-mib',type=float,default=100)
    p.add_argument('--max-candidates',type=int,default=30)
    p.add_argument('--app-root',action='append',help='replace default inventory roots; repeatable')
    p.add_argument('--seconds',type=float,default=20)
    p.add_argument('--max-files',type=int,default=30000)
    p.add_argument('--check-open-files',action='store_true')
    a=p.parse_args()
    if a.seconds <= 0 or a.max_files <= 0 or a.max_candidates <= 0 or a.min_mib < 0:p.error('limits must be positive')
    selected=list(a.paths)
    omitted=[]
    if a.scan_json:
        scan=json.loads(Path(a.scan_json).read_text())
        candidates={}
        for group in ('app_support','containers','group_containers','caches','home'):
            for item in scan.get('groups',{}).get(group,[]):
                if group=='home' and not item.get('name','').startswith('.'):continue
                if item.get('size_kb',0) >= a.min_mib*1024:
                    candidates[item['path']]=item.get('size_kb',0)
        ordered=sorted(candidates,key=candidates.get,reverse=True)
        selected.extend(ordered[:a.max_candidates])
        omitted=ordered[a.max_candidates:]
    if not selected:p.error('provide data paths or --scan-json')
    selected=list(dict.fromkeys(selected))
    roots=[Path(x).expanduser().resolve() for x in (a.app_root or ['/Applications','~/Applications','/System/Applications'])]
    inv=inventory(roots)
    component_roots=[Path('/Library/Audio/Plug-Ins/HAL'),Path.home()/'Library/Audio/Plug-Ins/HAL',Path('/Library/Input Methods'),Path.home()/'Library/Input Methods']
    components=inventory(component_roots,('.app','.driver','.bundle','.appex'))
    process_rows=[]
    process_error=None
    try:
        ps=subprocess.run(['ps','-axo','pid=,comm='],capture_output=True,text=True,timeout=10)
        if ps.returncode!=0:process_error=ps.stderr[:300]
        for line in ps.stdout.splitlines():
            bits=line.strip().split(None,1)
            if len(bits)==2:process_rows.append({'pid':bits[0],'executable':bits[1]})
    except (OSError,subprocess.TimeoutExpired) as e:process_error=str(e)[:300]
    print(json.dumps({'candidate_coverage':{'selected':selected,'omitted_by_limit':omitted,'min_mib':a.min_mib,'note':'candidate screening only; unrecognized identity or absence does not prove residual'},'app_inventory':inv,'component_inventory':components,'process_check_error':process_error,'evidence':[evidence(x,inv['apps'],a.seconds,a.max_files,a.check_open_files,components['apps'],process_rows) for x in selected]},ensure_ascii=False,indent=2))

if __name__ == '__main__':main()
