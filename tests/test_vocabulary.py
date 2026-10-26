import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vocabulary import VocabularyStore, parse_words, make_state

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/vocabulary.json"


class VocabularyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.store = VocabularyStore(self.directory, EXAMPLE)
        self.gid = self.store.state["groups"][0]["id"]

    def test_formats_and_normalization(self):
        inputs = ['[{"word":" concise ","definition":"brief"}]',
                  'word,definition\nconcise,brief', 'concise\tbrief',
                  'concise｜brief', '\ufeffconcise = brief\r\n']
        for text in inputs:
            with self.subTest(text=text):
                words, _ = parse_words(text)
                self.assertEqual(words[0]["term"], "concise")
                self.assertEqual(words[0]["meaning"], "brief")
                self.assertEqual(words[0]["sequence"], 1)

    def test_multiline_quotes_and_order(self):
        words, _ = parse_words('meaning,term,notes\n"brief, clear",concise,"line 1\nline 2"')
        self.assertEqual(words[0]["expansion"], 'line 1\nline 2')
        words, _ = parse_words('1|a||one|\n1|b||two|\n3|c||three|')
        self.assertEqual([w["sequence"] for w in words], [1, 2, 3])

    def test_invalid_input(self):
        for text in ('', '[{}]', '[{"term":"a","meaning":4}]',
                     '[{"term":"a","meaning":"b","image":"x"}]',
                     'term,meaning\na,b,c', 'a=b\na=c',
                     '[{"term":"a","term":"b","meaning":"c"}]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_words(text)

    def test_duplicates_and_limits(self):
        words, notes = parse_words('a=b\na=b')
        self.assertEqual(len(words), 1)
        self.assertTrue(notes)
        for text in ('a=b\n' * 5001, 'a=' + 'b' * 2_000_000):
            with self.assertRaises(ValueError):
                parse_words(text)

    def test_legacy_metadata_and_source_preserved(self):
        catalog = json.loads(EXAMPLE.read_text())
        catalog['categories'][0]['words'][0]['source_ref'] = 'old private metadata'
        raw = json.dumps(catalog)
        source = self.directory / 'vocabulary.json'
        source.write_text(raw)
        store = VocabularyStore(self.directory, EXAMPLE)
        store.name_group('New')
        self.assertEqual(source.read_text(), raw)
        self.assertEqual(store.state['groups'][0]['words'][0]['term'], 'concise')

    def test_groups_create_rename_and_empty_guard(self):
        gid = self.store.name_group(' New ')
        self.store.name_group('Renamed', gid)
        self.assertEqual(self.store.group(gid)['name'], 'Renamed')
        with self.assertRaises(ValueError): self.store.name_group('renamed')
        with self.assertRaises(ValueError): self.store.begin(gid)

    def test_edit_keeps_identity_and_progress(self):
        self.store.begin(self.gid)
        self.store.rate(self.gid, 'forgotten')
        before = copy.deepcopy(self.store.group(self.gid)['words'][0])
        self.store.put_words(self.gid, [{'term':'concise', 'meaning':'short and clear'}], before['id'])
        after = self.store.group(self.gid)['words'][0]
        for key in ('id', 'forgotten', 'encounters', 'streak'):
            self.assertEqual(before[key], after[key])
        self.assertEqual(after['meaning'], 'short and clear')
        self.assertTrue(list((self.directory / 'backups').glob('*/*.json')))

    def test_import_dedup_and_session_append(self):
        self.store.begin(self.gid)
        self.store.rate(self.gid, 'remembered')
        self.assertEqual(self.store.put_words(self.gid, [{'term':'concise','meaning':'replace?'}, {'term':'new','meaning':'fresh'}]), (1, 1))
        self.assertEqual(len(self.store.state['sessions'][self.gid]['queue']), 2)
        self.assertEqual(self.store.state['sessions'][self.gid]['cursor'], 1)
        self.assertEqual(len({w['sequence'] for w in self.store.group(self.gid)['words']}), 2)
        self.assertNotEqual(self.store.group(self.gid)['words'][0]['meaning'], 'replace?')

    def test_resume_repetition_and_restart(self):
        self.store.begin(self.gid)
        for rating in ('forgotten', 'remembered', 'skipped', 'remembered', 'remembered'):
            self.store.rate(self.gid, rating)
        state = self.store.state
        self.assertEqual(state['sessions'][self.gid]['cursor'], 5)
        self.assertEqual(len(state['sessions'][self.gid]['queue']), 5)
        loaded = VocabularyStore(self.directory, EXAMPLE)
        self.assertEqual(loaded.begin(self.gid), state['sessions'][self.gid])
        loaded.begin(self.gid, restart=True)
        self.assertEqual(loaded.state['sessions'][self.gid]['cursor'], 0)
        self.assertEqual(loaded.group(self.gid)['words'][0]['forgotten'], 1)

    def test_failed_save_does_not_change_memory(self):
        before = copy.deepcopy(self.store.state)
        with patch.object(Path, 'replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError): self.store.name_group('Unsaved')
        self.assertEqual(self.store.state, before)

    def test_corrupt_file_not_overwritten(self):
        path = self.directory / 'desktop-vocabulary.json'
        path.write_text('broken')
        with self.assertRaises(ValueError): VocabularyStore(self.directory, EXAMPLE)
        self.assertEqual(path.read_text(), 'broken')

    def test_numbered_plain_words(self):
        words, _ = parse_words('1. concise: brief\n2) obsolete：no longer used')
        self.assertEqual([w['term'] for w in words], ['concise', 'obsolete'])
        with self.assertRaises(ValueError): parse_words('a: b\nmissing separator')

    def test_v1_migration_preserves_progress_with_backup(self):
        self.store.begin(self.gid)
        self.store.rate(self.gid, 'forgotten')
        old = copy.deepcopy(self.store.state)
        old['version'] = 1
        old.pop('books')
        old.pop('book_sessions')
        for group in old['groups']: group.pop('book_id')
        original = json.dumps(old)
        self.store.path.write_text(original)
        loaded = VocabularyStore(self.directory, EXAMPLE)
        self.assertEqual(loaded.state['version'], 2)
        self.assertEqual(loaded.state['sessions'], old['sessions'])
        self.assertEqual(loaded.group(self.gid)['words'], old['groups'][0]['words'])
        self.assertTrue(any(p.read_text() == original for p in (self.directory / 'backups').glob('*/*.json')))

    def test_book_scoped_names_and_atomic_bulk_import(self):
        bid = self.store.name_book('SAT')
        other = self.store.name_book('CET-4')
        words, _ = parse_words('a: first\nb: second')
        gid = self.store.import_group(bid, 'Day 1', words)
        self.store.import_group(other, 'Day 1', words)
        self.assertEqual(self.store.group(gid)['book_id'], bid)
        before = copy.deepcopy(self.store.state)
        with self.assertRaises(ValueError): self.store.import_group(bid, 'Day 1', words)
        with self.assertRaises(ValueError): self.store.import_group(bid, 'bad', [{'term':'x'}])
        self.assertEqual(self.store.state, before)

    def test_book_resume_next_group_and_new_words(self):
        bid = self.store.group(self.gid)['book_id']
        second = self.store.import_group(bid, 'Day 2', [{'term':'next','meaning':'following'}])
        self.store.name_group('Empty', book_id=bid)
        self.assertEqual(self.store.begin_book(bid), self.gid)
        self.store.rate(self.gid, 'remembered')
        self.assertEqual(self.store.begin_book(bid), second)
        loaded = VocabularyStore(self.directory, EXAMPLE)
        self.assertEqual(loaded.begin_book(bid), second)
        loaded.rate(second, 'remembered')
        self.assertIsNone(loaded.begin_book(bid))
        loaded.put_words(self.gid, [{'term':'added','meaning':'new'}])
        self.assertEqual(loaded.begin_book(bid), self.gid)
        self.assertEqual(loaded.state['sessions'][self.gid]['cursor'], 1)

    def test_random_order_stable_across_reload_and_mode_change(self):
        bid = self.store.group(self.gid)['book_id']
        for n in range(4):
            self.store.import_group(bid, f'Group {n}', [{'term':str(i),'meaning':'number'} for i in range(5)])
        current = self.store.begin_book(bid, 'Random')
        before = copy.deepcopy(self.store.state)
        loaded = VocabularyStore(self.directory, EXAMPLE)
        self.assertEqual(loaded.begin_book(bid, 'Random'), current)
        self.assertEqual(loaded.state['book_sessions'], before['book_sessions'])
        self.assertEqual(loaded.state['sessions'], before['sessions'])
        loaded.begin_book(bid, 'Sequential')
        self.assertEqual(loaded.state['book_sessions'][bid]['current'], current)
        self.assertEqual(loaded.state['sessions'], before['sessions'])

    def test_book_restart_preserves_counters(self):
        bid = self.store.group(self.gid)['book_id']
        self.store.begin_book(bid)
        self.store.rate(self.gid, 'remembered')
        self.store.begin_book(bid, restart=True)
        self.assertEqual(self.store.state['sessions'][self.gid]['cursor'], 0)
        self.assertEqual(self.store.group(self.gid)['words'][0]['remembered'], 1)


if __name__ == '__main__':
    unittest.main()
