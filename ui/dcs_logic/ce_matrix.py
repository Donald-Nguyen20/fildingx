# -*- coding: utf-8 -*-
"""MA TRAN NHAN QUA (Cause & Effect Matrix): cho nhieu tin hieu DICH (effect, vd MFT,
ETS, RUNBACK), tim TAT CA nguyen nhan GOC dan toi tung tin hieu (xuyen sheet/CPU), gom
lai thanh 1 bang: hang = nguyen nhan, cot = tin hieu dich, o = OR (1 minh du) hay AND
(can du ca nhom). Xay tren core/cond_tree.py (da co san, dung cho "Xem dieu kien" cu).

Chi doc DB, khong sua gi.
"""
from __future__ import annotations
from . import cond_tree as CT
from . import signal_graph as SG
from . import project_index as PI


def resolve_target_candidates(name, db_paths=None):
    """Tim cac diem BAT DAU hop le cho 1 ten tin hieu DICH: (db, sheet) ma tin hieu
    ten NAY thuc su duoc SINH RA (co khoi xuat ra no tren sheet do) - khac voi
    project_index.locate_full() tra ve MOI noi ten do XUAT HIEN (ca noi chi la dau
    vao/tham chieu). Tra ve list dict {db, sheet, net, label, cpuname, sheetlbl}."""
    name = (name or "").strip()
    if not name:
        return []
    try:
        PI.ensure(db_paths or [])
    except Exception:
        pass
    # ten trong CAD_ID co the khac hoa/thuong voi nguoi go -> thu chinh xac truoc,
    # roi thu UPPER(), cuoi cung LIKE (khong phan biet hoa/thuong) roi loc lai dung ten
    rows = PI.locate_full(name)
    if not rows and name.upper() != name:
        rows = PI.locate_full(name.upper())
    if not rows:
        rows = [(cpuname, cpuno, slbl, db, sheet, sigid)
                for (nm, cpuname, cpuno, slbl, db, sheet, sigid) in PI.find(name, limit=50)
                if nm.strip().upper() == name.upper()]
    out = []
    seen = set()
    for (cpuname, cpuno, slbl, db, sheet, sigid) in rows:
        key = (db, sheet)
        if key in seen:
            continue
        try:
            if name.upper() not in SG._produced_names(db, sheet):
                continue
        except Exception:
            continue
        seen.add(key)
        out.append({"db": db, "sheet": sheet, "net": sigid, "label": name,
                    "cpuname": cpuname, "sheetlbl": slbl})
    return out


def expand_full(db, sheet, net, cpu_paths=None, max_expansions=400):
    """build() roi lap expand() tren MOI la co the mo rong, cho toi khi het (hoac
    cham tran max_expansions / vong lap). 2 loai la duoc mo rong:
    - kind='cross': tin hieu san xuat o SHEET/CPU khac -> nhay sang do dung logic that.
    - type='opaque' (khoi KHONG co trong logic_sem.json, vd khoi TAG/Data-Link nhu
      DDL_TG dang dung de xuat MFT ra ngoai) -> mo tiep 1 buoc vao chan vao cua no, vi
      da qua thuc te cac khoi nay chi la vo boc/chuyen tiep, nguyen nhan THAT (AND/OR/
      SR...) nam ngay phia sau. KHONG mo rong 'cmp' (so sanh nguong) - do la 1 nguyen
      nhan CO TEN hop le (vd "FURN PRS HI HI"), dung lai dung y nghia cho ma tran."""
    cpu_paths = cpu_paths or {}
    ctr = [0]
    tree = CT.build(db, sheet, net, depth=40, cpu_paths=cpu_paths, _ctr=ctr)
    visited = set()
    budget = [max_expansions]

    def walk(node):
        if budget[0] <= 0:
            return node
        t = node.get("type")
        if t == "gate":
            node["children"] = [walk(c) for c in node["children"]]
            return node
        if t == "leaf" and node.get("kind") == "cross" and node.get("expandable"):
            key = ("cross", node.get("db"), (node.get("label") or "").upper())
            if key in visited:
                node["kind"] = "source"
                node["note"] = "vong lap xuyen sheet (da gap ten nay roi)"
                return node
            visited.add(key)
            budget[0] -= 1
            sub = CT.expand(node, cpu_paths=cpu_paths, id_base=ctr[0], depth=40)
            if sub is None:
                return node
            ctr[0] = CT.max_id(sub) + 1
            return walk(sub)
        if t == "opaque":
            # CHI mo qua khoi vo boc THAT SU don gian (dung 1 chan vao co ten, vd khoi
            # TAG/Data-Link nhu DDL_TG dung de xuat tin hieu ra ngoai). Khoi opaque co
            # TU 2 chan vao tro len la 1 khoi chuc nang THAT (vd bang trang thai gop
            # nhieu tin hieu khong lien quan) - mo qua se lan sang logic KHONG lien
            # quan (da thay thuc te: no ra hang tram dong khong dinh dang gi den MFT).
            # Dung lai o do, coi no la 1 nguyen nhan co ten (dung y nghia hon).
            real_ins = [n for n in node.get("in_nets", []) if n]
            if len(real_ins) != 1:
                return node
            key = ("opaque", node.get("db"), node.get("sheet"), node.get("net"))
            if key in visited:
                return node
            visited.add(key)
            budget[0] -= 1
            sub = CT.expand(node, cpu_paths=cpu_paths, id_base=ctr[0], depth=40)
            if sub is None or not sub.get("children"):
                return node        # khong mo rong duoc (khong co chan vao co ten) -> giu nguyen la 1 hang
            ctr[0] = CT.max_id(sub) + 1
            sub["children"] = [walk(c) for c in sub["children"]]
            return sub
        return node

    return walk(tree)


_REL_TXT = {">=": "≥", "<=": "≤", ">": ">", "<": "<", "==": "="}


def _redundancy_base(cpuname):
    """Ten 'goc' cua 1 CPU bo hau to kenh A/B: 'BPS_A'->'BPS', 'TSQ B'->'TSQ',
    'BSQ-B'->'BSQ'. Dung de nhan ra CAP DU PHONG that su (BPS_A vs BPS_B), thay vi
    so bua moi CPU co nhac toi tin hieu dich (nhieu CPU chi NHAN lai tin hieu do,
    khong he chua logic sinh ra no - so voi chung se ra canh bao sai hang loat)."""
    import re as _re
    s = (cpuname or "").strip().upper()
    m = _re.match(r"^(.*?)[ _\-]?([AB])$", s)
    return (m.group(1), m.group(2)) if m else (s, "")


def _channel_specific(label):
    """True neu chinh TEN nguyen nhan da ghi ro no thuoc kenh A hay B (vd 'MFT (BMS
    CTLR A)', 'CPU A SELECTED'). Nhung dong nay chi co o 1 kenh la DUNG THIET KE,
    khong phai lech cau hinh -> khong canh bao."""
    import re as _re
    s = (label or "").upper()
    return bool(_re.search(r"\b(CTLR|CPU|CH|CHANNEL|SIDE|CTRL)\s*[AB]\b", s)
                or _re.search(r"[ (\-][AB]\)?\s*$", s))


def _redundant_groups(cpus):
    """{ten_goc: {cpu1, cpu2}} chi giu nhom co DU CA 2 kenh A va B."""
    g = {}
    for c in cpus:
        base, ch = _redundancy_base(c)
        if ch:
            g.setdefault(base, {})[ch] = c
    return {b: set(d.values()) for b, d in g.items() if len(d) >= 2}


def _cmp_detail(node):
    """Voi la CMP (so sanh nguong analog): tra chuoi '<tin hieu do> ≥ <nguong> <don vi>'
    lay tu THAM SO THAT cua khoi, vd 'DRUM LEVEL ≥ 250 mm'. Rong neu khong doc duoc.
    Lam tai lieu dung duoc ngay, khong phai mo sheet tra nguong."""
    db = node.get("db"); sh = node.get("sheet"); net = node.get("net")
    if not db or sh is None or not net:
        return ""
    try:
        from . import sheet_sim as SS
        for onet, innet, rel, thr in SS.comparators(db, sh):
            if onet != net:
                continue
            src = (SG._name_of(db, sh, innet) or innet) if innet else ""
            r = _REL_TXT.get(rel, rel or "so sanh")
            if thr is None:
                return ("%s %s nguong (dong)" % (src, r)).strip()
            v = ("%g" % thr) if isinstance(thr, float) else str(thr)
            unit = _unit_of(db, sh, innet)
            return ("%s %s %s%s" % (src, r, v, (" " + unit) if unit else "")).strip()
    except Exception:
        pass
    return ""


def _unit_of(db, sheet, net):
    """Don vi ky thuat cua 1 tin hieu analog (CAD_ID.SENSOR dang '0 100 %')."""
    if not net:
        return ""
    try:
        import sqlite3
        from . import dbreader as D2
        c = D2.connect(db).cursor()
        r = c.execute("SELECT SENSOR FROM CAD_ID WHERE ID=? AND SIGNALID=?",
                      (sheet, net)).fetchone()
        s = (D2._clean(r[0]) if r else "") or ""
        parts = s.split()
        return parts[-1] if len(parts) >= 2 else ""
    except Exception:
        return ""


def _block_desc(node):
    """Mo ta thay the khi nguyen nhan KHONG co ten (chi con ma net tho, vd 'T578-07'):
    dung ten khoi sinh ra no + cac dau vao co ten, de dong do van doc duoc."""
    blk = node.get("block") or ""
    ins = []
    for n in (node.get("in_nets") or []):
        if not n:
            continue
        nm = SG._name_of(node.get("db"), node.get("sheet"), n)
        if nm:
            ins.append(nm)
    if blk and ins:
        return "%s cua: %s" % (blk, ", ".join(ins[:3]))
    return blk or ""


def _is_raw_name(lb):
    """True neu nhan chi la ma net tho (T578-07, a1, DJ0634...) chu khong phai ten
    mo ta - dung de xep xuong cuoi bang va co gang thay bang mo ta khoi."""
    s = (lb or "").strip()
    if not s:
        return True
    if " " in s:                      # co khoang trang -> gan nhu chac chan la ten mo ta
        return False
    import re as _re
    return bool(_re.match(r"^[A-Za-z]{0,3}\d[\w\-]*$", s))


def _label_of(node):
    lb = node.get("label") or node.get("net") or "?"
    if node.get("type") == "cmp" or node.get("kind") == "cmp":
        det = _cmp_detail(node)
        if det:
            # giu ca ten tin hieu ket qua (vd 'FURN PRS HI HI') lan dieu kien that
            lb = "%s  [%s]" % (lb, det) if not _is_raw_name(lb) else det
    elif _is_raw_name(lb):
        d = _block_desc(node)
        if d:
            lb = "%s (%s)" % (lb, d)
    return ("NOT " + lb) if node.get("neg") else lb


def _row_key(node):
    # Chi dung TEN lam khoa (bo qua db) khi co ten - de nguyen nhan CUNG TEN tu 2
    # CPU du phong A/B (logic giong het nhau) gop thanh 1 dong duy nhat trong ma
    # tran, thay vi hien lap doi. Khong co ten (net thuan tuy) thi van phan biet
    # theo db/sheet/net vi khong the biet chac 2 net khac db la "cung 1 nguyen nhan".
    lb = node.get("label") or node.get("net") or ""
    if lb:
        return ("lbl", lb.strip().upper())
    return ("net", node.get("db"), node.get("sheet"), node.get("id"))


def _collect(node, target_disp, rows, and_stack):
    """Duyet cay (da mo rong xuyen sheet), gom moi la (leaf/cmp/opaque) thanh 1 hang
    trong `rows` (dict key -> row), danh dau OR / AND(nhom) cho cot target_disp.
    and_stack: list [(group_id, [nhan cac anh em AND khac])] tu goc toi node hien tai."""
    t = node.get("type")
    if t == "gate":
        op = node.get("op")
        if op == "SR":
            # chot SR (latch): chi nhanh SET (children[0]) moi la NGUYEN NHAN lam no
            # len 1. Nhanh RESET (children[1]) la dieu kien XOA chot (VD dieu kien cho
            # phep RESET MFT) - hoan toan KHAC y nghia "cai gi gay ra no", nen KHONG
            # theo vao, tranh lan sang toan bo logic permissive/interlock khong lien quan.
            ch = node.get("children") or []
            if ch:
                _collect(ch[0], target_disp, rows, and_stack)
            return
        if op == "AND":
            gid = "G%d" % node.get("id", 0)
            child_labels = [_label_of(c) for c in node.get("children", [])]
            for i, c in enumerate(node.get("children", [])):
                others = [child_labels[j] for j in range(len(child_labels)) if j != i]
                _collect(c, target_disp, rows, and_stack + [(gid, others)])
        else:
            for c in node.get("children", []):
                _collect(c, target_disp, rows, and_stack)
        return
    if t == "const":
        return
    if t == "opaque" and node.get("expanded") and node.get("children"):
        # khoi vo boc (TAG/Data-Link...) da duoc mo rong xuyen qua chan vao -> chi la
        # trung gian, KHONG tinh la 1 nguyen nhan rieng, di xuyen qua den cac con that
        for c in node["children"]:
            _collect(c, target_disp, rows, and_stack)
        return
    key = _row_key(node)
    row = rows.get(key)
    if row is None:
        row = {"label": _label_of(node), "db": node.get("db"), "sheet": node.get("sheet"),
               "sheetlbl": node.get("sheetlbl"), "net": node.get("net"),
               "kind": node.get("kind") or t, "marks": {}, "source": "tree"}
        rows[key] = row
    if and_stack:
        gid, others = and_stack[-1]
        row["marks"][target_disp] = {"kind": "and", "group": gid, "with": others}
    else:
        row["marks"][target_disp] = {"kind": "or"}


def tag_fid_causes(name, db_paths):
    """Tim nguyen nhan GOC qua CAD_TAG_FID: nhan da duoc CON NGUOI ghi san dang
    '<mo ta nguyen nhan> (<TEN TIN HIEU DICH>)', vd 'LOSS OF BOTH FDF (MFT)' cho
    tin hieu dich 'MFT'. Day la quy uoc lam tai lieu TRIP CIRCUIT rat pho bien trong
    du an nay - sach va dung y con nguoi da xac nhan, nen UU TIEN dung truoc khi phai
    suy luan tu day (xem build_matrix). Chi ap dung duoc voi tin hieu co quy uoc nay
    (thuong la TRIP/BAO DONG tong hop qua khoi TAG, khong phai moi tin hieu deu co).
    Tra ve list dict {label, db, sheet, block_id} da loai trung theo (db, nhan)."""
    import sqlite3
    from . import dbreader as D
    out = []
    seen = set()
    suffix = "(%s)" % (name or "").strip().upper()
    for db in (db_paths or []):
        try:
            c = sqlite3.connect(D.ro_uri(db), uri=True).cursor()   # read-only
            rows = c.execute(
                "SELECT DISTINCT f.BLOCK_ID, f.FIDVALUE, b.ID "
                "FROM CAD_TAG_FID f JOIN CAD_BLOCK b ON f.BLOCK_ID=b.BLOCK_ID "
                "WHERE UPPER(f.FIDVALUE) LIKE ?", ("%" + suffix,)).fetchall()
        except Exception:
            continue
        for bid, fv, sheet in rows:
            fv = (D._clean(fv) or "").strip()
            if not fv.upper().endswith(suffix):
                continue
            label = fv[: -len(suffix)].strip()
            if not label:
                continue
            key = (db, label.upper())
            if key in seen:
                continue
            seen.add(key)
            out.append({"label": label, "db": db, "sheet": sheet, "block_id": bid})
    return out


_TRIP_KEYWORDS = ("TRIP", "MFT", "RNBK", "RUNBACK", "ETS", "PROTECT", "SHUT DOWN",
                  "SHUTDOWN", "S/D", "EMERG", "INTERLOCK", "INTLK", "LOCKOUT",
                  "MASTER FUEL", "BOILER TRIP", "TURBINE TRIP", "ABN")


def term_label(node, depth=0):
    """Nhan doc duoc cho 1 dieu kien trong dang OR-cua-AND. Khac _label_of o cho:
    cong NOT / cong long nhau bi coi la 1 dieu kien thi phai dien giai NOI DUNG cua
    no ('KHONG (X)', 'XOR cua: A, B') thay vi chi in ten net trung gian (a2, b3...)."""
    if node is None:
        return "?"
    if node.get("type") == "gate" and depth < 3:
        op = node.get("op")
        ch = node.get("children") or []
        if op == "NOT" and ch:
            return "KHONG (%s)" % term_label(ch[0], depth + 1)
        if op in ("AND", "OR") and ch:
            sep = " VA " if op == "AND" else " HOAC "
            inner = sep.join(term_label(c, depth + 1) for c in ch[:4])
            if len(ch) > 4:
                inner += ", ..."
            return "(%s)" % inner
        if ch:
            return "%s cua: %s" % (op or node.get("block") or "?",
                                   ", ".join(term_label(c, depth + 1) for c in ch[:3]))
    return _label_of(node)


def to_dnf(node, max_terms=10, max_products=120, _budget=None):
    """Rut gon cay dieu kien ve dang "TONG CUA CAC TICH" (OR cua cac nhom AND) -
    dung cach nguoi van hanh doc mach bao ve:

        DICH = A  hoac  B  hoac  (C va D va E)  hoac ...

    Bo het cac ten net trung gian, khoi vo boc, cong long nhau nhieu tang - chi con
    danh sach cac CACH lam tin hieu dich len 1. Moi phan tu tra ve la 1 LIST cac node
    la; list 1 phan tu = nguyen nhan doc lap (OR), nhieu phan tu = phai du ca nhom (AND).
    Co chan tran de cay lon khong no to hop (max_terms/max_products)."""
    if _budget is None:
        _budget = [4000]
    _budget[0] -= 1
    if _budget[0] <= 0 or node is None:
        return []
    t = node.get("type")
    if t == "const":
        return []
    if t == "gate":
        op = node.get("op")
        ch = node.get("children") or []
        if op == "SR":
            # chi nhanh SET moi la nguyen nhan lam tin hieu len 1 (nhanh RESET la dieu
            # kien XOA chot - khac hoan toan y nghia "cai gi gay ra no")
            return to_dnf(ch[0], max_terms, max_products, _budget) if ch else []
        if op == "NOT":
            # phu dinh 1 cong long nhau -> khong khai trien De Morgan (se no va kho doc),
            # coi ca cum la 1 dieu kien co ten
            return [[node]]
        if op == "OR":
            out = []
            for c in ch:
                for p in to_dnf(c, max_terms, max_products, _budget):
                    if len(out) >= max_products:
                        return out
                    out.append(p)
            return out
        if op == "AND":
            out = [[]]
            for c in ch:
                sub = to_dnf(c, max_terms, max_products, _budget)
                if not sub:
                    continue
                new = []
                for base in out:
                    for p in sub:
                        if len(base) + len(p) > max_terms:
                            continue
                        if len(new) >= max_products:
                            break
                        merged = list(base)
                        for x in p:
                            if x not in merged:
                                merged.append(x)
                        new.append(merged)
                    if len(new) >= max_products:
                        break
                out = new or out
            return [p for p in out if p]
        # XOR va cac cong khac: coi ca cum la 1 dieu kien
        return [[node]]
    if t == "opaque" and node.get("children"):
        out = []
        for c in node["children"]:
            for p in to_dnf(c, max_terms, max_products, _budget):
                if len(out) >= max_products:
                    return out
                out.append(p)
        return out
    return [[node]]          # la / cmp / opaque chua mo rong = 1 nguyen nhan co ten


# --------------------------------------------------------------------- XEM THEO LOP
# build_matrix() tra ve nguyen nhan GOC (da bung het xuyen sheet/CPU) - dung de lam
# TAI LIEU va xuat Excel. Nhung cay that co the 400+ khoi (MFT day), doc bang mat
# khong noi. Che do LOP tra loi tung buoc: "cai gi TRUC TIEP gay ra X" -> bam vao 1
# nguyen nhan -> "cai gi gay ra CAI DO" -> ...
#
# Diem mau chot: 1 lop KHONG phai 1 tang cua cay. Cay tho day net trung gian vo nghia
# (T578-07, a1) va khoi vo boc (DDL_TG) - neu chia theo tang, nguoi dung phai bam 3-4
# lan moi toi 1 nguyen nhan doc duoc. Nen 1 lop = di toi TIN HIEU CO TEN gan nhat,
# tu nhay qua moi thu trung gian.

_DRILL_CACHE = {}


def _named_stop(node):
    """Diem DUNG cua 1 lop: la/cmp/opaque (hien nhien), hoac 1 cong logic co dau ra
    MANG TEN MO TA (tin hieu trung gian co y nghia, vd 'FUEL TRIP') - dung lai o do
    de nguoi doc thay tung buoc, thay vi phang thang xuong tan nguyen nhan goc."""
    if node.get("type") != "gate":
        return True
    lb = (node.get("label") or "").strip()
    return bool(lb) and not _is_raw_name(lb)


def layer_dnf(node, max_terms=10, max_products=120, _budget=None, _root=True):
    """Giong to_dnf nhung CHI di DUNG 1 LOP: dung ngay khi gap tin hieu co ten
    (_named_stop). Tra ve list cac 'san pham': moi cai la list node = 1 nhom AND
    (list 1 phan tu = nguyen nhan doc lap). Cac san pham quan he OR voi nhau."""
    if _budget is None:
        _budget = [2000]
    _budget[0] -= 1
    if _budget[0] <= 0 or node is None:
        return []
    if node.get("type") == "const":
        return []
    if not _root and _named_stop(node):
        return [[node]]
    ch = node.get("children") or []
    if node.get("type") != "gate":
        # opaque da duoc bung (co con) va dang o goc -> di tiep vao cac con
        out = []
        for c in ch:
            for p in layer_dnf(c, max_terms, max_products, _budget, False):
                if len(out) >= max_products:
                    return out
                out.append(p)
        return out
    op = node.get("op")
    if op == "SR":
        # chi nhanh SET moi la nguyen nhan lam tin hieu len 1 (nhanh RESET la dieu
        # kien XOA chot - khac hoan toan y nghia "cai gi gay ra no")
        return layer_dnf(ch[0], max_terms, max_products, _budget, False) if ch else []
    if op == "NOT":
        return layer_dnf(ch[0], max_terms, max_products, _budget, False) if ch else []
    if op == "OR":
        out = []
        for c in ch:
            for p in layer_dnf(c, max_terms, max_products, _budget, False):
                if len(out) >= max_products:
                    return out
                out.append(p)
        return out
    if op == "AND":
        out = [[]]
        for c in ch:
            sub = layer_dnf(c, max_terms, max_products, _budget, False)
            if not sub:
                continue
            new = []
            for base in out:
                for p in sub:
                    if len(base) + len(p) > max_terms:
                        continue
                    if len(new) >= max_products:
                        break
                    merged = list(base)
                    for x in p:
                        if x not in merged:
                            merged.append(x)
                    new.append(merged)
                if len(new) >= max_products:
                    break
            out = new or out
        return [p for p in out if p]
    return [[c] for c in ch]     # XOR / cong dac biet: liet ke dau vao, cau truc
                                 # chinh xac xem o "So do logic"


def _same_sig(a, b):
    """2 node co phai CUNG 1 tin hieu khong (uu tien so theo ten, vi sau khi nhay
    xuyen sheet thi ma net doi nhung ten thi khong)."""
    la = (a.get("label") or "").strip().upper()
    lb = (b.get("label") or "").strip().upper()
    if la and lb:
        return la == lb
    return ((a.get("db"), a.get("sheet"), a.get("net"))
            == (b.get("db"), b.get("sheet"), b.get("net")))


def can_drill(node):
    """Co the mo them 1 lop duoi nguyen nhan nay khong (kiem tra RE, khong doc DB)."""
    if not node:
        return False
    t = node.get("type")
    k = node.get("kind")
    if t == "gate":
        return bool(node.get("children"))
    if t == "const" or k in ("const", "source", "const-empty"):
        return False
    if t == "cmp" or k == "cmp":
        return False        # so sanh nguong da la 1 nguyen nhan co ten hop le
    if k == "cross":
        return True
    if t == "opaque":
        return any(node.get("in_nets") or [])
    return False


def _layer_from(node, cpu_paths=None, hops=4, _seen=None):
    """Lay 1 lop nguyen nhan bat dau tu `node`.

    Rat hiem khi 1 tin hieu la dau ra TRUC TIEP cua 1 cong AND/OR. Thuc te no thuong la:
      - dau ra 1 khoi TAG/Data-Link (type 'opaque') dung de xuat tin hieu ra ngoai, hoac
      - chi la diem PHAT LAI tren sheet/CPU khac (kind 'cross') - vd MFT o UCS chi la ban
        sao nhan qua C-NET, logic that nam o BMS.
    Nhung diem do KHONG mang thong tin gi cho nguoi doc, nen tu nhay qua (toi da `hops`
    buoc) cho toi khi gap logic that - dung tinh than "1 lop = toi TIN HIEU CO TEN gan
    nhat", khong bat nguoi dung bam xuyen qua cac muc rong."""
    if node is None or hops <= 0:
        return []
    prods = layer_dnf(node, _root=True)
    if prods or not can_drill(node):
        return prods
    _seen = _seen or set()
    key = (node.get("db"), node.get("sheet"), node.get("net"))
    if key in _seen:
        return []
    try:
        sub = CT.expand(node, cpu_paths=cpu_paths or {}, id_base=0, depth=40)
    except Exception:
        return []
    return _layer_from(sub, cpu_paths, hops - 1, _seen | {key})


def drill(node, cpu_paths=None):
    """LOP TIEP THEO cua 1 nguyen nhan. Tra ve list san pham (OR cua cac nhom AND),
    [] neu day (nguyen nhan goc - tin hieu ngoai/so sanh nguong/khong bung them duoc).
    Ket qua duoc nho lai (_DRILL_CACHE) vi UI goi ham nay de biet truoc moi dong con
    mo duoc hay khong."""
    if not can_drill(node):
        return []
    if node.get("type") == "gate":
        return layer_dnf(node, _root=True)       # cung sheet, khong can doc them DB
    key = ("drill", node.get("db"), node.get("sheet"), node.get("net"),
           (node.get("label") or "").strip().upper(), node.get("kind"))
    if key in _DRILL_CACHE:
        return _DRILL_CACHE[key]
    try:
        sub = CT.expand(node, cpu_paths=cpu_paths or {}, id_base=0, depth=40)
    except Exception:
        sub = None
    out = _layer_from(sub, cpu_paths, hops=3) if sub is not None else []
    # Bung ra chinh no = khong tien them buoc nao (vd tin hieu cross tro toi 1 diem
    # phat lai chu khong phai noi co logic) -> coi nhu da toi goc, tranh vong lap.
    out = [p for p in out if not (len(p) == 1 and _same_sig(p[0], node))]
    _DRILL_CACHE[key] = out
    return out


def first_layer(cand, cpu_paths=None):
    """Lop 1 cua 1 tin hieu DICH: cac nguyen nhan TRUC TIEP gay ra no.
    cand = {'db','sheet','net',...} nhu resolve_target_candidates() tra ve."""
    key = ("l1", cand.get("db"), cand.get("sheet"), cand.get("net"))
    if key in _DRILL_CACHE:
        return _DRILL_CACHE[key]
    try:
        tree = CT.build(cand["db"], cand["sheet"], cand["net"], depth=40,
                        cpu_paths=cpu_paths or {})
    except Exception:
        return []
    out = _layer_from(tree, cpu_paths, hops=4)
    _DRILL_CACHE[key] = out
    return out


def pick_source(cands, cpu_paths=None, max_try=8):
    """Chon ung vien nao la NGUON LOGIC THAT cua tin hieu.

    1 ten nhu MFT duoc 'san xuat' o rat nhieu cho (19 cho voi DB Unit 1): phan lon chi
    la diem PHAT LAI - nhan qua C-NET roi xuat ra I/O hoac sang sheet khac. Dem so
    nguyen nhan lop 1 khong phan biet duoc, vi diem phat lai cung ra 2 'nguyen nhan'
    (chinh no + tiep diem QB cua no). Dau hieu that su la co nguyen nhan lop 1 nao con
    BUNG THEM duoc hay khong - ngo cut thi khong. Tra ve (candidate, products_lop1)."""
    best, best_key, best_l1 = None, None, []
    for c in (cands or [])[:max_try]:
        l1 = first_layer(c, cpu_paths)
        deep = sum(1 for prod in l1 for n in prod if drill(n, cpu_paths))
        key = (deep, sum(len(p) for p in l1))
        if best_key is None or key > best_key:
            best, best_key, best_l1 = c, key, l1
    return best, best_l1


def known_targets(db_paths, keywords=True):
    """Danh sach TEN TIN HIEU DICH goi y de dua vao ma tran, tu 2 nguon:
      1) CAD_TAG_FID - quy uoc '<nguyen nhan> (<TEN DICH>)' do ky su ghi san (chac chan
         nhat, kem so nguyen nhan da ghi nhan);
      2) cac tin hieu co ten mang tu khoa bao ve/trip (TRIP, RNBK, ETS, INTERLOCK...)
         va THUC SU duoc san xuat o dau do - dung khi du an khong theo quy uoc (1).
    Chi giu ten co that trong chi muc (bo nhan rac kieu 'A-PH', 'D/E').
    Tra [(ten, so_nguyen_nhan_da_ghi_nhan)] - 0 nghia la goi y theo tu khoa."""
    import sqlite3
    import re as _re
    from . import dbreader as D2
    cnt = {}
    for db in (db_paths or []):
        try:
            c = sqlite3.connect(D2.ro_uri(db), uri=True).cursor()   # read-only
            rows = c.execute("SELECT FIDVALUE FROM CAD_TAG_FID "
                             "WHERE FIDVALUE LIKE '%(%)'").fetchall()
        except Exception:
            continue
        for (fv,) in rows:
            fv = (D2._clean(fv) or "").strip()
            m = _re.search(r"\(([^()]{2,40})\)\s*$", fv)
            if not m:
                continue
            head = fv[: m.start()].strip()
            if not head:
                continue                       # '(X)' don doc - khong phai quy uoc nay
            nm = m.group(1).strip().upper()
            if not nm or nm.replace(" ", "").isdigit():
                continue
            cnt[nm] = cnt.get(nm, 0) + 1
    # Quy uoc '(...)' con duoc dung cho nhieu muc dich khac (nhan pha 'A-PH', 'D/E',
    # don vi...), khong phai deu la tin hieu dich. Chi giu ten NAO THUC SU la 1 tin
    # hieu co that trong du an (co trong chi muc) - bo het nhan rac.
    out = []
    seen = set()
    try:
        PI.ensure(db_paths or [])
    except Exception:
        pass
    for k, v in cnt.items():
        if v < 2:
            continue                        # 1 dong le thuong la trung hop
        try:
            if not PI.locate(k):
                continue                    # khong phai ten tin hieu -> bo
        except Exception:
            pass
        seen.add(k)
        out.append((k, v))
    out.sort(key=lambda t: (-t[1], t[0]))
    if not keywords:
        return out
    # nguon 2: quet chi muc theo tu khoa bao ve/trip
    kw_rows = []
    for kw in _TRIP_KEYWORDS:
        try:
            for (nm, _cpuname, _cpuno, _slbl, _db, _sh, _sid) in PI.find(kw, limit=400):
                nm = (nm or "").strip()
                u = nm.upper()
                if not nm or u in seen:
                    continue
                seen.add(u)
                kw_rows.append((nm, 0))
        except Exception:
            continue
    kw_rows.sort(key=lambda t: t[0].upper())
    return out + kw_rows


def _merge_mark(row, disp, new_mark, cpuname=None):
    """Ghi mark[disp] cho 1 hang, gop dung khi CUNG 1 ten nguyen nhan duoc gap lai
    (vd tu nhieu CPU/candidate khac nhau cho cung 1 tin hieu dich). KHONG duoc ghi
    de vo dieu kien theo thu tu xu ly (bug da gap: candidate xu ly SAU de len OR
    lam mat thong tin candidate truoc do tinh la AND) - AND phai THANG OR, vi AND
    la ket qua "chat che" hon (nguyen nhan nay o it nhat 1 noi KHONG du 1 minh gay
    hieu ung, nen khong the coi la OR doc lap chung cho ca 2 noi). Van luu lai o
    dau (CPU nao) tung thay OR truc tiep, de sau nay co the chu thich neu can."""
    old = row["marks"].get(disp)
    cpus = (old or {}).get("_or_at") or set()
    seen_at = (old or {}).get("_seen_at") or set()      # MOI CPU da gap nguyen nhan nay
    kinds = (old or {}).get("_kinds") or set()          # cac kieu da gap ('or'/'and')
    if cpuname:
        seen_at = seen_at | {cpuname}
    kinds = kinds | {new_mark.get("kind")}
    if new_mark.get("kind") == "or" and cpuname:
        cpus = cpus | {cpuname}

    def _stamp(m):
        m["_or_at"] = cpus
        m["_seen_at"] = seen_at
        m["_kinds"] = kinds
        return m

    if old is None:
        row["marks"][disp] = _stamp(dict(new_mark))
        return
    if old.get("kind") == "and":
        _stamp(old)
        return
    if new_mark.get("kind") == "and":
        row["marks"][disp] = _stamp(dict(new_mark))
        return
    _stamp(old)


def build_matrix(targets, cpu_paths=None, mode="or"):
    """mode: 'or'     = chi nguyen nhan doc lap (1 minh du gay hieu ung) - mac dinh cu;
             'or_and' = them ca nguyen nhan AND, gom theo nhom Gxx (can du ca nhom moi
                        gay hieu ung). BAT BUOC phai co cho mach trip dung 2-out-of-3
                        hoac khoa lien dong: neu chi loc OR thi ma tran co the TRONG
                        HOAN TOAN du mach van co day du nguyen nhan (da gap that voi
                        TURBINE TRIP COMMAND cua EHC);
             'all'    = nhu 'or_and' (giu de mo rong ve sau).
    targets: [{'disp', 'cands':[{'db','sheet','net'},...]}] (disp = ten hien cot,
    VD 'MFT'; 'cands' = TAT CA noi (db/sheet) thuc su san xuat ra tin hieu ten do -
    khong con bat nguoi dung chon 1 noi duy nhat, ma GOP nguyen nhan tu MOI noi tim
    duoc, vd 2 CPU du phong A/B cung san xuat 1 ten tin hieu se duoc gop chung).
    Nguyen nhan TRUNG TEN (vd tu 2 CPU du phong A/B co logic giong het nhau) chi
    hien 1 dong duy nhat trong bang - khong lap doi (khoa theo TEN, khong theo db).
    QUAN TRONG: neu cung 1 ten nguyen nhan duoc tinh khac nhau o cac candidate/CPU
    (vd 1 he thong coi no la AND-voi-cai-khac, he thong khac coi no la OR-truc-tiep -
    day KHONG phai luon la CPU du phong giong het nhau, co the la 2 he thong khac
    nhau nhu UCS va BMS), thi AND THANG OR khi gop (_merge_mark) - an toan hon cho
    tai lieu trip circuit, tranh bao sai rang 1 minh no da du gay hieu ung trong
    khi thuc te co it nhat 1 he thong yeu cau ket hop them dieu kien khac.
    (Van chap nhan targets kieu cu {'db','sheet','net','disp'} - tu quy thanh 1 cand).
    Tra ve (columns=[disp,...], rows=[{'label','db','sheet','net','kind','source',
    'marks':{disp:{...}}}]), rows sap theo so cot lien quan giam dan roi theo ten.
    CHI GIU quan he OR (1 nguyen nhan minh no da du gay hieu ung O MOI NOI da gap) -
    cac nguyen nhan dang AND (it nhat 1 noi phai ket hop voi nguyen nhan khac) bi AN
    hoan toan khoi ma tran, theo yeu cau: ma tran chi liet ke nhung nguyen nhan doc
    lap, tu no du gay ra tin hieu dich, khong can biet no ket hop voi gi.
    Voi MOI ung vien (db/sheet): uu tien lay nguyen nhan tu CAD_TAG_FID TRONG CHINH
    DB cua ung vien do (nhan nguoi lam tai lieu san, sach hon) - CHI khi khong co gi
    (tin hieu khong theo quy uoc do) moi suy luan tu day qua cond_tree (expand_full/
    _collect), co the sot/lan hon vi phai tu doan qua cac khoi TAG/chot SR."""
    cpu_paths = cpu_paths or {}
    if mode not in ("or", "or_and", "all"):
        mode = "or"
    rows = {}
    columns = []
    tgt_cpus = {}        # disp -> {cpuname da xet} (de biet nguyen nhan thieu o CPU nao)
    for tg in targets:
        disp = tg.get("disp") or tg.get("net")
        columns.append(disp)
        cands = tg.get("cands") or [tg]
        cpus_here = set()
        for cand in cands:
            cpuname = cand.get("cpuname") or ""
            if cpuname:
                cpus_here.add(cpuname)
            src_lbl = "%s / %s" % (cpuname or "?", cand.get("sheetlbl") or "?")
            fid_causes = tag_fid_causes(disp, [cand["db"]])
            if fid_causes:
                for fc in fid_causes:
                    # Chi khoa theo TEN (bo db) - nguyen nhan cung ten tu CPU du
                    # phong A/B se gop chung 1 dong, khong lap doi.
                    key = ("lbl", fc["label"].strip().upper())
                    row = rows.get(key)
                    if row is None:
                        row = {"label": fc["label"], "db": fc["db"], "sheet": fc["sheet"],
                               "sheetlbl": None, "net": None, "kind": "tag",
                               "marks": {}, "source": "tag", "srcs": []}
                        rows[key] = row
                    if src_lbl not in row["srcs"]:
                        row["srcs"].append(src_lbl)
                    _merge_mark(row, disp, {"kind": "or"}, cpuname)
            else:
                local = {}
                tree = expand_full(cand["db"], cand["sheet"], cand["net"], cpu_paths=cpu_paths)
                _collect(tree, disp, local, [])
                for key, lrow in local.items():
                    row = rows.get(key)
                    if row is None:
                        row = {k: v for k, v in lrow.items() if k != "marks"}
                        row["marks"] = {}
                        row["srcs"] = []
                        rows[key] = row
                    row.setdefault("srcs", [])
                    # nguon THAT cua chinh nguyen nhan (co the o CPU/sheet khac cand)
                    rs = "%s / %s" % (lrow.get("cpu") or cpuname or "?",
                                      lrow.get("sheetlbl") or cand.get("sheetlbl") or "?")
                    if rs not in row["srcs"]:
                        row["srcs"].append(rs)
                    mk = lrow["marks"].get(disp)
                    if mk:
                        _merge_mark(row, disp, mk, cpuname)
        tgt_cpus[disp] = cpus_here
    # CPU nao thuc su cho ra it nhat 1 nguyen nhan - CPU khong phan tich duoc (0 nguyen
    # nhan) thi KHONG duoc dung de so sanh, neu khong se bao "thieu" oan cho moi dong.
    tgt_active = {}
    for row in rows.values():
        for d, mk in row["marks"].items():
            tgt_active.setdefault(d, set()).update(mk.get("_seen_at") or set())
    tgt_redun = {d: _redundant_groups(c & (tgt_active.get(d) or set()))
                 for d, c in tgt_cpus.items()}

    out_rows = []
    for row in rows.values():
        marks = {}
        warns = []
        for k, v in row["marks"].items():
            kind = v.get("kind")
            if mode == "or" and kind != "or":
                continue
            seen_at = v.get("_seen_at") or set()
            kinds = v.get("_kinds") or set()
            # CANH BAO LECH CAU HINH - CHI so trong CAP DU PHONG A/B that su (BPS_A vs
            # BPS_B...). Khong so voi moi CPU co nhac toi tin hieu dich, vi nhieu CPU
            # chi NHAN lai tin hieu (khong chua logic sinh ra no) -> se bao sai hang loat.
            for base, pair in (tgt_redun.get(k) or {}).items():
                if not (seen_at & pair):
                    continue                      # nguyen nhan nay khong lien quan cap do
                if _channel_specific(row.get("label")):
                    continue                      # ten da tu ghi ro kenh (vd 'MFT (BMS CTLR A)')
                missing = sorted(pair - seen_at)
                if missing:
                    warns.append("%s: co o %s nhung KHONG co o %s"
                                 % (k, ", ".join(sorted(seen_at & pair)), ", ".join(missing)))
            if len(kinds - {None}) > 1:
                warns.append("%s: cho la OR, cho lai la AND (khac nhau giua cac noi)" % k)
            v = {kk: vv for kk, vv in v.items()
                 if kk not in ("_or_at", "_seen_at", "_kinds")}
            marks[k] = v
        if not marks:      # khong con o nao hop che do -> bo dong
            continue
        row = dict(row)
        row["marks"] = marks
        row["warn"] = "; ".join(warns)
        row["source_txt"] = ", ".join((row.get("srcs") or [])[:3])
        row["raw_name"] = _is_raw_name((row.get("label") or "").split(" (")[0])
        out_rows.append(row)
    # dong co ten mo ta len truoc, dong chi co ma net tho xuong cuoi
    out_rows.sort(key=lambda r: (1 if r.get("raw_name") else 0,
                                 -len(r["marks"]), (r["label"] or "").upper()))
    return columns, out_rows


def is_valid_target(db, sheet, net):
    """True neu tin hieu nay co y nghia boolean (dung duoc cho ma tran nhan qua)."""
    try:
        return CT.is_boolean_signal(db, sheet, net)
    except Exception:
        return True
