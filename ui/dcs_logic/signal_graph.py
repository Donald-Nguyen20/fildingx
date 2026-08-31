# -*- coding: utf-8 -*-
"""
So do node muc TIN HIEU: node = DIEM I/O (tin hieu co line-name), canh = chuoi
khoi noi tu diem I/O nay -> diem I/O khac. Net trung gian (a0,a1...) duoc CO GON.
Chan input->output noi theo LOGIC NOI BO (macro_iodep).

Hai pham vi:
  - trace()         : chi trong 1 sheet.
  - trace_project() : xuyen SHEET (gop tin hieu cung line-name trong 1 DB) va
                      xuyen CPU (C-NET, khop ten + token CPUxx).
"""
from __future__ import annotations
import os
import re
import json
from collections import defaultdict, deque
from . import dbreader as D
from . import sheet_render as SR

TERM = "E0B1"
_IODEP = None


def _iodep():
    global _IODEP
    if _IODEP is None:
        p = os.path.join(os.path.dirname(__file__), "macro_iodep.json")
        try:
            _IODEP = json.load(open(p, encoding="utf-8"))
        except Exception:
            _IODEP = {}
    return _IODEP


def _pin_out(mdef, pinno, idx, n):
    if mdef and mdef.get("pins"):
        pi = mdef["pins"].get(str(pinno))
        if pi:
            return pi.get("side") == "out"
    return idx == n - 1


def _sheet_nets(c, sheet_id, MP):
    IODEP = _iodep()
    blocks = {}
    for bid, sym, code in c.execute(
            "SELECT BLOCK_ID,SYMBOL,MACROCODE FROM CAD_BLOCK WHERE ID=? ORDER BY BLOCK_ID", (sheet_id,)):
        blocks[bid] = {"code": (code or "").upper(), "sym": sym or ""}
    pins = defaultdict(list)
    for bid, pn, sig in c.execute(
            "SELECT p.BLOCK_ID,p.PINNO,p.SIGNALID FROM CAD_BLOCK_PIN p "
            "JOIN CAD_BLOCK b ON p.BLOCK_ID=b.BLOCK_ID WHERE b.ID=? ORDER BY p.PINNO", (sheet_id,)):
        pins[bid].append((pn, D._clean(sig)))
    feeds = defaultdict(list)
    fedby = defaultdict(list)

    def link(i, o, lbl):
        if i and o and i != o:
            feeds[i].append((o, lbl))
            fedby[o].append((i, lbl))

    for bid, plist in pins.items():
        info = blocks[bid]
        if info["code"] == TERM:
            continue
        mdef = MP.get(info["sym"])
        n = len(plist)
        ins, outs = [], []
        for idx, (pn, sig) in enumerate(plist):
            (outs if _pin_out(mdef, pn, idx, n) else ins).append(sig)
        blabel = D.macro_name(info["code"], info["sym"])
        dep = IODEP.get(info["code"])
        if dep and dep.get("dep") and dep["nin"] == len(ins) and dep["nout"] == len(outs):
            for oi, o in enumerate(outs):
                for ii in dep["dep"].get(str(oi), []):
                    if 0 <= ii < len(ins):
                        link(ins[ii], o, blabel)
        else:
            for o in outs:
                for i in ins:
                    link(i, o, blabel)
    return feeds, fedby


def block_output_net(db_path, sheet_id, bid):
    c = D.connect(db_path).cursor()
    MP = SR._macro_pins()
    row = c.execute("SELECT SYMBOL,MACROCODE FROM CAD_BLOCK WHERE BLOCK_ID=?", (bid,)).fetchone()
    sym = (row[0] or "") if row else ""
    mdef = MP.get(sym)
    plist = [(pn, D._clean(sig)) for pn, sig in c.execute(
        "SELECT PINNO,SIGNALID FROM CAD_BLOCK_PIN WHERE BLOCK_ID=? ORDER BY PINNO", (bid,))]
    n = len(plist)
    outs = [sig for idx, (pn, sig) in enumerate(plist) if sig and _pin_out(mdef, pn, idx, n)]
    if outs:
        return outs[0]
    return plist[0][1] if plist else ""


# ---------------- pham vi 1 SHEET ----------------
def trace(db_path, sheet_id, start_net, direction="both", depth=4):
    c = D.connect(db_path).cursor()
    MP = SR._macro_pins()
    R = D._resolvers(db_path)
    slbl = _dbc(db_path)["num"].get(sheet_id) or str(sheet_id)
    feeds, fedby = _sheet_nets(c, sheet_id, MP)
    name_cache = {}

    def nm(net):
        if net not in name_cache:
            ln, _r = SR._res(R, sheet_id, net)
            name_cache[net] = ln or None
        return name_cache[net]

    def is_io(net):
        return net == start_net or bool(nm(net))

    def reach(net, dmap):
        res = []

        def walk(cur, labels, local):
            for nx, lb in dmap.get(cur, ()):
                nl = labels + [lb]
                if is_io(nx):
                    res.append((nx, nl))
                elif nx not in local and len(nl) < 8:
                    walk(nx, nl, local | {nx})
        walk(net, [], {net})
        return res

    nodes = {}
    edges = {}

    def nid(net):
        return "%s:%s" % (sheet_id, net)

    def add(net):
        k = nid(net)
        if k not in nodes:
            ln = nm(net)
            nodes[k] = {"id": k, "net": net, "sheet": sheet_id, "sheetlbl": slbl,
                        "db": db_path, "label": ln or net, "named": bool(ln)}
        return k

    start_key = add(start_net)
    fu = [start_net]; fd = [start_net]
    seen = {start_net}
    for _ in range(depth):
        nu, nd = [], []
        if direction in ("up", "both"):
            for net in fu:
                for src, labels in reach(net, fedby):
                    add(src)
                    edges.setdefault((nid(src), nid(net)), " -> ".join(reversed(labels)))
                    if src not in seen:
                        seen.add(src); nu.append(src)
        if direction in ("down", "both"):
            for net in fd:
                for dst, labels in reach(net, feeds):
                    add(dst)
                    edges.setdefault((nid(net), nid(dst)), " -> ".join(labels))
                    if dst not in seen:
                        seen.add(dst); nd.append(dst)
        fu, fd = nu, nd
        if not fu and not fd:
            break

    elist = [{"src": s, "dst": d, "block": b, "kind": "blk"} for (s, d), b in edges.items()]
    return list(nodes.values()), elist, start_key


# ---------------- pham vi TOAN DU AN ----------------
_DBC = {}


def _dbc(db):
    """Cache maps giai ma ten + chi muc ten cho 1 DB (nhieu DB cung luc)."""
    if db in _DBC:
        return _DBC[db]
    c = D.connect(db).cursor()
    meta = {}; code2sheet = {}; num = {}; sheetname = {}; comment1 = {}
    try:
        for sid, pano, ps, loop, sh, snm, cm1 in c.execute(
                "SELECT ID,PANO,PASHEETNO,LOOPNO,SHEETNO,SHEETNAME,COMMENT1 FROM CAD_DATA"):
            pano = D._clean(pano); ps = D._clean(ps)
            meta[sid] = (pano, ps); code2sheet[(pano, ps)] = sid
            loop = D._clean(loop); sh = D._clean(sh)
            # dia chi Loop-Sheet dang "109-18" (loop 3 so - sheet 2 so) de de tra ban ve
            num[sid] = (loop.zfill(3) + "-" + sh.zfill(2)) if (loop and sh) else (loop or sh)
            sheetname[sid] = D._clean(snm)
            comment1[sid] = D._clean(cm1)
    except Exception:
        pass
    idname = {}; idline = {}
    try:
        for sid, sig, ln, il in c.execute("SELECT ID,SIGNALID,LINENAME,IDLINE_ID FROM CAD_ID"):
            idname[(sid, D._clean(sig))] = D._clean(ln); idline[(sid, D._clean(sig))] = il
    except Exception:
        pass
    # fallback: CAD_SIGNAL (SYSTEMLINE -> LINENAME) cho DB kieu EHC - net tren chan la
    # thang dia chi he thong (DZ0005, EW0331...), ten chi co trong CAD_SIGNAL
    sysname = {}
    try:
        for sl, ln in c.execute("SELECT SYSTEMLINE,LINENAME FROM CAD_SIGNAL"):
            sl = D._clean(sl); ln = D._clean(ln)
            if sl and ln and sl not in sysname:
                sysname[sl] = ln
    except Exception:
        pass
    pacodes = sorted({k[0] for k in code2sheet if k[0]}, key=len, reverse=True)
    name2 = defaultdict(list)
    for (sid, sig), ln in idname.items():
        if ln:
            name2[ln.upper()].append((sid, sig))
    cpuno = None; cpuname = ""
    try:
        r = c.execute("SELECT CPUNO,CPUNAME FROM CAD_CPU").fetchone()
        if r:
            cpuno = r[0]; cpuname = D._clean(r[1])
    except Exception:
        pass
    d = {"meta": meta, "code2sheet": code2sheet, "num": num, "idname": idname,
         "idline": idline, "pacodes": pacodes, "name2": name2,
         "cpuno": cpuno, "cpuname": cpuname, "comment1": comment1,
         "sheetname": sheetname, "sysname": sysname, "nets": {}, "prodn": {}}
    _DBC[db] = d
    return d


def sys_name(db, sheet):
    """Ten he thong hien thi thay cho 'CPU1': lay COMMENT1 cua sheet (CAD_DATA),
    rong thi lui ve CPUNAME roi CPU<so>."""
    R = _dbc(db)
    return (R["comment1"].get(sheet) or R.get("cpuname")
            or ("CPU%s" % R.get("cpuno")))


def _name_of(db, sheet, net):
    R = _dbc(db)
    sid, sig = D._parse_tag(net, R["pacodes"], R["code2sheet"])
    if sid is not None:
        return R["idname"].get((sid, sig), "")
    return (R["idname"].get((sheet, net), "")
            or R.get("sysname", {}).get(net, ""))


def _nets(db, sheet):
    R = _dbc(db)
    if sheet not in R["nets"]:
        c = D.connect(db).cursor()
        R["nets"][sheet] = _sheet_nets(c, sheet, SR._macro_pins())
    return R["nets"][sheet]


def _produced_names(db, sheet):
    """Ten tin hieu (line-name) la NGO RA cua khoi tren sheet do (= sheet sinh ra no)."""
    R = _dbc(db)
    if sheet in R["prodn"]:
        return R["prodn"][sheet]
    c = D.connect(db).cursor(); MP = SR._macro_pins()
    blocks = {}
    for bid, sym, code in c.execute(
            "SELECT BLOCK_ID,SYMBOL,MACROCODE FROM CAD_BLOCK WHERE ID=? ORDER BY BLOCK_ID", (sheet,)):
        blocks[bid] = (sym or "", (code or "").upper())
    pins = defaultdict(list)
    for bid, pn, sig in c.execute(
            "SELECT p.BLOCK_ID,p.PINNO,p.SIGNALID FROM CAD_BLOCK_PIN p "
            "JOIN CAD_BLOCK b ON p.BLOCK_ID=b.BLOCK_ID WHERE b.ID=? ORDER BY p.PINNO", (sheet,)):
        pins[bid].append((pn, D._clean(sig)))
    prod = set()
    for bid, plist in pins.items():
        sym, code = blocks.get(bid, ("", ""))
        if code == TERM:
            continue
        mdef = MP.get(sym); n = len(plist)
        for idx, (pn, sig) in enumerate(plist):
            if sig and _pin_out(mdef, pn, idx, n):
                ln = _name_of(db, sheet, sig)
                if ln:
                    prod.add(ln.upper())
    R["prodn"][sheet] = prod
    return prod


def _reach(db, sheet, net, dmap, anchor):
    res = []

    def walk(cur, labels, local):
        for nx, lb in dmap.get(cur, ()):
            nl = labels + [lb]
            if _name_of(db, sheet, nx) or (db, sheet, nx) == anchor:
                res.append((nx, nl))
            elif nx not in local and len(nl) < 8:
                walk(nx, nl, local | {nx})
    walk(net, [], {net})
    return res


_GSIG = {}


def _gsig(cpu_paths):
    """Chi muc ten tin hieu toan du an: NAME(upper) -> [(cpu, db, addr)] tu CAD_SIGNAL."""
    key = tuple(sorted((k, v) for k, v in cpu_paths.items()))
    if key in _GSIG:
        return _GSIG[key]
    idx = defaultdict(list)
    for cpu, db in cpu_paths.items():
        try:
            c = D.connect(db).cursor()
            for ln, addr in c.execute("SELECT LINENAME,SYSTEMLINE FROM CAD_SIGNAL"):
                ln = D._clean(ln)
                if ln:
                    idx[ln.upper()].append((cpu, db, D._clean(addr)))
        except Exception:
            pass
    _GSIG[key] = idx
    return idx


def _addr_sheet(db, addr):
    try:
        c = D.connect(db).cursor()
        r = c.execute(
            "SELECT b.ID FROM CAD_BLOCK_PIN p JOIN CAD_BLOCK b ON p.BLOCK_ID=b.BLOCK_ID "
            "WHERE p.SIGNALID=? LIMIT 1", (addr,)).fetchone()
        return r[0] if r else None
    except Exception:
        return None


def _cross_cpu(name, cur_db, cur_cpu, cpu_paths):
    """[(pdb, psheet, paddr, nhan)] o CPU khac cho tin hieu cung ten (C-NET)."""
    if not name or not cpu_paths:
        return []
    gidx = _gsig(cpu_paths)
    out = []; seen_cpu = set()
    for (cpu, db, addr) in gidx.get(name.upper(), []):
        if cpu == cur_cpu or db == cur_db or cpu in seen_cpu or not addr:
            continue
        sid = _addr_sheet(db, addr)
        if sid is None:
            continue
        seen_cpu.add(cpu)
        out.append((db, sid, addr, "C-NET -> CPU%02d" % cpu))
    return out[:8]


def trace_project(start_db, start_sheet, start_net, direction="both", depth=4,
                  cpu_paths=None, merge=False):
    """merge=False: node = (CPU, sheet, tin hieu) -> hien tung LOP sheet, co canh
    'xuyen sheet'. merge=True: gop cung ten trong 1 DB thanh 1 node (gon)."""
    cpu_paths = cpu_paths or {}
    dbidx = {}

    def didx(db):
        if db not in dbidx:
            dbidx[db] = len(dbidx)
        return dbidx[db]

    nodes = {}
    edges = {}
    anchor = (start_db, start_sheet, start_net)

    def keyof(db, sheet, net):
        nm = _name_of(db, sheet, net)
        if merge and nm:
            return "N|%d|%s" % (didx(db), nm.upper())
        if nm:
            return "S|%d|%s|%s" % (didx(db), sheet, nm.upper())
        return "L|%d|%s|%s" % (didx(db), sheet, net)

    def add(db, sheet, net):
        k = keyof(db, sheet, net)
        if k not in nodes:
            nm = _name_of(db, sheet, net)
            R = _dbc(db)
            nodes[k] = {"id": k, "label": nm or net, "named": bool(nm),
                        "cpu": R["cpuno"], "db": db, "sheet": sheet, "net": net,
                        "sheetlbl": (R["num"].get(sheet) or str(sheet)), "sheets": {sheet}}
        else:
            nodes[k]["sheets"].add(sheet)
        return k

    start_key = add(start_db, start_sheet, start_net)
    seenkey = set()
    MAX_NODES = 800
    q = deque([(start_db, start_sheet, start_net, 0)])
    while q:
        if len(nodes) > MAX_NODES:
            break
        db, sheet, net, d = q.popleft()
        k = keyof(db, sheet, net)
        if k in seenkey:
            continue
        seenkey.add(k)
        # boundary = da toi do sau: van them dau vao/ra TRUC TIEP trong sheet (lam la),
        # de moi node hien du I/O; nhung KHONG di tiep va khong bung xuyen sheet/CPU.
        boundary = d >= depth
        R = _dbc(db)
        nm = _name_of(db, sheet, net)
        occ = ([(sheet, net)] if boundary else
               (R["name2"].get(nm.upper(), [(sheet, net)]) if (merge and nm) else [(sheet, net)]))
        for (s, n) in occ:
            feeds, fedby = _nets(db, s)
            if direction in ("up", "both"):
                for src, labels in _reach(db, s, n, fedby, anchor):
                    ks = add(db, s, src)
                    edges.setdefault((ks, k, "blk"), " -> ".join(reversed(labels)))
                    if not boundary and keyof(db, s, src) not in seenkey:
                        q.append((db, s, src, d + 1))
            if direction in ("down", "both"):
                for dst, labels in _reach(db, s, n, feeds, anchor):
                    kd = add(db, s, dst)
                    edges.setdefault((k, kd, "blk"), " -> ".join(labels))
                    if not boundary and keyof(db, s, dst) not in seenkey:
                        q.append((db, s, dst, d + 1))
        if boundary:
            continue
        # xuyen SHEET (chi che do tach): noi cung line-name o sheet khac trong cung DB
        if not merge and nm:
            up_nm = nm.upper()
            pa = up_nm in _produced_names(db, sheet)
            for (s2, n2) in R["name2"].get(up_nm, []):
                if s2 == sheet:
                    continue
                kb = add(db, s2, n2)
                pb = up_nm in _produced_names(db, s2)
                if pb and not pa:
                    edges.setdefault((kb, k, "xsheet"), "sheet %s" % (R["num"].get(sheet) or sheet))
                else:
                    edges.setdefault((k, kb, "xsheet"), "sheet %s" % (R["num"].get(s2) or s2))
                if keyof(db, s2, n2) not in seenkey:
                    q.append((db, s2, n2, d + 1))
        # xuyen CPU (C-NET)
        if nm and cpu_paths:
            for (pdb, ps, pnet, plabel) in _cross_cpu(nm, db, R["cpuno"], cpu_paths):
                kp = add(pdb, ps, pnet)
                edges.setdefault((k, kp, "cnet"), plabel)
                if keyof(pdb, ps, pnet) not in seenkey:
                    q.append((pdb, ps, pnet, d + 1))

    for v in nodes.values():
        v["sheets"] = sorted(v["sheets"])
    elist = [{"src": s, "dst": d, "block": b, "kind": kd} for (s, d, kd), b in edges.items()]
    return list(nodes.values()), elist, start_key


# ---------------- che do HIEN KHOI HAM (do thi luong phan tin hieu <-> khoi) ----------------
_LMAP = {}


def _logic_maps(db, sheet):
    """Cho 1 sheet: prod(net->bid san sinh), cons(net->[bid tieu thu]),
    bio(bid->(ins, outs, code, sym))."""
    key = (db, sheet)
    if key in _LMAP:
        return _LMAP[key]
    c = D.connect(db).cursor()
    MP = SR._macro_pins()
    binfo = {}
    for bid, sym, code in c.execute(
            "SELECT BLOCK_ID,SYMBOL,MACROCODE FROM CAD_BLOCK WHERE ID=? ORDER BY BLOCK_ID", (sheet,)):
        binfo[bid] = (sym or "", (code or "").upper())
    pins = defaultdict(list)
    for bid, pn, sig in c.execute(
            "SELECT p.BLOCK_ID,p.PINNO,p.SIGNALID FROM CAD_BLOCK_PIN p "
            "JOIN CAD_BLOCK b ON p.BLOCK_ID=b.BLOCK_ID WHERE b.ID=? ORDER BY p.PINNO", (sheet,)):
        pins[bid].append((pn, D._clean(sig)))
    prod = {}; cons = defaultdict(list); bio = {}
    for bid, pl in pins.items():
        sym, code = binfo[bid]
        if code == TERM:
            continue
        mdef = MP.get(sym)
        n = len(pl)
        ins = []; outs = []
        for idx, (pn, net) in enumerate(pl):
            if not net:
                continue
            if _pin_out(mdef, pn, idx, n):
                outs.append(net)
            else:
                ins.append(net)
        bio[bid] = (ins, outs, code, sym)
        for o in outs:
            prod.setdefault(o, bid)
        for i in ins:
            cons[i].append(bid)
    m = {"prod": prod, "cons": cons, "bio": bio}
    _LMAP[key] = m
    return m


def trace_blocks(db0, sheet0, start_net, direction="both", depth=6, cpu_paths=None, project=False):
    """Do thi GIONG LOGIC: node = tin hieu HOAC khoi ham; tin hieu -> [khoi] -> tin hieu.
    project=True: noi lien sheet qua ten + lien CPU qua C-NET."""
    cpu_paths = cpu_paths or {}
    dbidx = {}

    def didx(dbx):
        dbidx.setdefault(dbx, len(dbidx))
        return dbidx[dbx]

    nodes = {}
    edges = set()

    def sig_key(dbx, sh, net):
        nm = _name_of(dbx, sh, net)
        if project and nm:
            return "S|%d|%s" % (didx(dbx), nm.upper())
        return "S|%d|%s|%s" % (didx(dbx), sh, net)

    def blk_key(dbx, bid):
        return "K|%d|%s" % (didx(dbx), bid)

    def add_sig(dbx, sh, net):
        k = sig_key(dbx, sh, net)
        if k not in nodes:
            nm = _name_of(dbx, sh, net); R = _dbc(dbx)
            nodes[k] = {"id": k, "label": nm or net, "named": bool(nm), "kind": "sig",
                        "cpu": R["cpuno"], "db": dbx, "sheet": sh, "net": net,
                        "sheetlbl": R["num"].get(sh) or str(sh), "sheets": {sh}}
        else:
            nodes[k]["sheets"].add(sh)
        return k

    def add_blk(dbx, sh, bid, code, sym):
        k = blk_key(dbx, bid)
        if k not in nodes:
            R = _dbc(dbx)
            nodes[k] = {"id": k, "label": D.macro_name(code, sym), "named": False,
                        "kind": "block", "block": D.macro_name(code, sym), "code": code,
                        "cpu": R["cpuno"], "db": dbx, "sheet": sh,
                        "sheetlbl": R["num"].get(sh) or str(sh), "sheets": {sh}}
        else:
            nodes[k]["sheets"].add(sh)
        return k

    start_key = add_sig(db0, sheet0, start_net)
    q = deque()
    if direction in ("down", "both"):
        q.append(("sig", db0, sheet0, start_net, 0, "dn"))
    if direction in ("up", "both"):
        q.append(("sig", db0, sheet0, start_net, 0, "up"))
    seen = set()
    MAX = 900
    while q:
        if len(nodes) > MAX:
            break
        typ, dbx, sh, ref, d, dr = q.popleft()
        stt = (typ, didx(dbx), sh if typ == "blk" else None, ref, dr)
        sk = (typ, dbx, sh, ref, dr)
        if sk in seen or d >= depth:
            continue
        seen.add(sk)
        if typ == "sig":
            ksig = sig_key(dbx, sh, ref)
            R = _dbc(dbx)
            nm = _name_of(dbx, sh, ref)
            occ = R["name2"].get(nm.upper(), [(sh, ref)]) if (project and nm) else [(sh, ref)]
            for (s2, n2) in occ:
                M = _logic_maps(dbx, s2)
                if dr == "dn":
                    for c in M["cons"].get(n2, []):
                        code, sym = M["bio"][c][2], M["bio"][c][3]
                        kb = add_blk(dbx, s2, c, code, sym)
                        edges.add((ksig, kb, "blk"))
                        q.append(("blk", dbx, s2, c, d + 1, "dn"))
                else:
                    pb = M["prod"].get(n2)
                    if pb is not None:
                        code, sym = M["bio"][pb][2], M["bio"][pb][3]
                        kb = add_blk(dbx, s2, pb, code, sym)
                        edges.add((kb, ksig, "blk"))
                        q.append(("blk", dbx, s2, pb, d + 1, "up"))
            if project and nm and cpu_paths:
                for (pdb, ps, pnet, plabel) in _cross_cpu(nm, dbx, R["cpuno"], cpu_paths):
                    kp = add_sig(pdb, ps, pnet)
                    edges.add((ksig, kp, "cnet") if dr == "dn" else (kp, ksig, "cnet"))
                    q.append(("sig", pdb, ps, pnet, d + 1, dr))
        else:  # block
            M = _logic_maps(dbx, sh)
            ins, outs, code, sym = M["bio"][ref]
            kb = blk_key(dbx, ref)
            if dr == "dn":
                for o in outs:
                    ks = add_sig(dbx, sh, o)
                    edges.add((kb, ks, "blk"))
                    q.append(("sig", dbx, sh, o, d + 1, "dn"))
            else:
                for i in ins:
                    ks = add_sig(dbx, sh, i)
                    edges.add((ks, kb, "blk"))
                    q.append(("sig", dbx, sh, i, d + 1, "up"))

    for v in nodes.values():
        v["sheets"] = sorted(v["sheets"])
    elist = [{"src": s, "dst": d, "block": "", "kind": k} for (s, d, k) in edges]
    return list(nodes.values()), elist, start_key
