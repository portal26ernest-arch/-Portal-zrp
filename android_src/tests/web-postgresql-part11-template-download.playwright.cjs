'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const { chromium } = require('playwright');

const origin = process.env.PORTAL_WEB_E2E_ORIGIN;
const pin = process.env.PORTAL_WEB_E2E_PIN;
const director = process.env.PORTAL_WEB_E2E_DIRECTOR;
const companyB = process.env.PORTAL_WEB_E2E_COMPANY_B;
assert(origin && pin && director && companyB, 'missing Part 11 fixture inputs');

const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

async function login(page) {
  await page.goto(origin + '/web/');
  await page.locator('#loginUser').fill(director);
  await page.locator('#loginPin').fill(pin);
  await page.locator('#loginSubmit').click();
  await page.locator('#nav').waitFor();
  const session = await page.evaluate(() =>
    JSON.parse(sessionStorage.getItem('portalSession')));
  assert(session && session.token, 'browser session token missing');
  assert.equal(page.url().includes(session.token), false);
  return session.token;
}

async function openExcel(page) {
  await page.locator('[data-action="go"][data-page="sections"]:visible').first().click();
  await page.locator('[data-page="excelImport"]:visible').first().waitFor();
  await page.locator('[data-page="excelImport"]:visible').first().click();
  await page.locator('[data-action="downloadExcelTemplate"][data-kind="blank"]').waitFor();
}
async function serverTemplate(page, token, endpoint, extraHeaders = {}) {
  return page.evaluate(async ({token, endpoint, extraHeaders}) => {
    const response = await fetch('/api/v3/' + endpoint, {
      headers: {Authorization: 'Bearer ' + token, ...extraHeaders}
    });
    let body = null;
    try { body = await response.json(); } catch {}
    return {status: response.status, body};
  }, {token, endpoint, extraHeaders});
}

async function downloadTemplate(page, kind) {
  const button = page.locator(
    '[data-action="downloadExcelTemplate"][data-kind="' + kind + '"]');
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    button.click()
  ]);
  const tempPath = await download.path();
  assert(tempPath, kind + ' download path missing');
  const bytes = fs.readFileSync(tempPath);
  assert(bytes.length > 1000, kind + ' XLSX is unexpectedly small');
  assert.equal(bytes[0], 0x50);
  assert.equal(bytes[1], 0x4b);
  assert.match(download.suggestedFilename(), /^PORTAL_template_v1\.1\.xlsx$/);
  return {bytes, digest: sha(bytes)};
}

async function main() {
  const browser = await chromium.launch({headless:true});
  const context = await browser.newContext({acceptDownloads:true});
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    const token = await login(page);
    await openExcel(page);

    const blank = await downloadTemplate(page, 'blank');
    const prefill = await downloadTemplate(page, 'prefill');
    assert.notEqual(blank.digest, prefill.digest,
      'blank and prefilled workbook must differ');
    const blankApi = await serverTemplate(
      page, token, 'document-template-blank');
    const prefillApi = await serverTemplate(
      page, token, 'document-template');
    assert.equal(blankApi.status, 200);
    assert.equal(prefillApi.status, 200);

    const blankPayload = Buffer.from(blankApi.body.data.file_b64, 'base64');
    const prefillPayload = Buffer.from(prefillApi.body.data.file_b64, 'base64');
    assert.equal(sha(blankPayload), blank.digest,
      'blank browser download differs from server payload');
    assert.equal(sha(prefillPayload), prefill.digest,
      'prefill browser download differs from server payload');
    assert.equal(blankApi.body.data.mime_type,
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    assert.equal(prefillApi.body.data.mime_type,
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    assert.equal(blankApi.body.data.template_version, '2.0');
    assert.equal(prefillApi.body.data.template_version, '2.0');

    const forged = await serverTemplate(
      page, token, 'document-template',
      {'X-Portal-Company': String(companyB)});
    assert.equal(forged.status, 403,
      'company user must not forge another company scope');
    assert.deepEqual(errors, []);

    console.log('BLANK_BYTES=' + blank.bytes.length);
    console.log('PREFILL_BYTES=' + prefill.bytes.length);
    console.log('BLANK_SHA256=' + blank.digest);
    console.log('PREFILL_SHA256=' + prefill.digest);
    console.log('PART11_BROWSER_DOWNLOAD=PASS');
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
