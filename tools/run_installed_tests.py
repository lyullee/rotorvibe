"""Run portable regressions against a wheel outside the source checkout.

Only tests and two project-authored helpers are copied, never package code.
Default release mode refuses skipped tests, including a missing optional bridge.
"""
import argparse,json,shutil,sys,tempfile,unittest
from pathlib import Path


def run(root,*,allow_optional_skips=False):
    root=Path(root).resolve()
    import rotorvibe,vibration
    for module in (rotorvibe,vibration):
        path=Path(module.__file__).resolve()
        if path.is_relative_to(root) or not path.is_relative_to(Path(sys.prefix).resolve()):
            raise ValueError('Install the wheel in a venv and run outside the source checkout.')
    if sys.prefix==sys.base_prefix: raise ValueError('Isolated virtual environment required.')
    with tempfile.TemporaryDirectory(prefix='rotorvibe-installed-tests-') as folder:
        temporary=Path(folder)
        for part in ('tests','tools','scripts'): (temporary/part).mkdir()
        for path in (root/'tests').glob('*.py'): shutil.copy2(path,temporary/'tests'/path.name)
        for relative in ('tools/release_contract.py','scripts/external_blind_metrics.py'):
            shutil.copy2(root/relative,temporary/relative)
        sys.path.insert(0,str(temporary))
        try:
            suite=unittest.defaultTestLoader.discover(str(temporary/'tests'))
            result=unittest.TextTestRunner(verbosity=1).run(suite)
        finally:
            sys.path.remove(str(temporary))
    from vibration.adapters import process_adapter_info
    passed=result.wasSuccessful() and (allow_optional_skips or not result.skipped)
    return {'status':'pass' if passed else 'fail','version':rotorvibe.__version__,
            'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'skips':len(result.skipped),'python':sys.version.split()[0],
            'optional_bridge':process_adapter_info(),
            'isolation':'venv site-packages outside source; only tests and helpers copied',
            'skips_allowed':bool(allow_optional_skips)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-optional-skips',action='store_true'); parser.add_argument('--output')
    args=parser.parse_args()
    report=run(Path(__file__).resolve().parents[1],allow_optional_skips=args.allow_optional_skips)
    content=json.dumps(report,indent=2)+'\n'
    if args.output: Path(args.output).write_text(content,encoding='utf8')
    print(content); raise SystemExit(report['status']!='pass')
