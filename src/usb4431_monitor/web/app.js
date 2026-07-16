const COLORS = ['#2563eb', '#047857', '#b45309', '#7e22ce'];
const CHART_TEXT = '#6b7280';
const CHART_GRID = '#e5e7eb';
const CHART_EMPTY = '#6b7280';
const state = {
  records: [],
  xMode: 'event',
  contextChannel: 0,
  lastCount: -1,
  locked: false,
  waveform: null,
  waveformRevision: -1,
  waveformDirty: true,
  waveformPolling: false,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const api = () => window.pywebview?.api;

function toast(message, error = false) {
  const node = $('#toast');
  node.textContent = message;
  node.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.className = 'toast', 3200);
}

function formatVoltage(value, signed = false) {
  if (value == null || !Number.isFinite(value)) return '—';
  const prefix = signed && value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(6)} V`;
}

function formatRate(rate) {
  if (!rate) return '—';
  return rate >= 1000 ? `${(rate / 1000).toFixed(rate % 1000 ? 2 : 1)} kS/s` : `${rate.toFixed(1)} S/s`;
}

class WaveformChart {
  constructor(canvas, channel) {
    this.canvas = canvas;
    this.channel = channel;
    this.hoverIndex = null;
    canvas.tabIndex = 0;
    canvas.setAttribute('role', 'img');
    this.resizeObserver = new ResizeObserver(() => { state.waveformDirty = true; });
    this.resizeObserver.observe(canvas);
    canvas.addEventListener('pointermove', event => this.onPointerMove(event));
    canvas.addEventListener('pointerleave', () => {
      this.hoverIndex = null;
      this.updateCursor();
      state.waveformDirty = true;
    });
    canvas.addEventListener('keydown', event => this.onKeyDown(event));
  }

  onKeyDown(event) {
    const values = this.values();
    if (!values.length || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    if (event.key === 'Home') this.hoverIndex = 0;
    else if (event.key === 'End') this.hoverIndex = values.length - 1;
    else {
      const current = this.hoverIndex == null ? 0 : this.hoverIndex;
      this.hoverIndex = Math.max(0, Math.min(values.length - 1, current + (event.key === 'ArrowRight' ? 1 : -1)));
    }
    this.updateCursor();
    state.waveformDirty = true;
  }

  values() {
    return state.waveform?.channels?.[this.channel] || [];
  }

  onPointerMove(event) {
    const values = this.values();
    if (!values.length) return;
    const rect = this.canvas.getBoundingClientRect();
    const plotLeft = 55;
    const plotRight = rect.width - 15;
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left - plotLeft) / Math.max(1, plotRight - plotLeft)));
    const waveform = state.waveform;
    const timeMs = waveform.window_start_ms + ratio * (waveform.window_end_ms - waveform.window_start_ms);
    const sampleIndex = Math.round((timeMs - waveform.first_sample_offset_ms) * waveform.sample_rate_Hz / 1000);
    this.hoverIndex = Math.max(0, Math.min(values.length - 1, sampleIndex));
    this.updateCursor();
    state.waveformDirty = true;
  }

  updateCursor() {
    const label = $(`.waveform-card[data-wave-channel="${this.channel}"] [data-wave-stat="cursor"]`);
    const values = this.values();
    if (this.hoverIndex == null || !values.length || !state.waveform) {
      label.textContent = values.length ? `共 ${values.length.toLocaleString()} 点` : '移动鼠标查看采样点';
      return;
    }
    const timeMs = state.waveform.first_sample_offset_ms + this.hoverIndex / state.waveform.sample_rate_Hz * 1000;
    label.textContent = `点 ${this.hoverIndex + 1} · ${timeMs.toFixed(4)} ms · ${Number(values[this.hoverIndex]).toFixed(7)} V`;
  }

  draw() {
    const rect = this.canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(rect.width * dpr);
    this.canvas.height = Math.round(rect.height * dpr);
    const ctx = this.canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    const width = rect.width, height = rect.height;
    const plot = { left: 55, top: 12, right: width - 15, bottom: height - 25 };
    const waveform = state.waveform;
    const values = this.values();
    let yMin = -1, yMax = 1;
    if (values.length) {
      yMin = Number(values[0]);
      yMax = yMin;
      for (let index = 1; index < values.length; index++) {
        const value = Number(values[index]);
        if (value < yMin) yMin = value;
        if (value > yMax) yMax = value;
      }
      const pad = yMin === yMax ? Math.max(Math.abs(yMin) * .002, .001) : (yMax - yMin) * .12;
      yMin -= pad; yMax += pad;
    }
    const xMin = waveform?.window_start_ms ?? 0;
    const xMax = waveform?.window_end_ms ?? 1;
    const xSpan = xMax - xMin || 1;
    const ySpan = yMax - yMin || 1;
    const px = timeMs => plot.left + (timeMs - xMin) / xSpan * (plot.right - plot.left);
    const py = value => plot.bottom - (value - yMin) / ySpan * (plot.bottom - plot.top);

    ctx.clearRect(0, 0, width, height);
    ctx.lineWidth = 1;
    ctx.font = '9px ui-monospace, Consolas, monospace';
    ctx.fillStyle = CHART_TEXT;
    ctx.strokeStyle = CHART_GRID;
    for (let index = 0; index <= 3; index++) {
      const y = plot.top + index * (plot.bottom - plot.top) / 3;
      ctx.beginPath(); ctx.moveTo(plot.left, y); ctx.lineTo(plot.right, y); ctx.stroke();
      ctx.fillText((yMax - index * ySpan / 3).toFixed(4), 7, y + 3);
    }
    for (let index = 0; index <= 4; index++) {
      const x = plot.left + index * (plot.right - plot.left) / 4;
      ctx.beginPath(); ctx.moveTo(x, plot.top); ctx.lineTo(x, plot.bottom); ctx.stroke();
      const label = `${(xMin + index * xSpan / 4).toFixed(2)} ms`;
      const textWidth = ctx.measureText(label).width;
      ctx.fillText(label, Math.max(plot.left, Math.min(plot.right - textWidth, x - textWidth / 2)), height - 7);
    }

    if (!values.length || !waveform) {
      ctx.fillStyle = CHART_EMPTY; ctx.font = '11px Segoe UI, sans-serif'; ctx.textAlign = 'center';
      ctx.fillText('等待触发窗口采样', (plot.left + plot.right) / 2, (plot.top + plot.bottom) / 2);
      ctx.textAlign = 'start';
      return;
    }

    ctx.beginPath();
    for (let index = 0; index < values.length; index++) {
      const timeMs = waveform.first_sample_offset_ms + index / waveform.sample_rate_Hz * 1000;
      const x = px(timeMs), y = py(Number(values[index]));
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = COLORS[this.channel]; ctx.lineWidth = 1.25; ctx.stroke();

    if (this.hoverIndex != null && this.hoverIndex < values.length) {
      const timeMs = waveform.first_sample_offset_ms + this.hoverIndex / waveform.sample_rate_Hz * 1000;
      const x = px(timeMs), y = py(Number(values[this.hoverIndex]));
      ctx.beginPath(); ctx.moveTo(x, plot.top); ctx.lineTo(x, plot.bottom);
      ctx.strokeStyle = 'rgba(75, 85, 99, .45)'; ctx.lineWidth = 1; ctx.stroke();
      ctx.beginPath(); ctx.arc(x, y, 3.2, 0, Math.PI * 2); ctx.fillStyle = COLORS[this.channel]; ctx.fill();
    }
  }
}

class DriftChart {
  constructor(canvas, channel) {
    this.canvas = canvas;
    this.channel = channel;
    this.zoom = null;
    this.drag = null;
    this.resizeObserver = new ResizeObserver(() => this.draw());
    this.resizeObserver.observe(canvas);
    canvas.addEventListener('wheel', event => this.onWheel(event), { passive: false });
    canvas.addEventListener('pointerdown', event => this.onPointerDown(event));
    canvas.addEventListener('pointermove', event => this.onPointerMove(event));
    canvas.addEventListener('pointerup', () => this.drag = null);
    canvas.addEventListener('pointerleave', () => this.drag = null);
    canvas.addEventListener('contextmenu', event => showContextMenu(event, channel));
  }

  xValue(record) {
    if (state.xMode === 'timestamp') return Date.parse(record.trigger_timestamp) / 1000;
    if (state.xMode === 'runtime') return record.run_time_s;
    return record.event_index;
  }

  domain() {
    if (!state.records.length) return [0, 1];
    return [this.xValue(state.records[0]), this.xValue(state.records.at(-1)) || 1];
  }

  reset() { this.zoom = null; this.draw(); }

  onWheel(event) {
    if (state.records.length < 2) return;
    event.preventDefault();
    const full = this.domain();
    const current = this.zoom || full;
    const rect = this.canvas.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left - 54) / Math.max(1, rect.width - 70)));
    const anchor = current[0] + ratio * (current[1] - current[0]);
    const factor = event.deltaY > 0 ? 1.28 : 0.78;
    let low = anchor - (anchor - current[0]) * factor;
    let high = anchor + (current[1] - anchor) * factor;
    const minSpan = Math.max((full[1] - full[0]) / 10000, 1e-9);
    if (high - low < minSpan) return;
    if (low < full[0]) { high += full[0] - low; low = full[0]; }
    if (high > full[1]) { low -= high - full[1]; high = full[1]; }
    this.zoom = [Math.max(full[0], low), Math.min(full[1], high)];
    this.draw();
  }

  onPointerDown(event) {
    if (!this.zoom) return;
    this.drag = { x: event.clientX, zoom: [...this.zoom] };
    this.canvas.setPointerCapture(event.pointerId);
  }

  onPointerMove(event) {
    if (!this.drag) return;
    const rect = this.canvas.getBoundingClientRect();
    const full = this.domain();
    const span = this.drag.zoom[1] - this.drag.zoom[0];
    const shift = -(event.clientX - this.drag.x) / Math.max(1, rect.width - 70) * span;
    let low = this.drag.zoom[0] + shift;
    let high = this.drag.zoom[1] + shift;
    if (low < full[0]) { high += full[0] - low; low = full[0]; }
    if (high > full[1]) { low -= high - full[1]; high = full[1]; }
    this.zoom = [low, high];
    this.draw();
  }

  draw() {
    const rect = this.canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(rect.width * dpr);
    this.canvas.height = Math.round(rect.height * dpr);
    const ctx = this.canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    const width = rect.width, height = rect.height;
    const plot = { left: 55, top: 17, right: width - 15, bottom: height - 30 };
    const domain = this.zoom || this.domain();
    const visible = state.records.filter(r => { const x = this.xValue(r); return x >= domain[0] && x <= domain[1]; });
    const values = visible.map(r => Number(r[`ai${this.channel}_mean_V`]));
    let yMin = values.length ? Math.min(...values) : -1;
    let yMax = values.length ? Math.max(...values) : 1;
    if (yMin === yMax) { const pad = Math.max(Math.abs(yMin) * .002, .001); yMin -= pad; yMax += pad; }
    else { const pad = (yMax - yMin) * .12; yMin -= pad; yMax += pad; }
    const xSpan = domain[1] - domain[0] || 1;
    const ySpan = yMax - yMin || 1;
    const px = x => plot.left + (x - domain[0]) / xSpan * (plot.right - plot.left);
    const py = y => plot.bottom - (y - yMin) / ySpan * (plot.bottom - plot.top);

    ctx.clearRect(0, 0, width, height);
    ctx.lineWidth = 1;
    ctx.font = '10px ui-monospace, Consolas, monospace';
    ctx.fillStyle = CHART_TEXT;
    ctx.strokeStyle = CHART_GRID;
    for (let i = 0; i <= 4; i++) {
      const y = plot.top + i * (plot.bottom - plot.top) / 4;
      ctx.beginPath(); ctx.moveTo(plot.left, y); ctx.lineTo(plot.right, y); ctx.stroke();
      const value = yMax - i * ySpan / 4;
      ctx.fillText(value.toFixed(4), 7, y + 3);
    }
    for (let i = 0; i <= 4; i++) {
      const x = plot.left + i * (plot.right - plot.left) / 4;
      ctx.beginPath(); ctx.moveTo(x, plot.top); ctx.lineTo(x, plot.bottom); ctx.stroke();
      const value = domain[0] + i * xSpan / 4;
      const label = formatAxisX(value, state.xMode);
      const tw = ctx.measureText(label).width;
      ctx.fillText(label, Math.max(plot.left, Math.min(plot.right - tw, x - tw / 2)), height - 9);
    }

    if (!visible.length) {
      ctx.fillStyle = CHART_EMPTY; ctx.font = '12px Segoe UI, sans-serif';
      ctx.textAlign = 'center'; ctx.fillText('等待触发结果', (plot.left + plot.right) / 2, (plot.top + plot.bottom) / 2); ctx.textAlign = 'start';
      return;
    }
    ctx.beginPath();
    visible.forEach((record, index) => {
      const x = px(this.xValue(record)), y = py(Number(record[`ai${this.channel}_mean_V`]));
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = COLORS[this.channel]; ctx.lineWidth = 1.5; ctx.stroke();
    const last = visible.at(-1);
    ctx.beginPath(); ctx.arc(px(this.xValue(last)), py(Number(last[`ai${this.channel}_mean_V`])), 3, 0, Math.PI * 2);
    ctx.fillStyle = COLORS[this.channel]; ctx.fill();
  }
}

function formatAxisX(value, mode) {
  if (mode === 'timestamp') return new Date(value * 1000).toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  if (mode === 'runtime') return value >= 60 ? `${(value / 60).toFixed(1)}m` : `${value.toFixed(1)}s`;
  return Math.round(value).toString();
}

const charts = [0, 1, 2, 3].map(channel => new DriftChart($(`#chart${channel}`), channel));
const waveformCharts = [0, 1, 2, 3].map(channel => new WaveformChart($(`#waveform${channel}`), channel));

function renderWaveformMeta() {
  const waveform = state.waveform;
  if (!waveform) {
    $('#waveformEvent').textContent = '等待触发';
    $('#waveformProgress').textContent = '0 / 0 点';
    $('#waveformState').textContent = '—';
    $('#waveformState').className = 'waveform-state';
  } else {
    $('#waveformEvent').textContent = `触发 #${waveform.event_index} · 样本 ${waveform.trigger_sample_index.toLocaleString()}`;
    $('#waveformProgress').textContent = `${waveform.collected_count.toLocaleString()} / ${waveform.expected_count.toLocaleString()} 点`;
    $('#waveformState').textContent = waveform.complete ? '窗口已完成' : '窗口采集中';
    $('#waveformState').className = `waveform-state ${waveform.complete ? 'complete' : 'collecting'}`;
  }
  waveformCharts.forEach(chart => chart.updateCursor());
}

function waveformAnimationFrame() {
  if (state.waveformDirty) {
    waveformCharts.forEach(chart => chart.draw());
    state.waveformDirty = false;
  }
  requestAnimationFrame(waveformAnimationFrame);
}

async function pollWaveform() {
  if (!state.waveformPolling || !api()) return;
  try {
    const update = await api().get_waveform_data(state.waveformRevision);
    if (update.changed) {
      state.waveformRevision = update.revision;
      state.waveform = update.waveform;
      state.waveformDirty = true;
      renderWaveformMeta();
    }
  } catch (error) {
    state.waveformPolling = false;
    toast(`原始波形同步失败：${error}`, true);
    return;
  }
  setTimeout(pollWaveform, 16);
}

function collectConfig() {
  return {
    mode: $('input[name="mode"]:checked').value,
    device: $('#device').value,
    trigger_channel: Number($('#triggerChannel').value),
    trigger_threshold_v: Number($('#threshold').value),
    trigger_hysteresis_v: Number($('#hysteresis').value),
    min_trigger_interval_ms: Number($('#minInterval').value),
    sample_rate_hz: Number($('#sampleRate').value),
    window_unit: $('#windowUnit').value,
    window_start: Number($('#windowStart').value),
    window_end: Number($('#windowEnd').value),
    simulation_trigger_period_ms: Number($('#simulationPeriod').value),
    simulation_realtime: $('#simulationRealtime').checked,
  };
}

function setLocked(locked) {
  state.locked = locked;
  $$('#configForm input, #configForm select, #configForm button').forEach(node => node.disabled = locked);
  $('#startButton').disabled = locked;
  $('#stopButton').disabled = !locked;
  $('#lockBadge').textContent = locked ? '参数已锁定' : '可编辑';
  $('#lockBadge').classList.toggle('locked', locked);
}

function renderState(info) {
  const labels = { idle: '待机', starting: '启动中', running: '采集中', draining: '完成窗口中', error: '采集异常' };
  $('#acquisitionStatus').textContent = labels[info.status] || info.status;
  $('#deviceStatus').textContent = info.device_status;
  $('#actualRate').textContent = formatRate(info.actual_sample_rate_hz);
  $('#windowRange').textContent = info.window_start_ms == null ? '—' : `${info.window_start_ms.toFixed(3)}–${info.window_end_ms.toFixed(3)} ms`;
  $('#sampleCount').textContent = info.sample_count == null ? '—' : info.sample_count.toLocaleString();
  $('#completedCount').textContent = info.completed_count.toLocaleString();
  $('#pendingCount').textContent = info.pending_count.toLocaleString();
  $('#runMessage').textContent = info.unfinished_windows ? `${info.message}；${info.unfinished_windows} 个窗口未完成。` : info.message;
  $('#statusDot').className = `status-dot ${info.status}`;
  setLocked(info.config_locked);
  $('#startButton').textContent = info.status === 'starting' ? '启动中…' : '开始采集';
  $('#stopButton').textContent = info.status === 'draining' ? '正在停止…' : '停止采集';
  if (info.status === 'draining') $('#stopButton').disabled = true;
  info.summaries.forEach((summary, channel) => {
    const card = $(`.chart-card[data-channel="${channel}"]`);
    $('[data-stat="latest"]', card).textContent = formatVoltage(summary.latest);
    $('[data-stat="drift"]', card).textContent = formatVoltage(summary.drift, true);
    $('[data-stat="min"]', card).textContent = formatVoltage(summary.min);
    $('[data-stat="max"]', card).textContent = formatVoltage(summary.max);
  });
}

async function refresh() {
  if (!api()) return;
  try {
    const info = await api().get_state();
    renderState(info);
    if (state.lastCount !== info.completed_count) {
      state.lastCount = info.completed_count;
      const plot = await api().get_plot_data();
      state.records = plot.records;
      $('#drawInfo').textContent = `绘制 ${plot.drawn.toLocaleString()} / ${plot.total.toLocaleString()} 点`;
      charts.forEach(chart => chart.draw());
    }
  } catch (error) {
    toast(`界面同步失败：${error}`, true);
  }
}

async function startAcquisition() {
  $('#startButton').disabled = true;
  const result = await api().start(collectConfig());
  if (!result.ok) toast(result.error, true);
  await refresh();
}

async function stopAcquisition() {
  const result = await api().stop();
  if (!result.ok) toast(result.error, true);
  await refresh();
}

async function exportAll() {
  const result = await api().export_all_csv();
  if (result.ok) toast(`已导出 ${result.count.toLocaleString()} 条完整记录`);
  else if (!result.cancelled) toast(result.error, true);
  await refresh();
}

async function clearData() {
  let result = await api().clear_data(false);
  if (result.confirm_required && window.confirm('存在未导出的结果，确定清空吗？')) result = await api().clear_data(true);
  if (!result.ok && !result.confirm_required) toast(result.error, true);
  if (result.ok) {
    state.lastCount = -1;
    state.waveformRevision = -1;
    state.waveform = null;
    state.waveformDirty = true;
    renderWaveformMeta();
    charts.forEach(chart => chart.reset());
  }
  await refresh();
}

function showContextMenu(event, channel) {
  event.preventDefault();
  state.contextChannel = channel;
  const menu = $('#contextMenu');
  menu.hidden = false;
  const x = Math.min(event.clientX, innerWidth - 200), y = Math.min(event.clientY, innerHeight - 150);
  menu.style.left = `${x}px`; menu.style.top = `${y}px`;
}

$('#contextMenu').addEventListener('click', async event => {
  const action = event.target.dataset.action;
  $('#contextMenu').hidden = true;
  if (action === 'reset') charts[state.contextChannel].reset();
  if (action === 'all') await exportAll();
  if (action === 'channel') {
    const result = await api().export_channel_csv(state.contextChannel);
    if (result.ok) toast(`AI${state.contextChannel} 已导出 ${result.count.toLocaleString()} 条记录`);
    else if (!result.cancelled) toast(result.error, true);
  }
});

document.addEventListener('click', event => { if (!event.target.closest('#contextMenu')) $('#contextMenu').hidden = true; });
$('#startButton').addEventListener('click', startAcquisition);
$('#stopButton').addEventListener('click', stopAcquisition);
$('#exportButton').addEventListener('click', exportAll);
$('#clearButton').addEventListener('click', clearData);
$('#xAxisMode').addEventListener('change', event => { state.xMode = event.target.value; charts.forEach(chart => chart.reset()); });
$('#windowUnit').addEventListener('change', event => {
  const toSeconds = event.target.value === 's';
  const factor = toSeconds ? .001 : 1000;
  $('#windowStart').value = Number($('#windowStart').value) * factor;
  $('#windowEnd').value = Number($('#windowEnd').value) * factor;
  $('#windowStart').step = toSeconds ? '.001' : '1';
  $('#windowEnd').step = toSeconds ? '.001' : '1';
});
$$('input[name="mode"]').forEach(input => input.addEventListener('change', () => {
  const simulation = $('input[name="mode"]:checked').value === 'simulation';
  $('#simulationOptions').style.display = simulation ? '' : 'none';
  $('#device').disabled = simulation || state.locked;
  $('#refreshDevices').disabled = simulation || state.locked;
  $('#modeHint').textContent = simulation ? '生成慢漂、噪声及 12 ms 触发脉冲。' : '四路默认 DC 耦合、±10 V，IEPE 关闭。';
}));
$('#refreshDevices').addEventListener('click', async () => {
  const result = await api().list_devices();
  if (result.ok && result.devices.length) { $('#device').value = result.devices[0]; toast(`检测到 ${result.devices.join('、')}`); }
  else toast(result.error || '未检测到 NI 设备', true);
});

window.addEventListener('pywebviewready', () => {
  refresh();
  state.waveformPolling = true;
  pollWaveform();
  setInterval(refresh, 400);
});
window.addEventListener('resize', () => {
  charts.forEach(chart => chart.draw());
  state.waveformDirty = true;
});
charts.forEach(chart => chart.draw());
renderWaveformMeta();
requestAnimationFrame(waveformAnimationFrame);
