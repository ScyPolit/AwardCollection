#!/usr/bin/env python3
"""Update only the web service after proving server-side source is unchanged."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import tarfile
import time
import urllib.request
from apply_release import BASE, PROJECT, PROJECT_NAME, compose, run, set_env, snapshot


def source_tree(root):
    ignored = {'.offline-wheels', '__pycache__', 'staticfiles'}
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file() and not ignored.intersection(path.relative_to(root).parts)
            and path.suffix not in {'.ttf', '.pyc'}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('revision')
    parser.add_argument('--archive', required=True)
    parser.add_argument('--archive-sha256', required=True)
    args = parser.parse_args()
    archive = Path(args.archive).resolve()
    if not re.fullmatch(r'[0-9a-f]{40}', args.revision) or not re.fullmatch(r'[0-9a-f]{64}', args.archive_sha256):
        raise ValueError('Full revision and SHA256 are required')
    if not archive.is_relative_to(BASE/'incoming') or hashlib.sha256(archive.read_bytes()).hexdigest() != args.archive_sha256:
        raise ValueError('Untrusted archive')
    stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    release = BASE/'releases'/(args.revision+'-web-'+stamp)
    release.mkdir(mode=0o700)
    with tarfile.open(archive) as bundle:
        bundle.extractall(release, filter='data')
    source = release/('AwardCollection-'+args.revision)
    config_before = json.loads(compose('config', '--format', 'json', capture=True).stdout)
    current_source = Path(config_before['services']['api']['build']['context']).parent
    for folder in ('backend', 'converter'):
        if source_tree(current_source/folder) != source_tree(source/folder):
            raise RuntimeError('A web-only release cannot change '+folder)
    services_before = {name: run(['docker','inspect','--format','{{.Id}} {{.Image}} {{.Created}}',PROJECT_NAME+'-'+name+'-1'], capture=True).stdout.strip() for name in ('api','worker','db','converter')}
    before = snapshot()
    checkpoint = BASE/'rollback'/('web-'+stamp)
    checkpoint.mkdir(mode=0o700)
    old_env, old_compose = (PROJECT/'.env').read_text(), (PROJECT/'compose.yaml').read_bytes()
    (checkpoint/'.env').write_text(old_env); os.chmod(checkpoint/'.env',0o600)
    (checkpoint/'compose.yaml').write_bytes(old_compose)
    image = run(['docker','inspect','--format','{{.Image}}',PROJECT_NAME+'-web-1'], capture=True).stdout.strip()
    tag = PROJECT_NAME+'-web:rollback-'+stamp
    run(['docker','tag',image,tag])
    state_path = PROJECT/'runtime/web-release-status.json'

    def progress(stage, **details):
        state = {'stage':stage,'revision':args.revision,'checkpoint':str(checkpoint),**details}
        state_path.write_text(json.dumps(state,indent=2)+'\n')
        print(json.dumps(state),flush=True)

    changed = False
    try:
        (PROJECT/'.env').write_text(set_env(old_env,{'WEB_SOURCE_DIR':source,'WEB_BUILD_VERSION':args.revision}))
        os.chmod(PROJECT/'.env',0o600)
        shutil.copyfile(source/'compose.yaml',PROJECT/'compose.yaml')
        config_after = json.loads(compose('config','--format','json',capture=True).stdout)
        if config_before['volumes'] != config_after['volumes']:
            raise RuntimeError('Volume identities changed')
        for name in services_before:
            original, updated = dict(config_before['services'][name]), dict(config_after['services'][name])
            original.pop('build',None); updated.pop('build',None)
            if original != updated:raise RuntimeError('Server runtime configuration changed: '+name)
        progress('build')
        compose('build','web',timeout=1800)
        changed = True
        compose('up','-d','--no-deps','web',timeout=180)
        progress('health')
        for _ in range(60):
            try:
                health = json.loads(urllib.request.urlopen('https://127.0.0.1:18443/api/v1/health/',context=ssl._create_unverified_context(),timeout=5).read())
                if health.get('status')=='ok':break
            except Exception:pass
            time.sleep(2)
        else:raise RuntimeError('Web proxy failed health check')
        actual = run(['docker','inspect','--format','{{index .Config.Labels "org.opencontainers.image.revision"}}',PROJECT_NAME+'-web-1'],capture=True).stdout.strip()
        if actual != args.revision:raise RuntimeError('Web revision mismatch')
        for name, identity in services_before.items():
            after_identity = run(['docker','inspect','--format','{{.Id}} {{.Image}} {{.Created}}',PROJECT_NAME+'-'+name+'-1'],capture=True).stdout.strip()
            if identity != after_identity:raise RuntimeError('Unexpected server recreation: '+name)
        if snapshot() != before:raise RuntimeError('Existing content changed')
        progress('done',backend_version=health.get('version'),server_containers_preserved=True,existing_content_preserved=True)
    except Exception as exc:
        (PROJECT/'.env').write_text(old_env);os.chmod(PROJECT/'.env',0o600)
        (PROJECT/'compose.yaml').write_bytes(old_compose)
        if changed:
            run(['docker','tag',tag,PROJECT_NAME+'-web:latest'])
            compose('up','-d','--no-deps','web',timeout=180)
        progress('failed',error=str(exc))
        raise


if __name__ == '__main__':
    main()
