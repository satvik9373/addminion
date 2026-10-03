/* LeadGen Dashboard — small fetch-based client. No secrets are rendered. */

async function api(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Accept': 'application/json' } };
  if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) data._status = res.status;
  return data;
}

function el(id) { return document.getElementById(id); }
function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

/* ---------------- health pill (all pages) ---------------- */
async function refreshHealth() {
  const pill = el('health-pill');
  if (!pill) return;
  try {
    const h = await api('/api/health');
    pill.className = 'health-pill ' + (h.healthy ? 'ok' : 'bad');
    pill.textContent = h.healthy ? 'healthy' : `${h.issue_count} issue(s)`;
  } catch (e) { pill.textContent = 'offline'; }
}

/* ---------------- overview ---------------- */
async function loadOverview() {
  try {
    const o = await api('/api/overview');
    el('s-total').textContent = o.total_leads;
    el('s-high').textContent = o.categories['High Score'];
    el('s-medium').textContent = o.categories['Medium Score'];
    el('s-low').textContent = o.categories['Low Score'];
    el('s-disq').textContent = o.categories['Disqualified'];
    el('s-qualified').textContent = o.qualified;
    el('s-contactable').textContent = o.total_contactable;
    el('s-phone').textContent = o.leads_with_phone;
    el('s-email').textContent = o.leads_with_email;
    el('s-instagram').textContent = o.leads_with_instagram;
    el('s-no-contact').textContent = o.leads_with_no_contact;
    el('s-contacted').textContent = o.contacted;
    el('s-replies').textContent = o.replies;

    const lg = o.leadgen, og = o.outreach;
    const lgSt = el('lg-status'), ogSt = el('og-status');
    lgSt.textContent = lg.running ? '● Running now' : (lg.last_run ? `Last run: ${lg.last_run.status}` : 'No runs yet');
    lgSt.className = 'run-status status-label ' + (lg.running ? 'running' : '');
    ogSt.textContent = og.running ? '● Running now' : (og.last_run ? `Last run: ${og.last_run.status}` : 'No runs yet');
    ogSt.className = 'run-status status-label ' + (og.running ? 'running' : '');

    el('lg-last').textContent = `Last run: ${fmtRun(lg.last_run)}`;
    el('lg-next').textContent = `Next scheduled: ${lg.next_scheduled_run || '—'}`;
    el('lg-sched').textContent = `Scheduler: ${lg.scheduler_enabled ? 'ON' : 'OFF'}`;

    el('og-mode').textContent = `Mode: ${og.mode === 'live' ? 'LIVE' : 'dry_run'}`;
    el('og-last').textContent = `Last run: ${fmtRun(og.last_run)}`;
    el('og-next').textContent = `Next scheduled: ${og.next_scheduled_run || '—'}`;
    el('og-sched').textContent = `Scheduler: ${og.scheduler_enabled ? 'ON' : 'OFF'}`;

    const s = og.stats || {};
    el('og-stats').innerHTML =
      `<div class="outreach-mini">ready ${s.leads_ready} · email ${s.email_pending}` +
      ` · IG ${s.ig_pending} · sent ${s.sent} · failed ${s.failed} · replies ${s.replied}</div>`;

    const hi = el('health-issues');
    hi.innerHTML = o.health_ok
      ? '<span style="color:var(--green)">All systems configured.</span>'
      : o.health_issues.map(i => `<div style="color:var(--amber)">⚠ ${esc(i)}</div>`).join('');
  } catch (e) {
    el('lg-status').textContent = 'Failed to load: ' + e;
  }
}

function fmtRun(r) {
  if (!r) return '—';
  return `#${r.id} ${r.run_type} · ${r.status} · ${esc(r.started_at) || ''}`;
}

/* ---------------- generic stage rendering ---------------- */
function renderStages(s, stageListId, statusLabelId) {
  const list = el(stageListId), lbl = el(statusLabelId);
  if (!list) return;
  el('progress-bar').style.width = (s.progress || 0) + '%';
  lbl.textContent = s.status;
  lbl.className = 'status-label ' + s.status;
  el('btn-run').disabled = (s.status === 'running');
  el('btn-stop').disabled = (s.status !== 'running');
  list.innerHTML = s.stages.map((name, i) => {
    let cls = 'stage';
    if (s.stage_errors && s.stage_errors[name]) cls += ' failed';
    else if (i < (s.stage_index ?? 0)) cls += ' done';
    else if (i === s.stage_index) cls += ' active';
    return `<div class="${cls}">${name}</div>`;
  }).join('');
}

/* ---------------- lead generation ---------------- */
async function loadLeadgen() {
  try {
    const s = await api('/api/leadgen/status');
    renderStages(s, 'stage-list', 'lg-status-label');
    el('lg-log').textContent = (s.log || []).join('\n') || 'Waiting for a run…';
    const h = await api('/api/leadgen/history');
    el('run-history').innerHTML = renderRuns(h, true);
    const sch = await api('/api/scheduler/leadgen/status');
    renderScheduler(sch);
  } catch (e) {
    el('lg-log').textContent = 'Failed to load: ' + e;
  }
}
async function runLeadgen() {
  const r = await api('/api/leadgen/run', 'POST');
  if (!r.ok && r.error) alert(r.error || 'Failed to start');
  loadLeadgen();
}
async function stopLeadgen() {
  await api('/api/leadgen/stop', 'POST');
  loadLeadgen();
}

/* ---------------- outreach ---------------- */
async function loadOutreach() {
  try {
    const s = await api('/api/outreach/status');
    renderStages(s, 'stage-list', 'og-status-label');

    const badge = el('mode-badge');
    badge.textContent = s.mode;
    badge.className = 'mode-badge ' + (s.mode === 'live' ? 'live' : '');

    const radios = document.querySelectorAll('input[name="mode"]');
    radios.forEach(r => { r.checked = (r.value === s.mode); });
    if (el('ch-phone')) el('ch-phone').checked = !!(s.channels && s.channels.phone);
    if (el('ch-email')) el('ch-email').checked = !!(s.channels && s.channels.email);
    if (el('ch-instagram')) el('ch-instagram').checked = !!(s.channels && s.channels.instagram_dm);

    const c = s.counts || {};
    el('og-counts').innerHTML =
      `<span>ready ${c.leads_ready ?? 0}</span>` +
      `<span>phone tasks ${c.phone_tasks ?? 0}</span>` +
      `<span>previewed ${c.previewed ?? 0}</span>` +
      `<span>sent ${c.sent ?? 0}</span>` +
      `<span>failed ${c.failed ?? 0}</span>` +
      `<span>skipped ${c.skipped ?? 0}</span>` +
      (s.current_channel ? `<span>channel: ${esc(s.current_channel)}</span>` : '');
    el('og-log').textContent = (s.log || []).join('\n') || 'Waiting for a run…';

    // Channel readiness breakdown + contactable totals
    const st = s.stats || {};
    const bd = el('channel-breakdown');
    if (bd) {
      const contactable = (st.contactable != null) ? st.contactable : (c.contactable ?? 0);
      const noContact = (st.no_contact != null) ? st.no_contact : (c.no_contact ?? 0);
      bd.innerHTML =
        `<div class="channel-cards">` +
          `<div class="channel-card"><b>PHONE</b><span>${st.phone_pending ?? c.phone_tasks ?? 0} ready</span></div>` +
          `<div class="channel-card"><b>EMAIL</b><span>${st.email_pending ?? 0} ready</span></div>` +
          `<div class="channel-card"><b>INSTAGRAM</b><span>${st.ig_pending ?? 0} ready</span></div>` +
        `</div>` +
        `<div class="contact-totals">` +
          `<span>${st.leads_ready ?? c.leads_ready ?? 0} qualified leads</span>` +
          `<span>${contactable} contactable</span>` +
          `<span style="color:${noContact ? 'var(--amber)' : 'var(--muted)'}">${noContact} no contact data</span>` +
        `</div>`;
    }

    const q = s.queue || [];
    el('queue-tbody').innerHTML = q.length
      ? q.map(i => `<tr><td>${esc(i.name) || '—'}</td><td>${esc(i.channel)}</td>` +
                   `<td>${esc(i.message_type)}</td><td>${esc(i.to) || ''}</td></tr>`).join('')
      : '<tr><td colspan="4">No queue built yet.</td></tr>';

    // Phone call tasks (manual)
    const pt = el('phone-tasks-tbody');
    if (pt) {
      const phoneItems = q.filter(i => i.channel === 'phone');
      pt.innerHTML = phoneItems.length
        ? phoneItems.map(i =>
            `<tr><td>${esc(i.name) || '—'}</td>` +
            `<td>${esc(i.to) || ''}</td>` +
            `<td>${esc(i.brokerage) || '—'}</td>` +
            `<td>${esc(i.phone_source) || '—'}</td>` +
            `<td>Ready</td>` +
            `<td class="phone-actions">` +
              `<button class="btn" onclick="markPhoneCalled('${esc(i.lead_id)}')">✓ Mark Called</button>` +
              `<button class="btn" onclick="skipPhoneTask('${esc(i.lead_id)}')">Skip</button>` +
              `<a class="btn" href="/leads" onclick="openDetail('${esc(i.lead_id)}');return false">Open Lead</a>` +
            `</td></tr>`).join('')
        : '<tr><td colspan="6">No pending phone tasks. Run the outreach pipeline to build them.</td></tr>';
    }

    const h = await api('/api/outreach/history');
    el('run-history').innerHTML = renderRuns(h, false);
    const sch = await api('/api/scheduler/outreach/status');
    renderScheduler(sch);
  } catch (e) {
    el('og-log').textContent = 'Failed to load: ' + e;
  }
}
async function runOutreach() {
  const s = await api('/api/outreach/status');
  if (s.mode === 'live') {
    if (!confirm('Live mode will actually send email / Instagram DMs to queued leads. Continue?')) return;
  }
  const r = await api('/api/outreach/run', 'POST');
  if (!r.ok && r.error) alert(r.error || 'Failed to start');
  loadOutreach();
}
async function stopOutreach() {
  await api('/api/outreach/stop', 'POST');
  loadOutreach();
}
async function setMode() {
  const sel = document.querySelector('input[name="mode"]:checked');
  if (!sel) return;
  const mode = sel.value;
  if (mode === 'live' && !confirm('Switching to LIVE mode means future runs actually send outreach. Continue?')) {
    const radios = document.querySelectorAll('input[name="mode"]');
    radios.forEach(r => { r.checked = (r.value === 'dry_run'); });
    return;
  }
  const r = await api('/api/outreach/mode', 'POST', { mode });
  if (!r.ok && r.error) alert(r.error);
  loadOutreach();
}
async function setChannels() {
  const r = await api('/api/outreach/channels', 'POST', {
    phone: !!el('ch-phone').checked,
    email: !!el('ch-email').checked,
    instagram_dm: !!el('ch-instagram').checked,
  });
  if (!r.ok && r.error) alert(r.error);
  loadOutreach();
}

/* ---------------- phone call tasks (manual) ---------------- */
async function markPhoneCalled(leadId) {
  if (!confirm('Mark this phone call as completed? This records a successful CALL for the lead (idempotent).')) return;
  const r = await api('/api/outreach/phone/complete', 'POST', { lead_id: leadId });
  if (!r.ok && r.error) alert(r.error);
  loadOutreach();
}
async function skipPhoneTask(leadId) {
  const r = await api('/api/outreach/phone/skip', 'POST', { lead_id: leadId });
  if (!r.ok && r.error) alert(r.error);
  loadOutreach();
}

/* ---------------- scheduler (per pipeline) ---------------- */
function renderScheduler(sch) {
  if (!el('sched-state')) return;
  el('sched-state').innerHTML = `
    <div>Status: <b style="color:${sch.enabled ? 'var(--green)' : 'var(--muted)'}">${sch.enabled ? 'ON' : 'OFF'}</b></div>
    <div>Frequency: every ${sch.frequency_hours} hour(s)</div>`;
  el('freq').value = sch.frequency_hours;
  el('btn-enable').disabled = sch.enabled;
  el('btn-disable').disabled = !sch.enabled;
  el('sched-next').textContent = `Next run: ${sch.next_run_at ? esc(sch.next_run_at) : '—'}`;
  el('sched-last').textContent = `Last run: ${sch.last_run_at ? esc(sch.last_run_at) + ' (' + esc(sch.last_status) + ')' : '—'}`;
}
async function setScheduler(pipeline, action) {
  const r = await api(`/api/scheduler/${pipeline}/${action}`, 'POST');
  if (!r.ok && r.error) alert(r.error);
  loadSchedulerFor(pipeline);
}
async function setFrequency(pipeline) {
  const h = parseFloat(el('freq').value);
  if (!h || h <= 0) { alert('Enter a positive number of hours'); return; }
  const r = await api(`/api/scheduler/${pipeline}/config`, 'POST', { frequency_hours: h });
  if (!r.ok && r.error) alert(r.error);
  loadSchedulerFor(pipeline);
}
async function loadSchedulerFor(pipeline) {
  try {
    const sch = await api(`/api/scheduler/${pipeline}/status`);
    renderScheduler(sch);
  } catch (e) { /* scheduler panel may be missing on this page */ }
}

/* ---------------- run history ---------------- */
function renderRuns(json, showNewLeads) {
  const runs = (json && json.runs) || [];
  const cols = showNewLeads ? 7 : 6;
  if (!runs.length) return `<tr><td colspan="${cols}">No runs recorded yet.</td></tr>`;
  return runs.map(r => `<tr>
    <td>${r.id}</td><td>${esc(r.run_type)}</td>
    <td>${esc(r.status)}</td>
    <td>${esc(r.started_at) || '—'}</td>
    <td>${esc(r.finished_at) || '—'}</td>
    ${showNewLeads ? `<td>${r.new_leads ?? ''}</td>` : ''}
    <td>${esc(r.error) || ''}</td>
  </tr>`).join('');
}

/* ---------------- leads ---------------- */
function debouncedLoad() { clearTimeout(window._leadT); window._leadT = setTimeout(loadLeads, 350); }

async function loadLeads() {
  const q = el('f-q').value.trim();
  const source = el('f-source').value;
  const category = el('f-category').value;
  const status = el('f-status').value;
  const contact = el('f-contact').value;
  const params = new URLSearchParams({ limit: '200' });
  if (q) params.set('q', q);
  if (source) params.set('source', source);
  if (category) params.set('category', category);
  if (status) params.set('status', status);
  if (contact) {
    if (contact === 'no_contact') params.set('no_contact', '1');
    else params.set(contact, '1');   // contactable / has_phone / has_email / has_instagram
  }

  const d = await api('/api/leads?' + params.toString());
  if (el('f-source').options.length <= 1 && d.sources) {
    (d.sources || []).forEach(s => {
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s; el('f-source').appendChild(opt);
    });
  }
  el('leads-count').textContent = `${d.count} lead(s)`;
  el('leads-tbody').innerHTML = (d.leads || []).map(l => `<tr>
    <td><a href="#" onclick="openDetail('${esc(l.id)}');return false">${esc(l.name) || '—'}</a></td>
    <td>${l.score ?? ''}</td>
    <td>${esc(l.category) || ''}</td>
    <td>${esc(l.source) || ''}</td>
    <td>${esc(l.brokerage) || ''}</td>
    <td>${esc(l.phone) || ''}</td>
    <td>${esc(l.email) || ''}</td>
    <td>${esc(l.instagram) || ''}</td>
    <td>${esc(l.outreach_status) || esc(l.email_status) || ''}</td>
    <td>${esc(l.instagram_dm_status) || ''}</td>
    <td>${esc(l.status) || ''}</td>
    <td><button class="btn" onclick="openDetail('${esc(l.id)}')">Details</button></td>
  </tr>`).join('');
}

async function openDetail(id) {
  // Lead IDs are full URLs with slashes/query chars — encode so the detail
  // route (<path:lead_id>) receives a safe path segment.
  const l = await api('/api/leads/' + encodeURIComponent(id));
  if (l.error) { alert(l.error); return; }
  el('lead-detail-body').textContent = JSON.stringify(l, null, 2);
  el('lead-detail-modal').classList.remove('hidden');
}
function closeDetail() { el('lead-detail-modal').classList.add('hidden'); }

/* ---------------- init ---------------- */
function init() {
  refreshHealth(); setInterval(refreshHealth, 15000);
  if (el('stat-cards')) { loadOverview(); setInterval(loadOverview, 8000); }
  if (el('lg-log')) { loadLeadgen(); setInterval(loadLeadgen, 2000); }
  if (el('og-log')) { loadOutreach(); setInterval(loadOutreach, 2500); }
  if (el('leads-tbody')) { loadLeads(); }
}
document.addEventListener('DOMContentLoaded', init);
