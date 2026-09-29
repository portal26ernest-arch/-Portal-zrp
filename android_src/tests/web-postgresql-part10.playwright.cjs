'use strict';

const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const origin = process.env.PORTAL_WEB_E2E_ORIGIN;
const pin = process.env.PORTAL_WEB_E2E_PIN;
const invoiceId = process.env.PORTAL_WEB_E2E_INVOICE_ID;
const companyB = process.env.PORTAL_WEB_E2E_COMPANY_B;
const directorUser = process.env.PORTAL_WEB_E2E_DIRECTOR;
const managerUser = process.env.PORTAL_WEB_E2E_MANAGER;
const packerUser = process.env.PORTAL_WEB_E2E_PACKER;
const ownerUser = process.env.PORTAL_WEB_E2E_OWNER;
const ownerPin = process.env.PORTAL_WEB_E2E_OWNER_PIN;
assert(origin && pin && invoiceId && companyB && directorUser && managerUser &&
  packerUser && ownerUser && ownerPin, 'missing Part 10 fixture inputs');

async function pageFor(browser) {
  const context = await browser.newContext({acceptDownloads:true});
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.goto(origin + '/web/');
  return {context, page, pageErrors};
}

async function loginCompany(page, username) {
  await page.locator('#loginUser').fill(username);
  await page.locator('#loginPin').fill(pin);
  await page.locator('#loginSubmit').click();
  await page.locator('#nav').waitFor();
  const session = await page.evaluate(() => JSON.parse(sessionStorage.getItem('portalSession')));
  assert(session && session.token);
  assert.equal(page.url().includes(session.token), false);
  return session.token;
}
async function loginOwner(page) {
  await page.locator('[data-action="loginOptions"]').click();
  await page.locator('[data-action="technicalLogin"]').click();
  await page.locator('#loginUser').fill(ownerUser);
  await page.locator('#loginPin').fill(ownerPin);
  await page.locator('#loginSubmit').click();
  await page.locator('[data-action="selectCompany"][data-id="1"]').waitFor();
  return (await page.evaluate(() => JSON.parse(sessionStorage.getItem('portalSession')))).token;
}

async function goTo(page, target) {
  if (target !== 'sections') {
    await page.locator('[data-action="go"][data-page="sections"]:visible').first().click();
  }
  await page.locator('[data-page="' + target + '"]').waitFor();
  await page.locator('[data-page="' + target + '"]').click();
}

async function api(page, token, path, options = {}) {
  return page.evaluate(async ({token, path, options}) => {
    const headers = {Authorization: 'Bearer ' + token, ...(options.headers || {})};
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(path, {
      method: options.method || 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body)
    });
    let body = null;
    try { body = await response.json(); } catch {}
    return {status: response.status, body};
  }, {token, path, options});
}

async function directorFlow(browser) {
  const {context, page, pageErrors} = await pageFor(browser);
  try {
    const token = await loginCompany(page, directorUser);
    await goTo(page, 'invoices');
    const xlsx = page.locator('[data-action="generateInvoiceXlsx"][data-id="' + invoiceId + '"]');
    await xlsx.waitFor();
    const [download] = await Promise.all([page.waitForEvent('download'), xlsx.click()]);
    assert.match(download.suggestedFilename(), /\.xlsx$/i);
    const edit = page.locator('[data-action="sendInvoiceEditing"][data-id="' + invoiceId + '"]');
    await edit.waitFor();
    await edit.click();
    await edit.waitFor({state:'detached'});
    const current = await api(page, token, '/api/v3/invoices');
    assert.equal(current.status, 200);
    const invoice = current.body.data.find(x => String(x.id) === String(invoiceId));
    assert.equal(invoice.state, 'editing');
    assert.equal(pageErrors.length, 0);
  } finally { await context.close(); }
}
async function managerFlow(browser) {
  const {context, page, pageErrors} = await pageFor(browser);
  try {
    const token = await loginCompany(page, managerUser);
    await goTo(page, 'invoices');
    assert.equal(await page.locator('[data-action="sendInvoiceEditing"][data-id="' + invoiceId + '"]').count(), 0);
    const edit = page.locator('[data-action="editInvoice"][data-id="' + invoiceId + '"]');
    await edit.waitFor();
    await edit.click();
    const form = page.locator('#invoiceRevisionForm');
    await form.waitFor();
    const rate = form.locator('[data-revision-rate]').first();
    const before = Number(await rate.inputValue());
    assert(Number.isFinite(before) && before > 0);
    await rate.fill((before + 1).toFixed(2));
    await form.locator('button[type="submit"]').click();
    await edit.waitFor({state:'detached'});
    const current = await api(page, token, '/api/v3/invoices');
    assert.equal(current.status, 200);
    const invoice = current.body.data.find(x => String(x.id) === String(invoiceId));
    assert.equal(invoice.state, 'finalized');
    assert.equal(Number(invoice.revision), 2);
    assert.equal(pageErrors.length, 0);
  } finally { await context.close(); }
}

async function packerFlow(browser) {
  const {context, page, pageErrors} = await pageFor(browser);
  try {
    const token = await loginCompany(page, packerUser);
    await page.locator('[data-action="go"][data-page="sections"]:visible').first().click();
    assert.equal(await page.locator('[data-page="invoices"]').count(), 0);
    const denied = await api(page, token, '/api/v3/invoices');
    assert.equal(denied.status, 403);
    assert.equal(pageErrors.length, 0);
  } finally { await context.close(); }
}
async function ownerFlow(browser) {
  const {context, page, pageErrors} = await pageFor(browser);
  try {
    const token = await loginOwner(page);
    const unselected = await api(page, token, '/api/v3/invoices');
    assert.equal(unselected.status, 403);

    await page.locator('[data-action="selectCompany"][data-id="1"]').click();
    await page.locator('[data-action="confirmSheet"]').click();
    await page.locator('#nav').waitFor();
    await goTo(page, 'invoices');
    const selected = await api(page, token, '/api/v3/invoices', {
      headers: {'X-Portal-Company':'1'}
    });
    assert.equal(selected.status, 200);
    assert(selected.body.data.some(x => String(x.id) === String(invoiceId)));

    const other = await api(page, token, '/api/v3/invoices', {
      headers: {'X-Portal-Company': String(companyB)}
    });
    assert.equal(other.status, 200);
    assert.equal(other.body.data.length, 0);
    assert.equal(pageErrors.length, 0);
  } finally { await context.close(); }
}

async function main() {
  const browser = await chromium.launch({headless:true});
  try {
    await directorFlow(browser);
    await managerFlow(browser);
    await packerFlow(browser);
    await ownerFlow(browser);
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
