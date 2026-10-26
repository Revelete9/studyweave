import type { ReviewResult } from "./review.ts";

export type Word = {
  id: string;
  sequence?: number;
  term: string;
  meaning: string;
  phonetic: string;
  expansion?: string;
  example?: string;
  remembered: number;
  forgotten: number;
  streak: number;
  encounters?: number;
  lastSeen?: string;
};

export type SortKey = "source" | "errorRate" | "errors" | "encounters";
export type SortDirection = "asc" | "desc";

export type WordGroup = {
  id: string;
  name: string;
  description: string;
  accent: string;
  words: Word[];
};

export type VocabularyCatalog = {
  pack_id?: string;
  version: string;
  retiredCategoryIds?: string[];
  total: number;
  categories: Array<{
    id: string;
    name: string;
    description: string;
    accent: string;
    words: Array<{
      sequence: number;
      term: string;
      meaning: string;
      phonetic: string;
      expansion?: string;
    }>;
  }>;
};

export type ReviewEvent = {
  id: string;
  queueEntryId?: string;
  groupId: string;
  wordId: string;
  result: ReviewResult;
  at: string;
};

export type SessionStats = {
  remembered: number;
  forgotten: number;
  skipped: number;
};

export const STORAGE_KEY = "sat-study-kit.web.v1";
export const ACCENTS = ["#ea6a47", "#4f7c62", "#4c6f91", "#a56a83", "#b1843f"];
export const SORT_OPTIONS: Array<{ key: Exclude<SortKey, "source">; label: string }> = [
  { key: "errorRate", label: "Error rate" },
  { key: "errors", label: "Errors" },
  { key: "encounters", label: "Encounters" },
];

export const DEFAULT_GROUPS: WordGroup[] = [{
  id: "example", name: "Library not loaded", description: "Open Word library to import your words", accent: "#4f7c62",
  words: [],
}];

export const emptySession: SessionStats = { remembered: 0, forgotten: 0, skipped: 0 };

export function makeId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function masteryFor(group: WordGroup) {
  if (!group.words.length) return 0;
  const total = group.words.reduce((sum, word) => {
    const remembered = word.remembered;
    const forgotten = word.forgotten;
    const attempts = remembered + forgotten;
    if (!attempts) return sum;
    const accuracy = remembered / attempts;
    const streakLift = Math.min(word.streak, 3) / 3;
    return sum + accuracy * 0.72 + streakLift * 0.28;
  }, 0);
  return Math.round((total / group.words.length) * 100);
}

export function statusFor(word: Word) {
  const remembered = word.remembered;
  const forgotten = word.forgotten;
  const attempts = remembered + forgotten;
  if (!attempts) return { label: "New", tone: "new" };
  if (word.streak >= 3) {
    return { label: "Mastered", tone: "mastered" };
  }
  return { label: "Learning", tone: "learning" };
}

export function encountersFor(word: Word) {
  return word.encounters ?? word.remembered + word.forgotten;
}

export function errorRateFor(word: Word) {
  const forgotten = word.forgotten;
  const judged = word.remembered + forgotten;
  return judged ? forgotten / judged : 0;
}

export function sortMetric(word: Word, key: Exclude<SortKey, "source">) {
  if (key === "errorRate") return errorRateFor(word);
  if (key === "errors") return word.forgotten;
  return encountersFor(word);
}

export function sameDay(iso: string) {
  return new Date(iso).toDateString() === new Date().toDateString();
}

export function groupsFromCatalog(catalog: VocabularyCatalog): WordGroup[] {
  return catalog.categories.map((category) => ({
    ...category,
    description: category.description === "User-reviewed AI-assisted import" ? "Imported vocabulary" : category.description,
    words: category.words.map((word) => ({
      id: `sat-${word.sequence}`,
      ...word,
      expansion: word.expansion ?? "",
      remembered: 0,
      forgotten: 0,
      streak: 0,
      encounters: 0,
    })),
  }));
}

export type CatalogMergeWord = Word;

export type CatalogMergeGroup<TWord extends CatalogMergeWord = CatalogMergeWord> = {
  id: string;
  name: string;
  description: string;
  accent: string;
  words: TWord[];
};

function isCatalogWord(word: CatalogMergeWord) {
  return word.id.startsWith("sat-") && Number.isInteger(word.sequence);
}

function withSavedProgress<TWord extends CatalogMergeWord>(catalogWord: TWord, savedWord?: TWord): TWord {
  if (!savedWord) return catalogWord;
  return {
    ...catalogWord,
    remembered: savedWord.remembered ?? 0,
    forgotten: savedWord.forgotten ?? 0,
    streak: savedWord.streak ?? 0,
    encounters: savedWord.encounters ?? savedWord.remembered + savedWord.forgotten,
    lastSeen: savedWord.lastSeen,
  };
}

export function mergeCatalogWithSavedGroups<
  TWord extends CatalogMergeWord,
  TGroup extends CatalogMergeGroup<TWord>,
>(catalogGroups: TGroup[], savedGroups: TGroup[], retiredGroupIds: string[] = []): TGroup[] {
  const savedCatalogWords = new Map<number, TWord>();
  for (const group of savedGroups) {
    for (const word of group.words) {
      if (isCatalogWord(word)) savedCatalogWords.set(word.sequence!, word);
    }
  }

  const catalogGroupIds = new Set(catalogGroups.map((group) => group.id));
  const savedGroupsById = new Map(savedGroups.map((group) => [group.id, group]));
  const refreshedCatalogGroups = catalogGroups.map((group) => {
    const savedGroup = savedGroupsById.get(group.id);
    const customWords = savedGroup?.words.filter((word) => !isCatalogWord(word)) ?? [];
    return {
      ...group,
      words: [
        ...group.words.map((word) => withSavedProgress(word, savedCatalogWords.get(word.sequence!))),
        ...customWords,
      ],
    };
  });

  return [
    ...refreshedCatalogGroups,
    ...savedGroups.filter((group) => !catalogGroupIds.has(group.id)).flatMap((group) => {
      if (!retiredGroupIds.includes(group.id)) return [group];
      const customWords = group.words.filter((word) => !isCatalogWord(word));
      return customWords.length ? [{ ...group, words: customWords }] : [];
    }),
  ];
}
