#!/usr/bin/env python3
"""Create a curated source review directory. Never publish or initialize Git."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT_FILES = ['README.md','START_HERE.md','AGENTS.md','CONTRIBUTING.md','SECURITY.md','THIRD_PARTY_NOTICES.md','.gitignore','.vercelignore','.env.example','package.json','package-lock.json','tsconfig.json','vite.config.ts','index.html','vercel.json']
DOCS = ['LOCAL_APP_CHECK_2026-10-19.md','SETUP.md','GITHUB_AND_DEPLOYMENT.md','VERIFICATION.md','MODEL_CARD.md','HYPNEXIS_SUBMISSION.md','DEMO_SCRIPT.md','DEMO_CHECKLIST.md','SUBMISSION_CHECKLIST.md','OPERATIONS.md','API_CONTRACT.md','VERCEL_PREPARATION_2026-10-19.md','CLOUD_DEPLOYMENT.md']
SCRIPTS = ['start_demo.sh','storage_snapshot.py','vercel-preflight.mjs','check-vercel-preflight.mjs','export_review_package.py','cloud_integration_checks.py']
BACKEND = ['.env.example','requirements.txt','requirements-lock-macos-arm64.txt','pyproject.toml','models/README.md','requirements-cloud.txt','Dockerfile.vercel','Dockerfile.worker','.dockerignore','certs/supabase-root.crt','Dockerfile.identity','requirements-identity.txt']
MIGRATIONS = ['20261016000001_phase2_schema_and_policies.sql','20261018000002_private_security_settings.sql','README.md']


def selected(root):
    names=set(ROOT_FILES)
    names.update('docs/'+name for name in DOCS)
    names.update('scripts/'+name for name in SCRIPTS)
    names.update('backend/'+name for name in BACKEND)
    names.update('supabase/migrations/'+name for name in MIGRATIONS)
    names.update(p.relative_to(root).as_posix() for p in (root/'supabase/migrations').glob('*_*.sql'))
    names.update(['supabase/README.md','supabase/SCHEMA_PLAN.md'])
    for directory,extensions in [('src',{'.ts','.tsx','.css'}),('backend/app',{'.py'}),('backend/tests',{'.py'}),('.github',{'.yml','.md'})]:
        for path in (root/directory).rglob('*'):
            if path.is_file() and path.suffix in extensions and '__pycache__' not in path.parts:
                names.add(path.relative_to(root).as_posix())
    names.update(path.relative_to(root).as_posix() for path in (root/'qa').glob('*_checks.cjs'))
    for name in ('public/favicon.svg','docs/assets/login.jpg'):
        if (root/name).is_file():names.add(name)
    for name in ('LICENSE','LICENSE.md'):
        if (root/name).is_file():names.add(name)
    missing=[name for name in names if not (root/name).is_file()]
    if missing:raise ValueError('Missing package inputs: '+', '.join(sorted(missing)))
    return sorted(names)


def validate(root,names):
    for name in names:
        path=root/name
        if path.is_symlink():raise ValueError('Symbolic file excluded: '+name)
        if name=='docs/assets/login.jpg':
            image=path.read_bytes()
            if not image.startswith(b'\xff\xd8\xff') or len(image)>2*1024*1024:raise ValueError('Invalid reviewed UI screenshot')
            continue
        text=path.read_text(encoding='utf-8')
        for candidate in re.findall(r'sb_secret_[A-Za-z0-9_-]{20,}',text):
            if 'ISOLATED_TEST' not in candidate:raise ValueError('Possible server secret in '+name)
        for candidate in re.findall(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',text):
            try:
                payload=candidate.split('.')[1]
                claims=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
            except Exception:continue
            if claims.get('role')=='service_role':raise ValueError('Privileged token in '+name)
        if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',text):
            raise ValueError('Private key in '+name)
    # If initialized later, prevent accidental staging of files outside this curated list.
    result=subprocess.run(['git','ls-files','-z'],cwd=root,capture_output=True)
    if result.returncode==0:
        tracked={name for name in result.stdout.decode().split('\0') if name}
        unexpected=tracked-set(names)-{'PACKAGE_MANIFEST.json'}
        if unexpected:raise ValueError('Tracked files outside reviewed package: '+', '.join(sorted(unexpected)))


def export(root,output):
    root=Path(root).resolve(); names=selected(root);validate(root,names)
    output=Path(output).absolute()
    if output.exists() or output.is_symlink():raise ValueError('Output must be a new directory.')
    if output.is_relative_to(root):raise ValueError('Choose an output outside the source project.')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.sightline-review-',dir=output.parent))
    try:
        manifest=[]
        for name in names:
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(root/name,target)
            manifest.append({'path':name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'bytes':target.stat().st_size})
        (stage/'PACKAGE_MANIFEST.json').write_text(json.dumps({'format':1,'scope':'Curated source review; private model, footage, secrets and owner data excluded. Not a published release.','files':manifest},indent=2))
        if output.exists() or output.is_symlink():raise ValueError('Output appeared; refusing overwrite.')
        stage.rename(output)
    except Exception:
        shutil.rmtree(stage);raise
    return len(names)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    try:
        if args.check:
            names=selected(root);validate(root,names);print(f'Reviewed {len(names)} source/configuration files; no matched secret patterns. No upload performed.')
        elif args.output:
            print(f'Prepared {export(root,args.output)} files for owner review. No Git initialization or upload performed.')
        else:parser.error('Choose --check or --output')
    except (ValueError,OSError,UnicodeError) as error:parser.exit(1,str(error)+'\n')


if __name__=='__main__':main()
