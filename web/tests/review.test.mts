import assert from "node:assert/strict";
import test from "node:test";
import {
  answerQueueEntry, createReviewQueue, summarizeQueueSession, summarizeQueueWord,
  captureReviewSession, restoreReviewSession,
} from "../src/review.ts";

function ids() {
  let value = 0;
  return () => `entry-${++value}`;
}

const words = ["alpha", "beta", "gamma"].map((id) => ({
  id,
  remembered: 0,
  forgotten: 0,
  streak: 0,
  encounters: 0,
}));

test("only the final answer at one queue position is counted", () => {
  const nextId = ids();
  let queue = createReviewQueue(words, nextId);

  queue = answerQueueEntry(queue, 0, "forgotten", "2026-08-08T10:00:00.000Z", nextId);
  assert.equal(queue.length, 4);
  assert.deepEqual(summarizeQueueWord(queue, "alpha"), {
    remembered: 0,
    forgotten: 1,
    streak: 0,
    encounters: 1,
    lastSeen: "2026-08-08T10:00:00.000Z",
  });

  queue = answerQueueEntry(queue, 0, "remembered", "2026-08-08T10:01:00.000Z", nextId);
  assert.equal(queue.length, 3, "the unvisited repeat created by the discarded answer is removed");
  assert.deepEqual(summarizeQueueWord(queue, "alpha"), {
    remembered: 1,
    forgotten: 0,
    streak: 1,
    encounters: 1,
    lastSeen: "2026-08-08T10:01:00.000Z",
  });
  assert.deepEqual(summarizeQueueSession(queue), { remembered: 1, forgotten: 0, skipped: 0 });

  queue = answerQueueEntry(queue, 0, "remembered", "2026-08-08T10:02:00.000Z", nextId);
  assert.equal(summarizeQueueWord(queue, "alpha")?.encounters, 1);

  queue = answerQueueEntry(queue, 0, "skipped", "2026-08-08T10:03:00.000Z", nextId);
  assert.deepEqual(summarizeQueueWord(queue, "alpha"), {
    remembered: 0,
    forgotten: 0,
    streak: 0,
    encounters: 1,
    lastSeen: "2026-08-08T10:03:00.000Z",
  });
});

test("an already visited repeat remains a distinct queue position", () => {
  const nextId = ids();
  let queue = createReviewQueue(words, nextId);
  queue = answerQueueEntry(queue, 0, "forgotten", "2026-08-08T10:00:00.000Z", nextId);
  queue = answerQueueEntry(queue, 3, "remembered", "2026-08-08T10:01:00.000Z", nextId);
  queue = answerQueueEntry(queue, 0, "remembered", "2026-08-08T10:02:00.000Z", nextId);

  assert.equal(queue.length, 4);
  assert.deepEqual(summarizeQueueWord(queue, "alpha"), {
    remembered: 2,
    forgotten: 0,
    streak: 2,
    encounters: 2,
    lastSeen: "2026-08-08T10:02:00.000Z",
  });
});

test("historical mistakes require three distinct correct retrievals and keep totals", () => {
  const nextId = ids();
  let queue = createReviewQueue([{ ...words[0], forgotten: 9, encounters: 9 }], nextId);
  for (let cursor = 0; cursor < 3; cursor++) {
    queue = answerQueueEntry(queue, cursor, "remembered", `2026-09-10T10:0${cursor}:00.000Z`, nextId);
    assert.equal(queue.length, Math.min(cursor + 2, 3));
    assert.equal(summarizeQueueWord(queue, "alpha")?.streak, cursor + 1);
  }
  assert.equal(summarizeQueueWord(queue, "alpha")?.forgotten, 9);
  assert.equal(summarizeQueueWord(queue, "alpha")?.encounters, 12);
});

test("re-grading the same position cannot satisfy the three-correct rule", () => {
  const nextId = ids();
  let queue = createReviewQueue([{ ...words[0], forgotten: 5, encounters: 5 }], nextId);
  for (let count = 0; count < 8; count++) queue = answerQueueEntry(queue, 0, "remembered", "2026-09-10T10:00:00Z", nextId);
  assert.equal(queue.length, 2);
  assert.equal(summarizeQueueWord(queue, "alpha")?.streak, 1);
  queue = answerQueueEntry(queue, 1, "forgotten", "2026-09-10T10:01:00Z", nextId);
  assert.equal(summarizeQueueWord(queue, "alpha")?.streak, 0);
  queue = answerQueueEntry(queue, 2, "skipped", "2026-09-10T10:02:00Z", nextId);
  assert.equal(queue.length, 4, "skip defers, it does not forgive a mistake");
});

test("successful retrievals are increasingly spaced in a sufficiently long queue", () => {
  const nextId = ids();
  let queue = createReviewQueue(Array.from({ length: 50 }, (_, i) => ({ ...words[0], id: `word-${i}` })), nextId);
  queue = answerQueueEntry(queue, 0, "forgotten", "2026-09-10T10:00:00Z", nextId);
  assert.equal(queue[4].wordId, "word-0");
  queue = answerQueueEntry(queue, 4, "remembered", "2026-09-10T10:01:00Z", nextId);
  assert.equal(queue[13].wordId, "word-0");
  queue = answerQueueEntry(queue, 13, "remembered", "2026-09-10T10:02:00Z", nextId);
  assert.equal(queue[34].wordId, "word-0");
});

test("a saved latest streak also drives the visible word summary", () => {
  let queue = createReviewQueue([{ ...words[0], forgotten: 8, streak: 2 }]);
  queue = answerQueueEntry(queue, 0, "remembered", "2026-09-10T10:00:00Z");
  assert.equal(queue.length, 1);
  assert.equal(summarizeQueueWord(queue, "alpha")?.streak, 3);
  assert.equal(summarizeQueueWord(queue, "alpha")?.remembered, 1);
});

const sessionWords = ["a", "b", "c"].map((id) => ({ id, remembered: 0, forgotten: 0, encounters: 0, streak: 0 }));

test("reload and category round-trip retain exact entries, cursor, and correction semantics", () => {
  const queue = answerQueueEntry(createReviewQueue(sessionWords), 0, "forgotten", "2026-09-10T10:00:00Z");
  const persisted = JSON.parse(JSON.stringify({ one: captureReviewSession(queue, 1, false), two: captureReviewSession(createReviewQueue(sessionWords), 2, false) }));
  const restored = restoreReviewSession(sessionWords, persisted.one);
  assert.deepEqual(restored.queue, JSON.parse(JSON.stringify(queue)));
  assert.equal(restored.cursor, 1);
  assert.equal(restoreReviewSession(sessionWords, persisted.two).cursor, 2);
  const revised = answerQueueEntry(restored.queue, 0, "remembered", "2026-09-10T10:01:00Z");
  assert.equal(summarizeQueueWord(revised, "a")?.encounters, 1);
  assert.equal(summarizeQueueWord(revised, "a")?.forgotten, 0);
});

test("completed rounds stay complete and catalog additions resume at new words", () => {
  const saved = captureReviewSession(createReviewQueue(sessionWords), 2, true);
  assert.equal(restoreReviewSession(sessionWords, saved).roundDone, true);
  const restored = restoreReviewSession([...sessionWords, { ...sessionWords[0], id: "d" }], saved);
  assert.equal(restored.roundDone, false);
  assert.equal(restored.queue[restored.cursor].wordId, "d");
});

test("deleting earlier words preserves the current entry and leaves totals untouched", () => {
  const saved = captureReviewSession(createReviewQueue(sessionWords), 2, false);
  const restored = restoreReviewSession(sessionWords.slice(1), saved);
  assert.equal(restored.cursor, 1);
  assert.equal(restored.queue[restored.cursor].id, saved.queue[2].id);
});

test("legacy migration uses local history and carries earlier unresolved mistakes", () => {
  const legacyWords = sessionWords.map((word, i) => ({ ...word, forgotten: i === 0 ? 7 : 0, encounters: i === 0 ? 7 : 0 }));
  const restored = restoreReviewSession(legacyWords, undefined, [
    { groupId: "one", wordId: "b", at: "2026-09-10T10:00:00Z" },
    { groupId: "another-group", wordId: "a", at: "2026-09-10T10:01:00Z" },
  ], "one");
  assert.equal(restored.approximate, true);
  assert.equal(restored.queue[restored.cursor].wordId, "c");
  assert.equal(restored.queue.at(-1)?.wordId, "a");
  assert.equal(summarizeQueueWord(restored.queue, "a")?.forgotten, 7);
});

test("malformed queue snapshots fall back without changing saved word totals", () => {
  const saved = { version: 1, cursor: 50, roundDone: false, queue: [{ id: "bad", baseline: null }] };
  const restored = restoreReviewSession(sessionWords, saved);
  assert.equal(restored.cursor, 0);
  assert.equal(restored.queue.length, 3);
});
