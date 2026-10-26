import { useCallback, useEffect, useRef, useState } from "react";
import LibraryWorkspace from "./LibraryWorkspace";
import type {
  ClipboardMode,
  GroupContent,
  LibraryClipboard,
} from "./clipboard";

export type Word = {
  id: string;
  term: string;
  meaning: string;
  phonetic: string;
  expansion: string;
  sequence: number;
  remembered: number;
  forgotten: number;
  streak: number;
  encounters: number;
  lastSeen?: string;
};
export type Group = {
  id: string;
  book_id: string;
  name: string;
  words: Word[];
};
export type Book = { id: string; name: string };
export type State = {
  books: Book[];
  groups: Group[];
  sessions: Record<string, { queue: string[]; cursor: number }>;
  book_sessions: Record<
    string,
    { mode: string; order: string[]; current: string | null }
  >;
};
type Question = {
  id?: string;
  module: number;
  passage: string;
  question: string;
  options: Record<string, string>;
  answer: string;
  explanation: string;
};
type Bank = {
  id: string;
  schema_version: number;
  title: string;
  questions: Question[];
};
export type Snapshot = {
  state: State;
  revision: string;
  canUndo: boolean;
  banks: Bank[];
  bankErrors: string[];
  wordFormats: string;
  questionFormats: string;
  id?: string;
  group_id?: string | null;
  preview?: any;
  corrections?: string[];
  message?: string;
  group_preview?: GroupContent[];
  group_ids?: string[];
};
export type Call = (
  action: string,
  args?: Record<string, any>,
) => Promise<Snapshot>;
export const status = (state: State, group: Group) =>
  !group.words.length
    ? "Empty"
    : !state.sessions[group.id]
      ? "Not started"
      : state.sessions[group.id].cursor >= state.sessions[group.id].queue.length
        ? "Complete"
        : "In progress";
export const mastery = (words: Word[]) =>
  words.length
    ? Math.round(
        (words.filter((w) => w.streak >= 3).length / words.length) * 100,
      )
    : 0;

export default function Desktop() {
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const current = useRef<Snapshot>(undefined);
  const [page, setPage] = useState("library");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [arrange, setArrange] = useState(false);
  const [libraryClipboard, setLibraryClipboard] =
    useState<LibraryClipboard | null>(null);
  const [clipboardMode, setClipboardMode] = useState<ClipboardMode>("app");
  const [review, setReview] = useState<{
    gid: string | null;
    bid?: string;
    order: string;
  }>({ gid: null, order: "Sequential" });
  const [revealed, setRevealed] = useState(false);
  const [help, setHelp] = useState(false);
  const [formDirty, setFormDirty] = useState(false);
  const [leaveTo, setLeaveTo] = useState<string>();
  const [libraryKey, setLibraryKey] = useState(0);
  const [reviewCount, setReviewCount] = useState({
    remembered: 0,
    forgotten: 0,
    skipped: 0,
  });
  const call: Call = useCallback(async (action, args = {}) => {
    if (pending.current)
      throw new Error("Please wait for the current change to finish.");
    pending.current = true;
    setBusy(true);
    try {
      const response = await fetch("/api", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${location.hash.slice(1)}`,
        },
        body: JSON.stringify({
          action,
          args: { revision: current.current?.revision, ...args },
        }),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(result.error || "The change could not be saved.");
      current.current = result;
      setSnapshot(result);
      setError(false);
      setNotice(result.message || "");
      return result;
    } catch (e) {
      setError(true);
      setNotice((e as Error).message);
      throw e;
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    void call("load").catch(() => {});
  }, [call]);
  useEffect(() => {
    const before = (e: BeforeUnloadEvent) => {
      if (formDirty || pending.current) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", before);
    return () => window.removeEventListener("beforeunload", before);
  }, [formDirty]);
  function navigate(to: string) {
    if (busy) return;
    if (formDirty) {
      setLeaveTo(to);
      return;
    }
    setPage(to);
    setNotice("");
  }
  async function start(
    gid?: string,
    bid?: string,
    order = "Sequential",
    restart = false,
  ) {
    if (formDirty) {
      setError(false);
      setNotice("Save or cancel your library edit before starting a review.");
      return;
    }
    try {
      const result = await call("begin", {
        group_id: gid,
        book_id: bid,
        order,
        restart,
      });
      setReview({ gid: result.group_id ?? null, bid, order });
      setRevealed(false);
      setPage("review");
      setReviewCount({ remembered: 0, forgotten: 0, skipped: 0 });
    } catch {
      /* message stays inline */
    }
  }
  async function rate(result: "remembered" | "forgotten" | "skipped") {
    if (
      pending.current ||
      !review.gid ||
      !snapshot ||
      (result !== "skipped" && !revealed)
    )
      return;
    try {
      const updated = await call("rate", {
        group_id: review.gid,
        book_id: review.bid,
        order: review.order,
        result,
        cursor: snapshot.state.sessions[review.gid].cursor,
      });
      setReview((r) => ({ ...r, gid: updated.group_id ?? null }));
      setRevealed(false);
      setReviewCount((c) => ({ ...c, [result]: c[result] + 1 }));
    } catch {
      /* message stays inline */
    }
  }
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (
        page !== "review" ||
        e.repeat ||
        (e.target as HTMLElement).closest(
          "input,textarea,select,[contenteditable=true]",
        )
      )
        return;
      if (e.key === "F1" || e.key === "?") {
        e.preventDefault();
        setHelp((v) => !v);
      } else if (e.key === "Escape") {
        e.preventDefault();
        navigate("library");
      } else if (e.key === " ") {
        e.preventDefault();
        setRevealed((v) => !v);
      } else if (["1", "2", "3", "ArrowRight"].includes(e.key)) {
        e.preventDefault();
        void rate(
          e.key === "1"
            ? "remembered"
            : e.key === "2"
              ? "forgotten"
              : "skipped",
        );
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });
  if (!snapshot)
    return (
      <div className="startup">
        <h1>StudyWeave</h1>
        <p>{notice || "Opening your local library…"}</p>
        {error && (
          <button onClick={() => void call("load").catch(() => {})}>
            Retry
          </button>
        )}
      </div>
    );
  const { state } = snapshot;
  const group = state.groups.find((g) => g.id === review.gid);
  const session = group && state.sessions[group.id];
  const word = group?.words.find(
    (w) => w.id === session?.queue[session.cursor],
  );
  const allWords = state.groups.flatMap((g) => g.words);
  const totalAnswers = allWords.reduce(
    (a, w) => a + w.remembered + w.forgotten,
    0,
  );
  const accuracy = totalAnswers
    ? Math.round(
        (allWords.reduce((a, w) => a + w.remembered, 0) / totalAnswers) * 100,
      )
    : 0;
  const safeCall = (action: string, args?: Record<string, any>) =>
    void call(action, args).catch(() => {});
  return (
    <div className="app-shell desktop-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">S</div>
          <p className="brand-name">StudyWeave</p>
        </div>
        <nav className="primary-nav" aria-label="Main navigation">
          {[
            ["library", "▤", "Word library"],
            ["review", "◎", "Review"],
            ["banks", "▧", "Question banks"],
            ["practice", "◷", "Practice"],
          ].map(([id, icon, name]) => (
            <button
              key={id}
              className={page === id ? "active" : ""}
              onClick={() => navigate(id)}
            >
              <span aria-hidden="true">{icon}</span>
              {name}
            </button>
          ))}
        </nav>
        <div className="sidebar-heading">MY BOOKS</div>
        <div className="group-list">
          {state.books.map((book, i) => (
            <button
              className="group-item"
              key={book.id}
              onClick={() => {
                if (formDirty) {
                  navigate("library");
                  return;
                }
                setLibraryKey((v) => v + 1);
                sessionStorage.setItem("desktop-open-book", book.id);
                setPage("library");
              }}
            >
              <span
                className="group-dot"
                style={{ background: ["#ea6a47", "#8eac94", "#8aabc6"][i % 3] }}
              />
              <span className="group-copy">
                <strong>{book.name}</strong>
                <small>
                  {state.groups.filter((g) => g.book_id === book.id).length}{" "}
                  groups
                </small>
              </span>
            </button>
          ))}
        </div>
        <div className="today-card">
          <p>YOUR LIBRARY</p>
          <div className="sidebar-totals">
            <strong>
              {allWords.length}
              <small>Words</small>
            </strong>
            <strong>
              {accuracy}%<small>Recall accuracy</small>
            </strong>
          </div>
          <button className="sidebar-backup" onClick={() => safeCall("export")}>
            Export full backup ↓
          </button>
        </div>
      </aside>
      <main className="main-content desktop-main" aria-busy={busy}>
        {leaveTo && (
          <div className="notice-banner">
            Keep your unsaved edit?
            <button
              onClick={() => {
                setFormDirty(false);
                setPage(leaveTo);
                setLibraryKey((v) => v + 1);
                setLeaveTo(undefined);
              }}
            >
              Discard edit
            </button>
            <button onClick={() => setLeaveTo(undefined)}>Keep editing</button>
          </div>
        )}
        {notice && (
          <div
            role={error ? "alert" : "status"}
            className={`desktop-notice ${error ? "error" : ""}`}
          >
            <span>{notice}</span>
            {error && <button onClick={() => safeCall("load")}>Reload</button>}
            <button aria-label="Dismiss message" onClick={() => setNotice("")}>
              ×
            </button>
          </div>
        )}
        {page === "library" && (
          <LibraryWorkspace
            key={libraryKey}
            snapshot={snapshot}
            call={call}
            busy={busy}
            arrange={arrange}
            setArrange={setArrange}
            onStudy={start}
            onDirty={setFormDirty}
            clipboard={libraryClipboard}
            setClipboard={setLibraryClipboard}
            clipboardMode={clipboardMode}
            setClipboardMode={setClipboardMode}
          />
        )}
        {page === "review" && (
          <>
            <header className="topbar">
              <div>
                <p className="eyebrow">
                  {review.bid
                    ? state.books.find((b) => b.id === review.bid)?.name
                    : "VOCABULARY"}
                </p>
                <h1>{group?.name || "Review"}</h1>
              </div>
              <div className="header-tools">
                <button
                  className="outline-button"
                  onClick={() => navigate("library")}
                >
                  Choose group
                </button>
                <button
                  className="help-button"
                  onClick={() => setHelp((v) => !v)}
                  aria-label="Keyboard shortcuts"
                >
                  ?
                </button>
              </div>
            </header>
            {help && (
              <div className="inline-help">
                <kbd>Space</kbd> Reveal / hide · <kbd>1</kbd> Remember ·{" "}
                <kbd>2</kbd> Forgot · <kbd>3</kbd> Skip · <kbd>Esc</kbd> Library
                · <kbd>?</kbd> Help. Reveal before rating.
              </div>
            )}
            {word && session ? (
              <div className="study-layout">
                <section className="study-column">
                  <div className="card-navigation">
                    <span>{review.order}</span>
                    <div className="progress-dashes">
                      {session.queue
                        .slice(
                          Math.max(0, session.cursor - 5),
                          session.cursor + 7,
                        )
                        .map((id, i) => (
                          <span
                            key={`${id}-${i}`}
                            className={
                              i < Math.min(session.cursor, 5)
                                ? "done"
                                : i === Math.min(session.cursor, 5)
                                  ? "current"
                                  : ""
                            }
                          />
                        ))}
                    </div>
                    <span>
                      {session.cursor + 1} / {session.queue.length}
                    </span>
                  </div>
                  <article
                    className={`word-card ${revealed ? "revealed" : ""}`}
                  >
                    <div className="paper-grain" />
                    <div className="card-meta">
                      <span
                        className={`status-badge ${word.streak >= 3 ? "mastered" : word.encounters ? "learning" : "new"}`}
                      >
                        {word.streak >= 3
                          ? "Mastered"
                          : word.encounters
                            ? "Learning"
                            : "New"}
                      </span>
                      <span>Streak {word.streak}</span>
                    </div>
                    <div className="word-main">
                      <h2>{word.term}</h2>
                      {word.phonetic && (
                        <p className="phonetic">{word.phonetic}</p>
                      )}
                    </div>
                    <button
                      className="reveal-area"
                      aria-expanded={revealed}
                      onClick={() => setRevealed((v) => !v)}
                    >
                      {revealed ? (
                        <span className="answer-copy">
                          <span className="meaning-block">
                            <small>Meaning</small>
                            <strong className="meaning-copy">
                              {word.meaning}
                            </strong>
                          </span>
                          {word.expansion && (
                            <span className="extension-copy">
                              <small>Notes</small>
                              <em>{word.expansion}</em>
                            </span>
                          )}
                        </span>
                      ) : (
                        <span className="reveal-prompt">
                          <i>↳</i>
                          <strong>
                            Reveal meaning <kbd>Space</kbd>
                          </strong>
                        </span>
                      )}
                    </button>
                    <div className="answer-actions">
                      <button
                        disabled={!revealed || busy}
                        className="remember-button"
                        onClick={() => void rate("remembered")}
                      >
                        <span className="action-key">1</span>
                        <strong>Remember</strong>
                        <i>✓</i>
                      </button>
                      <button
                        disabled={!revealed || busy}
                        className="forget-button"
                        onClick={() => void rate("forgotten")}
                      >
                        <span className="action-key">2</span>
                        <strong>Forgot</strong>
                        <i>↻</i>
                      </button>
                      <button
                        disabled={busy}
                        className="skip-button"
                        onClick={() => void rate("skipped")}
                      >
                        <span className="action-key">3</span>
                        <strong>Skip</strong>
                        <i>→</i>
                      </button>
                    </div>
                  </article>
                  <section className="association-strip">
                    <div className="association-title">
                      <span className="link-mark">∞</span>
                      <strong>In this group</strong>
                    </div>
                    <div className="association-words">
                      {group?.words
                        .filter((w) => w.id !== word.id)
                        .slice(0, 3)
                        .map((w) => (
                          <span key={w.id}>
                            <strong>{w.term}</strong>
                            <small>{revealed ? w.meaning : "···"}</small>
                          </span>
                        ))}
                    </div>
                  </section>
                </section>
                <aside className="session-panel">
                  <div>
                    <p className="eyebrow">THIS SESSION</p>
                    <h3>
                      {Object.values(reviewCount).reduce((a, b) => a + b, 0)}{" "}
                      responses
                    </h3>
                  </div>
                  <div className="session-numbers">
                    {Object.entries(reviewCount).map(([key, value]) => (
                      <div key={key}>
                        <span className={`number-dot ${key}`} />
                        <strong>{value}</strong>
                        <small>{key[0].toUpperCase() + key.slice(1)}</small>
                      </div>
                    ))}
                  </div>
                  <div className="learning-note">
                    <p>
                      Missed words return after spaced intervals until three
                      consecutive correct recalls.
                    </p>
                  </div>
                  <div className="mastery-pill">
                    <span>Mastered in group</span>
                    <strong>{mastery(group!.words)}%</strong>
                  </div>
                </aside>
              </div>
            ) : (
              <section className="empty-panel">
                <div className="empty-glyph">◎</div>
                <h2>
                  {session || review.bid
                    ? "Round complete"
                    : "Choose what to study"}
                </h2>
                {(session || review.bid) && (
                  <button
                    className="primary-button"
                    onClick={() =>
                      void start(
                        review.gid ?? undefined,
                        review.bid,
                        review.order,
                        true,
                      )
                    }
                  >
                    Start new round
                  </button>
                )}
                <button
                  className="outline-button"
                  onClick={() => navigate("library")}
                >
                  Browse word books
                </button>
              </section>
            )}
          </>
        )}
        {(page === "banks" || page === "practice") && (
          <QuestionWorkspace
            key={page}
            snapshot={snapshot}
            call={call}
            practice={page === "practice"}
            busy={busy}
            onDirty={setFormDirty}
          />
        )}
      </main>
    </div>
  );
}

function QuestionWorkspace({
  snapshot,
  call,
  practice,
  busy,
  onDirty,
}: {
  snapshot: Snapshot;
  call: Call;
  practice: boolean;
  busy: boolean;
  onDirty: (v: boolean) => void;
}) {
  const [bid, setBid] = useState(snapshot.banks[0]?.id);
  const bank = snapshot.banks.find((b) => b.id === bid) ?? snapshot.banks[0];
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("");
  const [minutes, setMinutes] = useState([32, 32]);
  const [editor, setEditor] = useState<
    "new" | "rename" | "question" | "import" | null
  >(null);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [format, setFormat] = useState("auto");
  const [preview, setPreview] = useState<any>();
  const previewInput = useRef({ text: "", format: "auto" });
  previewInput.current = { text, format };
  const [corrections, setCorrections] = useState<string[]>([]);
  const [draft, setDraft] = useState<Question>({
    module: 1,
    passage: "",
    question: "",
    options: { A: "", B: "", C: "", D: "" },
    answer: "",
    explanation: "",
  });
  const [original, setOriginal] = useState<any>();
  const [dirty, setDirty] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [saving, setSaving] = useState(false);
  const editorGeneration = useRef(0);
  const touch = () => {
    setDirty(true);
    onDirty(true);
  };
  useEffect(() => () => onDirty(false), []);
  const safe = (action: string, args?: Record<string, any>) =>
    void call(action, args).catch(() => {});
  const open = (kind: typeof editor, question?: Question) => {
    editorGeneration.current += 1;
    setDirty(false);
    setDiscard(false);
    onDirty(false);
    setEditor(kind);
    setName(kind === "rename" ? (bank?.title ?? "") : "");
    setText("");
    setPreview(undefined);
    setOriginal(
      bank
        ? {
            schema_version: bank.schema_version,
            title: bank.title,
            questions: bank.questions,
          }
        : undefined,
    );
    setDraft(
      question ?? {
        module: 1,
        passage: "",
        question: "",
        options: { A: "", B: "", C: "", D: "" },
        answer: "",
        explanation: "",
      },
    );
  };
  const cancel = () => {
    if (saving) return;
    if (dirty && editor !== "import") {
      setDiscard(true);
      return;
    }
    closeEditor();
  };
  const closeEditor = () => {
    editorGeneration.current += 1;
    previewInput.current = { text: "", format };
    setText("");
    setPreview(undefined);
    setEditor(null);
    setDirty(false);
    setDiscard(false);
    onDirty(false);
  };
  const save = async () => {
    setSaving(true);
    try {
      const result = await call("bank", {
        id:
          editor === "new" || (editor === "import" && name.trim())
            ? undefined
            : bank?.id,
        original,
        ...(editor === "new" ||
        editor === "rename" ||
        (editor === "import" && name.trim())
          ? { name }
          : {}),
        ...(editor === "question"
          ? { question: draft, question_id: draft.id }
          : {}),
        ...(editor === "import" ? { text, format } : {}),
      });
      setBid(result.id);
      closeEditor();
    } catch {
      /* inline error */
    } finally {
      setSaving(false);
    }
  };
  return (
    <section>
      <header className="topbar">
        <h1>{practice ? "Practice" : "Question banks"}</h1>
        {!practice && (
          <button
            className="primary-button"
            disabled={!!editor}
            onClick={() => open("new")}
          >
            ＋ New bank
          </button>
        )}
      </header>
      <div className="bank-selector">
        <label>
          Question bank
          <select
            value={bank?.id ?? ""}
            disabled={!!editor}
            onChange={(e) => {
              setBid(e.target.value);
              setSelected("");
            }}
          >
            {snapshot.banks.map((b) => (
              <option key={b.id} value={b.id}>
                {b.title} · {b.questions.length} questions
              </option>
            ))}
          </select>
        </label>
        {!practice && bank && (
          <>
            <button
              className="outline-button"
              disabled={!!editor}
              onClick={() => open("rename")}
            >
              Rename
            </button>
            <button
              className="outline-button"
              onClick={() => safe("export", { bank_id: bank.id })}
            >
              Export ↓
            </button>
          </>
        )}
      </div>
      {snapshot.bankErrors.length > 0 && (
        <details className="inline-help">
          <summary>Unreadable bank files</summary>
          {snapshot.bankErrors.map((e) => (
            <p key={e}>{e}</p>
          ))}
        </details>
      )}
      {practice ? (
        <div className="practice-card">
          <span className="practice-symbol">◷</span>
          <h2>Reading & Writing</h2>
          <div className="module-grid">
            {[1, 2].map((n, i) => (
              <label key={n}>
                Module {n}
                <strong>
                  {bank?.questions.filter((q) => q.module === n).length ?? 0}{" "}
                  questions
                </strong>
                <span>Minutes</span>
                <input
                  type="number"
                  min="1"
                  max="180"
                  value={minutes[i]}
                  onChange={(e) =>
                    setMinutes((v) =>
                      v.map((m, j) => (j === i ? Number(e.target.value) : m)),
                    )
                  }
                />
              </label>
            ))}
          </div>
          <button
            className="primary-button"
            disabled={busy || !bank}
            onClick={() => safe("exam", { bank_id: bank.id, minutes })}
          >
            Start exam →
          </button>
          <p>
            The original exam window opens separately. No official adaptive
            scoring.
          </p>
        </div>
      ) : editor ? (
        <div className="inline-editor bank-editor">
          <header>
            <h2>
              {editor === "import"
                ? "Paste questions"
                : editor === "question"
                  ? draft.id
                    ? "Edit question"
                    : "Add question"
                  : editor === "new"
                    ? "New bank"
                    : "Rename bank"}
            </h2>
            <button
              aria-label="Close editor"
              disabled={saving}
              onClick={cancel}
            >
              ×
            </button>
          </header>
          {discard && (
            <div className="inline-help">
              Discard this unsaved edit?
              <button onClick={closeEditor}>Discard</button>
              <button onClick={() => setDiscard(false)}>Keep editing</button>
            </div>
          )}
          {editor !== "question" && (
            <label>
              {editor === "import"
                ? "New bank name (leave blank to append)"
                : "Bank name"}
              <input
                autoFocus
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  touch();
                }}
              />
            </label>
          )}
          {editor === "question" && (
            <>
              <div className="field-pair">
                <label>
                  Module
                  <select
                    value={draft.module}
                    onChange={(e) => {
                      setDraft((d) => ({
                        ...d,
                        module: Number(e.target.value),
                      }));
                      touch();
                    }}
                  >
                    <option value="1">1</option>
                    <option value="2">2</option>
                  </select>
                </label>
                <label>
                  Answer
                  <select
                    value={draft.answer}
                    onChange={(e) => {
                      setDraft((d) => ({ ...d, answer: e.target.value }));
                      touch();
                    }}
                  >
                    <option value="">Unknown</option>
                    {[..."ABCD"].map((k) => (
                      <option key={k}>{k}</option>
                    ))}
                  </select>
                </label>
              </div>
              {["passage", "question"].map((k) => (
                <label key={k}>
                  {k[0].toUpperCase() + k.slice(1)}
                  <textarea
                    value={draft[k as "passage" | "question"]}
                    onChange={(e) => {
                      setDraft((d) => ({ ...d, [k]: e.target.value }));
                      touch();
                    }}
                  />
                </label>
              ))}
              <div className="field-pair">
                {[..."ABCD"].map((k) => (
                  <label key={k}>
                    {k}
                    <textarea
                      value={draft.options[k]}
                      onChange={(e) => {
                        setDraft((d) => ({
                          ...d,
                          options: { ...d.options, [k]: e.target.value },
                        }));
                        touch();
                      }}
                    />
                  </label>
                ))}
              </div>
              <label>
                Explanation
                <textarea
                  value={draft.explanation}
                  onChange={(e) => {
                    setDraft((d) => ({ ...d, explanation: e.target.value }));
                    touch();
                  }}
                />
              </label>
            </>
          )}
          {editor === "import" && (
            <>
              <label>
                Format
                <select
                  value={format}
                  onChange={(e) => {
                    setFormat(e.target.value);
                    setPreview(undefined);
                    touch();
                  }}
                >
                  {["auto", "plain", "json", "csv", "tsv", "tagged"].map(
                    (f) => (
                      <option key={f}>{f}</option>
                    ),
                  )}
                </select>
              </label>
              <label>
                Question text
                <textarea
                  rows={10}
                  value={text}
                  placeholder={
                    "1. Which word means brief and clear?\nA. Concise\nB. Obsolete\nC. Ambiguous\nD. Contradictory\nAnswer: A"
                  }
                  onChange={(e) => {
                    setText(e.target.value);
                    setPreview(undefined);
                    touch();
                  }}
                />
              </label>
              <label>
                Or upload a text file
                <input
                  type="file"
                  accept=".txt,.json,.csv,.tsv"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    const generation = editorGeneration.current;
                    if (f && f.size <= 2000000) {
                      const content = await f.text();
                      if (generation === editorGeneration.current) {
                        setText(content);
                        setPreview(undefined);
                        touch();
                      }
                    }
                    e.target.value = "";
                  }}
                />
              </label>
              <details>
                <summary>Supported formats & corrections</summary>
                <pre>{snapshot.questionFormats}</pre>
              </details>
              <button
                className="outline-button"
                disabled={busy}
                onClick={async () => {
                  const generation = editorGeneration.current;
                  try {
                    const r = await call("preview", {
                      text,
                      format,
                      questions: true,
                    });
                    if (
                      generation === editorGeneration.current &&
                      previewInput.current.text === text &&
                      previewInput.current.format === format
                    ) {
                      setPreview(r.preview);
                      setCorrections(r.corrections ?? []);
                    }
                  } catch {}
                }}
              >
                Preview
              </button>
              {preview && (
                <div className="parse-preview">
                  <strong>{preview.questions.length} questions</strong>
                  {corrections.map((c, i) => (
                    <p key={i}>{c}</p>
                  ))}
                  {preview.questions.map((q: Question, i: number) => (
                    <p key={i}>
                      {i + 1}. {q.question}
                    </p>
                  ))}
                </div>
              )}
            </>
          )}
          <footer>
            <button className="outline-button" disabled={saving} onClick={cancel}>
              Cancel
            </button>
            <button
              className="primary-button"
              disabled={busy || (editor === "import" && !preview)}
              onClick={() => void save()}
            >
              Save
            </button>
          </footer>
        </div>
      ) : (
        <>
          <div className="bank-tools">
            <input
              placeholder="Search questions or passages"
              aria-label="Search questions"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button
              className="outline-button"
              disabled={!bank}
              onClick={() => open("question")}
            >
              ＋ Add question
            </button>
            <button className="outline-button" onClick={() => open("import")}>
              Paste questions
            </button>
          </div>
          <div className="question-layout">
            <div className="question-list">
              {bank?.questions
                .filter((q) =>
                  (q.question + q.passage)
                    .toLowerCase()
                    .includes(query.toLowerCase()),
                )
                .map((q) => (
                  <button
                    key={q.id}
                    className={selected === q.id ? "selected" : ""}
                    onClick={() => setSelected(q.id!)}
                  >
                    <span>Module {q.module}</span>
                    <strong>{q.question}</strong>
                  </button>
                ))}
            </div>
            <article className="question-detail">
              {(() => {
                const q = bank?.questions.find((q) => q.id === selected);
                return q ? (
                  <>
                    <button
                      className="outline-button"
                      onClick={() => open("question", q)}
                    >
                      Edit question
                    </button>
                    <p>{q.passage}</p>
                    <h2>{q.question}</h2>
                    {Object.entries(q.options).map(([k, v]) => (
                      <p className="question-option" key={k}>
                        <b>{k}</b>
                        {v}
                      </p>
                    ))}
                    <p>Answer: {q.answer || "Unknown"}</p>
                    <p>{q.explanation}</p>
                  </>
                ) : (
                  <div className="empty-hint">
                    Choose a question to read it here.
                  </div>
                );
              })()}
            </article>
          </div>
        </>
      )}
    </section>
  );
}
