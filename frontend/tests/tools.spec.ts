import { test, expect } from '@playwright/test';

test('real backend: permission approval, exact preview, execution result, activity and revocation', async ({ page, request }) => {
  // This test only runs the read-only system-info tool, never apps or websites.
  const session = await (await request.get('/api/tools/session')).json();
  const headers = { 'X-Jarvis-Tool-Token': session.token };
  await request.put('/api/tools/policy', { headers, data: { approved: true, enabled: false } });
  try {
    await page.goto('/');
    await page.locator('.tool-controls summary').click();
    await expect(page.getByRole('button', { name: 'Preview action', exact: true })).toBeDisabled();
    await page.getByRole('checkbox', { name: 'Enable computer tools', exact: true }).check();
    await expect(page.getByRole('button', { name: 'Apply approved permissions' })).toBeDisabled();
    await page.getByRole('checkbox', { name: /I approve these session permissions/ }).check();
    await page.getByRole('button', { name: 'Apply approved permissions' }).click();
    await expect(page.locator('.tool-controls summary')).toContainText('SESSION ENABLED');
    await page.getByRole('button', { name: 'Preview action', exact: true }).click();
    const preview = page.getByRole('region', { name: 'Tool action preview' });
    await expect(preview).toContainText('system_info · pending');
    await expect(page.getByRole('button', { name: 'Run approved action' })).toBeDisabled();
    await expect(page.getByLabel('Tool result', { exact: true })).toHaveCount(0);
    await page.getByRole('checkbox', { name: 'I approve this exact action' }).check();
    await page.getByRole('button', { name: 'Run approved action' }).click();
    await expect(preview).toContainText('system_info · completed');
    await expect(page.getByLabel('Tool result', { exact: true })).toContainText('workspace_disk_free_bytes');
    await expect(page.getByRole('log', { name: 'Activity history' })).toContainText('Tool system_info: completed');
    await page.getByRole('button', { name: 'Dismiss action result' }).click();
    await page.getByRole('button', { name: 'Preview action', exact: true }).click();
    await page.getByRole('button', { name: 'Cancel action', exact: true }).click();
    await expect(preview).toContainText('cancelled');
    await page.getByRole('button', { name: 'Disable tools and revoke access' }).click();
    await expect(page.locator('.tool-controls summary')).toContainText('DISABLED');
    await expect(page.getByRole('button', { name: 'Preview action', exact: true })).toBeDisabled();
  } finally {
    await request.put('/api/tools/policy', { headers, data: { approved: true, enabled: false } });
  }
});

test('AI tool proposal requires approval and unavailable model errors remain honest', async ({ page }) => {
  let executed = 0;
  let configured = false;
  const job = { id: 'synthetic-job', tool: 'system_info', arguments: {}, status: 'pending', result: null, error: null };
  await page.route('**/api/tools/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/session')) return route.fulfill({ json: { token: 'test-token', catalog: [{ name: 'system_info', description: 'Basic system details.', input_schema: {} }] } });
    if (path.endsWith('/policy')) {
      if (route.request().method() === 'PUT') configured = route.request().postDataJSON().enabled;
      return route.fulfill({ json: { enabled: configured, roots: {}, applications: [], websites: {} } });
    }
    if (path.endsWith('/plan')) {
      if (route.request().postDataJSON().question === 'unavailable') return route.fulfill({ status: 503, json: { error: { message: 'Ollama is unavailable. No action was executed.' } } });
      return route.fulfill({ json: { proposal: job } });
    }
    if (path.endsWith('/activity')) return route.fulfill({ json: [] });
    if (path.endsWith('/cancel')) { job.status = 'cancelled'; return route.fulfill({ json: job }); }
    if (path.endsWith('/execute')) executed++;
    return route.fulfill({ json: job });
  });
  await page.goto('/');
  await page.locator('.tool-controls summary').click();
  await page.getByRole('checkbox', { name: 'Enable computer tools', exact: true }).check();
  await page.getByRole('checkbox', { name: /I approve these session permissions/ }).check();
  await page.getByRole('button', { name: 'Apply approved permissions' }).click();
  await page.getByRole('textbox', { name: 'Tool request', exact: true }).fill('Show system info');
  await page.getByRole('button', { name: 'Ask JARVIS to select a tool' }).click();
  await expect(page.getByRole('region', { name: 'Tool action preview' })).toContainText('pending');
  await expect(page.getByRole('button', { name: 'Run approved action' })).toBeDisabled();
  expect(executed).toBe(0);
  await page.getByRole('button', { name: 'Cancel action', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Tool action preview' })).toContainText('cancelled');
  await page.getByRole('textbox', { name: 'Tool request', exact: true }).fill('unavailable');
  await page.getByRole('button', { name: 'Ask JARVIS to select a tool' }).click();
  await expect(page.locator('.tool-controls .memory-notice')).toContainText('Ollama is unavailable');
  expect(executed).toBe(0);
});
