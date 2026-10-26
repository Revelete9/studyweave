export type ImportedWord = { sequence?: number; term: string; meaning: string; phonetic: string; expansion: string };
export type WordFormat = "auto" | "json" | "csv" | "tsv" | "pipe" | "pairs";

// Quoted fields may contain separators, doubled quotes and line breaks.
export function splitTable(text: string, delimiter: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], field = "", quoted = false, closed = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') { quoted = false; closed = true; }
      else field += c;
    } else if (c === delimiter || c === "\n") {
      row.push(field); field = ""; closed = false;
      if (c === "\n") { if (row.some(v => v.trim())) rows.push(row); row = []; }
    } else if (c === '"' && !field.trim() && !closed) { field = ""; quoted = true; }
    else if (closed && c.trim()) throw new Error("Unexpected text after a closing quote.");
    else if (c === '"') throw new Error("Quote a whole field and double any quotes inside it.");
    else field += c;
  }
  if (quoted) throw new Error("Unclosed quoted field.");
  row.push(field);
  if (row.some(v => v.trim())) rows.push(row);
  return rows;
}

export function parseWords(input: string, format: WordFormat = "auto"): { words: ImportedWord[]; corrections: string[]; format: string } {
  if (new TextEncoder().encode(input).length > 2_000_000) throw new Error("Import limit: 2 MB.");
  const corrections: string[] = [];
  let text = input.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n");
  if (text !== input) corrections.push("Normalized BOM / line endings.");
  if (text.trim() !== text) corrections.push("Removed outer whitespace.");
  text = text.trim();
  if (!text) throw new Error("Paste words or choose a text file first.");
  if (format === "auto") {
    format = /^[\[{]/.test(text) ? "json" : text.split("\n")[0].includes("\t") ? "tsv"
      : /[|｜]/.test(text.split("\n")[0]) ? "pipe"
      : text.split("\n")[0].includes("=") ? "pairs" : "csv";
  }
  let entries: Record<string, unknown>[];
  const aliases: Record<string, string> = { word: "term", definition: "meaning", pronunciation: "phonetic", notes: "expansion", number: "sequence" };
  const columns = new Set(["term", "meaning", "phonetic", "expansion", "sequence"]);
  if (format === "json") {
    const parsed = JSON.parse(text);
    entries = Array.isArray(parsed) ? parsed : parsed?.words;
    if (!Array.isArray(entries)) throw new Error('JSON must be an array or an object containing "words".');
  } else if (format === "pairs") {
    entries = text.split("\n").filter(line => line.trim()).map((line, i) => {
      const split = line.indexOf("=");
      if (split < 1) throw new Error(`Line ${i + 1}: expected word = meaning.`);
      return { term: line.slice(0, split), meaning: line.slice(split + 1) };
    });
  } else {
    if (format === "pipe" && text.includes("｜")) {
      text = text.replace(/｜/g, "|"); corrections.push("Converted full-width pipe separators to |.");
    }
    const rows = splitTable(text, format === "tsv" ? "\t" : format === "pipe" ? "|" : ",");
    if (!rows.length) throw new Error("No words found. Provide a term and meaning on each row.");
    const header = rows[0].map(v => aliases[v.trim().toLowerCase()] ?? v.trim().toLowerCase());
    const hasHeader = header.includes("term") && header.includes("meaning");
    if (hasHeader && (header.some(v => !columns.has(v)) || new Set(header).size !== header.length))
      throw new Error("Header contains unknown or duplicate columns.");
    const names = hasHeader ? header : rows[0].length === 2 ? ["term", "meaning"]
      : rows[0].length === 4 ? ["term", "phonetic", "meaning", "expansion"]
      : rows[0].length === 5 ? ["sequence", "term", "phonetic", "meaning", "expansion"] : [];
    if (!names.length) throw new Error("Use a header, or 2, 4 or 5 columns. See supported formats.");
    entries = rows.slice(hasHeader ? 1 : 0).map((row, i) => {
      if (row.length !== names.length) throw new Error(`Row ${i + (hasHeader ? 2 : 1)}: expected ${names.length} columns, got ${row.length}. Quote fields containing separators.`);
      return Object.fromEntries(names.map((name, j) => [name, row[j]]));
    });
  }
  if (!entries.length || entries.length > 5000) throw new Error("Import 1–5,000 words at a time.");
  const words: ImportedWord[] = [], seen = new Map<string, ImportedWord>(), sequences = new Set<number>();
  entries.forEach((raw, i) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error(`Entry ${i + 1}: expected an object.`);
    const value: Record<string, unknown> = {};
    for (const [key, v] of Object.entries(raw)) {
      const canonical = aliases[key.trim().toLowerCase()] ?? key.trim().toLowerCase();
      if (!columns.has(canonical) || canonical in value) throw new Error(`Entry ${i + 1}: unknown or duplicate field ${key}.`);
      value[canonical] = v;
      if (canonical !== key) corrections.push(`Entry ${i + 1}: normalized field ${key} to ${canonical}.`);
    }
    const clean = (key: string, required = false) => {
      const v = value[key] ?? "";
      if (typeof v !== "string") throw new Error(`Entry ${i + 1}: ${key} must be text.`);
      if (required && !v.trim()) throw new Error(`Entry ${i + 1}: ${key} cannot be empty.`);
      if (v !== v.trim()) corrections.push(`Entry ${i + 1}: trimmed ${key}.`);
      return v.trim();
    };
    const word: ImportedWord = { term: clean("term", true), meaning: clean("meaning", true), phonetic: clean("phonetic"), expansion: clean("expansion") };
    const key = word.term.toLowerCase();
    const previous = seen.get(key);
    if (previous) {
      if (["meaning", "phonetic", "expansion"].some(k => previous[k as keyof ImportedWord] !== word[k as keyof ImportedWord]))
        throw new Error(`Conflicting entries for ${word.term}. Combine meanings or remove the duplicate.`);
      corrections.push(`Skipped duplicate word: ${word.term}.`); return;
    }
    const number = value.sequence;
    if (number !== undefined && number !== "") {
      const n = typeof number === "string" && /^\d+$/.test(number.trim()) ? Number(number.trim()) : number;
      if (typeof n !== "number" || !Number.isSafeInteger(n) || n < 1 || sequences.has(n))
        corrections.push(`Entry ${i + 1}: invalid / duplicate sequence will be assigned automatically.`);
      else { word.sequence = n; sequences.add(n); }
    }
    seen.set(key, word); words.push(word);
  });
  return { words, corrections, format };
}
