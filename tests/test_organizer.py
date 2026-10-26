import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from organizer import Organizer
from vocabulary import VocabularyStore


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = VocabularyStore(Path(self.temp.name), Path(__file__).resolve().parents[1] / 'examples/vocabulary.json')
        self.src = self.store.state['groups'][0]['id']
        self.book = self.store.group(self.src)['book_id']
        self.other = self.store.name_book('Destination')
        self.dst = self.store.import_group(self.other, 'New group', [{'term':'other', 'meaning':'different'}])
        self.wid = self.store.group(self.src)['words'][0]['id']

    def test_move_word_preserves_records_and_reconciles_queues(self):
        self.store.begin(self.src)
        self.store.rate(self.src, 'forgotten')
        self.store.begin(self.dst)
        before = copy.deepcopy(self.store.group(self.src)['words'][0])
        self.store.transfer('word', self.src, self.dst, [self.wid])
        self.assertEqual(self.store.group(self.src)['words'], [])
        self.assertEqual(self.store.state['sessions'][self.src], {'queue': [], 'cursor': 0})
        moved = self.store.group(self.dst)['words'][-1]
        for key in ('id', 'remembered', 'forgotten', 'streak', 'encounters', 'lastSeen'):
            self.assertEqual(moved[key], before[key])
        self.assertEqual(self.store.state['sessions'][self.dst]['queue'][-1], self.wid)
        self.store.validate(self.store.state)

    def test_move_group_preserves_session_and_repairs_book_plans(self):
        self.store.begin_book(self.book)
        self.store.begin_book(self.other)
        self.store.rate(self.src, 'forgotten')
        session = copy.deepcopy(self.store.state['sessions'][self.src])
        self.store.transfer('group', self.book, self.other, [self.src])
        self.assertEqual(self.store.group(self.src)['book_id'], self.other)
        self.assertEqual(self.store.state['sessions'][self.src], session)
        self.assertNotIn(self.src, self.store.state['book_sessions'][self.book]['order'])
        self.assertIsNone(self.store.state['book_sessions'][self.book]['current'])
        self.assertIn(self.src, self.store.state['book_sessions'][self.other]['order'])

    def test_copy_words_and_groups_start_fresh(self):
        self.store.begin(self.src)
        self.store.rate(self.src, 'forgotten')
        self.store.transfer('word', self.src, self.dst, [self.wid], True)
        clone = self.store.group(self.dst)['words'][-1]
        self.assertNotEqual(clone['id'], self.wid)
        self.assertEqual(clone['forgotten'], 0)
        self.assertNotIn('lastSeen', clone)
        self.assertEqual(self.store.group(self.src)['words'][0]['forgotten'], 1)
        self.store.transfer('group', self.book, self.other, [self.src], True)
        clone_group = self.store.state['groups'][-1]
        self.assertNotEqual(clone_group['id'], self.src)
        self.assertNotEqual(clone_group['words'][0]['id'], self.wid)
        self.assertNotIn(clone_group['id'], self.store.state['sessions'])

    def test_conflicting_batch_is_rejected_without_partial_move(self):
        self.store.put_words(self.src, [{'term':'other', 'meaning':'a conflict'}])
        before = copy.deepcopy(self.store.state)
        with self.assertRaises(ValueError):
            self.store.transfer('word', self.src, self.dst, [w['id'] for w in self.store.group(self.src)['words']])
        self.assertEqual(self.store.state, before)
        self.store.name_group(self.store.group(self.src)['name'], book_id=self.other)
        before = copy.deepcopy(self.store.state)
        with self.assertRaises(ValueError): self.store.transfer('group', self.book, self.other, [self.src])
        self.assertEqual(self.store.state, before)

    def test_same_destination_stale_ids_and_disk_error(self):
        before = copy.deepcopy(self.store.state)
        for args in [('word', self.src, self.src, [self.wid]), ('word', self.src, self.dst, ['missing']),
                     ('group', self.book, self.other, ['missing']), ('word', self.src, 'missing', [self.wid])]:
            with self.assertRaises(ValueError): self.store.transfer(*args)
        with patch.object(Path, 'replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError): self.store.transfer('word', self.src, self.dst, [self.wid])
        self.assertEqual(self.store.state, before)

    def test_undo_restores_exact_state_and_rejects_stale_undo(self):
        organizer = Organizer.__new__(Organizer)
        organizer.store = self.store
        organizer.notify = MagicMock()
        organizer.undo_button = MagicMock()
        organizer.refresh = MagicMock()
        organizer.undo_before = copy.deepcopy(self.store.state)
        self.store.transfer('word', self.src, self.dst, [self.wid])
        organizer.undo_after = copy.deepcopy(self.store.state)
        expected = copy.deepcopy(organizer.undo_before)
        organizer.undo()
        self.assertEqual(self.store.state, expected)
        organizer.undo_before = expected
        organizer.undo_after = copy.deepcopy(self.store.state)
        self.store.name_book('New change')
        after = copy.deepcopy(self.store.state)
        organizer.undo()
        self.assertEqual(self.store.state, after)

    def test_partial_queue_cursor_keeps_only_surviving_history(self):
        self.store.put_words(self.src, [{'term':'stay', 'meaning':'remain'}])
        stay = self.store.group(self.src)['words'][1]['id']
        self.store.begin(self.src)
        self.store.rate(self.src, 'forgotten')
        self.store.rate(self.src, 'remembered')
        self.store.transfer('word', self.src, self.dst, [self.wid])
        self.assertEqual(self.store.state['sessions'][self.src], {'queue':[stay], 'cursor':1})
        self.assertEqual(self.store.group_status(self.src), 'Complete')


if __name__ == '__main__':
    unittest.main()
