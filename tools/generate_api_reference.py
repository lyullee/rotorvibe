"""Regenerate original API declarations from source without importing services."""
import ast,json,tomllib
from pathlib import Path


def generate(root):
    root=Path(root).resolve()
    version=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf8'))['project']['version']
    lines=['# Complete public API reference','',f'Source-derived declarations for RotorVibe {version} candidate.',
           'README and P1_GUIDE.md/P2_GUIDE.md explain purpose, units, shapes, outputs and lifecycle.',
           'Candidate not yet published. Experimental life APIs are explicitly separate.','']
    catalog=[]
    for path in sorted((root/'vibration').rglob('*.py')):
        tree=ast.parse(path.read_text(encoding='utf8')); rel=path.relative_to(root).as_posix()
        nodes=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and not n.name.startswith('_')]
        interfaces=[]
        if nodes: lines+=['## '+rel,'',f'[Implementation](../{rel})','']
        for node in nodes:
            if isinstance(node,ast.FunctionDef):
                declaration=f'{node.name}({ast.unparse(node.args)})'
                interfaces.append(declaration); lines+=['```python',declaration,'```','']; continue
            lines+=['### '+node.name,'']
            fields=[n for n in node.body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name)]
            if fields:
                lines+=['| Constructor field | Type | Default |','|---|---|---|']
                for n in fields:
                    annotation=ast.unparse(n.annotation).replace('|','\\|')
                    default=(ast.unparse(n.value) if n.value else 'required').replace('|','\\|')
                    lines.append(f'| `{n.target.id}` | `{annotation}` | `{default}` |')
                lines+=['']
                interfaces.append(node.name+'('+', '.join(n.target.id for n in fields)+')')
            for n in node.body:
                if isinstance(n,ast.FunctionDef) and (not n.name.startswith('_') or n.name in ('__init__','__call__')):
                    declaration=f'{node.name}.{n.name}({ast.unparse(n.args)})'
                    interfaces.append(declaration); lines+=['```python',declaration,'```','']
        catalog.append({'module':rel,'role':(ast.get_docstring(tree) or 'See implementation and operating guides.').splitlines()[0],
                        'interfaces':interfaces})
    (root/'docs/API_REFERENCE.md').write_text('\n'.join(lines).rstrip()+'\n',encoding='utf8')
    (root/'research/module_catalog.json').write_text(json.dumps(catalog,indent=2)+'\n',encoding='utf8')
    return {'version':version,'modules':len(catalog),'interfaces':sum(len(m['interfaces']) for m in catalog)}


if __name__=='__main__': print(json.dumps(generate(Path(__file__).resolve().parents[1])))
