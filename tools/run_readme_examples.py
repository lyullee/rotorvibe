"""Execute this repository's trusted Python README/user-guide examples separately."""
import argparse,contextlib,io,json,re,sys
from pathlib import Path


def run(root,*,installed=False):
    root=Path(root).resolve()
    if not installed: sys.path.insert(0,str(root))
    import rotorvibe
    if installed and Path(rotorvibe.__file__).resolve().is_relative_to(root):
        raise ValueError('Expected installed distribution outside the source checkout.')
    rows=[]
    for document in ('README.md','README.ko.md','docs/USER_GUIDE.md'):
        content=(root/document).read_text(encoding='utf8')
        for index,code in enumerate(re.findall(r'```python\s*\n(.*?)```',content,re.S),1):
            namespace={'__name__':'__main__'}
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compile(code,document+':'+str(index),'exec'),namespace)
            rows.append({'document':document,'block':index,'status':'pass'})
    if not rows: raise ValueError('No executable examples found.')
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--installed',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(Path(__file__).resolve().parents[1],installed=args.installed),indent=2))
