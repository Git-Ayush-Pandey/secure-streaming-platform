import React, { useState, useEffect } from 'react';
import { Settings, Save, Monitor, LayoutTemplate, Info } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { configureStream } from '../api/stream';

const FPS_OPTIONS    = [5, 10, 15, 20, 30];


const PRESETS = {
  fullscreen: { x: 0, y: 0, width: 1920, height: 1080, label: 'Full Screen' },
  left_half:  { x: 0, y: 0, width: 960,  height: 1080, label: 'Left Half' },
  right_half: { x: 960, y: 0, width: 960, height: 1080, label: 'Right Half' },
  custom:     { label: 'Custom' },
};

export default function StreamConfig() {
  const { serverInfo, refreshServerInfo } = useApp();

  const cap     = serverInfo?.config?.capture;
  const udpPort = serverInfo?.stream?.udp_port ?? serverInfo?.config?.server?.port ?? 8765;

  const [form, setForm] = useState({
    x: 0, y: 0, width: 1280, height: 720, fps: 20,
  });
  const [preset,  setPreset]  = useState('custom');
  const [saving,  setSaving]  = useState(false);
  const [saved,   setSaved]   = useState(false);
  const [error,   setError]   = useState('');

  // Populate from server config on load
  useEffect(() => {
    if (cap) {
      setForm({
        x:       cap.x       ?? 0,
        y:       cap.y       ?? 0,
        width:   cap.width   ?? 1280,
        height:  cap.height  ?? 720,
        fps:     cap.fps     ?? 20,
        // quality and codec removed, forced JPEG-100 backend
      });
    }
  }, [serverInfo]);

  function applyPreset(key) {
    setPreset(key);
    if (key !== 'custom') {
      const p = PRESETS[key];
      setForm(f => ({ ...f, x: p.x, y: p.y, width: p.width, height: p.height }));
    }
  }

  function setField(field, val) {
    setPreset('custom');
    setForm(f => ({ ...f, [field]: val }));
  }

  // Clamp to backend validation limits:
  //   width  [64, 7680], height [64, 4320], fps [1, 60]
  function setInt(field, raw, min, max) {
    const n = Math.max(min, Math.min(max, parseInt(raw, 10) || min));
    setField(field, n);
  }

  async function handleSave() {
    setSaving(true);
    setError('');
    setSaved(false);
    try {
      await configureStream({ ...form, fps: Number(form.fps) });
      await refreshServerInfo();
      setSaved(true);
      setTimeout(() => setSaved(false), 4000);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1 className="page-title">Capture Configuration</h1>
      <p className="page-subtitle">
        Configure the screen capture region and frame rate.
      </p>

      {/* Backend validation limits info */}
      <div style={{
        display: 'flex', gap: 8, alignItems: 'flex-start',
        background: 'rgba(0,212,255,0.05)',
        border: '1px solid rgba(0,212,255,0.12)',
        borderRadius: 10, padding: '10px 14px',
        marginBottom: 20, fontSize: 12,
        color: 'var(--text-muted)',
      }}>
        <Info size={13} color="var(--accent-cyan)" style={{ flexShrink: 0, marginTop: 1 }} />
        <span>
          Backend limits: Width 64–7680 px · Height 64–4320 px · FPS 1–60.
          Frames sent over UDP as <strong>AES-256-GCM (seq AAD)</strong>, fragmented to fit MTU.
          Codec: <strong style={{ fontFamily: 'JetBrains Mono', color: 'var(--accent-cyan)' }}>JPEG</strong>.
        </span>
      </div>

      <div className="grid-2">
        {/* Capture Region */}
        <div className="card">
          <div className="card-title"><Monitor size={14} /> Capture Region</div>

          <div style={{ marginBottom: 16 }}>
            <div className="form-label">Preset</div>
            <div className="preset-grid">
              {Object.entries(PRESETS).map(([key, val]) => (
                <button
                  key={key}
                  id={`preset-${key}`}
                  className={`preset-btn${preset === key ? ' active' : ''}`}
                  onClick={() => applyPreset(key)}
                >
                  {val.label}
                </button>
              ))}
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">X Position</label>
              <input id="capture-x" type="number" className="form-input"
                value={form.x} min={0}
                onChange={e => setInt('x', e.target.value, 0, 7680)} />
            </div>
            <div className="form-group">
              <label className="form-label">Y Position</label>
              <input id="capture-y" type="number" className="form-input"
                value={form.y} min={0}
                onChange={e => setInt('y', e.target.value, 0, 4320)} />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Width (64–7680 px)</label>
              <input id="capture-width" type="number" className="form-input"
                value={form.width} min={64} max={7680}
                onChange={e => setInt('width', e.target.value, 64, 7680)} />
            </div>
            <div className="form-group">
              <label className="form-label">Height (64–4320 px)</label>
              <input id="capture-height" type="number" className="form-input"
                value={form.height} min={64} max={4320}
                onChange={e => setInt('height', e.target.value, 64, 4320)} />
            </div>
          </div>

          <div style={{
            background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.15)',
            borderRadius: 8, padding: '10px 14px',
            fontSize: 12, color: 'var(--accent-cyan)', fontFamily: 'JetBrains Mono',
          }}>
            Region: ({form.x}, {form.y}) → {form.width} × {form.height} px
          </div>
        </div>

        {/* Encoding Settings */}
        <div className="card">
          <div className="card-title"><LayoutTemplate size={14} /> Encoding Settings</div>

          <div className="form-group" style={{ marginBottom: 20 }}>
            <div className="form-label">Frame Rate (1–60 FPS)</div>
            <div className="fps-grid">
              {FPS_OPTIONS.map(f => (
                <button
                  key={f}
                  id={`fps-${f}`}
                  className={`fps-btn${form.fps === f ? ' active' : ''}`}
                  onClick={() => setForm(prev => ({ ...prev, fps: f }))}
                >
                  {f} FPS
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="card mt-20">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <button
            id="save-stream-config"
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving}
          >
            {saving
              ? <><span className="spinner" style={{ width: 14, height: 14 }} /> Applying…</>
              : <><Save size={14} /> Apply Configuration</>
            }
          </button>

          {saved && (
            <span style={{ color: 'var(--accent-green)', fontSize: 13, fontWeight: 600 }}>
              ✓ Applied — capture restarted, UDP stream continues
            </span>
          )}
          {error && (
            <span style={{ color: 'var(--accent-red)', fontSize: 13 }}>
              ✕ {error}
            </span>
          )}
        </div>

        <p style={{ marginTop: 10, fontSize: 12, color: 'var(--text-muted)' }}>
          Applying restarts the <strong>screen capture</strong> service only.
          The UDP stream service on port <strong style={{ fontFamily: 'JetBrains Mono' }}>
            {udpPort}</strong> remains running.
          Registered clients will resume receiving frames within one capture cycle.
        </p>
      </div>
    </div>
  );
}

/** Rough Mbps estimate: pixels × fps × bitsPerPixel / 1e6 */
function estimateMbps({ width, height, fps }) {
  // Approximate bits per pixel for high-quality JPEG (quality 95)
  const bpp = 0.9; // JPEG ultra quality approx 0.9 bits per pixel
  const mbps = (width * height * fps * bpp) / 1e6;
  return mbps.toFixed(1);
}
