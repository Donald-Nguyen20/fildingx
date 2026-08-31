# -*- coding: utf-8 -*-
"""
Bo doc 1 sheet DAY DU tu UCS.db de ve TRUNG THUC nhu UCS.pdf.
Vi tri/ten chan lay tu DINH NGHIA MACRO (DEF/MCR/MacroDef.db + SVG) qua
macro_pins.json: pin = goc khoi + offset macro; khung khoi = SYMBOLAREA.
"""
from __future__ import annotations
import os, json, re
from collections import defaultdict
from . import dbreader as D
from .model import _manual_terms

TERM_CODE = "E0B1"
_MPINS = None


def _macro_pins():
    global _MPINS
    if _MPINS is None:
        p = os.path.join(os.path.dirname(__file__), "macro_pins.json")
        try:
            _MPINS = json.load(open(p, encoding="utf-8"))
        except Exception:
            _MPINS = {}
    return _MPINS


def _pad(v):
    """So loop-sheet dang 5 chu so co so 0 dau (vd 8739 -> 08739)."""
    if v is None:
        return ""
    st = str(v).strip()
    return st.zfill(5) if st.isdigit() else st


class SBlock:
    def __init__(self):
        self.bid = None
        self.code = ""
        self.name = ""
        self.x = 0.0
        self.y = 0.0
        self.exorder = -1
        self.n_in = 0
        self.n_out = 0
        self.in_names = []
        self.out_names = []
        self.label = ""
        self.params = []
        self.tag = ""
        self.tdes = ""
        self.sym = ""          # ten SYMBOL (de tim file SVG)
        self.parammap = {}      # {paramno:int -> gia tri} de dat dung o placeholder
        self.pins = []          # [(x, y, is_out, name, connected)] toa do DB
        self.box = None         # (x_left, y_bot, x_right, y_top)


class STerm:
    def __init__(self):
        self.side = "L"
        self.x = 0.0
        self.y = 0.0
        self.linename = ""
        self.ref = ""
        self.lid = ""
        self.targets = []
        self.refs = []
        self.xcpu = None   # so CPU doi tac neu la terminal lien-CPU (C-NET)


class SWire:
    def __init__(self, signalid):
        self.signalid = signalid
        self.polylines = []


class SText:
    def __init__(self, x, y, s):
        self.x = x; self.y = y; self.s = s


class Sheet:
    def __init__(self):
        self.id = None
        self.title = ""
        self.pa = ""
        self.sheetno = ""
        self.drawno = ""
        self.loopno = ""       # so loop (CAD_DATA.LOOPNO), da zfill(3), vd "011"
        self.loopno_raw = ""   # so loop KHONG zfill (dung de khop dung cot ben trai)
        self.loopsheetno = ""  # so sheet trong loop (CAD_DATA.SHEETNO), vd "80"
        self.comment1 = ""     # CAD_DATA.COMMENT1 - ten sheet hien o cot ben trai
        self.cpuno = None      # CAD_CPU.CPUNO - de hien "CPUx  ten" truoc tieu de sheet
        self.cpuname = ""      # CAD_CPU.CPUNAME
        self.blocks = []
        self.terms = []
        self.wires = []
        self.texts = []
        self.xmin = self.xmax = self.ymin = self.ymax = 0.0


def build_sheet(path, sheet_id):
    c = D.connect(path).cursor()
    R = D._resolvers(path)
    mterms = _manual_terms()
    MP = _macro_pins()
    sh = Sheet()
    sh.id = sheet_id
    meta = c.execute(
        "SELECT PANO,PASHEETNO,SHEETNAME,DRAWNO,LOOPNO,SHEETNO,COMMENT1 FROM CAD_DATA WHERE ID=?",
        (sheet_id,)).fetchone()
    if meta:
        sh.pa, sh.sheetno, sh.title, sh.drawno = (D._clean(x) for x in meta[:4])
        loopno, loopsheetno = meta[4], meta[5]
        sh.loopno = str(loopno).zfill(3) if loopno is not None else ""
        sh.loopno_raw = str(loopno) if loopno is not None else ""
        sh.loopsheetno = str(loopsheetno) if loopsheetno is not None else ""
        sh.comment1 = D._clean(meta[6]) if len(meta) > 6 else ""
    try:
        cpu = c.execute("SELECT CPUNO,CPUNAME FROM CAD_CPU").fetchone()
        if cpu:
            sh.cpuno, sh.cpuname = cpu[0], D._clean(cpu[1])
    except Exception:
        pass
    _mtitle = re.search(r"CPU0*(\d+)", sh.title or "")
    sheet_partner = int(_mtitle.group(1)) if (_mtitle and re.match(r"\s*(FROM|TO)\s+CPU", sh.title or "", re.I)) else None

    rows = list(c.execute(
        "SELECT BLOCK_ID,SYMBOL,MACROCODE,X,Y,EXEORDER FROM CAD_BLOCK WHERE ID=? ORDER BY BLOCK_ID", (sheet_id,)))
    if not rows:
        raise ValueError("Sheet %s khong co khoi." % sheet_id)

    pin1 = {}
    pins_all = defaultdict(list)
    for bid, pn, sig in c.execute(
            "SELECT BLOCK_ID,PINNO,SIGNALID FROM CAD_BLOCK_PIN WHERE BLOCK_ID IN "
            "(SELECT BLOCK_ID FROM CAD_BLOCK WHERE ID=?) ORDER BY PINNO", (sheet_id,)):
        sig = D._clean(sig)
        pin1.setdefault(bid, sig)
        pins_all[bid].append((pn, sig))

    # diem cuoi moi net (chi dung cho fallback khi thieu dinh nghia macro)
    net_ends = defaultdict(list)
    for lid, sig in c.execute("SELECT LINE_ID,SIGNALID FROM CAD_LIN WHERE ID=?", (sheet_id,)).fetchall():
        sig = D._clean(sig)
        det = c.execute(
            "SELECT GROUPNO,X,Y FROM CAD_LIN_DETAIL WHERE LINE_ID=? ORDER BY GROUPNO,VERTEXNO", (lid,)).fetchall()
        curg = None; first = None; last = None
        for g, x, y in det:
            if g != curg:
                if first is not None:
                    net_ends[sig].append(first); net_ends[sig].append(last)
                curg = g; first = (float(x), float(y))
            last = (float(x), float(y))
        if first is not None:
            net_ends[sig].append(first); net_ends[sig].append(last)

    params = defaultdict(dict)
    for bid, pno, val in c.execute(
            "SELECT BLOCK_ID,PARAMNO,PARAMVALUE FROM CAD_BLOCK_PARAM WHERE BLOCK_ID IN "
            "(SELECT BLOCK_ID FROM CAD_BLOCK WHERE ID=?)", (sheet_id,)):
        params[bid][str(pno)] = D._clean(val)

    tag_of, tdes_of = {}, {}
    for bid, suf, val in c.execute(
            "SELECT BLOCK_ID,FIDSUFFIX,FIDVALUE FROM CAD_TAG_FID WHERE BLOCK_ID IN "
            "(SELECT BLOCK_ID FROM CAD_BLOCK WHERE ID=?)", (sheet_id,)):
        suf, val = D._clean(suf), D._clean(val)
        if not val:
            continue
        if suf == "Ttag":
            tag_of.setdefault(bid, val)
        elif suf == "TDes1":
            tdes_of.setdefault(bid, val)

    xs, ys, logic_x = [], [], []
    for bid, sym, code, x, y, exo in rows:
        code = (code or "").upper()
        x, y = float(x or 0), float(y or 0)
        xs.append(x); ys.append(y)
        if code != TERM_CODE:
            logic_x.append(x)
    sh.xmin, sh.xmax = (min(xs), max(xs)) if xs else (0, 0)
    sh.ymin, sh.ymax = (min(ys), max(ys)) if ys else (0, 0)
    midx = (min(logic_x) + max(logic_x)) / 2.0 if logic_x else 100

    # dem so chan (khong ke terminal E0B1) tren tung net => phat hien fanout noi bo
    term_bids = {bid for bid, sym, code, x, y, exo in rows if (code or "").upper() == TERM_CODE}
    net_local = defaultdict(int)
    for _bid, _plist in pins_all.items():
        if _bid in term_bids:
            continue
        for _pn, _sig in _plist:
            if _sig:
                net_local[_sig] += 1
    self_num = R["num"].get(sheet_id)

    for bid, sym, code, x, y, exo in rows:
        codeU = (code or "").upper()
        x, y = float(x or 0), float(y or 0)
        if codeU == TERM_CODE:
            net = pin1.get(bid, "")
            ln, ref = _res(R, sheet_id, net)
            t = STerm()
            t.side = "L" if x < midx else "R"
            t.x, t.y = x, y
            t.linename, t.ref, t.lid = ln, ref, net
            t.targets = _targets(c, R, sheet_id, net, side=t.side, path=path)
            t.refs = []
            # self cross-ref: terminal ngo ra ma net con duoc dung boi khoi khac
            # tren cung sheet (fanout noi bo) -> PDF liet ke so cua CHINH sheet (vd 08739)
            if t.side == "R" and self_num and net_local.get(net, 0) >= 2:
                t.refs.append(_pad(self_num))
            # DB kieu EHC: dau vao lay tin hieu do CHINH sheet nay sinh ra (hoi tiep noi
            # bo) -> ban ve goc ghi so cua chinh sheet nay o cot "From" (vd 01180)
            if (t.side == "L" and self_num and net in R.get("syskeys", ())
                    and sheet_id in _producers(path).get(net, ())):
                t.refs.append(_pad(self_num))
            for _sid, _lb in t.targets:
                s2 = _pad(R["num"].get(_sid))
                if s2 and s2 not in t.refs:
                    t.refs.append(s2)
            if not t.refs and ref:
                t.refs = [_pad(ref)]
            _mm = re.search(r"CPU0*(\d+)", t.linename or "")
            if _mm:
                t.xcpu = int(_mm.group(1))
            elif sheet_partner:
                t.xcpu = sheet_partner
            sh.terms.append(t)
        else:
            b = SBlock()
            b.bid = bid; b.code = codeU; b.x = x; b.y = y
            b.exorder = exo if exo is not None and exo >= 0 else -1
            b.name = D.macro_name(codeU, sym)
            b.sym = sym or ""
            mdef = MP.get(sym) or MP.get((sym or "").strip())
            terms = mterms.get(codeU)
            if terms:
                b.in_names = list(terms[0]); b.out_names = list(terms[1])
            pr = params.get(bid, {})
            b.label = pr.get("1", "")
            b.params = [pr[k] for k in sorted(pr, key=lambda z: int(z)) if k != "1" and pr[k]]
            b.parammap = {int(k): pr[k] for k in pr if str(k).isdigit()}
            b.tag = tag_of.get(bid, "")
            b.tdes = tdes_of.get(bid, "")
            # PARAM1 cua khoi tag = mã KKS, trung voi Ttag -> bo di, chi hien 1 ma KKS
            if b.label and b.tag and b.label.strip() == b.tag.strip():
                b.label = ""
            _compute_pins(b, pins_all.get(bid, []), net_ends, x, y, mdef)
            sh.blocks.append(b)

    for lid, sig in c.execute("SELECT LINE_ID,SIGNALID FROM CAD_LIN WHERE ID=?", (sheet_id,)).fetchall():
        det = list(c.execute(
            "SELECT GROUPNO,VERTEXNO,X,Y FROM CAD_LIN_DETAIL WHERE LINE_ID=? ORDER BY GROUPNO,VERTEXNO", (lid,)))
        if not det:
            continue
        w = SWire(D._clean(sig))
        cur_g = None; poly = []
        for g, v, x, y in det:
            if g != cur_g:
                if poly:
                    w.polylines.append(poly)
                poly = []; cur_g = g
            poly.append((float(x), float(y)))
        if poly:
            w.polylines.append(poly)
        sh.wires.append(w)

    for tid, kind, s, x, y in c.execute(
            "SELECT TEXT_ID,TEXTKIND,TEXTSTRING,X,Y FROM CAD_TEXT WHERE ID=?", (sheet_id,)):
        sh.texts.append(SText(float(x or 0), float(y or 0), D._clean(s)))
    return sh


def _compute_pins(b, pinlist, net_ends, bx, by, mdef=None):
    connected = {pn for pn, sig in pinlist if sig}
    pinsig = {pn: D._clean(sig) for pn, sig in pinlist}
    # ---- Nguon chuan: dinh nghia macro (offset + ten + canh + khung) ----
    if mdef and mdef.get("pins"):
        for pn_s, info in sorted(mdef["pins"].items(), key=lambda kv: int(kv[0])):
            pn = int(pn_s)
            px = bx + float(info["dx"])
            py = by + float(info["dy"])
            is_out = (info.get("side") == "out")
            b.pins.append((px, py, is_out, info.get("name", ""), pn in connected, pinsig.get(pn, "")))
        b.n_in = mdef.get("in_num", 0)
        b.n_out = mdef.get("out_num", 0)
        box = mdef.get("box")
        if box:
            b.box = (bx + box["lx"], by - box["ry"], bx + box["rx"], by - box["ly"])
        else:
            xs = [p[0] for p in b.pins]; ys = [p[1] for p in b.pins]
            b.box = (min(xs), min(ys) - 2, max(xs), max(ys) + 3)
        return
    # ---- Fallback: suy tu diem cuoi day (khi thieu dinh nghia macro) ----
    raw = []
    for pinno, sig in pinlist:
        if not (sig and net_ends.get(sig)):
            continue
        px, py = min(net_ends[sig], key=lambda p: abs(p[0] - bx) + abs(p[1] - by))
        raw.append((pinno, px, py, D._clean(sig)))
    if not raw:
        return
    xsr = [p[1] for p in raw]
    xmin, xmax = min(xsr), max(xsr)
    thr = (xmin + xmax) / 2.0 if (xmax - xmin) > 1 else None

    def _is_out(px):
        return px > thr if thr is not None else px > bx + 0.5

    ins = [p for p in raw if not _is_out(p[1])]
    outs = [p for p in raw if _is_out(p[1])]
    ins.sort(key=lambda p: -p[2])
    outs.sort(key=lambda p: -p[2])
    b.n_in, b.n_out = len(ins), len(outs)
    for i, p in enumerate(ins):
        nm = b.in_names[i] if i < len(b.in_names) else ""
        b.pins.append((p[1], p[2], False, nm, True, p[3]))
    for j, p in enumerate(outs):
        nm = b.out_names[j] if j < len(b.out_names) else ""
        b.pins.append((p[1], p[2], True, nm, True, p[3]))
    allx = [p[0] for p in b.pins]; ally = [p[1] for p in b.pins]
    xl, xr = min(allx), max(allx)
    if xr - xl < 8:
        xr = xl + 8
    b.box = (xl, min(ally) - 2, xr, max(ally) + 5)


def _res(R, sheet_id, net):
    sid, sig = D._parse_tag(net, R["pacodes"], R["code2sheet"])
    if sid is not None:
        return (R["idname"].get((sid, sig), ""), R["num"].get(sid, ""))
    ln = R["idname"].get((sheet_id, net), "")
    if not ln:
        # DB kieu EHC: net = dia chi he thong (DZ0005...), ten o CAD_SIGNAL
        ln = R.get("sysname", {}).get(net, "")
    il = R["idline"].get((sheet_id, net))
    ref = ""
    if il and R["crs"].get(il):
        pano, ps = R["crs"][il][0]
        ref = R["num"].get(R["code2sheet"].get((pano, ps)), "")
    return (ln, ref)


def _sheet_label(c, sid):
    r = c.execute("SELECT PANO,PASHEETNO,SHEETNAME FROM CAD_DATA WHERE ID=?", (sid,)).fetchone()
    if not r:
        return "Sheet %s" % sid
    pa, ps, nm = (D._clean(x) for x in r)
    return "%s %s  %s" % (pa, ps, nm)


_PROD = {"path": None, "map": {}}


def _producers(path):
    """{net: {sheet_id,...}} - sheet SINH RA tin hieu (net nam tren chan RA cua 1 khoi).
    Dung cho DB kieu EHC (net = dia chi he thong dung chung khap noi): cot "From" cua
    terminal DAU VAO phai chi ra DUNG sheet sinh ra no (thuong chi 1), khong phai liet ke
    moi sheet co dung tin hieu do. Quet 1 lan/DB roi cache (~0.3s cho 76k chan)."""
    if _PROD["path"] == path:
        return _PROD["map"]
    MP = _macro_pins()
    m = {}
    try:
        c = D.connect(path).cursor()
        for sid, sym, pn, sig in c.execute(
                "SELECT b.ID,b.SYMBOL,p.PINNO,p.SIGNALID FROM CAD_BLOCK_PIN p "
                "JOIN CAD_BLOCK b ON p.BLOCK_ID=b.BLOCK_ID "
                "WHERE p.SIGNALID IS NOT NULL AND TRIM(p.SIGNALID)<>''"):
            pdef = (MP.get(sym) or {}).get("pins", {})
            if pdef.get(str(pn), {}).get("side") == "out":
                m.setdefault(D._clean(sig), set()).add(sid)
    except Exception:
        m = {}
    _PROD.update(path=path, map=m)
    return m


def _targets(c, R, sheet_id, net, side="L", path=None):
    ids = []; seen = set()
    sid, sig = D._parse_tag(net, R["pacodes"], R["code2sheet"])
    if sid is not None and sid != sheet_id and sid not in seen:
        seen.add(sid); ids.append(sid)
    il = R["idline"].get((sheet_id, net))
    if il:
        for pano, ps in R["crs"].get(il, []):
            tsid = R["code2sheet"].get((pano, ps))
            if tsid is not None and tsid != sheet_id and tsid not in seen:
                seen.add(tsid); ids.append(tsid)
    # Duong nhay thu 3 (DB kieu EHC): net = dia chi he thong (co trong CAD_SIGNAL),
    # khong dung CAD_ID_CRS. Phai theo DUNG CHIEU, giong het ban ve goc:
    #   terminal TRAI  (dau vao, cot "From") -> sheet SINH RA tin hieu (chan RA), thuong 1
    #   terminal PHAI  (dau ra,  cot "To")   -> cac sheet TIEU THU tin hieu (chan VAO)
    # Neu khong phan chieu (liet ke moi sheet co dung) thi 1 dau vao se hien hang chuc
    # diem den - sai voi ban ve that.
    if not ids and net in R.get("syskeys", ()) and path:
        try:
            prod = _producers(path).get(net, set())
            if side == "L":
                cand = [s for s in sorted(prod) if s != sheet_id]
            else:
                users = {row[0] for row in c.execute(
                    "SELECT DISTINCT ID FROM CAD_LIN WHERE SIGNALID=?", (net,))}
                cand = sorted(users - prod - {sheet_id})
            for tsid in cand[:25]:      # chan tran menu voi tin hieu dung khap noi
                if tsid not in seen:
                    seen.add(tsid); ids.append(tsid)
        except Exception:
            pass
    return [(i, _sheet_label(c, i)) for i in ids]
