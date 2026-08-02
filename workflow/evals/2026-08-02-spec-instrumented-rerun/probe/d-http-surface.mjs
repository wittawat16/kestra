import http from 'node:http';
import os from 'node:os';

// D1: loopback-only binding is enforced by listen(port,'127.0.0.1') — verify a LAN address is refused
const server = http.createServer((req, res) => {
  if (req.method === 'POST' && req.url === '/requeue') {
    res.writeHead(303, { Location: '/?outcome=moved' }); res.end(); return;
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(`<p>url=${req.url} method=${req.method}</p>`);
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const { address, port } = server.address();
console.log('D1 bound to:', address, port);

const lan = Object.values(os.networkInterfaces()).flat()
  .filter(i => i && i.family === 'IPv4' && !i.internal).map(i => i.address);
console.log('D1 non-loopback IPv4 on this host:', JSON.stringify(lan));
if (lan.length) {
  try {
    const r = await fetch(`http://${lan[0]}:${port}/`, { signal: AbortSignal.timeout(1500) });
    console.log('D1 VERDICT reachable on LAN addr — BAD:', r.status);
  } catch (e) {
    console.log('D1 VERDICT refused on LAN addr — GOOD:', e.constructor.name, String(e.cause && e.cause.code || e.message).slice(0,40));
  }
} else { console.log('D1 no non-loopback iface to test against'); }

// D2: POST -> 303 redirect: does platform fetch follow it, and with what method?
const r2 = await fetch(`http://127.0.0.1:${port}/requeue`, { method: 'POST' });
console.log('D2 final status:', r2.status, '| redirected:', r2.redirected, '| final url:', new URL(r2.url).pathname + new URL(r2.url).search);
console.log('D2 body:', (await r2.text()).trim());
const r3 = await fetch(`http://127.0.0.1:${port}/requeue`, { method: 'POST', redirect: 'manual' });
console.log('D2 manual mode status:', r3.status, '| Location hdr:', r3.headers.get('location'));

// D3: ephemeral port 0 gives a distinct port each time (parallel-test safety)
const s2 = http.createServer(() => {}); await new Promise(r => s2.listen(0, '127.0.0.1', r));
console.log('D3 second ephemeral port differs:', s2.address().port !== port, s2.address().port);
s2.close();

// D4: unclosed server keeps the runner alive? demonstrate handle count
console.log('D4 active handles before close:', process._getActiveHandles().filter(h => h.constructor.name === 'Server').length);
server.close();
await new Promise(r => setTimeout(r, 50));
console.log('D4 active handles after close:', process._getActiveHandles().filter(h => h.constructor.name === 'Server').length);
