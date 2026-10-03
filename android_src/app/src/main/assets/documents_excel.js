'use strict';

// LIVE Documents + Excel UI for the Part 1 server API.
// Import preview credentials stay only in page memory.
(() => {
  const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  const PDF = 'application/pdf';
  const JSON_MIME = 'application/json';
  const MAX_XLSX = 10 * 1024 * 1024;
  const SHEETS = ['Компания', 'Сотрудники', 'Клиенты', 'Операции_Тарифы', 'Материалы', 'Приход_материалов', 'Нормы_материалов', 'Выработка'];
  const DOCUMENT_TYPE_LABELS = Object.freeze({
    payroll_xlsx: 'Расчёт зарплаты (Excel)',
    payroll_slip_xlsx: 'Расчётный лист (Excel)',
    payroll_slip_pdf: 'Расчётный лист (PDF)',
    invoice_xlsx: 'Счёт на оплату (Excel)',
    invoice_pdf: 'Счёт на оплату (PDF)',
    report_xlsx: 'Отчёт (Excel)',
    report_pdf: 'Отчёт (PDF)',
    import_template_xlsx: 'Шаблон импорта Excel',
    import_result: 'Результат импорта'
  });
  const DOCUMENT_CATEGORY_LABELS = Object.freeze({
    payroll: 'Зарплата',
    invoice: 'Счета',
    report: 'Отчёты',
    imports: 'Импорт Excel',
    company: 'Компания',
    clients: 'Клиенты',
    employees: 'Сотрудники'
  });
  const documentTypeLabel = value => DOCUMENT_TYPE_LABELS[value] || value || 'Без типа';
  const documentCategoryLabel = value => DOCUMENT_CATEGORY_LABELS[value] || value || 'Без категории';
  const IMPORT_CLASSIFICATION_LABELS = Object.freeze({
    new: 'Новая запись',
    update: 'Изменение',
    unchanged: 'Без изменений',
    conflict: 'Конфликт',
    invalid: 'Ошибка'
  });
  const importClassificationLabel = value => IMPORT_CLASSIFICATION_LABELS[value] || value || 'Неизвестный статус';

  const state = {
    page: 1,
    limit: 50,
    query: '',
    filters: {},
    rows: [],
    total: 0,
    preview: null,
    file: null,
    busy: false,
    templateInfo: null
  };

  const h = value => esc(value == null ? '' : String(value));
  const allowed = key => Array.isArray(S.me?.permissions) && S.me.permissions.includes(key);

  function requireCompany() {
    if (isOwner() && !S.company) throw new Error('Сначала выберите компанию');
  }

  function requireDocs() {
    requireCompany();
    if (!allowed('documents.read')) throw new Error('Нет права на просмотр документов');
  }

  function requireImport() {
    requireCompany();
    const needed = [
      'imports.manage', 'users.manage', 'clients.manage',
      'rates.employee', 'rates.client', 'company.settings',
      'documents.manage', 'documents.read'
    ];
    const roleAllowed = ['admin', 'director'].includes(S.me?.role) || (isOwner() && !!S.company);
    if (!S.stage3 || !roleAllowed || !needed.every(allowed)) {
      throw new Error('Импорт недоступен для текущей роли или набора прав');
    }
  }

  function queryPath() {
    const params = new URLSearchParams({
      page: String(state.page),
      limit: String(state.limit),
      status: state.filters.status || 'all',
      include_archived: 'true'
    });
    if (state.query) params.set('q', state.query);
    for (const [key, value] of Object.entries(state.filters)) {
      if (key !== 'status' && value) params.set(key, value);
    }
    return 'documents?' + params.toString();
  }

  async function loadDocs(append = false) {
    requireDocs();
    const data = await productionGet(queryPath());
    state.rows = append ? state.rows.concat(data.items || []) : (data.items || []);
    state.total = Number(data.total || 0);
    state.page = Number(data.page || state.page);
    renderDocs();
  }

  function safeFileName(raw) {
    const name = String(raw || 'PORTAL_document')
      .split(/[\\/]/).pop()
      .replace(/[^A-Za-z0-9._-]/g, '_')
      .slice(0, 120);
    return name || 'PORTAL_document';
  }

  async function savePayload(file) {
    if (!window.PortalNative?.saveBase64FileAsync) {
      throw new Error('Сохранение доступно в мобильном приложении');
    }
    const mime = file?.mime_type;
    if (![XLSX, PDF, JSON_MIME].includes(mime)) {
      throw new Error('Неподдерживаемый тип файла');
    }
    const saved = await nativePromise(id =>
      PortalNative.saveBase64FileAsync(id, safeFileName(file.filename), mime, file.file_b64)
    );
    if (!saved.ok) throw new Error(saved.error || 'Не удалось сохранить файл');
    toast('Сохранено · ' + saved.location);
  }

  async function sharePayload(file) {
    if (!window.PortalNative?.shareBase64FileAsync) throw new Error('Системная отправка доступна в мобильном приложении');
    const mime = file?.mime_type;
    if (![XLSX, PDF, JSON_MIME].includes(mime)) throw new Error('Неподдерживаемый тип файла');
    const recipient = window.prompt('Email получателя (необязательно)', '') || '';
    const subject = window.prompt('Тема (необязательно)', file.filename || '') || '';
    const text = window.prompt('Текст (необязательно)', '') || '';
    const result = await nativePromise(id => PortalNative.shareBase64FileAsync(
      id, safeFileName(file.filename), mime, file.file_b64, recipient, subject, text
    ));
    if (!result.ok) throw new Error(result.error || 'Не удалось открыть системную отправку');
  }

  function renderDocs() {
    const documentCard = d => {
      const archived = d.status === 'archived';
      const size = d.size_bytes ? `${Math.max(1, Math.round(d.size_bytes / 1024))} КБ` : '—';
      return `<article class="item ${archived ? 'archived-document' : ''}" data-document-id="${h(d.id)}">
        <div class="row between">
          <b class="grow">${h(d.title || d.original_filename)}</b>
          <span class="badge ${archived ? 'amber' : 'green'}">${archived ? 'В архиве' : 'Готов'}</span>
        </div>
        <p class="meta">${h(documentTypeLabel(d.document_type))} · ${h(documentCategoryLabel(d.category))} · ${h((d.document_date || d.created_at || '').slice(0, 10))}</p>
        <p class="meta">${d.client_id ? `Клиент #${h(d.client_id)} · ` : ''}${d.employee_id ? `Сотрудник #${h(d.employee_id)} · ` : ''}${size} · версия ${h(d.revision || 1)} · ${archived ? 'архивная запись' : 'текущая версия'}</p>
        <div class="item-actions">
          ${!archived && d.status === 'ready' ? btn('Скачать', 'downloadPortalDocument', `data-id="${h(d.id)}"`, 'secondary') : ''}
          ${!archived && d.status === 'ready' && window.PortalNative?.shareBase64FileAsync ? btn('Поделиться', 'sharePortalDocument', `data-id="${h(d.id)}"`, 'secondary') : ''}
          ${btn('История версий', 'showPortalDocumentHistory', `data-id="${h(d.id)}"`, 'text')}
          ${!archived && allowed('documents.manage') ? btn('В архив', 'archivePortalDocument', `data-id="${h(d.id)}"`, 'text') : ''}
        </div>
      </article>`;
    };
    const folders = new Map();
    for (const d of state.rows) {
      const month = (d.document_date || d.created_at || '').slice(0, 7) || 'без даты';
      const folder = [documentCategoryLabel(d.category), documentTypeLabel(d.document_type), month,
        d.client_id ? `клиент #${d.client_id}` : 'компания', d.employee_id ? `сотрудник #${d.employee_id}` : ''].filter(Boolean).join(' / ');
      if (!folders.has(folder)) folders.set(folder, []);
      folders.get(folder).push(d);
    }
    const rows = [...folders.entries()].map(([folder, docs]) =>
      `<section class="card document-folder" data-document-folder="${h(folder)}"><h3>${h(folder)}</h3><div class="list">${docs.map(documentCard).join('')}</div></section>`
    ).join('');

    const createButton = allowed('documents.manage')
      ? btn('Создать расчётный документ', 'newPayrollDocument', '', 'secondary')
      : '';

    $('content').innerHTML =
      heading('Документы', 'Файлы выбранной компании', createButton) +
      `<form id="documentsFilters" class="card document-filters">
        <label class="field"><span>Поиск</span><input id="docQuery" type="search" maxlength="200" value="${h(state.query)}" placeholder="Название или имя файла"></label>
        <div class="filter-grid">
          ${selectField('docType', 'Тип документа', '<option value="">Все типы</option>' +
            Object.entries(DOCUMENT_TYPE_LABELS)
              .map(([value, label]) => `<option value="${h(value)}">${h(label)}</option>`).join(''))}
          ${selectField('docCategory', 'Категория', '<option value="">Все категории</option>' +
            Object.entries(DOCUMENT_CATEGORY_LABELS)
              .map(([value, label]) => `<option value="${h(value)}">${h(label)}</option>`).join(''))}
          ${selectField('docStatus', 'Статус', '<option value="all">Все</option><option value="ready">Готов</option><option value="archived">В архиве</option>')}
          ${allowed('clients.read') || allowed('clients.manage') ? field('docClient', 'ID клиента', state.filters.client_id || '', 'number', 'min="1" step="1"') : ''}
          ${allowed('users.manage') || allowed('payroll.all') ? field('docEmployee', 'ID сотрудника', state.filters.employee_id || '', 'number', 'min="1" step="1"') : ''}
          ${field('docFrom', 'С даты', '', 'date')}
          ${field('docTo', 'По дату', '', 'date')}
        </div>
        <button class="btn secondary block" type="submit">Применить фильтры</button>
      </form>
      <div class="section-label"><h2>Документы · ${state.total}</h2><button class="btn text" data-action="refreshPortalDocuments">Обновить</button></div>
      <div class="list">${rows || '<div class="empty">Документы не найдены. Попробуйте изменить фильтры.</div>'}</div>
      ${state.rows.length < state.total ? btn('Показать ещё', 'morePortalDocuments', '', 'secondary block') : ''}`;

    $('docType').value = state.filters.document_type || '';
    $('docCategory').value = state.filters.category || '';
    $('docStatus').value = state.filters.status || 'all';
    $('docFrom').value = state.filters.date_from || '';
    $('docTo').value = state.filters.date_to || '';
    if ($('docClient')) $('docClient').value = state.filters.client_id || '';
    if ($('docEmployee')) $('docEmployee').value = state.filters.employee_id || '';

    $('documentsFilters').addEventListener('submit', event => {
      event.preventDefault();
      state.query = $('docQuery').value.trim();
      state.filters = {
        document_type: $('docType').value,
        category: $('docCategory').value,
        status: $('docStatus').value,
        date_from: $('docFrom').value,
        date_to: $('docTo').value,
        ...($('docClient') ? {client_id: $('docClient').value} : {}),
        ...($('docEmployee') ? {employee_id: $('docEmployee').value} : {})
      };
      state.page = 1;
      state.rows = [];
      loadDocs().catch(handleError);
    });
  }

  screens.documents = async () => {
    state.page = 1;
    state.rows = [];
    paint('<div class="loading"><span class="spinner"></span><p>Загружаем документы…</p></div>');
    try {
      await loadDocs();
    } catch (error) {
      paint(heading('Документы', '') +
        `<div class="notice warning">${h(error.message || 'Не удалось загрузить документы. Проверьте подключение и права доступа.')}</div>` +
        btn('Повторить', 'refreshPortalDocuments', '', 'secondary'));
      throw error;
    }
  };

  window.PortalDocuments = Object.freeze({
    openForClient: async identity => {
      requireDocs();
      if (!allowed('clients.read') && !allowed('clients.manage')) throw new Error('Нет права фильтровать документы по клиенту');
      const clientId=Number(identity);
      if (!Number.isSafeInteger(clientId) || clientId<1) throw new Error('Некорректный клиент');
      state.query='';state.filters={client_id:String(clientId),status:'all'};state.page=1;state.rows=[];
      return screens.documents();
    }
  });

  actions.refreshPortalDocuments = () => {
    state.page = 1;
    state.rows = [];
    return loadDocs();
  };

  actions.morePortalDocuments = async () => {
    const previous = state.page;
    state.page++;
    try {
      await loadDocs(true);
    } catch (error) {
      state.page = previous;
      throw error;
    }
  };

  actions.downloadPortalDocument = async button => {
    requireDocs();
    const file = await productionGet('document-file?id=' + encodeURIComponent(button.dataset.id));
    await savePayload(file);
  };

  actions.showPortalDocumentHistory = async button => {
    requireDocs();
    const versions = await productionGet('document-history?id=' + encodeURIComponent(button.dataset.id));
    const selected = String(button.dataset.id);
    openSheet('История версий документа', `<div class="list">${(versions || []).map(version => {
      const status = version.status === 'archived' ? 'В архиве' : 'Доступна';
      const current = String(version.id) === selected ? ' · выбранная версия' : '';
      return `<article class="item"><b>Версия ${h(version.revision || 1)}</b><p>${h(version.title || version.filename || 'Документ')}</p><p class="meta">${h((version.created_at || '').slice(0, 16).replace('T', ' '))} · ${status}${current}</p></article>`;
    }).join('') || '<p class="empty">История версий пуста</p>'}</div>`);
  };

  actions.sharePortalDocument = async button => {
    requireDocs();
    const row = state.rows.find(item => String(item.id) === String(button.dataset.id));
    if (!row || row.status !== 'ready') throw new Error('Документ недоступен для отправки');
    const file = await productionGet('document-file?id=' + encodeURIComponent(button.dataset.id));
    await sharePayload(file);
  };

  actions.archivePortalDocument = async button => {
    requireDocs();
    if (!allowed('documents.manage')) throw new Error('Нет права архивировать документы');
    const yes = await confirmSheet(
      'Архивировать документ',
      'Документ останется в истории и перестанет скачиваться.',
      'В архив'
    );
    if (!yes) return;
    await productionPost('document-archive', {id: button.dataset.id});
    toast('Документ перемещён в архив');
    state.page = 1;
    state.rows = [];
    await loadDocs();
  };

  function fileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('Не удалось прочитать выбранный файл'));
      reader.onload = () => {
        const value = String(reader.result || '');
        const comma = value.indexOf(',');
        if (comma < 0) reject(new Error('Не удалось подготовить файл'));
        else resolve(value.slice(comma + 1));
      };
      reader.readAsDataURL(file);
    });
  }

  function validateExcelFile(file) {
    if (!file) return 'Сначала выберите XLSX-файл';
    if (!file.name.toLowerCase().endsWith('.xlsx')) return 'Выберите файл с расширением .xlsx';
    if (file.size <= 0) return 'Файл пуст';
    if (file.size > MAX_XLSX) return 'Файл больше лимита 10 МиБ';
    return '';
  }

  function summaryHtml(summary) {
    return `<div class="metrics">${[
      ['Новые','new'], ['Изменения','update'], ['Без изменений','unchanged'],
      ['Конфликты','conflict'], ['Ошибки','invalid']
    ].map(([label, key]) => metric(label, num(summary?.[key] || 0))).join('')}</div>`;
  }

  function previewHtml(preview) {
    const rows = (preview.rows || []).map(row =>
      `<article class="item">
        <div class="row between">
          <b>${h(row.sheet)} · строка ${h(row.row)}</b>
          <span class="badge ${['conflict','invalid'].includes(row.classification) ? 'amber' : 'green'}">${h(importClassificationLabel(row.classification))}</span>
        </div>
        ${row.errors?.length ? `<p class="meta">${row.errors.map(e => h(typeof e === 'string' ? e : (e.code || 'Проверьте строку'))).join(' · ')}</p>` : ''}
        ${row.changes ? `<details><summary>Изменения</summary><pre class="safe-diff">${h(JSON.stringify(row.changes, null, 2))}</pre></details>` : ''}
      </article>`
    ).join('');

    return summaryHtml(preview.summary) +
      `<p class="meta">Шаблон ${h(preview.template_version)} · файл подтверждается контрольной суммой. Результат предварительной проверки действует ограниченное время.</p>
       <div class="list">${rows || '<p class="empty">Изменений нет</p>'}</div>
       ${preview.can_apply && state.file ? btn(state.busy ? 'Применяем…' : 'Применить изменения', 'applyExcelImport', '', 'block') : ''}`;
  }

  function renderImport(extra = '') {
    const preview = state.preview;
    paint(
      heading('Импорт Excel', 'Шаблон · проверка · подтверждение · результат') +
      `<div class="card">
        <p class="meta">PORTAL Excel ${h(state.templateInfo?.template_version || '2.0')}. Заполняйте обычные названия и значения — служебные строки и ID скрыты. Для роли и активности в Excel есть готовые выпадающие списки.</p>
        <p class="meta">Листы: ${SHEETS.join(' · ')}</p>
        <div class="stack">
          ${btn('Скачать пустой шаблон', 'downloadExcelTemplate', 'data-kind="blank"', 'secondary block')}
          ${window.PortalNative?.shareBase64FileAsync ? btn('Поделиться пустым шаблоном', 'shareExcelTemplate', 'data-kind="blank"', 'secondary block') : ''}
          ${btn('Скачать шаблон с данными компании', 'downloadExcelTemplate', 'data-kind="prefill"', 'secondary block')}
          ${window.PortalNative?.shareBase64FileAsync ? btn('Поделиться шаблоном компании', 'shareExcelTemplate', 'data-kind="prefill"', 'secondary block') : ''}
        </div>
      </div>
      <div class="card">
        <h3>Загрузить заполненный файл</h3>
        <input id="excelFile" type="file" accept=".xlsx,${XLSX}">
        <div id="selectedExcel" class="meta">${state.file ? `${h(state.file.name)} · ${Math.ceil(state.file.size / 1024)} КБ` : ''}</div>
        ${btn(state.busy ? 'Проверяем…' : 'Проверить файл', 'previewExcelImport', '', 'secondary block')}
        <p class="meta">Только XLSX до 10 МиБ. Содержимое проверяет сервер; формулы на телефоне не исполняются.</p>
      </div>
      ${extra}
      ${preview ? `<section class="card">
        <div class="row between"><h3>Результат проверки</h3>${btn('Отменить проверку', 'clearExcelPreview', '', 'text')}</div>
        ${previewHtml(preview)}
      </section>` : ''}`
    );

    $('excelFile').addEventListener('change', event => {
      const file = event.target.files?.[0] || null;
      state.file = null;
      state.preview = null;
      const problem = validateExcelFile(file);
      if (file && problem) toast(problem, true);
      if (!problem) {
        state.file = file;
        $('selectedExcel').textContent = `${file.name} · ${Math.max(1, Math.round(file.size / 1024))} КБ`;
      }
    });
  }

  screens.excelImport = async () => {
    requireImport();
    state.preview = null;
    state.file = null;
    state.busy = false;
    paint('<div class="loading"><span class="spinner"></span><p>Загружаем сведения о шаблоне…</p></div>');
    try {
      state.templateInfo = await productionGet('document-template-info');
      renderImport();
    } catch (error) {
      paint(heading('Импорт Excel', '') +
        `<div class="notice warning">${h(error.message || 'Не удалось загрузить шаблон. Проверьте подключение и права доступа.')}</div>` +
        btn('Повторить', 'go', 'data-page="excelImport"', 'secondary'));
      throw error;
    }
  };

  actions.downloadExcelTemplate = async button => {
    if (button.dataset.kind === 'prefill') requireImport();
    else requireDocs();
    const endpoint = button.dataset.kind === 'prefill' ? 'document-template' : 'document-template-blank';
    const file = await productionGet(endpoint);
    await savePayload(file);
  };

  actions.shareExcelTemplate = async button => {
    if (button.dataset.kind === 'prefill') requireImport(); else requireDocs();
    const endpoint = button.dataset.kind === 'prefill' ? 'document-template' : 'document-template-blank';
    await sharePayload(await productionGet(endpoint));
  };

  actions.previewExcelImport = async () => {
    requireImport();
    if (state.busy) return;
    const file = state.file || $('excelFile')?.files?.[0];
    const problem = validateExcelFile(file);
    if (problem) {
      toast(problem, true);
      return;
    }

    state.busy = true;
    renderImport();
    try {
      const encoded = await fileAsBase64(file);
      const preview = await productionPost('excel-import-preview', {
        file_b64: encoded,
        original_filename: safeFileName(file.name),
        mime_type: XLSX
      });
      state.preview = preview;
      state.file = file;
      state.busy = false;
      renderImport('<p class="notice">Проверка завершена. Изменения ещё не применены.</p>');
    } catch (error) {
      state.preview = null;
      state.busy = false;
      renderImport(`<p class="notice warning">${h(error.message || 'Не удалось проверить файл')}</p>`);
      throw error;
    }
  };

  actions.clearExcelPreview = () => {
    state.preview = null;
    state.file = null;
    state.busy = false;
    renderImport();
  };

  actions.applyExcelImport = async () => {
    requireImport();
    const preview = state.preview;
    const file = state.file;
    if (!preview?.can_apply || !file || state.busy) return;

    state.busy = true;
    renderImport();
    const yes = await confirmSheet(
      'Применить изменения?',
      `Будут применены изменения из «${file.name}» к компании «${S.company?.name || ''}». Сервер применит их атомарно.`,
      'Применить'
    );
    if (!yes) {
      state.busy = false;
      renderImport();
      return;
    }

    try {
      const encoded = await fileAsBase64(file);
      const result = await productionPost('excel-import-apply', {
        file_b64: encoded,
        original_filename: safeFileName(file.name),
        mime_type: XLSX,
        import_id: preview.import_id,
        preview_token: preview.preview_token
      });

      state.preview = null;
      state.file = null;
      state.busy = false;

      if (result.status === 'applied') {
        const counts = result.result_counts || {};
        renderImport(
          `<div class="notice">Импорт применён: новых ${num(counts.new || 0)}, обновлено ${num(counts.updated || 0)}, без изменений ${num(counts.unchanged || 0)}.</div>` +
          (result.result_document_id ? btn('Скачать отчёт импорта', 'downloadImportResult', `data-id="${h(result.result_document_id)}"`, 'secondary') + (window.PortalNative?.shareBase64FileAsync ? btn('Поделиться отчётом', 'shareImportResult', `data-id="${h(result.result_document_id)}"`, 'secondary') : '') : '')
        );
        toast('Импорт применён');
        return;
      }

      renderImport(
        `<div class="notice warning">Импорт полностью отменён. Ошибок: ${num(result.error_report?.length || 0)}. Скачайте безопасный отчёт и выполните новый preview после исправления файла.</div>` +
        (result.result_document_id ? btn('Скачать отчёт импорта', 'downloadImportResult', `data-id="${h(result.result_document_id)}"`, 'secondary') + (window.PortalNative?.shareBase64FileAsync ? btn('Поделиться отчётом', 'shareImportResult', `data-id="${h(result.result_document_id)}"`, 'secondary') : '') : '')
      );
    } catch (error) {
      let terminal = null;
      try {
        terminal = await productionGet('excel-import-result?id=' + encodeURIComponent(preview.import_id));
      } catch {}

      state.preview = null;
      state.file = null;
      state.busy = false;

      if (terminal?.status === 'failed') {
        renderImport(
          `<div class="notice warning">Импорт полностью отменён. Ошибок: ${num(terminal.error_report?.length || 0)}. Сервер сохранил безопасный отчёт.</div>` +
          (terminal.result_document_id ? btn('Скачать отчёт импорта', 'downloadImportResult', `data-id="${h(terminal.result_document_id)}"`, 'secondary') + (window.PortalNative?.shareBase64FileAsync ? btn('Поделиться отчётом', 'shareImportResult', `data-id="${h(terminal.result_document_id)}"`, 'secondary') : '') : '')
        );
        return;
      }

      if (terminal?.status === 'applied') {
        const counts = terminal.result_counts || {};
        renderImport(
          `<div class="notice">Импорт уже применён: новых ${num(counts.new || 0)}, обновлено ${num(counts.updated || 0)}, без изменений ${num(counts.unchanged || 0)}. Повтор не создал второй импорт.</div>` +
          (terminal.result_document_id ? btn('Скачать отчёт импорта', 'downloadImportResult', `data-id="${h(terminal.result_document_id)}"`, 'secondary') + (window.PortalNative?.shareBase64FileAsync ? btn('Поделиться отчётом', 'shareImportResult', `data-id="${h(terminal.result_document_id)}"`, 'secondary') : '') : '')
        );
        return;
      }

      const stale = /preview|token|срок|справочник|изменил/i.test(error.message || '');
      renderImport(
        `<div class="notice warning">${h(stale
          ? 'Результат предварительной проверки устарел или справочники изменились. Выберите файл и выполните проверку заново.'
          : (error.message || 'Не удалось применить импорт. Выполните новую предварительную проверку.'))}</div>`
      );
    }
  };

  actions.downloadImportResult = async button => {
    requireImport();
    const file = await productionGet('document-file?id=' + encodeURIComponent(button.dataset.id));
    await savePayload(file);
  };

  actions.shareImportResult = async button => {
    requireImport();
    await sharePayload(await productionGet('document-file?id=' + encodeURIComponent(button.dataset.id)));
  };
})();
