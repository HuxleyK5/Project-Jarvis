import { test, expect } from '@playwright/test';

test('connects to the real backend and reports actual model availability', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const response = await request.get('/api/health');
  expect(response.ok()).toBeTruthy();
  const health = await response.json();
  expect(health).toMatchObject({ status: 'ok', service: 'JARVIS', provider: 'ollama' });
  expect(typeof health.ai_connected).toBe('boolean');
  await page.goto('/');
  await expect(page.locator('.connection-badge')).toHaveText('Backend online');
  await expect(page.getByRole('button', { name: 'Start microphone' })).toBeEnabled();
  await expect(page.getByRole('checkbox', { name: /I allow in-memory/ })).not.toBeChecked();
  const send = page.getByRole('button', { name: 'Send message to JARVIS' });
  await expect(send).toBeDisabled();
  await page.getByRole('textbox', { name: 'Message JARVIS' }).fill('   ');
  await expect(send).toBeDisabled();
  if (!health.ai_connected) {
    await expect(page.getByText('Backend ready. AI model not connected.')).toBeVisible();
    await page.getByRole('textbox', { name: 'Message JARVIS' }).fill('Hello JARVIS');
    await send.click();
    await expect(page.locator('.chat-error')).toContainText(/Ollama|model/i, { timeout: 10000 });
    await expect(page.locator('.message-assistant')).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});

test('shows loading then offline error and recovers on refresh', async ({ page }) => {
  let release: () => void = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/health', async route => {
    await gate;
    await route.fulfill({ status: 503, body: 'Unavailable' });
  });
  await page.goto('/');
  await expect(page.locator('.connection-badge')).toHaveText('Connecting');
  await expect(page.getByRole('button', { name: 'Refresh backend status' })).toBeDisabled();
  release();
  await expect(page.locator('.connection-badge')).toHaveText('Backend offline');
  await expect(page.getByRole('alert')).toContainText('HTTP 503');
  await expect(page.locator('.system-row').filter({ hasText: 'AI model' })).toContainText('Unknown');
  await page.unroute('**/api/health');
  await page.getByRole('button', { name: 'Refresh backend status' }).click();
  await expect(page.locator('.connection-badge')).toHaveText('Backend online');
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('rejects malformed health data instead of showing a false connection', async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { status: 'ok' } }));
  await page.goto('/');
  await expect(page.locator('.connection-badge')).toHaveText('Backend offline');
  await expect(page.getByRole('alert')).toContainText('Unexpected health response');
});

test('automatically detects a lost connection and reconnects on the next poll', async ({ page }) => {
  await page.clock.install();
  await page.goto('/');
  await expect(page.locator('.connection-badge')).toHaveText('Backend online');
  await page.route('**/api/health', route => route.fulfill({ status: 503, body: 'Unavailable' }));
  await page.clock.fastForward(10000);
  await expect(page.locator('.connection-badge')).toHaveText('Backend offline');
  await page.unroute('**/api/health');
  await page.clock.fastForward(10000);
  await expect(page.locator('.connection-badge')).toHaveText('Backend online');
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
    await expect(page.locator('.connection-badge')).toHaveText('Backend online');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    await expect(page.getByRole('heading', { name: 'SYSTEM STATUS' })).toBeVisible();
    expect(await page.locator('.orbit-outer').evaluate(element => getComputedStyle(element).animationName)).toBe('none');
    if (width === 1440 || width === 390) {
      await page.screenshot({ path: `test-results/dashboard-${width}.png`, fullPage: true });
    }
  }
});
