import copy
import json
import tempfile
import unittest
from pathlib import Path
from question_bank import parse_questions, append_questions, save_bank, read_bank
from simulator import SATReadingSimulator

ROOT = Path(__file__).resolve().parents[1]


class BankTests(unittest.TestCase):
    def setUp(self):
        self.bank = read_bank(ROOT / "examples/questions.json")
        self.q = self.bank["questions"][0]

    def parse(self, value):
        return parse_questions(json.dumps(value), "json")

    def test_only_one_example_and_unknown_answer(self):
        self.assertEqual(len(self.bank["questions"]), 1)
        del self.q["answer"]
        self.assertIsNone(self.parse([self.q])[0]["questions"][0]["answer"])

    def test_csv_quoted_multiline_and_headers(self):
        text = 'Question,A,B,C,D,Answer,Passage\n"Choose, please",yes,no,maybe,never,a,"First line\nSecond line"'
        bank, notes = parse_questions(text, "csv")
        self.assertEqual(bank["questions"][0]["passage"], "First line\nSecond line")
        self.assertEqual(bank["questions"][0]["answer"], "A")
        self.assertTrue(notes)

    def test_tsv(self):
        bank, _ = parse_questions("question\tA\tB\tC\tD\nWhich?\tone\ttwo\tthree\tfour", "auto")
        self.assertEqual(bank["questions"][0]["options"]["B"], "two")

    def test_tagged_multiline(self):
        text = "Passage: First\nSecond\nQuestion: Which?\nA: one\nB: two\nC: three\nD: four\nAnswer: ｂ\n---\nQuestion: Again?\nA: yes\nB: no\nC: maybe\nD: never"
        bank, _ = parse_questions(text)
        self.assertEqual(len(bank["questions"]), 2)
        self.assertEqual(bank["questions"][0]["answer"], "B")
        self.assertEqual(bank["questions"][0]["passage"], "First\nSecond")

    def test_invalid_input_rejected_without_partial_import(self):
        for field, value in (("answer", "Z"), ("module", True), ("module", 3), ("question", ""), ("figure", "x.png")):
            item = {**self.q, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.parse([self.q, item])
        bad = copy.deepcopy(self.q)
        bad["options"]["D"] = ""
        with self.assertRaises(ValueError): self.parse([bad])

    def test_bad_json_and_table_columns(self):
        for text in ('{"questions":[],"questions":[]}', '[NaN]', 'question,A,B,C,D\n"unfinished,yes,no,a,b', 'question,A,B,C,D\nWhich?,yes,no,a,b,extra'):
            with self.subTest(text=text), self.assertRaises((ValueError, __import__('csv').Error)):
                parse_questions(text)

    def test_exact_duplicate_and_conflicting_ids(self):
        other = {**self.q, "question": "A different question?"}
        bank, notes = self.parse([self.q, copy.deepcopy(self.q), other])
        self.assertEqual(len(bank["questions"]), 2)
        self.assertEqual(len({q["id"] for q in bank["questions"]}), 2)
        self.assertTrue(any("duplicate" in n for n in notes))

    def test_append_is_deduplicated_and_keeps_original(self):
        before = copy.deepcopy(self.bank)
        bank, _ = append_questions(self.bank, self.bank)
        self.assertEqual(len(bank["questions"]), 1)
        self.assertEqual(self.bank, before)

    def test_save_backup_and_path_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "banks"
            path = save_bank(self.bank, directory)
            before = path.read_bytes()
            self.bank["title"] = "Changed"
            save_bank(self.bank, directory, path)
            backups = list((Path(temp) / "backups").glob("*/*.json"))
            self.assertEqual(backups[0].read_bytes(), before)
            self.assertEqual(read_bank(path)["title"], "Changed")
            with self.assertRaises(ValueError): save_bank(self.bank, directory, Path(temp) / "outside.json")

    def test_empty_bank_and_multiple_banks_discovered(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            save_bank({"schema_version": 1, "title": "Empty", "questions": []}, data / "banks")
            save_bank(self.bank, data / "banks")
            app = SATReadingSimulator.__new__(SATReadingSimulator)
            app.data_dir = data
            choices = app.discover_banks()
            self.assertEqual(len(choices), 3)  # Two local banks and the bundled example.
            empty = next(path for label, path in choices if "Empty" in label)
            with self.assertRaises(ValueError): app.load_bank(empty)
            app.load_bank(ROOT / "examples/questions.json")
            self.assertEqual(len(app.modules), 1)

    def test_two_modules_and_module_two_only_guard(self):
        second = {**self.q, "id": "second", "module": 2}
        with tempfile.TemporaryDirectory() as temp:
            path = save_bank({**self.bank, "questions": [self.q, second]}, Path(temp))
            app = SATReadingSimulator.__new__(SATReadingSimulator)
            app.load_bank(path)
            self.assertEqual(len(app.modules), 2)
            path = save_bank({**self.bank, "questions": [second]}, Path(temp))
            with self.assertRaises(ValueError): app.load_bank(path)

    def test_legacy_bank_is_read_without_mutation(self):
        old = {"schema_version": 3, "title": "Legacy", "modules": [{"id": 1, "questions": [{**self.q, "answer_source": "provided", "source_ref": "notes", "available": True, "needs_review": []}]}]}
        bank, notes = self.parse(old)
        self.assertEqual(bank["questions"], self.bank["questions"])
        self.assertTrue(notes)

    def test_limits(self):
        with self.assertRaises(ValueError): parse_questions("x" * 2_000_001)
        with self.assertRaises(ValueError): self.parse([self.q] * 201)


if __name__ == "__main__": unittest.main()
