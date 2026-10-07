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
  const FETCH_TIMEOUT_MS = 20 * 1000;
  const CACHEABLE = [
    /^\/api\/company$/,
    /^\/api\/(?:dashboard|invoices|payroll\/mine|work\/mine)(?:\?.*)?$/,
    /^\/api\/(?:admin\/)?clients(?:\?.*)?$/,
    /^\/api\/clients\/\d+(?:\/operations)?(?:\?.*)?$/,
    /^\/api\/admin\/clients\/\d+\/operations(?:\?.*)?$/,
    /^\/api\/(?:users|materials|jobs)(?:\?.*)?$/,
    /^\/api\/v3\/(?:catalog|products|client-requisites|client-name-history|tariff-history|today|tasks|timers|batches|works|shipments|returns|invoices|receivables|finance|analytics|expenses|economy|activity|payroll-periods|payroll-settlements|documents|settings|permissions|chat-users|notification-centers|presence|organizer|organizer-directors|organizer-events|organizer-requests|organizer-request-events|organizer-request-responsibles|organizer-users)(?:\?.*)?$/
  ];
  const OUTBOX_PATHS = new Set(['/api/v3/work','/api/v3/links','/api/v3/batches','/api/v3/tasks','/api/v3/shipments','/api/v3/returns']);
  let cacheCompany = '';
  let cacheIdentity = '';
  const cacheScope = () => cacheCompany && cacheIdentity ? cacheCompany + '|' + cacheIdentity : '';
  const desktopCache = () => {
    try { return window.chrome?.webview?.hostObjects?.sync?.portalDesktopCache || null; }
    catch { return null; }
  };
  const cacheRead = (scope, key) => {
    try {
      const raw = desktopCache()?.Read(String(scope), key);
      if (!raw) return null;
      const item = JSON.parse(String(raw));
      if (!item || item.v !== 2 || item.key !== key || !item.savedAt || !item.data) return null;
      if (Date.now() - Number(item.savedAt) > CACHE_MAX_AGE_MS) return null;
      return {data:item.data,savedAt:Number(item.savedAt),stale:!!item.staleAt};
    } catch { return null; }
  };
  const cacheWrite = (scope, key, data) => {
    try {
      return !!desktopCache()?.Write(String(scope), key, JSON.stringify({v:2,key,savedAt:Date.now(),staleAt:0,data}));
    } catch { return false; }
  };
  const cacheClearScope = scope => {
    try { return !!desktopCache()?.ClearCompany(String(scope)); }
    catch { return false; }
  };
  const invalidationKeys = target => {
    const keys = new Set();
    const add = (...values) => values.forEach(value => keys.add(value));
    if (/\/api\/v3\/work(?:\?|$)/.test(target)) {
      add('/api/dashboard','/api/work/mine','/api/payroll/mine','/api/v3/today','/api/v3/tasks','/api/v3/timers','/api/v3/works','/api/v3/finance','/api/v3/analytics','/api/v3/invoices','/api/v3/receivables');
    } else if (/\/api\/v3\/links(?:\?|$)/.test(target)) {
      add('/api/v3/today','/api/v3/tasks','/api/v3/batches','/api/v3/finance','/api/v3/analytics','/api/v3/invoices','/api/v3/receivables');
    } else if (/\/api\/v3\/(?:batches|tasks)(?:\?|$)/.test(target)) {
      add('/api/dashboard','/api/v3/today','/api/v3/tasks','/api/v3/timers','/api/v3/batches','/api/v3/finance','/api/v3/analytics');
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
      add('/api/dashboard','/api/invoices','/api/v3/invoices','/api/v3/receivables','/api/v3/finance','/api/v3/today');
    } else if (/\/api\/v3\/expenses(?:\/|\?|$)/i.test(target)) {
      add('/api/dashboard','/api/v3/expenses','/api/v3/finance','/api/v3/today');
    } else if (/\/api\/v3\/payroll-settlements(?:\/|\?|$)/i.test(target)) {
      add('/api/dashboard','/api/payroll/mine','/api/v3/payroll-periods','/api/v3/payroll-settlements','/api/v3/finance','/api/v3/today');
    } else if (/\/api\/v3\/(?:organizer|organizer-requests|organizer-request-events)(?:\/|\?|$)/i.test(target)) {
      add('/api/v3/organizer','/api/v3/organizer-requests','/api/v3/organizer-request-events','/api/v3/tasks','/api/v3/today');
    } else if (/\/api\/v3\/documents?(?:\/|\?|$)/i.test(target)) {
      add('/api/v3/documents');
    } else if (/\/api\/jobs(?:\/|\?|$)/i.test(target)) {
      add('/api/dashboard','/api/jobs','/api/v3/tasks','/api/v3/today');
    } else if (/\/(?:settings)(?:\/|\?|$)/i.test(target)) {
      add('/api/company','/api/v3/settings','/api/v3/today');
    }
    return [...keys];
  };
  const invalidateCache = (scope, target) => {
    const keys = invalidationKeys(target);
    if (!scope || !keys.length) return false;
    try { return !!desktopCache()?.MarkStale(String(scope), JSON.stringify(keys)); }
    catch { return false; }
  };
  const canCache = (verb, target, token) =>
    verb === 'GET' && !!token && !!cacheScope() && CACHEABLE.some(pattern => pattern.test(target));

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
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      const response = await fetch(target, {
        method:verb,
        headers,
        body:body || undefined,
        credentials:'same-origin',
        cache:'no-store',
        redirect:'error',
        signal:controller.signal
      });
      let data;
      try { data = await response.json(); }
      catch { data = {ok:false, error:'Некорректный ответ сервера'}; }
      if (!data || typeof data !== 'object' || Array.isArray(data)) data = {ok:false, error:'Некорректный ответ сервера'};
      return {...data, ok:response.ok && data.ok !== false, httpStatus:response.status};
    } finally {
      clearTimeout(timer);
    }
  };

  const appMetadata = () => JSON.stringify(window.__PORTAL_BUILD_METADATA__ || {platform:'Web'});

  window.PortalNative = {
    getAppMetadata: appMetadata,
    getServerUrl: () => location.origin,
    setServerUrl: () => false,
    setCacheCompany: value => {
      const next = String(value || '');
      cacheCompany = /^[1-9]\d{0,9}$/.test(next) ? next : '';
      return !!cacheCompany;
    },
    setCacheIdentity: (userId,role,permissionsJson='[]') => {
      const user = String(userId || ''), safeRole = String(role || '').toLowerCase();
      let permissions=[];
      try{const raw=JSON.parse(String(permissionsJson||'[]'));if(Array.isArray(raw))permissions=[...new Set(raw.map(String).filter(value=>/^[a-z0-9._-]{1,80}$/i.test(value)))].sort();}catch{}
      const signature=permissions.join(',');
      cacheIdentity = /^[1-9]\d{0,9}$/.test(user) && /^[a-z_]{2,40}$/.test(safeRole) && signature.length<=1500 ? user + '|' + safeRole + '|' + signature : '';
      return !!cacheIdentity;
    },
    clearCompanyCache: () => cacheScope() ? cacheClearScope(cacheScope()) : true,
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
    openMessengerWindow: (provider,relayJson='') => { if(!window.__PORTAL_DESKTOP__)return false; try { const p=String(provider||'telegram').toLowerCase()==='max'?'max':'telegram'; if(window.chrome?.webview?.postMessage){ window.chrome.webview.postMessage(JSON.stringify({type:'openMessenger',provider:p,relay:relayJson||''})); return true; } if(p==='telegram')return false; window.open('portal-messenger://open?provider=max','_blank'); return true; } catch { return false; } },
    clearMessengerSession: () => { try { window.open('portal-messenger://clear','_blank'); } catch {} },
    checkUpdates: id => result(id, {ok:true, configured:false, web:true}),
    requestAsync: async (id, method, path, body, token, company) => {
      const verb = String(method || 'GET').toUpperCase();
      const target = apiTarget(path);
      if (!target || !['GET','POST'].includes(verb)) return fail(id, 'Недопустимый API-запрос');
      if (company && !/^[1-9]\d{0,9}$/.test(String(company))) return fail(id, 'Недопустимый контекст компании');
      if (token && (typeof token !== 'string' || token.length > 8192 || /[\r\n]/.test(token))) return fail(id, 'Недопустимая сессия');
      if (body && (typeof body !== 'string' || body.length > 24 * 1024 * 1024 || verb !== 'POST')) return fail(id, 'Недопустимые данные запроса');
      const scope = cacheScope();
      const cacheEligible = canCache(verb, target, token);
      const cached = cacheEligible ? cacheRead(scope, target) : null;
      if (cached) {
        result(id, {...cached.data,cached:true,stale:cached.stale,cached_at:new Date(cached.savedAt).toISOString()});
        fetchJson(verb, target, body, token, company).then(fresh => {
          if (fresh.ok) cacheWrite(scope, target, fresh);
          else if (fresh.httpStatus === 401 || fresh.httpStatus === 403) cacheClearScope(scope);
        }).catch(() => {});
        return;
      }
      try {
        const data = await fetchJson(verb, target, body, token, company);
        if (cacheEligible && data.ok) cacheWrite(scope, target, data);
        if (verb === 'POST' && data.ok && scope && invalidationKeys(target).length) invalidateCache(scope, target);
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
