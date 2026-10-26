// Portable content only: no private IDs, review history, or source paths.
export type WordContent = {
  term: string;
  phonetic: string;
  meaning: string;
  expansion: string;
};
export type GroupContent = { name: string; words: WordContent[] };
export type LibraryClipboard =
  | { format: "sat-study-kit/groups"; version: 1; groups: GroupContent[] }
  | { format: "sat-study-kit/words"; version: 1; words: WordContent[] };
export type ClipboardMode = "app" | "system";

export const contentOnly = (word: WordContent): WordContent => ({
  term: word.term,
  phonetic: word.phonetic,
  meaning: word.meaning,
  expansion: word.expansion,
});
export const copyGroups = (groups: GroupContent[]): LibraryClipboard => ({
  format: "sat-study-kit/groups",
  version: 1,
  groups: groups.map((group) => ({
    name: group.name,
    words: group.words.map(contentOnly),
  })),
});
export const copyWords = (words: WordContent[]): LibraryClipboard => ({
  format: "sat-study-kit/words",
  version: 1,
  words: words.map(contentOnly),
});
export const clipboardLabel = (pack: LibraryClipboard) =>
  "groups" in pack
    ? `${pack.groups.length} ${pack.groups.length === 1 ? "group" : "groups"}`
    : `${pack.words.length} ${pack.words.length === 1 ? "word" : "words"}`;
export function isGroupClipboard(text: string) {
  try {
    return JSON.parse(text)?.format === "sat-study-kit/groups";
  } catch {
    return false;
  }
}
export async function copyToClipboard(
  pack: LibraryClipboard,
  mode: ClipboardMode,
  setAppCopy: (pack: LibraryClipboard) => void,
  writeSystem: (text: string) => Promise<void>,
) {
  if (mode === "app") setAppCopy(pack);
  else await writeSystem(JSON.stringify(pack, null, 2));
}
