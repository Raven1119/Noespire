'use strict';
const fs = require('node:fs');
const {spawn} = require('node:child_process');
const request = JSON.parse(fs.readFileSync('/work/launch.json', 'utf8'));
const child = spawn('codex', request.argv, {stdio: ['pipe', 'inherit', 'inherit']});
child.stdin.end(request.prompt);
// Host timeout is authoritative. This same-ceiling watchdog only bounds an
// orphan container if the host process dies without running its finally block.
let timedOut = false;
const timer = setTimeout(() => {
  timedOut = true;
  child.kill('SIGTERM');
  setTimeout(() => process.exit(124), 10000).unref();
}, request.timeout * 1000);
child.on('error', e => {clearTimeout(timer); console.error(e.message); process.exitCode = 127;});
child.on('exit', (code, signal) => {clearTimeout(timer); process.exitCode = timedOut ? 124 : (code ?? 128);});
