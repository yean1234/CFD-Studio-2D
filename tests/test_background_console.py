"""Status polling must not allocate Windows console windows."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

class BackgroundConsoleTests(unittest.TestCase):
    def test_status_wsl_call_hides_console_and_preserves_output(self):
        source=Path(__file__).resolve().parents[1]/'cfd_studio/app.py'
        tree=ast.parse(source.read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='wsl')
        runner=Mock(return_value=SimpleNamespace(returncode=0,stdout=b'OK',stderr=b''))
        env={'subprocess':SimpleNamespace(run=runner),'os':SimpleNamespace(name='nt'),
             '_wsl_argv':lambda *args:['wsl.exe',*args]}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<wsl>','exec'),env)
        self.assertEqual(env['wsl']('echo OK'),(True,'OK'))
        self.assertEqual(runner.call_args.kwargs['creationflags'],0x08000000)
        self.assertEqual(runner.call_args.kwargs['input'],b'echo OK')
        env['os'].name='posix';env['wsl']('echo OK')
        self.assertEqual(runner.call_args.kwargs['creationflags'],0)
