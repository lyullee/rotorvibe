"""Exercise the release guard against real local Git refs; no remote mutation."""
import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
from tools.release_contract import verify_tag,write_checksums


class ReleaseChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        (self.root/'pyproject.toml').write_text('[project]\nversion="0.1.0a2"\n',encoding='utf8')
        for name in ('rotorvibe','vibration'):
            (self.root/name).mkdir(); (self.root/name/'__init__.py').write_text('__version__="0.1.0a2"\n',encoding='utf8')
        self.git('init','-q'); self.git('config','user.name','Local release test')
        self.git('config','user.email','test@example.invalid')
        self.git('add','.'); self.git('commit','-qm','fixture'); self.git('tag','v0.1.0a2')

    def tearDown(self):
        # Git's object files may be read-only on Windows; TemporaryDirectory
        # already handles that platform case for its exclusively owned tree.
        self.temp.cleanup()

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.STDOUT,text=True).strip()

    def test_clean_tag_passes_without_source_or_ref_changes(self):
        before=self.git('show-ref'); digest=hashlib.sha256((self.root/'pyproject.toml').read_bytes()).hexdigest()
        self.assertEqual(verify_tag(self.root,'v0.1.0a2'),'0.1.0a2')
        self.assertEqual(before,self.git('show-ref')); self.assertEqual(self.git('status','--porcelain'),'')
        self.assertEqual(digest,hashlib.sha256((self.root/'pyproject.toml').read_bytes()).hexdigest())

    def test_branch_or_injected_text_cannot_be_a_release_tag(self):
        for tag in ('main','refs/heads/main','v0.1.0a2; echo bad','v0.1.0a2\n','../v0.1.0a2','v0.1.0a2-extra'):
            with self.subTest(tag=tag),self.assertRaises(ValueError): verify_tag(self.root,tag)

    def test_mismatched_package_or_facade_version_rejected(self):
        with self.assertRaises(ValueError): verify_tag(self.root,'v0.1.0a1')
        (self.root/'rotorvibe/__init__.py').write_text('__version__="0.1.0a1"\n',encoding='utf8')
        with self.assertRaises(ValueError): verify_tag(self.root,'v0.1.0a2')

    def test_missing_ref_rejected(self):
        self.git('tag','-d','v0.1.0a2')
        with self.assertRaises(ValueError): verify_tag(self.root,'v0.1.0a2')

    def test_new_head_is_not_mistaken_for_existing_tag(self):
        (self.root/'README.md').write_text('new source',encoding='utf8')
        self.git('add','.'); self.git('commit','-qm','new source')
        with self.assertRaises(ValueError): verify_tag(self.root,'v0.1.0a2')

    def test_dirty_and_untracked_sources_rejected(self):
        (self.root/'vibration/__init__.py').write_text('__version__="0.1.0a2"\n# changed\n',encoding='utf8')
        with self.assertRaises(ValueError): verify_tag(self.root,'v0.1.0a2')
        self.git('checkout','--','vibration/__init__.py')
        (self.root/'untracked.py').write_text('pass\n',encoding='utf8')
        with self.assertRaises(ValueError): verify_tag(self.root,'v0.1.0a2')

    def test_checksums_cover_exact_bytes_of_both_artifacts(self):
        dist=self.root/'dist'; dist.mkdir(); expected={}
        for name,value in [('a.whl',b'wheel bytes'),('a.tar.gz',b'source bytes')]:
            (dist/name).write_bytes(value); expected[name]=hashlib.sha256(value).hexdigest()
        target=self.root/'metadata/SHA256SUMS.txt'; write_checksums(dist,target)
        actual={name:digest for digest,name in (line.split() for line in target.read_text().splitlines())}
        self.assertEqual(actual,expected)
        (dist/'extra.whl').write_bytes(b'extra')
        with self.assertRaises(ValueError): write_checksums(dist,target)


if __name__=='__main__': unittest.main()
