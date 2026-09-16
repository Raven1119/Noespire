// Generic JSON-RPC stdio MCP bridge. It exposes only the host's bound allowlist.
// No shell, arbitrary URL, filesystem, or graph operations are implemented here.
'use strict';
const readline = require('node:readline');
const url = process.env.DANUS_CAPABILITY_URL;
const token = process.env.DANUS_CAPABILITY_TOKEN;
const limit = 2 * 1024 * 1024;
async function rpc(body) {
  const r = await fetch(url, {method: 'POST', headers: {
    Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'
  }, body: JSON.stringify(body)});
  if (!r.ok) throw new Error(`capability HTTP ${r.status}`);
  const text = await r.text();
  if (Buffer.byteLength(text) > limit) throw new Error('capability response too large');
  const value = JSON.parse(text);
  if (value.error) throw new Error(value.error);
  return value;
}
async function handle(m) {
  if (m.method === 'initialize') return {protocolVersion: '2024-11-05',
    capabilities: {tools: {}}, serverInfo: {name: 'danus-capabilities', version: '1'}};
  if (m.method === 'ping') return {};
  if (m.method === 'tools/list') return await rpc({method: 'list'});
  if (m.method === 'tools/call') {
    try {
      const value = await rpc({method: 'call', name: m.params.name,
                               arguments: m.params.arguments ?? {}});
      return {content: [{type: 'text', text: JSON.stringify(value.result)}], isError: false};
    } catch (e) {
      return {content: [{type: 'text', text: String(e.message)}], isError: true};
    }
  }
  throw new Error('unsupported MCP method');
}
const lines = readline.createInterface({input: process.stdin, crlfDelay: Infinity});
lines.on('line', async line => {
  let m;
  try {
    if (Buffer.byteLength(line) > limit) throw new Error('request too large');
    m = JSON.parse(line);
    if (m.id === undefined) return;
    const result = await handle(m);
    process.stdout.write(JSON.stringify({jsonrpc: '2.0', id: m.id, result}) + '\n');
  } catch (e) {
    process.stdout.write(JSON.stringify({jsonrpc: '2.0', id: m?.id ?? null,
      error: {code: -32600, message: String(e.message)}}) + '\n');
  }
});
