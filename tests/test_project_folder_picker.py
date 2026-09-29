"""Native picker protocol: preserve Unicode paths and cancellation, isolate errors."""
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from cfd_studio.project_storage import ProjectStorage


class FolderPickerTests(unittest.TestCase):
    def call(self, result=None, error=None, start=''):
        with patch('cfd_studio.project_storage.os.name', 'nt'), patch('cfd_studio.project_storage.subprocess.run', return_value=result, side_effect=error) as run:
            value=ProjectStorage.pick_project_folder(None,start)
            return value,run.call_args

    def test_unicode_drive_path_is_returned_without_code_interpolation(self):
        start='D:\\실험\\$(not-code)';selected='D:\\해석 결과\\새 프로젝트'
        result,args=self.call(SimpleNamespace(returncode=0,stdout=selected.encode('utf-8')),start=start)
        self.assertEqual(result,{'path':selected,'cancelled':False})
        self.assertEqual(args.kwargs['env']['CFD_PROJECT_PICK_START'],start)
        self.assertNotIn(start,args.args[0][-1])
        self.assertEqual(args.kwargs['creationflags'],0x08000000)
        self.assertIn('-STA',args.args[0])

    def test_owner_is_topmost_and_disposed_for_all_dialog_outcomes(self):
        result,args=self.call(SimpleNamespace(returncode=0,stdout=b''))
        self.assertEqual(result,{'path':'','cancelled':True})
        command=args.args[0][-1]
        self.assertIn('$owner.TopMost=$true',command)
        self.assertIn('$d.ShowDialog($owner)',command)
        self.assertIn('finally{$d.Dispose();$owner.Close();$owner.Dispose()}',command)

    def test_native_failure_is_not_reported_as_cancelled(self):
        with self.assertRaisesRegex(ValueError,'열지 못'):
            self.call(SimpleNamespace(returncode=1,stdout=b''))

    def test_timeout_offers_retry_instead_of_leaving_the_ui_busy(self):
        with self.assertRaisesRegex(ValueError,'시간이 초과'):
            self.call(error=subprocess.TimeoutExpired('powershell',600))
