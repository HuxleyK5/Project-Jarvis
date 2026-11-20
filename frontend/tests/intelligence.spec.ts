import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { status: 'ok', service: 'JARVIS', ai_connected: true } }));
});

test('long session summaries retain sourced older context, stay temporary, and can be cleared', async ({ page }) => {
  const bodies: { messages: { role: string; content: string }[]; context_summary?: string; save_history?: boolean }[] = [];
  await page.route('**/api/chat', route => {
    bodies.push(route.request().postDataJSON());
    return route.fulfill({ contentType: 'application/x-ndjson', body: '{"type":"delta","content":"Synthetic reply"}\n{"type":"done"}\n' });
  });
  await page.goto('/');
  await expect(page.locator('.connection-badge')).toHaveText('Backend online');
  const input = page.getByRole('textbox', { name: 'Message JARVIS' });
  for (let index = 0; index < 12; index++) {
    await input.fill(index === 0 ? 'My synthetic project is Garden Beacon' : `Follow-up test ${index}`);
    await input.press('Enter');
    await expect(page.locator('.message-assistant')).toHaveCount(index + 1);
    await expect(page.locator('.message-assistant').last()).toContainText('Complete');
  }
  expect(bodies[11].context_summary).toContain('User stated: My synthetic project is Garden Beacon');
  expect(bodies[11].context_summary).toContain('Assistant previously replied (unverified)');
  expect(bodies[11].messages.length).toBeLessThanOrEqual(21);
  expect(bodies.every(body => !body.save_history)).toBeTruthy();
  await page.locator('.session-context summary').click();
  await expect(page.locator('.session-context pre')).toContainText('Garden Beacon');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Clear older session summary' }).click();
  await expect(page.locator('.session-context pre')).toHaveCount(0);
  await page.reload();
  await expect(page.locator('.message')).toHaveCount(0);
});

test('session personality is configurable without silently saving preferences', async ({ page }) => {
  let captured: { assistant_preferences?: { tone: string; detail: string } } | null = null;
  await page.route('**/api/memory/settings', route => route.fulfill({ json: { enabled: false, save_history: false, allowed: true } }));
  await page.route('**/api/chat', route => {
    captured = route.request().postDataJSON();
    return route.fulfill({ contentType: 'application/x-ndjson', body: '{"type":"delta","content":"Synthetic reply"}\n{"type":"done"}\n' });
  });
  await page.goto('/');
  await page.locator('.assistant-preferences summary').click();
  await page.getByRole('combobox', { name: 'Assistant tone' }).selectOption('friendly');
  await page.getByRole('combobox', { name: 'Answer detail' }).selectOption('detailed');
  await expect(page.getByRole('button', { name: 'Save assistant preferences' })).toBeDisabled();
  await page.getByRole('textbox', { name: 'Message JARVIS' }).fill('Hello');
  await page.getByRole('button', { name: 'Send message to JARVIS' }).click();
  await expect.poll(() => captured?.assistant_preferences).toEqual({ tone: 'friendly', detail: 'detailed' });
});

test('archive recall and persistent style require separate explicit approval', async ({ page }) => {
  let config = { enabled: true, save_history: false, allowed: true, recall_history: false };
  let saved: unknown;
  await page.route('**/api/memory/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/settings')) {
      if (route.request().method() === 'PUT') config = { ...config, ...route.request().postDataJSON() };
      return route.fulfill({ json: config });
    }
    if (path.endsWith('/personality')) {
      if (route.request().method() === 'PUT') { saved = route.request().postDataJSON(); return route.fulfill({ json: saved }); }
      return route.fulfill({ json: { tone: 'professional', detail: 'balanced' } });
    }
    return route.fulfill({ json: [] });
  });
  await page.goto('/');
  await page.locator('.memory-panel summary').click();
  const recall = page.getByRole('checkbox', { name: 'Recall previous conversations' });
  await expect(recall).not.toBeChecked();
  await recall.check();
  await expect.poll(() => config.recall_history).toBe(true);
  await page.locator('.assistant-preferences summary').click();
  await page.getByRole('combobox', { name: 'Assistant tone' }).selectOption('formal');
  const save = page.getByRole('button', { name: 'Save assistant preferences' });
  await expect(save).toBeDisabled();
  await page.getByRole('checkbox', { name: /I approve saving this exact tone/ }).check();
  await save.click();
  expect(saved).toEqual({ tone: 'formal', detail: 'balanced', approved: true });
  await page.getByRole('checkbox', { name: 'Enable persistent memory', exact: true }).uncheck();
  await expect(recall).not.toBeChecked();
  await expect(page.getByRole('combobox', { name: 'Assistant tone' })).toHaveValue('professional');
});
