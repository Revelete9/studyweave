import assert from "node:assert/strict";
import test from "node:test";
import {
  mergeCatalogWithSavedGroups, encountersFor, errorRateFor, statusFor, STORAGE_KEY,
  type CatalogMergeWord, type CatalogMergeGroup,
} from "../src/library.ts";

test("StudyWeave keeps the existing browser storage namespace", () => {
  assert.equal(STORAGE_KEY, "sat-study-kit.web.v1");
});

function word(sequence: number, term: string): CatalogMergeWord {
  return {
    id: `sat-${sequence}`,
    sequence,
    term,
    phonetic: "",
    meaning: `new ${term}`,
    expansion: "",
    remembered: 0,
    forgotten: 0,
    streak: 0,
    encounters: 0,
  };
}

test("catalog upgrades add and regroup built-in words while preserving progress and custom content", () => {
  const catalog: CatalogMergeGroup[] = [
    { id: "group-a", name: "A new", description: "", accent: "#111", words: [word(1, "one")] },
    { id: "group-b", name: "B new", description: "", accent: "#222", words: [word(2, "two"), word(3, "three")] },
  ];
  const saved: CatalogMergeGroup[] = [
    {
      id: "group-a",
      name: "A old",
      description: "",
      accent: "#999",
      words: [
        { ...word(1, "edited one"), meaning: "old meaning", remembered: 4, forgotten: 2, streak: 3, encounters: 7 },
        { ...word(2, "two"), remembered: 1, forgotten: 1, streak: 0, encounters: 2 },
        { ...word(99, "removed from catalog"), remembered: 5 },
        { ...word(100, "custom"), id: "word-custom", sequence: undefined, remembered: 2 },
      ],
    },
    { id: "group-custom", name: "My group", description: "", accent: "#333", words: [] },
  ];

  const merged = mergeCatalogWithSavedGroups(catalog, saved);
  assert.deepEqual(merged.map((group) => group.id), ["group-a", "group-b", "group-custom"]);
  assert.equal(merged[0].name, "A new");
  assert.deepEqual(merged[0].words.map((item) => item.id), ["sat-1", "word-custom"]);
  assert.equal(merged[0].words[0].term, "one");
  assert.equal(merged[0].words[0].meaning, "new one");
  assert.equal(merged[0].words[0].remembered, 4);
  assert.equal(merged[0].words[0].forgotten, 2);
  assert.equal(merged[0].words[0].encounters, 7);
  assert.equal(merged[1].words[0].id, "sat-2");
  assert.equal(merged[1].words[0].remembered, 1);
  assert.equal(merged[1].words[1].id, "sat-3");
  assert.equal(merged[1].words[1].remembered, 0);
});

test('moving options to one category preserves progress and removes retired copies', () => {
  const makeGroup = (id: string, words: CatalogMergeWord[]): CatalogMergeGroup =>
    ({ id, name: id, description: '', accent: '#111', words });
  const customWord = { ...word(9, 'custom'), id: 'word-custom' };
  const saved = [
    makeGroup('retired', [{ ...word(1, 'one'), remembered: 7 }, customWord]),
    makeGroup('retired-empty', [word(2, 'two')]),
  ];
  const merged = mergeCatalogWithSavedGroups(
    [makeGroup('sat-question-options', [word(1, 'one'), word(2, 'two')])],
    saved, ['retired', 'retired-empty'],
  );
  assert.equal(merged[0].words[0].remembered, 7);
  assert.deepEqual(merged.flatMap(g => g.words).map(w => w.id), ['sat-1', 'sat-2', 'word-custom']);
  assert.deepEqual(saved[0].words.map(w => w.id), ['sat-1', 'word-custom']);
});

test("local counters determine status, error rate, and encounters", () => {
  const item = { ...word(1, "one"), remembered: 3, forgotten: 1, streak: 3, encounters: 5 };
  assert.equal(statusFor(item).label, "Mastered");
  assert.equal(errorRateFor(item), 0.25);
  assert.equal(encountersFor(item), 5);
  assert.equal(encountersFor({ ...item, encounters: undefined }), 4);
  assert.equal(statusFor(word(2, "two")).label, "New");
});
