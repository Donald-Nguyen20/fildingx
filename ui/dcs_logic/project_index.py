# -*- coding: utf-8 -*-
"""Chi muc TRA CUU chung cho ca du an (nhieu file DB) -> tra tin hieu & C-NET tuc thi,
khong quet lai tung DB. Luu ra 1 file SQLite, cache theo dau thoi gian file.
KHONG dung embeddings - bo truy xuat chinh la engine do thi cua app.

QUAN TRONG (Windows): MOI ket noi sqlite3 mo ra o day PHAI duoc dong lai bang try/finally,
ke ca khi co loi giua chung - neu khong, file handle se con giu file .tdesigner_index.db,
va lan goi build()/rebuild ke tiep se bao WinError 32 (file dang duoc dung boi tien trinh
khac - thuc ra la CHINH minh, do ket noi truoc chua dong het)."""
from __future__ import annotations
import os
import sqlite3
import hashlib
from . import dbreader as D


def index_path():
    return os.path.join(os.path.expanduser("~"), ".tdesigner_index.db")


def _sig(db_paths):
    h = hashlib.sha1()
    for p in sorted(db_paths):
        try:
            h.update(("%s|%d|%d;" % (os.path.abspath(p), int(os.path.getmtime(p)),
                                     os.path.getsize(p))).encode())
        except Exception:
            h.update(p.encode())
    return h.hexdigest()


def _sig_sheets(cur):
    """{systemline: [sheet_id,...]} cho DB kieu EHC - ten tin hieu nam o CAD_SIGNAL
    (khong co so sheet), phai tu tra xem dia chi do dung o sheet nao qua chan khoi.
    Uu tien sheet SINH RA (net tren chan RA); khong co thi lay cac sheet co dung."""
    from . import sheet_render as SR
    MP = SR._macro_pins()
    prod = {}
    used = {}
    try:
        for sid, sym, pn, sig in cur.execute(
                "SELECT b.ID,b.SYMBOL,p.PINNO,p.SIGNALID FROM CAD_BLOCK_PIN p "
                "JOIN CAD_BLOCK b ON p.BLOCK_ID=b.BLOCK_ID "
                "WHERE p.SIGNALID IS NOT NULL AND TRIM(p.SIGNALID)<>''"):
            s = D._clean(sig)
            if not s:
                continue
            side = (MP.get(sym) or {}).get("pins", {}).get(str(pn), {}).get("side")
            (prod if side == "out" else used).setdefault(s, set()).add(sid)
    except Exception:
        return {}
    out = {}
    for s in set(prod) | set(used):
        ids = prod.get(s) or used.get(s) or set()
        out[s] = sorted(ids)[:10]      # tin hieu he thong dung khap noi -> chan bot
    return out


def _num_map(cur):
    num = {}
    try:
        for sid, loop, sh in cur.execute("SELECT ID,LOOPNO,SHEETNO FROM CAD_DATA"):
            loop = D._clean(loop); sh = D._clean(sh)
            if loop and sh:
                num[sid] = "%s-%s" % (str(loop).zfill(3), str(sh).zfill(2))
            elif loop or sh:
                num[sid] = str(loop or sh)
    except Exception:
        pass
    return num


def build(db_paths, out_path=None):
    """Dung lai index tu danh sach file DB. Tra ve duong dan file index."""
    out_path = out_path or index_path()
    tmp = out_path + ".tmp"
    if os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass    # file .tmp cu bi khoa (vd lan build truoc loi giua chung) - ghi de len van duoc
    con = sqlite3.connect(tmp)
    try:
        con.execute("CREATE TABLE sig(name TEXT, db TEXT, cpuno TEXT, cpuname TEXT, "
                    "sheet INT, sheetlbl TEXT, signalid TEXT)")
        con.execute("CREATE TABLE cnet(systemline TEXT, name TEXT, cpuno TEXT, cpuname TEXT, "
                    "db TEXT, sheet INT, sheetlbl TEXT)")
        con.execute("CREATE TABLE meta(key TEXT, val TEXT)")
        for p in db_paths:
            try:
                meta = D.db_meta(p)
            except Exception:
                meta = {}
            cpuno = str(meta.get("cpuno") or ""); cpuname = meta.get("cpuname") or ""
            pc = None
            try:
                pc = sqlite3.connect(D.ro_uri(p), uri=True)   # source DB: read-only
                c = pc.cursor()
                num = _num_map(c)
                try:
                    rows = c.execute("SELECT ID,SIGNALID,LINENAME,SYSTEMLINE FROM CAD_ID").fetchall()
                except Exception:
                    rows = []
                seen_names = set()
                for sid, sigid, ln, sysl in rows:
                    ln = D._clean(ln); sysl = D._clean(sysl); sigid = D._clean(sigid)
                    slbl = num.get(sid, str(sid))
                    if ln:
                        seen_names.add(ln.upper())
                        con.execute("INSERT INTO sig VALUES(?,?,?,?,?,?,?)",
                                    (ln, p, cpuno, cpuname, sid, slbl, sigid))
                    if sysl:
                        con.execute("INSERT INTO cnet VALUES(?,?,?,?,?,?,?)",
                                    (sysl, ln, cpuno, cpuname, p, sid, slbl))
                # Nguon ten thu 2 (DB kieu EHC): CAD_SIGNAL. Nhieu DB (21 EHC MC, 23/25
                # BFPT...) KHONG dat ten trong CAD_ID - vd 'TURBINE TRIP COMMAND' chi co o
                # CAD_SIGNAL - neu khong nap vao day thi tim kiem se khong ra du man hinh
                # van hien ten. Chi nap ten CHUA co trong CAD_ID de khong sinh dong trung.
                try:
                    srows = c.execute("SELECT SYSTEMLINE,LINENAME FROM CAD_SIGNAL").fetchall()
                except Exception:
                    srows = []
                if srows:
                    sheets_of = _sig_sheets(c) if any(
                        D._clean(l) and D._clean(l).upper() not in seen_names
                        for _s, l in srows) else {}
                    for sysl, ln in srows:
                        sysl = D._clean(sysl); ln = D._clean(ln)
                        if not ln or ln.upper() in seen_names:
                            continue
                        for sid in (sheets_of.get(sysl) or [None]):
                            slbl = num.get(sid, str(sid)) if sid is not None else ""
                            con.execute("INSERT INTO sig VALUES(?,?,?,?,?,?,?)",
                                        (ln, p, cpuno, cpuname, sid, slbl, sysl))
                        if sysl:
                            con.execute("INSERT INTO cnet VALUES(?,?,?,?,?,?,?)",
                                        (sysl, ln, cpuno, cpuname, p, None, ""))
            except Exception:
                continue
            finally:
                if pc is not None:
                    pc.close()
        con.execute("CREATE INDEX ix_sig_name ON sig(name)")
        con.execute("CREATE INDEX ix_cnet_line ON cnet(systemline)")
        con.execute("CREATE INDEX ix_cnet_name ON cnet(name)")
        con.execute("INSERT INTO meta VALUES('sig', ?)", (_sig(db_paths),))
        con.commit()
    finally:
        con.close()     # LUON dong, ke ca khi loi o tren - neu khong tmp se bi khoa mai
    if os.path.exists(out_path):
        try:
            os.remove(out_path)
        except OSError as e:
            # con noi khac dang mo file index cu (vd 1 truy van truoc chua dong het) ->
            # bao ro nguyen nhan thay vi de WinError 32 kho hieu lot ra ngoai
            raise OSError("Khong the ghi de index cu (dang bi khoa boi 1 tien trinh/ket noi "
                          "khac): %s. Thu dong cac cua so tim kiem/ma tran dang mo roi thu "
                          "lai." % e)
    os.rename(tmp, out_path)
    return out_path


def ensure(db_paths, out_path=None):
    """Dung index neu chua co / DB da doi. Tra ve duong dan index."""
    out_path = out_path or index_path()
    want = _sig(db_paths)
    con = None
    try:
        con = sqlite3.connect(out_path)
        cur = con.execute("SELECT val FROM meta WHERE key='sig'").fetchone()
        if cur and cur[0] == want:
            return out_path
    except Exception:
        pass
    finally:
        if con is not None:
            con.close()
    return build(db_paths, out_path)


def find(query, limit=300, out_path=None):
    """Tim tin hieu theo ten (LIKE). Tra ve [(name, cpuname, cpuno, sheetlbl, db, sheet, signalid)]."""
    out_path = out_path or index_path()
    con = None
    try:
        con = sqlite3.connect(out_path)
        return con.execute(
            "SELECT DISTINCT name,cpuname,cpuno,sheetlbl,db,sheet,signalid FROM sig "
            "WHERE UPPER(name) LIKE ? ORDER BY name LIMIT ?",
            ("%" + query.upper() + "%", limit)).fetchall()
    except Exception:
        return []
    finally:
        if con is not None:
            con.close()


def locate(name, out_path=None):
    """Cac vi tri (cpuname, cpuno, sheetlbl, db, sheet) cua tin hieu ten CHINH XAC."""
    out_path = out_path or index_path()
    con = None
    try:
        con = sqlite3.connect(out_path)
        return con.execute(
            "SELECT DISTINCT cpuname,cpuno,sheetlbl,db,sheet FROM sig WHERE name=?",
            (name,)).fetchall()
    except Exception:
        return []
    finally:
        if con is not None:
            con.close()


def locate_full(name, out_path=None):
    """Vi tri kem signalid: [(cpuname, cpuno, slbl, db, sheet, signalid)] cho ten CHINH XAC."""
    out_path = out_path or index_path()
    con = None
    try:
        con = sqlite3.connect(out_path)
        return con.execute(
            "SELECT DISTINCT cpuname,cpuno,sheetlbl,db,sheet,signalid FROM sig WHERE name=?",
            (name,)).fetchall()
    except Exception:
        return []
    finally:
        if con is not None:
            con.close()


def cnet_partners(name, out_path=None):
    """Cac CPU/sheet lien quan qua C-NET (cung SYSTEMLINE) voi tin hieu ten `name`."""
    out_path = out_path or index_path()
    con = None
    try:
        con = sqlite3.connect(out_path)
        lines = [r[0] for r in con.execute("SELECT DISTINCT systemline FROM cnet WHERE name=?", (name,))]
        res = []
        for sl in lines:
            for r in con.execute(
                    "SELECT DISTINCT systemline,cpuname,cpuno,sheetlbl,name FROM cnet WHERE systemline=?", (sl,)):
                res.append(r)
        return res
    except Exception:
        return []
    finally:
        if con is not None:
            con.close()
