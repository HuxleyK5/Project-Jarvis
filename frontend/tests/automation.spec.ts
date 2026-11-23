import { test, expect } from '@playwright/test';

test('real backend executes an approved automatic multi-step workflow and persists metadata', async ({ page, request }) => {
  const session = await (await request.get('/api/tools/session')).json();
  const headers = { 'X-Jarvis-Tool-Token': session.token };
  const reset = async () => {
    await request.put('/api/automation/policy', { headers, data: { enabled: false, automatic_tools: [], approved: true } });
    await request.put('/api/tools/policy', { headers, data: { enabled: false, approved: true } });
  };
  await reset();
  await request.put('/api/tools/policy', { headers, data: { enabled: true, approved: true } });
  try {
    await page.goto('/');
    await page.locator('.automation-controls > summary').click();
    await expect(page.getByRole('button', { name: 'Generate workflow plan' })).toBeDisabled();
    await page.getByRole('checkbox', { name: 'Enable automation for this backend session' }).check();
    await page.getByRole('checkbox', { name: 'Allow automatic system_info', exact: true }).check();
    await expect(page.getByRole('button', { name: 'Apply workflow permissions' })).toBeDisabled();
    await page.getByRole('checkbox', { name: 'I approve workflow permissions and local metadata history' }).check();
    await page.getByRole('button', { name: 'Apply workflow permissions' }).click();
    await expect(page.locator('.automation-controls > summary')).toContainText('SESSION ENABLED');
    await page.getByText('Manual structured plan (works without AI)', { exact: true }).click();
    await page.getByRole('button', { name: 'Preview structured workflow' }).click();
    const plan = page.getByRole('region', { name: 'Workflow plan', exact: true });
    await expect(plan).toContainText('Check workstation twice · planned');
    await expect(plan.locator('.workflow-steps > li')).toHaveCount(2);
    await expect(plan).toContainText('automatic · pending');
    await page.getByRole('button', { name: 'Start workflow', exact: true }).click();
    await expect(plan).toContainText('Check workstation twice · completed');
    await expect(plan).toContainText('Completed steps: 1, 2. Incomplete steps: none.');
    await expect(plan).toContainText('System information returned');
    await expect(page.getByRole('log', { name: 'Activity history' })).toContainText(/Workflow .+: completed/);
    await page.locator('.workflow-history > summary').click();
    await expect(page.locator('.workflow-history')).toContainText('2/2 complete');
    await page.getByRole('button', { name: 'Disable automation and cancel workflows' }).click();
    await expect(page.locator('.automation-controls > summary')).toContainText('DISABLED');
    await expect(page.getByRole('button', { name: 'Preview structured workflow' })).toBeDisabled();
  } finally { await reset(); }
});

test('confirmation applies to the exact full plan, blocked plans cannot start, and previews can be cancelled', async ({ page, request }) => {
  const session = await (await request.get('/api/tools/session')).json();
  const headers = { 'X-Jarvis-Tool-Token': session.token };
  await request.put('/api/tools/policy', { headers, data: { enabled: true, approved: true } });
  await request.put('/api/automation/policy', { headers, data: { enabled: true, automatic_tools: [], approved: true } });
  try {
    await page.goto('/');
    await page.locator('.automation-controls > summary').click();
    await page.getByText('Manual structured plan (works without AI)', { exact: true }).click();
    await page.getByRole('textbox', { name: 'Explicit workflow plan' }).fill(JSON.stringify({ outcome: 'Needs exact confirmation', steps: [{ tool: 'system_info', arguments: {} }] }));
    await page.getByRole('button', { name: 'Preview structured workflow' }).click();
    const plan = page.getByRole('region', { name: 'Workflow plan', exact: true });
    await expect(plan).toContainText('confirmation required · pending');
    await expect(page.getByRole('button', { name: 'Start workflow', exact: true })).toBeDisabled();
    await page.getByRole('checkbox', { name: 'I approve this exact ordered workflow, including significant actions' }).check();
    await expect(page.getByRole('button', { name: 'Start workflow', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: 'Cancel workflow', exact: true }).click();
    await expect(plan).toContainText('Needs exact confirmation · cancelled');
    await expect(plan).toContainText('Completed steps: none. Incomplete steps: 1.');
    await page.getByRole('textbox', { name: 'Explicit workflow plan' }).fill(JSON.stringify({ outcome: 'Blocked test', steps: [{ tool: 'system_info', arguments: {} }, { tool: 'shell', arguments: { command: 'never' } }] }));
    await page.getByRole('button', { name: 'Preview structured workflow' }).click();
    await expect(plan).toContainText('Blocked test · blocked');
    await expect(plan).toContainText('system_info · confirmation required · skipped');
    await expect(plan.getByRole('button', { name: 'Start workflow', exact: true })).toHaveCount(0);
  } finally {
    await request.put('/api/automation/policy', { headers, data: { enabled: false, automatic_tools: [], approved: true } });
    await request.put('/api/tools/policy', { headers, data: { enabled: false, approved: true } });
  }
});

test('natural-language planning displays steps and honest model errors without auto-execution', async ({ page }) => {
  let starts = 0;
  const workflows: object[] = [];
  const flow = { id: 'synthetic-workflow', outcome: 'Synthetic AI plan', status: 'planned', requires_confirmation: true, scheduled_for: null, error: null,
    steps: [{ number: 1, tool: 'system_info', arguments: {}, category: 'confirmation_required', status: 'pending', result: null, verification: null, error: null }], report: { completed: [], incomplete: [1] } };
  await page.route('**/api/automation/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/policy')) return route.fulfill({ json: { enabled: true, automatic_tools: [], eligible_automatic_tools: ['system_info'], scheduler_available: false } });
    if (path.endsWith('/workflows')) return route.fulfill({ json: workflows });
    if (path.endsWith('/history')) return route.fulfill({ json: [] });
    if (path.endsWith('/plan')) {
      if (route.request().postDataJSON().question === 'unavailable') return route.fulfill({ status: 503, json: { error: { message: 'Ollama is unavailable; nothing was executed.' } } });
      workflows.push(flow);
      return route.fulfill({ json: { workflow: flow } });
    }
    if (path.endsWith('/start')) starts++;
    return route.fulfill({ json: flow });
  });
  await page.goto('/');
  await page.locator('.automation-controls > summary').click();
  await page.getByRole('textbox', { name: 'Workflow instruction' }).fill('Check system information');
  await page.getByRole('button', { name: 'Generate workflow plan' }).click();
  await expect(page.getByRole('region', { name: 'Workflow plan', exact: true })).toContainText('Synthetic AI plan');
  await expect(page.getByRole('button', { name: 'Start workflow', exact: true })).toBeDisabled();
  expect(starts).toBe(0);
  await page.getByRole('textbox', { name: 'Workflow instruction' }).fill('unavailable');
  await page.getByRole('button', { name: 'Generate workflow plan' }).click();
  await expect(page.locator('.automation-controls .memory-notice')).toContainText('Ollama is unavailable');
  expect(starts).toBe(0);
});
