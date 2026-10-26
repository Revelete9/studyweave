import type { CSSProperties, FormEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { parseWords, type WordFormat } from "./import";
import exampleCatalog from "../../examples/vocabulary.json";
import {
  type Word,
  type SortKey,
  type SortDirection,
  type WordGroup,
  type VocabularyCatalog,
  type ReviewEvent,
  type SessionStats,
  STORAGE_KEY,
  ACCENTS,
  SORT_OPTIONS,
  DEFAULT_GROUPS,
  emptySession,
  makeId,
  masteryFor,
  statusFor,
  encountersFor,
  errorRateFor,
  sortMetric,
  sameDay,
  groupsFromCatalog,
  mergeCatalogWithSavedGroups,
} from "./library";
import {
  answerQueueEntry, createReviewQueue, queueLearningProgress,
  summarizeQueueSession, summarizeQueueWord, captureReviewSession, restoreReviewSession,
  type ReviewQueueEntry, type ReviewResult, type ReviewSession,
} from "./review";

export default function App() {
  const storageKey = useRef(`${STORAGE_KEY}:example`);
  const importFile = useRef<HTMLInputElement>(null);
  const [groups, setGroups] = useState<WordGroup[]>(DEFAULT_GROUPS);
  const [reviews, setReviews] = useState<ReviewEvent[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState(DEFAULT_GROUPS[0].id);
  const [mode, setMode] = useState<"study" | "library">("study");
  const [queue, setQueue] = useState<ReviewQueueEntry[]>(() => createReviewQueue(DEFAULT_GROUPS[0].words));
  const [cursor, setCursor] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [roundDone, setRoundDone] = useState(false);
  const [session, setSession] = useState<SessionStats>(emptySession);
  const [ready, setReady] = useState(false);
  const [batchText, setBatchText] = useState("");
  const [importFormat, setImportFormat] = useState<WordFormat>("auto");
  const [importPreview, setImportPreview] = useState<ReturnType<typeof parseWords> | null>(null);
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupDescription, setNewGroupDescription] = useState("");
  const [notice, setNotice] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState({ sequence: "", term: "", phonetic: "", meaning: "", expansion: "" });
  const [libraryQuery, setLibraryQuery] = useState("");
  const [libraryStatus, setLibraryStatus] = useState<"all" | "new" | "learning" | "mastered">("all");
  const [librarySort, setLibrarySort] = useState<{ key: SortKey; direction: SortDirection }>({
    key: "source",
    direction: "asc",
  });
  const [catalogVersion, setCatalogVersion] = useState<string>();
  const reviewSessions = useRef<Record<string, ReviewSession>>({});
  const storageWritable = useRef(false);

  useEffect(() => {
    let cancelled = false;
    async function hydrate() {
      try {
        let initialGroups = DEFAULT_GROUPS;
        let initialReviews: ReviewEvent[] = [];
        let requestedGroup: string | undefined;
        let loadedCatalogVersion: string | undefined;
        let retiredCategoryIds: string[] = [];
        let savedCatalogVersion: string | undefined;
        {
          const catalogResponse = await fetch("/vocabulary.json", { cache: "no-store" });
          const catalog = (catalogResponse.ok && catalogResponse.headers.get("content-type")?.includes("json")
            ? await catalogResponse.json() : exampleCatalog) as VocabularyCatalog;
          if (Array.isArray(catalog.categories) && catalog.categories.length) {
            initialGroups = groupsFromCatalog(catalog);
            loadedCatalogVersion = catalog.version;
            storageKey.current = `${STORAGE_KEY}:${catalog.pack_id ?? "example"}`;
            retiredCategoryIds = catalog.retiredCategoryIds ?? [];
          }
        }

        const saved = window.localStorage.getItem(storageKey.current);
        if (saved) {
          const parsed = JSON.parse(saved) as {
            groups?: WordGroup[];
            reviews?: ReviewEvent[];
            selectedGroupId?: string;
            catalogVersion?: string;
            progressSchema?: number;
            reviewSessions?: Record<string, ReviewSession>;
          };
          // Preserve the exact old payload before the first upgraded write.
          const backupKey = `${storageKey.current}-backup-before-queue-v3`;
          if (parsed.progressSchema !== 3 && !window.localStorage.getItem(backupKey)) {
            window.localStorage.setItem(backupKey, saved);
          }
          reviewSessions.current = parsed.reviewSessions && typeof parsed.reviewSessions === "object"
            ? parsed.reviewSessions : {};
          requestedGroup = parsed.selectedGroupId;
          savedCatalogVersion = parsed.catalogVersion;
          if (Array.isArray(parsed.groups) && parsed.groups.length) {
            const savedGroups = parsed.groups.map((group) => ({
              ...group,
              description: group.description === "User-reviewed AI-assisted import" ? "Imported vocabulary" : group.description,
              words: group.words.map((word, index) => ({
                ...word,
                sequence: word.sequence ?? index + 1,
                expansion: word.expansion ?? word.example ?? "",
                encounters: word.encounters ?? word.remembered + word.forgotten,
              })),
            }));
            initialGroups = loadedCatalogVersion && parsed.catalogVersion !== loadedCatalogVersion
              ? mergeCatalogWithSavedGroups(initialGroups, savedGroups, retiredCategoryIds)
              : savedGroups;
          }
          if (Array.isArray(parsed.reviews)) initialReviews = parsed.reviews;
        }

        if (cancelled) return;
        const activeGroup = initialGroups.find((group) => group.id === requestedGroup) ?? initialGroups[0];
        setGroups(initialGroups);
        setReviews(initialReviews);
        setSelectedGroupId(activeGroup.id);
        const restored = restoreReviewSession(activeGroup.words, reviewSessions.current[activeGroup.id], initialReviews, activeGroup.id);
        setQueue(restored.queue);
        setCursor(restored.cursor);
        setRoundDone(restored.roundDone);
        setSession(summarizeQueueSession(restored.queue));
        if (restored.approximate) setNotice("Your totals were preserved. The last review position was estimated because the old version did not save the full queue.");
        setCatalogVersion(loadedCatalogVersion ?? savedCatalogVersion);
        storageWritable.current = true;
      } catch {
        if (!cancelled) {
          storageWritable.current = false;
          setNotice("Could not load the library or saved progress. Saving is paused. Export your existing data before retrying.");
        }
      } finally {
        if (!cancelled) setReady(true);
      }
    }

    void hydrate();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!ready || !storageWritable.current) return;
    reviewSessions.current[selectedGroupId] = captureReviewSession(queue, cursor, roundDone);
    const save = () => {
      try {
        window.localStorage.setItem(storageKey.current, JSON.stringify({
        progressSchema: 3,
        reviewSessions: reviewSessions.current,
        catalogVersion,
        groups,
        reviews: reviews.slice(-2000),
        selectedGroupId,
        }));
      } catch {
        setNotice("Saving failed, possibly because browser storage is full. Existing progress was not cleared. Export a backup before closing this page.");
      }
    };
    save();
    window.addEventListener("pagehide", save);
    return () => window.removeEventListener("pagehide", save);
  }, [catalogVersion, groups, ready, reviews, selectedGroupId, queue, cursor, roundDone]);

  const selectedGroup = useMemo(
    () => groups.find((group) => group.id === selectedGroupId) ?? groups[0],
    [groups, selectedGroupId],
  );

  const currentWord = selectedGroup?.words.find((word) => word.id === queue[cursor]?.wordId);
  const currentLearning = currentWord ? queueLearningProgress(queue, currentWord.id) : null;
  const currentExpansion = currentWord?.expansion || currentWord?.example || "";
  const relatedWords = useMemo(() => {
    if (!selectedGroup || !currentWord) return [];
    const peers = selectedGroup.words.filter((word) => word.id !== currentWord.id);
    if (peers.length <= 3) return peers;
    const start = cursor % peers.length;
    return [...peers.slice(start), ...peers.slice(0, start)].slice(0, 3);
  }, [currentWord, cursor, selectedGroup]);
  const todayReviews = useMemo(() => reviews.filter((review) => sameDay(review.at)), [reviews]);
  const todayAnswered = todayReviews.filter((review) => review.result !== "skipped");
  const todayRemembered = todayAnswered.filter((review) => review.result === "remembered").length;
  const todayRate = todayAnswered.length ? Math.round((todayRemembered / todayAnswered.length) * 100) : 0;
  const groupMastery = selectedGroup ? masteryFor(selectedGroup) : 0;
  const filteredWords = useMemo(() => {
    if (!selectedGroup) return [];
    const query = libraryQuery.trim().toLowerCase();
    const matching = selectedGroup.words.filter((word) => {
      const status = statusFor(word).tone;
      const matchesStatus = libraryStatus === "all" || status === libraryStatus;
      const matchesQuery = !query || [word.term, word.phonetic, word.meaning, word.expansion, word.example]
        .some((value) => value?.toLowerCase().includes(query));
      return matchesStatus && matchesQuery;
    });

    if (librarySort.key === "source") return matching;
    const direction = librarySort.direction === "asc" ? 1 : -1;
    return [...matching].sort((a, b) => {
      const metricDifference = sortMetric(a, librarySort.key as Exclude<SortKey, "source">)
        - sortMetric(b, librarySort.key as Exclude<SortKey, "source">);
      if (metricDifference !== 0) return metricDifference * direction;
      return (a.sequence ?? Number.MAX_SAFE_INTEGER) - (b.sequence ?? Number.MAX_SAFE_INTEGER);
    });
  }, [libraryQuery, librarySort, libraryStatus, selectedGroup]);

  function prepareGroup(group?: WordGroup) {
    reviewSessions.current[selectedGroupId] = captureReviewSession(queue, cursor, roundDone);
    const restored = restoreReviewSession(group?.words ?? [], group ? reviewSessions.current[group.id] : undefined, reviews, group?.id);
    setQueue(restored.queue);
    setCursor(restored.cursor);
    setRevealed(false);
    setRoundDone(restored.roundDone);
    setSession(summarizeQueueSession(restored.queue));
  }

  function moveForward(nextQueue = queue) {
    setRevealed(false);
    if (cursor + 1 >= nextQueue.length) {
      setRoundDone(true);
      return;
    }
    setCursor((value) => value + 1);
  }

  function answerWord(result: ReviewResult) {
    if (!ready || !storageWritable.current || roundDone || !currentWord || !selectedGroup) return;
    const currentEntry = queue[cursor];
    if (!currentEntry) return;

    const answeredAt = new Date().toISOString();
    const nextQueue = answerQueueEntry(queue, cursor, result, answeredAt);
    const wordSummary = summarizeQueueWord(nextQueue, currentWord.id);
    if (!wordSummary) return;

    setQueue(nextQueue);
    setReviews((items) => [
      ...items.filter((review) => review.queueEntryId !== currentEntry.id),
      {
        id: `review-${currentEntry.id}`,
        queueEntryId: currentEntry.id,
        groupId: selectedGroup.id,
        wordId: currentWord.id,
        result,
        at: answeredAt,
      },
    ]);
    setGroups((items) =>
      items.map((group) =>
        group.id !== selectedGroup.id
          ? group
          : {
              ...group,
              words: group.words.map((word) =>
                word.id !== currentWord.id
                  ? word
                  : {
                      ...word,
                      remembered: wordSummary.remembered,
                      forgotten: wordSummary.forgotten,
                      streak: wordSummary.streak,
                      encounters: wordSummary.encounters,
                      lastSeen: wordSummary.lastSeen,
                    },
              ),
            },
      ),
    );
    setSession(summarizeQueueSession(nextQueue));
    moveForward(nextQueue);
  }

  function gradeWord(result: "remembered" | "forgotten") {
    answerWord(result);
  }

  function skipWord() {
    answerWord("skipped");
  }

  function previousWord() {
    if (cursor === 0) return;
    setRoundDone(false);
    setRevealed(false);
    setCursor((value) => value - 1);
  }

  function restartRound() {
    if (!selectedGroup) return;
    const ordered = [...selectedGroup.words]
      .sort((a, b) =>
        b.forgotten - b.remembered - (a.forgotten - a.remembered))
      .map((word) => word.id);
    setQueue(createReviewQueue(ordered.map((id) => selectedGroup.words.find((word) => word.id === id)!)));
    setCursor(0);
    setRevealed(false);
    setRoundDone(false);
    setSession(emptySession);
  }

  useEffect(() => {
    function handleKeydown(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(target.tagName) || mode !== "study" || roundDone) {
        return;
      }
      if (event.key === " ") {
        event.preventDefault();
        setRevealed((value) => !value);
      } else if (event.key === "1") {
        gradeWord("remembered");
      } else if (event.key === "2") {
        gradeWord("forgotten");
      } else if (event.key === "ArrowRight") {
        skipWord();
      } else if (event.key === "ArrowLeft") {
        previousWord();
      }
    }
    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  });

  function selectGroup(id: string) {
    prepareGroup(groups.find((group) => group.id === id));
    setSelectedGroupId(id);
    setNotice("");
  }

  function handleAddGroup(event: FormEvent) {
    event.preventDefault();
    const name = newGroupName.trim();
    if (!name) {
      setNotice("Enter a name for the new group.");
      return;
    }
    const group: WordGroup = {
      id: makeId("group"),
      name,
      description: newGroupDescription.trim() || "A group of related words",
      accent: ACCENTS[groups.length % ACCENTS.length],
      words: [],
    };
    setGroups((items) => [...items, group]);
    setSelectedGroupId(group.id);
    prepareGroup(group);
    setNewGroupName("");
    setNewGroupDescription("");
    setNotice(`Created ${group.name}. You can now add words.`);
  }

  function previewWords() {
    try { setImportPreview(parseWords(batchText, importFormat)); setNotice(""); }
    catch (error) { setImportPreview(null); setNotice((error as Error).message); }
  }

  function handleAddWords(event: FormEvent) {
    event.preventDefault();
    if (!selectedGroup) return;
    if (!importPreview) { setNotice("Preview the import before adding words."); return; }
    const parsed = importPreview.words;
    const existing = new Set(selectedGroup.words.map((word) => word.term.toLowerCase()));
    const unique = parsed.filter((word) => {
      const key = word.term.toLowerCase();
      if (existing.has(key)) return false;
      existing.add(key);
      return true;
    });
    const used = new Set(selectedGroup.words.map(word => word.sequence));
    let nextSequence = Math.max(0, ...selectedGroup.words.map(word => word.sequence ?? 0)) + 1;
    let renumbered = 0;
    const words: Word[] = unique.map((word) => {
      let sequence = word.sequence;
      if (!sequence || used.has(sequence)) {
        if (sequence) renumbered++;
        while (used.has(nextSequence)) nextSequence++;
        sequence = nextSequence++;
      }
      used.add(sequence);
      return ({
      id: makeId("word"),
      ...word,
      sequence,
      remembered: 0,
      forgotten: 0,
      streak: 0,
      encounters: 0,
    }); });
    const updatedGroup = { ...selectedGroup, words: [...selectedGroup.words, ...words] };
    setGroups((items) => items.map((group) => (group.id === selectedGroup.id ? updatedGroup : group)));
    prepareGroup(updatedGroup);
    setBatchText("");
    setImportPreview(null);
    const duplicateCount = parsed.length - words.length;
    setNotice(
      `Added ${words.length} words${duplicateCount ? `; skipped ${duplicateCount} existing words (existing content kept)` : ""}${renumbered ? `; reassigned ${renumbered} conflicting numbers` : ""}.`,
    );
  }

  function deleteWord(word: Word) {
    if (!selectedGroup || !window.confirm(`Delete ${word.term} from ${selectedGroup.name}?`)) return;
    const updatedGroup = { ...selectedGroup, words: selectedGroup.words.filter((item) => item.id !== word.id) };
    setGroups((items) => items.map((group) => (group.id === selectedGroup.id ? updatedGroup : group)));
    prepareGroup(updatedGroup);
    setNotice(`Deleted ${word.term}.`);
  }

  function deleteGroup() {
    if (!selectedGroup) return;
    if (groups.length === 1) {
      setNotice("Keep at least one group. Create another group before deleting this one.");
      return;
    }
    if (!window.confirm(`Delete ${selectedGroup.name} and all its words?`)) return;
    const remaining = groups.filter((group) => group.id !== selectedGroup.id);
    setGroups(remaining);
    setSelectedGroupId(remaining[0].id);
    prepareGroup(remaining[0]);
    setNotice(`Deleted the group ${selectedGroup.name}.`);
  }

  function startEdit(word: Word) {
    setEditingId(word.id);
    setEditDraft({
      sequence: word.sequence?.toString() ?? "",
      term: word.term,
      phonetic: word.phonetic,
      meaning: word.meaning,
      expansion: word.expansion || word.example || "",
    });
  }

  function saveEdit(wordId: string) {
    if (!selectedGroup || !editDraft.term.trim()) {
      setNotice("The word cannot be empty.");
      return;
    }
    setGroups((items) =>
      items.map((group) =>
        group.id !== selectedGroup.id
          ? group
          : {
              ...group,
              words: group.words.map((word) =>
                word.id === wordId
                    ? {
                      ...word,
                      sequence: editDraft.sequence ? Number(editDraft.sequence) : word.sequence,
                      term: editDraft.term.trim(),
                      phonetic: editDraft.phonetic.trim(),
                      meaning: editDraft.meaning.trim(),
                      expansion: editDraft.expansion.trim(),
                    }
                  : word,
              ),
            },
      ),
    );
    setEditingId(null);
    setNotice("Word updated.");
  }

  function exportData() {
    const payload = storageWritable.current ? JSON.stringify({
      progressSchema: 3, catalogVersion, groups, reviews, selectedGroupId,
      reviewSessions: { ...reviewSessions.current, [selectedGroupId]: captureReviewSession(queue, cursor, roundDone) },
    }, null, 2) : window.localStorage.getItem(storageKey.current) ?? "{}";
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `sat-study-backup-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setNotice("Backup exported.");
  }

  function toggleLibrarySort(key: Exclude<SortKey, "source">) {
    setLibrarySort((current) => current.key === key
      ? { key, direction: current.direction === "desc" ? "asc" : "desc" }
      : { key, direction: "desc" });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            W
          </div>
          <div>
            <p className="brand-name">Word Clusters</p>
            <p className="brand-subtitle">SAT STUDY KIT</p>
          </div>
        </div>

        <nav className="primary-nav" aria-label="Main navigation">
          <button className={mode === "study" ? "active" : ""} onClick={() => setMode("study")}>
            <span aria-hidden="true">◎</span>
            Review
          </button>
          <button className={mode === "library" ? "active" : ""} onClick={() => setMode("library")}>
            <span aria-hidden="true">▤</span>
            Word library
          </button>
        </nav>

        <div className="sidebar-heading">
          <span>My groups</span>
          <button className="mini-add" aria-label="New group" onClick={() => setMode("library")}>
            ＋
          </button>
        </div>

        <div className="group-list">
          {groups.map((group) => {
            const mastery = masteryFor(group);
            return (
              <button
                key={group.id}
                className={`group-item ${group.id === selectedGroupId ? "selected" : ""}`}
                style={{ "--group-accent": group.accent } as CSSProperties}
                onClick={() => selectGroup(group.id)}
              >
                <span className="group-dot" aria-hidden="true" />
                <span className="group-copy">
                  <strong>{group.name}</strong>
                  <small>Words: {group.words.length}</small>
                </span>
                <span className="group-mastery">{mastery}%</span>
              </button>
            );
          })}
        </div>

        <div className="today-card">
          <div className="today-card-head">
            <span>Today</span>
            <strong>{todayRate}%</strong>
          </div>
          <div className="today-track" aria-label={`Accuracy today ${todayRate}%`}>
            <span style={{ width: `${todayRate}%` }} />
          </div>
          <p>{todayAnswered.length ? `Answers today: ${todayAnswered.length}` : "No answers yet. Start with one card."}</p>
        </div>
      </aside>

      <main className="main-area">
        {notice ? <div className="notice" role="status"><span>●</span>{notice}<button onClick={() => setNotice("")} aria-label="Dismiss notice">×</button></div> : null}

        {mode === "study" ? (
          <>
            <header className="topbar">
              <div>
                <p className="eyebrow">REVIEWING · WORDS: {selectedGroup?.words.length ?? 0}</p>
                <h1>{selectedGroup?.name ?? "My groups"}</h1>
                <p className="topbar-description">{selectedGroup?.description}</p>
              </div>
              <div className="mastery-pill">
                <span>Group mastery</span>
                <strong>{groupMastery}%</strong>
              </div>
            </header>

            {!selectedGroup?.words.length ? (
              <section className="empty-panel">
                <span className="empty-glyph" aria-hidden="true">＋</span>
                <p className="eyebrow">EMPTY GROUP</p>
                <h2>This group has no words yet</h2>
                <p>Add a few related words, then return here to review them.</p>
                <button className="primary-button" onClick={() => setMode("library")}>
                  Add words
                </button>
              </section>
            ) : roundDone ? (
              <section className="round-summary">
                <div className="summary-stamp" aria-hidden="true">DONE</div>
                <p className="eyebrow">ROUND COMPLETE</p>
                <h2>You have finished this group.</h2>
                <p className="summary-lead">Missed words return until you recall them correctly three times in a row. A wrong answer restarts the streak. Historical errors stay in your record. This round is saved.</p>
                <div className="summary-grid">
                  <div><strong>{session.remembered}</strong><span>Remembered</span></div>
                  <div><strong>{session.forgotten}</strong><span>Forgotten</span></div>
                  <div><strong>{session.skipped}</strong><span>Skipped</span></div>
                </div>
                <button className="primary-button" onClick={restartRound}>Start another round <span aria-hidden="true">↻</span></button>
              </section>
            ) : currentWord ? (
              <div className="study-layout">
                <section className="study-column">
                  <div className="card-navigation">
                    <button onClick={previousWord} disabled={cursor === 0} aria-label="Previous card">←</button>
                    <div className="progress-dashes" aria-label={`Card ${cursor + 1} of ${queue.length}`}>
                      {queue.slice(0, 12).map((entry, index) => (
                        <span key={entry.id} className={index < cursor ? "done" : index === cursor ? "current" : ""} />
                      ))}
                    </div>
                    <span className="page-count">{String(cursor + 1).padStart(2, "0")} / {String(queue.length).padStart(2, "0")}</span>
                  </div>

                  <article className={`word-card ${revealed ? "revealed" : ""}`}>
                    <div className="paper-grain" aria-hidden="true" />
                    <div className="card-meta">
                      <span className={`status-badge ${statusFor(currentWord).tone}`}>{statusFor(currentWord).label}</span>
                      <span>#{String(currentWord.sequence ?? cursor + 1).padStart(3, "0")} · {currentLearning?.forgotten ? `Recovery ${Math.min(currentLearning.streak, 3)}/3` : `Streak ${currentWord.streak}`}</span>
                    </div>
                    <div className="word-main">
                      <p className="word-label">WORD</p>
                      <h2>{currentWord.term}</h2>
                      <p className="phonetic">{currentWord.phonetic || "Pronunciation not provided"}</p>
                    </div>

                    <button className="reveal-area" onClick={() => setRevealed((value) => !value)} aria-expanded={revealed}>
                      {revealed ? (
                        <span className="answer-copy">
                          <span className="meaning-block">
                            <small>Meaning</small>
                            <strong className="meaning-copy">{currentWord.meaning || "No meaning provided"}</strong>
                          </span>
                          {currentExpansion ? (
                            <span className="extension-copy">
                              <small>Notes</small>
                              <em>{currentExpansion}</em>
                            </span>
                          ) : null}
                          <small>Click to hide the definition</small>
                        </span>
                      ) : (
                        <span className="reveal-prompt">
                          <i aria-hidden="true">↳</i>
                          <span><strong>Can you recall the meaning?</strong><small>Click or press Space to reveal</small></span>
                        </span>
                      )}
                    </button>

                    <div className="answer-actions">
                      <button className="remember-button" onClick={() => gradeWord("remembered")}>
                        <span className="action-key">1</span>
                        <span><strong>Remember</strong><small>{currentLearning?.needsReview ? "Recall 3 times to finish" : "Next word"}</small></span>
                        <i aria-hidden="true">✓</i>
                      </button>
                      <button className="forget-button" onClick={() => gradeWord("forgotten")}>
                        <span className="action-key">2</span>
                        <span><strong>Forgot</strong><small>Review again later</small></span>
                        <i aria-hidden="true">↻</i>
                      </button>
                      <button className="skip-button" onClick={skipWord}>
                        <span><strong>Skip</strong><small>Decide later</small></span>
                        <i aria-hidden="true">→</i>
                      </button>
                    </div>
                  </article>

                  <section className="association-strip">
                    <div className="association-title">
                      <span className="link-mark" aria-hidden="true">∞</span>
                      <div><strong>Related words</strong><small>Use connections to help recall</small></div>
                    </div>
                    <div className="association-words">
                      {relatedWords.map((word) => (
                        <span key={word.id}><strong>{word.term}</strong><small>{revealed ? word.meaning : "····"}</small></span>
                      ))}
                    </div>
                  </section>
                </section>

                <aside className="session-panel">
                  <div>
                    <p className="eyebrow">THIS ROUND</p>
                    <h3>Responses: {session.remembered + session.forgotten + session.skipped}</h3>
                  </div>
                  <div className="session-numbers">
                    <div><span className="number-dot remembered" /><strong>{session.remembered}</strong><small>Remembered</small></div>
                    <div><span className="number-dot forgotten" /><strong>{session.forgotten}</strong><small>Forgotten</small></div>
                    <div><span className="number-dot skipped" /><strong>{session.skipped}</strong><small>Skipped</small></div>
                  </div>
                  <div className="learning-note">
                    <span aria-hidden="true">※</span>
                    <p><strong>Study tip</strong>Recall this word first, then look at related words. Try linking them with a specific example.</p>
                  </div>
                  <div className="shortcut-note">
                    <span>1 Remember</span><span>2 Forgot</span><span>→ Skip</span>
                  </div>
                </aside>
              </div>
            ) : null}
          </>
        ) : (
          <section className="library-view">
            <header className="topbar library-topbar">
              <div>
                <p className="eyebrow">VOCABULARY LIBRARY</p>
                <h1>Word library</h1>
                <p className="topbar-description">Paste or upload your own words in a supported format. Preview corrections before adding them. One original example is included.</p>
              </div>
              <div className="library-header-actions">
                <button className="outline-button" onClick={exportData}>Export backup ↓</button>
              </div>
            </header>

            <div className="library-tools">
              <form className="tool-card group-form" onSubmit={handleAddGroup}>
                <div className="tool-number">01</div>
                <div className="tool-heading"><p className="eyebrow">NEW GROUP</p><h2>New group</h2></div>
                <label>Group name<input value={newGroupName} onChange={(event) => setNewGroupName(event.target.value)} placeholder="For example: Travel" /></label>
                <label>Description<input value={newGroupDescription} onChange={(event) => setNewGroupDescription(event.target.value)} placeholder="For example: Airports and transport" /></label>
                <button className="dark-button" type="submit">Create group ＋</button>
              </form>

              <form className="tool-card word-form" onSubmit={handleAddWords}>
                <div className="tool-number">02</div>
                <div className="tool-heading"><p className="eyebrow">ADD WORDS TO</p><h2>{selectedGroup?.name}</h2></div>
                <label>Import format<select value={importFormat} onChange={event => { setImportFormat(event.target.value as WordFormat); setImportPreview(null); }}>
                  <option value="auto">Auto-detect</option><option value="csv">CSV</option><option value="tsv">TSV</option><option value="pipe">Pipe-separated</option><option value="pairs">Word = meaning</option><option value="json">JSON</option>
                </select></label>
                <button className="outline-button" type="button" onClick={() => importFile.current?.click()}>Upload text file (.csv, .tsv, .txt, .json)</button>
                <input ref={importFile} style={{ display: "none" }} aria-label="Upload text file" type="file" accept=".csv,.tsv,.txt,.json" onChange={async event => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  if (file.size > 2_000_000) { setNotice("Import limit: 2 MB."); return; }
                  try { setBatchText(await file.text()); setImportPreview(null); }
                  catch { setNotice("Could not read the file."); }
                  event.target.value = "";
                }} />
                <label>Words to import
                  <textarea value={batchText} onChange={(event) => { setBatchText(event.target.value); setImportPreview(null); }} placeholder={"concise = brief and clear"} />
                </label>
                <details><summary>Supported formats and automatic corrections</summary>
                  <p>CSV, TSV or pipe: use a header (term, meaning, phonetic, expansion, sequence), or 2 columns: word / meaning; 4: word / pronunciation / meaning / notes; 5: sequence / word / pronunciation / meaning / notes. Quote fields containing separators or line breaks; double quotes inside quoted fields.</p>
                  <p>Pairs: one word = meaning per line. JSON: an array of objects with term and meaning; optional phonetic, expansion and sequence. Header aliases: word, definition, pronunciation, notes, number.</p>
                  <p>Automatic corrections: BOM, line endings, outer whitespace, full-width pipe separators, field aliases and invalid or conflicting sequence numbers. Identical duplicates are skipped; conflicting new definitions are rejected. Existing words are kept, not overwritten. Spelling, definitions and missing content are never guessed.</p>
                </details>
                <button className="outline-button" type="button" onClick={previewWords}>Preview import</button>
                {importPreview && <div role="status"><p>{importPreview.words.length} words · {importPreview.format}. Existing words will be skipped.</p>
                  <ul>{importPreview.corrections.map((message, i) => <li key={i}>{message}</li>)}</ul>
                  <div style={{maxHeight: 220, overflow: "auto"}}>{importPreview.words.map((word, i) => <p key={i}><strong>{word.term}</strong> — {word.meaning} {word.phonetic} {word.expansion}</p>)}</div>
                </div>}
                <button className="primary-button" type="submit" disabled={!importPreview}>Add previewed words →</button>
              </form>
            </div>

            <section className="word-table-card" style={{ "--group-accent": selectedGroup?.accent ?? ACCENTS[0] } as CSSProperties}>
              <div className="word-table-head">
                <div>
                  <span className="group-color" />
                  <div><p className="eyebrow">CURRENT GROUP</p><h2>{selectedGroup?.name}</h2></div>
                </div>
                <div className="table-actions"><span>Words: {selectedGroup?.words.length ?? 0} · Mastery {groupMastery}%</span><button onClick={deleteGroup}>Delete group</button></div>
              </div>

              <div className="word-filter-bar">
                <label className="word-search">
                  <span aria-hidden="true">⌕</span>
                  <input
                    value={libraryQuery}
                    onChange={(event) => setLibraryQuery(event.target.value)}
                    placeholder="Search words, meanings or notes"
                    aria-label="Search this group"
                  />
                </label>
                <select value={libraryStatus} onChange={(event) => setLibraryStatus(event.target.value as typeof libraryStatus)} aria-label="Filter by learning status">
                  <option value="all">All statuses</option>
                  <option value="new">New</option>
                  <option value="learning">Learning</option>
                  <option value="mastered">Mastered</option>
                </select>
                <span>Results: {filteredWords.length}</span>
              </div>

              <div className="sort-toolbar" aria-label="Sort words">
                <div className="sort-toolbar-copy">
                  <strong>Sort words</strong>
                  <small>Click again to reverse the order</small>
                </div>
                <div className="sort-buttons">
                  {SORT_OPTIONS.map((option) => {
                    const active = librarySort.key === option.key;
                    const arrow = active ? (librarySort.direction === "desc" ? "↓" : "↑") : "↕";
                    return (
                      <button
                        key={option.key}
                        className={active ? "active" : ""}
                        onClick={() => toggleLibrarySort(option.key)}
                        aria-pressed={active}
                        title={`${option.label}: ${active && librarySort.direction === "asc" ? "Low to high" : "High to low"}`}
                      >
                        {option.label}<span aria-hidden="true">{arrow}</span>
                      </button>
                    );
                  })}
                  <button
                    className="restore-order"
                    onClick={() => setLibrarySort({ key: "source", direction: "asc" })}
                    disabled={librarySort.key === "source"}
                  >
                    Original order
                  </button>
                </div>
              </div>

              {filteredWords.length ? (
                <div className="word-list">
                  {filteredWords.map((word) => {
                    const index = selectedGroup.words.findIndex((item) => item.id === word.id);
                    const status = statusFor(word);
                    const attempts = word.remembered + word.forgotten;
                    const errorRate = attempts ? Math.round(errorRateFor(word) * 100) : null;
                    const encounters = encountersFor(word);
                    return editingId === word.id ? (
                      <div className="word-edit-row" key={word.id}>
                        <input type="number" min="1" aria-label="Sequence" value={editDraft.sequence} onChange={(event) => setEditDraft({ ...editDraft, sequence: event.target.value })} />
                        <input aria-label="Word" value={editDraft.term} onChange={(event) => setEditDraft({ ...editDraft, term: event.target.value })} />
                        <input aria-label="Pronunciation" value={editDraft.phonetic} onChange={(event) => setEditDraft({ ...editDraft, phonetic: event.target.value })} />
                        <input aria-label="Meaning" value={editDraft.meaning} onChange={(event) => setEditDraft({ ...editDraft, meaning: event.target.value })} />
                        <input aria-label="Notes" value={editDraft.expansion} onChange={(event) => setEditDraft({ ...editDraft, expansion: event.target.value })} />
                        <div><button className="save-edit" onClick={() => saveEdit(word.id)}>Save</button><button onClick={() => setEditingId(null)}>Cancel</button></div>
                      </div>
                    ) : (
                      <div className="word-row" key={word.id}>
                        <span className="row-index">{String(word.sequence ?? index + 1).padStart(3, "0")}</span>
                        <div className="word-identity"><strong>{word.term}</strong><small>{word.phonetic || "No pronunciation"}</small></div>
                        <div className="word-definition"><strong>{word.meaning || "No meaning"}</strong><small>{word.expansion || word.example || "No notes"}</small></div>
                        <span className={`status-badge ${status.tone}`}>{status.label}</span>
                        <div className="accuracy">
                          <strong>{errorRate === null ? "—" : `${errorRate}%`}</strong>
                          <small>Errors {word.forgotten} · Seen {encounters}</small>
                        </div>
                        <div className="row-actions"><button onClick={() => startEdit(word)}>Edit</button><button onClick={() => deleteWord(word)}>Delete</button></div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="table-empty">
                  <p>{selectedGroup?.words.length ? "No words match these filters." : "This group has no words yet."}</p>
                  <span>{selectedGroup?.words.length ? "Try a different keyword or status." : "Paste the words above, one per line."}</span>
                </div>
              )}
            </section>
          </section>
        )}
      </main>
    </div>
  );
}
