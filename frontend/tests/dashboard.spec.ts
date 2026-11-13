import { test, expect } from '@playwright/test';

test('connects to the real FastAPI backend and stores typed messages honestly', async ({ page, request }) => {
  const errors: string[] = [];
  const requests: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  const health = await request.get('/api/health');
  expect(health.ok()).toBeTruthy();
  expect(await health.json()).toEqual({ status: 'ok', service: 'JARVIS', ai_connected: false });
  await page.goto('/');
  await expect(page.getByRole('status')).toHaveText('Backend online');
  await expect(page.getByText('Backend ready. AI model not connected.')).toBeVisible();
  await expect(page.getByRole('button', { name: /Microphone unavailable/ })).toBeDisabled();
  const save = page.getByRole('button', { name: 'Save message to session' });
  await expect(save).toBeDisabled();
  const input = page.getByRole('textbox', { name: 'Message JARVIS' });
  await input.fill('   ');
  await expect(save).toBeDisabled();
  await input.fill('Hello JARVIS');
  await input.press('Enter');
  await expect(page.getByRole('log', { name: 'Conversation history' }).getByText('Hello JARVIS')).toBeVisible();
  await expect(page.getByText('Saved locally · Not sent to AI')).toBeVisible();
  await expect(input).toHaveValue('');
  await input.fill('<script>alert("test")</script>');
  await save.click();
  await expect(page.locator('.message')).toHaveCount(2);
  await expect(page.getByRole('log', { name: 'Activity history' }).getByText('Message saved to this session · not sent')).toHaveCount(2);
  expect(errors).toEqual([]);
  expect(requests.filter(url => !url.startsWith('http://127.0.0.1:5173/'))).toEqual([]);
  expect(requests.some(url => /chat|message\?/.test(url))).toBeFalsy();
  await page.reload();
  await expect(page.locator('.message')).toHaveCount(0);
});

test('shows loading then offline error and recovers on refresh', async ({ page }) => {
  let release: () => void = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/health', async route => {
    await gate;
    await route.fulfill({ status: 503, body: 'Unavailable' });
  });
  await page.goto('/');
  await expect(page.getByRole('status')).toHaveText('Connecting');
  await expect(page.getByRole('button', { name: 'Refresh backend status' })).toBeDisabled();
  release();
  await expect(page.getByRole('status')).toHaveText('Backend offline');
  await expect(page.getByRole('alert')).toContainText('HTTP 503');
  await expect(page.locator('.system-row').filter({ hasText: 'AI model' })).toContainText('Unknown');
  await page.unroute('**/api/health');
  await page.getByRole('button', { name: 'Refresh backend status' }).click();
  await expect(page.getByRole('status')).toHaveText('Backend online');
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('rejects malformed health data instead of showing a false connection', async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { status: 'ok' } }));
  await page.goto('/');
  await expect(page.getByRole('status')).toHaveText('Backend offline');
  await expect(page.getByRole('alert')).toContainText('Unexpected health response');
});

test('automatically detects a lost connection and reconnects on the next poll', async ({ page }) => {
  await page.clock.install();
  await page.goto('/');
  await expect(page.getByRole('status')).toHaveText('Backend online');
  await page.route('**/api/health', route => route.fulfill({ status: 503, body: 'Unavailable' }));
  await page.clock.runFor(10000);
  await expect(page.getByRole('status')).toHaveText('Backend offline');
  await page.unroute('**/api/health');
  await page.clock.runFor(10000);
  await expect(page.getByRole('status')).toHaveText('Backend online');
});

test('times out an unresponsive backend', async ({ page }) => {
  await page.route('**/api/health', () => {});
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Connection timed out', { timeout: 6500 });
  await expect(page.getByRole('button', { name: 'Refresh backend status' })).toBeEnabled();
});

test('desktop and mobile layouts fit and honor reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const width of [1440, 1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/');
    await expect(page.getByRole('status')).toHaveText('Backend online');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    await expect(page.getByRole('heading', { name: 'SYSTEM STATUS' })).toBeVisible();
    expect(await page.locator('.orbit-outer').evaluate(element => getComputedStyle(element).animationName)).toBe('none');
    if (width === 1440 || width === 390) {
      await page.screenshot({ path: `test-results/dashboard-${width}.png`, fullPage: true });
    }
  }
});
