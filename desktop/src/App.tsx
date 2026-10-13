import { useEffect, useMemo, useRef, useState } from "react";
import { Aperture, ImagePlus, FolderOpen, SlidersHorizontal, Sparkles, Download, Trash2, Sun, Palette, Scissors, RotateCcw, CheckCircle2, AlertCircle } from "lucide-react";

type Photo = { id: string; name: string; url: string; file: File };
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) || "http://127.0.0.1:8000";

export default function App() {
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [brightness, setBrightness] = useState(0);
  const [contrast, setContrast] = useState(100);
  const [saturation, setSaturation] = useState(100);
  const [apiOnline, setApiOnline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("Import ảnh để bắt đầu chỉnh sửa.");
  const inputRef = useRef<HTMLInputElement>(null);
  const selected = photos.find(p => p.id === selectedId) || photos[0] || null;
  const filter = useMemo(() => `brightness(${100 + brightness}%) contrast(${contrast}%) saturate(${saturation}%)`, [brightness, contrast, saturation]);

  useEffect(() => {
    let active = true;
    fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) })
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(() => active && setApiOnline(true))
      .catch(() => active && setApiOnline(false));
    return () => { active = false; };
  }, []);

  function addFiles(files: FileList | null) {
    const incoming = Array.from(files || []).filter(f => f.type.startsWith("image/"));
    const next = incoming.map(file => ({ id: crypto.randomUUID(), name: file.name, url: URL.createObjectURL(file), file }));
    setPhotos(prev => [...prev, ...next]);
    if (next.length) { setSelectedId(prev => prev || next[0].id); setNotice(`Đã thêm ${next.length} ảnh.`); }
    else setNotice("Chưa chọn tệp ảnh hợp lệ.");
  }

  function exportImage(photo: Photo) {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) return setNotice("Không thể xuất ảnh.");
      ctx.filter = filter; ctx.drawImage(img, 0, 0);
      canvas.toBlob(blob => {
        if (!blob) return setNotice("Xuất ảnh thất bại.");
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a"); a.href = url; a.download = `${photo.name.replace(/\.[^.]+$/, "")}-khiettran.jpg`; a.click();
        URL.revokeObjectURL(url); setNotice(`Đã xuất ${photo.name}.`);
      }, "image/jpeg", 0.95);
    };
    img.onerror = () => setNotice("Không đọc được ảnh.");
    img.src = photo.url;
  }

  async function runAI(endpoint: string, label: string) {
    if (!selected || busy) return;
    setBusy(true); setNotice(`Đang xử lý: ${label}…`);
    try {
      const form = new FormData(); form.append("file", selected.file, selected.name);
      const response = await fetch(`${API_BASE}${endpoint}`, { method: "POST", body: form });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Yêu cầu thất bại (${response.status}).`);
      }
      const blob = await response.blob();
      const file = new File([blob], `${selected.name.replace(/\.[^.]+$/, "")}-${label}.png`, { type: "image/png" });
      const photo = { id: crypto.randomUUID(), name: file.name, url: URL.createObjectURL(file), file };
      setPhotos(prev => [...prev, photo]); setSelectedId(photo.id); setNotice(`Hoàn tất ${label}; ảnh kết quả đã được thêm vào thư viện.`);
    } catch (e) { setNotice(e instanceof Error ? e.message : "Không kết nối được dịch vụ AI."); }
    finally { setBusy(false); }
  }

  async function checkCapabilities() {
    try {
      const r = await fetch(`${API_BASE}/api/v1/capabilities`);
      if (!r.ok) throw new Error();
      const data = await r.json();
      setNotice(`API hoạt động. Cấu hình AI: ${data.ai_provider_configured ? "đã có token" : "chưa có token"}. Cần thử xử lý ảnh thật để xác nhận model.`);
    } catch { setNotice("Không kết nối được API. Kiểm tra VITE_API_BASE_URL."); }
  }

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-mark"><Aperture size={22}/></div><div><strong>KHIETTRAN <span>AI STUDIO</span></strong><small>PORTRAIT WORKFLOW · MVP</small></div></div>
      <div className="top-actions"><span className={`connection ${apiOnline ? "online" : "offline"}`}>{apiOnline ? "● API trực tuyến" : "● API ngoại tuyến"}</span><button className="btn" onClick={() => inputRef.current?.click()}><FolderOpen size={16}/> Import ảnh</button><button className="btn primary" disabled={!selected} onClick={() => selected && exportImage(selected)}><Download size={16}/> Xuất ảnh</button></div>
    </header>
    <div className="workspace">
      <aside className="left-rail"><button className="rail-item active"><ImagePlus/><span>Thư viện</span></button><button className="rail-item" onClick={() => setNotice("Điều chỉnh bằng bảng bên phải.")}><SlidersHorizontal/><span>Chỉnh màu</span></button><button className="rail-item" onClick={() => setNotice("Chọn ảnh rồi chạy công cụ AI ở bảng bên phải.")}><Sparkles/><span>AI chân dung</span></button><button className="rail-item" onClick={() => selected && runAI("/api/v1/background/remove", "no-background")}><Scissors/><span>Tách nền</span></button></aside>
      <main className="main-area">
        <div className="section-head"><div><h1>Không gian chỉnh sửa</h1><p>Chỉnh màu tại máy · AI xử lý qua API HTTPS</p></div><strong>{photos.length} ẢNH</strong></div>
        <section className="preview-stage">{selected ? <div className="preview-wrap"><img src={selected.url} alt={selected.name} style={{filter}}/><span className="preview-name">{selected.name}</span></div> : <button className="empty-state" onClick={() => inputRef.current?.click()}><ImagePlus size={36}/><strong>Thêm ảnh để bắt đầu</strong><span>Chọn một hoặc nhiều ảnh từ máy tính</span><small>JPG · PNG · WEBP</small></button>}</section>
        <div className="library-head"><strong>Thư viện ảnh</strong><button className="icon-btn" onClick={() => inputRef.current?.click()}><ImagePlus size={16}/></button><button className="icon-btn" disabled={!photos.length} onClick={() => { photos.forEach(p => URL.revokeObjectURL(p.url)); setPhotos([]); setSelectedId(null); }}><Trash2 size={16}/></button></div>
        <section className="filmstrip">{photos.length ? photos.map(p => <button key={p.id} className={`thumb ${selected?.id === p.id ? "selected" : ""}`} onClick={() => setSelectedId(p.id)}><img src={p.url} alt={p.name}/><span>{p.name}</span></button>) : <p>Ảnh đã nhập sẽ xuất hiện ở đây.</p>}</section>
        <footer className="statusbar"><span><CheckCircle2 size={15}/>{notice}</span><span>Ảnh gốc không bị ghi đè</span></footer>
      </main>
      <aside className="right-panel"><div className="panel-title"><SlidersHorizontal size={18}/><strong>Điều chỉnh</strong><button className="icon-btn" onClick={() => {setBrightness(0);setContrast(100);setSaturation(100);}}><RotateCcw size={15}/></button></div>
        <section className="tool-section"><h3><Sun size={16}/> Ánh sáng</h3><Slider label="Độ sáng" value={brightness} min={-50} max={50} onChange={setBrightness}/><Slider label="Tương phản" value={contrast} min={50} max={160} onChange={setContrast}/></section>
        <section className="tool-section"><h3><Palette size={16}/> Màu sắc</h3><Slider label="Bão hòa" value={saturation} min={0} max={180} onChange={setSaturation}/></section>
        <section className="tool-section ai-tools"><h3><Sparkles size={16}/> AI chân dung</h3><p>Cần máy chủ API và token Replicate hợp lệ.</p><button className="tool-button" onClick={checkCapabilities}>Kiểm tra kết nối AI</button><button className="tool-button" disabled={!selected || busy} onClick={() => runAI("/api/v1/portrait/retouch", "portrait-enhanced")}>Làm đẹp chân dung · GFPGAN</button><button className="tool-button" disabled={!selected || busy} onClick={() => runAI("/api/v1/background/remove", "no-background")}>Tách nền bằng AI</button><button className="tool-button" disabled={!selected || busy} onClick={() => runAI("/api/v1/image/restore", "restored")}>Phục hồi ảnh · GFPGAN</button></section>
        <div className="privacy-note"><AlertCircle size={17}/><p><strong>Bảo vệ dữ liệu</strong><br/>Khi chạy AI, ảnh được gửi đến API và nhà cung cấp AI đã cấu hình.</p></div>
      </aside>
    </div>
    <input ref={inputRef} hidden type="file" accept="image/*" multiple onChange={e => {addFiles(e.target.files);e.currentTarget.value="";}}/>
  </div>;
}

function Slider({label,value,min,max,onChange}:{label:string;value:number;min:number;max:number;onChange:(v:number)=>void}) {
  return <label className="slider-control"><span>{label}<b>{value}</b></span><input type="range" min={min} max={max} value={value} onChange={e=>onChange(Number(e.target.value))}/><small>{min}<i>{max}</i></small></label>;
}
