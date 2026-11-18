import { test, expect, type Page } from '@playwright/test';

const status = { manual_available: true, wake_available: true, wake_phrase: 'Hey JARVIS', message: 'Test assets' };

async function syntheticMicrophone(page: Page) {
  // Oscillator -> MediaStreamDestination. Never opens a physical microphone or plays sound.
  await page.addInitScript(() => {
    const state = window as unknown as { testTrack?: MediaStreamTrack; micRequests: number };
    state.micRequests = 0;
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: async () => {
      state.micRequests++;
      const context = new AudioContext({ sampleRate: 48000 });
      await context.resume();
      const oscillator = context.createOscillator();
      const destination = context.createMediaStreamDestination();
      oscillator.connect(destination);
      oscillator.start();
      state.testTrack = destination.stream.getAudioTracks()[0];
      return destination.stream;
    } });
  });
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { status: 'ok', service: 'JARVIS', ai_connected: false } }));
});

test('requires session consent and reports missing assets without opening the microphone', async ({ page }) => {
  await syntheticMicrophone(page);
  await page.route('**/api/voice/status', route => route.fulfill({ json: { manual_available: false, wake_available: false, message: 'Voice models are missing. No downloads occur automatically.' } }));
  await page.goto('/');
  const consent = page.getByRole('checkbox', { name: /I allow in-memory/ });
  await expect(consent).not.toBeChecked();
  await expect(page.getByRole('checkbox', { name: /Enable continuous/ })).not.toBeChecked();
  await expect(page.getByRole('button', { name: 'Record one command' })).toBeDisabled();
  await page.getByRole('button', { name: 'Start microphone' }).click();
  await expect(page.locator('.voice-error')).toContainText('session microphone consent');
  await consent.check();
  await page.getByRole('button', { name: 'Record one command' }).click();
  await expect(page.locator('.voice-error')).toContainText('Voice models are missing');
  expect(await page.evaluate(() => (window as unknown as { micRequests: number }).micRequests)).toBe(0);
});

test('explains browser permission denial', async ({ page }) => {
  await page.route('**/api/voice/status', route => route.fulfill({ json: status }));
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: async () => { throw new DOMException('Denied in test', 'NotAllowedError'); } });
  });
  await page.goto('/');
  await page.getByRole('checkbox', { name: /I allow in-memory/ }).check();
  await page.getByRole('button', { name: 'Record one command' }).click();
  await expect(page.locator('.voice-error')).toContainText('Microphone permission denied');
  await expect(page.getByRole('button', { name: 'Stop listening' })).toBeDisabled();
});

test('manual audio frames lead to visible voice text and the existing chat API', async ({ page }) => {
  await syntheticMicrophone(page);
  await page.route('**/api/voice/status', route => route.fulfill({ json: status }));
  let frames = 0;
  let hello: unknown;
  await page.routeWebSocket('**/api/voice/listen', socket => {
    socket.onMessage(data => {
      if (typeof data !== 'string') { expect(data.byteLength).toBe(2560); frames++; return; }
      const message = JSON.parse(data);
      if (message.mode) { hello = message; socket.send(JSON.stringify({ type: 'state', state: 'recording' })); }
      if (message.type === 'finish') {
        socket.send(JSON.stringify({ type: 'state', state: 'transcribing' }));
        socket.send(JSON.stringify({ type: 'transcript', text: 'Synthetic voice test question' }));
      }
    });
  });
  let sent: { messages: { role: string; content: string }[] } | null = null;
  await page.route('**/api/chat', route => {
    sent = route.request().postDataJSON();
    return route.fulfill({ contentType: 'application/x-ndjson', body: '{"type":"delta","content":"Test reply"}\n{"type":"done"}\n' });
  });
  await page.goto('/');
  await page.getByRole('checkbox', { name: /I allow in-memory/ }).check();
  await page.getByRole('button', { name: 'Record one command' }).click();
  await expect.poll(() => frames).toBeGreaterThan(0);
  expect(hello).toEqual({ consent: true, mode: 'manual' });
  await page.getByRole('button', { name: 'Finish and transcribe' }).click();
  await expect(page.locator('.message-user')).toContainText('YOU · VOICE');
  await expect(page.locator('.message-user')).toContainText('Synthetic voice test question');
  await expect(page.locator('.recognized-speech')).toContainText('Synthetic voice test question');
  expect(sent).toEqual({ messages: [{ role: 'user', content: 'Synthetic voice test question' }] });
  expect(await page.evaluate(() => (window as unknown as { testTrack: MediaStreamTrack }).testTrack.readyState)).toBe('ended');
});

test('continuous listening is opt-in and disabling it releases the microphone', async ({ page }) => {
  await syntheticMicrophone(page);
  await page.route('**/api/voice/status', route => route.fulfill({ json: status }));
  let frames = 0;
  await page.routeWebSocket('**/api/voice/listen', socket => socket.onMessage(data => {
    if (typeof data !== 'string') { frames++; return; }
    if (JSON.parse(data).mode === 'wake') socket.send(JSON.stringify({ type: 'state', state: 'listening' }));
  }));
  await page.goto('/');
  await page.getByRole('checkbox', { name: /I allow in-memory/ }).check();
  const continuous = page.getByRole('checkbox', { name: /Enable continuous/ });
  await continuous.check();
  await page.getByRole('button', { name: 'Start wake listening' }).click();
  await expect.poll(() => frames).toBeGreaterThan(0);
  await continuous.uncheck();
  await expect(page.getByRole('button', { name: 'Stop listening' })).toBeDisabled();
  expect(await page.evaluate(() => (window as unknown as { testTrack: MediaStreamTrack }).testTrack.readyState)).toBe('ended');
});

test('withdrawing consent stops an active microphone', async ({ page }) => {
  await syntheticMicrophone(page);
  await page.route('**/api/voice/status', route => route.fulfill({ json: status }));
  await page.routeWebSocket('**/api/voice/listen', socket => socket.onMessage(data => {
    if (typeof data === 'string' && JSON.parse(data).mode) socket.send(JSON.stringify({ type: 'state', state: 'recording' }));
  }));
  await page.goto('/');
  const consent = page.getByRole('checkbox', { name: /I allow in-memory/ });
  await consent.check();
  await page.getByRole('button', { name: 'Record one command' }).click();
  await expect(page.getByRole('button', { name: 'Finish and transcribe' })).toBeVisible();
  await consent.uncheck();
  expect(await page.evaluate(() => (window as unknown as { testTrack: MediaStreamTrack }).testTrack.readyState)).toBe('ended');
  await expect(page.getByRole('button', { name: 'Record one command' })).toBeDisabled();
});
