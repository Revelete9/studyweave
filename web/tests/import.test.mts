import assert from 'node:assert/strict';
import test from 'node:test';
import { parseWords } from '../src/import.ts';

test('pairs, CSV, TSV, pipe and JSON represent the same words', () => {
  for (const input of ['concise = brief', 'concise,brief', 'concise\tbrief', 'concise|brief', '[{"term":"concise","meaning":"brief"}]']) {
    const { words } = parseWords(input);
    assert.equal(words[0].term, 'concise'); assert.equal(words[0].meaning, 'brief');
  }
});
test('quoted delimiters, quotes and multiline cells are preserved', () => {
  const result = parseWords('term,meaning,notes\nconcise,"brief, clear","A ""short""\nnote"', 'csv');
  assert.equal(result.words[0].meaning, 'brief, clear');
  assert.equal(result.words[0].expansion, 'A "short"\nnote');
});
test('legacy four and five-column rows and named columns', () => {
  assert.equal(parseWords('4 | concise | /x/ | brief | note').words[0].sequence, 4);
  assert.equal(parseWords('concise | /x/ | brief | note').words[0].phonetic, '/x/');
  assert.equal(parseWords('definition,word\nbrief,concise').words[0].term, 'concise');
});
test('safe corrections are reported and content is not guessed', () => {
  const result = parseWords('\ufeff concise ｜ brief \r\n');
  assert.equal(result.words[0].term, 'concise'); assert.ok(result.corrections.length > 0);
  const misspelling = parseWords('conciese = brief');
  assert.equal(misspelling.words[0].term, 'conciese');
});
test('duplicate rows skipped; conflicting definitions rejected', () => {
  assert.equal(parseWords('concise=brief\nCONCISE=brief').words.length, 1);
  assert.throws(() => parseWords('concise=brief\nconcise=long'));
});
test('invalid and duplicate sequence numbers are repaired explicitly', () => {
  const result = parseWords('[{"term":"one","meaning":"first","sequence":1},{"term":"two","meaning":"second","sequence":1}]');
  assert.equal(result.words[1].sequence, undefined); assert.ok(result.corrections.length);
});
test('malformed data is rejected as a whole', () => {
  for (const [input, format] of [
    ['term,meaning\na,b,c','csv'], ['"a,b','csv'], ['a=','pairs'], ['a=b\ninvalid','pairs'],
    ['[{"term":"a","meaning":"b","image":"x"}]','json'], ['term,meaning,word\na,b,c','csv']
  ] as const) assert.throws(() => parseWords(input, format));
  assert.throws(() => parseWords('x'.repeat(2_000_001)));
  assert.throws(() => parseWords(',,', 'csv'), /No words found/);
});
