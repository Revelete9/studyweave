export type ReviewResult = "remembered" | "forgotten" | "skipped";

export type QueueWordProgress = {
  id: string;
  remembered: number;
  forgotten: number;
  streak: number;
  encounters?: number;
  lastSeen?: string;
};

type QueueBaseline = {
  remembered: number;
  forgotten: number;
  streak: number;
  encounters: number;
  lastSeen?: string;
};

export type ReviewQueueEntry = {
  id: string;
  wordId: string;
  result: ReviewResult | null;
  answeredAt?: string;
  repeatOf?: string;
  baseline: QueueBaseline;
};

export type QueueWordSummary = QueueBaseline;

export type QueueSessionSummary = {
  remembered: number;
  forgotten: number;
  skipped: number;
};

function defaultEntryId() {
  return `queue-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function createReviewQueue(
  words: QueueWordProgress[],
  idFactory: () => string = defaultEntryId,
): ReviewQueueEntry[] {
  return words.map((word) => ({
    id: idFactory(),
    wordId: word.id,
    result: null,
    baseline: {
      remembered: word.remembered,
      forgotten: word.forgotten,
      streak: word.streak,
      encounters: word.encounters ?? word.remembered + word.forgotten,
      lastSeen: word.lastSeen,
    },
  }));
}

export function answerQueueEntry(
  queue: ReviewQueueEntry[],
  cursor: number,
  result: ReviewResult,
  answeredAt: string,
  idFactory: () => string = defaultEntryId,
): ReviewQueueEntry[] {
  const previous = queue[cursor];
  if (!previous) return queue;

  const nextQueue = queue.map((entry, index) => index === cursor
    ? { ...entry, result, answeredAt }
    : entry);

  // Rebuild only unvisited automatic repeats. Answered positions retain their identity.
  for (let index = nextQueue.length - 1; index > cursor; index--) {
    const entry = nextQueue[index];
    if (entry.wordId === previous.wordId && entry.repeatOf && entry.result === null) nextQueue.splice(index, 1);
  }
  const learning = queueLearningProgress(nextQueue, previous.wordId);
  if (learning.needsReview && !nextQueue.slice(cursor + 1).some((entry) => entry.wordId === previous.wordId && entry.result === null)) {
    const lastAnswered = nextQueue.reduce((last, entry, index) => entry.wordId === previous.wordId && entry.result !== null ? index : last, cursor);
    const repeatAt = Math.min(Math.max(cursor, lastAnswered) + reviewSpacing(learning.streak), nextQueue.length);
    nextQueue.splice(repeatAt, 0, {
      ...previous,
      id: idFactory(),
      result: null,
      answeredAt: undefined,
      repeatOf: previous.id,
    });
  }

  return nextQueue;
}

// Three successful retrievals at distinct positions, with 3 / 8 / 20 intervening
// cards when the queue is long enough. Skips do not discharge the review debt.
export function reviewSpacing(streak: number) {
  return streak <= 0 ? 4 : streak === 1 ? 9 : 21;
}

export function queueLearningProgress(queue: ReviewQueueEntry[], wordId: string) {
  const first = queue.find((entry) => entry.wordId === wordId);
  let forgotten = first?.baseline.forgotten ?? 0;
  let streak = first?.baseline.streak ?? 0;
  for (const entry of queue) {
    if (entry.wordId !== wordId) continue;
    if (entry.result === "forgotten") { forgotten++; streak = 0; }
    if (entry.result === "remembered") streak++;
  }
  return { forgotten, streak, needsReview: forgotten > 0 && streak < 3 };
}

export function summarizeQueueWord(queue: ReviewQueueEntry[], wordId: string): QueueWordSummary | null {
  const first = queue.find((entry) => entry.wordId === wordId);
  if (!first) return null;

  const summary: QueueWordSummary = { ...first.baseline };
  for (const entry of queue) {
    if (entry.wordId !== wordId || entry.result === null) continue;

    summary.encounters++;
    if (entry.result === "remembered") {
      summary.remembered++;
      summary.streak++;
    } else if (entry.result === "forgotten") {
      summary.forgotten++;
      summary.streak = 0;
    }

    if (entry.answeredAt && (!summary.lastSeen || entry.answeredAt > summary.lastSeen)) {
      summary.lastSeen = entry.answeredAt;
    }
  }

  return summary;
}

export function summarizeQueueSession(queue: ReviewQueueEntry[]): QueueSessionSummary {
  const summary: QueueSessionSummary = { remembered: 0, forgotten: 0, skipped: 0 };
  for (const entry of queue) {
    if (entry.result !== null) summary[entry.result]++;
  }
  return summary;
}

// Queue snapshots let a round resume without counting an answer twice.

export type ReviewSession = {
  version: 1;
  queue: ReviewQueueEntry[];
  cursor: number;
  roundDone: boolean;
};

type HistoryItem = { groupId: string; wordId: string; at: string };

export function captureReviewSession(queue: ReviewQueueEntry[], cursor: number, roundDone: boolean): ReviewSession {
  return { version: 1, queue, cursor, roundDone };
}

function validEntry(value: unknown): value is ReviewQueueEntry {
  if (!value || typeof value !== "object") return false;
  const entry = value as ReviewQueueEntry;
  return typeof entry.id === "string" && typeof entry.wordId === "string"
    && [null, "remembered", "forgotten", "skipped"].includes(entry.result)
    && !!entry.baseline && [entry.baseline.remembered, entry.baseline.forgotten, entry.baseline.encounters, entry.baseline.streak]
      .every((count) => Number.isInteger(count) && count >= 0);
}

export function restoreReviewSession(
  words: QueueWordProgress[], saved: unknown, history: HistoryItem[] = [], groupId = "",
): ReviewSession & { approximate: boolean } {
  const snapshot = saved as Partial<ReviewSession> | undefined;
  if (snapshot?.version === 1 && Array.isArray(snapshot.queue) && snapshot.queue.every(validEntry)
    && new Set(snapshot.queue.map((entry) => entry.id)).size === snapshot.queue.length
    && Number.isInteger(snapshot.cursor) && snapshot.cursor! >= 0
    && snapshot.cursor! <= Math.max(0, snapshot.queue.length - 1) && typeof snapshot.roundDone === "boolean") {
    const allowed = new Set(words.map((word) => word.id));
    const before = snapshot.queue.slice(0, snapshot.cursor).filter((entry) => allowed.has(entry.wordId)).length;
    const queue = snapshot.queue.filter((entry) => allowed.has(entry.wordId));
    const present = new Set(queue.map((entry) => entry.wordId));
    const additions = createReviewQueue(words.filter((word) => !present.has(word.id)));
    const wasDone = snapshot.roundDone;
    const cursor = wasDone && additions.length ? queue.length : Math.min(before, Math.max(0, queue.length - 1));
    return { ...captureReviewSession([...queue, ...additions], cursor, wasDone && additions.length === 0), approximate: false };
  }

  // Older releases saved totals/history but no queue. Resume approximately after
  // the most recently answered word; do not replay that answer into its totals.
  const queue = createReviewQueue(words);
  const latest = history.filter((item) => item.groupId === groupId && words.some((word) => word.id === item.wordId))
    .sort((a, b) => b.at.localeCompare(a.at))[0]
    ?? words.filter((word) => !!word.lastSeen).map((word) => ({ wordId: word.id, at: word.lastSeen! }))
      .sort((a, b) => b.at.localeCompare(a.at))[0];
  const previousIndex = latest ? words.findIndex((word) => word.id === latest.wordId) : -1;
  const cursor = previousIndex < 0 ? 0 : Math.min(previousIndex + 1, Math.max(0, queue.length - 1));
  // Unfinished weak words before the recovered cursor still need practice.
  const debt = words.slice(0, cursor).filter((word) => word.forgotten > 0 && word.streak < 3);
  queue.push(...createReviewQueue(debt).map((entry) => ({ ...entry, repeatOf: "legacy-recovery" })));
  return { ...captureReviewSession(queue, cursor, false), approximate: !!latest };
}
