/* Browser-only adapter for the shared PORTAL UI. Android keeps its native bridge. */
(function () {
  if (window.PortalNative || !/^https?:$/.test(location.protocol)) return;

  const MAX_BYTES = 20 * 1024 * 1024;
  const MAX_BASE64 = Math.ceil(MAX_BYTES * 4 / 3) + 8;
  const FILE_TYPES = new Map([
    ['application/pdf', ['.pdf']],
    ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', ['.xlsx']],
    ['application/json', ['.json']],
    ['image/jpeg', ['.jpg', '.jpeg']],
    ['image/png', ['.png']],
    ['image/webp', ['.webp']],
    ['text/plain', ['.txt']]
  ]);

  // Local-first company snapshot. Keep the last known-good data for 30 days
  // and refresh it silently whenever the section is read.
  const CACHE_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;
  const CACHEABLE = [
    /^\/api\/company$/,
    /^\/api\/(?:admin\/)?clients(?:\?.*)?$/,
    /^\/api\/clients\/\d+(?:\/operations)?(?:\?.*)?$/,
    /^\/api\/admin\/clients\/\d+\/operations(?:\?.*)?$/,
    /^\/api\/(?:users|materials|jobs)(?:\?.*)?$/,
    /^\/api\/v3\/(?:catalog|products|client-requisites|client-name-history|tariff-history|today|tasks|timers|batches|invoices|receivables|finance|analytics|payroll-periods|documents|settings|permissions|chat-users)(?:\?.*)?$/
  ];
  const INVALIDATES_CACHE = /\/(?:clients?|users?|materials?|operations?|tariffs?|products?|invitations?|company-access)(?:\/|\?|$)/i;
  const OUTBOX_PATHS = new Set(['/api/v3/work','/api/v3/links','/api/v3/batches','/api/v3/tasks','/api/v3/shipments','/api/v3/returns']);
  let cacheCompany = '';
  const desktopCache = () => {
    try { return window.chrome?.webview?.hostObjects?.sync?.portalDesktopCache || null; }
    catch { return null; }
  };
  const cacheRead = (company, key) => {
    try {
      const raw = desktopCache()?.Read(String(company), key);
      if (!raw) return null;
      const item = JSON.parse(String(raw));
      if (!item || item.v !== 1 || !item.savedAt || !item.data) return null;
      if (Date.now() - Number(item.savedAt) > CACHE_MAX_AGE_MS) return null;
      return item.data;
    } catch { return null; }
  };
  const cacheWrite = (company, key, data) => {
    try {
      return !!desktopCache()?.Write(String(company), key, JSON.stringify({v:1,savedAt:Date.now(),data}));
    } catch { return false; }
  };
  const cacheClearCompany = company => {
    try { return !!desktopCache()?.ClearCompany(String(company)); }
    catch { return false; }
  };
  const cacheDelete = (company, key) => {
    try { return !!desktopCache()?.Delete(String(company), key); }
    catch { return false; }
  };
  const invalidationKeys = target => {
    const keys = new Set();
    const add = (...values) => values.forEach(value => keys.add(value));
    if (/\/api\/v3\/work(?:\?|$)/.test(target)) {
      add('/api/v3/today','/api/v3/tasks','/api/v3/timers','/api/v3/finance','/api/v3/analytics','/api/v3/invoices','/api/v3/receivables');
    } else if (/\/api\/v3\/links(?:\?|$)/.test(target)) {
      add('/api/v3/today','/api/v3/tasks','/api/v3/batches','/api/v3/finance','/api/v3/analytics','/api/v3/invoices','/api/v3/receivables');
    } else if (/\/api\/v3\/(?:batches|tasks)(?:\?|$)/.test(target)) {
      add('/api/v3/today','/api/v3/tasks','/api/v3/timers','/api/v3/batches','/api/v3/finance','/api/v3/analytics');
    } else if (/\/api\/v3\/(?:shipments|returns)(?:\?|$)/.test(target)) {
      add('/api/v3/today','/api/v3/tasks','/api/v3/batches','/api/v3/finance','/api/v3/analytics','/api/v3/invoices','/api/v3/receivables');
    } else if (/\/(?:tariffs?|operations?|products?)(?:\/|\?|$)/i.test(target)) {
      add('/api/v3/catalog','/api/v3/tariff-history','/api/v3/products','/api/v3/today','/api/v3/finance','/api/v3/analytics');
    } else if (/\/(?:clients?)(?:\/|\?|$)/i.test(target)) {
      add('/api/clients','/api/admin/clients','/api/v3/catalog','/api/v3/client-name-history','/api/v3/client-requisites','/api/v3/today','/api/v3/finance','/api/v3/analytics');
    } else if (/\/(?:materials?)(?:\/|\?|$)/i.test(target)) {
      add('/api/materials','/api/v3/today','/api/v3/finance','/api/v3/analytics');
    } else if (/\/(?:users?|invitations?|company-access|permissions)(?:\/|\?|$)/i.test(target)) {
      add('/api/users','/api/v3/permissions','/api/v3/chat-users');
    } else if (/\/(?:invoices?|payments?)(?:\/|\?|$)/i.test(target)) {
      add('/api/v3/invoices','/api/v3/receivables','/api/v3/finance','/api/v3/today');
    } else if (/\/(?:settings)(?:\/|\?|$)/i.test(target)) {
      add('/api/company','/api/v3/settings','/api/v3/today');
    }
    return [...keys];
  };
  const invalidateCache = (company, target) => {
    for (const key of invalidationKeys(target)) cacheDelete(company, key);
  };
  const canCache = (verb, target, token) =>
    verb === 'GET' && !!token && !!cacheCompany && CACHEABLE.some(pattern => pattern.test(target));

  const result = (id, obj) => window.PortalBridgeResult(String(id), JSON.stringify(obj));
  const fail = (id, error, network = false) => result(id, {ok:false, httpStatus:0, network, error});
  const safeName = value => {
    const name = String(value || 'download').replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_').slice(0, 120);
    return name && name !== '.' && name !== '..' ? name : 'download';
  };
  const validFile = (name, mime) => {
    const extensions = FILE_TYPES.get(String(mime || ''));
    const lower = String(name || '').toLowerCase();
    return !!extensions && extensions.some(ext => lower.endsWith(ext));
  };
  const decode = value => {
    const b64 = String(value || '');
    if (!b64 || b64.length > MAX_BASE64) throw new Error('Файл превышает допустимый размер');
    const raw = atob(b64);
    if (!raw.length || raw.length > MAX_BYTES) throw new Error('Файл превышает допустимый размер');
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    return bytes;
  };
  const apiTarget = value => {
    if (typeof value !== 'string' || !value.startsWith('/api/') || value.startsWith('//') || value.includes('\\') || value.includes('#')) return null;
    const rawPath = value.split('?', 1)[0];
    if (rawPath.includes('%') || rawPath.includes('//')) return null;
    try {
      const url = new URL(value, location.origin);
      if (url.origin !== location.origin || !url.pathname.startsWith('/api/') || url.username || url.password) return null;
      return url.pathname + url.search;
    } catch {
      return null;
    }
  };
  const download = (filename, mime, b64) => {
    if (!validFile(filename, mime)) throw new Error('Тип файла не разрешён для скачивания');
    const bytes = decode(b64);
    const objectUrl = URL.createObjectURL(new Blob([bytes], {type:mime}));
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = safeName(filename);
    anchor.rel = 'noopener';
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    return {ok:true, location:'загрузки браузера'};
  };

  const fetchJson = async (verb, target, body, token, company) => {
    const headers = {Accept:'application/json'};
    if (token) headers.Authorization = 'Bearer ' + token;
    if (company) headers['X-Portal-Company'] = String(company);
    if (body) headers['Content-Type'] = 'application/json';
    const response = await fetch(target, {
      method:verb,
      headers,
      body:body || undefined,
      credentials:'same-origin',
      cache:'no-store',
      redirect:'error'
    });
    let data;
    try { data = await response.json(); }
    catch { data = {ok:false, error:'Некорректный ответ сервера'}; }
    if (!data || typeof data !== 'object' || Array.isArray(data)) data = {ok:false, error:'Некорректный ответ сервера'};
    return {...data, ok:response.ok && data.ok !== false, httpStatus:response.status};
  };

  window.PortalNative = {
    getServerUrl: () => location.origin,
    setServerUrl: () => false,
    setCacheCompany: value => {
      const next = String(value || '');
      cacheCompany = /^[1-9]\d{0,9}$/.test(next) ? next : '';
      return !!cacheCompany;
    },
    clearCompanyCache: () => cacheCompany ? cacheClearCompany(cacheCompany) : true,
    queueMutation: json => {
      try {
        if (!cacheCompany || typeof json !== 'string' || json.length > 512 * 1024) return false;
        const row = JSON.parse(json);
        if (!row || row.method !== 'POST' || !OUTBOX_PATHS.has(row.path) || !/^[0-9a-f-]{36}$/i.test(String(row.request_id || ''))
            || !row.body || row.body.request_id !== row.request_id) return false;
        return !!desktopCache()?.EnqueueMutation(String(cacheCompany), String(row.request_id), JSON.stringify(row));
      } catch { return false; }
    },
    pendingMutations: () => {
      try {
        if (!cacheCompany) return '[]';
        const raw = desktopCache()?.PendingMutations(String(cacheCompany));
        if (!raw) return '[]';
        const rows = JSON.parse(String(raw));
        if (!Array.isArray(rows)) return '[]';
        const parsed = rows.map(value => {
          try { return JSON.parse(String(value)); } catch { return null; }
        }).filter(Boolean);
        return JSON.stringify(parsed);
      } catch { return '[]'; }
    },
    removeMutation: requestId => {
      try {
        return !!cacheCompany && /^[0-9a-f-]{36}$/i.test(String(requestId || ''))
          && !!desktopCache()?.RemoveMutation(String(cacheCompany), String(requestId));
      } catch { return false; }
    },
    pendingMutationCount: () => {
      try { return cacheCompany ? Number(desktopCache()?.PendingMutationCount(String(cacheCompany)) || 0) : 0; }
      catch { return 0; }
    },
    checkUpdates: id => result(id, {ok:true, configured:false, web:true}),
    requestAsync: async (id, method, path, body, token, company) => {
      const verb = String(method || 'GET').toUpperCase();
      const target = apiTarget(path);
      if (!target || !['GET','POST'].includes(verb)) return fail(id, 'Недопустимый API-запрос');
      if (company && !/^[1-9]\d{0,9}$/.test(String(company))) return fail(id, 'Недопустимый контекст компании');
      if (token && (typeof token !== 'string' || token.length > 8192 || /[\r\n]/.test(token))) return fail(id, 'Недопустимая сессия');
      if (body && (typeof body !== 'string' || body.length > 24 * 1024 * 1024 || verb !== 'POST')) return fail(id, 'Недопустимые данные запроса');
      const cacheScope = cacheCompany;
      const cacheEligible = canCache(verb, target, token);
      const cached = cacheEligible ? cacheRead(cacheScope, target) : null;
      if (cached) {
        result(id, {...cached, cached:true});
        fetchJson(verb, target, body, token, company).then(fresh => {
          if (fresh.ok) cacheWrite(cacheScope, target, fresh);
          else if (fresh.httpStatus === 401 || fresh.httpStatus === 403) cacheClearCompany(cacheScope);
        }).catch(() => {});
        return;
      }
      try {
        const data = await fetchJson(verb, target, body, token, company);
        if (cacheEligible && data.ok) cacheWrite(cacheScope, target, data);
        if (verb === 'POST' && data.ok && cacheScope) {
          if (INVALIDATES_CACHE.test(target) || OUTBOX_PATHS.has(target.split('?',1)[0]) || /\/(?:invoices?|payments?|settings)(?:\/|\?|$)/i.test(target))
            invalidateCache(cacheScope, target);
        }
        result(id, data);
      } catch {
        fail(id, 'Нет соединения с сервером', true);
      }
    },
    requestForCompany: () => JSON.stringify({ok:false, httpStatus:0, error:'Используйте requestAsync'}),
    saveBase64FileAsync: (id, name, mime, b64) => {
      try { result(id, download(name, mime, b64)); }
      catch (error) { result(id, {ok:false, error:error.message}); }
    },
    shareBase64FileAsync: (id, name, mime, b64, recipient, subject, message) => {
      try {
        if (!validFile(name, mime)) throw new Error('Тип файла не разрешён для отправки');
        const bytes = decode(b64);
        if (typeof navigator.share === 'function' && typeof navigator.canShare === 'function' && typeof File === 'function') {
          const file = new File([bytes], safeName(name), {type:mime});
          if (navigator.canShare({files:[file]})) {
            const payload = {files:[file]};
            if (subject) payload.title = String(subject).slice(0, 200);
            if (message) payload.text = String(message).slice(0, 2000);
            navigator.share(payload)
              .then(() => result(id, {ok:true, shared:true}))
              .catch(error => result(id, {ok:false, cancelled:error && error.name === 'AbortError', error:error && error.name === 'AbortError' ? 'Отправка отменена' : 'Не удалось открыть системное меню отправки'}));
            return;
          }
        }
        result(id, download(name, mime, b64));
      } catch (error) {
        result(id, {ok:false, error:error.message});
      }
    }
  };

  document.documentElement.classList.add('web-client');
  window.__PORTAL_WEB__ = true;
})();
