import { test, expect } from '@playwright/test';

test('approved memories can be searched, edited, deleted, and disabled without auto-saving', async ({ page }) => {
  let settings = { enabled: false, save_history: false, allowed: true };
  let next = 0;
  let entries: { id: number; kind: string; content: string; created_at: string; updated_at: string }[] = [];
  await page.route('**/api/memory/**', route => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    if (url.pathname.endsWith('/settings')) {
      if (method === 'PUT') { const body = route.request().postDataJSON(); expect(body.approved).toBe(true); settings = { ...settings, enabled: body.enabled, save_history: body.enabled && body.save_history }; }
      return route.fulfill({ json: settings });
    }
    if (url.pathname.endsWith('/conversations')) return route.fulfill({ json: [] });
    const id = Number(url.pathname.split('/').at(-1));
    if (method === 'DELETE') {
      expect(url.searchParams.get('confirm')).toBe('true');
      entries = entries.filter(item => item.id !== id);
      return route.fulfill({ json: { deleted: true } });
    }
    if (method === 'POST' || method === 'PUT') {
      const body = route.request().postDataJSON();
      expect(body.approved).toBe(true);
      const item = { id: method === 'POST' ? ++next : id, kind: body.kind, content: body.content, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
      entries = [item, ...entries.filter(entry => entry.id !== item.id)];
      return route.fulfill({ status: method === 'POST' ? 201 : 200, json: item });
    }
    return route.fulfill({ json: entries.filter(item => item.content.includes(url.searchParams.get('q') || '')) });
  });
  await page.goto('/');
  await page.locator('.memory-panel summary').click();
  const enable = page.getByRole('checkbox', { name: 'Enable persistent memory', exact: true });
  await expect(enable).not.toBeChecked();
  await expect(page.getByRole('checkbox', { name: 'Save future conversation history' })).not.toBeChecked();
  await enable.check();
  await page.getByRole('combobox', { name: 'Memory category' }).selectOption('project');
  await page.getByRole('textbox', { name: 'Exact memory text' }).fill('Synthetic garden project');
  const approve = page.getByRole('checkbox', { name: /I reviewed this exact text/ });
  await expect(page.getByRole('button', { name: 'Approve and save memory' })).toBeDisabled();
  await approve.check();
  await page.getByRole('button', { name: 'Approve and save memory' }).click();
  await expect(page.locator('.saved-memory')).toContainText('Synthetic garden project');
  await page.getByRole('button', { name: 'Edit memory', exact: true }).click();
  await page.getByRole('textbox', { name: 'Exact memory text' }).fill('Updated synthetic garden project');
  await expect(approve).not.toBeChecked();
  await approve.check();
  await page.getByRole('button', { name: 'Approve and update memory' }).click();
  await expect(page.locator('.saved-memory')).toContainText('Updated synthetic garden project');
  await page.getByRole('textbox', { name: 'Search saved memory and history' }).fill('not-present');
  await page.getByRole('button', { name: 'Search saved data' }).click();
  await expect(page.locator('.saved-memory')).toHaveCount(0);
  await page.getByRole('textbox', { name: 'Search saved memory and history' }).fill('');
  await page.getByRole('button', { name: 'Search saved data' }).click();
  await expect(page.locator('.saved-memory')).toHaveCount(1);
  page.once('dialog', dialog => dialog.dismiss());
  await page.getByRole('button', { name: 'Delete memory', exact: true }).click();
  await expect(page.locator('.saved-memory')).toHaveCount(1);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Delete memory', exact: true }).click();
  await expect(page.locator('.saved-memory')).toHaveCount(0);
  await enable.uncheck();
  expect(settings.enabled).toBe(false);
});

test('history requires opt-in, carries stable session IDs, and explains a skipped sensitive turn', async ({ page }) => {
  let settings = { enabled: false, save_history: false, allowed: true };
  await page.route('**/api/health', route => route.fulfill({ json: { status: 'ok', service: 'JARVIS', ai_connected: true } }));
  await page.route('**/api/memory/**', route => {
    if (route.request().url().endsWith('/settings')) {
      if (route.request().method() === 'PUT') {
        const body = route.request().postDataJSON();
        settings = { ...settings, enabled: body.enabled, save_history: body.enabled && body.save_history };
      }
      return route.fulfill({ json: settings });
    }
    return route.fulfill({ json: [] });
  });
  const requests: { save_history?: boolean; conversation_id?: string; turn_id?: string }[] = [];
  await page.route('**/api/chat', route => {
    const body = route.request().postDataJSON(); requests.push(body);
    return route.fulfill({ contentType: 'application/x-ndjson', body:
      '{"type":"delta","content":"Test reply"}\n' + (body.save_history ? '{"type":"memory","status":"skipped_sensitive"}\n' : '') + '{"type":"done"}\n' });
  });
  await page.goto('/');
  await expect(page.locator('.connection-badge')).toHaveText('Backend online');
  const input = page.getByRole('textbox', { name: 'Message JARVIS' });
  await input.fill('Unsaved test question'); await input.press('Enter');
  await expect(page.locator('.message-assistant')).toContainText('Complete');
  expect(requests[0].save_history).toBeUndefined();
  await page.locator('.memory-panel summary').click();
  await page.getByRole('checkbox', { name: 'Enable persistent memory', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Save future conversation history' }).check();
  await input.fill('Synthetic sensitive turn'); await input.press('Enter');
  await expect(page.locator('.memory-notice')).toContainText('NOT saved');
  expect(requests[1].save_history).toBe(true);
  expect(requests[1].conversation_id).toMatch(/^[a-f0-9-]{36}$/);
  await expect(page.locator('.message-assistant').last()).toContainText('Complete');
  await input.fill('Another test turn'); await input.press('Enter');
  await expect.poll(() => requests.length).toBe(3);
  expect(requests[2].conversation_id).toBe(requests[1].conversation_id);
  expect(requests[2].turn_id).not.toBe(requests[1].turn_id);
});
