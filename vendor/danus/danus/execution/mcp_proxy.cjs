// Generic JSON-RPC stdio MCP bridge. It exposes only the host's bound allowlist.
// No shell, arbitrary URL, filesystem, or graph operations are implemented here.
'use strict';
const readline = require('node:readline');
const url = process.env.DANUS_CAPABILITY_URL;
const token = process.env.DANUS_CAPABILITY_TOKEN;
const limit = 2 * 1024 * 1024;
function rpc(body) {
  // Node fetch has a shorter implicit headers deadline than a full verifier.
  // Use the host-configured bound explicitly for this single fixed endpoint.
  const http = require('node:http');
  return new Promise((resolve, reject) => {
    const req = http.request(url, {method: 'POST', headers: {
      Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'
    }}, response => {
      let chunks = [], size = 0;
      response.on('data', data => {
        size += data.length;
        if (size > limit) { req.destroy(new Error('capability response too large')); return; }
        chunks.push(data);
      });
      response.on('error', reject);
      response.on('end', () => {
        try {
          if (response.statusCode !== 200) throw new Error(`capability HTTP ${response.statusCode}`);
          const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
          if (value.error) throw new Error(value.error);
          resolve(value);
        } catch (error) { reject(error); }
      });
    });
    const timer = setTimeout(() => req.destroy(new Error('capability wait timeout')),
                             Number(process.env.DANUS_TOOL_TIMEOUT || 600) * 1000);
    req.on('close', () => clearTimeout(timer));
    req.on('error', reject);
    req.end(JSON.stringify(body));
  });
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
