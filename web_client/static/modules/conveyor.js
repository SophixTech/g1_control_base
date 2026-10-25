// Independent diagnostic panel. ROI images never enter the three model camera streams.
(() => {
  let editing = false;
  let revision = -1;
  let latest = null;
  const labels = {disabled:'未启用', stopped:'人工停止 / 未启动', waiting:'等待传送台归位',
    resuming:'正在获取新动作', running:'运行', countdown:'延迟停止', fault:'故障，需人工处理'};
  async function poll() {
    try {
      const response = await fetch('/api/client/conveyor');
      if (!response.ok) return;
      const data = await response.json(); latest = data;
      App.conveyorEnabled = !!data.enabled;
      if (typeof setThreadControlUI === "function") setThreadControlUI();
      const busy = data.authorized || !!App.isControlRunning;
      document.getElementById('conveyor-enabled').disabled = busy;
      document.getElementById('conveyor-apply').disabled = busy;
      if (!editing) {
        document.getElementById('conveyor-enabled').checked = data.enabled;
        document.getElementById('conveyor-delay').value = data.config.stop_delay_s;
        document.getElementById('conveyor-rois').value = JSON.stringify(data.config.rois);
      }
      document.getElementById('conveyor-state').textContent =
        `${labels[data.phase] || data.phase} · ${data.visible}/5` +
        (data.remaining_s != null ? ` · ${data.remaining_s.toFixed(1)} 秒` : '') +
        (data.error ? ` · ${data.error}` : '');
      document.getElementById('conveyor-points').textContent = (data.points || []).map(
        (p,i) => `${i+1}: ${p.visible ? '可见' : '不可见'} (${p.area}px)`).join(' | ');
      if (data.preview_jpeg && data.revision !== revision) {
        const img = document.getElementById('conveyor-preview');
        img.src = 'data:image/jpeg;base64,' + data.preview_jpeg; img.hidden = false;
        revision = data.revision;
      } else if (!data.preview_jpeg) {
        document.getElementById('conveyor-preview').hidden = true; revision = -1;
      }
    } catch (_) { /* Reconnect on next poll. */ }
    finally { setTimeout(poll, latest?.enabled ? 200 : 1000); }
  }
  async function apply(onlyToggle = false) {
    try {
      const patch = {'vision.conveyor_gate.enabled':document.getElementById('conveyor-enabled').checked};
      if (!onlyToggle) {
        patch['vision.conveyor_gate.stop_delay_s'] = Number(document.getElementById('conveyor-delay').value);
        patch['vision.conveyor_gate.rois'] = JSON.parse(document.getElementById('conveyor-rois').value);
      }
      const res = await apiFetch('/api/client/config/patch', {method:'POST', body:JSON.stringify({patch})});
      App.config = res.config || App.config;
      editing = false; revision = -1;
      toast('检测配置已应用', 'ok');
    } catch (error) { toast(error.message || '检测配置无效', 'error'); editing = false; }
  }
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('conveyor-enabled').addEventListener('change', () => apply(true));
    for (const id of ['conveyor-delay','conveyor-rois']) {
      document.getElementById(id).addEventListener('input', () => { editing = true; });
    }
    document.getElementById('conveyor-apply').addEventListener('click', () => apply());
    poll();
  });
})();
