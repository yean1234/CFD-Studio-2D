"""Verify the real HTML entrypoint and the static route without starting Studio."""
import ast
from html.parser import HTMLParser
from pathlib import Path
import unittest
from cfd_studio.execution_workspace import get_route

ROOT = Path(__file__).resolve().parents[1]

class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []
    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.sources.append(dict(attrs).get('src'))

class AgentDeliveryTests(unittest.TestCase):
    def test_html_loads_agent_after_workspace_and_translations(self):
        tree = ast.parse((ROOT/'cfd_studio/app.py').read_text(encoding='utf-8'))
        html = next(node.value.value for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'INDEX_HTML' for t in node.targets)
                    and isinstance(node.value, ast.Constant))
        parser = Scripts()
        parser.feed(html)
        self.assertEqual(parser.sources.count('/agent_controls.js'), 1)
        self.assertLess(parser.sources.index('/execution_workspace.js'), parser.sources.index('/agent_controls.js'))
        self.assertLess(parser.sources.index('/i18n_help.js'), parser.sources.index('/agent_controls.js'))

    def test_route_serves_exact_script_without_workspace_access(self):
        class Handler:
            path = '/agent_controls.js'
            def _send(self, code, body, content_type):
                self.result = (code, body, content_type)
        handler = Handler()
        self.assertTrue(get_route(handler, None))
        self.assertEqual(handler.result, (200, (ROOT/'cfd_studio/internal/agent_controls.js').read_bytes(), 'text/javascript; charset=utf-8'))
