'use strict';

const assert = require('node:assert/strict');
const { chromium } = require('playwright');

async function main() {
  const origin = process.env.PORTAL_WEB_E2E_ORIGIN;
  const pin = process.env.PORTAL_WEB_E2E_PIN;
  const companyB = process.env.PORTAL_WEB_E2E_COMPANY_B;
  const documentId = process.env.PORTAL_WEB_E2E_DOCUMENT_ID;
  const xlsxPath = process.env.PORTAL_WEB_E2E_XLSX;
  assert(origin && pin && companyB && documentId && xlsxPath, 'missing isolated fixture inputs');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });

  try {
    const web = await page.goto(origin + '/web/');
    assert.equal(web.status(), 200);
    await page.locator('#loginUser').fill('admin');
    await page.locator('#loginPin').fill(pin);
    await page.locator('#loginSubmit').click();
    await page.locator('#nav').waitFor();

    const session = await page.evaluate(() => JSON.parse(sessionStorage.getItem('portalSession')));
    assert(session && session.token);
    assert.equal(page.url().includes(session.token), false);

    const meta = await page.evaluate(async token => {
      const response = await fetch('/api/v3/meta', { headers: { Authorization: 'Bearer ' + token } });
      return { status: response.status, body: await response.json() };
    }, session.token);
    assert.equal(meta.status, 200);
    assert.equal(meta.body.ok, true);
    assert(Array.isArray(meta.body.permissions));
    assert(meta.body.permissions.includes('documents.read'));

    // Real Documents list -> browser Blob download -> archive.
    await page.locator('[data-action="go"][data-page="sections"]').click();
    await page.locator('[data-page="documents"]').waitFor();
    await page.locator('[data-page="documents"]').click();
    const article = page.locator('[data-document-id="' + documentId + '"]');
    try {
      await article.waitFor();
    } catch (error) {
      const diagnostics = await page.evaluate(async token => {
        const response = await fetch('/api/v3/documents?page=1&limit=50&status=all&include_archived=true', {
          headers: { Authorization: 'Bearer ' + token }
        });
        const body = await response.json();
        return {status: response.status, ids: (body.data?.items || body.items || []).map(x => x.id), content: document.querySelector('#content')?.innerText || ''};
      }, session.token);
      throw new Error('document missing in UI; diagnostics=' + JSON.stringify(diagnostics));
    }

    const [docDownload] = await Promise.all([
      page.waitForEvent('download'),
      article.locator('[data-action="downloadPortalDocument"]').click()
    ]);
    assert.match(docDownload.suggestedFilename(), /\.pdf$/i);

    await article.locator('[data-action="archivePortalDocument"]').click();
    await page.locator('[data-action="confirmSheet"]').click();
    await page.locator('[data-document-id="' + documentId + '"] .badge').filter({hasText:'В архиве'}).waitFor();
    assert.equal(await page.locator('[data-document-id="' + documentId + '"] [data-action="downloadPortalDocument"]').count(), 0);

    // Real XLSX file chooser -> preview -> explicit confirm/apply -> result download.
    await page.locator('[data-action="go"][data-page="sections"]').click();
    await page.locator('[data-page="excelImport"]').waitFor();
    await page.locator('[data-page="excelImport"]').click();
    await page.locator('#excelFile').waitFor();
    await page.locator('#excelFile').setInputFiles(xlsxPath);
    await page.locator('[data-action="previewExcelImport"]').click();
    await page.getByText('Результат проверки').waitFor();
    const previewText = await page.locator('#content').innerText();
    assert.match(previewText, /Новые\s*1/);
    await page.locator('[data-action="applyExcelImport"]').click();
    await page.locator('[data-action="confirmSheet"]').click();
    await page.getByText(/Импорт применён:/).waitFor();

    const resultButton = page.locator('[data-action="downloadImportResult"]');
    await resultButton.waitFor();
    const [resultDownload] = await Promise.all([
      page.waitForEvent('download'),
      resultButton.click()
    ]);
    assert.match(resultDownload.suggestedFilename(), /\.json$/i);

    // Normal company user cannot forge another company scope.
    const forged = await page.evaluate(async ({ token, company }) => {
      const response = await fetch('/api/v3/documents', {
        headers: { Authorization: 'Bearer ' + token, 'X-Portal-Company': company }
      });
      return response.status;
    }, { token: session.token, company: companyB });
    assert.equal(forged, 403);

    // Server logout revokes the token, and reload returns to login.
    await page.evaluate(async token => {
      await fetch('/api/logout', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
        body: '{}'
      });
    }, session.token);
    const revoked = await page.evaluate(async token => (await fetch('/api/me', {
      headers: { Authorization: 'Bearer ' + token }
    })).status, session.token);
    assert.equal(revoked, 401);
    await page.reload();
    await page.locator('#loginUser').waitFor();
    assert.equal(await page.locator('#app').isVisible(), false);
    const expected403 = errors.filter(message => message === 'Failed to load resource: the server responded with a status of 403 (Forbidden)');
    const expected401 = errors.filter(message => message === 'Failed to load resource: the server responded with a status of 401 (Unauthorized)');
    const unexpectedErrors = errors.filter(message => !expected403.includes(message) && !expected401.includes(message));
    assert.equal(expected403.length, 1);
    assert.equal(expected401.length, 1);
    assert.deepEqual(unexpectedErrors, []);
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error => { console.error(error.stack || error); process.exitCode = 1; });
