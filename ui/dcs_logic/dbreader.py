# -*- coding: utf-8 -*-
"""
Doc file DB du an cua T-Designer (SQLite, bang CAD_*) va dung lai sheet
theo bo cuc bao cao goc: 7 cot
[Line Name | From | LID | Logic Chart | LID | To | Line Name].

Ten Line Name cua terminal dau vao duoc giai ma chinh xac qua CAD_DATA:
  tag 'HA035AG-11' -> PA=HA, PASHEETNO=035AG -> sheet 867, sig 11
                   -> CAD_ID[867,11] = "PULV A PAFL CTRL AUTO CTRL CMD"
  From/To = LOOPNO+SHEETNO cua sheet nguon/dich.
"""
from __future__ import annotations
import os
import json
import sqlite3
from collections import defaultdict
from .model import Circuit, BLOCK_SPECS, _manual_terms

_NAME_BY_CODE = {}


def _load_names():
    global _NAME_BY_CODE
    if _NAME_BY_CODE:
        return
    p = os.path.join(os.path.dirname(__file__), "macro_catalog.json")
    if os.path.exists(p):
        for m in json.load(open(p, encoding="utf-8")).get("macros", []):
            _NAME_BY_CODE[m["code"].upper()] = m["short"]


def _clean(s):
    if s is None:
        return ""
    return "".join(ch for ch in str(s) if 32 <= ord(ch) < 127).strip()


def macro_name(code, symbol):
    _load_names()
    nm = _NAME_BY_CODE.get((code or "").upper())
    return nm or _clean(symbol) or ("code " + str(code))


def ro_uri(path):
    """SQLite URI that cannot write. '?' and '#' would end the path early."""
    return "file:%s?mode=ro" % str(path).replace("?", "%3f").replace("#", "%23")


def connect(path):
    # Read-only: these are the plant's design masters, and nothing here writes.
    con = sqlite3.connect(ro_uri(path), uri=True)
    con.text_factory = lambda b: b.decode("latin-1", "replace")
    return con


def list_project(path):
    c = connect(path).cursor()
    out = {}
    try:
        r = c.execute("SELECT PROJNO,PROJNAME,PROJNAME1,PROJNAME2 FROM CAD_PJ LIMIT 1").fetchone()
        if r:
            out["project"] = " / ".join(_clean(x) for x in r[1:] if _clean(x))
    except Exception:
        pass
    for tbl, key in [("CAD_PA", "pas"), ("CAD_CPU", "cpus")]:
        try:
            out[key] = [tuple(_clean(x) for x in row) for row in c.execute("SELECT * FROM %s" % tbl)]
        except Exception:
            out[key] = []
    return out


def db_meta(path):
    """Thong tin du an + CPU cua 1 file DB (de gom nhom, phat hien quan he)."""
    c = connect(path).cursor()
    proj = None
    try:
        proj = c.execute("SELECT PROJNO,PROJNAME,PROJNAME1 FROM CAD_PJ").fetchone()
    except Exception:
        pass
    cpu = None
    try:
        cpu = c.execute("SELECT CPUNO,CPUNAME FROM CAD_CPU").fetchone()
    except Exception:
        pass
    return {
        "projno": proj[0] if proj else None,
        "projname": _clean(proj[1]) if proj else "",
        "projdesc": _clean(proj[2]) if proj else "",
        "cpuno": cpu[0] if cpu else None,
        "cpuname": _clean(cpu[1]) if cpu else "",
    }


def loop_names(path):
    """{loopno: ten loop} tu CAD_LOOP - ten CHUC NANG that cua tung mach dieu khien
    (vd 184 -> 'M-BFP MIN FLW CTRL', 156 -> 'BFPT A'), dung de gom cay sheet theo Loop."""
    try:
        c = connect(path).cursor()
        return {ln: _clean(nm) for ln, nm in c.execute("SELECT LOOPNO,LOOPNAME FROM CAD_LOOP")}
    except Exception:
        return {}


def list_sheets(path):
    c = connect(path).cursor()
    counts = dict(c.execute("SELECT ID,COUNT(*) FROM CAD_BLOCK GROUP BY ID"))
    meta = {}
    try:
        for sid, pano, ps, nm, c1, loop, sno in c.execute(
                "SELECT ID,PANO,PASHEETNO,SHEETNAME,COMMENT1,LOOPNO,SHEETNO FROM CAD_DATA"):
            meta[sid] = (_clean(pano), _clean(ps), _clean(nm), _clean(c1), loop, sno)
    except Exception:
        pass
    lnames = loop_names(path)
    res = []
    for sid, n in counts.items():
        pa, ps, nm, c1, loop, sno = meta.get(sid, ("", "", "", "", None, None))
        res.append({"id": sid, "pa": pa, "sheetno": ps, "name": nm, "nblocks": n,
                    "comment1": c1, "loopno": loop, "sheetno_num": sno,
                    "loopname": lnames.get(loop, "")})
    res.sort(key=lambda d: (d["pa"], d["sheetno"], d["id"]))
    return res


def _register_spec(key, label, n_in, n_out, term=None):
    if key not in BLOCK_SPECS:
        BLOCK_SPECS[key] = {
            "inputs": n_in, "outputs": n_out,
            "in_names": ["I%d" % (i + 1) for i in range(n_in)],
            "out_names": ["O%d" % (j + 1) for j in range(n_out)],
            "desc": label, "label": label, "short": label,
            "code": "", "category": "DB import", "params": 0,
            "obs": False, "generic": True, "term": term,
        }
    return key


_register_spec("TERM_IN", "", 0, 1, term="in")
_register_spec("TERM_OUT", "", 1, 0, term="out")

TERM_CODE = "E0B1"
TERM_W = 300
GAPL = 90
GAPR = 90
SCX = 4.0
SCY = 7.0

# ------- bo giai ma ten tin hieu (cache theo path) -------
_RES = {"path": None}


def _resolvers(path):
    if _RES["path"] == path:
        return _RES
    c = connect(path).cursor()
    meta, code2sheet, num = {}, {}, {}
    try:
        for sid, pano, ps, loop, sh in c.execute(
                "SELECT ID,PANO,PASHEETNO,LOOPNO,SHEETNO FROM CAD_DATA"):
            pano, ps = _clean(pano), _clean(ps)
            meta[sid] = (pano, ps)
            code2sheet[(pano, ps)] = sid
            loop, sh = _clean(loop), _clean(sh)
            num[sid] = (loop + sh.zfill(2)) if (loop and sh) else (loop or sh)
    except Exception:
        pass
    idname, idline = {}, {}
    try:
        for sid, sig, ln, il in c.execute("SELECT ID,SIGNALID,LINENAME,IDLINE_ID FROM CAD_ID"):
            idname[(sid, _clean(sig))] = _clean(ln)
            idline[(sid, _clean(sig))] = il
    except Exception:
        pass
    # Nguon ten thu 2: CAD_SIGNAL (SYSTEMLINE -> LINENAME). Mot so DB (vd 21 EHC MC.db)
    # dat net tren chan khoi bang THANG dia chi he thong (DZ0005, EW0331...) va ten cua
    # chung chi nam o CAD_SIGNAL, khong co trong CAD_ID -> dung lam fallback khi CAD_ID
    # khong khop (app goc cung doc duoc ten cho cac DB nay).
    sysname = {}
    syskeys = set()   # MOI dia chi he thong (ke ca chua dat ten) - de biet net nao la global
    try:
        for sl, ln in c.execute("SELECT SYSTEMLINE,LINENAME FROM CAD_SIGNAL"):
            sl = _clean(sl); ln = _clean(ln)
            if not sl:
                continue
            syskeys.add(sl)
            if ln and sl not in sysname:
                sysname[sl] = ln
    except Exception:
        pass
    crs = defaultdict(list)   # idline -> [(pano,ps),...]
    try:
        for il, cid, pano, ps in c.execute("SELECT IDLINE_ID,CRS_ID,PANO,PASHEETNO FROM CAD_ID_CRS"):
            crs[il].append((_clean(pano), _clean(ps)))
    except Exception:
        pass
    pacodes = sorted({k[0] for k in code2sheet if k[0]}, key=len, reverse=True)
    _RES.update(path=path, meta=meta, code2sheet=code2sheet, num=num,
                idname=idname, idline=idline, crs=crs, pacodes=pacodes,
                sysname=sysname, syskeys=syskeys)
    return _RES


def _parse_tag(tag, pacodes, code2sheet):
    """tag 'HA035AG-11' -> (sheet_id, sig) neu giai ma duoc."""
    base, _, sig = tag.rpartition("-")
    if not base or not sig:
        return (None, None)
    for pa in pacodes:
        if base.startswith(pa):
            ps = base[len(pa):]
            sid = code2sheet.get((pa, ps))
            if sid is not None:
                return (sid, sig)
    return (None, None)


def build_circuit(path, sheet_id):
    c = connect(path).cursor()
    rows = list(c.execute(
        "SELECT BLOCK_ID,SYMBOL,MACROCODE,X,Y FROM CAD_BLOCK WHERE ID=? ORDER BY BLOCK_ID", (sheet_id,)))
    if not rows:
        raise ValueError("Sheet %s khong co khoi." % sheet_id)
    R = _resolvers(path)
    mterms = _manual_terms()

    blk = {}
    for bid, sym, code, x, y in rows:
        blk[bid] = (sym, (code or "").upper(), float(x or 0), float(y or 0))

    lin_net = {}
    try:
        for lid_, netsig in c.execute("SELECT LINE_ID,SIGNALID FROM CAD_LIN WHERE ID=?", (sheet_id,)):
            lin_net[lid_] = _clean(netsig)
    except Exception:
        pass

    pins, sig_pins = {}, defaultdict(list)
    for bid in blk:
        lst = []
        for pinno, sig, pt, ns in c.execute(
                "SELECT PINNO,SIGNALID,PIN_TYPE,NOT_SIGN FROM CAD_BLOCK_PIN WHERE BLOCK_ID=? ORDER BY PINNO", (bid,)):
            sig = _clean(sig)
            lst.append((pinno, sig, pt, ns))
            if sig:
                sig_pins[sig].append((bid, pinno))
        pins[bid] = lst

    producer = {}
    for sig, lst in sig_pins.items():
        if len(lst) > 1:
            producer[sig] = min(lst, key=lambda t: blk[t[0]][2])

    in_idx, out_idx, pin_role = defaultdict(dict), defaultdict(dict), {}
    for bid in blk:
        code = blk[bid][1]
        terms = mterms.get(code)
        npins = max([pn for pn, *_ in pins[bid]], default=0)
        use_man = bool(terms and code != TERM_CODE
                       and (len(terms[0]) + len(terms[1])) >= npins
                       and (len(terms[0]) + len(terms[1])) > 0)
        if use_man:
            # theo manual: PINNO 1..n_in = vao, tiep theo = ra
            n_in = len(terms[0])
            for pinno, sig, pt, ns in pins[bid]:
                if pinno <= n_in:
                    in_idx[bid][pinno] = pinno - 1
                    pin_role[(bid, pinno)] = ("in", pinno - 1)
                else:
                    j = pinno - n_in - 1
                    out_idx[bid][pinno] = j
                    pin_role[(bid, pinno)] = ("out", j)
        else:
            ins, outs = [], []
            for pinno, sig, pt, ns in pins[bid]:
                is_out = sig in producer and producer[sig] == (bid, pinno)
                (outs if is_out else ins).append(pinno)
            for i, pn in enumerate(ins):
                in_idx[bid][pn] = i
                pin_role[(bid, pn)] = ("in", i)
            for j, pn in enumerate(outs):
                out_idx[bid][pn] = j
                pin_role[(bid, pn)] = ("out", j)

    tag_of, tdes_of, tid_of = {}, {}, {}
    try:
        for bid, suf, val in c.execute("SELECT BLOCK_ID,FIDSUFFIX,FIDVALUE FROM CAD_TAG_FID"):
            if bid not in blk:
                continue
            suf, val = _clean(suf), _clean(val)
            if not val:
                continue
            if suf == "Ttag" and bid not in tag_of:
                tag_of[bid] = val
            elif suf == "TDes1" and bid not in tdes_of:
                tdes_of[bid] = val
            elif suf == "TID" and bid not in tid_of:
                tid_of[bid] = val
    except Exception:
        pass

    logic_ids = [b for b in blk if blk[b][1] != TERM_CODE]
    xs = [blk[b][2] for b in logic_ids] or [0]
    minlx, maxlx = min(xs), max(xs)
    midlx = (minlx + maxlx) / 2.0
    ys = [blk[b][3] for b in blk]
    ymax = max(ys) if ys else 0
    logic_x0 = TERM_W + GAPL
    right_x = logic_x0 + (maxlx - minlx) * SCX + 140 + GAPR

    def resolve(net):
        """(line_name, ref_num). ref = sheet nguon (input) hoac dich (output)."""
        # 1) tag chi ro sheet khac: HAxxxx-nn
        sid, sig = _parse_tag(net, R["pacodes"], R["code2sheet"])
        if sid is not None:
            return (R["idname"].get((sid, sig), ""), R["num"].get(sid, ""))
        # 2) tin hieu cuc bo dinh nghia tren sheet nay -> ten + dich qua CRS
        ln = R["idname"].get((sheet_id, net), "")
        if not ln:
            # 3) DB kieu EHC: net = dia chi he thong, ten nam o CAD_SIGNAL
            ln = R.get("sysname", {}).get(net, "")
        il = R["idline"].get((sheet_id, net))
        ref = ""
        if il and R["crs"].get(il):
            pano, ps = R["crs"][il][0]
            ref = R["num"].get(R["code2sheet"].get((pano, ps)), "")
        return (ln, ref)

    in_name = resolve
    out_name = resolve

    cir = Circuit("SHEET_%s" % sheet_id)
    id_map = {}
    for bid in blk:
        sym, code, x, y = blk[bid]
        yy = (ymax - y) * SCY
        if code == TERM_CODE:
            net = pins[bid][0][1] if pins[bid] else ""   # net = signal cua CHAN (CAD_LIN khong map theo block_id)
            is_input = x < midlx
            if is_input:
                ln, frm = in_name(net)
                b = cir.add_block("TERM_IN", tag=ln, x=0, y=yy)
                b.param.update(crs=frm, lid=net, side="L")
            else:
                ln, to = out_name(net)
                b = cir.add_block("TERM_OUT", tag=ln, x=right_x, y=yy)
                b.param.update(crs=to, lid=net, side="R")
            id_map[bid] = b
        else:
            label = macro_name(code, sym)
            terms = mterms.get(code)
            npins = max([pn for pn, *_ in pins[bid]], default=0)
            if terms and (len(terms[0]) + len(terms[1])) >= npins and (len(terms[0]) + len(terms[1])) > 0:
                n_in, n_out = len(terms[0]), len(terms[1])
                btype = "DB::%s::manual" % code
                if btype not in BLOCK_SPECS:
                    _register_spec(btype, label, n_in, n_out)
                    BLOCK_SPECS[btype]["in_names"] = terms[0]
                    BLOCK_SPECS[btype]["out_names"] = terms[1]
            else:
                n_in, n_out = len(in_idx[bid]), len(out_idx[bid])
                btype = _register_spec("DB::%s::%dx%d" % (label, n_in, n_out), label, n_in, n_out)
            xx = logic_x0 + (x - minlx) * SCX
            b = cir.add_block(btype, tag=tag_of.get(bid, ""), x=xx, y=yy)
            b.param.update(macro=label, code=code,
                           tdes=tdes_of.get(bid, ""), tid=tid_of.get(bid, ""))
            id_map[bid] = b

    for sig, lst in sig_pins.items():
        if sig not in producer:
            continue
        pbid, ppin = producer[sig]
        prole = pin_role.get((pbid, ppin))
        if not prole or prole[0] != "out":
            continue
        for bid, pinno in lst:
            if (bid, pinno) == (pbid, ppin):
                continue
            role = pin_role.get((bid, pinno))
            if role and role[0] == "in":
                cir.connect(id_map[pbid].id, prole[1], id_map[bid].id, role[1])

    cir.report = {"term_w": TERM_W, "left_x": 0, "logic_x0": logic_x0,
                  "right_x": right_x, "right_w": TERM_W,
                  "top": -60, "bottom": ymax * SCY + 40}
    return cir


def _sheet_lbl(c, sid):
    r = c.execute("SELECT COMMENT1,LOOPNO,SHEETNO,SHEETNAME FROM CAD_DATA WHERE ID=?", (sid,)).fetchone()
    if not r:
        return "Sheet %s" % sid
    c1, lo, sn, nm = r
    parts = [_clean(c1),
             ("Loop %s" % lo) if lo is not None else "",
             ("Sheet %s" % sn) if sn is not None else "",
             _clean(nm)]
    return " ".join(p for p in parts if p) or ("Sheet %s" % sid)


def resolve_cross_cpu(cur_path, cur_sheet_name, signalid, linename, cpu_paths, cur_cpuno=None):
    """Tra ve danh sach (db_path, sheet_id, nhan) o CPU doi tac cho 1 tin hieu lien-CPU.
    Khop theo TEN tin hieu (bo tien to CPUxx); CPU doi tac lay tu token CPUxx.
    Neu khong khop ten -> fallback: cac sheet 'TO CPU<cur>' cua DB doi tac.
    Moi thao tac boc try/except: loi thi tra [] (khong lam hong luong hien tai)."""
    import re
    try:
        part = None
        for src in (linename or "", cur_sheet_name or ""):
            m = re.search(r"CPU0*(\d+)", src)
            if m:
                part = int(m.group(1)); break
        if part is None or part == cur_cpuno:
            return []
        ppath = cpu_paths.get(part)
        if not ppath or ppath == cur_path:
            return []
        # ten mo ta tin hieu (uu tien CAD_SIGNAL cua DB hien tai)
        name = (linename or "").strip()
        try:
            cc = connect(cur_path).cursor()
            r = cc.execute("SELECT LINENAME FROM CAD_SIGNAL WHERE SYSTEMLINE=?", (signalid,)).fetchone()
            if r and (r[0] or "").strip():
                name = r[0].strip()
        except Exception:
            pass
        key = re.sub(r"^CPU\d+\s+", "", name, flags=re.I).strip().upper()
        out = []; seen = set()
        pc = connect(ppath).cursor()
        if key:
            addrs = [row[0] for row in pc.execute(
                "SELECT SYSTEMLINE FROM CAD_SIGNAL WHERE UPPER(TRIM(LINENAME))=?", (key,))]
            for a in addrs:
                for (sid,) in pc.execute(
                        "SELECT DISTINCT b.ID FROM CAD_BLOCK_PIN p JOIN CAD_BLOCK b "
                        "ON p.BLOCK_ID=b.BLOCK_ID WHERE p.SIGNALID=?", (a,)):
                    if sid in seen:
                        continue
                    seen.add(sid)
                    out.append((ppath, sid, _sheet_lbl(pc, sid)))
        if not out:
            like = ("TO CPU%02d%%" % cur_cpuno) if cur_cpuno else "TO CPU%"
            for (sid,) in pc.execute("SELECT ID FROM CAD_DATA WHERE SHEETNAME LIKE ?", (like,)):
                if sid in seen:
                    continue
                seen.add(sid)
                out.append((ppath, sid, _sheet_lbl(pc, sid)))
        return out[:40]
    except Exception:
        return []
