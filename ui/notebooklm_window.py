"""
ui/notebooklm_window.py — NotebookLM integration window.
"""
import asyncio
import subprocess
import sys
import os
import threading
from pathlib import Path


def _load_source_map() -> dict:
    """Load nlm_source_map.json. Returns {} nếu chưa có hoặc lỗi.
    Hỗ trợ cả format cũ {"name": "path"} và mới {"name": {"path":..., "notebooks":[...]}}.
    """
    import json
    try:
        from paths import NLM_SOURCE_MAP
        with open(NLM_SOURCE_MAP, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # Migrate format cũ
        migrated = {}
        for k, v in raw.items():
            if isinstance(v, str):
                migrated[k] = {"path": v, "notebooks": []}
            else:
                migrated[k] = v
        return migrated
    except Exception:
        return {}


def _save_source_map(src_map: dict):
    """Ghi nlm_source_map.json, bỏ các entry file không còn tồn tại."""
    import json
    try:
        from paths import NLM_SOURCE_MAP
        # Loại entry path không hợp lệ
        clean = {k: v for k, v in src_map.items()
                 if isinstance(v, dict) and os.path.isfile(v.get("path", ""))}
        with open(NLM_SOURCE_MAP, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _upsert_source_map(source_title: str, file_path: str, notebook_id: str = ""):
    """Thêm hoặc cập nhật entry trong source map."""
    src_map = _load_source_map()
    entry = src_map.get(source_title, {"path": file_path, "notebooks": []})
    entry["path"] = file_path
    if notebook_id and notebook_id not in entry.get("notebooks", []):
        entry.setdefault("notebooks", []).append(notebook_id)
    src_map[source_title] = entry
    _save_source_map(src_map)


def _lookup_source_path(source_title: str) -> str | None:
    """Tìm đường dẫn local từ tên source. Trả None nếu không có."""
    src_map = _load_source_map()
    entry = src_map.get(source_title) or next(
        (v for k, v in src_map.items() if k.lower() == source_title.lower()), None
    )
    if not entry:
        return None
    path = entry.get("path", "")
    return path if os.path.isfile(path) else None


def is_nlm_logged_in() -> bool:
    """Kiểm tra file storage_state.json đã tồn tại chưa (tức là đã login)."""
    try:
        from notebooklm.paths import get_storage_path
        return get_storage_path().exists()
    except Exception:
        return False

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QTextEdit, QLineEdit,
    QSplitter, QFileDialog, QMessageBox, QTabWidget, QWidget,
    QComboBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont


def _run_async(coro):
    """Chạy coroutine trong thread hiện tại."""
    return asyncio.run(coro)


# ── Workers ──────────────────────────────────────────────────────

class LoginWorker(QThread):
    done  = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._event = threading.Event()

    def run(self):
        try:
            # Restore DefaultEventLoopPolicy for Playwright on Windows
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

            from playwright.sync_api import sync_playwright
            from notebooklm.paths import get_storage_path, get_browser_profile_dir

            storage_path   = get_storage_path()
            browser_profile = get_browser_profile_dir()
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            browser_profile.mkdir(parents=True, exist_ok=True)

            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(browser_profile),
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--password-store=basic",
                    ],
                    ignore_default_args=["--enable-automation"],
                )
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://notebooklm.google.com/")

                # Chờ user bấm "Save Login"
                self._event.wait()

                # Force .google.com cookies
                page.goto("https://accounts.google.com/", wait_until="load")
                page.goto("https://notebooklm.google.com/", wait_until="load")

                context.storage_state(path=str(storage_path))
                try:
                    storage_path.chmod(0o600)
                except Exception:
                    pass
                context.close()

            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    def confirm(self):
        """Gửi tín hiệu lưu cookies sau khi đăng nhập xong."""
        self._event.set()


class ListNotebooksWorker(QThread):
    done  = Signal(list)
    error = Signal(str)

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _fetch():
                async with await NotebookLMClient.from_storage() as client:
                    return await client.notebooks.list()
            notebooks = _run_async(_fetch())
            self.done.emit(notebooks)
        except Exception as e:
            self.error.emit(str(e))


class CreateNotebookWorker(QThread):
    done  = Signal(object)
    error = Signal(str)

    def __init__(self, title: str):
        super().__init__()
        self.title = title

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _create():
                async with await NotebookLMClient.from_storage() as client:
                    return await client.notebooks.create(title=self.title)
            nb = _run_async(_create())
            self.done.emit(nb)
        except Exception as e:
            self.error.emit(str(e))


class DeleteNotebookWorker(QThread):
    done  = Signal()
    error = Signal(str)

    def __init__(self, notebook_id: str):
        super().__init__()
        self.notebook_id = notebook_id

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _delete():
                async with await NotebookLMClient.from_storage() as client:
                    await client.notebooks.delete(self.notebook_id)
            _run_async(_delete())
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class RenameNotebookWorker(QThread):
    done  = Signal(str)   # new title
    error = Signal(str)

    def __init__(self, notebook_id: str, new_title: str):
        super().__init__()
        self.notebook_id = notebook_id
        self.new_title   = new_title

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _rename():
                async with await NotebookLMClient.from_storage() as client:
                    nb = await client.notebooks.rename(self.notebook_id, self.new_title)
                    return getattr(nb, "title", self.new_title)
            title = _run_async(_rename())
            self.done.emit(title)
        except Exception as e:
            self.error.emit(str(e))


class ListSourcesWorker(QThread):
    done  = Signal(list)
    error = Signal(str)

    def __init__(self, notebook_id: str):
        super().__init__()
        self.notebook_id = notebook_id

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _fetch():
                async with await NotebookLMClient.from_storage() as client:
                    return await client.sources.list(self.notebook_id)
            sources = _run_async(_fetch())
            self.done.emit(sources)
        except Exception as e:
            self.error.emit(str(e))


class DeleteSourceWorker(QThread):
    done  = Signal()
    error = Signal(str)

    def __init__(self, notebook_id: str, source_id: str):
        super().__init__()
        self.notebook_id = notebook_id
        self.source_id   = source_id

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _delete():
                async with await NotebookLMClient.from_storage() as client:
                    await client.sources.delete(self.notebook_id, self.source_id)
            _run_async(_delete())
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class AddSourceWorker(QThread):
    done  = Signal()
    error = Signal(str)

    def __init__(self, notebook_id: str, file_path: str):
        super().__init__()
        self.notebook_id = notebook_id
        self.file_path   = file_path

    @staticmethod
    def _doc_to_docx(doc_path: str) -> str:
        """Convert .doc → .docx bằng Word COM, trả về path file tạm."""
        import tempfile, win32com.client as win32
        word = win32.Dispatch("Word.Application")
        word.Visible = False
        tmp = tempfile.mktemp(suffix=".docx")
        try:
            doc = word.Documents.Open(os.path.abspath(doc_path))
            doc.SaveAs(tmp, FileFormat=16)  # 16 = wdFormatXMLDocument (.docx)
            doc.Close(False)
        finally:
            word.Quit()
        return tmp

    def run(self):
        tmp_file = None
        try:
            from notebooklm import NotebookLMClient
            from pathlib import Path
            upload_path = self.file_path
            if self.file_path.lower().endswith(".doc"):
                tmp_file = self._doc_to_docx(self.file_path)
                upload_path = tmp_file
            async def _add():
                async with await NotebookLMClient.from_storage() as client:
                    await client.sources.add_file(self.notebook_id, Path(upload_path), wait=True)
            _run_async(_add())
            # Save source map
            if not self.file_path.lower().endswith(".doc"):
                _upsert_source_map(
                    os.path.basename(self.file_path),
                    self.file_path,
                    self.notebook_id,
                )
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if tmp_file and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass


_SUMMARIZE_PROMPT = (
    "Please provide a comprehensive summary of this document following its original structure and headings. "
    "Include: main topics, key findings or procedures, important technical data, "
    "warnings or critical notices, and key takeaways. "
    "Use plain text only — no markdown, no ### or ** symbols, no bullet asterisks. "
    "Use the document's own section titles as headings."
)

_TRANSLATE_VI_PROMPT = (
    "Now provide a comprehensive summary of the same document in Vietnamese. "
    "Follow the same structure and section headings as the document. "
    "Include all main topics, key findings, procedures, technical data, warnings, and key takeaways — same level of detail as the English summary. "
    "Write in proper Vietnamese with full diacritical marks and tone marks (ă, â, đ, ê, ô, ơ, ư and all tone accents). "
    "Do NOT use ASCII transliteration (write 'không' not 'khong', 'được' not 'duoc', etc.). "
    "Use plain text only — no markdown, no ### or ** symbols, no bullet asterisks."
)


class NLMAutoSummarizeWorker(QThread):
    """Auto-pick first notebook (or create one) → upload → summarize → delete source."""
    done  = Signal(str)
    error = Signal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _work():
                async with await NotebookLMClient.from_storage() as client:
                    notebooks = await client.notebooks.list()
                    if notebooks:
                        nb = notebooks[0]
                        nb_id = getattr(nb, "id", None) or getattr(nb, "notebook_id", "")
                    else:
                        nb = await client.notebooks.create(title="Auto Summary")
                        nb_id = getattr(nb, "id", None) or getattr(nb, "notebook_id", "")
                    source = await client.sources.add_file(nb_id, Path(self.file_path), wait=True)
                    sid = getattr(source, "source_id", None) or getattr(source, "id", None)
                    result_orig = await client.chat.ask(nb_id, _SUMMARIZE_PROMPT, source_ids=[sid])
                    summary_orig = (getattr(result_orig, "answer", None) or str(result_orig)).strip()
                    result_vi = await client.chat.ask(nb_id, _TRANSLATE_VI_PROMPT, source_ids=[sid])
                    summary_vi = (getattr(result_vi, "answer", None) or str(result_vi)).strip()
                    await client.sources.delete(nb_id, sid)
                    separator = "\n\n" + "─" * 48 + "\n🇻🇳  BẢN TIẾNG VIỆT\n" + "─" * 48 + "\n\n"
                    return summary_orig + separator + summary_vi
            text = _run_async(_work())
            self.done.emit(text)
        except Exception as e:
            self.error.emit(str(e))


_MINDMAP_TEMPLATE = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
  *{box-sizing:border-box;}
  html,body{margin:0;padding:0;background:#0d0f1a;width:100%;height:100%;overflow:hidden;font-family:sans-serif;}
  #app{width:100%;height:100%;}
  svg{width:100%;height:100%;display:block;cursor:grab;}
  svg.dragging{cursor:grabbing;}
  .nd{cursor:pointer;}
  .nd:hover rect,.nd:hover ellipse{filter:brightness(1.25);}
  .lk{fill:none;}
  text{pointer-events:none;dominant-baseline:middle;}
  #toolbar{position:fixed;top:8px;left:50%;transform:translateX(-50%);display:flex;gap:5px;z-index:20;
    background:rgba(13,15,26,0.92);padding:6px 10px;border-radius:10px;
    border:1px solid rgba(255,255,255,0.1);backdrop-filter:blur(8px);}
  #toolbar button{background:rgba(255,255,255,0.07);color:#c8d4f0;border:1px solid rgba(255,255,255,0.13);
    border-radius:6px;padding:4px 10px;font-size:12px;cursor:pointer;transition:background .15s;}
  #toolbar button:hover{background:rgba(255,255,255,0.18);}
  #search{background:rgba(255,255,255,0.07);color:#c8d4f0;border:1px solid rgba(255,255,255,0.18);
    border-radius:6px;padding:4px 8px;font-size:12px;width:140px;outline:none;}
  #search::placeholder{color:rgba(200,212,240,0.35);}
  #detail{position:fixed;max-width:260px;min-width:180px;
    background:rgba(13,15,26,0.97);border:1px solid rgba(255,255,255,0.18);border-radius:12px;
    padding:12px 14px;color:#c8d4f0;font-size:12px;display:none;z-index:30;line-height:1.6;
    box-shadow:0 4px 24px rgba(0,0,0,0.6);}
  #detail .dtitle{font-weight:bold;font-size:13px;margin-bottom:6px;color:#89b4fa;word-break:break-word;}
  #detail .dbread{font-size:10px;color:rgba(200,212,240,0.45);margin-bottom:6px;}
  #detail .dchildren{margin-top:6px;font-size:11px;color:#a0b0d0;}
  #detail .dchildren div{padding:2px 0;border-top:1px solid rgba(255,255,255,0.06);}
  #detail .dclose{float:right;cursor:pointer;opacity:0.45;font-size:15px;line-height:1;margin-left:6px;}
  #detail .dclose:hover{opacity:1;}
</style></head><body>
<div id="toolbar">
  <input id="search" type="text" placeholder="🔍 Search…" oninput="doSearch(this.value)">
  <button onclick="fitScreen()">⊡ Fit</button>
  <button onclick="expandAll()">+ All</button>
  <button onclick="collapseDeep()">− Deep</button>
  <button onclick="collapseAll()">− All</button>

</div>
<div id="detail">
  <span class="dclose" onclick="closeDetail()">✕</span>
  <div class="dbread" id="det-bread"></div>
  <div class="dtitle" id="det-title"></div>
  <div class="dchildren" id="det-children"></div>
</div>
<div id="app"><svg id="svg"><g id="canvas"></g></svg></div>
<script>
const RAW=__TREE_DATA__;
const TITLE="__TITLE__";

// ── Topic palettes (one per level-1 branch) ─────────────
const PAL=[
  {node:'#1a3560',text:'#89b4fa',edge:'#4a80c8',accent:'#89b4fa'},
  {node:'#1a3d22',text:'#a6e3a1',edge:'#4caf70',accent:'#a6e3a1'},
  {node:'#3d2800',text:'#fab387',edge:'#d07030',accent:'#fab387'},
  {node:'#301a50',text:'#cba6f7',edge:'#8060c0',accent:'#cba6f7'},
  {node:'#3d1020',text:'#f38ba8',edge:'#c04060',accent:'#f38ba8'},
  {node:'#0d3530',text:'#94e2d5',edge:'#30a898',accent:'#94e2d5'},
  {node:'#3d3000',text:'#f9e2af',edge:'#c09030',accent:'#f9e2af'},
];

// ── Stats pattern: numbers with technical units ──────────
const STATS_RE=/\b\d[\d,.]* *(°[CF]|bar|rpm|%|kg|kw|mw|kv|hz|m\/s|cycles?|h\b|hr\b|min\b|ms\b|psi|mpa|kpa|kj|mj|kwh|mwh|°)\b/i;
function isStats(s){return STATS_RE.test(s||'');}

// ── Tree init ────────────────────────────────────────────
let uid=0;
function initTree(n,parent,level,topic){
  n._id=uid++;n._parent=parent;n._level=level;
  n._collapsed=(level>=3);
  n._topic=topic;
  n._detail=n.description||n.detail||n.content||'';
  n.children=(n.children||[]);
  if(level===0) n.children.forEach((c,i)=>initTree(c,n,1,i%PAL.length));
  else          n.children.forEach(c=>initTree(c,n,level+1,topic));
}
initTree(RAW,null,0,0);

// ── Leaf count (for arc allocation) ─────────────────────
function leaves(n){
  if(n._collapsed||!n.children.length) return 1;
  return n.children.reduce((s,c)=>s+leaves(c),0);
}

// ── Horizontal tree layout ───────────────────────────────
const NH=30,VGAP=8,HGAP=44;
let _bx0=0,_bx1=0,_by0=0,_by1=0;

function subtreeH(n){
  if(n._collapsed||!n.children.length) return NH+VGAP;
  return n.children.reduce((s,c)=>s+subtreeH(c),0);
}

function layout(n,x,y0,lv){
  n._lv=lv; n._x=x;
  if(n._collapsed||!n.children.length){n._y=y0;return NH+VGAP;}
  const tot=n.children.reduce((s,c)=>s+subtreeH(c),0);
  let cy=y0;
  n.children.forEach(c=>{layout(c,x+nw(n.name,lv)+HGAP,cy,lv+1);cy+=subtreeH(c);});
  n._y=y0+(tot-NH)/2;
  return tot;
}

function doLayout(){
  layout(RAW,24,24,0);
  const vis=allVis(RAW);
  _bx0=0; _bx1=Math.max(...vis.map(n=>n._x+nw(n.name,n._lv)))+24;
  _by0=0; _by1=Math.max(...vis.map(n=>n._y+NH))+24;
}

function allVis(n){
  let r=[n];
  if(!n._collapsed) n.children.forEach(c=>r=r.concat(allVis(c)));
  return r;
}

// ── Helpers ──────────────────────────────────────────────
function esc(s){return(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function nw(name,lv){return Math.min(200,Math.max(64,(name||'').length*7+(lv===0?28:18)));}
function nh(lv){return lv===0?38:lv===1?32:28;}

let _q='';

// ── Render ───────────────────────────────────────────────
function render(){
  doLayout();
  const vis=allVis(RAW);
  let s='';

  // ── Edges ──
  vis.forEach(n=>{
    if(!n._parent) return;
    const p=n._parent;
    const ECOLS=['#4a80c8','#4caf70','#d07030','#8060c0','#c04060','#30a898'];
    const ec=ECOLS[Math.min(n._lv-1,ECOLS.length-1)];
    const pw=nw(p.name,p._lv);
    const x1=p._x+pw, y1=p._y+NH/2;
    const x2=n._x,    y2=n._y+NH/2;
    const mx=(x1+x2)/2;
    const sw=n._lv<=1?2.5:1.5, op=n._lv<=1?0.7:0.45;
    s+=`<path class="lk" stroke="${ec}" stroke-width="${sw}" opacity="${op}"
      d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}"/>`;
  });

  // ── Nodes ──
  vis.forEach(n=>{
    const w=nw(n.name,n._lv), h=nh(n._lv);
    const x=n._x, y=n._y;
    const stats=isStats(n.name);
    const matched=_q&&(n.name||'').toLowerCase().includes(_q);
    const hasKids=n.children.length>0;

    // Fill / stroke — color by level
    const LCOLS=[
      {fill:'#1e2a4a',text:'#89b4fa',stroke:'#4a80c8'},  // lv0 blue
      {fill:'#1a3d22',text:'#a6e3a1',stroke:'#4caf70'},  // lv1 green
      {fill:'#3d2800',text:'#fab387',stroke:'#d07030'},  // lv2 orange
      {fill:'#301a50',text:'#cba6f7',stroke:'#8060c0'},  // lv3 purple
      {fill:'#3d1020',text:'#f38ba8',stroke:'#c04060'},  // lv4 red
      {fill:'#0d3530',text:'#94e2d5',stroke:'#30a898'},  // lv5 teal
    ];
    const lc=LCOLS[Math.min(n._lv,LCOLS.length-1)];
    let fill=lc.fill,textC=lc.text,strokeC=lc.stroke;
    let strokeW=n._lv===0?2.5:n._lv===1?2:1.2;
    let rx=n._lv===0?16:12;
    if(stats){fill='#332600';textC='#ffd870';strokeC='#c09030';strokeW=2;rx=8;}
    if(matched){fill='#2a1e00';strokeC='#ffd700';strokeW=2.5;textC='#ffd700';}

    const fs=n._lv===0?14:n._lv===1?12:11;
    const fw=n._lv<=1?'bold':'normal';
    const label=esc(n.name||'')+(n._collapsed&&hasKids?' ▸':'');

    s+=`<g class="nd" onclick="nodeClick(${n._id},event)">`;
    s+=`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${fill}" stroke="${strokeC}" stroke-width="${strokeW}"/>`;
    // Stats badge
    if(stats) s+=`<circle cx="${x+w-7}" cy="${y+7}" r="4" fill="#c09030" opacity="0.9"/>`;
    // Detail dot
    if(n._detail) s+=`<circle cx="${x+7}" cy="${y+7}" r="3" fill="${lc.text}" opacity="0.7"/>`;
    s+=`<title>${esc(n.name||'')}${n._detail?'\n\n'+n._detail.slice(0,240):''}</title>`;
    s+=`<text x="${x+w/2}" y="${y+h/2}" text-anchor="middle" fill="${textC}" font-size="${fs}" font-weight="${fw}">${label}</text>`;
    s+=`</g>`;
  });

  document.getElementById('canvas').innerHTML=s;
}

// ── Node click ───────────────────────────────────────────
function nodeClick(id,evt){
  evt.stopPropagation();
  const vis=allVis(RAW);
  const n=vis.find(x=>x._id===id);
  if(!n) return;
  showDetail(n,evt);
  if(n.children.length){n._collapsed=!n._collapsed;render();}
}

function breadcrumb(n){
  const parts=[];
  let cur=n._parent;
  while(cur){parts.unshift(cur.name||'');cur=cur._parent;}
  return parts.join(' › ');
}

function showDetail(n,evt){
  const dlg=document.getElementById('detail');
  document.getElementById('det-title').textContent=n.name||'';
  const bread=breadcrumb(n);
  const breadEl=document.getElementById('det-bread');
  breadEl.textContent=bread; breadEl.style.display=bread?'block':'none';
  const chEl=document.getElementById('det-children');
  if(n.children.length){
    chEl.innerHTML=n.children.map(c=>`<div>▸ ${esc(c.name||'')}</div>`).join('');
    chEl.style.display='block';
  } else {
    chEl.innerHTML=''; chEl.style.display='none';
  }
  // position near click, avoid overflow
  dlg.style.display='block';
  const sw=window.innerWidth, sh=window.innerHeight;
  const dw=dlg.offsetWidth||260, dh=dlg.offsetHeight||120;
  let px=evt.clientX+14, py=evt.clientY-20;
  if(px+dw>sw-8) px=evt.clientX-dw-14;
  if(py+dh>sh-8) py=sh-dh-8;
  if(py<8) py=8;
  dlg.style.left=px+'px'; dlg.style.top=py+'px';
}
function closeDetail(){document.getElementById('detail').style.display='none';}

// ── Search ───────────────────────────────────────────────
function doSearch(val){
  _q=val.trim().toLowerCase();
  if(_q) expandForSearch(RAW,_q);
  render();
}
function expandForSearch(n,q){
  const mine=(n.name||'').toLowerCase().includes(q);
  const childHit=n.children.some(c=>expandForSearch(c,q));
  if(childHit) n._collapsed=false;
  return mine||childHit;
}

// ── Expand / Collapse ────────────────────────────────────
function setAll(n,v){n._collapsed=v;n.children.forEach(c=>setAll(c,v));}
function expandAll(){setAll(RAW,false);render();fitScreen();}
function collapseAll(){RAW.children.forEach(c=>setAll(c,true));render();fitScreen();}
function collapseDeep(){collapseLevel(RAW,2);render();fitScreen();}
function collapseLevel(n,max){n._collapsed=(n._lv>=max);n.children.forEach(c=>collapseLevel(c,max));}

// ── Zoom & Pan ───────────────────────────────────────────
const svg=document.getElementById('svg');
const canvas=document.getElementById('canvas');
let vx=0,vy=0,vs=1;
function applyT(){canvas.setAttribute('transform',`translate(${vx},${vy}) scale(${vs})`);}
function fitScreen(){
  const sw=svg.clientWidth,sh=svg.clientHeight;
  const cw=_bx1-_bx0,ch=_by1-_by0;
  if(cw<=0||ch<=0) return;
  vs=Math.min(sw/cw,sh/ch)*0.88;
  vx=sw/2-(_bx0+cw/2)*vs; vy=sh/2-(_by0+ch/2)*vs;
  applyT();
}
svg.addEventListener('wheel',e=>{
  e.preventDefault();
  const r=svg.getBoundingClientRect();
  const mx=e.clientX-r.left,my=e.clientY-r.top;
  const f=e.deltaY<0?1.12:0.89;
  const ns=Math.min(6,Math.max(0.08,vs*f));
  vx=mx-(mx-vx)*(ns/vs); vy=my-(my-vy)*(ns/vs); vs=ns; applyT();
},{passive:false});
let drag=false,ddx=0,ddy=0;
svg.addEventListener('mousedown',e=>{
  if(e.target.closest('.nd')) return;
  drag=true; ddx=e.clientX-vx; ddy=e.clientY-vy; svg.classList.add('dragging');
});
window.addEventListener('mousemove',e=>{if(!drag)return;vx=e.clientX-ddx;vy=e.clientY-ddy;applyT();});
window.addEventListener('mouseup',()=>{drag=false;svg.classList.remove('dragging');});
svg.addEventListener('click',()=>closeDetail());



// ── Keyboard shortcuts ───────────────────────────────────
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){closeDetail();document.getElementById('search').value='';doSearch('');}
  if(e.key==='f'&&!e.ctrlKey&&!e.metaKey) fitScreen();
});

// ── Init ─────────────────────────────────────────────────
render();
setTimeout(fitScreen,80);
</script></body></html>"""


def _mindmap_to_html(node: dict, title: str = "") -> str:
    """Convert mind map tree dict → self-contained SVG mind map HTML."""
    import json
    return (_MINDMAP_TEMPLATE
            .replace("__TITLE__", title)
            .replace("__TREE_DATA__", json.dumps(node, ensure_ascii=False)))


class MindMapWorker(QThread):
    """Upload file → generate_mind_map() → render HTML → delete source."""
    done  = Signal(str)   # HTML content
    error = Signal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            import os
            async def _work():
                async with await NotebookLMClient.from_storage() as client:
                    # Use a dedicated temp notebook so only this file is in scope
                    title = os.path.basename(self.file_path)
                    nb = await client.notebooks.create(title=f"[MindMap] {title}")
                    nb_id = getattr(nb, "id", None) or getattr(nb, "notebook_id", "")
                    try:
                        source = await client.sources.add_file(nb_id, Path(self.file_path), wait=True)
                        result = await client.artifacts.generate_mind_map(nb_id)
                        # result contains the mind_map tree directly
                        if isinstance(result, dict):
                            tree = result.get("mind_map") or result
                        else:
                            raw = getattr(result, "mind_map", None)
                            tree = raw if isinstance(raw, dict) else vars(result) if hasattr(result, "__dict__") else {"name": str(result)}
                        return _mindmap_to_html(tree, title)
                    finally:
                        # Always clean up the temp notebook
                        try:
                            await client.notebooks.delete(nb_id)
                        except Exception:
                            pass
            html = _run_async(_work())
            self.done.emit(html)
        except Exception as e:
            self.error.emit(str(e))


class NLMSummarizeWorker(QThread):
    """Upload file → chat.ask(summarize) → delete source."""
    done  = Signal(str)
    error = Signal(str)

    def __init__(self, notebook_id: str, file_path: str):
        super().__init__()
        self.notebook_id = notebook_id
        self.file_path   = file_path

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _work():
                async with await NotebookLMClient.from_storage() as client:
                    source = await client.sources.add_file(
                        self.notebook_id, Path(self.file_path), wait=True
                    )
                    sid = getattr(source, "source_id", None) or getattr(source, "id", None)
                    result = await client.chat.ask(
                        self.notebook_id,
                        _SUMMARIZE_PROMPT,
                        source_ids=[sid],
                    )
                    await client.sources.delete(self.notebook_id, sid)
                    return getattr(result, "answer", None) or str(result)
            text = _run_async(_work())
            self.done.emit(text)
        except Exception as e:
            self.error.emit(str(e))



class ChatWorker(QThread):
    done  = Signal(str, list)   # answer, deduplicated citations
    error = Signal(str)

    def __init__(self, notebook_id: str, question: str):
        super().__init__()
        self.notebook_id = notebook_id
        self.question    = question

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _chat():
                async with await NotebookLMClient.from_storage() as client:
                    result = await client.chat.ask(self.notebook_id, self.question)
                    # Build source_id → title map
                    src_map = {}
                    try:
                        sources = await client.sources.list(self.notebook_id)
                        for s in sources:
                            sid   = getattr(s, "source_id", None) or getattr(s, "id", "")
                            title = getattr(s, "title", None) or getattr(s, "name", "") or ""
                            if sid:
                                src_map[sid] = title
                    except Exception:
                        pass
                    return result, src_map
            result, src_map = _run_async(_chat())
            text = getattr(result, "answer", None) or getattr(result, "message", None) or getattr(result, "text", None) or str(result)

            seen, citations = set(), []
            for c in (getattr(result, "references", None) or []):
                quote  = (getattr(c, "cited_text", None) or "").strip()
                src_id = getattr(c, "source_id", "") or ""
                if quote and quote not in seen:
                    seen.add(quote)
                    citations.append({"text": quote, "source": src_map.get(src_id, "")})

            self.done.emit(text, citations)
        except Exception as e:
            self.error.emit(str(e))


class PageFindWorker(QThread):
    """Runs _find_page_for_citation in background; emits found(page) when done."""
    found = Signal(int)   # page index (0-based)

    def __init__(self, pdf_path: str, cited_text: str):
        super().__init__()
        self.pdf_path   = pdf_path
        self.cited_text = cited_text

    def run(self):
        import re
        try:
            import fitz
            doc = fitz.open(self.pdf_path)
            # Pass 1: exact snippet (shrinking)
            for length in (60, 40, 20):
                snippet = self.cited_text[:length].strip()
                if len(snippet) < 8:
                    continue
                for i in range(len(doc)):
                    if doc[i].search_for(snippet):
                        doc.close()
                        self.found.emit(i)
                        return
            # Pass 2: uppercase keyword matching
            keywords = list(dict.fromkeys(
                re.findall(r'\b[A-Z][A-Z0-9_\-]{3,}\b', self.cited_text)))[:8]
            if keywords:
                best_page, best_score = None, 0
                for i in range(len(doc)):
                    score = sum(1 for k in keywords if k in doc[i].get_text())
                    if score > best_score:
                        best_score, best_page = score, i
                if best_score >= 3:
                    doc.close()
                    self.found.emit(best_page)
                    return
            doc.close()
        except Exception:
            pass
        # Not found — do not emit (preview stays at page 0)


# ── Notebook Picker Dialog (used from external windows) ──────────

class NLMNotebookPickerDialog(QDialog):
    """Show list of notebooks, return selected notebook_id."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Notebook")
        self.setFixedSize(360, 280)
        self.selected_id = None

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Select a notebook to summarize into:"))

        self.lst = QListWidget()
        lay.addWidget(self.lst, 1)

        btns = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setFixedHeight(32)
        ok_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(32)
        cancel_btn.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        lay.addLayout(btns)

        self._load()

    def _load(self):
        self.lst.addItem(QListWidgetItem("⏳ Loading…"))
        w = ListNotebooksWorker()
        w.done.connect(self._on_loaded)
        w.error.connect(lambda e: (self.lst.clear(), self.lst.addItem(f"Error: {e}")))
        self._worker = w
        w.start()

    def _on_loaded(self, notebooks):
        self.lst.clear()
        for nb in notebooks:
            title = getattr(nb, "title", None) or getattr(nb, "name", str(nb))
            nb_id = getattr(nb, "id", None) or getattr(nb, "notebook_id", "")
            item  = QListWidgetItem(f"📓 {title}")
            item.setData(Qt.UserRole, nb_id)
            self.lst.addItem(item)
        if self.lst.count():
            self.lst.setCurrentRow(0)

    def _accept(self):
        item = self.lst.currentItem()
        if item:
            self.selected_id = item.data(Qt.UserRole)
            self.accept()

    @staticmethod
    def pick(parent=None) -> str | None:
        if not is_nlm_logged_in():
            QMessageBox.warning(
                parent, "Not Logged In",
                "Please log in to NotebookLM first.\n\nGo to the 📓 NotebookLM tab and click 🔑 Login Google."
            )
            return None
        dlg = NLMNotebookPickerDialog(parent)
        if dlg.exec() == QDialog.Accepted:
            return dlg.selected_id
        return None


# ── Chat display with clickable source links ─────────────────────

class ChatDisplay(QTextEdit):
    link_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)

    def mousePressEvent(self, e):
        anchor = self.anchorAt(e.pos())
        if anchor and anchor.startswith("nlm://"):
            self.link_clicked.emit(anchor)
        else:
            super().mousePressEvent(e)


# ── Embedded Widget ───────────────────────────────────────────────

class NotebookLMWidget(QWidget):
    """Embedded widget — dùng trong tab hoặc dialog."""
    open_preview    = Signal(str, object)  # file_path, page_num (int or None)
    goto_page_signal = Signal(int)          # jump to page after background search

    def __init__(self, parent=None):
        super().__init__(parent)
        self._citation_refs: list = []

        self._current_notebook_id = None
        self._workers = []
        self._thinking_step = 0
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(500)
        self._thinking_timer.timeout.connect(self._tick_thinking)

        self._setup_ui()

        # Auto-load nếu đã có session
        if is_nlm_logged_in():
            self.lbl_status.setText("🟢 Logged in")
            self._load_notebooks()
        else:
            self.lbl_status.setText("⚪ Not logged in")

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(8, 8, 8, 8)

        # ── Header: Login + status ────────────────────────────────
        header = QHBoxLayout()
        self.lbl_status = QLabel("⚪ Not logged in")
        self.lbl_status.setStyleSheet("font-size: 12px; color: #a6adc8;")
        self.lbl_status.setMaximumWidth(320)
        self.btn_login = QPushButton("🔑 Switch Account")
        self.btn_login.setFixedHeight(32)
        self.btn_login.clicked.connect(self._login)
        self.btn_save_login = QPushButton("✅ Save Login")
        self.btn_save_login.setFixedHeight(32)
        self.btn_save_login.setEnabled(False)
        self.btn_save_login.setToolTip("Click after you have finished logging in on the browser")
        self.btn_save_login.clicked.connect(self._save_login)
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.clicked.connect(self._load_notebooks)
        header.addWidget(self.lbl_status)
        header.addStretch()
        header.addWidget(self.btn_login)
        header.addWidget(self.btn_save_login)
        header.addWidget(self.btn_refresh)
        lay.addLayout(header)

        # ── Splitter: notebooks list | main panel ─────────────────
        splitter = QSplitter(Qt.Horizontal)

        # Left: notebook list
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(6)

        lbl_nb = QLabel("📓 Notebooks")
        lbl_nb.setStyleSheet("font-weight: bold; font-size: 13px;")
        left_lay.addWidget(lbl_nb)

        self.lst_notebooks = QListWidget()
        self.lst_notebooks.currentItemChanged.connect(self._on_notebook_selected)
        self.lst_notebooks.setStyleSheet("QListWidget { font-size: 16px; font-weight: bold; } QListWidget::item { padding: 6px 4px; }")
        self.lst_notebooks.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lst_notebooks.customContextMenuRequested.connect(self._nb_context_menu)
        left_lay.addWidget(self.lst_notebooks, 1)

        nb_btn_row = QHBoxLayout()
        nb_btn_row.setSpacing(4)
        self.btn_new_nb = QPushButton("➕ New")
        self.btn_new_nb.setFixedHeight(34)
        self.btn_new_nb.clicked.connect(self._create_notebook)
        self.btn_del_nb = QPushButton("🗑 Delete")
        self.btn_del_nb.setFixedHeight(34)
        self.btn_del_nb.setEnabled(False)
        self.btn_del_nb.clicked.connect(self._delete_notebook)
        nb_btn_row.addWidget(self.btn_new_nb)
        nb_btn_row.addWidget(self.btn_del_nb)
        left_lay.addLayout(nb_btn_row)

        splitter.addWidget(left)

        # Right: tabs
        right = QTabWidget()

        # Tab 1: Chat
        chat_widget = QWidget()
        chat_lay = QVBoxLayout(chat_widget)
        chat_lay.setSpacing(6)

        self.lbl_nb_name = QLabel("Select a notebook →")
        self.lbl_nb_name.setStyleSheet("font-size: 13px; font-weight: bold; color: #89b4fa;")
        chat_lay.addWidget(self.lbl_nb_name)

        self.chat_display = ChatDisplay()
        self.chat_display.setPlaceholderText("Chat history will appear here…")
        self.chat_display.setStyleSheet("font-size: 18px;")
        self.chat_display.link_clicked.connect(self._on_source_link_clicked)
        chat_lay.addWidget(self.chat_display, 1)

        self.lbl_thinking = QLabel("")
        self.lbl_thinking.setStyleSheet("font-size: 14px; color: #89b4fa; padding: 2px 4px;")
        self.lbl_thinking.setVisible(False)
        chat_lay.addWidget(self.lbl_thinking)

        input_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask a question about your documents…")
        self.chat_input.setFixedHeight(36)
        self.chat_input.returnPressed.connect(self._send_chat)
        self.btn_send = QPushButton("Send ➤")
        self.btn_send.setFixedHeight(36)
        self.btn_send.setEnabled(False)
        self.btn_send.clicked.connect(self._send_chat)
        input_row.addWidget(self.chat_input, 1)
        input_row.addWidget(self.btn_send)
        chat_lay.addLayout(input_row)

        right.addTab(chat_widget, "💬 Chat")

        # Tab 2: Sources
        src_widget = QWidget()
        src_lay = QVBoxLayout(src_widget)
        src_lay.setSpacing(6)

        src_lay.addWidget(QLabel("Files added to this notebook:"))
        self.lst_sources = QListWidget()
        self.lst_sources.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lst_sources.customContextMenuRequested.connect(self._show_source_context_menu)
        src_lay.addWidget(self.lst_sources, 1)

        src_btn_row = QHBoxLayout()
        self.btn_add_file = QPushButton("📄 Add File")
        self.btn_add_file.setFixedHeight(30)
        self.btn_add_file.setEnabled(False)
        self.btn_add_file.clicked.connect(self._add_file)
        src_btn_row.addWidget(self.btn_add_file)
        src_btn_row.addStretch()
        src_lay.addLayout(src_btn_row)

        right.addTab(src_widget, "📎 Sources")

        splitter.addWidget(right)
        splitter.setSizes([240, 760])

        lay.addWidget(splitter, 1)

    # ── Auth ─────────────────────────────────────────────────────

    def _login(self):
        self.btn_login.setEnabled(False)
        self.lbl_status.setText("🔄 Opening browser for login…")
        self._login_worker = LoginWorker()
        self._login_worker.done.connect(self._on_login_done)
        self._login_worker.error.connect(self._on_login_error)
        self._workers.append(self._login_worker)
        self._login_worker.start()
        self.btn_save_login.setEnabled(True)

    def _save_login(self):
        if hasattr(self, "_login_worker"):
            self._login_worker.confirm()
        self.btn_save_login.setEnabled(False)
        self.lbl_status.setText("🔄 Saving login…")

    def _on_login_done(self):
        self.lbl_status.setText("🟢 Logged in")
        self.btn_login.setEnabled(True)
        self._load_notebooks()

    def _on_login_error(self, msg: str):
        self.lbl_status.setText("🔴 Login failed")
        self.btn_login.setEnabled(True)
        QMessageBox.critical(self, "Login Error", msg)

    # ── Notebooks ─────────────────────────────────────────────────

    def _load_notebooks(self):
        self.lbl_status.setText("🔄 Loading notebooks…")
        w = ListNotebooksWorker()
        w.done.connect(self._on_notebooks_loaded)
        w.error.connect(lambda e: (
            self.lbl_status.setText("🔴 Auth expired — click Switch Account"),
            self.lbl_status.setToolTip(e),
        ))
        self._workers.append(w)
        w.start()

    @staticmethod
    def _notebook_emoji(title: str) -> str:
        t = title.lower()
        if any(k in t for k in ("boiler", "lo hoi", "steam", "furnace", "burner")): return "🔥"
        if any(k in t for k in ("turbine", "generator", "rotor")): return "⚙️"
        if any(k in t for k in ("electric", "dien", "điện", "power")): return "⚡"
        if any(k in t for k in ("pump", "bom", "bơm", "valve", "van")): return "🔧"
        if any(k in t for k in ("safety", "an toan", "an toàn", "hazard", "alarm")): return "⚠️"
        if any(k in t for k in ("chemistry", "water", "nuoc", "nước", "chemical")): return "💧"
        if any(k in t for k in ("procedure", "sop", "operation", "quy trinh", "quy trình")): return "📋"
        if any(k in t for k in ("drawing", "ban ve", "bản vẽ", "piping", "diagram")): return "📐"
        if any(k in t for k in ("report", "bao cao", "báo cáo", "summary")): return "📊"
        if any(k in t for k in ("training", "huan luyen", "huấn luyện", "course")): return "🎓"
        return "📓"

    def _on_notebooks_loaded(self, notebooks):
        self.lst_notebooks.clear()
        for nb in notebooks:
            title = getattr(nb, "title", None) or getattr(nb, "name", str(nb))
            nb_id  = getattr(nb, "id", None) or getattr(nb, "notebook_id", "")
            emoji = self._notebook_emoji(title)
            item = QListWidgetItem(f"{emoji}  {title}")
            item.setData(Qt.UserRole, nb_id)
            self.lst_notebooks.addItem(item)
        self.lbl_status.setText(f"🟢 {len(notebooks)} notebook(s) loaded")

    def _create_notebook(self):
        from PySide6.QtWidgets import QInputDialog
        title, ok = QInputDialog.getText(self, "New Notebook", "Notebook title:")
        if not ok or not title.strip():
            return
        w = CreateNotebookWorker(title.strip())
        w.done.connect(lambda nb: self._load_notebooks())
        w.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
        self._workers.append(w)
        w.start()

    def _nb_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        item = self.lst_notebooks.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        act_rename = menu.addAction("✏️ Rename")
        act_delete = menu.addAction("🗑 Delete")
        action = menu.exec(self.lst_notebooks.mapToGlobal(pos))
        if action == act_rename:
            self._rename_notebook(item)
        elif action == act_delete:
            self._delete_notebook()

    def _rename_notebook(self, item):
        from PySide6.QtWidgets import QInputDialog
        nb_id = item.data(Qt.UserRole)
        old_title = item.text().split("  ", 1)[-1]  # bỏ emoji prefix
        new_title, ok = QInputDialog.getText(
            self, "Rename Notebook", "New name:", text=old_title
        )
        if not ok or not new_title.strip() or new_title.strip() == old_title:
            return
        w = RenameNotebookWorker(nb_id, new_title.strip())
        w.done.connect(lambda t: self._load_notebooks())
        w.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
        self._workers.append(w)
        w.start()

    def _delete_notebook(self):
        item = self.lst_notebooks.currentItem()
        if not item:
            return
        title = item.text()
        nb_id = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "Delete Notebook",
            f"Delete \"{title}\"?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.btn_del_nb.setEnabled(False)
        w = DeleteNotebookWorker(nb_id)
        w.done.connect(lambda: self._load_notebooks())
        w.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
        self._workers.append(w)
        w.start()

    def _on_notebook_selected(self, current, _prev):
        if not current:
            self.btn_del_nb.setEnabled(False)
            return
        self._current_notebook_id = current.data(Qt.UserRole)
        self.lbl_nb_name.setText(f"📓 {current.text()}")
        self.btn_del_nb.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.btn_add_file.setEnabled(True)
        self.chat_display.clear()
        self._load_sources()

    def _load_sources(self):
        if not self._current_notebook_id:
            return
        self.lst_sources.clear()
        self.lst_sources.addItem("⏳ Loading…")
        w = ListSourcesWorker(self._current_notebook_id)
        w.done.connect(self._on_sources_loaded)
        w.error.connect(lambda e: (self.lst_sources.clear(), self.lst_sources.addItem(f"Error: {e}")))
        self._workers.append(w)
        w.start()

    def _on_sources_loaded(self, sources):
        self.lst_sources.clear()
        if not sources:
            self.lst_sources.addItem("(no sources)")
            return
        for s in sources:
            title = getattr(s, "title", None) or getattr(s, "name", None) or str(s)
            sid   = getattr(s, "source_id", None) or getattr(s, "id", None) or ""
            item  = QListWidgetItem(f"📄 {title}")
            item.setData(Qt.UserRole, sid)   # lưu source_id
            self.lst_sources.addItem(item)

    def _show_source_context_menu(self, pos):
        item = self.lst_sources.itemAt(pos)
        if not item:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction("🗑 Delete Source").triggered.connect(
            lambda: self._delete_source(item)
        )
        menu.exec(self.lst_sources.mapToGlobal(pos))

    def _delete_source(self, item):
        from PySide6.QtWidgets import QMessageBox
        title = item.text().lstrip("📄 ").strip()
        sid   = item.data(Qt.UserRole)
        if not sid:
            QMessageBox.warning(self, "Error", "Cannot delete: source ID not found.")
            return
        reply = QMessageBox.question(self, "Delete Source",
            f'Delete "{title}" from this notebook?',
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        w = DeleteSourceWorker(self._current_notebook_id, sid)
        w.done.connect(lambda: self._load_sources())
        w.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
        self._workers.append(w)
        w.start()

    # ── Chat ──────────────────────────────────────────────────────

    def _start_thinking(self):
        self._thinking_step = 0
        self.lbl_thinking.setVisible(True)
        self._thinking_timer.start()

    def _stop_thinking(self):
        self._thinking_timer.stop()
        self.lbl_thinking.setVisible(False)

    def _tick_thinking(self):
        frames = ["🤔 Thinking", "🤔 Thinking·", "🤔 Thinking··", "🤔 Thinking···"]
        self.lbl_thinking.setText(frames[self._thinking_step % len(frames)])
        self._thinking_step += 1

    def _send_chat(self):
        if not self._current_notebook_id:
            return
        question = self.chat_input.text().strip()
        if not question:
            return
        self.chat_display.append(f"<b style='color:#89b4fa'>You:</b> {question}")
        self.chat_input.clear()
        self.btn_send.setEnabled(False)
        self._start_thinking()

        w = ChatWorker(self._current_notebook_id, question)
        w.done.connect(self._on_chat_done)
        w.error.connect(self._on_chat_error)
        self._workers.append(w)
        w.start()

    def _on_chat_done(self, text: str, citations: list):
        self._stop_thinking()
        self._citation_refs = citations
        html = self._md_to_html(text)
        self.chat_display.append(f"<b style='color:#a6e3a1'>Mr Finder:</b><br>{html}")
        if citations:
            parts = []
            for i, c in enumerate(citations, 1):
                quote  = c.get("text", "")
                source = c.get("source", "")
                short  = quote[:150] + ("…" if len(quote) > 150 else "")
                src_html = (
                    f" <a href='nlm://{i-1}' style='color:#1d4ed8;text-decoration:underline'>{source}</a>"
                    if source else ""
                )
                parts.append(
                    f"<span style='color:#15803d'>[{i}]{src_html}</span>"
                    f" <i style='color:#374151'>\"{short}\"</i>"
                )
            self.chat_display.append(
                "<span style='font-size:15px;color:#b45309'>──────────────── Sources ────────────────</span><br>"
                + "<br>".join(parts)
            )
        self.chat_display.append("<br>")
        self.btn_send.setEnabled(True)

    def _on_source_link_clicked(self, href: str):
        try:
            idx = int(href.replace("nlm://", ""))
            c = self._citation_refs[idx]
            source     = c.get("source", "")
            cited_text = c.get("text", "")
        except Exception:
            return

        # Tìm trong source map
        local_path = _lookup_source_path(source)

        if not local_path:
            from PySide6.QtWidgets import QFileDialog, QMessageBox
            answer = QMessageBox.question(self, "File not found",
                f'"{source}" not in local map.\nLocate the file manually?',
                QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
            local_path, _ = QFileDialog.getOpenFileName(
                self, f"Locate: {source}", "", "PDF Files (*.pdf)")
            if not local_path:
                return
            _upsert_source_map(source, local_path, self._current_notebook_id or "")

        if not local_path.lower().endswith(".pdf"):
            return
        # Open preview immediately (no lag), then find the right page in background
        self.open_preview.emit(local_path, None)
        if cited_text.strip():
            worker = PageFindWorker(local_path, cited_text)
            worker.found.connect(self.goto_page_signal)
            worker.finished.connect(worker.deleteLater)
            # Keep a reference so GC doesn't collect it before it finishes
            if not hasattr(self, "_page_find_workers"):
                self._page_find_workers = []
            self._page_find_workers.append(worker)
            worker.finished.connect(lambda: self._page_find_workers.remove(worker)
                                    if worker in self._page_find_workers else None)
            worker.start()

    _LATEX_MAP = {
        r"\rightarrow": "→", r"\leftarrow": "←",
        r"\Rightarrow": "⇒", r"\Leftarrow": "⇐",
        r"\leftrightarrow": "↔", r"\Leftrightarrow": "⇔",
        r"\leq": "≤", r"\geq": "≥", r"\neq": "≠",
        r"\approx": "≈", r"\times": "×", r"\div": "÷",
        r"\pm": "±", r"\infty": "∞", r"\cdot": "·",
        r"\alpha": "α", r"\beta": "β", r"\gamma": "γ",
        r"\delta": "δ", r"\Delta": "Δ", r"\mu": "μ",
        r"\pi": "π", r"\sigma": "σ", r"\theta": "θ",
        r"\sum": "∑", r"\prod": "∏", r"\int": "∫",
        r"\sqrt": "√", r"\partial": "∂",
    }

    @staticmethod
    def _replace_latex(text: str) -> str:
        import re
        def _sub(m):
            inner = m.group(1).strip()
            for sym, uni in NotebookLMWidget._LATEX_MAP.items():
                inner = inner.replace(sym, uni)
            # nếu còn lại chỉ là text thuần → trả về text không có $
            return inner
        return re.sub(r"\$([^$]+)\$", _sub, text)

    @staticmethod
    def _md_to_html(text: str) -> str:
        """Convert basic markdown to HTML for display."""
        import re
        text = NotebookLMWidget._replace_latex(text)
        lines = text.split("\n")
        out = []
        for line in lines:
            # Headers
            if line.startswith("### "):
                out.append(f"<b style='font-size:18px;color:#6c27b0'>{line[4:]}</b>")
            elif line.startswith("## "):
                out.append(f"<b style='font-size:18px;color:#1565c0'>{line[3:]}</b>")
            elif line.startswith("# "):
                out.append(f"<b style='font-size:18px;color:#0d47a1'>{line[2:]}</b>")
            elif line.startswith("- ") or line.startswith("* "):
                out.append(f"&nbsp;&nbsp;• {line[2:]}")
            elif line.strip() == "":
                out.append("<br>")
            else:
                out.append(line)
        result = "<br>".join(out)
        # Bold **text**
        result = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", result)
        # Italic *text*
        result = re.sub(r"\*(.+?)\*", r"<i>\1</i>", result)
        return result

    def _on_chat_error(self, msg: str):
        self._stop_thinking()
        self.chat_display.append(f"<b style='color:#f38ba8'>Error:</b> {msg}")
        self.btn_send.setEnabled(True)

    # ── Sources ───────────────────────────────────────────────────

    def _add_file(self):
        if not self._current_notebook_id:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select File", "",
            "Documents (*.pdf *.txt *.doc *.docx *.pptx *.md)"
        )
        if not path:
            return
        # Kiểm tra trùng với danh sách source đang hiển thị
        fname = os.path.basename(path).strip().lower()
        existing = []
        for i in range(self.lst_sources.count()):
            t = self.lst_sources.item(i).text().lstrip("📄 ").strip().lower()
            existing.append(t)
        if fname in existing:
            QMessageBox.warning(self, "Duplicate File",
                f'"{os.path.basename(path)}" already exists in this notebook.')
            return
        self.btn_add_file.setEnabled(False)
        w = AddSourceWorker(self._current_notebook_id, path)
        w.done.connect(self._on_source_added)
        w.error.connect(lambda e: (
            QMessageBox.critical(self, "Error", e),
            self.btn_add_file.setEnabled(True),
        ))
        self._workers.append(w)
        w.start()

    def _on_source_added(self):
        self.btn_add_file.setEnabled(True)
        self._load_sources()  # reload danh sách thực tế


# ── Dialog wrapper (backward compat) ─────────────────────────────

class NotebookLMWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NotebookLM")
        self.resize(1000, 680)
        self.setModal(False)
        self.setStyleSheet("QDialog { background: #1e2030; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(NotebookLMWidget(self))

        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )
