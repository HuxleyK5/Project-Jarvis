import { test, expect, type Page } from '@playwright/test';

function wav(seconds = 2) {
  const samples = 16000 * seconds;
  const data = Buffer.alloc(44 + samples * 2);
  data.write('RIFF', 0); data.writeUInt32LE(data.length - 8, 4); data.write('WAVEfmt ', 8);
  data.writeUInt32LE(16, 16); data.writeUInt16LE(1, 20); data.writeUInt16LE(1, 22);
  data.writeUInt32LE(16000, 24); data.writeUInt32LE(32000, 28); data.writeUInt16LE(2, 32); data.writeUInt16LE(16, 34);
  data.write('data', 36); data.writeUInt32LE(samples * 2, 40);
  for (let i = 0; i < samples; i++) data.writeInt16LE(Math.round(9000 * Math.sin(i * Math.PI * 440 / 8000)), 44 + i * 2);
  return data;
}

async function ask(page: Page, text = 'What can you help me with?') {
  await page.getByRole('textbox', { name: 'Message JARVIS' }).fill(text);
  await page.getByRole('button', { name: 'Send message to JARVIS' }).click();
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { status: 'ok', service: 'JARVIS', ai_connected: true } }));
  await page.route('**/api/speech/status', route => route.fulfill({ json: { available: true, voice: 'test-voice' } }));
  await page.route('**/api/chat', route => route.fulfill({ contentType: 'application/x-ndjson', body:
    '{"type":"delta","content":"I can answer questions and help you plan."}\n{"type":"done"}\n' }));
});

test('speech is opt-in; playback, waveform, pause, stop, and replay work', async ({ page }) => {
  let calls = 0;
  await page.route('**/api/speech/synthesize', route => { calls++; return route.fulfill({ contentType: 'audio/wav', body: wav(3) }); });
  await page.goto('/');
  const controls = page.locator('.speech-controls');
  const enable = page.getByRole('checkbox', { name: 'Enable spoken responses (local Piper)' });
  await expect(enable).not.toBeChecked();
  await ask(page);
  await expect(page.locator('.message-assistant')).toContainText('Complete');
  expect(calls).toBe(0);
  await enable.check();
  await page.getByRole('button', { name: 'Replay last response' }).click();
  await expect(controls.getByRole('status')).toHaveText('PLAYING');
  await expect.poll(async () => page.locator('.waveform i').first().evaluate(element => parseFloat((element as HTMLElement).style.height))).toBeGreaterThan(3);
  await page.getByRole('button', { name: 'Pause speech' }).click();
  await expect(controls.getByRole('status')).toHaveText('PAUSED');
  await page.getByRole('button', { name: 'Resume speech' }).click();
  await expect(controls.getByRole('status')).toHaveText('PLAYING');
  await page.getByRole('button', { name: 'Stop speech', exact: true }).click();
  await expect(controls.getByRole('status')).toHaveText('IDLE');
  await page.getByRole('button', { name: 'Replay last response' }).click();
  await expect(controls.getByRole('status')).toHaveText('PLAYING');
  await enable.uncheck();
  await expect(controls.getByRole('status')).toHaveText('IDLE');
});

test('stopping pending synthesis prevents stale audio from starting', async ({ page }) => {
  let release: () => void = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/speech/synthesize', async route => { await gate; await route.fulfill({ contentType: 'audio/wav', body: wav() }).catch(() => {}); });
  await page.goto('/');
  await page.getByRole('checkbox', { name: 'Enable spoken responses (local Piper)' }).check();
  await ask(page);
  await expect(page.locator('.speech-controls').getByRole('status')).toHaveText('GENERATING');
  await page.getByRole('button', { name: 'Stop speech', exact: true }).click();
  release();
  await expect(page.locator('.speech-controls').getByRole('status')).toHaveText('IDLE');
  await expect(page.getByRole('button', { name: 'Pause speech' })).toBeDisabled();
});

test('missing Piper never prevents displaying the actual AI text', async ({ page }) => {
  await page.route('**/api/speech/status', route => route.fulfill({ json: { available: false, message: 'Piper voice is missing. No download performed.' } }));
  await page.route('**/api/speech/synthesize', route => route.fulfill({ status: 503, json: { error: { message: 'Piper voice is missing.' } } }));
  await page.goto('/');
  await page.getByRole('checkbox', { name: 'Enable spoken responses (local Piper)' }).check();
  await expect(page.locator('.speech-error')).toContainText('Piper voice is missing');
  await ask(page);
  await expect(page.locator('.message-assistant')).toContainText('I can answer questions and help you plan.');
  await expect(page.locator('.speech-error')).toHaveText('Piper voice is missing.');
});

test('selected output is applied to the AudioContext that renders speech', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'enumerateDevices', { value: async () => [{ kind: 'audiooutput', deviceId: 'test-speakers', label: 'Test speakers' }] });
    Object.defineProperty(AudioContext.prototype, 'setSinkId', { value: async function(id: string) { (window as unknown as { selectedSink: string }).selectedSink = id; } });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Refresh outputs' }).click();
  await page.getByRole('combobox', { name: 'Audio output device' }).selectOption('test-speakers');
  expect(await page.evaluate(() => (window as unknown as { selectedSink: string }).selectedSink)).toBe('test-speakers');
});

test('full synthetic wake, acknowledgement, question, AI text, speech, and wake-resume flow', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: async () => {
      const context = new AudioContext({ sampleRate: 16000 });
      await context.resume();
      const oscillator = context.createOscillator();
      const destination = context.createMediaStreamDestination();
      oscillator.connect(destination); oscillator.start();
      return destination.stream;
    } });
  });
  await page.route('**/api/voice/status', route => route.fulfill({ json: { manual_available: true, wake_available: true } }));
  const spoken: string[] = [];
  await page.route('**/api/speech/synthesize', route => {
    spoken.push(route.request().postDataJSON().text);
    return route.fulfill({ contentType: 'audio/wav', body: wav(1) });
  });
  let channel: { send: (message: string) => void } | undefined;
  let resumes = 0;
  await page.routeWebSocket('**/api/voice/listen', socket => {
    channel = socket;
    socket.onMessage(message => {
      if (typeof message !== 'string') return;
      const control = JSON.parse(message);
      if (control.mode === 'wake' || control.type === 'resume') {
        if (control.type === 'resume') resumes++;
        socket.send(JSON.stringify({ type: 'state', state: 'listening' }));
      }
    });
  });
  await page.goto('/');
  await page.getByRole('checkbox', { name: 'Enable spoken responses (local Piper)' }).check();
  await page.getByRole('checkbox', { name: /I allow in-memory/ }).check();
  await page.getByRole('checkbox', { name: /Enable continuous/ }).check();
  await page.getByRole('button', { name: 'Start wake listening' }).click();
  await expect(page.locator('#voice').getByRole('status')).toHaveText('LISTENING');
  channel!.send(JSON.stringify({ type: 'state', state: 'recording' }));
  await expect(page.locator('.message-assistant')).toContainText('Yes, how can I help?');
  await expect(page.locator('#voice').getByRole('status')).toHaveText('RECORDING');
  channel!.send(JSON.stringify({ type: 'transcript', text: 'What can you help me with?' }));
  channel!.send(JSON.stringify({ type: 'state', state: 'paused' }));
  await expect(page.locator('.message-user')).toContainText('What can you help me with?');
  await expect(page.locator('.message-assistant').last()).toContainText('I can answer questions and help you plan.');
  await expect.poll(() => resumes).toBe(1);
  expect(spoken).toEqual(['Yes, how can I help?', 'I can answer questions and help you plan.']);
  await expect(page.locator('#voice').getByRole('status')).toHaveText('LISTENING');
  await page.getByRole('button', { name: 'Stop listening', exact: true }).click();
});
