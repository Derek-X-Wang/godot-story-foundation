#!/usr/bin/env node
/* Opt-in characterization of the exact official Godot Web Sample driver.
 * No engine/game assets are bundled and no lifecycle methods are replaced.
 * Known defects are required negative controls, not successful pause contracts.
 * Mock nodes record calls; manual ended events do not simulate browser timing.
 */
'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Official 4.6.3-stable, MIT (see licenses/Godot-MIT.txt). External input only:
// https://github.com/godotengine/godot/blob/35e80b3a8822a9df9be390814b62f44c0a9c69e8/platform/web/js/libs/library_godot_audio.js
const sourceCommit = '35e80b3a8822a9df9be390814b62f44c0a9c69e8';
const expectedSha256 = '46e8983be587672d11d073dc65eee0bf89cb6b43acf612de1eb16f17abb1849e';
assert.equal(process.argv.length, 3,
  'Usage: node tests/audio/test_web_pause_driver.cjs /path/to/official/library_godot_audio.js');
const sourcePath = path.resolve(process.argv[2]);
const sourceBytes = fs.readFileSync(sourcePath);
const sourceSha256 = crypto.createHash('sha256').update(sourceBytes).digest('hex');
assert.equal(sourceSha256, expectedSha256,
  'Source integrity mismatch: use the exact pinned official file; review before changing the pin');

let checks = 0;
function equal(actual, expected, message) { checks++; assert.equal(actual, expected, message); }
function check(value, message) { checks++; assert(value, message); }

function makeDriver() {
  const sources = [];
  const queuedEnds = [];
  const errors = [];
  function node() {
    return {
      edges: [],
      connect(target) { this.edges.push(target); return target; },
      disconnect() { this.edges = []; },
    };
  }
  function buffer(numberOfChannels, length, sampleRate) {
    const channels = Array.from({ length: numberOfChannels }, () => new Float32Array(length));
    return {
      numberOfChannels, length, sampleRate, duration: length / sampleRate,
      getChannelData(index) { return channels[index]; },
      copyToChannel(data, index, offset) { channels[index].set(data, offset); },
    };
  }
  const context = {
    currentTime: 100,
    destination: node(),
    createGain() { return Object.assign(node(), { gain: { value: 1 } }); },
    createChannelSplitter: node,
    createChannelMerger: node,
    createBuffer: buffer,
    createBufferSource() {
      const listeners = new Set();
      const source = Object.assign(node(), {
        playbackRate: { value: 1 }, starts: [], stopCalls: 0, ended: false,
        addEventListener(type, listener) { assert.equal(type, 'ended'); listeners.add(listener); },
        removeEventListener(type, listener) { assert.equal(type, 'ended'); listeners.delete(listener); },
        start(when, offset) {
          assert.equal(this.starts.length, 0, 'A BufferSource can only start once');
          this.starts.push({ when, offset, contextTime: context.currentTime });
        },
        stop() {
          assert.equal(this.starts.length, 1, 'Cannot stop an unstarted source');
          this.stopCalls++;
          // Real stop completion is asynchronous. Tests deliberately drain it
          // before resuming; this does not establish event-race behavior.
          queuedEnds.push(() => this.dispatchEnded());
        },
        dispatchEnded() {
          if (this.ended) return;
          this.ended = true;
          for (const listener of [...listeners]) listener({ type: 'ended' });
        },
      });
      sources.push(source);
      return source;
    },
  };
  class RecordingWorklet {
    constructor() {
      Object.assign(this, node());
      this.messages = [];
      this.port = { onmessage: null, postMessage: message => this.messages.push(message) };
      this.parameters = new Map([['reset', { setValueAtTime() {} }]]);
    }
  }
  const sandbox = {
    LibraryManager: { library: {} },
    autoAddDeps() {},
    mergeInto(library, definitions) { Object.assign(library, definitions); },
    AudioWorkletNode: RecordingWorklet,
    GodotRuntime: { error: error => errors.push(error) },
  };
  // Evaluate the complete, hash-checked upstream file unchanged. These stubs
  // capture Emscripten registration; they do not emulate the C++/Wasm bridge.
  vm.runInNewContext(sourceBytes.toString('utf8'), sandbox,
    { filename: sourcePath, timeout: 1000 });
  const audio = sandbox.LibraryManager.library.$GodotAudio;
  sandbox.GodotAudio = audio;
  audio.ctx = context;
  audio.samples = new Map();
  audio.sampleNodes = new Map();
  audio.buses = [];
  audio.audioPositionWorkletNodes = [];
  audio.audioPositionWorkletPromise = Promise.resolve();
  audio.set_sample_bus_count(1);
  // Silence is intentional: duration/offset metadata only, no licensed asset.
  audio.Sample.create({ id: 'synthetic-loop', audioBuffer: buffer(2, 6000, 100) },
    { numberOfChannels: 2, sampleRate: 100, loopMode: 'forward' });
  async function play(offset = 0) {
    // Mirrors godot_audio_sample_start's options, including playbackRate=1.
    audio.start_sample('synthetic-player', 'synthetic-loop', 0,
      { offset, volume: new Float32Array(8).fill(1), playbackRate: 1, pitchScale: 1, start: true });
    await new Promise(resolve => setImmediate(resolve));
    equal(errors.length, 0, 'Position-worklet connection completed without errors');
    return audio.SampleNode.getSampleNode('synthetic-player');
  }
  function pause(enable) { audio.sample_set_pause('synthetic-player', enable); }
  function drainStoppedEvents() { while (queuedEnds.length) queuedEnds.shift()(); }
  function lastOffset() { return sources.at(-1).starts.at(-1).offset; }
  function finishCurrentSource() {
    const source = sources.at(-1);
    context.currentTime += source.buffer.duration - source.starts.at(-1).offset;
    source.dispatchEnded();
  }
  function stop() { audio.stop_sample('synthetic-player'); drainStoppedEvents(); }
  return { audio, context, sources, play, pause, drainStoppedEvents, lastOffset,
    finishCurrentSource, stop };
}

async function main() {
  // Positive controls: zero-offset natural restart, one hold, explicit stop.
  const normal = makeDriver();
  const normalPlayer = await normal.play();
  equal(normal.lastOffset(), 0, 'Initial source starts at zero');
  for (let loop = 0; loop < 2; loop++) {
    normal.finishCurrentSource();
    equal(normal.lastOffset(), 0, 'Injected natural end restarts a zero-offset loop at zero');
  }
  normal.context.currentTime += 3;
  normal.pause(true);
  normal.drainStoppedEvents();
  equal(normalPlayer.pauseTime, 3, 'First real hold captures three played seconds');
  const countWhileHeld = normal.sources.length;
  normal.context.currentTime += 10;
  equal(normal.sources.length, countWhileHeld, 'Stopped ended event does not restart while paused');
  normal.pause(false);
  equal(normal.lastOffset(), 3, 'First resume excludes the first ten-second hold');
  normal.stop();
  equal(normal.audio.sampleNodes.size, 0, 'Explicit stop unregisters the player');
  check(normal.sources.every(source => source.edges.length === 0), 'Stop disconnects all created sources');

  // Negative control 1: unchanged false is an operation, not an idempotent state.
  const refresh = makeDriver();
  await refresh.play();
  for (let i = 0; i < 3; i++) {
    refresh.context.currentTime += 2;
    const before = refresh.sources.length;
    refresh.pause(false);
    equal(refresh.sources.length, before + 1, 'Redundant false replaces the source');
    equal(refresh.lastOffset(), 0, 'Redundant false restarts at zero');
  }
  refresh.stop();

  // Negative control 2: repeated true overwrites the original held position.
  const repeated = makeDriver();
  const repeatedPlayer = await repeated.play();
  repeated.context.currentTime += 3;
  repeated.pause(true);
  repeated.drainStoppedEvents();
  equal(repeatedPlayer.pauseTime, 3, 'First true stores the actual elapsed interval');
  repeated.context.currentTime += 10;
  repeated.pause(true);
  repeated.drainStoppedEvents();
  equal(repeatedPlayer.pauseTime, 13, 'Repeated true incorporates held wall-clock time');
  repeated.pause(false);
  equal(repeated.lastOffset(), 13, 'Repeated true corrupts the resumed offset');
  repeated.stop();

  // Negative control 3: even transition-only calls fail on the second real hold.
  const second = makeDriver();
  const secondPlayer = await second.play();
  const originalStartTime = secondPlayer._sourceStartTime;
  second.context.currentTime += 3;
  second.pause(true);
  second.drainStoppedEvents();
  second.context.currentTime += 10;
  second.pause(false);
  equal(second.lastOffset(), 3, 'Transition-only first resume looks correct');
  equal(secondPlayer._sourceStartTime, originalStartTime, 'Unpause retains the original source clock');
  second.context.currentTime += 2;
  second.pause(true);
  second.drainStoppedEvents();
  equal(secondPlayer.pauseTime, 15, 'Second real hold captures 15 seconds instead of five');
  second.context.currentTime += 10;
  second.pause(false);
  equal(second.lastOffset(), 15, 'Second resume includes the earlier ten-second hold');
  check(second.lastOffset() !== 5, 'Same-state suppression alone cannot provide accumulated playback time');
  second.stop();

  // Negative control 4: stop/play(saved_offset) repairs the immediate position
  // but the same offset survives every later ended-driven loop restart.
  const resumed = makeDriver();
  await resumed.play();
  resumed.context.currentTime += 5;
  const savedOffset = 5; // Explicit consumer-owned elapsed time, no worklet claim.
  resumed.stop();
  resumed.context.currentTime += 10;
  await resumed.play(savedOffset);
  equal(resumed.lastOffset(), 5, 'Stop/play initially restores the saved offset');
  for (let loop = 0; loop < 2; loop++) {
    resumed.finishCurrentSource();
    equal(resumed.lastOffset(), 5, 'Natural-end callback restarts at the saved nonzero offset');
    check(resumed.lastOffset() !== 0, 'Later full loops lose their first five seconds');
  }
  resumed.stop();

  console.log('WEB_AUDIO_PAUSE_RESULT ' + JSON.stringify({
    passed: true, checks, sourceCommit, sourceSha256,
    negativeControls: { redundantFalseRestarts: true, repeatedTrueRewritesOffset: true,
      secondHoldIncludesPriorHold: true, savedOffsetPersistsIntoLoops: true },
    scope: 'Pinned official Sample driver characterization with mock nodes and injected ended events; '
      + 'not a lifecycle fix, native/Stream mixer test, browser scheduling test or listening validation',
  }));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
