"""Tiny MAT fixtures verify original acquisition grouping and reserved-test access."""
import csv,io,tempfile,unittest,zipfile,hashlib,json
from pathlib import Path
import numpy as np
from scipy.io import savemat
from vibration.independent_data import IndependentRotorCatalog


class IndependentDataChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); raw=self.root/'raw/cross_speed'; raw.mkdir(parents=True)
        stream=io.BytesIO(); savemat(stream,{'signals':np.ones((4,25600)),'fs':25600,'speed_rpm':600,'original_file':'run1','second_id':1,'condition':'healthy'})
        blob=stream.getvalue()
        with zipfile.ZipFile(raw/'normal_600rpm.zip','w') as archive: archive.writestr('a.mat',blob)
        rows=[dict(sample_id='a',archive_name='normal_600rpm.zip',archived_filename='a.mat',condition='normal',speed_rpm='600',original_file='run1',second_id='1',group_id='normal|run1',file_sha256=hashlib.sha256(blob).hexdigest()),
              dict(sample_id='reserved',archive_name='missing.zip',archived_filename='b.mat',condition='normal',speed_rpm='1200',original_file='reserved_run',second_id='1',group_id='normal|reserved_run',file_sha256='0'*64)]
        with (raw/'dataset_manifest.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
        with (raw/'recording_disjoint_partitions.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['scenario','role','sample_id']); w.writeheader()
            w.writerows([dict(scenario='MS_600_900_to_1200',role='train',sample_id='a'),dict(scenario='MS_600_900_to_1200',role='test',sample_id='reserved')])
        self.catalog=IndependentRotorCatalog(self.root)

    def tearDown(self): self.tmp.cleanup()

    def test_source_mat_identity_and_unknown_unit_are_preserved(self):
        a,meta=self.catalog.load('cross_speed:a')
        self.assertEqual(a.shape,(25600,4)); self.assertEqual(meta['unit'],'unknown')
        self.assertEqual(meta['group_id'],'normal|run1'); self.assertEqual(meta['role'],'source_train'); self.assertEqual(meta['reference_label'],'normal')

    def test_reserved_access_is_refused_before_opening_missing_archive(self):
        with self.assertRaises(PermissionError): self.catalog.load('cross_speed:reserved')
        self.assertFalse((self.root/'metadata/reserved_access.jsonl').exists())

    def test_explicit_final_open_is_audited_before_signal_decoding(self):
        with self.assertRaises(FileNotFoundError): self.catalog.load('cross_speed:reserved',frozen_model_sha256='a'*64)
        entry=json.loads((self.root/'metadata/reserved_access.jsonl').read_text())
        self.assertEqual(entry['frozen_model_sha256'],'a'*64)

    def test_checksum_mismatch_is_not_silently_loaded(self):
        self.catalog.records['cross_speed:a']['file_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'checksum'): self.catalog.load('cross_speed:a')

    def test_archive_path_escape_is_refused(self):
        with self.assertRaises(ValueError): self.catalog._archive('../outside.zip')

    def test_role_filter_keeps_target_out_of_source_normal_list(self):
        rows=self.catalog.rows(role='source_train',normal_only=True)
        self.assertEqual([r['id'] for r in rows],['cross_speed:a'])

    def test_truncated_derived_lvm_columns_do_not_drop_acceleration_samples(self):
        folder=self.root/'raw/marra'; folder.mkdir()
        lines=['LabVIEW Measurement\t','X_Value\tTime\tTrigger\tAH\tAV\tBH\tBV\tVH\tVV\tWH\tWV']
        for i in range(36000):
            time=f'{i/6000:.6f}' if i<35900 else ''
            lines.append(f'{i}\t{time}\t{int(i%300<10)}\t1\t2\t3\t4\t\t\t\t')
        with zipfile.ZipFile(folder/'Baseline.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('Baseline/20Hz/sample.lvm','\n'.join(lines))
        a,meta=self.catalog.load_marra('Baseline.zip','Baseline/20Hz/sample.lvm')
        self.assertEqual(a.shape,(36000,4)); np.testing.assert_array_equal(a[-1],[1,2,3,4]); self.assertEqual(meta['rpm'],1200)

    def test_partition_rejects_same_acquisition_across_roles(self):
        path=self.root/'raw/cross_speed/dataset_manifest.csv'; text=path.read_text().replace('normal|reserved_run','normal|run1'); path.write_text(text)
        with self.assertRaisesRegex(ValueError,'crosses'): IndependentRotorCatalog(self.root)

if __name__=='__main__': unittest.main()
