import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const endpoint = process.argv[2] ?? 'http://127.0.0.1:9223';
const output = path.resolve(process.argv[3] ?? 'qa-screenshots/after');
const width = Number(process.argv[4] ?? 1440);
const height = Number(process.argv[5] ?? 900);
const preset = process.argv[6] ?? 'story';
const targetUrl = process.argv[7] ?? 'http://127.0.0.1:5173/#/home';
const requestedTheme = process.argv[8];
const theme = requestedTheme === 'light' || requestedTheme === 'dark' || requestedTheme === 'system' ? requestedTheme : null;
const storyChapters = [
  ['01-ask', 0.03],
  ['02-understand', 0.18],
  ['03-assemble', 0.33],
  ['04-estimate', 0.49],
  ['05-secure', 0.65],
  ['06-verify', 0.8],
  ['07-deliver', 0.96],
];
const chapters = preset === 'story' ? storyChapters : [[preset, preset === 'deliver' ? 0.96 : 0]];
const audits = [];

async function waitForDebugger() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const pages = await fetch(`${endpoint}/json/list`).then((response) => response.json());
      const page = pages.find((item) => item.type === 'page');
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl;
    } catch {
      // Chrome may still be starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error('Chrome DevTools endpoint did not become ready.');
}

const socket = new WebSocket(await waitForDebugger());
const pending = new Map();
let sequence = 0;

await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true });
  socket.addEventListener('error', reject, { once: true });
});

socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);
  if (!message.id) return;
  const request = pending.get(message.id);
  if (!request) return;
  pending.delete(message.id);
  if (message.error) request.reject(new Error(message.error.message));
  else request.resolve(message.result);
});

function send(method, params = {}) {
  const id = ++sequence;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

await mkdir(output, { recursive: true });
await send('Page.enable');
await send('Runtime.enable');
if (theme) {
  await send('Page.addScriptToEvaluateOnNewDocument', {
    source: `window.localStorage.setItem('eb-theme', ${JSON.stringify(theme)});`,
  });
}
await send('Emulation.setDeviceMetricsOverride', {
  width,
  height,
  deviceScaleFactor: 1,
  mobile: false,
});
await send('Page.navigate', { url: targetUrl });
await new Promise((resolve) => setTimeout(resolve, 700));
if (theme) {
  await send('Runtime.evaluate', {
    expression: `(() => {
      if (window.localStorage.getItem('eb-theme') === ${JSON.stringify(theme)}) return;
      window.localStorage.setItem('eb-theme', ${JSON.stringify(theme)});
      window.location.reload();
    })()`,
  });
}
await new Promise((resolve) => setTimeout(resolve, 1200));

for (const [name, progress] of chapters) {
  await send('Runtime.evaluate', {
    expression: `(() => {
      const run = document.querySelector('.story-run');
      window.scrollTo(0, run ? ${progress} * (run.offsetHeight - window.innerHeight) : 0);
      ${preset === 'team' ? "document.querySelector('.team-trigger')?.click();" : ''}
    })()`,
  });
  await new Promise((resolve) => setTimeout(resolve, 850));
  const { data } = await send('Page.captureScreenshot', {
    format: 'png',
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await writeFile(path.join(output, `${name}.png`), Buffer.from(data, 'base64'));
  const audit = await send('Runtime.evaluate', {
    expression: `JSON.stringify({
      viewport: [window.innerWidth, window.innerHeight],
      chapter: document.querySelector('.app-frame')?.getAttribute('data-chapter') ?? 'quiet',
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      title: document.querySelector('.team-panel h2')?.textContent?.trim() ?? document.querySelector('.story-scene.is-on h2, .quiet-chapter h2')?.textContent?.trim() ?? '',
    })`,
    returnByValue: true,
  });
  audits.push({ name, ...JSON.parse(audit.result.value) });
}

socket.close();
console.log(`Captured ${chapters.length} chapters in ${output}`);
console.log(JSON.stringify(audits));
