"""Headless tests for desktop routing and bank-save boundaries, not visual QA."""
import ast
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import desktop
from question_bank import read_bank


class DesktopWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app = desktop.DesktopApp.__new__(desktop.DesktopApp)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app.data_dir = Path(self.temp.name)
        self.app.notice = MagicMock()

    def test_clean_navigation_does_not_prompt(self):
        self.app.form_snapshot = lambda: ('original',)
        self.app.form_initial = ('original',)
        self.assertTrue(self.app.leave_form(MagicMock()))
        self.app.notice.assert_not_called()

    def test_dirty_navigation_waits_for_inline_choice(self):
        self.app.form_snapshot = lambda: ('changed',)
        self.app.form_initial = ('original',)
        self.app.feedback = MagicMock()
        action = MagicMock()
        with patch.object(desktop.tk, 'Frame'), patch.object(desktop, 'button') as button:
            self.assertFalse(self.app.leave_form(action))
            action.assert_not_called()
            choices = {call.args[1]: call.args[2] for call in button.call_args_list}
            choices['Keep editing']()
            action.assert_not_called()
            self.assertIsNotNone(self.app.form_snapshot)
            choices['Discard changes']()
            action.assert_called_once()
            self.assertIsNone(self.app.form_snapshot)

    def test_editing_example_creates_local_copy(self):
        source = desktop.ROOT / 'examples/questions.json'
        before = source.read_bytes()
        bank = read_bank(source)
        bank['title'] = 'My editable copy'
        self.app.persist_bank(bank, source)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(self.app.bank_path.parent, self.app.data_dir / 'banks')
        self.assertEqual(read_bank(self.app.bank_path)['title'], bank['title'])

    def test_bank_rename_keeps_path_and_backs_up(self):
        bank = read_bank(desktop.ROOT / 'examples/questions.json')
        self.app.persist_bank(bank)
        path = self.app.bank_path
        renamed = copy.deepcopy(bank)
        renamed['title'] = 'Renamed'
        self.app.persist_bank(renamed, path)
        self.assertEqual(path, self.app.bank_path)
        self.assertEqual(read_bank(path)['title'], 'Renamed')
        self.assertTrue(list((self.app.data_dir / 'backups').glob('*/*.json')))

    def test_library_workflows_do_not_create_dialogs(self):
        tree = ast.parse(Path(desktop.__file__).read_text(encoding='utf-8'))
        functions = {'group_form', 'edit_word', 'import_form', 'bank_form', 'edit_question', 'saved'}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in functions:
                for call in ast.walk(node):
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
                        self.assertNotIn(call.func.attr, {'Toplevel', 'askstring', 'showinfo', 'showerror', 'askyesno'})

    def test_plain_question_group(self):
        text = '1. First question?\nA. One\nB. Two\nC. Three\nD. Four\nAnswer: A\n\n2) Second question?\nA) Red\nB) Blue\nC) Green\nD) White'
        bank, notes = desktop.parse_questions(text)
        self.assertEqual(len(bank['questions']), 2)
        self.assertEqual(bank['questions'][0]['answer'], 'A')
        self.assertFalse(bank['questions'][1]['answer'])
        self.assertTrue(notes)
        with self.assertRaises(ValueError):
            desktop.parse_questions('1. Incomplete?\nA. Only one option')

    def test_shortcuts_inactive_in_editors_and_exam(self):
        self.app.root = MagicMock()
        self.app.review_active = False
        self.app.rate_review = MagicMock()
        event = SimpleNamespace(keysym='1', state=0, widget=MagicMock())
        self.app.review_key(event)
        self.app.review_active = True
        self.app.review_key(event)
        self.app.rate_review.assert_not_called()

    def test_shortcuts_consume_one_key_press_and_require_reveal(self):
        self.app.root = MagicMock()
        self.app.review_active = True
        self.app.review_key_down = set()
        self.app.review_key_time = 0
        self.app.revealed = False
        self.app.review_card = MagicMock()
        event = SimpleNamespace(keysym='space', state=0, widget=MagicMock())
        event.widget.winfo_toplevel.return_value = self.app.root
        self.assertEqual(self.app.review_key(event), 'break')
        self.assertTrue(self.app.revealed)
        self.app.review_key(event)
        self.app.review_card.assert_called_once()
        self.app.revealed = False
        self.app.store = MagicMock()
        self.app.rate_review('remembered')
        self.app.store.rate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
