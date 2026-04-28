    const qs = (s) => document.querySelector(s);
    const qsa = (s) => document.querySelectorAll(s);
    const loginMask = qs('#loginMask');
    const loginHint = qs('#loginHint');
    const revealedEnvValues = new Map();
    let envRevealAll = false;
    let taskWorkspaceData = { tasks: [], sessions: [] };
    let taskWorkspaceSelected = { type: 'root', taskId: '' };
    let pluginCatalogData = { items: [], errors: [] };
    let pluginPanelSelected = { type: 'root', package: '', kind: '', fullName: '' };
    let pluginTreeState = { packages: {}, groups: {} };
    let selectedPluginFile = null;
    let copyToastTimer = null;
    const PANEL_COLLAPSE_KEY = 'weboter.panel.collapsed';
    const AUTO_REFRESH_KEY = 'weboter.panel.autoRefresh';
    const WORKFLOW_PROP_COLLAPSE_KEY = 'weboter.panel.workflow.propCollapsed';
    let autoRefreshEnabled = false;
    let autoRefreshTimer = null;
    let workflowWorkspaceData = {
      items: [],
      workflowItems: [],
      selectedWorkflow: '',
      flow: null,
      editFlow: null,
      editMode: false,
      flowPath: '',
      selectedNodeKey: '',
      propCollapsed: false,
    };

    const tabMeta = {
      overview: { title: '运行总览', desc: '查看服务状态、队列与最近执行信息。' },
      tasks: { title: '任务与会话', desc: '快速观察最近任务和会话状态。' },
      env: { title: 'Env 管理', desc: '维护 service 内部受管环境变量。' },
      plugins: { title: '插件目录', desc: '查看 builtin 与已加载插件，并上传新的 zip 插件包。' },
      workflow: { title: 'Workflow 设计', desc: '左侧选择 workflow，中间查看节点，右侧查看节点属性。' },
      user: { title: '用户', desc: '登录与会话管理。' },
      system: { title: '系统', desc: '系统状态与运维信息。' },
    };

    function statusClass(status) {
      const s = (status || '').toLowerCase();
      if (['ok', 'running', 'succeeded'].includes(s)) return 'ok';
      if (['paused', 'guard_waiting', 'queued'].includes(s)) return 'warn';
      return 'bad';
    }

    function pill(status) {
      return `<span class="pill ${statusClass(status)}">${status || '-'}</span>`;
    }

    async function request(url, method = 'GET', body = null) {
      const res = await fetch(url, {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : {},
        body: body ? JSON.stringify(body) : null,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || data.detail || `HTTP ${res.status}`);
      return data;
    }

    function showCopyToast(message = '已复制') {
      const toast = qs('#copyToast');
      toast.textContent = message;
      toast.classList.add('show');
      if (copyToastTimer) clearTimeout(copyToastTimer);
      copyToastTimer = setTimeout(() => {
        toast.classList.remove('show');
      }, 1200);
    }

    async function copyText(text, message = '已复制') {
      const normalized = String(text ?? '');
      try {
        await navigator.clipboard.writeText(normalized);
        showCopyToast(message);
      } catch {
        const temp = document.createElement('textarea');
        temp.value = normalized;
        temp.style.position = 'fixed';
        temp.style.opacity = '0';
        document.body.appendChild(temp);
        temp.select();
        document.execCommand('copy');
        temp.remove();
        showCopyToast(message);
      }
    }

    function valueToDisplayText(value) {
      if (value === null) return 'null';
      if (typeof value === 'string') return value;
      if (typeof value === 'number' || typeof value === 'boolean') return String(value);
      try {
        return JSON.stringify(value);
      } catch {
        return String(value);
      }
    }

    function valueToCopyText(value) {
      if (typeof value === 'string') return value;
      try {
        return JSON.stringify(value, null, 2);
      } catch {
        return String(value);
      }
    }

    function icon(name) {
      if (name === 'copy') {
        return '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="10" height="10" rx="2"></rect><path d="M6 15H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1"></path></svg>';
      }
      if (name === 'refresh') {
        return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0 2 5.3"></path><path d="M20 4v7h-7"></path></svg>';
      }
      if (name === 'auto-on') {
        return '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="10" width="18" height="8" rx="4"></rect><circle cx="16" cy="14" r="3"></circle></svg>';
      }
      if (name === 'auto-off') {
        return '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="10" width="18" height="8" rx="4"></rect><circle cx="8" cy="14" r="3"></circle></svg>';
      }
      if (name === 'eye') {
        return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>';
      }
      return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18"></path><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"></path><path d="M9.9 5.2A11.4 11.4 0 0 1 12 5c6.5 0 10 7 10 7a16.9 16.9 0 0 1-4 4.8"></path><path d="M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a10.7 10.7 0 0 0 4.1-.8"></path></svg>';
    }

    function renderTopIcons() {
      const refreshBtn = qs('#topRefreshBtn');
      const autoBtn = qs('#autoRefreshBtn');
      if (refreshBtn) refreshBtn.innerHTML = icon('refresh');
      if (autoBtn) {
        autoBtn.innerHTML = icon(autoRefreshEnabled ? 'auto-on' : 'auto-off');
        autoBtn.classList.toggle('active', autoRefreshEnabled);
      }
    }

    function setAutoRefresh(enabled) {
      autoRefreshEnabled = !!enabled;
      localStorage.setItem(AUTO_REFRESH_KEY, autoRefreshEnabled ? '1' : '0');
      if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
      }
      if (autoRefreshEnabled) {
        autoRefreshTimer = setInterval(() => {
          refreshCurrentPage().catch(() => {});
        }, 10000);
      }
      renderTopIcons();
    }

    async function ensureRevealedValue(name) {
      if (revealedEnvValues.has(name)) return revealedEnvValues.get(name);
      const data = await request(`/panel/api/env/${encodeURIComponent(name)}?reveal=true`);
      revealedEnvValues.set(name, data.value);
      return data.value;
    }

    async function preloadRevealedValues(items) {
      const jobs = (items || []).map(async (item) => {
        if (!item?.name || revealedEnvValues.has(item.name)) return;
        await ensureRevealedValue(item.name);
      });
      await Promise.all(jobs);
    }

    function parseValue(input) {
      return String(input ?? '');
    }

    function escapeHtml(input) {
      return String(input ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function deepClone(value) {
      if (value === undefined) return undefined;
      return JSON.parse(JSON.stringify(value));
    }

    function prettyJson(value, fallback) {
      const target = value === undefined ? fallback : value;
      try {
        return JSON.stringify(target, null, 2);
      } catch {
        return JSON.stringify(fallback, null, 2);
      }
    }

    function parseObjectJson(label, text, fallback = {}) {
      const raw = String(text ?? '').trim();
      if (!raw) return fallback;
      let parsed;
      try {
        parsed = JSON.parse(raw);
      } catch {
        throw new Error(`${label} 不是合法 JSON`);
      }
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
        throw new Error(`${label} 必须是 JSON 对象`);
      }
      return parsed;
    }

    function parseArrayJson(label, text, fallback = []) {
      const raw = String(text ?? '').trim();
      if (!raw) return fallback;
      let parsed;
      try {
        parsed = JSON.parse(raw);
      } catch {
        throw new Error(`${label} 不是合法 JSON`);
      }
      if (!Array.isArray(parsed)) {
        throw new Error(`${label} 必须是 JSON 数组`);
      }
      return parsed;
    }

    // 识别表示“节点引用”的类型名（大小写不敏感）
    const NODE_REF_TYPE_NAMES = new Set(['nodeid', 'node']);

    // 插件目录尚未加载时的最小兜底契约
    const CONTROL_INPUT_TYPES_FALLBACK = {
      'builtin.NextNode': {
        next_node: ['NodeId'],
      },
      'builtin.LoopUntil': {
        loop_back: ['NodeId'],
        loop_out: ['NodeId'],
        loop_fail_node: ['NodeId'],
      },
    };

    function isNodeRefAcceptedTypes(acceptedTypes) {
      const list = Array.isArray(acceptedTypes) ? acceptedTypes : [];
      return list.some((name) => NODE_REF_TYPE_NAMES.has(String(name || '').toLowerCase()));
    }

    function findControlDeclaration(controlFullName) {
      if (!controlFullName) return null;
      const plugins = pluginCatalogData.items || [];
      for (const plugin of plugins) {
        const controls = plugin.controls || [];
        const hit = controls.find((item) => item.full_name === controlFullName);
        if (hit) return hit;
      }
      return null;
    }

    function findActionDeclaration(actionFullName) {
      if (!actionFullName) return null;
      const plugins = pluginCatalogData.items || [];
      for (const plugin of plugins) {
        const actions = plugin.actions || [];
        const hit = actions.find((item) => item.full_name === actionFullName);
        if (hit) return hit;
      }
      return null;
    }

    function listCatalogTypes(kind) {
      const plugins = pluginCatalogData.items || [];
      const names = [];
      for (const plugin of plugins) {
        const items = kind === 'action' ? (plugin.actions || []) : (plugin.controls || []);
        for (const item of items) {
          if (item.full_name) names.push(item.full_name);
        }
      }
      return Array.from(new Set(names)).sort((a, b) => a.localeCompare(b));
    }

    function getNodeIdOptionsForFlow(flow, currentNodeId = '') {
      const nodes = flow?.nodes || [];
      const options = nodes
        .map((item) => item.node_id || '')
        .filter((id) => id && id !== currentNodeId)
        .sort((a, b) => a.localeCompare(b));
      return ['', ...options];
    }

    function normalizeAcceptedTypes(acceptedTypes) {
      const list = Array.isArray(acceptedTypes) ? acceptedTypes : [];
      return list.map((name) => String(name || '').toLowerCase());
    }

    function resolveFieldEditorType(field, flow, currentNodeId = '') {
      const accepted = normalizeAcceptedTypes(field?.accepted_types);
      if (accepted.some((name) => NODE_REF_TYPE_NAMES.has(name))) {
        return {
          type: 'select',
          options: getNodeIdOptionsForFlow(flow, currentNodeId),
        };
      }
      if (accepted.includes('bool') || accepted.includes('boolean')) {
        return {
          type: 'select',
          options: ['', 'true', 'false'],
        };
      }
      if (accepted.includes('int') || accepted.includes('float') || accepted.includes('number')) {
        return {
          type: 'number',
          options: [],
        };
      }
      return {
        type: 'text',
        options: [],
      };
    }

    function resolveNodeRefParamKeys(controlFullName) {
      const fromCatalog = findControlDeclaration(controlFullName);
      if (fromCatalog && Array.isArray(fromCatalog.inputs)) {
        return new Set(
          fromCatalog.inputs
            .filter((field) => isNodeRefAcceptedTypes(field.accepted_types))
            .map((field) => field.name)
            .filter(Boolean)
        );
      }

      const fallback = CONTROL_INPUT_TYPES_FALLBACK[controlFullName] || {};
      return new Set(
        Object.entries(fallback)
          .filter(([, acceptedTypes]) => isNodeRefAcceptedTypes(acceptedTypes))
          .map(([name]) => name)
      );
    }

    function requiredLabel(label, required = false) {
      const star = required ? '<span class="field-required">*</span>' : '';
      return `${star}${escapeHtml(label)}`;
    }

    function renderOutputsRows(node) {
      const outputs = Array.isArray(node?.outputs) ? node.outputs : [];
      if (!outputs.length) {
        const emptyNote = workflowWorkspaceData.editMode ? '当前无输出映射，可点击 + 添加。' : '(空)';
        return `<div class="placeholder">${emptyNote}</div>`;
      }
      return `
        <div class="workflow-output-list ${workflowWorkspaceData.editMode ? 'editable' : ''}">
          ${outputs.map((item, index) => {
            const src = String(item?.src || '').trim();
            const name = String(item?.name || src || '').trim();
            const pos = String(item?.pos || 'flow').trim() || 'flow';
            const cvt = String(item?.cvt || '').trim();
            const editableClass = workflowWorkspaceData.editMode ? 'editable' : '';
            return `
              <div class="workflow-output-item ${editableClass}" data-output-index="${index}">
                <div class="workflow-output-row">
                  <span class="workflow-output-label">src</span>
                  <span class="workflow-output-name mono ${editableClass}" data-output-inline-field="src" data-output-index="${index}" title="${escapeHtml(src || '-')}\">${escapeHtml(src || '-')}</span>
                </div>
                <div class="workflow-output-row">
                  <span class="workflow-output-label">cvt</span>
                  <span class="workflow-output-cvt mono ${editableClass}" data-output-inline-field="cvt" data-output-index="${index}">${escapeHtml(cvt || 'raw')}</span>
                </div>
                <div class="workflow-output-row">
                  <span class="workflow-output-label">to</span>
                  <span class="workflow-output-path mono">
                    <span class="workflow-output-chip workflow-output-chip--pos ${editableClass}" data-output-inline-field="pos" data-output-index="${index}">${escapeHtml(pos)}</span>
                    <span>.</span>
                    <span class="workflow-output-target-name ${editableClass}" data-output-inline-field="name" data-output-index="${index}">${escapeHtml(name || '-')}</span>
                  </span>
                </div>
                ${workflowWorkspaceData.editMode ? '<button class="danger icon-only" type="button" data-output-delete="' + index + '" title="删除输出项" aria-label="删除输出项"><span class="font-icon" aria-hidden="true">🗑</span></button>' : ''}
              </div>
            `;
          }).join('')}
        </div>
      `;
    }

    function bindOutputEditors() {
      if (!workflowWorkspaceData.editMode) return;
      const draft = getWorkflowDraftFlow();
      const context = getSelectedNodeContext(draft, workflowWorkspaceData.selectedNodeKey);
      if (!context?.node) return;

      const updateOutputField = (index, field, value) => {
        const outputs = Array.isArray(context.node.outputs) ? context.node.outputs : [];
        if (!outputs[index]) return;
        outputs[index][field] = String(value ?? '').trim();
        context.node.outputs = outputs;
      };

      for (const token of qsa('[data-output-inline-field][data-output-index]')) {
        token.addEventListener('dblclick', () => {
          if (!(token instanceof HTMLElement)) return;
          const field = token.getAttribute('data-output-inline-field') || '';
          const rawIndex = token.getAttribute('data-output-index') || '';
          const index = Number(rawIndex);
          if (!field || !Number.isInteger(index) || index < 0) return;

          const outputs = Array.isArray(context.node.outputs) ? context.node.outputs : [];
          const item = outputs[index];
          if (!item) return;

          if (field === 'pos' || field === 'cvt') {
            const options = field === 'pos' ? ['flow', 'global'] : ['', 'int', 'float', 'str', 'bool'];
            const current = String(item[field] || '').trim();
            token.innerHTML = `<select class="workflow-edit-input mono">${options.map((option) => {
              const selected = option === current ? 'selected' : '';
              return `<option value="${escapeHtml(option)}" ${selected}>${escapeHtml(option || 'raw')}</option>`;
            }).join('')}</select>`;
            const select = token.querySelector('select');
            if (!(select instanceof HTMLSelectElement)) return;
            select.focus();
            const commit = () => {
              updateOutputField(index, field, select.value || '');
              renderWorkflowProps();
            };
            select.addEventListener('change', commit);
            select.addEventListener('blur', commit);
            return;
          }

          const current = String(item[field] || '').trim();
          token.innerHTML = `<input class="workflow-edit-input mono" value="${escapeHtml(current)}" />`;
          const input = token.querySelector('input');
          if (!(input instanceof HTMLInputElement)) return;
          input.focus();
          const commit = (rollback = false) => {
            if (!rollback) {
              updateOutputField(index, field, input.value || '');
            }
            renderWorkflowProps();
          };
          input.addEventListener('blur', () => commit(false));
          input.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              commit(true);
              return;
            }
            if (event.key === 'Enter') {
              event.preventDefault();
              commit(false);
            }
          });
        });
      }

      for (const btn of qsa('[data-output-delete]')) {
        btn.addEventListener('click', () => {
          const rawIndex = btn.getAttribute('data-output-delete') || '';
          const index = Number(rawIndex);
          if (!Number.isInteger(index) || index < 0) return;
          const outputs = Array.isArray(context.node.outputs) ? context.node.outputs : [];
          outputs.splice(index, 1);
          context.node.outputs = outputs;
          renderWorkflowProps();
        });
      }

      const addBtn = qs('#workflowAddOutputBtn');
      if (addBtn) {
        addBtn.addEventListener('click', () => {
          const outputs = Array.isArray(context.node.outputs) ? context.node.outputs : [];
          outputs.push({ src: '', name: '', pos: 'flow', cvt: '' });
          context.node.outputs = outputs;
          renderWorkflowProps();
        });
      }
    }

    function renderKeyValueRows(obj, nodeRefKeys, options = {}) {
      const values = obj || {};
      const declarationInputs = Array.isArray(options.declarationInputs) ? options.declarationInputs : [];
      const editable = !!options.editable;
      const kind = options.kind || '';
      const flow = options.flow || null;
      const node = options.node || null;

      const declaredNames = new Set(declarationInputs.map((field) => field.name).filter(Boolean));
      const extras = Object.keys(values).filter((name) => !declaredNames.has(name));
      const hasDeclaration = declarationInputs.length > 0;
      if (!hasDeclaration && extras.length === 0) {
        return '<tr><td colspan="2" class="mono">(空)</td></tr>';
      }

      const rows = [];
      for (const field of declarationInputs) {
        const key = field.name || '';
        if (!key) continue;
        const value = values[key] ?? field.default ?? '';
        const isNodeRef = nodeRefKeys && nodeRefKeys.has(key);
        if (editable && kind && flow && node) {
          const editor = resolveFieldEditorType(field, flow, node.node_id || '');
          const optionsJson = escapeHtml(JSON.stringify(editor.options || []));
          const displayValue = valueToDisplayText(value) || '-';
          const nodeRefTag = isNodeRef ? '<span class="prop-node-ref-tag">node</span>' : '';
          rows.push(`<tr><th>${requiredLabel(key, !!field.required)}</th><td>${nodeRefTag}<span class="mono workflow-inline-edit-cell editable" data-contract-inline-kind="${escapeHtml(kind)}" data-contract-inline-field="${escapeHtml(key)}" data-contract-inline-type="${escapeHtml(editor.type)}" data-contract-inline-options="${optionsJson}">${escapeHtml(displayValue)}</span></td></tr>`);
        } else {
          const valHtml = isNodeRef
            ? `<span class="prop-node-ref-tag">node</span><span class="mono">${escapeHtml(valueToDisplayText(value))}</span>`
            : `<span class="mono">${escapeHtml(valueToDisplayText(value))}</span>`;
          rows.push(`<tr><th>${requiredLabel(key, !!field.required)}</th><td>${valHtml}</td></tr>`);
        }
      }

      for (const key of extras) {
        const value = values[key];
        if (editable && kind) {
          rows.push(`<tr><th>${requiredLabel(key, false)}</th><td><span class="mono workflow-inline-edit-cell editable" data-contract-inline-kind="${escapeHtml(kind)}" data-contract-inline-field="${escapeHtml(key)}" data-contract-inline-type="text" data-contract-inline-options="[]">${escapeHtml(valueToDisplayText(value) || '-')}</span></td></tr>`);
        } else {
          const isNodeRef = nodeRefKeys && nodeRefKeys.has(key);
          const valHtml = isNodeRef
            ? `<span class="prop-node-ref-tag">node</span><span class="mono">${escapeHtml(valueToDisplayText(value))}</span>`
            : `<span class="mono">${escapeHtml(valueToDisplayText(value))}</span>`;
          rows.push(`<tr><th>${requiredLabel(key, false)}</th><td>${valHtml}</td></tr>`);
        }
      }

      if (rows.length === 0) {
        return '<tr><td colspan="2" class="mono">(空)</td></tr>';
      }
      return rows.join('');
    }

    async function ensureLogin() {
      try {
        const me = await request('/panel/api/me');
        loginMask.style.display = 'none';
        qs('#panelUser').textContent = me.username || '-';
        qs('#panelUserHint').textContent = me.needs_reset ? '建议尽快重置密码' : `更新于 ${me.updated_at || '-'}`;
        const avatar = qs('#menuUserAvatar');
        if (avatar) {
          const first = (me.username || 'U').trim().charAt(0) || 'U';
          avatar.textContent = first.toUpperCase();
        }
        return true;
      } catch {
        loginMask.style.display = 'grid';
        return false;
      }
    }

    function setActiveTab(tab) {
      for (const item of qsa('[data-tab]')) {
        item.classList.toggle('active', item.getAttribute('data-tab') === tab);
      }
      for (const section of qsa('.section')) {
        section.classList.toggle('active', section.id === tab);
      }
      const meta = tabMeta[tab] || tabMeta.overview;
      qs('#workspaceTitle').textContent = meta.title;
      qs('#workspaceDesc').textContent = meta.desc;
    }

    function renderOverview(data) {
      const stats = [
        { k: 'Service', v: data.service?.status || 'unknown' },
        { k: '任务队列', v: `${data.task_queue?.queued ?? 0} queued / ${data.task_queue?.running ?? 0} running` },
        { k: '会话数(最近)', v: String(data.session_count ?? 0) },
      ];
      qs('#stats').innerHTML = stats.map(item => `
        <div class="stat">
          <div class="k">${item.k}</div>
          <div class="v">${item.v}</div>
        </div>
      `).join('');
    }

    function sourceLabel(source) {
      if (!source) return 'unknown';
      if (source === 'builtin') return 'builtin';
      if (source.startsWith('plugin_root:')) return 'plugin_root';
      if (source.startsWith('entry_point:')) return 'entry_point';
      return source;
    }

    function sanitizeInternalText(text) {
      const raw = String(text ?? '');
      return raw
        .replace(/plugin_root:[^\s]+/g, 'plugin_root')
        .replace(/\/[A-Za-z0-9._\-/]+/g, '[internal path]');
    }

    function renderFieldList(fields, kind) {
      if (!fields || fields.length === 0) {
        return '<div class="placeholder" style="padding:10px;">未声明' + (kind === 'input' ? '输入' : '输出') + '约定</div>';
      }
      return `<div class="field-list">${fields.map((field) => {
        const tags = [];
        if (kind === 'input') {
          tags.push(`<span class="field-tag">${(field.accepted_types || ['any']).join(' | ')}</span>`);
          if (field.default !== undefined && field.default !== null && field.default !== '') {
            tags.push(`<span class="field-tag">default: ${valueToDisplayText(field.default)}</span>`);
          }
        } else if (field.type) {
          tags.push(`<span class="field-tag">${field.type}</span>`);
        }
        return `<div class="field-card">
          <div class="field-head">
            <span class="field-name mono">${kind === 'input' && field.required ? '<span class="field-required">*</span>' : ''}${field.name || '-'}</span>
            <span class="field-tags">${tags.join('')}</span>
          </div>
          <div class="contract-desc">${field.description || '无说明'}</div>
        </div>`;
      }).join('')}</div>`;
    }

    function findPluginSelection() {
      const items = pluginCatalogData.items || [];
      if (pluginPanelSelected.type === 'overview') {
        return { overview: true };
      }
      if (pluginPanelSelected.type === 'plugin' && pluginPanelSelected.package) {
        const plugin = items.find((item) => item.package === pluginPanelSelected.package);
        if (plugin) return { plugin };
      }
      if (pluginPanelSelected.type === 'kind-group' && pluginPanelSelected.package && pluginPanelSelected.kind) {
        const plugin = items.find((item) => item.package === pluginPanelSelected.package);
        if (plugin) return { plugin, kindGroup: pluginPanelSelected.kind };
      }
      if (pluginPanelSelected.type === 'leaf' && pluginPanelSelected.package && pluginPanelSelected.fullName) {
        const plugin = items.find((item) => item.package === pluginPanelSelected.package);
        if (plugin) {
          const collection = pluginPanelSelected.kind === 'control' ? (plugin.controls || []) : (plugin.actions || []);
          const leaf = collection.find((item) => item.full_name === pluginPanelSelected.fullName);
          if (leaf) return { plugin, leaf };
        }
      }
      return null;
    }

    function ensurePluginSelection(items) {
      const selected = findPluginSelection();
      if (selected) return;
      // 默认选中"总览"节点
      pluginPanelSelected = { type: 'overview', package: '', kind: '', fullName: '' };
    }

    function pluginGroupStateKey(packageName, kind) {
      return `${packageName}:${kind}`;
    }

    function isPluginPackageOpen(packageName) {
      if (Object.prototype.hasOwnProperty.call(pluginTreeState.packages, packageName)) {
        return pluginTreeState.packages[packageName];
      }
      return true;
    }

    function isPluginGroupOpen(packageName, kind) {
      const key = pluginGroupStateKey(packageName, kind);
      if (Object.prototype.hasOwnProperty.call(pluginTreeState.groups, key)) {
        return pluginTreeState.groups[key];
      }
      if (pluginPanelSelected.package === packageName && pluginPanelSelected.kind === kind) {
        return true;
      }
      return false;
    }

    function openPluginPath(packageName, kind = '') {
      if (!packageName) return;
      pluginTreeState.packages[packageName] = true;
      if (kind) {
        pluginTreeState.groups[pluginGroupStateKey(packageName, kind)] = true;
      }
    }

    function renderPluginTree(items) {
      const tree = qs('#pluginTree');
      if (!items || items.length === 0) {
        tree.innerHTML = '<div class="placeholder">暂无插件</div>';
        return;
      }

      // 构建总览和上传按钮（一行）
      const overviewHtml = `
        <div style="display:flex;align-items:center;gap:8px;padding:0;margin-bottom:0;">
          <button class="tree-overview-btn" id="overviewBtn">总览</button>
          <button class="primary" id="pluginUploadBtn">
            <svg viewBox="0 0 24 24"><path d="M12 2v12M5 10l7-7 7 7M5 20h14"/></svg>
          </button>
          <input id="pluginFileInput" type="file" accept=".zip" hidden />
        </div>
        <div style="height:1px;background:var(--line);margin:6px 0;"></div>
      `;

      // 构建插件包节点
      const packagesHtml = items.map((plugin) => {
        const actionCount = plugin.actions?.length || 0;
        const controlCount = plugin.controls?.length || 0;
        const packageOpenAttr = isPluginPackageOpen(plugin.package) ? ' open' : '';
        return `
          <details class="tree-section"${packageOpenAttr}>
            <summary class="plugin-package-summary" data-plugin-package="${plugin.package}" data-package-name="${plugin.package}">
              <span class="tree-section-title mono">${plugin.package}</span>
            </summary>
            <div style="display:grid;gap:6px;">
              ${actionCount > 0 ? renderPluginTreeSection('Actions', plugin.actions || [], plugin.package) : ''}
              ${controlCount > 0 ? renderPluginTreeSection('Controls', plugin.controls || [], plugin.package) : ''}
            </div>
          </details>
        `;
      }).join('');

      tree.innerHTML = overviewHtml + packagesHtml;

      // 总览按钮点击
      const overviewBtn = qs('#overviewBtn');
      if (overviewBtn) {
        overviewBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          pluginPanelSelected = { type: 'overview', package: '', kind: '', fullName: '' };
          renderPluginsPanel(pluginCatalogData);
        });
      }

      // 上传按钮事件
      const uploadBtn = qs('#pluginUploadBtn');
      const fileInput = qs('#pluginFileInput');
      if (uploadBtn && fileInput) {
        uploadBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          fileInput.click();
        });
        fileInput.addEventListener('change', async (e) => {
          if (e.target.files.length > 0) {
            try {
              uploadBtn.disabled = true;
              uploadBtn.innerHTML = '<span style="font-size: .9rem;">上传中...</span>';
              await uploadPluginFile(e.target.files[0]);
              showCopyToast('✓ 插件上传成功');
              fileInput.value = '';
            } catch (err) {
              alert('✗ 上传失败: ' + (err.message || '未知错误'));
            } finally {
              uploadBtn.disabled = false;
              uploadBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 2v12M5 10l7-7 7 7M5 20h14"/></svg>';
            }
          }
        });
      }

      // 插件包点击（防止冒泡到 details 展开动作）
      for (const summary of qsa('.plugin-package-summary')) {
        summary.addEventListener('click', (e) => {
          e.preventDefault();
          const packageName = summary.getAttribute('data-package-name');
          pluginTreeState.packages[packageName] = !isPluginPackageOpen(packageName);
          pluginPanelSelected = { type: 'plugin', package: packageName, kind: '', fullName: '' };
          renderPluginsPanel(pluginCatalogData);
        });
      }

      // Actions/Controls 二级节点点击
      for (const summary of qsa('.plugin-kind-summary')) {
        summary.addEventListener('click', (e) => {
          e.preventDefault();
          const packageName = summary.getAttribute('data-plugin-package');
          const kind = summary.getAttribute('data-plugin-kind-group');
          const stateKey = pluginGroupStateKey(packageName, kind);
          pluginTreeState.packages[packageName] = true;
          pluginTreeState.groups[stateKey] = !isPluginGroupOpen(packageName, kind);
          pluginPanelSelected = {
            type: 'kind-group',
            package: packageName,
            kind: kind,
            fullName: '',
          };
          renderPluginsPanel(pluginCatalogData);
        });
      }

      // 具体 action/control 项点击
      for (const btn of qsa('[data-plugin-leaf]')) {
        btn.addEventListener('click', () => {
          const packageName = btn.getAttribute('data-plugin-package') || '';
          const kind = btn.getAttribute('data-plugin-kind') || '';
          openPluginPath(packageName, kind);
          pluginPanelSelected = {
            type: 'leaf',
            package: packageName,
            kind: kind,
            fullName: btn.getAttribute('data-plugin-leaf') || '',
          };
          renderPluginsPanel(pluginCatalogData);
        });
      }
    }

    function renderPluginTreeSection(label, items, packageName) {
      if (!items || items.length === 0) {
        return '';
      }

      const kind = label === 'Actions' ? 'action' : 'control';
      const kindTag = label === 'Actions' ? 'A' : 'C';
      const groupOpenAttr = isPluginGroupOpen(packageName, kind) ? ' open' : '';

      return `
        <details class="tree-section nested-tree-section"${groupOpenAttr}>
          <summary class="plugin-kind-summary" data-plugin-package="${packageName}" data-plugin-kind-group="${kind}">
            <span style="color:var(--muted);">${label} (${items.length})</span>
          </summary>
          <div style="display:grid;gap:4px;">
            ${items.map((item) => {
              const selected = pluginPanelSelected.type === 'leaf' && pluginPanelSelected.fullName === item.full_name;
              return `
                <button class="tree-node child-level-1 ${selected ? 'active' : ''}" 
                  data-plugin-leaf="${item.full_name}" 
                  data-plugin-kind="${kind}" 
                  data-plugin-package="${packageName}">
                  <span class="tree-node-name mono">${item.name}</span>
                  <span class="tree-node-count">${kindTag}</span>
                </button>
              `;
            }).join('')}
          </div>
        </details>
      `;
    }

    function renderPluginDetail(items) {
      const detail = qs('#pluginDetail');
      if (!items || items.length === 0) {
        detail.innerHTML = '<div class="placeholder">当前没有可展示的插件。</div>';
        return;
      }

      // 处理总览节点
      if (pluginPanelSelected.type === 'overview') {
        const totalActions = items.reduce((sum, item) => sum + (item.action_count || 0), 0);
        const totalControls = items.reduce((sum, item) => sum + (item.control_count || 0), 0);
        const errors = pluginCatalogData.errors || [];

        detail.innerHTML = `
          <div class="plugin-detail-head">
            <div class="plugin-detail-title">系统插件概览</div>
            <div class="contract-desc">查看已加载的所有插件及统计信息</div>
          </div>
          <div class="mini-grid">
            <div class="mini-card"><div class="mini-k">插件数</div><div class="mini-v">${items.length}</div></div>
            <div class="mini-card"><div class="mini-k">Actions</div><div class="mini-v">${totalActions}</div></div>
            <div class="mini-card"><div class="mini-k">Controls</div><div class="mini-v">${totalControls}</div></div>
          </div>
          ${errors.length ? `
            <div>
              <div class="contract-section-title" style="color:var(--bad);">⚠ 加载错误</div>
              <div class="error-list">
                ${errors.map((item) => `<div class="error-item">
                  <div><strong>${sourceLabel(item.source || 'plugin')}</strong></div>
                  <div class="mono">${item.module || item.package || '-'}</div>
                  <div>${sanitizeInternalText(item.error || 'unknown error')}</div>
                </div>`).join('')}
              </div>
            </div>
          ` : '<div class="placeholder" style="padding:12px;">✓ 所有插件加载正常</div>'}
        `;
        return;
      }

      // 处理 Actions/Controls 分类节点
      if (pluginPanelSelected.type === 'kind-group') {
        const plugin = items.find(p => p.package === pluginPanelSelected.package);
        if (!plugin) {
          detail.innerHTML = '<div class="placeholder">未找到插件</div>';
          return;
        }

        const isAction = pluginPanelSelected.kind === 'action';
        const kindLabel = isAction ? 'Actions' : 'Controls';
        const items_list = isAction ? (plugin.actions || []) : (plugin.controls || []);

        detail.innerHTML = `
          <div class="plugin-detail-head">
            <div class="plugin-detail-title">${kindLabel}</div>
            <div class="contract-desc">共 ${items_list.length} 个 ${kindLabel === 'Actions' ? '动作' : '控制'}</div>
            <div class="plugin-detail-meta">
              <span class="field-tag">插件 ${plugin.package}</span>
            </div>
          </div>
          ${renderPluginDetailList(items_list, plugin, isAction ? 'action' : 'control')}
        `;
        return;
      }

      // 处理插件级选择：只显示插件信息和数量，不显示列表
      const selected = findPluginSelection();
      const plugin = selected?.plugin || items[0];
      if (!plugin) {
        detail.innerHTML = '<div class="placeholder">当前没有可展示的插件。</div>';
        return;
      }

      // 处理 leaf 级选择
      const leaf = selected?.leaf || null;
      if (leaf) {
        detail.innerHTML = `
          <div class="plugin-detail-head">
            <div class="plugin-detail-title mono">${leaf.full_name}</div>
            <div class="contract-desc">${leaf.description || '无说明'}</div>
            <div class="plugin-detail-meta">
              <span class="field-tag">${leaf.kind}</span>
              <span class="field-tag">plugin ${plugin.package}</span>
              <span class="field-tag">${sourceLabel(plugin.source)}</span>
            </div>
          </div>
          <div>
            <div class="contract-section-title">输入约定</div>
            ${renderFieldList(leaf.inputs || [], 'input')}
          </div>
          <div>
            <div class="contract-section-title">输出约定</div>
            ${renderFieldList(leaf.outputs || [], 'output')}
          </div>
        `;
        return;
      }

      // 插件级选择：只显示基本信息和数量
      detail.innerHTML = `
        <div class="plugin-detail-head">
          <div class="plugin-detail-title mono">${plugin.package}</div>
          <div class="contract-desc">${plugin.description || '该插件未提供额外说明。'}</div>
          <div class="plugin-detail-meta">
            <span class="field-tag">${sourceLabel(plugin.source)}</span>
            <span class="field-tag">actions ${plugin.action_count || 0}</span>
            <span class="field-tag">controls ${plugin.control_count || 0}</span>
          </div>
        </div>
        <div class="mini-grid">
          <div class="mini-card"><div class="mini-k">Action 数量</div><div class="mini-v">${plugin.action_count || 0}</div></div>
          <div class="mini-card"><div class="mini-k">Control 数量</div><div class="mini-v">${plugin.control_count || 0}</div></div>
          <div class="mini-card"><div class="mini-k">来源</div><div class="mini-v">${sourceLabel(plugin.source)}</div></div>
        </div>
        <div style="padding:12px;color:var(--muted);font-size:.9rem;background:#f5f5f5;border-radius:10px;">
          点击左侧 <strong>Actions</strong> 或 <strong>Controls</strong> 查看具体内容
        </div>
      `;
    }

    function renderPluginDetailList(items, plugin, kind) {
      return `
        <div class="contract-block">
          <table>
            <thead><tr><th>名称</th><th>说明</th><th>输入</th><th>输出</th></tr></thead>
            <tbody>
              ${items.map((item) => `<tr><td class="mono"><a href="javascript:void(0)" class="detail-list-link" data-full-name="${item.full_name}" data-kind="${kind}" data-package="${plugin.package}">${item.name}</a></td><td>${item.description || '-'}</td><td>${item.inputs?.length || 0}</td><td>${item.outputs?.length || 0}</td></tr>`).join('')}
            </tbody>
          </table>
        </div>
      `;
    }

    function renderPluginsPanel(data) {
      const items = data.items || [];
      pluginCatalogData = data;
      ensurePluginSelection(items);
      renderPluginTree(items);
      renderPluginDetail(items);

      // 添加表格链接点击事件
      for (const link of qsa('.detail-list-link')) {
        link.addEventListener('click', (e) => {
          e.preventDefault();
          const packageName = link.getAttribute('data-package');
          const kind = link.getAttribute('data-kind');
          openPluginPath(packageName, kind);
          pluginPanelSelected = {
            type: 'leaf',
            package: packageName,
            kind: kind,
            fullName: link.getAttribute('data-full-name'),
          };
          renderPluginsPanel(pluginCatalogData);
        });
      }
    }

    async function refreshPluginsPanel() {
      const data = await request('/panel/api/plugins');
      renderPluginsPanel(data);
    }

    async function uploadPluginFile(file) {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch('/panel/api/plugins/upload', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || data.detail || `HTTP ${res.status}`);
      // 上传成功后刷新插件列表
      await refreshPluginsPanel();
      return data;
    }

    function updateWorkflowLayoutState() {
      const layout = qs('#workflowLayout');
      if (!layout) return;
      layout.classList.toggle('prop-collapsed', !!workflowWorkspaceData.propCollapsed);
      const toggleBtn = qs('#workflowPropToggleBtn');
      if (toggleBtn) {
        toggleBtn.title = workflowWorkspaceData.propCollapsed ? '显示属性窗格' : '隐藏属性窗格';
        toggleBtn.setAttribute('aria-label', toggleBtn.title);
      }
    }

    function selectWorkflowNode(nodeId) {
      workflowWorkspaceData.selectedNodeKey = nodeId || '';
      renderWorkflowWorkspace();
    }

    function getWorkflowDisplayItem(workflowName) {
      const items = workflowWorkspaceData.workflowItems || [];
      return items.find((item) => item.workflow === workflowName) || { workflow: workflowName, name: workflowName };
    }

    function collectFlowGroups(flow, parentKey = 'main', parentLabel = '主流程', depth = 0) {
      if (!flow) return [];
      const flowLabel = depth === 0
        ? `主流程 · ${flow.name || flow.flow_id || '-'}`
        : `${parentLabel} / ${flow.name || flow.flow_id || '-'}`;
      const group = {
        flowKey: parentKey,
        flowLabel,
        flowId: flow.flow_id || '',
        depth,
        nodes: flow.nodes || [],
      };
      const subflows = flow.sub_flows || [];
      const children = subflows.flatMap((subFlow, idx) => collectFlowGroups(subFlow, `${parentKey}.${idx}`, flowLabel, depth + 1));
      return [group, ...children];
    }

    function flattenFlowNodes(flow) {
      const groups = collectFlowGroups(flow);
      return groups.flatMap((group) => {
        const nodes = group.nodes || [];
        return nodes.map((node) => ({
          key: `${group.flowKey}::${node.node_id || ''}`,
          group,
          node,
        }));
      });
    }

    function getFlowByGroupKey(flow, flowKey) {
      if (!flow || !flowKey) return null;
      if (flowKey === 'main') return flow;
      const parts = flowKey.split('.').slice(1);
      let cursor = flow;
      for (const part of parts) {
        const index = Number(part);
        if (!Number.isInteger(index) || index < 0) return null;
        const subFlows = cursor.sub_flows || [];
        cursor = subFlows[index];
        if (!cursor) return null;
      }
      return cursor;
    }

    function getSelectedNodeContext(flow = workflowWorkspaceData.flow, selectedNodeKey = workflowWorkspaceData.selectedNodeKey) {
      if (!flow || !selectedNodeKey) return null;
      const sep = selectedNodeKey.indexOf('::');
      if (sep <= 0) return null;
      const flowKey = selectedNodeKey.slice(0, sep);
      const nodeId = selectedNodeKey.slice(sep + 2);
      const targetFlow = getFlowByGroupKey(flow, flowKey);
      if (!targetFlow) return null;
      const nodes = targetFlow.nodes || [];
      const index = nodes.findIndex((item) => item.node_id === nodeId);
      if (index < 0) return null;
      const groups = collectFlowGroups(flow);
      const group = groups.find((item) => item.flowKey === flowKey) || null;
      return {
        flowKey,
        flow: targetFlow,
        group,
        index,
        node: nodes[index],
      };
    }

    function getWorkflowDraftFlow() {
      return workflowWorkspaceData.editMode ? workflowWorkspaceData.editFlow : workflowWorkspaceData.flow;
    }

    function startWorkflowEditMode() {
      if (!workflowWorkspaceData.flow) return;
      workflowWorkspaceData.editMode = true;
      workflowWorkspaceData.editFlow = deepClone(workflowWorkspaceData.flow);
      renderWorkflowWorkspace();
    }

    function cancelWorkflowEditMode() {
      workflowWorkspaceData.editMode = false;
      workflowWorkspaceData.editFlow = null;
      renderWorkflowWorkspace();
    }

    function renderEditableCell(value, path, type = 'text', options = []) {
      const display = type === 'json-object' || type === 'json-array'
        ? prettyJson(value, type === 'json-array' ? [] : {})
        : valueToDisplayText(value);
      const escapedDisplay = escapeHtml(display || '-');
      if (!workflowWorkspaceData.editMode) {
        return `<span class="mono">${escapedDisplay}</span>`;
      }
      const optionsPayload = escapeHtml(JSON.stringify(options || []));
      return `<span class="mono workflow-inline-edit-cell editable" data-edit-path="${escapeHtml(path)}" data-edit-type="${escapeHtml(type)}" data-edit-options="${optionsPayload}">${escapedDisplay}</span>`;
    }

    function applyWorkflowFieldEdit(path, rawText, type = 'text') {
      const flow = getWorkflowDraftFlow();
      if (!flow || !workflowWorkspaceData.editMode) return { changed: false };
      if (path.startsWith('flow.')) {
        const field = path.slice(5);
        if (field === 'display_name') {
          flow.name = String(rawText ?? '').trim();
          return { changed: true };
        }
        if (field === 'name' || field === 'description' || field === 'start_node_id' || field === 'log') {
          flow[field] = String(rawText ?? '').trim();
          return { changed: true };
        }
        return { changed: false };
      }

      if (path.startsWith('node.')) {
        const context = getSelectedNodeContext(flow, workflowWorkspaceData.selectedNodeKey);
        if (!context) throw new Error('当前节点不存在');
        const node = context.node;
        const field = path.slice(5);
        if (field === 'node_id') {
          const nextNodeId = String(rawText ?? '').trim();
          if (!nextNodeId) throw new Error('node_id 不能为空');
          if (context.flow.nodes.some((item, idx) => idx !== context.index && item.node_id === nextNodeId)) {
            throw new Error(`节点 ID 已存在: ${nextNodeId}`);
          }
          const oldNodeId = node.node_id || '';
          node.node_id = nextNodeId;
          if ((context.flow.start_node_id || '') === oldNodeId) {
            context.flow.start_node_id = nextNodeId;
          }
          workflowWorkspaceData.selectedNodeKey = `${context.flowKey}::${nextNodeId}`;
          return { changed: true };
        }
        if (field === 'name' || field === 'description' || field === 'action' || field === 'control' || field === 'log') {
          node[field] = String(rawText ?? '').trim();
          return { changed: true };
        }
        if (field === 'inputs') {
          node.inputs = parseObjectJson('inputs', rawText, {});
          return { changed: true };
        }
        if (field === 'params') {
          node.params = parseObjectJson('params', rawText, {});
          return { changed: true };
        }
        if (field === 'outputs') {
          node.outputs = parseArrayJson('outputs', rawText, []);
          return { changed: true };
        }
      }

      return { changed: false };
    }

    function bindWorkflowInlineEditors() {
      if (!workflowWorkspaceData.editMode) return;
      for (const cell of qsa('[data-edit-path]')) {
        cell.addEventListener('dblclick', () => {
          if (!(cell instanceof HTMLElement)) return;
          if (cell.getAttribute('data-editing') === '1') return;
          const path = cell.getAttribute('data-edit-path') || '';
          const type = cell.getAttribute('data-edit-type') || 'text';
          const optionsJson = cell.getAttribute('data-edit-options') || '[]';
          if (!path) return;
          const initialText = cell.textContent || '';
          let options = [];
          try {
            options = JSON.parse(optionsJson);
          } catch {
            options = [];
          }
          cell.setAttribute('data-editing', '1');
          const useTextarea = type === 'json-object' || type === 'json-array' || initialText.length > 80;
          const useSelect = type === 'select';
          const useNumber = type === 'number';
          cell.innerHTML = `
            <div class="workflow-inline-editor">
              ${useSelect
                ? `<select class="mono">${(options || []).map((option) => {
                  const text = String(option ?? '');
                  const selected = text === (initialText === '-' ? '' : initialText) ? 'selected' : '';
                  return `<option value="${escapeHtml(text)}" ${selected}>${escapeHtml(text || '(空)')}</option>`;
                }).join('')}</select>`
                : useNumber
                  ? `<input class="mono" type="number" value="${escapeHtml(initialText === '-' ? '' : initialText)}" />`
                  : useTextarea
                ? `<textarea class="mono" rows="6">${escapeHtml(initialText === '-' ? '' : initialText)}</textarea>`
                : `<input class="mono" value="${escapeHtml(initialText === '-' ? '' : initialText)}" />`}
            </div>
          `;

          const input = cell.querySelector('input, textarea, select');
          if (input instanceof HTMLElement) input.focus();

          let closed = false;
          const closeEditor = (apply, rollback = false) => {
            if (closed) return;
            closed = true;
            if (!apply || rollback) {
              renderWorkflowWorkspace();
              return;
            }
            try {
              const nextValue = (cell.querySelector('input, textarea, select')?.value || '').trim();
              const result = applyWorkflowFieldEdit(path, nextValue, type);
              if (!result.changed) {
                renderWorkflowWorkspace();
                return;
              }
              renderWorkflowWorkspace();
            } catch (err) {
              alert(err.message || '字段修改失败');
              renderWorkflowWorkspace();
            }
          };

          const editor = cell.querySelector('input, textarea, select');
          if (editor instanceof HTMLSelectElement) {
            editor.addEventListener('change', () => closeEditor(true));
            editor.addEventListener('blur', () => closeEditor(true));
            return;
          }
          if (editor instanceof HTMLInputElement || editor instanceof HTMLTextAreaElement) {
            editor.addEventListener('blur', () => closeEditor(true));
            editor.addEventListener('keydown', (event) => {
              if (event.key === 'Escape') {
                event.preventDefault();
                closeEditor(false, true);
                return;
              }
              if (editor instanceof HTMLInputElement && event.key === 'Enter') {
                event.preventDefault();
                closeEditor(true);
                return;
              }
              if (editor instanceof HTMLTextAreaElement && event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                closeEditor(true);
              }
            });
          }
        });
      }
    }

    function bindContractFieldEditors() {
      if (!workflowWorkspaceData.editMode) return;
      for (const token of qsa('[data-contract-inline-kind][data-contract-inline-field]')) {
        token.addEventListener('dblclick', () => {
          if (!(token instanceof HTMLElement)) return;
          if (token.getAttribute('data-editing') === '1') return;
          const kind = token.getAttribute('data-contract-inline-kind') || '';
          const field = token.getAttribute('data-contract-inline-field') || '';
          const editorType = token.getAttribute('data-contract-inline-type') || 'text';
          const optionsJson = token.getAttribute('data-contract-inline-options') || '[]';
          if (!kind || !field) return;

          const flow = getWorkflowDraftFlow();
          const context = getSelectedNodeContext(flow, workflowWorkspaceData.selectedNodeKey);
          if (!context?.node) return;
          const target = kind === 'action' ? (context.node.inputs || {}) : (context.node.params || {});
          const current = valueToDisplayText(target[field] ?? '');

          let options = [];
          try {
            options = JSON.parse(optionsJson);
          } catch {
            options = [];
          }

          token.setAttribute('data-editing', '1');
          if (editorType === 'select') {
            token.innerHTML = `<select class="workflow-edit-input mono">${options.map((option) => {
              const text = String(option ?? '');
              const selected = text === current ? 'selected' : '';
              return `<option value="${escapeHtml(text)}" ${selected}>${escapeHtml(text || '(空)')}</option>`;
            }).join('')}</select>`;
            const select = token.querySelector('select');
            if (!(select instanceof HTMLSelectElement)) return;
            select.focus();
            const commit = () => {
              const value = (select.value || '').trim();
              if (!value) delete target[field];
              else target[field] = value;
              if (kind === 'action') context.node.inputs = target;
              else context.node.params = target;
              renderWorkflowProps();
            };
            select.addEventListener('change', commit);
            select.addEventListener('blur', commit);
            return;
          }

          const inputType = editorType === 'number' ? 'number' : 'text';
          token.innerHTML = `<input type="${inputType}" class="workflow-edit-input mono" value="${escapeHtml(current)}" />`;
          const input = token.querySelector('input');
          if (!(input instanceof HTMLInputElement)) return;
          input.focus();
          const commit = (rollback = false) => {
            if (!rollback) {
              const value = (input.value || '').trim();
              if (!value) delete target[field];
              else target[field] = value;
              if (kind === 'action') context.node.inputs = target;
              else context.node.params = target;
            }
            renderWorkflowProps();
          };
          input.addEventListener('blur', () => commit(false));
          input.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              commit(true);
              return;
            }
            if (event.key === 'Enter') {
              event.preventDefault();
              commit(false);
            }
          });
        });
      }
    }

    async function saveWorkflowFlow(nextFlow, nextSelectedNodeKey = '') {
      const workflow = workflowWorkspaceData.selectedWorkflow;
      if (!workflow || !nextFlow) {
        throw new Error('请先选择 workflow');
      }
      const data = await request(`/panel/api/workflows/${encodeURIComponent(workflow)}`, 'PUT', { flow: nextFlow });
      workflowWorkspaceData.flow = data.flow || nextFlow;
      workflowWorkspaceData.flowPath = data.path || workflowWorkspaceData.flowPath;
      const allNodes = flattenFlowNodes(workflowWorkspaceData.flow);
      const hasSelected = allNodes.some((item) => item.key === nextSelectedNodeKey);
      workflowWorkspaceData.selectedNodeKey = hasSelected ? nextSelectedNodeKey : '';
      renderWorkflowWorkspace();
      showCopyToast('workflow 已保存');
    }

    async function saveWorkflowEditMode() {
      const flow = getWorkflowDraftFlow();
      if (!flow || !workflowWorkspaceData.editMode) {
        return;
      }
      await saveWorkflowFlow(flow, workflowWorkspaceData.selectedNodeKey || '');
      workflowWorkspaceData.editMode = false;
      workflowWorkspaceData.editFlow = null;
      renderWorkflowWorkspace();
    }

    function requireEditableFlow() {
      if (!workflowWorkspaceData.editMode) {
        alert('请先点击进入编辑');
        return null;
      }
      const flow = getWorkflowDraftFlow();
      if (!flow) {
        alert('请先选择 workflow');
        return null;
      }
      return flow;
    }

    async function addWorkflowNode(targetKey = 'main') {
      const workingFlow = requireEditableFlow();
      if (!workingFlow) return;
      const defaultId = `node_${Date.now().toString().slice(-6)}`;
      const nodeId = (window.prompt('输入新节点 node_id', defaultId) || '').trim();
      if (!nodeId) return;
      const nodeName = (window.prompt('输入节点名称（可选）', nodeId) || '').trim();
      const actionName = (window.prompt('输入 action（可选，例如 builtin.OpenPage）', '') || '').trim();
      const controlName = (window.prompt('输入 control（可选，例如 builtin.NextNode）', 'builtin.NextNode') || '').trim();

      const targetFlow = getFlowByGroupKey(workingFlow, targetKey);
      if (!targetFlow) {
        alert('目标流程不存在');
        return;
      }

      const nodes = targetFlow.nodes || [];
      if (nodes.some((item) => item.node_id === nodeId)) {
        alert(`节点 ID 已存在: ${nodeId}`);
        return;
      }

      nodes.push({
        node_id: nodeId,
        name: nodeName,
        description: '',
        action: actionName,
        inputs: {},
        outputs: [],
        control: controlName,
        params: {},
        log: 'short',
      });
      targetFlow.nodes = nodes;
      if (!targetFlow.start_node_id) {
        targetFlow.start_node_id = nodeId;
      }

      workflowWorkspaceData.selectedNodeKey = `${targetKey}::${nodeId}`;
      renderWorkflowWorkspace();
    }

    async function deleteSelectedNode(flowOverride = null) {
      const workingFlow = flowOverride || requireEditableFlow();
      if (!workingFlow) return;

      const context = getSelectedNodeContext(workingFlow, workflowWorkspaceData.selectedNodeKey);
      if (!context) {
        alert('请先选择节点');
        return;
      }
      const nodeName = context.node.name || context.node.node_id;
      if (!window.confirm(`确认删除节点 ${nodeName}?`)) return;

      const targetFlow = getFlowByGroupKey(workingFlow, context.flowKey);
      if (!targetFlow) {
        alert('节点所在流程不存在');
        return;
      }
      const nodes = targetFlow.nodes || [];
      const removed = nodes.splice(context.index, 1)[0];
      targetFlow.nodes = nodes;
      if (removed && targetFlow.start_node_id === removed.node_id) {
        targetFlow.start_node_id = nodes[0]?.node_id || '';
      }

      workflowWorkspaceData.selectedNodeKey = '';
      renderWorkflowWorkspace();
    }

    function restoreSelectedNodeDraft() {
      if (!workflowWorkspaceData.editMode || !workflowWorkspaceData.flow) {
        return;
      }
      const draftFlow = getWorkflowDraftFlow();
      const context = getSelectedNodeContext(draftFlow, workflowWorkspaceData.selectedNodeKey);
      if (!context) {
        alert('请先选择节点');
        return;
      }

      const sourceFlow = getFlowByGroupKey(workflowWorkspaceData.flow, context.flowKey);
      const sourceNode = sourceFlow?.nodes?.[context.index] || null;
      if (!sourceNode) {
        const nodes = context.flow.nodes || [];
        nodes.splice(context.index, 1);
        context.flow.nodes = nodes;
        workflowWorkspaceData.selectedNodeKey = '';
        renderWorkflowWorkspace();
        return;
      }

      const nextNode = deepClone(sourceNode);
      context.flow.nodes[context.index] = nextNode;
      workflowWorkspaceData.selectedNodeKey = `${context.flowKey}::${nextNode.node_id || ''}`;
      renderWorkflowWorkspace();
    }

    async function deleteCurrentWorkflow() {
      const workflow = workflowWorkspaceData.selectedWorkflow;
      if (!workflow) {
        alert('请先选择 workflow');
        return;
      }
      if (!window.confirm(`确认删除 workflow ${workflow} ?`)) return;
      await request(`/panel/api/workflows/${encodeURIComponent(workflow)}`, 'DELETE');
      showCopyToast(`已删除 workflow: ${workflow}`);
      await refreshWorkflowWorkspace();
    }

    function updateWorkflowToolbarState() {
      const hasWorkflow = !!workflowWorkspaceData.selectedWorkflow;
      const editBtn = qs('#workflowEditBtn');
      const cancelBtn = qs('#workflowCancelEditBtn');
      const saveBtn = qs('#workflowSaveBtn');
      const deleteWorkflowBtn = qs('#workflowDeleteBtn');
      const createTaskBtn = qs('#workflowCreateTaskBtn');
      if (editBtn) editBtn.disabled = !hasWorkflow || workflowWorkspaceData.editMode;
      if (cancelBtn) cancelBtn.disabled = !hasWorkflow || !workflowWorkspaceData.editMode;
      if (saveBtn) saveBtn.disabled = !hasWorkflow || !workflowWorkspaceData.editMode;
      if (deleteWorkflowBtn) deleteWorkflowBtn.disabled = !hasWorkflow;
      if (createTaskBtn) createTaskBtn.disabled = !hasWorkflow || workflowWorkspaceData.editMode;
    }

    function renderWorkflowNav() {
      const nav = qs('#workflowNav');
      const items = workflowWorkspaceData.workflowItems || [];
      if (!nav) return;
      nav.innerHTML = `
        <div class="workflow-nav-title">workflow 列表 (${items.length})</div>
        ${items.length > 0 ? items.map((item) => {
          const workflowName = item.workflow || '';
          const displayName = item.name || workflowName;
          const active = workflowWorkspaceData.selectedWorkflow === workflowName ? 'active' : '';
          return `<button class="workflow-nav-node ${active}" data-workflow-name="${escapeHtml(workflowName)}" title="${escapeHtml(displayName)}">
            <span class="workflow-nav-node-name">${escapeHtml(displayName)}</span>
            <span class="workflow-nav-node-id mono">${escapeHtml(workflowName)}</span>
          </button>`;
        }).join('') : '<div class="placeholder">当前目录没有 workflow 文件。</div>'}
      `;

      for (const btn of qsa('[data-workflow-name]')) {
        btn.addEventListener('click', async () => {
          const name = btn.getAttribute('data-workflow-name') || '';
          if (!name || name === workflowWorkspaceData.selectedWorkflow) return;
          await loadWorkflowDetail(name);
          renderWorkflowWorkspace();
        });
      }
    }

    function renderWorkflowCanvas() {
      const canvas = qs('#workflowCanvas');
      const createBtn = qs('#workflowCreateTaskBtn');
      if (!canvas) return;

      const flow = getWorkflowDraftFlow();
      const groups = collectFlowGroups(flow);
      const allNodes = flattenFlowNodes(flow);
      if (createBtn) createBtn.disabled = !workflowWorkspaceData.selectedWorkflow;

      if (!flow) {
        canvas.innerHTML = '<div class="placeholder">请选择左侧 workflow。</div>';
        return;
      }

      canvas.innerHTML = `
        ${groups.map((group) => {
          const groupNodes = (group.nodes || []).map((node) => {
            const nodeId = node.node_id || '';
            const nodeKey = `${group.flowKey}::${nodeId}`;
            const isActive = workflowWorkspaceData.selectedNodeKey === nodeKey;
            const typeLabel = node.action || node.control || 'unknown';
            const extra = node.action ? 'action' : (node.control ? 'control' : 'node');
            const nodeTypeClass = node.action && node.control ? 'node-type--mixed'
              : node.control ? 'node-type--control'
              : node.action ? 'node-type--action'
              : '';
            return `
              <button class="workflow-node-card ${isActive ? 'active' : ''} ${nodeTypeClass}" data-workflow-node-key="${escapeHtml(nodeKey)}">
                <div class="workflow-node-title">${escapeHtml(node.name || nodeId || '(未命名节点)')}</div>
                <div class="workflow-node-meta">id: ${escapeHtml(nodeId)}</div>
                <div class="workflow-node-meta">${extra}: ${escapeHtml(typeLabel)}</div>
                <div class="workflow-node-meta">inputs: ${Object.keys(node.inputs || {}).length} · params: ${Object.keys(node.params || {}).length}</div>
              </button>
            `;
          }).join('');
          return `
            <div class="workflow-flow-group">
              <div class="workflow-flow-group-head">
                <span class="workflow-flow-group-title">${escapeHtml(group.flowLabel)}</span>
                <div class="workflow-flow-group-actions">
                  <span class="workflow-flow-group-count">${(group.nodes || []).length} 节点</span>
                  <button class="workflow-flow-add-btn" data-flow-add-node="${escapeHtml(group.flowKey)}" title="在此流程添加节点" aria-label="在此流程添加节点" ${workflowWorkspaceData.editMode ? '' : 'disabled'}>
                    <span class="font-icon" aria-hidden="true">＋</span>
                  </button>
                </div>
              </div>
              <div class="workflow-node-grid">${groupNodes || '<div class="placeholder">该流程没有节点。</div>'}</div>
            </div>
          `;
        }).join('')}
        <div class="workflow-canvas-footnote k">总节点数: ${allNodes.length} · 当前仅展示节点，不绘制连线。点击画布空白处可切换回 workflow 属性。</div>
      `;

      for (const btn of qsa('[data-workflow-node-key]')) {
        btn.addEventListener('click', () => {
          const nodeKey = btn.getAttribute('data-workflow-node-key') || '';
          selectWorkflowNode(nodeKey);
        });
      }

      for (const btn of qsa('[data-flow-add-node]')) {
        btn.addEventListener('click', (event) => {
          event.stopPropagation();
          const flowKey = btn.getAttribute('data-flow-add-node') || 'main';
          addWorkflowNode(flowKey).catch(err => alert(err.message || '添加节点失败'));
        });
      }

      canvas.addEventListener('click', (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;
        if (target.closest('.workflow-node-card')) return;
        if (workflowWorkspaceData.selectedNodeKey) {
          workflowWorkspaceData.selectedNodeKey = '';
          renderWorkflowWorkspace();
        }
      });
    }

    function renderWorkflowProps() {
      const prop = qs('#workflowProp');
      if (!prop) return;

      const flow = getWorkflowDraftFlow();
      if (!flow) {
        prop.innerHTML = '<div class="placeholder">暂无属性内容。</div>';
        return;
      }

      const nodes = flattenFlowNodes(flow);
      const selectedNodeWithMeta = nodes.find((item) => item.key === workflowWorkspaceData.selectedNodeKey) || null;
      const selectedContext = getSelectedNodeContext(flow, workflowWorkspaceData.selectedNodeKey);
      const selectedNode = selectedContext?.node || selectedNodeWithMeta?.node || null;
      const selectedGroup = selectedContext?.group || selectedNodeWithMeta?.group || null;
      const selectedFlow = selectedContext?.flow || null;
      if (!selectedNode) {
        const workflowMeta = getWorkflowDisplayItem(workflowWorkspaceData.selectedWorkflow);
        const subflowCount = (flow.sub_flows || []).length;
        prop.innerHTML = `
          <div class="workflow-prop-head">
            <div class="workflow-prop-title">Flow 属性</div>
            <div class="k">${workflowWorkspaceData.editMode ? '编辑模式' : '当前未选中节点。'}</div>
          </div>
          <div class="workflow-prop-block">
            <table class="workflow-prop-table">
              <tbody>
                <tr><th>workflow</th><td class="mono">${escapeHtml(workflowMeta.workflow || '-')}</td></tr>
                <tr><th>${requiredLabel('display_name', true)}</th><td>${renderEditableCell(flow.name || workflowMeta.name || '', 'flow.display_name')}</td></tr>
                <tr><th>${requiredLabel('flow_id', true)}</th><td class="mono">${escapeHtml(flow.flow_id || '-')}</td></tr>
                <tr><th>description</th><td>${renderEditableCell(flow.description || '', 'flow.description')}</td></tr>
                <tr><th>${requiredLabel('start_node_id', true)}</th><td>${renderEditableCell(flow.start_node_id || '', 'flow.start_node_id')}</td></tr>
                <tr><th>log</th><td>${renderEditableCell(flow.log || 'short', 'flow.log', 'select', ['none', 'short', 'full'])}</td></tr>
                <tr><th>total_nodes</th><td>${nodes.length}</td></tr>
                <tr><th>sub_flows</th><td>${subflowCount}</td></tr>
                <tr><th>path</th><td class="mono">${escapeHtml(workflowWorkspaceData.flowPath || '-')}</td></tr>
              </tbody>
            </table>
          </div>
        `;
        bindWorkflowInlineEditors();
        return;
      }

      const actionName = selectedNode.action || '';
      const controlName = selectedNode.control || '';
      const actionOptions = Array.from(new Set([...listCatalogTypes('action'), actionName].filter(Boolean))).sort((a, b) => a.localeCompare(b));
      const controlOptions = Array.from(new Set([...listCatalogTypes('control'), controlName].filter(Boolean))).sort((a, b) => a.localeCompare(b));
      const actionSection = actionName
        ? `
          <div class="workflow-prop-block workflow-component workflow-component--action">
            <div class="workflow-component-head">
              <div class="workflow-component-title">Action 组件</div>
              <span class="workflow-component-kind">Action</span>
            </div>
            <table class="workflow-prop-table">
              <tbody>
                <tr><th>${requiredLabel('type', true)}</th><td>${renderEditableCell(actionName, 'node.action', 'select', actionOptions)}
                </td></tr>
              </tbody>
            </table>
            <div class="contract-section-title">inputs</div>
            <table class="workflow-prop-table"><tbody>${renderKeyValueRows(selectedNode.inputs || {}, null, {
              declarationInputs: findActionDeclaration(actionName)?.inputs || [],
              editable: workflowWorkspaceData.editMode,
              kind: 'action',
              flow: selectedFlow,
              node: selectedNode,
            })}</tbody></table>
            <div class="contract-section-title">outputs</div>
            ${workflowWorkspaceData.editMode
              ? '<div class="workflow-edit-actions"><button class="ghost icon-only" type="button" id="workflowAddOutputBtn" title="添加输出项" aria-label="添加输出项"><span class="font-icon" aria-hidden="true">＋</span></button></div>'
              : ''}
            ${renderOutputsRows(selectedNode)}
          </div>
        `
        : `
          <div class="workflow-prop-block workflow-component workflow-component--empty">
            <div class="workflow-component-head">
              <div class="workflow-component-title">Action 组件</div>
              <span class="workflow-component-kind">Action</span>
            </div>
            ${workflowWorkspaceData.editMode
              ? `<table class="workflow-prop-table"><tbody><tr><th>${requiredLabel('type', true)}</th><td>${renderEditableCell(actionName, 'node.action', 'select', ['', ...actionOptions])}</td></tr></tbody></table>`
              : '<div class="placeholder">该节点未挂载 Action 组件。</div>'}
          </div>
        `;

      const controlSection = controlName
        ? `
          <div class="workflow-prop-block workflow-component workflow-component--control">
            <div class="workflow-component-head">
              <div class="workflow-component-title">Control 组件</div>
              <span class="workflow-component-kind">Control</span>
            </div>
            <table class="workflow-prop-table">
              <tbody>
                <tr><th>${requiredLabel('type', true)}</th><td>${renderEditableCell(controlName, 'node.control', 'select', controlOptions)}
                </td></tr>
              </tbody>
            </table>
            <div class="contract-section-title">params</div>
            <table class="workflow-prop-table"><tbody>${renderKeyValueRows(selectedNode.params || {}, resolveNodeRefParamKeys(controlName), {
              declarationInputs: findControlDeclaration(controlName)?.inputs || [],
              editable: workflowWorkspaceData.editMode,
              kind: 'control',
              flow: selectedFlow,
              node: selectedNode,
            })}</tbody></table>
          </div>
        `
        : `
          <div class="workflow-prop-block workflow-component workflow-component--empty">
            <div class="workflow-component-head">
              <div class="workflow-component-title">Control 组件</div>
              <span class="workflow-component-kind">Control</span>
            </div>
            ${workflowWorkspaceData.editMode
              ? `<table class="workflow-prop-table"><tbody><tr><th>${requiredLabel('type', true)}</th><td>${renderEditableCell(controlName, 'node.control', 'select', ['', ...controlOptions])}</td></tr></tbody></table>`
              : '<div class="placeholder">该节点未挂载 Control 组件。</div>'}
          </div>
        `;

      prop.innerHTML = `
        <div class="workflow-prop-head">
          <div class="workflow-prop-title">节点属性</div>
          <div class="k">${workflowWorkspaceData.editMode ? '编辑模式' : escapeHtml(selectedNode.name || selectedNode.node_id || '-')}</div>
        </div>
        <div class="workflow-prop-block">
          <table class="workflow-prop-table">
            <tbody>
              <tr><th>${requiredLabel('node_id', true)}</th><td>${renderEditableCell(selectedNode.node_id || '', 'node.node_id')}</td></tr>
              <tr><th>${requiredLabel('name', true)}</th><td>${renderEditableCell(selectedNode.name || '', 'node.name')}</td></tr>
              <tr><th>description</th><td>${renderEditableCell(selectedNode.description || '', 'node.description')}</td></tr>
              <tr><th>log</th><td>${renderEditableCell(selectedNode.log || 'short', 'node.log')}</td></tr>
              <tr><th>flow_group</th><td class="mono">${escapeHtml(selectedGroup?.flowLabel || '-')}</td></tr>
              <tr><th>flow_id</th><td class="mono">${escapeHtml(selectedGroup?.flowId || '-')}</td></tr>
            </tbody>
          </table>
          ${workflowWorkspaceData.editMode ? '<div class="workflow-edit-actions"><button class="ghost" id="workflowRestoreNodeBtn" title="恢复当前节点" aria-label="恢复当前节点"><span class="font-icon" aria-hidden="true">↺</span></button><button class="danger" id="workflowDeleteNodeBtn" title="删除当前节点" aria-label="删除当前节点"><span class="font-icon" aria-hidden="true">🗑</span></button></div>' : ''}
        </div>
        ${actionSection}
        ${controlSection}
      `;

      const restoreNodeBtn = qs('#workflowRestoreNodeBtn');
      if (restoreNodeBtn) {
        restoreNodeBtn.addEventListener('click', () => {
          restoreSelectedNodeDraft();
        });
      }

      const deleteNodeBtn = qs('#workflowDeleteNodeBtn');
      if (deleteNodeBtn) {
        deleteNodeBtn.addEventListener('click', () => {
          deleteSelectedNode().catch(err => alert(err.message || '删除节点失败'));
        });
      }

      bindWorkflowInlineEditors();
      bindContractFieldEditors();
      bindOutputEditors();
    }

    function renderWorkflowWorkspace() {
      updateWorkflowLayoutState();
      updateWorkflowToolbarState();
      renderWorkflowNav();
      renderWorkflowCanvas();
      renderWorkflowProps();
    }

    async function loadWorkflowDetail(name) {
      const data = await request(`/panel/api/workflows/${encodeURIComponent(name)}`);
      workflowWorkspaceData.selectedWorkflow = name;
      workflowWorkspaceData.flow = data.flow || null;
      workflowWorkspaceData.editFlow = null;
      workflowWorkspaceData.editMode = false;
      workflowWorkspaceData.flowPath = data.path || '';
      const nodes = flattenFlowNodes(workflowWorkspaceData.flow);
      const hasSelected = nodes.some((item) => item.key === workflowWorkspaceData.selectedNodeKey);
      workflowWorkspaceData.selectedNodeKey = hasSelected ? workflowWorkspaceData.selectedNodeKey : '';
    }

    async function ensureWorkflowCatalogReady() {
      if (Array.isArray(pluginCatalogData.items) && pluginCatalogData.items.length > 0) {
        return;
      }
      try {
        const data = await request('/panel/api/plugins');
        pluginCatalogData = data;
      } catch {
        // 插件目录失败时允许 workflow 基础查看，编辑能力降级为非契约模式。
      }
    }

    async function refreshWorkflowWorkspace() {
      await ensureWorkflowCatalogReady();
      const data = await request('/panel/api/workflows');
      const items = data.items || [];
      const workflowItems = data.workflows || items.map((item) => ({ workflow: item, name: item }));
      workflowWorkspaceData.items = items;
      workflowWorkspaceData.workflowItems = workflowItems;

      if (!items.length) {
        workflowWorkspaceData.selectedWorkflow = '';
        workflowWorkspaceData.flow = null;
        workflowWorkspaceData.editFlow = null;
        workflowWorkspaceData.editMode = false;
        workflowWorkspaceData.flowPath = '';
        workflowWorkspaceData.selectedNodeKey = '';
        renderWorkflowWorkspace();
        return;
      }

      let target = workflowWorkspaceData.selectedWorkflow;
      if (!target || !items.includes(target)) {
        target = items[0];
      }
      await loadWorkflowDetail(target);
      renderWorkflowWorkspace();
    }

    async function createTaskFromCurrentWorkflow() {
      const workflow = workflowWorkspaceData.selectedWorkflow;
      if (!workflow) {
        alert('请先选择 workflow');
        return;
      }
      const data = await request(`/panel/api/workflows/${encodeURIComponent(workflow)}/create-task`, 'POST');
      const taskId = data?.task?.task_id || '-';
      showCopyToast(`task 已创建: ${taskId}`);
    }

    function findLinkedSession(task) {
      const taskId = task?.task_id || '';
      const sessionId = task?.session_id || taskId;
      return taskWorkspaceData.sessions.find(s => s.session_id === sessionId || s.task_id === taskId) || null;
    }

    function workflowDisplayName(task, linkedSession = null) {
      const session = linkedSession || findLinkedSession(task);
      return session?.workflow_name || task?.workflow_name || '-';
    }

    function setPanelCollapsed(collapsed) {
      document.body.classList.toggle('panel-collapsed', collapsed);
      const icon = qs('#panelToggleIcon');
      if (icon) icon.textContent = collapsed ? '›' : '‹';
      localStorage.setItem(PANEL_COLLAPSE_KEY, collapsed ? '1' : '0');
    }

    async function refreshSystemPanel() {
      const data = await request('/panel/api/overview');
      qs('#sysServiceStatus').innerHTML = pill(data.service?.status || 'unknown');
      qs('#sysQueueStatus').textContent = `${data.task_queue?.queued ?? 0} queued / ${data.task_queue?.running ?? 0} running`;
      qs('#sysSessionCount').textContent = String(data.session_count ?? 0);
    }

    function renderTaskOpsNav() {
      const nav = qs('#opsNav');
      const tasks = taskWorkspaceData.tasks || [];
      const selectedRoot = taskWorkspaceSelected.type === 'root';
      nav.innerHTML = `
        <div class="ops-nav-title">导航</div>
        <button data-ops-root="1" class="${selectedRoot ? 'active' : ''}">总览</button>
        <div class="ops-nav-title">任务 (${tasks.length})</div>
        ${tasks.map(item => `
          <button data-ops-task="${item.task_id}" class="${taskWorkspaceSelected.taskId === item.task_id ? 'active' : ''}">
            <div class="mono">${item.task_id}</div>
            <div>${pill(item.status)} ${workflowDisplayName(item)}</div>
          </button>
        `).join('') || '<div class="placeholder" style="padding:10px;">暂无任务</div>'}
      `;

      for (const btn of qsa('[data-ops-root]')) {
        btn.addEventListener('click', () => {
          taskWorkspaceSelected = { type: 'root', taskId: '' };
          renderTaskWorkspace();
        });
      }
      for (const btn of qsa('[data-ops-task]')) {
        btn.addEventListener('click', () => {
          taskWorkspaceSelected = { type: 'task', taskId: btn.getAttribute('data-ops-task') || '' };
          renderTaskWorkspace();
        });
      }
    }

    async function sessionAction(sessionId, action) {
      await request(`/panel/api/sessions/${encodeURIComponent(sessionId)}/${action}`, 'POST');
      await refreshTasksWorkspace();
      showCopyToast(`会话 ${action} 已提交`);
    }

    async function openTaskLogs(taskId) {
      const data = await request(`/panel/api/tasks/${encodeURIComponent(taskId)}/logs?lines=160`);
      const box = qs('#taskLogBox');
      if (!box) return;
      box.textContent = data.content || '(暂无日志)';
    }

    function renderTaskWorkspace() {
      renderTaskOpsNav();
      const detail = qs('#opsDetail');
      const tasks = taskWorkspaceData.tasks || [];
      const sessions = taskWorkspaceData.sessions || [];

      if (taskWorkspaceSelected.type === 'root') {
        const runningTasks = tasks.filter(t => ['running', 'guard_waiting', 'paused', 'queued'].includes((t.status || '').toLowerCase())).length;
        const runningSessions = sessions.filter(s => ['running', 'guard_waiting', 'paused', 'created'].includes((s.status || '').toLowerCase())).length;
        detail.innerHTML = `
          <h3 style="margin:0;">任务与会话总览</h3>
          <div class="mini-grid">
            <div class="mini-card"><div class="mini-k">任务总数</div><div class="mini-v">${tasks.length}</div></div>
            <div class="mini-card"><div class="mini-k">进行中任务</div><div class="mini-v">${runningTasks}</div></div>
            <div class="mini-card"><div class="mini-k">活跃会话</div><div class="mini-v">${runningSessions}</div></div>
          </div>
          <table>
            <thead><tr><th>task_id</th><th>status</th><th>workflow</th><th>关联会话</th><th>操作</th></tr></thead>
            <tbody>
              ${tasks.map(item => {
                const linked = findLinkedSession(item);
                return `<tr>
                  <td class="mono">${item.task_id}</td>
                  <td>${pill(item.status)}</td>
                  <td>${workflowDisplayName(item, linked)}</td>
                  <td>${linked ? `${pill(linked.status)} <span class="mono">${linked.session_id}</span>` : '-'}</td>
                  <td><button class="ghost" data-open-task="${item.task_id}">查看</button></td>
                </tr>`;
              }).join('') || '<tr><td colspan="5">暂无任务</td></tr>'}
            </tbody>
          </table>
        `;
        for (const btn of qsa('[data-open-task]')) {
          btn.addEventListener('click', () => {
            taskWorkspaceSelected = { type: 'task', taskId: btn.getAttribute('data-open-task') || '' };
            renderTaskWorkspace();
          });
        }
        return;
      }

      const task = tasks.find(t => t.task_id === taskWorkspaceSelected.taskId);
      if (!task) {
        taskWorkspaceSelected = { type: 'root', taskId: '' };
        renderTaskWorkspace();
        return;
      }
      const linkedSession = findLinkedSession(task);
      detail.innerHTML = `
        <h3 style="margin:0;">任务详情</h3>
        <div class="mini-grid">
          <div class="mini-card"><div class="mini-k">task_id</div><div class="mini-v mono">${task.task_id}</div></div>
          <div class="mini-card"><div class="mini-k">状态</div><div class="mini-v">${pill(task.status)}</div></div>
          <div class="mini-card"><div class="mini-k">workflow</div><div class="mini-v">${workflowDisplayName(task, linkedSession)}</div></div>
        </div>
        <div class="mini-card">
          <div class="mini-k">workflow_path</div>
          <div class="mini-v mono">${task.workflow_path || '-'}</div>
        </div>
        <h3 style="margin:6px 0 0;">关联会话</h3>
        ${linkedSession ? `
          <div class="mini-grid">
            <div class="mini-card"><div class="mini-k">session_id</div><div class="mini-v mono">${linkedSession.session_id}</div></div>
            <div class="mini-card"><div class="mini-k">状态</div><div class="mini-v">${pill(linkedSession.status)}</div></div>
            <div class="mini-card"><div class="mini-k">当前节点</div><div class="mini-v mono">${linkedSession.current_node_id || '-'}</div></div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button class="ghost" data-sess-act="pause" data-sess-id="${linkedSession.session_id}">暂停</button>
            <button class="ghost" data-sess-act="resume" data-sess-id="${linkedSession.session_id}">继续</button>
            <button class="ghost" data-sess-act="interrupt" data-sess-id="${linkedSession.session_id}">中断到下节点前</button>
            <button class="danger" data-sess-act="abort" data-sess-id="${linkedSession.session_id}">终止</button>
          </div>
        ` : '<div class="placeholder">该任务暂无关联会话。</div>'}
        <h3 style="margin:6px 0 0;">任务日志</h3>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button class="ghost" data-task-log="${task.task_id}">刷新日志</button>
        </div>
        <div id="taskLogBox" class="log-box">(点击“刷新日志”加载)</div>
      `;

      for (const btn of qsa('[data-sess-act]')) {
        btn.addEventListener('click', async () => {
          const action = btn.getAttribute('data-sess-act') || '';
          const sessionId = btn.getAttribute('data-sess-id') || '';
          if (!action || !sessionId) return;
          try {
            await sessionAction(sessionId, action);
          } catch (err) {
            alert(err.message || '会话操作失败');
          }
        });
      }
      for (const btn of qsa('[data-task-log]')) {
        btn.addEventListener('click', async () => {
          const taskId = btn.getAttribute('data-task-log') || '';
          if (!taskId) return;
          try {
            await openTaskLogs(taskId);
          } catch (err) {
            alert(err.message || '读取日志失败');
          }
        });
      }
    }

    async function refreshTasksWorkspace() {
      const [taskData, sessionData] = await Promise.all([
        request('/panel/api/tasks?limit=40'),
        request('/panel/api/sessions?limit=40'),
      ]);
      taskWorkspaceData = {
        tasks: taskData.items || [],
        sessions: sessionData.items || [],
      };
      if (taskWorkspaceSelected.type === 'task') {
        const exists = taskWorkspaceData.tasks.some(t => t.task_id === taskWorkspaceSelected.taskId);
        if (!exists) taskWorkspaceSelected = { type: 'root', taskId: '' };
      }
      renderTaskWorkspace();
    }

    function groupByPrefix(items) {
      const groups = {};
      for (const item of items) {
        const parts = (item.name || '').split('.');
        const group = parts.length > 1 ? parts[0] : '__ungrouped__';
        if (!groups[group]) groups[group] = [];
        groups[group].push(item);
      }
      return groups;
    }

    function renderEnvGroups(items) {
      const container = qs('#envGroups');
      if (!items || items.length === 0) {
        container.innerHTML = '<div class="placeholder">暂无 Env 变量</div>';
        return;
      }

      const grouped = groupByPrefix(items);
      container.innerHTML = Object.entries(grouped).map(([group, gItems]) => {
        const safeId = group.replace(/[^a-zA-Z0-9_]/g, '_');
        const displayGroup = group === '__ungrouped__' ? '（未分组）' : group;
        const prefix = group === '__ungrouped__' ? '' : group + '.';
        const rows = gItems.map(item => {
          const key = prefix ? item.name.slice(prefix.length) : item.name;
          const valueText = envRevealAll && revealedEnvValues.has(item.name)
            ? valueToDisplayText(revealedEnvValues.get(item.name))
            : (item.masked_value || '-');
          return `<tr>
            <td style="font-family:monospace">
              <span class="env-cell-wrap">
                <span class="env-cell-text">${key}</span>
                <span class="inline-actions">
                  <button class="icon-btn" title="复制 key" data-copy-key="${item.name}">${icon('copy')}</button>
                </span>
              </span>
            </td>
            <td style="font-family:monospace;color:var(--muted)">
              <span class="env-cell-wrap">
                <span class="env-cell-text" data-env-value="${item.name}">${valueText}</span>
                <span class="inline-actions">
                  <button class="icon-btn" title="复制 value" data-copy-value="${item.name}">${icon('copy')}</button>
                </span>
              </span>
            </td>
            <td><button class="danger" style="font-size:.8rem;padding:4px 8px" data-env-del="${item.name}">删除</button></td>
          </tr>`;
        }).join('');
        return `
          <div class="env-group open">
            <div class="env-group-header">
              <span class="env-group-chevron">▶</span>
              <span class="env-group-name">${displayGroup}</span>
              <span class="env-group-count">${gItems.length} 项</span>
              <button class="icon-btn" title="复制组变量" data-copy-group="${group}">${icon('copy')}</button>
              <button class="ghost" style="font-size:.8rem;padding:4px 8px;margin-left:auto" data-grp-add="${safeId}">＋ 添加</button>
            </div>
            <div class="env-group-body">
              <div class="env-add-form" id="grpForm_${safeId}">
                <input id="grpName_${safeId}" placeholder="变量名" value="${prefix}" />
                <input id="grpValue_${safeId}" placeholder="变量值（字符串）" />
                <button class="primary" data-grp-save="${safeId}">保存</button>
                <button class="ghost" data-grp-cancel="${safeId}">取消</button>
              </div>
              <table class="env-table">
                <colgroup>
                  <col class="col-key" />
                  <col class="col-value" />
                  <col class="col-op" />
                </colgroup>
                <thead><tr><th>key</th><th style="white-space:nowrap">值 <button class="icon-btn" title="${envRevealAll ? '隐藏明文' : '显示明文'}" data-env-eye-all="1">${icon(envRevealAll ? 'eye-off' : 'eye')}</button></th><th>操作</th></tr></thead>
                <tbody>${rows}</tbody>
              </table>
            </div>
          </div>`;
      }).join('');

      for (const header of qsa('.env-group-header')) {
        header.addEventListener('click', (e) => {
          if (e.target.closest('button')) return;
          header.closest('.env-group').classList.toggle('open');
        });
      }

      for (const btn of qsa('[data-grp-add]')) {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const id = btn.getAttribute('data-grp-add');
          qs(`#grpForm_${id}`)?.classList.toggle('open');
        });
      }

      for (const btn of qsa('[data-grp-save]')) {
        btn.addEventListener('click', async () => {
          const id = btn.getAttribute('data-grp-save');
          const name = (qs(`#grpName_${id}`)?.value || '').trim();
          if (!name) { alert('请输入变量名'); return; }
          const value = parseValue(qs(`#grpValue_${id}`)?.value || '');
          await request('/panel/api/env', 'POST', { name, value });
          await refreshEnv();
        });
      }

      for (const btn of qsa('[data-grp-cancel]')) {
        btn.addEventListener('click', () => {
          const id = btn.getAttribute('data-grp-cancel');
          qs(`#grpForm_${id}`)?.classList.remove('open');
        });
      }

      for (const btn of qsa('[data-env-del]')) {
        btn.addEventListener('click', async () => {
          const name = btn.getAttribute('data-env-del');
          if (!name || !confirm(`确认删除 ${name}?`)) return;
          await request(`/panel/api/env/${encodeURIComponent(name)}`, 'DELETE');
          revealedEnvValues.delete(name);
          await refreshEnv();
        });
      }

      for (const btn of qsa('[data-env-eye-all]')) {
        btn.addEventListener('click', async () => {
          try {
            if (!envRevealAll) {
              await preloadRevealedValues(items);
            }
            envRevealAll = !envRevealAll;
            renderEnvGroups(items);
          } catch (err) {
            alert(err.message || '切换明文显示失败');
          }
        });
      }

      for (const btn of qsa('[data-copy-key]')) {
        btn.addEventListener('click', async () => {
          const key = btn.getAttribute('data-copy-key') || '';
          await copyText(key, 'key 已复制');
        });
      }

      for (const btn of qsa('[data-copy-value]')) {
        btn.addEventListener('click', async () => {
          const name = btn.getAttribute('data-copy-value') || '';
          if (!name) return;
          try {
            const value = await ensureRevealedValue(name);
            await copyText(valueToCopyText(value), 'value 已复制');
          } catch (err) {
            alert(err.message || '复制 value 失败');
          }
        });
      }

      for (const btn of qsa('[data-copy-group]')) {
        btn.addEventListener('click', async () => {
          const groupName = btn.getAttribute('data-copy-group');
          const inGroup = (grouped[groupName] || []).slice();
          if (inGroup.length === 0) return;
          try {
            const lines = [];
            for (const item of inGroup) {
              const value = await ensureRevealedValue(item.name);
              lines.push(`${item.name}=${valueToCopyText(value)}`);
            }
            await copyText(lines.join('\n'), `${groupName === '__ungrouped__' ? '未分组' : groupName} 已复制`);
          } catch (err) {
            alert(err.message || '复制分组失败');
          }
        });
      }
    }

    async function refreshEnv() {
      const data = await request('/panel/api/env');
      const items = data.items || [];
      if (envRevealAll) {
        await preloadRevealedValues(items);
      }
      renderEnvGroups(items);
    }

    async function refreshOverview() {
      const data = await request('/panel/api/overview');
      renderOverview(data);
    }

    async function refreshCurrentPage() {
      const active = document.querySelector('.section.active')?.id || 'overview';
      if (active === 'overview') {
        await refreshOverview();
      } else if (active === 'tasks') {
        await refreshTasksWorkspace();
      } else if (active === 'env') {
        await refreshEnv();
      } else if (active === 'plugins') {
        await refreshPluginsPanel();
      } else if (active === 'workflow') {
        await refreshWorkflowWorkspace();
      } else if (active === 'system') {
        await refreshSystemPanel();
      }
    }

    qs('#topRefreshBtn').addEventListener('click', () => {
      refreshCurrentPage().catch(err => alert(err.message));
    });

    qs('#autoRefreshBtn').addEventListener('click', () => {
      setAutoRefresh(!autoRefreshEnabled);
    });

    qs('#panelToggle').addEventListener('click', () => {
      const collapsed = !document.body.classList.contains('panel-collapsed');
      setPanelCollapsed(collapsed);
    });

    qs('#logoutBtn').addEventListener('click', async () => {
      await request('/panel/api/logout', 'POST');
      loginMask.style.display = 'grid';
    });

    qs('#showLoginBtn').addEventListener('click', () => {
      loginMask.style.display = 'grid';
    });

    qs('#sysRefreshBtn').addEventListener('click', () => {
      refreshSystemPanel().catch(err => alert(err.message));
    });

    qs('#envRefreshBtn').addEventListener('click', () => {
      refreshEnv().catch(err => alert(err.message));
    });

    qs('#envNewBtn').addEventListener('click', () => {
      qs('#envGlobalForm').classList.toggle('open');
    });

    qs('#envCancelBtn').addEventListener('click', () => {
      qs('#envGlobalForm').classList.remove('open');
      qs('#envName').value = '';
      qs('#envValue').value = '';
    });

    qs('#envSaveBtn').addEventListener('click', async () => {
      const name = (qs('#envName').value || '').trim();
      if (!name) {
        alert('请输入变量名');
        return;
      }
      const value = parseValue(qs('#envValue').value || '');
      await request('/panel/api/env', 'POST', { name, value });
      qs('#envName').value = '';
      qs('#envValue').value = '';
      qs('#envGlobalForm').classList.remove('open');
      await refreshEnv();
    });

    qs('#workflowRefreshBtn').addEventListener('click', () => {
      refreshWorkflowWorkspace().catch(err => alert(err.message));
    });

    qs('#workflowEditBtn').addEventListener('click', () => {
      startWorkflowEditMode();
    });

    qs('#workflowCancelEditBtn').addEventListener('click', () => {
      cancelWorkflowEditMode();
    });

    qs('#workflowSaveBtn').addEventListener('click', () => {
      saveWorkflowEditMode().catch(err => alert(err.message || '保存 workflow 失败'));
    });

    qs('#workflowDeleteBtn').addEventListener('click', () => {
      deleteCurrentWorkflow().catch(err => alert(err.message || '删除 workflow 失败'));
    });

    qs('#workflowCreateTaskBtn').addEventListener('click', () => {
      createTaskFromCurrentWorkflow().catch(err => alert(err.message));
    });

    qs('#workflowPropToggleBtn').addEventListener('click', () => {
      workflowWorkspaceData.propCollapsed = !workflowWorkspaceData.propCollapsed;
      localStorage.setItem(WORKFLOW_PROP_COLLAPSE_KEY, workflowWorkspaceData.propCollapsed ? '1' : '0');
      updateWorkflowLayoutState();
    });

    qs('#loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      loginHint.textContent = '';
      try {
        await request('/panel/api/login', 'POST', {
          username: qs('#username').value,
          password: qs('#password').value,
        });
        loginMask.style.display = 'none';
        await ensureLogin();
        await refreshOverview();
      } catch (err) {
        loginHint.textContent = err.message || '登录失败';
      }
    });

    for (const btn of qsa('[data-tab]')) {
      btn.addEventListener('click', async () => {
        const target = btn.getAttribute('data-tab');
        setActiveTab(target);
        if (target === 'overview') {
          await refreshOverview().catch(err => alert(err.message));
        } else if (target === 'tasks') {
          await refreshTasksWorkspace().catch(err => alert(err.message));
        } else if (target === 'env') {
          await refreshEnv().catch(err => alert(err.message));
        } else if (target === 'plugins') {
          await refreshPluginsPanel().catch(err => alert(err.message));
        } else if (target === 'workflow') {
          await refreshWorkflowWorkspace().catch(err => alert(err.message));
        } else if (target === 'system') {
          await refreshSystemPanel().catch(err => alert(err.message));
        }
      });
    }

    (async () => {
      setPanelCollapsed(localStorage.getItem(PANEL_COLLAPSE_KEY) === '1');
      setAutoRefresh(localStorage.getItem(AUTO_REFRESH_KEY) === '1');
      workflowWorkspaceData.propCollapsed = localStorage.getItem(WORKFLOW_PROP_COLLAPSE_KEY) === '1';
      updateWorkflowLayoutState();
      renderTopIcons();
      const loggedIn = await ensureLogin();
      if (loggedIn) {
        setActiveTab('overview');
        await refreshOverview().catch(err => alert(err.message));
      }
    })();
