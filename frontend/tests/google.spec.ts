import { test, expect, type Page } from '@playwright/test';

const services = ['calendar', 'gmail', 'classroom'];
const connected = () => services.map(service => ({ service, enabled: true, write: service !== 'classroom', send: service === 'gmail', role: 'student', status: 'connected', client_configured: true, saved_authorization: true, requested_scopes: ['https://www.googleapis.com/auth/synthetic-test-scope'], connection_verified: false }));

async function mockGoogle(page: Page, extra: (path: string, body: any, method: string) => unknown) {
  await page.route('**/api/integrations/google/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/integrations/google', '');
    const body = route.request().postData() ? route.request().postDataJSON() : null;
    if (path === '/status') return route.fulfill({ json: connected() });
    const value = extra(path, body, route.request().method());
    if (value && typeof value === 'object' && 'httpError' in value) return route.fulfill({ status: 403, json: { error: { message: (value as { httpError: string }).httpError } } });
    return route.fulfill({ json: value || {} });
  });
}

test('real backend integrations default off and missing OAuth setup never appears connected', async ({ page, request }) => {
  const session = await (await request.get('/api/tools/session')).json();
  const headers = { 'X-Jarvis-Tool-Token': session.token };
  const initial = await (await request.get('/api/integrations/google/status', { headers })).json();
  expect(initial.every((item: { enabled: boolean }) => !item.enabled)).toBeTruthy();
  try {
    await page.goto('/');
    await page.locator('.google-controls > summary').click();
    const calendar = page.getByRole('region', { name: 'Google calendar integration', exact: true });
    await expect(calendar).toContainText('DISABLED');
    await expect(calendar.getByRole('button', { name: 'Connect or renew Google calendar' })).toBeDisabled();
    await calendar.getByRole('checkbox', { name: 'Enable Google calendar', exact: true }).check();
    await expect(calendar.getByRole('button', { name: 'Apply calendar capabilities' })).toBeDisabled();
    await calendar.getByRole('checkbox', { name: /I approve these calendar capabilities/ }).check();
    await calendar.getByRole('button', { name: 'Apply calendar capabilities' }).click();
    if (!initial[0].client_configured) {
      await expect(calendar).toContainText('SETUP REQUIRED');
      await expect(calendar.getByRole('button', { name: 'Connect or renew Google calendar' })).toBeDisabled();
      await expect(calendar.getByRole('button', { name: 'Load upcoming Google events' })).toHaveCount(0);
    }
    await calendar.getByRole('checkbox', { name: 'Enable Google calendar', exact: true }).uncheck();
    await calendar.getByRole('checkbox', { name: /I approve these calendar capabilities/ }).check();
    await calendar.getByRole('button', { name: 'Apply calendar capabilities' }).click();
    await expect(calendar).toContainText('DISABLED');
  } finally {
    await request.put('/api/integrations/google/calendar/settings', { headers, data: { enabled: false, approved: true } });
  }
});

test('Calendar event proposal shows exact data and requires confirmation before a write', async ({ page }) => {
  let writes = 0;
  let proposal: any;
  await mockGoogle(page, (path, body) => {
    if (path === '/calendar/events') return { events: [{ id: 'synthetic-event', summary: 'Synthetic source event', start: { dateTime: '2026-12-01T10:00:00Z' }, end: { dateTime: '2026-12-01T11:00:00Z' } }], has_more: false };
    if (path === '/calendar/proposals') { proposal = { id: 'calendar-proposal', service: 'calendar', action: 'create_event', payload: body, status: 'pending', result: null, error: null }; return proposal; }
    if (path.endsWith('/execute')) { writes++; proposal = { ...proposal, status: 'completed', result: { event_id: 'synthetic-created' } }; return proposal; }
    if (path.startsWith('/proposals/')) return proposal;
    return null;
  });
  await page.goto('/'); await page.locator('.google-controls > summary').click();
  const calendar = page.getByRole('region', { name: 'Google calendar integration', exact: true });
  await calendar.getByRole('button', { name: 'Load upcoming Google events' }).click();
  await expect(calendar).toContainText('Synthetic source event');
  await calendar.getByRole('textbox', { name: 'Google event title' }).fill('Synthetic proposed event');
  await calendar.getByLabel('Google event start', { exact: true }).fill('2026-12-02T10:00');
  await calendar.getByLabel('Google event end', { exact: true }).fill('2026-12-02T11:00');
  await calendar.getByRole('button', { name: 'Preview Google event' }).click();
  const preview = calendar.getByRole('region', { name: 'Google calendar action preview' });
  await expect(preview).toContainText('Synthetic proposed event');
  await expect(preview.getByRole('button', { name: 'Execute confirmed Google action' })).toBeDisabled();
  expect(writes).toBe(0);
  await calendar.getByRole('textbox', { name: 'Google event title' }).fill('Unproposed edits do not alter snapshot');
  await preview.getByRole('checkbox', { name: 'I confirm this exact Google create event action' }).check();
  await preview.getByRole('button', { name: 'Execute confirmed Google action' }).click();
  await expect(preview).toContainText('completed');
  expect(writes).toBe(1);
  expect(proposal.payload.title).toBe('Synthetic proposed event');
});

test('Gmail reads escaped content, summarizes only with consent, and confirms sending separately from drafts', async ({ page }) => {
  let sends = 0, drafts = 0, summaries = 0;
  let proposal: any;
  const mail = { id: 'msg1', thread_id: 'thread1', subject: 'Synthetic email subject', from: 'sender@example.org', to: 'recipient@example.org', date: 'Synthetic date', text: '<img src="https://example.org/no-fetch"> Synthetic plain email', snippet: '', plain_text_available: true };
  await mockGoogle(page, (path, body) => {
    if (path === '/gmail/messages') return { messages: [{ id: 'msg1', threadId: 'thread1' }], next_page_token: null };
    if (path === '/gmail/messages/msg1') return mail;
    if (path === '/gmail/threads/thread1') return { messages: [mail] };
    if (path.endsWith('/summarize')) { summaries++; expect(body.approved).toBe(true); return { summary: 'Synthetic isolated summary' }; }
    if (path.startsWith('/gmail/proposals/')) { proposal = { id: 'mail-proposal', service: 'gmail', action: path.split('/').at(-1), payload: body, status: 'pending', result: null, error: null }; return proposal; }
    if (path.endsWith('/execute')) { if (proposal.action === 'create_draft') drafts++; else sends++; proposal = { ...proposal, status: 'completed', result: { message_id: 'synthetic-result' } }; return proposal; }
    if (path.startsWith('/proposals/')) return proposal;
    return null;
  });
  await page.goto('/'); await page.locator('.google-controls > summary').click();
  const gmail = page.getByRole('region', { name: 'Google gmail integration', exact: true });
  await gmail.getByRole('button', { name: 'Search authorized Gmail' }).click();
  await gmail.getByRole('button', { name: 'Read message msg1', exact: true }).click();
  await expect(gmail).toContainText('Synthetic email subject');
  await expect(gmail.locator('img')).toHaveCount(0);
  await expect(gmail.getByRole('button', { name: 'Summarize selected Gmail conversation locally' })).toBeDisabled();
  await gmail.getByRole('checkbox', { name: 'I approve sending this selected conversation to local Ollama for a summary' }).check();
  await gmail.getByRole('button', { name: 'Summarize selected Gmail conversation locally' }).click();
  await expect(gmail).toContainText('Synthetic isolated summary');
  expect(summaries).toBe(1); expect(sends).toBe(0);
  await gmail.getByRole('textbox', { name: 'Google email recipients' }).fill('recipient@example.org');
  await gmail.getByRole('textbox', { name: 'Google email subject' }).fill('Synthetic draft subject');
  await gmail.getByRole('textbox', { name: 'Google email body' }).fill('Synthetic draft body');
  await gmail.getByRole('button', { name: 'Preview Gmail draft' }).click();
  const preview = gmail.getByRole('region', { name: 'Google gmail action preview' });
  await preview.getByRole('checkbox', { name: 'I confirm this exact Google create draft action' }).check();
  await preview.getByRole('button', { name: 'Execute confirmed Google action' }).click();
  await expect(preview).toContainText('completed');
  expect(drafts).toBe(1); expect(sends).toBe(0);
  await gmail.getByRole('button', { name: 'Preview Gmail send' }).click();
  await expect(preview.getByRole('button', { name: 'Execute confirmed Google action' })).toBeDisabled();
  await preview.getByRole('checkbox', { name: 'I confirm this exact Google send message action' }).check();
  await preview.getByRole('button', { name: 'Execute confirmed Google action' }).click();
  await expect(preview).toContainText('completed');
  expect(sends).toBe(1);
});

test('Classroom groups assignments by course, preserves missing dates, and shows access restrictions', async ({ page }) => {
  let deny = false;
  await mockGoogle(page, path => {
    if (path === '/classroom/courses') return deny ? { httpError: 'Google denied API access. Check school administrator restrictions.' } : { courses: [{ id: 'class1', name: 'Synthetic Robotics' }, { id: 'class2', name: 'Synthetic Science' }], next_page_token: null };
    if (path.endsWith('/class1/assignments')) return { assignments: [{ id: 'work1', title: 'Synthetic robot design', dueDate: { year: 2026, month: 12, day: 2 }, dueTime: { hours: 18 } }], next_page_token: null };
    if (path.endsWith('/class2/assignments')) return { assignments: [{ id: 'work2', title: 'Synthetic observation', dueDate: null }], next_page_token: null };
    return null;
  });
  await page.goto('/'); await page.locator('.google-controls > summary').click();
  const classroom = page.getByRole('region', { name: 'Google classroom integration', exact: true });
  await classroom.getByRole('button', { name: 'Load available Classroom courses' }).click();
  await classroom.getByRole('button', { name: 'Load assignments for Synthetic Robotics', exact: true }).click();
  await classroom.getByRole('button', { name: 'Load assignments for Synthetic Science', exact: true }).click();
  await expect(classroom.locator('.google-course').filter({ hasText: 'Synthetic Robotics' })).toContainText('Synthetic robot design');
  await expect(classroom.locator('.google-course').filter({ hasText: 'Synthetic Science' })).toContainText('No due date provided');
  deny = true;
  await classroom.getByRole('button', { name: 'Load available Classroom courses' }).click();
  await expect(classroom.locator('.memory-notice')).toContainText('administrator restrictions');
});
