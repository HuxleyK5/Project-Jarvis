import { test, expect } from '@playwright/test';

const ready = { status: 'ok', service: 'JARVIS', ai_connected: true, provider: 'ollama', model: 'qwen3:4b', ai_status: 'ready', ai_message: 'Model installed' };
test.beforeEach(async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: ready }));
});

test('streams replies, sends follow-up context, and resets the session on reload', async ({ page }) => {
  const requests: { messages: { role: string; content: string }[] }[] = [];
  await page.route('**/api/chat', route => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({ contentType: 'application/x-ndjson', body:
      JSON.stringify({ type: 'delta', content: 'Hello ' }) + '\n'
      + JSON.stringify({ type: 'delta', content: '世界 <script>test</script>' }) + '\n'
      + JSON.stringify({ type: 'done', model: 'qwen3:4b' }) + '\n' });
  });
  await page.goto('/');
  await expect(page.locator('.connection-badge')).toHaveText('Backend online');
  const input = page.getByRole('textbox', { name: 'Message JARVIS' });
  await input.fill('My name is Alex');
  await input.press('Enter');
  await expect(page.locator('.message-assistant')).toContainText('Hello 世界 <script>test</script>');
  await expect(page.locator('.message-assistant')).toContainText('Local AI · Complete');
  await expect(page.locator('.message-assistant script')).toHaveCount(0);
  await input.fill('What is my name?');
  await input.press('Enter');
  await expect(page.locator('.message-assistant')).toHaveCount(2);
  expect(requests[1].messages).toEqual([
    { role: 'user', content: 'My name is Alex' },
    { role: 'assistant', content: 'Hello 世界 <script>test</script>' },
    { role: 'user', content: 'What is my name?' },
  ]);
  await page.reload();
  await expect(page.locator('.message')).toHaveCount(0);
});

test('preserves partial output but excludes failed turns from follow-up context', async ({ page }) => {
  const requests: { messages: { role: string; content: string }[] }[] = [];
  await page.route('**/api/chat', route => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({ contentType: 'application/x-ndjson', body:
      '{"type":"delta","content":"Partial response"}\n{"type":"error","error":{"message":"Ollama connection lost"}}\n' });
  });
  await page.goto('/');
  await expect(page.locator('.connection-badge')).toHaveText('Backend online');
  const input = page.getByRole('textbox', { name: 'Message JARVIS' });
  await input.fill('First question');
  await input.press('Enter');
  await expect(page.locator('.chat-error')).toHaveText('Ollama connection lost');
  await expect(page.locator('.message-assistant')).toContainText('Incomplete · Excluded from context');
  await input.fill('New question');
  await input.press('Enter');
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1].messages).toEqual([{ role: 'user', content: 'New question' }]);
});

test('stops a pending response and permits another message', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await page.route('**/api/chat', () => {});
  await page.goto('/');
  await expect(page.locator('.connection-badge')).toHaveText('Backend online');
  await page.getByRole('textbox', { name: 'Message JARVIS' }).fill('Slow question');
  await page.getByRole('button', { name: 'Send message to JARVIS' }).click();
  await expect(page.getByRole('button', { name: 'Stop response' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await expect(page.getByRole('button', { name: 'Send message to JARVIS' })).toBeDisabled();
  await page.getByRole('button', { name: 'Stop response' }).click();
  await expect(page.locator('.chat-error')).toContainText('Response stopped');
  await page.getByRole('textbox', { name: 'Message JARVIS' }).fill('Another question');
  await expect(page.getByRole('button', { name: 'Send message to JARVIS' })).toBeEnabled();
});

test('does not treat a truncated stream as a completed reply', async ({ page }) => {
  await page.route('**/api/chat', route => route.fulfill({ contentType: 'application/x-ndjson', body:
    '{"type":"delta","content":"Interrupted answer"}\n' }));
  await page.goto('/');
  await expect(page.locator('.connection-badge')).toHaveText('Backend online');
  await page.getByRole('textbox', { name: 'Message JARVIS' }).fill('Hello');
  await page.getByRole('button', { name: 'Send message to JARVIS' }).click();
  await expect(page.locator('.chat-error')).toContainText('ended before completion');
  await expect(page.locator('.message-assistant')).toContainText('Incomplete · Excluded from context');
});
