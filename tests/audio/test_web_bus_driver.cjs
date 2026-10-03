#!/usr/bin/env node
/* Execute the shipped Godot Web driver, not a rewritten routing algorithm.
 * Recording AudioNodes establish graph connectivity/gain, not audible output.
 * Real browser gesture, focus and device checks remain separate.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '../..');
assert(process.argv[2], 'Pass the exact Godot 4.6.3 exported engine JS path');
const enginePath = path.resolve(process.argv[2]);
const engine = fs.readFileSync(enginePath, 'utf8');
const engineSha256 = crypto.createHash('sha256').update(engine).digest('hex');
assert.equal(engineSha256, 'e3f56ee40e6f84371053db06692cfac15e2c8659547b11c6b2dfa1996dabd981',
  'Review this exact-driver test when the pinned Godot Web engine changes');
const begin = engine.indexOf('var GodotAudio=');
const end = engine.indexOf(';function _godot_audio_get_sample_playback_position', begin);
assert(begin >= 0 && end > begin, 'Pinned engine contains the complete Web Audio driver');
const driverSource = engine.slice(begin, end) + ';this.audio = GodotAudio;';
const helperSource = fs.readFileSync(path.resolve(process.argv[3] || path.join(root,
  'addons/story_foundation/audio/web_safe_audio_buses.gd')), 'utf8');
assert(!helperSource.includes('AudioServer.add_bus('), 'Do not enter the broken Web insertion path');
assert(helperSource.includes('AudioServer.bus_count'), 'Module selects the native append index');
assert(/AudioServer\.bus_count\s*=\s*index\s*\+\s*1/.test(helperSource),
  'Module appends through native bus count growth');
assert(helperSource.includes('AudioServer.set_bus_send'), 'New bus has explicit routing');

let checks = 0;
function check(value, message) { checks++; assert(value, message); }
function equal(actual, expected, message) { checks++; assert.equal(actual, expected, message); }
function makeDriver() {
  let nextId = 0;
  const destination = { label: 'browser-destination', edges: [] };
  const context = {
    destination,
    createGain() {
      return {
        label: 'gain-' + nextId++, edges: [], gain: { value: 1 },
        connect(target) { this.edges.push(target); return target; },
        disconnect() { this.edges = []; },
      };
    },
  };
  const sandbox = {};
  vm.runInNewContext(driverSource, sandbox);
  const audio = sandbox.audio;
  audio.ctx = context;
  audio.buses = [];
  audio.set_sample_bus_count(1);
  const master = audio.buses[0];
  function reachesOutput(node, seen = new Set()) {
    if (node === destination) return true;
    if (seen.has(node)) return false;
    seen.add(node);
    return node.edges.some(target => reachesOutput(target, seen));
  }
  function hasCycle(node, ancestors = new Set()) {
    if (ancestors.has(node)) return true;
    const next = new Set(ancestors); next.add(node);
    return node.edges.some(target => hasCycle(target, next));
  }
  function effectiveGain(node, ancestors = new Set()) {
    if (node === destination) return 1;
    if (ancestors.has(node)) return 0;
    const next = new Set(ancestors); next.add(node);
    return (node.gain?.value ?? 1) * node.edges.reduce((sum, target) => sum + effectiveGain(target, next), 0);
  }
  return { audio, master, reachesOutput, hasCycle, effectiveGain };
}
function setup(legacy) {
  const d = makeDriver();
  equal(d.audio.buses.indexOf(d.master), 0, 'Original Master starts at index zero');
  check(d.reachesOutput(d.master.getInputNode()), 'Initial single-Master path reaches output');
  // AudioServer::add_bus() forwards the default -1 unchanged to Web. Even an
  // explicit index >= native bus_count is normalized to -1 by the C++ server.
  for (const nativeIndex of (legacy ? [1, 2] : [1, 2, 3])) {
    if (legacy) d.audio.add_sample_bus(-1);
    else d.audio.set_sample_bus_count(nativeIndex + 1);
    d.audio.set_sample_bus_send(nativeIndex, 0);
  }
  return d;
}
const broken = setup(true);
equal(broken.audio.buses.indexOf(broken.master), 2, 'Negative control reproduces Master index drift');
for (const bus of broken.audio.buses) {
  check(!broken.reachesOutput(bus.getInputNode()), 'Negative control disconnects every bus from output');
  check(broken.hasCycle(bus.getInputNode()), 'Negative control creates a routing cycle');
  equal(broken.effectiveGain(bus.getInputNode()), 0, 'Negative control is silent despite unmuted gain=1');
}
const fixed = setup(false);
equal(fixed.audio.buses.length, 4, 'Exactly four buses including Music');
check(helperSource.includes('AudioServer.get_bus_index'), 'Existing names are reused');
check(helperSource.includes('AudioServer.set_bus_name'), 'Appended bus receives explicit name');
equal(fixed.audio.buses.indexOf(fixed.master), 0, 'Master remains index zero');
for (const [index, bus] of fixed.audio.buses.entries()) {
  check(fixed.reachesOutput(bus.getInputNode()), 'Bus ' + index + ' reaches browser output');
  check(!fixed.hasCycle(bus.getInputNode()), 'Bus ' + index + ' has no routing cycle');
  equal(fixed.effectiveGain(bus.getInputNode()), 1, 'No duplicate output routes or gain before settings');
  equal(bus.getSend(), index === 0 ? null : fixed.master, 'Bus sends retain native index semantics');
}
const gain = index => fixed.effectiveGain(fixed.audio.buses[index].getInputNode());
const near = (actual, expected, message) => check(Math.abs(actual - expected) < 1e-6, message);
fixed.audio.set_sample_bus_volume_db(1, 20 * Math.log10(0.6));
fixed.audio.set_sample_bus_volume_db(2, 20 * Math.log10(0.6));
fixed.audio.set_sample_bus_volume_db(3, 20 * Math.log10(0.9));
near(gain(3), 0.9, 'Synthetic third-channel gain is independent');
near(gain(1), 0.6, 'Synthetic first-channel gain is preserved');
near(gain(2), 0.6, 'Synthetic second-channel gain is preserved');
fixed.audio.set_sample_bus_volume_db(0, 20 * Math.log10(0.5));
near(gain(1), 0.3, 'Master and SFX gains compose');
near(gain(2), 0.3, 'Master and Ambience gains compose');
near(gain(3), 0.45, 'Master and Music gains compose');
for (const index of [1, 2, 3]) {
  fixed.audio.set_sample_bus_mute(index, true);
  equal(gain(index), 0, 'Per-bus mute is silent');
  for (const other of [1, 2, 3].filter(i => i !== index))
    near(gain(other), other === 3 ? 0.45 : 0.3, 'Other buses remain audible');
  fixed.audio.set_sample_bus_mute(index, false);
  near(gain(index), index === 3 ? 0.45 : 0.3, 'Unmute retains selected gain');
}
fixed.audio.set_sample_bus_mute(0, true);
equal(gain(1), 0, 'Master mute covers SFX');
equal(gain(2), 0, 'Master mute covers Ambience');
equal(gain(3), 0, 'Master mute covers Music');
fixed.audio.set_sample_bus_mute(0, false);
near(gain(1), 0.3, 'Master unmute restores SFX path');
near(gain(2), 0.3, 'Master unmute restores Ambience path');
near(gain(3), 0.45, 'Master unmute restores Music path');
fixed.audio.set_sample_bus_count(4);
equal(fixed.audio.buses.length, 4, 'Repeated count does not duplicate buses');
equal(fixed.audio.buses[0], fixed.master, 'Repeated count keeps Master identity');
console.log('WEB_AUDIO_BUS_RESULT ' + JSON.stringify({ passed: true, checks, engineSha256,
  legacyAllBusesDisconnected: true, fixedAllBusesReachOutput: true, fixedGraphAcyclic: true,
  independentGainAndMute: true, scope: 'Exact exported driver with recording AudioNodes; not actual browser or audible-device validation' }));
