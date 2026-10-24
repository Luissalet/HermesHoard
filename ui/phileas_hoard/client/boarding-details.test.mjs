import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { build } from 'esbuild';
import { changedFields, rebaseDraft, settleSave, afterAddSave, installCopilot, CONTEXT_REQUEST } from './src/copilot-context.js';

const require = createRequire(import.meta.url);
const bundle = await build({ entryPoints: [new URL('./src/components/travel.jsx', import.meta.url).pathname.replace(/^\/(\w:)/, '$1')], bundle: true, format: 'cjs', platform: 'node', external: ['react', 'react-dom'], write: false });
const module = { exports: {} };
new Function('require', 'module', 'exports', bundle.outputFiles[0].text)(require, module, module.exports);
const { fromSegment, segmentPatch } = module.exports;

test('boarding edits remain partial, clear explicitly, rebase later typing and reach the final copilot consumer', async () => {
  const segment = { id: 's_boarding', kind: 'train', coach: '05', seat: '12A', travel_class: 'Turista', gate: null, notes: 'Original ñ', price: 0, dep_local: '2026-11-12T09:00' };
  const base = fromSegment(segment);
  assert.equal(base.price, '0');
  assert.equal(base.gate, '');
  const draft = { ...base, coach: '07', seat: '14B', travel_class: 'Preferente ñ' };
  const sent = changedFields(base, draft);
  assert.deepEqual(segmentPatch(draft, base, true), { seat: '14B', coach: '07', travel_class: 'Preferente ñ' });
  const cleared = { ...draft, coach: '', travel_class: '' };
  assert.deepEqual(segmentPatch(cleared, draft, true), { coach: '', travel_class: '' });
  const flight = fromSegment({ ...segment, kind: 'flight', gate: 'E12' });
  assert.deepEqual(segmentPatch({ ...flight, gate: '' }, flight, true), { gate: '' });

  const later = { ...draft, notes: 'Typed during save', travel_class: 'Later class' };
  const settled = settleSave(base, sent, later);
  assert.equal(settled.close, false);
  const refreshed = rebaseDraft(settled.base, later, fromSegment({ ...segment, ...sent }));
  assert.deepEqual(changedFields(refreshed.base, refreshed.draft), { travel_class: 'Later class', notes: 'Typed during save' });
  assert.deepEqual(segmentPatch(refreshed.draft, refreshed.base, true), { travel_class: 'Later class', notes: 'Typed during save' });
  assert.deepEqual(afterAddSave({ segment: { id: 'new_real_id' } }, 'segment', false), { close: false, id: 'new_real_id' });

  const win = new EventTarget();
  win.location = { hash: '#/viaje/t_boarding' };
  const editor = { form: 'segment', mode: 'edit', kind: 'segment', object_id: segment.id, trip_id: 't_boarding', fields: refreshed.draft, changed: changedFields(refreshed.base, refreshed.draft) };
  win.addEventListener(CONTEXT_REQUEST, e => e.detail.provide(editor));
  installCopilot(win, async (name, args) => {
    assert.equal(name, 'trip_get'); assert.equal(args.trip, 't_boarding');
    return { trip: { id: 't_boarding', title: 'Fictitious trip' }, segments: [segment] };
  });
  const context = await win.hoardCopilot.context();
  assert.deepEqual(context.view.editor, editor);
  assert.equal(context.view.editor.fields.coach, '07');
  assert.equal(context.view.editor.fields.seat, '14B');
  assert.equal(context.view.editor.fields.travel_class, 'Later class');
  assert.ok(context.active_objects.some(o => o.kind === 'segment' && o.object_id === segment.id));
});
