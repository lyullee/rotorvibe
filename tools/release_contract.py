"""Read-only tag/source verification; never restores source, commits or pushes."""
import argparse,ast,hashlib,re,subprocess,tomllib
from pathlib import Path


def verify_tag(root,tag,*,check_git=True):
    root=Path(root)
    if not isinstance(tag,str) or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?',tag):
        raise ValueError('Release requires a version tag such as v0.1.0a2, never a branch.')
    version=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf8'))['project']['version']
    if tag!='v'+version: raise ValueError('Tag and package version differ.')
    for package in ('rotorvibe','vibration'):
        tree=ast.parse((root/package/'__init__.py').read_text(encoding='utf8'))
        declared=[ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                  and any(isinstance(t,ast.Name) and t.id=='__version__' for t in n.targets)]
        if declared!=[version]: raise ValueError('Facade version differs: '+package)
    if check_git:
        def git(*args): return subprocess.check_output(['git','-C',str(root),*args],text=True,stderr=subprocess.PIPE).strip()
        try:
            commit=git('rev-parse','--verify','refs/tags/'+tag+'^{commit}')
            if commit!=git('rev-parse','HEAD'): raise ValueError('HEAD is not the requested release tag.')
            if git('status','--porcelain','--untracked-files=normal'): raise ValueError('Release source must be clean.')
        except subprocess.CalledProcessError as exc: raise ValueError('Release tag must exist in this checkout.') from exc
    return version


def write_checksums(folder,target):
    folder=Path(folder); paths=sorted(p for p in folder.iterdir() if p.is_file())
    if len(paths)!=2 or sum(p.suffix=='.whl' for p in paths)!=1 or sum(p.name.endswith('.tar.gz') for p in paths)!=1:
        raise ValueError('Expected exactly one wheel and one source archive.')
    target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in paths),encoding='ascii')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag'); parser.add_argument('--dist'); parser.add_argument('--checksums')
    args=parser.parse_args()
    if args.tag: print('Verified release '+verify_tag(Path(__file__).resolve().parents[1],args.tag))
    if args.dist and args.checksums: write_checksums(args.dist,args.checksums)
    if not args.tag and not (args.dist and args.checksums): parser.error('Supply --tag or --dist with --checksums')
