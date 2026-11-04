"""The new original-recording holdout cannot be opened by development callers."""
import tempfile,json,hashlib,unittest
from pathlib import Path
from vibration.condition_data import UosRotorCatalog


class NewRecordingGuardChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); (self.root/'metadata').mkdir()
        rows=[{'id':'test','role':'reserved_new_test','path':'missing.mat','rpm':1200,'sample_rate_hz':16000}]
        (self.root/'metadata/record_plan.json').write_text(json.dumps(rows))
        self.catalog=UosRotorCatalog(self.root)
    def tearDown(self): self.tmp.cleanup()

    def test_no_hash_refuses_before_reading_missing_mat(self):
        with self.assertRaises(PermissionError): self.catalog.load('test')
        self.assertFalse((self.root/'metadata/new_test_access.jsonl').exists())

    def test_explicit_open_records_model_identity_before_decoding(self):
        with self.assertRaises(FileNotFoundError): self.catalog.load('test',frozen_model_sha256='a'*64)
        row=json.loads((self.root/'metadata/new_test_access.jsonl').read_text())
        self.assertEqual(row['model_sha256'],'a'*64); self.assertEqual(row['purpose'],'frozen_final_test')

    def test_extra_matched_reference_has_distinct_role_and_rate(self):
        (self.root/'metadata/matched_normal_plan.json').write_text(json.dumps([{'id':'normal8k','role':'matched_normal_reference','sample_rate_hz':8000}]))
        catalog=UosRotorCatalog(self.root)
        self.assertEqual(len(catalog.rows('reserved_new_test')),1)
        self.assertEqual(catalog.rows('matched_normal_reference')[0]['sample_rate_hz'],8000)

if __name__=='__main__': unittest.main()
