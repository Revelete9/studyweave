import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from desktop_host import Workspace, make_server, main


class HostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Workspace(self.temp.name)
        self.book = self.app.store.state['books'][0]['id']
        self.group = self.app.store.state['groups'][0]['id']

    def call(self, action, **args):
        return self.app.dispatch(action, {'revision': self.app.revision(), **args})

    def test_reads_same_data_and_preserves_records_through_transfer_and_undo(self):
        self.call('begin', group_id=self.group)
        self.call('rate', group_id=self.group, cursor=0, result='forgotten')
        book = self.call('book', name='Target')['id']
        group = self.call('group', name='Empty', book_id=book)['id']
        before = copy.deepcopy(self.app.store.state)
        word = self.app.store.group(self.group)['words'][0]
        moved = self.call('transfer',kind='word',source=self.group,target=group,ids=[word['id']])
        self.assertTrue(moved['canUndo'])
        self.assertEqual(self.app.store.group(group)['words'][0],word)
        self.call('undo')
        self.assertEqual(self.app.store.state,before)
        self.assertEqual(Workspace(self.temp.name).store.state,before)

    def test_stale_edits_and_double_rating_are_rejected(self):
        revision = self.app.revision()
        self.call('book',name='New')
        with self.assertRaises(ValueError):
            self.app.dispatch('group',dict(revision=revision,name='Stale',book_id=self.book))
        self.call('begin',group_id=self.group)
        self.call('rate',group_id=self.group,cursor=0,result='remembered')
        with self.assertRaises(ValueError):
            self.call('rate',group_id=self.group,cursor=0,result='remembered')

    def test_external_change_detected_instead_of_overwritten(self):
        self.call('book',name='First')
        other = Workspace(self.temp.name)
        other.dispatch('book',dict(revision=other.revision(),name='External'))
        with self.assertRaises(ValueError):
            self.call('book',name='Unsafe')
        self.assertIn('External',[b['name'] for b in self.call('load')['state']['books']])
        self.assertNotIn('Unsafe',[b['name'] for b in self.app.store.state['books']])

    def test_import_preview_no_mutation_and_invalid_import_atomic(self):
        before = copy.deepcopy(self.app.store.state)
        preview = self.call('preview',text='1. lucid: clear',format='plain')
        self.assertEqual(preview['preview'][0]['term'],'lucid')
        self.assertEqual(before,self.app.store.state)
        with self.assertRaises(ValueError):
            self.call('import',text='invalid',format='plain',book_id=self.book,name='Fail')
        self.assertEqual(before,self.app.store.state)
        result = self.call('import',text='1. lucid: clear',format='plain',book_id=self.book,name='Pasted')
        self.assertEqual(self.app.store.group(result['id'])['name'],'Pasted')

    def test_bank_create_edit_and_stale_guard(self):
        bank_id=self.call('bank',name='Practice')['id']
        original={'schema_version':1,'title':'Practice','questions':[]}
        text='1. Pick one.\nA. One\nB. Two\nC. Three\nD. Four\nAnswer: A'
        self.call('bank',id=bank_id,original=original,text=text,format='plain')
        with self.assertRaises(ValueError):
            self.call('bank',id=bank_id,original=original,name='Stale')
        bank=next(b for b in self.call('load')['banks'] if b['id']==bank_id)
        self.assertEqual(len(bank['questions']),1)

    def test_bulk_import_directly_into_new_bank(self):
        text='1. Pick one.\nA. One\nB. Two\nC. Three\nD. Four\nAnswer: A'
        result=self.call('bank',name='Direct paste',text=text,format='plain')
        bank=next(b for b in result['banks'] if b['id']==result['id'])
        self.assertEqual(bank['title'],'Direct paste')
        self.assertEqual(len(bank['questions']),1)

    def clipboard_text(self, names=('Clarity',)):
        return json.dumps({'format': 'sat-study-kit/groups', 'version': 1, 'groups': [
            {'name': name, 'words': [{'term': 'lucid', 'phonetic': '/ˈluːsɪd/',
                                      'meaning': 'clear', 'expansion': 'lucid prose'}]}
            for name in names]})

    def test_paste_copied_groups_keeps_fields_progress_and_supports_undo(self):
        self.call('begin', group_id=self.group)
        self.call('rate', group_id=self.group, cursor=0, result='forgotten')
        before = copy.deepcopy(self.app.store.state)
        text = self.clipboard_text(('Clarity', 'Usage'))
        preview = self.call('preview_groups', book_id=self.book, text=text)
        self.assertEqual(before, self.app.store.state)
        self.assertEqual(len(preview['group_preview']), 2)
        result = self.call('paste_groups', book_id=self.book, text=text)
        self.assertTrue(result['canUndo'])
        word = self.app.store.group(result['group_ids'][0])['words'][0]
        self.assertEqual((word['phonetic'], word['expansion']), ('/ˈluːsɪd/', 'lucid prose'))
        self.assertEqual((word['remembered'], word['forgotten'], word['encounters']), (0, 0, 0))
        self.assertEqual(self.app.store.group(self.group), before['groups'][0])
        self.call('undo')
        self.assertEqual(before, self.app.store.state)

    def test_duplicate_names_are_copied_without_overwriting_and_plan_is_extended(self):
        self.call('begin', book_id=self.book)
        text = self.clipboard_text(('Clarity', 'Clarity'))
        first = self.call('paste_groups', book_id=self.book, text=text)
        preview = self.call('preview_groups', book_id=self.book, text=text)
        self.assertEqual([g['name'] for g in preview['group_preview']], ['Clarity (copy 2)', 'Clarity (copy 3)'])
        self.assertEqual([self.app.store.group(gid)['name'] for gid in first['group_ids']], ['Clarity', 'Clarity (copy)'])
        self.assertTrue(set(first['group_ids']) <= set(self.app.store.state['book_sessions'][self.book]['order']))

    def test_invalid_clipboard_and_save_errors_never_partially_paste(self):
        before = copy.deepcopy(self.app.store.state)
        pack = json.loads(self.clipboard_text(('Valid', 'Invalid')))
        pack['groups'][1]['words'][0]['id'] = 'untrusted-id'
        with self.assertRaises(ValueError):
            self.call('paste_groups', book_id=self.book, text=json.dumps(pack))
        self.assertEqual(before, self.app.store.state)
        with patch.object(self.app.store, 'save', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                self.call('paste_groups', book_id=self.book, text=self.clipboard_text())
        self.assertEqual(before, self.app.store.state)

    def test_group_clipboard_limits_empty_groups_and_word_formats(self):
        from vocabulary import parse_group_clipboard, parse_words
        words, _ = parse_words('lucid | /ˈluːsɪd/ | clear | lucid prose')
        self.assertEqual(words[0]['expansion'], 'lucid prose')
        simple, _ = parse_words('lucid: clear\nconcise: brief')
        self.assertEqual([w['sequence'] for w in simple], [1, 2])
        pack = json.loads(self.clipboard_text())
        pack['groups'][0]['words'] = []
        self.assertEqual(parse_group_clipboard(json.dumps(pack))[0]['words'], [])
        for invalid in ['{}', self.clipboard_text(tuple(str(i) for i in range(101))), 'x' * 2_000_001]:
            with self.assertRaises(ValueError):
                parse_group_clipboard(invalid)

    def test_http_api_requires_token_and_prevents_path_traversal(self):
        server,url=make_server(self.app)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base,token=url.split('#')
        base=base.split('?')[0]
        body=json.dumps({'action':'load'}).encode()
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(base+'api',data=body))
        self.assertEqual(error.exception.code,403)
        with urlopen(Request(base+'api',data=body,headers={'Authorization':'Bearer '+token})) as response:
            self.assertIn('state',json.load(response))
        with self.assertRaises(HTTPError):
            urlopen(base+'%2e%2e/desktop_host.py')


class StartupTests(unittest.TestCase):
    def test_missing_webview_gives_setup_instructions_before_touching_data(self):
        with patch.dict(sys.modules, {'webview': None}), \
                patch.object(sys, 'argv', ['desktop_host.py']), \
                patch('desktop_host.Path.exists', return_value=True), \
                patch('desktop_host.Workspace') as workspace, \
                patch('desktop_host.make_server') as server:
            with self.assertRaisesRegex(RuntimeError, 'Launch SAT Study Kit.cmd') as error:
                main()
            self.assertIn(sys.executable, str(error.exception))
            workspace.assert_not_called()
            server.assert_not_called()


if __name__ == '__main__':
    unittest.main()
