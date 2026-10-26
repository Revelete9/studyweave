import assert from "node:assert/strict";
import test from "node:test";
import {
  copyGroups,
  copyWords,
  copyToClipboard,
  isGroupClipboard,
} from "../src/clipboard.ts";

const word = () => ({
  term: "lucid",
  phonetic: "/ˈluːsɪd/",
  meaning: "clear",
  expansion: "lucid prose",
  id: "private-id",
  sequence: 42,
  remembered: 10,
  forgotten: 2,
  streak: 3,
  encounters: 12,
});

test("a copied group is a content snapshot, including all editable properties", () => {
  const original = [{ name: "Clarity", words: [word()] }];
  const pack = copyGroups(original);
  original[0].name = "Renamed";
  original[0].words[0].meaning = "Changed";
  assert.deepEqual(pack, {
    format: "sat-study-kit/groups",
    version: 1,
    groups: [
      {
        name: "Clarity",
        words: [
          {
            term: "lucid",
            phonetic: "/ˈluːsɪd/",
            meaning: "clear",
            expansion: "lucid prose",
          },
        ],
      },
    ],
  });
  assert.equal(isGroupClipboard(JSON.stringify(pack)), true);
});
test("word copy strips progress and numbering, without dropping notes or pronunciation", () => {
  const pack = copyWords([word()]);
  assert.equal(isGroupClipboard(JSON.stringify(pack)), false);
  const text = JSON.stringify(pack);
  for (const hidden of ["private-id", "remembered", "sequence", "encounters"])
    assert.equal(text.includes(hidden), false);
  assert.equal(text.includes("lucid prose"), true);
});
test("in-app copy never writes to the system clipboard", async () => {
  const pack = copyGroups([{ name: "Clarity", words: [word()] }]);
  let stored;
  await copyToClipboard(
    pack,
    "app",
    (value) => {
      stored = value;
    },
    async () => {
      assert.fail("System clipboard must not be touched");
    },
  );
  assert.equal(stored, pack);
});
test("system option writes portable text, leaving in-app data untouched", async () => {
  const pack = copyGroups([{ name: "Clarity", words: [word()] }]);
  let text = "";
  await copyToClipboard(
    pack,
    "system",
    () => {
      assert.fail("Keep the app copy");
    },
    async (value) => {
      text = value;
    },
  );
  assert.deepEqual(JSON.parse(text), pack);
  await assert.rejects(
    copyToClipboard(
      pack,
      "system",
      () => {
        assert.fail();
      },
      async () => {
        throw new Error("Denied");
      },
    ),
    /Denied/,
  );
});
