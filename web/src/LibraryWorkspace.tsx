import { useEffect, useRef, useState } from "react";
import type { Book, Call, Group, Snapshot, Word } from "./Desktop";
import { mastery, status } from "./Desktop";
import {
  clipboardLabel,
  copyGroups,
  copyWords,
  copyToClipboard,
  isGroupClipboard,
} from "./clipboard";
import type {
  ClipboardMode,
  GroupContent,
  LibraryClipboard,
} from "./clipboard";

type View = { bid: string; gid: string };
const wordCount = (n: number) => `${n} ${n === 1 ? "word" : "words"}`;
type Draft = {
  key: string;
  kind: "book" | "group" | "word" | "paste";
  name: string;
  meaning: string;
  phonetic: string;
  expansion: string;
  sequence?: number;
  id?: string;
  text: string;
  format: string;
  preview?: Word[];
  notes?: string[];
  groupPreview?: GroupContent[];
  copied?: boolean;
  dirty: boolean;
  bid: string;
  gid: string;
};
type Drag = {
  kind: "group" | "word";
  source: string;
  ids: string[];
  x: number;
  y: number;
  startX: number;
  startY: number;
  active: boolean;
  copy: boolean;
  target?: { kind: string; id: string; pane: string };
  title: string;
  pointerId: number;
};
const blank = (kind: Draft["kind"], view: View): Draft => ({
  key: crypto.randomUUID(),
  kind,
  ...view,
  name: "",
  meaning: "",
  phonetic: "",
  expansion: "",
  text: "",
  format: "auto",
  dirty: false,
});

export default function LibraryWorkspace({
  snapshot,
  call,
  busy,
  arrange,
  setArrange,
  onStudy,
  onDirty,
  clipboard,
  setClipboard,
  clipboardMode,
  setClipboardMode,
}: {
  snapshot: Snapshot;
  call: Call;
  busy: boolean;
  arrange: boolean;
  setArrange: (v: boolean) => void;
  onStudy: (gid?: string, bid?: string, order?: string) => void;
  onDirty: (v: boolean) => void;
  clipboard: LibraryClipboard | null;
  setClipboard: (pack: LibraryClipboard) => void;
  clipboardMode: ClipboardMode;
  setClipboardMode: (mode: ClipboardMode) => void;
}) {
  const { state } = snapshot;
  const first = state.books[0]?.id ?? "";
  const [views, setViews] = useState<View[]>(() => [
    { bid: sessionStorage.getItem("desktop-open-book") || "", gid: "" },
    { bid: state.books[1]?.id ?? first, gid: "" },
  ]);
  const [drafts, setDrafts] = useState<(Draft | null)[]>([null, null]);
  const draftsRef = useRef(drafts);
  draftsRef.current = drafts;
  const [discard, setDiscard] = useState<number | null>(null);
  const [savingPane, setSavingPane] = useState<number | null>(null);
  const [selection, setSelection] = useState<string[][]>([[], []]);
  const [queries, setQueries] = useState(["", ""]);
  const [filters, setFilters] = useState(["all", "all"]);
  const [sorts, setSorts] = useState(["sequence", "sequence"]);
  const [descending, setDescending] = useState([false, false]);
  const [order, setOrder] = useState("Sequential");
  const [copy, setCopy] = useState(false);
  const drag = useRef<Drag | null>(null);
  const [ghost, setGhost] = useState<Drag | null>(null);
  const suppressClick = useRef(0);
  const anchor = useRef<string[]>(["", ""]);
  const [hint, setHint] = useState("");
  const [clipboardBusy, setClipboardBusy] = useState(false);
  const activePane = useRef(0);
  const callRef = useRef(call);
  callRef.current = call;
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const copyRef = useRef(copy);
  copyRef.current = copy;
  useEffect(() => {
    sessionStorage.removeItem("desktop-open-book");
  }, []);
  useEffect(() => {
    onDirty(drafts.some((d) => d?.dirty));
  }, [drafts, onDirty]);
  useEffect(() => () => onDirty(false), []);
  useEffect(() => {
    // Undo may remove freshly pasted items; do not keep ghost selections.
    setSelection((previous) => {
      const next = previous.map((ids, pane) => {
        const view = views[pane];
        const available = new Set(
          view.gid
            ? (state.groups.find((g) => g.id === view.gid)?.words ?? []).map(
                (w) => w.id,
              )
            : state.groups
                .filter((g) => g.book_id === view.bid)
                .map((g) => g.id),
        );
        return ids.filter((id) => available.has(id));
      });
      return next.every((ids, i) => ids.length === previous[i].length)
        ? previous
        : next;
    });
  }, [state.groups, views]);
  const updateView = (pane: number, view: View) => {
    if (drafts[pane]) {
      setHint("Save or cancel this pane's edit before navigating.");
      return;
    }
    setViews((v) => v.map((x, i) => (i === pane ? view : x)));
    setSelection((s) => s.map((x, i) => (i === pane ? [] : x)));
    setQueries((q) => q.map((x, i) => (i === pane ? "" : x)));
  };
  function open(
    pane: number,
    kind: Draft["kind"],
    record?: Word | Group | Book,
  ) {
    const view = views[pane];
    if (drafts[pane]) {
      setHint("Save or cancel this edit first.");
      return;
    }
    const d = blank(kind, view);
    if (record) {
      d.id = record.id;
      d.name = "term" in record ? record.term : record.name;
      if ("term" in record)
        Object.assign(d, {
          meaning: record.meaning,
          phonetic: record.phonetic,
          expansion: record.expansion,
          sequence: record.sequence,
        });
    }
    if (kind === "paste") {
      const compatible = clipboard && (!view.gid || "words" in clipboard);
      if (clipboardMode === "app" && compatible) {
        d.text = JSON.stringify(clipboard, null, 2);
        d.copied = true;
        d.dirty = true;
      }
    }
    setDrafts((ds) => ds.map((old, i) => (i === pane ? d : old)));
    setHint("");
    if (kind === "paste") {
      if (d.text) void previewPaste(pane, d);
      else if (clipboardMode === "system") void readSystem(pane, d);
    }
  }
  async function previewPaste(pane: number, draft: Draft) {
    try {
      const groups = isGroupClipboard(draft.text);
      if (groups && draft.gid) {
        setHint(
          "This clipboard contains whole groups. Open a book to paste them.",
        );
        return;
      }
      const result = await call(groups ? "preview_groups" : "preview", {
        text: draft.text,
        format: draft.format,
        book_id: draft.bid,
      });
      setDrafts((ds) =>
        ds.map((d, i) =>
          i === pane &&
          d &&
          d.key === draft.key &&
          d.text === draft.text &&
          d.format === draft.format
            ? {
                ...d,
                preview: result.preview,
                groupPreview: result.group_preview,
                notes: result.corrections,
              }
            : d,
        ),
      );
    } catch {
      /* Validation errors are displayed without losing the pasted text. */
    }
  }
  async function readSystem(pane: number, draft: Draft) {
    if (draft.text.trim()) {
      setHint(
        "Clear the text first before replacing it from the system clipboard.",
      );
      return;
    }
    setClipboardBusy(true);
    try {
      const text = await navigator.clipboard.readText();
      if (new TextEncoder().encode(text).length > 2000000) {
        setHint(
          "Clipboard limit: 2 MB. Copy a smaller set of groups or words.",
        );
        return;
      }
      if (
        draftsRef.current[pane]?.key !== draft.key ||
        draftsRef.current[pane]?.text !== draft.text
      ) {
        setHint(
          "The editor changed while reading the clipboard. Your edits were kept.",
        );
        return;
      }
      const next = {
        ...draft,
        text,
        copied: isGroupClipboard(text),
        dirty: true,
        preview: undefined,
        groupPreview: undefined,
      };
      setDrafts((ds) => ds.map((d, i) => (i === pane ? next : d)));
      setClipboardMode("system");
      await previewPaste(pane, next);
    } catch {
      setHint(
        "System clipboard could not be read. Click the text box and use Ctrl+V instead.",
      );
    } finally {
      setClipboardBusy(false);
    }
  }
  function useAppClipboard(pane: number, draft: Draft) {
    if (!clipboard) {
      setHint(
        "The in-app clipboard is empty. Select a group and copy it first.",
      );
      return;
    }
    if (draft.text.trim()) {
      setHint(
        "Clear the text first before replacing it from the in-app clipboard.",
      );
      return;
    }
    const next = {
      ...draft,
      text: JSON.stringify(clipboard, null, 2),
      copied: true,
      dirty: true,
    };
    setDrafts((ds) => ds.map((d, i) => (i === pane ? next : d)));
    setClipboardMode("app");
    void previewPaste(pane, next);
  }
  async function copySelection(pane: number, mode: ClipboardMode) {
    const view = views[pane];
    const group = state.groups.find((g) => g.id === view.gid);
    const selected = selection[pane];
    const groups = group
      ? [group]
      : state.groups.filter(
          (g) => g.book_id === view.bid && selected.includes(g.id),
        );
    const words = group?.words.filter((w) => selected.includes(w.id)) ?? [];
    if (!groups.length && !words.length) {
      setHint("Select at least one group to copy.");
      return;
    }
    const pack = words.length ? copyWords(words) : copyGroups(groups);
    setClipboardBusy(true);
    try {
      await copyToClipboard(pack, mode, setClipboard, (text) =>
        navigator.clipboard.writeText(text),
      );
      setClipboardMode(mode);
      setHint(
        `Copied ${clipboardLabel(pack)} ${mode === "app" ? "in-app. Your system clipboard was not changed." : "to the system clipboard. Transfer this text to another device and paste it there."}`,
      );
    } catch {
      setHint(
        "System clipboard access was denied. Your in-app copy was not changed; use Copy in-app instead.",
      );
    } finally {
      setClipboardBusy(false);
    }
  }
  function changeDraft(pane: number, values: Partial<Draft>) {
    setDrafts((ds) =>
      ds.map((d, i) =>
        i === pane && d
          ? {
              ...d,
              ...values,
              ...("text" in values || "format" in values
                ? { preview: undefined, groupPreview: undefined }
                : {}),
              dirty: true,
            }
          : d,
      ),
    );
  }
  function cancel(pane: number) {
    if (savingPane === pane) return;
    // Cancel and × dismiss a paste directly. The old confirmation appeared above
    // the scrolled preview, making both controls look unresponsive.
    if (drafts[pane]?.dirty && drafts[pane]?.kind !== "paste") {
      setDiscard(pane);
      return;
    }
    closeDraft(pane);
  }
  function closeDraft(pane: number) {
    const next = draftsRef.current.map((d, i) => (i === pane ? null : d));
    // Invalidate the draft immediately, including a pending clipboard read.
    draftsRef.current = next;
    setDrafts(next);
    setDiscard(null);
    setHint("");
  }
  async function save(pane: number) {
    const d = drafts[pane];
    if (!d) return;
    if (
      d.kind === "paste" &&
      !(isGroupClipboard(d.text) ? d.groupPreview : d.preview)
    )
      return;
    if (
      d.kind === "paste" &&
      !isGroupClipboard(d.text) &&
      !d.gid &&
      !d.name.trim()
    ) {
      setHint("Enter a name for the new group.");
      return;
    }
    setSavingPane(pane);
    try {
      const groupPaste = d.kind === "paste" && isGroupClipboard(d.text);
      const result = await call(
        groupPaste ? "paste_groups" : d.kind === "paste" ? "import" : d.kind,
        {
          id: d.id,
          name: d.name,
          book_id: d.bid,
          group_id: d.gid,
          word: {
            term: d.name,
            meaning: d.meaning,
            phonetic: d.phonetic,
            expansion: d.expansion,
            ...(d.sequence ? { sequence: d.sequence } : {}),
          },
          text: d.text,
          format: d.format,
        },
      );
      setDrafts((ds) => ds.map((old, i) => (i === pane ? null : old)));
      if (groupPaste)
        setSelection((all) =>
          all.map((ids, i) => (i === pane ? (result.group_ids ?? []) : ids)),
        );
      if (d.kind === "book" && !d.id)
        setViews((v) =>
          v.map((x, i) => (i === pane ? { bid: result.id!, gid: "" } : x)),
        );
      if (
        (d.kind === "group" && !d.id) ||
        (d.kind === "paste" && !groupPaste && d.name.trim())
      )
        setViews((v) =>
          v.map((x, i) => (i === pane ? { bid: d.bid, gid: result.id! } : x)),
        );
    } catch {
      /* leave draft in place */
    } finally {
      setSavingPane(null);
    }
  }
  function choose(
    pane: number,
    id: string,
    ids: string[],
    ctrl: boolean,
    shift: boolean,
  ) {
    setSelection((all) =>
      all.map((selected, i) => {
        if (i !== pane) return selected;
        if (shift && ids.includes(anchor.current[pane])) {
          const a = ids.indexOf(anchor.current[pane]),
            b = ids.indexOf(id);
          return ids.slice(Math.min(a, b), Math.max(a, b) + 1);
        }
        anchor.current[pane] = id;
        return ctrl
          ? selected.includes(id)
            ? selected.filter((x) => x !== id)
            : [...selected, id]
          : [id];
      }),
    );
  }
  function down(
    e: React.PointerEvent,
    pane: number,
    kind: "group" | "word",
    source: string,
    id: string,
    title: string,
  ) {
    if (
      !arrange ||
      busy ||
      e.button !== 0 ||
      (e.target as HTMLElement).closest("button,input,select,textarea,a")
    )
      return;
    const ids = selection[pane].includes(id) ? selection[pane] : [id];
    if (!selection[pane].includes(id) && !e.ctrlKey && !e.shiftKey)
      setSelection((s) => s.map((x, i) => (i === pane ? ids : x)));
    drag.current = {
      kind,
      source,
      ids,
      x: e.clientX,
      y: e.clientY,
      startX: e.clientX,
      startY: e.clientY,
      active: false,
      copy: e.ctrlKey || copy,
      target: undefined,
      title: ids.length > 1 ? `${ids.length} ${kind}s` : title,
      pointerId: e.pointerId,
    };
  }
  useEffect(() => {
    function targetAt(x: number, y: number, d: Drag) {
      let el = document.elementFromPoint(x, y) as HTMLElement | null;
      while (el) {
        if (
          el.dataset.dropKind === (d.kind === "group" ? "book" : "group") &&
          el.dataset.dropId &&
          el.dataset.dropId !== d.source
        )
          return {
            kind: el.dataset.dropKind,
            id: el.dataset.dropId,
            pane: el.dataset.pane!,
          };
        el = el.parentElement;
      }
    }
    let raf = 0;
    const paint = () => {
      const d = drag.current;
      if (!d?.active) return;
      const scroll = document
        .elementFromPoint(d.x, d.y)
        ?.closest(".pane-scroll") as HTMLElement | null;
      if (scroll) {
        const r = scroll.getBoundingClientRect();
        const delta = d.y < r.top + 55 ? -12 : d.y > r.bottom - 55 ? 12 : 0;
        if (delta) scroll.scrollTop += delta;
      }
      const target = targetAt(d.x, d.y, d);
      if (JSON.stringify(target) !== JSON.stringify(d.target)) {
        d.target = target;
        setGhost({ ...d });
      }
      raf = requestAnimationFrame(paint);
    };
    const move = (e: PointerEvent) => {
      const d = drag.current;
      if (!d || e.pointerId !== d.pointerId) return;
      if (
        !d.active &&
        Math.hypot(e.clientX - d.startX, e.clientY - d.startY) < 7
      )
        return;
      e.preventDefault();
      if (!d.active) {
        d.active = true;
        document.body.classList.add("is-arranging");
        raf = requestAnimationFrame(paint);
      }
      Object.assign(d, {
        x: e.clientX,
        y: e.clientY,
        copy: e.ctrlKey || copyRef.current,
      });
      d.target = targetAt(d.x, d.y, d);
      setGhost({ ...d });
    };
    const stop = () => {
      drag.current = null;
      setGhost(null);
      cancelAnimationFrame(raf);
      document.body.classList.remove("is-arranging");
    };
    const up = (e: PointerEvent) => {
      const d = drag.current;
      if (!d || e.pointerId !== d.pointerId) return;
      if (d.active) {
        suppressClick.current = Date.now() + 300;
        const target = targetAt(e.clientX, e.clientY, d);
        if (target && !busyRef.current) {
          void callRef
            .current("transfer", {
              kind: d.kind,
              source: d.source,
              target: target.id,
              ids: d.ids,
              copy: e.ctrlKey || copyRef.current,
            })
            .then(() => {
              setSelection([[], []]);
              setHint("");
            })
            .catch(() => {});
        } else
          setHint(
            "Nothing changed. Drop groups into another book, or words into another group.",
          );
      }
      stop();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape" && drag.current) {
        e.preventDefault();
        stop();
        setHint("Drag cancelled. Nothing changed.");
      }
    };
    window.addEventListener("pointermove", move, { passive: false });
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", stop);
    window.addEventListener("blur", stop);
    window.addEventListener("keydown", key);
    return () => {
      stop();
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", stop);
      window.removeEventListener("blur", stop);
      window.removeEventListener("keydown", key);
    };
  }, []);
  useEffect(() => {
    const undo = (e: KeyboardEvent) => {
      if (
        arrange &&
        e.ctrlKey &&
        e.key === "z" &&
        !drafts.some(Boolean) &&
        snapshot.canUndo
      ) {
        e.preventDefault();
        void call("undo").catch(() => {});
      }
    };
    window.addEventListener("keydown", undo);
    return () => window.removeEventListener("keydown", undo);
  }, [arrange, drafts, snapshot.canUndo, call]);
  const isTarget = (pane: number, kind: string, id: string) =>
    ghost?.target?.pane === String(pane) &&
    ghost.target.kind === kind &&
    ghost.target.id === id;
  const safe = (action: string, args?: Record<string, any>) =>
    void call(action, args).catch(() => {});
  const toggleArrange = () => {
    if (drafts.some(Boolean)) {
      setHint("Save or cancel your edit before changing the layout.");
      return;
    }
    setArrange(!arrange);
    setSelection([[], []]);
    if (!arrange)
      setViews((v) => [{ bid: v[0].bid || first, gid: v[0].gid }, v[1]]);
  };
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (
        !(event.ctrlKey || event.metaKey) ||
        event.altKey ||
        busy ||
        clipboardBusy ||
        drafts.some(Boolean) ||
        target.closest(
          "textarea,select,[contenteditable=true],input:not([type=checkbox]):not([type=radio])",
        ) ||
        window.getSelection()?.toString()
      )
        return;
      const pane = arrange ? activePane.current : 0;
      if (
        event.key.toLowerCase() === "c" &&
        (selection[pane].length || views[pane].gid)
      ) {
        event.preventDefault();
        void copySelection(pane, clipboardMode);
      } else if (event.key.toLowerCase() === "v" && views[pane].bid) {
        event.preventDefault();
        open(pane, "paste");
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [
    arrange,
    busy,
    clipboardBusy,
    drafts,
    selection,
    views,
    clipboardMode,
    clipboard,
  ]);
  return (
    <section className="library-workspace">
      <header className="topbar">
        <div>
          <p className="eyebrow">VOCABULARY</p>
          <h1>{arrange ? "Organize books & groups" : "Word library"}</h1>
        </div>
        <button
          className={`outline-button ${arrange ? "active" : ""}`}
          aria-pressed={arrange}
          onClick={toggleArrange}
        >
          {arrange ? "Back to word library" : "Organize books & groups"}
        </button>
      </header>
      <div className="clipboard-toolbar">
        <span>Clipboard</span>
        <div className="segmented" aria-label="Clipboard mode">
          <button
            aria-pressed={clipboardMode === "app"}
            className={clipboardMode === "app" ? "active" : ""}
            onClick={() => setClipboardMode("app")}
          >
            In-app
          </button>
          <button
            aria-pressed={clipboardMode === "system"}
            className={clipboardMode === "system" ? "active" : ""}
            onClick={() => setClipboardMode("system")}
          >
            System / share
          </button>
        </div>
        <span className="clipboard-summary">
          {clipboardMode === "app"
            ? clipboard
              ? `${clipboardLabel(clipboard)} ready`
              : "Keeps your system clipboard untouched"
            : "Copy replaces the system clipboard"}
        </span>
      </div>
      {arrange && (
        <div className="arrange-toolbar">
          <span className="drag-tip">
            <span aria-hidden="true">⠿</span> Build study plans: move or copy
            between books
          </span>
          <div className="segmented" aria-label="Transfer mode">
            <button
              aria-pressed={!copy}
              className={!copy ? "active" : ""}
              onClick={() => setCopy(false)}
            >
              Move
            </button>
            <button
              aria-pressed={copy}
              className={copy ? "active" : ""}
              onClick={() => setCopy(true)}
            >
              Copy
            </button>
          </div>
          <span className="ctrl-tip">Ctrl-drag to copy</span>
          <button
            className="undo-button"
            disabled={!snapshot.canUndo || busy}
            onClick={() => safe("undo")}
          >
            ↶ Undo
          </button>
        </div>
      )}
      {hint && (
        <div className="inline-help">
          {hint}
          <button onClick={() => setHint("")}>×</button>
        </div>
      )}
      <div className={`library-panes ${arrange ? "paired" : ""}`}>
        {views.slice(0, arrange ? 2 : 1).map((view, pane) => {
          const book = state.books.find((b) => b.id === view.bid);
          const group = state.groups.find(
            (g) => g.id === view.gid && g.book_id === book?.id,
          );
          const members = state.groups.filter((g) => g.book_id === book?.id);
          const draft = drafts[pane];
          const query = queries[pane].toLowerCase();
          const words =
            group?.words
              .filter(
                (w) =>
                  `${w.term} ${w.meaning} ${w.phonetic} ${w.expansion}`
                    .toLowerCase()
                    .includes(query) &&
                  (filters[pane] === "all" ||
                    (filters[pane] === "mastered"
                      ? w.streak >= 3
                      : filters[pane] === "new"
                        ? !w.encounters
                        : w.encounters > 0 && w.streak < 3)),
              )
              .slice()
              .sort((a, b) => {
                const metric = (w: Word) =>
                  sorts[pane] === "errors"
                    ? w.forgotten
                    : sorts[pane] === "errorRate"
                      ? w.forgotten / Math.max(1, w.remembered + w.forgotten)
                      : sorts[pane] === "seen"
                        ? w.encounters
                        : w.sequence;
                return (metric(a) - metric(b)) * (descending[pane] ? -1 : 1);
              }) ?? [];
          const shownGroups = members.filter((g) =>
            g.name.toLowerCase().includes(query),
          );
          const kind = group ? "group" : "book",
            dropId = group?.id ?? book?.id ?? "";
          const draftField = (
            key: "name" | "meaning" | "phonetic" | "expansion",
            label: string,
            multi = false,
          ) => (
            <label>
              {label}
              {multi ? (
                <textarea
                  rows={3}
                  value={draft![key]}
                  onChange={(e) => changeDraft(pane, { [key]: e.target.value })}
                />
              ) : (
                <input
                  autoFocus={key === "name"}
                  value={draft![key]}
                  onChange={(e) => changeDraft(pane, { [key]: e.target.value })}
                />
              )}
            </label>
          );
          return (
            <section
              className={`library-pane ${isTarget(pane, kind, dropId) ? "drop-ready" : ""}`}
              key={pane}
              aria-label={pane ? "Right library" : "Left library"}
              onPointerDownCapture={() => {
                activePane.current = pane;
              }}
              onFocusCapture={() => {
                activePane.current = pane;
              }}
            >
              <header className="pane-heading">
                <div className="breadcrumbs">
                  <button
                    disabled={!!draft}
                    onClick={() => updateView(pane, { bid: "", gid: "" })}
                  >
                    Books
                  </button>
                  {book && (
                    <>
                      <span>/</span>
                      <button
                        disabled={!!draft}
                        onClick={() =>
                          updateView(pane, { bid: book.id, gid: "" })
                        }
                      >
                        {book.name}
                      </button>
                    </>
                  )}
                  {group && (
                    <>
                      <span>/</span>
                      <strong>{group.name}</strong>
                    </>
                  )}
                </div>
                {arrange && <span className="pane-number">0{pane + 1}</span>}
              </header>
              {arrange && (
                <div className="pane-pickers">
                  <select
                    aria-label={`${pane ? "Right" : "Left"} book`}
                    disabled={!!draft}
                    value={book?.id ?? ""}
                    onChange={(e) =>
                      updateView(pane, { bid: e.target.value, gid: "" })
                    }
                  >
                    <option value="">All books</option>
                    {state.books.map((b) => (
                      <option value={b.id} key={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                  {book && (
                    <select
                      aria-label={`${pane ? "Right" : "Left"} group`}
                      disabled={!!draft}
                      value={group?.id ?? ""}
                      onChange={(e) =>
                        updateView(pane, { bid: book.id, gid: e.target.value })
                      }
                    >
                      <option value="">All groups</option>
                      {members.map((g) => (
                        <option value={g.id} key={g.id}>
                          {g.name}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )}
              <div className="pane-title">
                <div>
                  <h2>{group?.name ?? book?.name ?? "Your word books"}</h2>
                  <p>
                    {group
                      ? `${wordCount(group.words.length)} · ${mastery(group.words)}% mastered`
                      : book
                        ? `${members.length} groups · ${members.reduce((n, g) => n + g.words.length, 0)} words`
                        : `${state.books.length} books`}
                  </p>
                </div>
                {book && !draft && (
                  <button
                    className="quiet-button"
                    onClick={() =>
                      open(pane, group ? "group" : "book", group ?? book)
                    }
                  >
                    Rename
                  </button>
                )}
              </div>
              <div className="pane-actions">
                {!group && (
                  <button
                    disabled={!!draft || busy}
                    className="dark-button"
                    onClick={() => open(pane, book ? "group" : "book")}
                  >
                    ＋ {book ? "Group" : "Book"}
                  </button>
                )}
                {book && (
                  <button
                    disabled={!!draft || busy}
                    className={group ? "dark-button" : "outline-button"}
                    onClick={() => open(pane, "paste")}
                  >
                    Paste {group ? "words" : "group"}
                  </button>
                )}
                {arrange && book && (
                  <button
                    disabled={!!draft}
                    className="quiet-button"
                    onClick={() => open(pane, "book")}
                  >
                    New book
                  </button>
                )}
                {group && (
                  <button
                    className="quiet-button"
                    onClick={() => safe("export", { group_id: group.id })}
                  >
                    Export ↓
                  </button>
                )}
              </div>
              {book && !draft && (
                <div className="selection-actions">
                  <span>
                    {selection[pane].length
                      ? `${selection[pane].length} selected`
                      : group
                        ? "Whole group"
                        : "Select groups to copy"}
                  </span>
                  <button
                    className="outline-button"
                    disabled={
                      busy ||
                      clipboardBusy ||
                      (!group && !selection[pane].length)
                    }
                    title={
                      clipboardMode === "app"
                        ? "Ctrl+C · Does not touch the system clipboard"
                        : "Ctrl+C · Replaces the system clipboard"
                    }
                    onClick={() => void copySelection(pane, clipboardMode)}
                  >
                    Copy {group && selection[pane].length ? "words" : "groups"}{" "}
                    {clipboardMode === "app" ? "in-app" : "to system"}
                  </button>
                  <button
                    className="quiet-button"
                    disabled={
                      busy ||
                      clipboardBusy ||
                      (!group && !selection[pane].length)
                    }
                    title={
                      clipboardMode === "app"
                        ? "Replaces the system clipboard with portable text"
                        : "Leaves the system clipboard unchanged"
                    }
                    onClick={() =>
                      void copySelection(
                        pane,
                        clipboardMode === "app" ? "system" : "app",
                      )
                    }
                  >
                    {clipboardMode === "app" ? "Copy to system" : "Copy in-app"}
                  </button>
                </div>
              )}
              {draft && (
                <form
                  className="inline-editor"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void save(pane);
                  }}
                >
                  <header>
                    <h3>
                      {draft.id
                        ? "Edit"
                        : draft.kind === "paste"
                          ? "Paste"
                          : "New"}{" "}
                      {draft.kind === "paste"
                        ? draft.gid
                          ? "words"
                          : "group"
                        : draft.kind}
                    </h3>
                    <button
                      type="button"
                      aria-label="Close editor"
                      disabled={savingPane === pane}
                      onClick={() => cancel(pane)}
                    >
                      ×
                    </button>
                  </header>
                  <p className="editor-destination">
                    {draft.kind === "book"
                      ? "Word library"
                      : `${book?.name}${draft.gid && group ? ` / ${group.name}` : ""}`}
                  </p>
                  {discard === pane && (
                    <div className="inline-help">
                      Discard unsaved changes?
                      <button type="button" onClick={() => closeDraft(pane)}>
                        Discard
                      </button>
                      <button type="button" onClick={() => setDiscard(null)}>
                        Keep editing
                      </button>
                    </div>
                  )}
                  {draft.kind !== "paste"
                    ? draftField(
                        "name",
                        draft.kind === "word" ? "Word" : "Name",
                      )
                    : !draft.gid &&
                      !isGroupClipboard(draft.text) &&
                      draftField("name", "Group name")}
                  {draft.kind === "word" && (
                    <>
                      {draftField("meaning", "Meaning", true)}
                      {draftField("phonetic", "Pronunciation")}
                      {draftField(
                        "expansion",
                        "Expansion / notes / examples",
                        true,
                      )}
                    </>
                  )}
                  {draft.kind === "paste" && (
                    <>
                      <div className="paste-source-buttons">
                        <button
                          type="button"
                          className="outline-button"
                          disabled={!clipboard || busy || clipboardBusy}
                          onClick={() => useAppClipboard(pane, draft)}
                        >
                          Use in-app copy
                        </button>
                        <button
                          type="button"
                          className="outline-button"
                          disabled={busy || clipboardBusy}
                          onClick={() => void readSystem(pane, draft)}
                        >
                          Read system clipboard
                        </button>
                      </div>
                      {draft.copied ? (
                        <div className="clipboard-loaded">
                          <strong>
                            Copied{" "}
                            {isGroupClipboard(draft.text) ? "groups" : "words"}{" "}
                            ready to paste
                          </strong>
                          <p>
                            Content is copied; learning progress starts fresh.
                            Existing items are kept.
                          </p>
                          <button
                            type="button"
                            className="quiet-button"
                            onClick={() => changeDraft(pane, { copied: false })}
                          >
                            Edit as text
                          </button>
                        </div>
                      ) : (
                        <>
                          <p className="paste-fields-help">
                            No numbering needed. Use <b>word: meaning</b> for a
                            short entry, or include pronunciation and notes
                            below. Blank optional fields are allowed.
                          </p>
                          <label>
                            Format
                            <select
                              value={draft.format}
                              onChange={(e) =>
                                changeDraft(pane, {
                                  format: e.target.value,
                                  preview: undefined,
                                })
                              }
                            >
                              {[
                                "auto",
                                "plain",
                                "pairs",
                                "json",
                                "csv",
                                "tsv",
                                "pipe",
                              ].map((f) => (
                                <option key={f}>{f}</option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Words
                            <textarea
                              rows={7}
                              placeholder={
                                "concise | /kənˈsaɪs/ | brief and clear | a concise explanation\nlucid | /ˈluːsɪd/ | clear and easy to understand | lucid prose"
                              }
                              value={draft.text}
                              onChange={(e) =>
                                changeDraft(pane, {
                                  text: e.target.value,
                                  preview: undefined,
                                })
                              }
                            />
                          </label>
                          <p className="field-order">
                            word | pronunciation | meaning | expansion / notes
                          </p>
                          <label>
                            Upload text file
                            <input
                              type="file"
                              accept=".txt,.json,.csv,.tsv"
                              onChange={async (e) => {
                                const f = e.target.files?.[0];
                                if (f) {
                                  if (f.size > 2000000)
                                    setHint("Import limit: 2 MB.");
                                  else {
                                    const content = await f.text();
                                    if (draftsRef.current[pane]?.key === draft.key)
                                      changeDraft(pane, {
                                        text: content,
                                        preview: undefined,
                                      });
                                  }
                                }
                                e.target.value = "";
                              }}
                            />
                          </label>
                          <details>
                            <summary>Formats & automatic corrections</summary>
                            <pre>{snapshot.wordFormats}</pre>
                          </details>
                        </>
                      )}
                      <button
                        type="button"
                        className="outline-button"
                        disabled={busy}
                        onClick={() => void previewPaste(pane, draft)}
                      >
                        Preview
                      </button>
                      {draft.preview && (
                        <div className="parse-preview">
                          <strong>{wordCount(draft.preview.length)}</strong>
                          {!!draft.notes?.length && (
                            <details>
                              <summary>
                                {draft.notes.length} automatic format
                                corrections
                              </summary>
                              {draft.notes.map((n, i) => (
                                <p key={i}>{n}</p>
                              ))}
                            </details>
                          )}
                          {draft.preview.map((w, i) => (
                            <div className="preview-word" key={i}>
                              <b>{w.term}</b>
                              {w.phonetic && <small>{w.phonetic}</small>}
                              <p>{w.meaning}</p>
                              {w.expansion && (
                                <p className="word-notes">{w.expansion}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                      {draft.groupPreview && (
                        <div className="parse-preview">
                          <strong>
                            {draft.groupPreview.length}{" "}
                            {draft.groupPreview.length === 1
                              ? "group"
                              : "groups"}{" "}
                            → {book?.name}
                          </strong>
                          <p>
                            These names will be used. Name conflicts get a
                            “copy” suffix.
                          </p>
                          {draft.groupPreview.map((g, i) => (
                            <details
                              key={i}
                              open={draft.groupPreview!.length === 1}
                            >
                              <summary>
                                {g.name} · {wordCount(g.words.length)}
                              </summary>
                              {g.words.map((w, j) => (
                                <div className="preview-word" key={j}>
                                  <b>{w.term}</b>
                                  {w.phonetic && <small>{w.phonetic}</small>}
                                  <p>{w.meaning}</p>
                                  {w.expansion && (
                                    <p className="word-notes">{w.expansion}</p>
                                  )}
                                </div>
                              ))}
                            </details>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                  <footer>
                    <button
                      type="button"
                      className="outline-button"
                      disabled={savingPane === pane}
                      onClick={() => cancel(pane)}
                    >
                      Cancel
                    </button>
                    <button
                      className="primary-button"
                      disabled={
                        busy ||
                        clipboardBusy ||
                        (draft.kind === "paste" &&
                          !(isGroupClipboard(draft.text)
                            ? draft.groupPreview
                            : draft.preview))
                      }
                    >
                      {draft.groupPreview
                        ? `Paste ${draft.groupPreview.length} ${draft.groupPreview.length === 1 ? "group" : "groups"}`
                        : `Save ${draft.kind === "paste" ? "words" : draft.kind}`}
                    </button>
                  </footer>
                </form>
              )}
              <div className="pane-filter">
                <input
                  aria-label={`${pane ? "Right" : "Left"} search`}
                  placeholder={
                    group ? "Search words, meanings or notes" : "Search library"
                  }
                  value={queries[pane]}
                  onChange={(e) =>
                    setQueries((v) =>
                      v.map((q, i) => (i === pane ? e.target.value : q)),
                    )
                  }
                />
                {group && (
                  <select
                    aria-label={`${pane ? "Right" : "Left"} learning status`}
                    value={filters[pane]}
                    onChange={(e) =>
                      setFilters((v) =>
                        v.map((f, i) => (i === pane ? e.target.value : f)),
                      )
                    }
                  >
                    <option value="all">All statuses</option>
                    <option value="new">New</option>
                    <option value="learning">Learning</option>
                    <option value="mastered">Mastered</option>
                  </select>
                )}
              </div>
              {group && (
                <div className="pane-sort">
                  <span>Sort</span>
                  {[
                    ["sequence", "Order"],
                    ["errors", "Errors"],
                    ["errorRate", "Error rate"],
                    ["seen", "Seen"],
                  ].map(([key, label]) => (
                    <button
                      key={key}
                      className={sorts[pane] === key ? "active" : ""}
                      onClick={() => {
                        if (sorts[pane] === key)
                          setDescending((v) =>
                            v.map((x, i) => (i === pane ? !x : x)),
                          );
                        else {
                          setSorts((v) =>
                            v.map((x, i) => (i === pane ? key : x)),
                          );
                          setDescending((v) =>
                            v.map((x, i) =>
                              i === pane ? key !== "sequence" : x,
                            ),
                          );
                        }
                      }}
                    >
                      {label}
                      {sorts[pane] === key
                        ? descending[pane]
                          ? " ↓"
                          : " ↑"
                        : ""}
                    </button>
                  ))}
                </div>
              )}
              <div
                className={`pane-scroll ${group ? "word-stack" : "container-grid"}`}
                data-drop-kind={kind}
                data-drop-id={dropId}
                data-pane={pane}
              >
                {!book &&
                  state.books
                    .filter((b) => b.name.toLowerCase().includes(query))
                    .map((b, i) => {
                      const gs = state.groups.filter((g) => g.book_id === b.id);
                      return (
                        <button
                          key={b.id}
                          data-drop-kind="book"
                          data-drop-id={b.id}
                          data-pane={pane}
                          className={`book-card ${isTarget(pane, "book", b.id) ? "drop-ready" : ""}`}
                          onClick={() =>
                            updateView(pane, { bid: b.id, gid: "" })
                          }
                        >
                          <div className={`book-spine tone-${i % 3}`}>
                            <span>{b.name.slice(0, 1)}</span>
                          </div>
                          <div>
                            <h3>{b.name}</h3>
                            <p>
                              {gs.length} groups ·{" "}
                              {gs.reduce((n, g) => n + g.words.length, 0)} words
                            </p>
                          </div>
                          <span className="card-arrow">↗</span>
                        </button>
                      );
                    })}
                {book &&
                  !group &&
                  shownGroups.map((g, i) => (
                    <article
                      key={g.id}
                      data-drop-kind="group"
                      data-drop-id={g.id}
                      data-pane={pane}
                      className={`group-tile ${selection[pane].includes(g.id) ? "selected" : ""} ${isTarget(pane, "group", g.id) ? "drop-ready" : ""}`}
                      onPointerDown={(e) =>
                        down(e, pane, "group", book.id, g.id, g.name)
                      }
                      onClick={(e) => {
                        if (Date.now() < suppressClick.current) return;
                        choose(
                          pane,
                          g.id,
                          shownGroups.map((g) => g.id),
                          e.ctrlKey,
                          e.shiftKey,
                        );
                      }}
                      onDoubleClick={() =>
                        updateView(pane, { bid: book.id, gid: g.id })
                      }
                    >
                      <div className="tile-top">
                        {
                          <input
                            type="checkbox"
                            aria-label={`Select ${g.name}`}
                            checked={selection[pane].includes(g.id)}
                            onClick={(e) => e.stopPropagation()}
                            onChange={() =>
                              choose(
                                pane,
                                g.id,
                                shownGroups.map((g) => g.id),
                                true,
                                false,
                              )
                            }
                          />
                        }
                        <span className="status-label">{status(state, g)}</span>
                        {arrange && (
                          <span className="drag-handle" title="Drag group">
                            ⠿
                          </span>
                        )}
                      </div>
                      <button
                        className="tile-title"
                        onClick={(e) => {
                          e.stopPropagation();
                          updateView(pane, { bid: book.id, gid: g.id });
                        }}
                      >
                        {g.name} <span>↗</span>
                      </button>
                      <p>{wordCount(g.words.length)}</p>
                      <div className="tile-meter">
                        <i style={{ width: `${mastery(g.words)}%` }} />
                      </div>
                      <footer>
                        <span>{mastery(g.words)}% mastered</span>
                        <button
                          disabled={!g.words.length || !!draft || busy}
                          onClick={(e) => {
                            e.stopPropagation();
                            onStudy(g.id, undefined, order);
                          }}
                        >
                          Study →
                        </button>
                      </footer>
                    </article>
                  ))}
                {group &&
                  words.map((w, i) => (
                    <article
                      key={w.id}
                      className={`arrange-word ${selection[pane].includes(w.id) ? "selected" : ""}`}
                      onPointerDown={(e) =>
                        down(e, pane, "word", group.id, w.id, w.term)
                      }
                      onClick={(e) => {
                        if (Date.now() < suppressClick.current) return;
                        choose(
                          pane,
                          w.id,
                          words.map((w) => w.id),
                          e.ctrlKey,
                          e.shiftKey,
                        );
                      }}
                    >
                      {
                        <input
                          type="checkbox"
                          aria-label={`Select ${w.term}`}
                          checked={selection[pane].includes(w.id)}
                          onClick={(e) => e.stopPropagation()}
                          onChange={() =>
                            choose(
                              pane,
                              w.id,
                              words.map((w) => w.id),
                              true,
                              false,
                            )
                          }
                        />
                      }
                      <div className="arrange-word-content">
                        <div>
                          <strong>{w.term}</strong>
                          {w.phonetic && <small>{w.phonetic}</small>}
                        </div>
                        <p>{w.meaning}</p>
                        {w.expansion && (
                          <small className="word-notes">{w.expansion}</small>
                        )}
                        <div className="word-statline">
                          <span
                            className={`status-badge ${w.streak >= 3 ? "mastered" : w.encounters ? "learning" : "new"}`}
                          >
                            {w.streak >= 3
                              ? "Mastered"
                              : w.encounters
                                ? "Learning"
                                : "New"}
                          </span>
                          <span>
                            {w.forgotten} errors · {w.encounters} seen ·{" "}
                            {w.remembered + w.forgotten
                              ? Math.round(
                                  (w.forgotten / (w.remembered + w.forgotten)) *
                                    100,
                                ) + "%"
                              : "—"}{" "}
                            error rate
                          </span>
                        </div>
                      </div>
                      <button
                        className="word-edit-button"
                        disabled={!!draft}
                        onClick={(e) => {
                          e.stopPropagation();
                          open(pane, "word", w);
                        }}
                      >
                        Edit
                      </button>
                      {arrange && <span className="drag-handle">⠿</span>}
                    </article>
                  ))}
                {book && !(group ? words.length : shownGroups.length) && (
                  <div className="drop-empty">
                    <span>{group ? "Aa" : "▱"}</span>
                    <strong>
                      {query
                        ? "No matches"
                        : group
                          ? "No words yet"
                          : "No groups yet"}
                    </strong>
                    <p>
                      {arrange
                        ? group
                          ? "Drop words here"
                          : "Drop groups here"
                        : "Add your own material above"}
                    </p>
                  </div>
                )}
              </div>
              <footer className="pane-footer">
                <span>
                  {selection[pane].length
                    ? `${selection[pane].length} selected`
                    : group
                      ? `${wordCount(words.length)} shown`
                      : book
                        ? `${shownGroups.length} groups`
                        : "Choose a book"}
                </span>
                {book && !draft && (
                  <div className="study-footer">
                    <select
                      aria-label={`${pane ? "Right" : "Left"} study order`}
                      value={order}
                      onChange={(e) => setOrder(e.target.value)}
                    >
                      <option>Sequential</option>
                      <option>Random</option>
                    </select>
                    <button
                      className="primary-button"
                      disabled={
                        busy ||
                        !(group
                          ? group.words.length
                          : members.some((g) => g.words.length))
                      }
                      onClick={() =>
                        onStudy(group?.id, group ? undefined : book.id, order)
                      }
                    >
                      {group
                        ? status(state, group) === "In progress"
                          ? "Resume"
                          : "Study group"
                        : "Study whole book"}{" "}
                      →
                    </button>
                  </div>
                )}
              </footer>
            </section>
          );
        })}
      </div>
      {ghost?.active && (
        <div
          className={`drag-ghost ${ghost.target ? "valid" : ""}`}
          style={{ left: ghost.x + 18, top: ghost.y + 14 }}
        >
          <span>{ghost.copy ? "＋ Copy" : "↗ Move"}</span>
          <strong>{ghost.title}</strong>
          <small>
            {ghost.target ? "Release to drop" : "Choose a destination"}
          </small>
        </div>
      )}
    </section>
  );
}
