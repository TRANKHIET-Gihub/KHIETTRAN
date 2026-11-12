import sys, subprocess, json
from pathlib import Path
import cv2, numpy as np
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QListWidget,QLabel,QFileDialog,QComboBox,QCheckBox,QDoubleSpinBox,QSpinBox,QGroupBox,QFormLayout,QProgressBar,QMessageBox,QAbstractItemView
from PySide6.QtCore import QThread, Signal

ROOT=Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent

def exe(name):
    p=ROOT/"runtime"/"ffmpeg"/(name+".exe")
    return str(p) if p.exists() else name

def probe(path):
    p=subprocess.run([exe("ffprobe"),"-v","error","-show_streams","-show_format","-of","json",str(path)],capture_output=True,text=True,encoding="utf-8",errors="replace")
    if p.returncode: raise RuntimeError(p.stderr.strip() or "ffprobe failed")
    return json.loads(p.stdout)

def nvenc_available():
    try:
        s=subprocess.run([exe("ffmpeg"),"-hide_banner","-encoders"],capture_output=True,text=True,encoding="utf-8",errors="ignore").stdout
        return "h264_nvenc" in s and "hevc_nvenc" in s
    except Exception:
        return False

def analyze(path):
    cap=cv2.VideoCapture(str(path))
    total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if not cap.isOpened(): raise RuntimeError("Cannot open source video.")
    ids=np.linspace(0,max(total-1,0),min(12,max(total,1))).astype(int)
    ys=[]; rg=[]; bg=[]; ss=[]
    for i in ids:
        cap.set(cv2.CAP_PROP_POS_FRAMES,int(i)); ok,f=cap.read()
        if not ok: continue
        x=cv2.cvtColor(f,cv2.COLOR_BGR2RGB).astype(np.float32)/255
        y=.2126*x[:,:,0]+.7152*x[:,:,1]+.0722*x[:,:,2]
        ys.append(float(y.mean())); rg.append(float((x[:,:,0]-x[:,:,1]).mean())); bg.append(float((x[:,:,2]-x[:,:,1]).mean()))
        hsv=cv2.cvtColor((x*255).astype(np.uint8),cv2.COLOR_RGB2HSV); ss.append(float(hsv[:,:,1].mean()/255))
    cap.release()
    if not ys: return 0,1,0,0,1
    ev=float(np.clip(np.log2(.48/max(np.mean(ys),1e-4)),-1.5,1.5))
    contrast=float(np.clip(1+(0.48-np.std(ys))*.6,.85,1.18))
    temp=float(np.clip(-np.mean(bg)*160,-25,25)); tint=float(np.clip(-np.mean(rg)*120,-20,20))
    sat=float(np.clip(1+(0.42-np.mean(ss))*.25,.9,1.12))
    return ev,contrast,temp,tint,sat

def make_filter(a,m,lut):
    ev,c,t,ti,s=a
    ev=float(np.clip(ev+m["exposure"],-3,3)); c=float(np.clip(c*m["contrast"],.5,1.8)); s=float(np.clip(s*m["saturation"],0,2))
    parts=[f"eq=contrast={c:.5f}:saturation={s:.5f}",f"exposure={ev:.5f}"]
    warm=float(np.clip((t+m["temperature"])/100,-.4,.4)); tint=float(np.clip((ti+m["tint"])/100,-.3,.3))
    if abs(warm)>1e-3 or abs(tint)>1e-3:
        rs=warm-tint; bs=-warm-tint
        parts.append(f"colorbalance=rs={rs:.4f}:gs={tint:.4f}:bs={bs:.4f}:rm={rs*.7:.4f}:gm={tint*.7:.4f}:bm={bs*.7:.4f}")
    sh=float(np.clip(m["shadows"]/100,-.5,.5)); hi=float(np.clip(m["highlights"]/100,-.5,.5))
    black=float(np.clip(m["blacks"]/100,-0.25,0.25)); white=float(np.clip(m["whites"]/100,-0.25,0.25))
    vib=float(np.clip(m["vibrance"]/100,-1,1))
    if abs(vib)>1e-3: parts.append("vibrance=intensity={:.4f}".format(vib))
    if any(abs(v)>1e-3 for v in (sh,hi,black,white)):
        p0=float(np.clip(black*.20,0,.20)); p25=float(np.clip(.25+sh*.18,0,1))
        p75=float(np.clip(.75+hi*.18,0,1)); p100=float(np.clip(1+white*.20,.80,1))
        parts.append("curves=all='0/{:.4f} 0.25/{:.4f} 0.75/{:.4f} 1/{:.4f}'".format(p0,p25,p75,p100))
    if lut:
        parts.append("lut3d=file='"+str(lut).replace(chr(92),"/").replace("'","\\'")+"'")
    return ",".join(parts)

class Worker(QThread):
    row=Signal(int,str); overall=Signal(int); done=Signal()
    def __init__(self,items,settings,manual,auto,lut):
        super().__init__(); self.items=items; self.settings=settings; self.manual=manual; self.auto=auto; self.lut=lut; self.cancelled=False
    def cancel(self): self.cancelled=True
    def run(self):
        total=len(self.items)
        for n,src in enumerate(self.items):
            if self.cancelled: break
            try:
                self.row.emit(n,"Analyzing" if self.auto else "Processing")
                a=analyze(src) if self.auto else (0,1,0,0,1)
                vf=make_filter(a,self.manual,self.lut)
                sizes={"2K":(2560,1440),"4K":(3840,2160),"8K":(7680,4320)}
                if self.settings["resolution"] in sizes:
                    w,h=sizes[self.settings["resolution"]]
                    vf+=f",scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
                use_nv=nvenc_available() and self.settings["nvenc"]
                if self.settings["codec"]=="H.265 / HEVC":
                    enc="hevc_nvenc" if use_nv else "libx265"
                else:
                    enc="h264_nvenc" if use_nv else "libx264"
                out=Path(self.settings["out"])/(src.stem+"_color.mp4"); out.parent.mkdir(parents=True,exist_ok=True)
                cmd=[exe("ffmpeg"),"-y","-hide_banner","-i",str(src),"-vf",vf,"-c:v",enc,"-b:v",f'{self.settings["bitrate"]}M',"-preset","p5" if use_nv else "medium","-map","0:v:0"]
                if self.settings["audio"]: cmd += ["-map","0:a?","-c:a","aac","-b:a","320k"]
                else: cmd += ["-an"]
                cmd += ["-movflags","+faststart",str(out)]
                p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace")
                while p.poll() is None:
                    if self.cancelled: p.kill(); raise RuntimeError("Cancelled")
                    p.stdout.readline()
                if p.returncode: raise RuntimeError(f"FFmpeg exit code {p.returncode}")
                info=probe(out)
                if not info.get("streams"): raise RuntimeError("Output validation failed")
                self.row.emit(n,"Done")
            except Exception as e:
                self.row.emit(n,"ERROR: "+str(e))
            self.overall.emit(int((n+1)/total*100))
        self.done.emit()

class Main(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("KHIETTRAN Video Color Studio"); self.resize(1180,760)
        self.files=[]; self.lut=None; self.worker=None
        root=QWidget(); self.setCentralWidget(root); layout=QHBoxLayout(root)
        left=QVBoxLayout(); left.addWidget(QLabel("<b>Source Videos</b>"))
        self.list=QListWidget(); self.list.setSelectionMode(QAbstractItemView.ExtendedSelection); left.addWidget(self.list)
        buttons=QHBoxLayout()
        for label,fn in [("Add",self.add),("Remove",self.remove),("Clear",self.clear)]:
            b=QPushButton(label); b.clicked.connect(fn); buttons.addWidget(b)
        left.addLayout(buttons)
        self.auto=QCheckBox("AUTO COLOR — offline frame analysis"); self.auto.setChecked(True); left.addWidget(self.auto)
        b=QPushButton("Load 3D LUT (.cube)"); b.clicked.connect(self.load_lut); left.addWidget(b)
        self.lutlabel=QLabel("LUT: None"); left.addWidget(self.lutlabel); layout.addLayout(left,3)

        right=QVBoxLayout()
        g=QGroupBox("Color"); f=QFormLayout(g); self.c={}
        specs=[("Exposure",-3,3,.1,0),("Contrast",.5,1.8,.01,1),("Highlights",-100,100,1,0),("Shadows",-100,100,1,0),("Whites",-100,100,1,0),("Blacks",-100,100,1,0),("Temperature",-100,100,1,0),("Tint",-100,100,1,0),("Vibrance",-100,100,1,0),("Saturation",0,2,.01,1)]
        for name,lo,hi,st,val in specs:
            w=QDoubleSpinBox(); w.setRange(lo,hi); w.setSingleStep(st); w.setValue(val); self.c[name]=w; f.addRow(name,w)
        right.addWidget(g)

        e=QGroupBox("Export"); ef=QFormLayout(e)
        self.res=QComboBox(); self.res.addItems(["Original","2K","4K","8K"])
        self.codec=QComboBox(); self.codec.addItems(["H.264","H.265 / HEVC"])
        self.br=QSpinBox(); self.br.setRange(10,500); self.br.setValue(40)
        self.nv=QCheckBox("Use NVIDIA NVENC when available"); self.nv.setChecked(nvenc_available())
        self.audio=QCheckBox("Keep audio"); self.audio.setChecked(True)
        self.out=QLabel(str(Path.home()/"KHIETTRAN_Output"))
        for lab,w in [("Resolution",self.res),("Codec",self.codec),("Bitrate Mbps",self.br)]: ef.addRow(lab,w)
        ef.addRow(self.nv); ef.addRow(self.audio)
        choose=QPushButton("Choose output folder"); choose.clicked.connect(self.choose); ef.addRow(choose); ef.addRow("Output",self.out)
        right.addWidget(e)

        self.progress=QProgressBar(); right.addWidget(self.progress); self.status=QLabel("Ready"); right.addWidget(self.status)
        self.start=QPushButton("START BATCH EXPORT"); self.start.clicked.connect(self.start_export)
        self.stop=QPushButton("CANCEL"); self.stop.clicked.connect(self.cancel); self.stop.setEnabled(False)
        rr=QHBoxLayout(); rr.addWidget(self.start); rr.addWidget(self.stop); right.addLayout(rr); layout.addLayout(right,4)

    def add(self):
        ps,_=QFileDialog.getOpenFileNames(self,"Add videos","", "Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)")
        for p in ps: self.files.append(Path(p)); self.list.addItem(p)
    def remove(self):
        for r in sorted([self.list.row(x) for x in self.list.selectedItems()],reverse=True):
            self.files.pop(r); self.list.takeItem(r)
    def clear(self): self.files=[]; self.list.clear()
    def load_lut(self):
        p,_=QFileDialog.getOpenFileName(self,"Load LUT","","3D LUT (*.cube)")
        if p: self.lut=Path(p); self.lutlabel.setText("LUT: "+self.lut.name)
    def choose(self):
        p=QFileDialog.getExistingDirectory(self,"Output folder")
        if p:self.out.setText(p)
    def start_export(self):
        if not self.files: return QMessageBox.warning(self,"No source","Add at least one video.")
        m={k.lower().replace(" ","_"):v.value() for k,v in self.c.items()}
        settings={"resolution":self.res.currentText(),"codec":self.codec.currentText(),"bitrate":self.br.value(),"nvenc":self.nv.isChecked(),"audio":self.audio.isChecked(),"out":self.out.text()}
        manual={"exposure":m["exposure"],"contrast":m["contrast"],"highlights":m["highlights"],"shadows":m["shadows"],"whites":m["whites"],"blacks":m["blacks"],"temperature":m["temperature"],"tint":m["tint"],"vibrance":m["vibrance"],"saturation":m["saturation"]}
        self.worker=Worker(self.files,settings,manual,self.auto.isChecked(),self.lut)
        self.worker.row.connect(lambda i,s:self.list.item(i).setText(str(self.files[i])+" — "+s))
        self.worker.overall.connect(self.progress.setValue); self.worker.done.connect(self.finished)
        self.start.setEnabled(False); self.stop.setEnabled(True); self.worker.start()
    def cancel(self):
        if self.worker:self.worker.cancel(); self.status.setText("Cancelling...")
    def finished(self):
        self.start.setEnabled(True); self.stop.setEnabled(False); self.status.setText("Batch export finished."); QMessageBox.information(self,"Complete","Batch export finished and outputs were validated.")

def run_self_test(log):
    import tempfile
    from pathlib import Path

    ffmpeg_path = Path(exe("ffmpeg"))
    ffprobe_path = Path(exe("ffprobe"))
    if getattr(sys, "frozen", False):
        for tool_path in (ffmpeg_path, ffprobe_path):
            if not tool_path.is_file():
                raise RuntimeError(f"Bundled executable missing: {tool_path}")
    log(f"FFmpeg path: {ffmpeg_path}")
    log(f"FFprobe path: {ffprobe_path}")

    version = subprocess.run(
        [str(ffmpeg_path), "-hide_banner", "-version"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
    )
    if version.returncode:
        raise RuntimeError("FFmpeg version check failed: " + version.stderr[-2000:])
    log("FFmpeg version check: PASS")

    enc = subprocess.run(
        [str(ffmpeg_path), "-hide_banner", "-encoders"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
    )
    if enc.returncode:
        raise RuntimeError("FFmpeg encoder listing failed: " + enc.stderr[-2000:])
    for name in ("libx264", "libx265"):
        if name not in enc.stdout:
            raise RuntimeError(f"Required FFmpeg encoder unavailable: {name}")
    log("Required encoders libx264/libx265: PASS")

    with tempfile.TemporaryDirectory(prefix="khiettran_selftest_") as td:
        td = Path(td)
        source = td / "source.mp4"
        cmd = [
            str(ffmpeg_path), "-y", "-hide_banner",
            "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000",
            "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(source)
        ]
        log("Creating synthetic test video with audio...")
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=120)
        if p.returncode:
            raise RuntimeError("Synthetic source creation failed: " + p.stderr[-3000:])
        if not source.is_file() or source.stat().st_size == 0:
            raise RuntimeError("Synthetic source was not created.")

        manual = {
            "exposure": 0.1, "contrast": 1.05, "highlights": 5, "shadows": 5,
            "whites": 5, "blacks": -5, "temperature": 2, "tint": 1,
            "vibrance": 10, "saturation": 1.05
        }
        vf = make_filter((0, 1, 0, 0, 1), manual, None)
        log("Filter chain: " + vf)

        for codec, encoder in (("h264", "libx264"), ("hevc", "libx265")):
            out = td / (codec + ".mp4")
            log(f"Encoding {codec.upper()} test output...")
            cmd = [
                str(ffmpeg_path), "-y", "-hide_banner", "-i", str(source),
                "-vf", vf, "-c:v", encoder, "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", "-map", "0:v:0", "-map", "0:a?",
                "-c:a", "aac", "-b:a", "128k", str(out)
            ]
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=180)
            if p.returncode:
                raise RuntimeError(f"{codec.upper()} encode failed (exit {p.returncode}): " + p.stderr[-4000:])
            if not out.is_file() or out.stat().st_size == 0:
                raise RuntimeError(f"{codec.upper()} output file missing or empty.")
            log(f"{codec.upper()} encode: PASS ({out.stat().st_size} bytes)")

            streams = probe(out).get("streams", [])
            kinds = {x.get("codec_type") for x in streams}
            if "video" not in kinds or "audio" not in kinds:
                raise RuntimeError(f"{codec.upper()} output missing video/audio stream: {streams}")
            log(f"{codec.upper()} video/audio stream validation: PASS")
    return True


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        import os
        import traceback
        log_path = Path(os.environ.get(
            "KHIETTRAN_SELFTEST_LOG",
            str(Path.home() / "KHIETTRAN-self-test.log")
        ))
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            def write_log(message):
                with log_path.open("a", encoding="utf-8") as stream:
                    stream.write(str(message) + "\n")
                    stream.flush()
            log_path.write_text("KHIETTRAN PORTABLE SELF-TEST START\n", encoding="utf-8")
            run_self_test(write_log)
            write_log("PASS: H.264, HEVC and audio streams validated.")
            sys.exit(0)
        except BaseException:
            detail = traceback.format_exc()
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as stream:
                    stream.write("\nSELF-TEST FAILURE\n")
                    stream.write(detail)
                    stream.flush()
            except Exception:
                pass
            if sys.stderr is not None:
                try:
                    print(detail, file=sys.stderr, flush=True)
                except Exception:
                    pass
            os._exit(1)
    app = QApplication(sys.argv)
    w = Main()
    w.show()
    sys.exit(app.exec())
