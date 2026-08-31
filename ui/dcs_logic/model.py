# -*- coding: utf-8 -*-
"""
T-Designer Lite - Logic model (KHONG phu thuoc GUI)
Ho tro khoi NHIEU NGO RA (tin hieu theo tung cong: (block_id, port)).
Nap TOAN BO thu vien macro that tu core/macro_catalog.json.
"""
from __future__ import annotations
import os
import json
from collections import defaultdict, deque

# ---------------------------------------------------------------------------
# 1. KHOI CO BAN (mo phong duoc day du)
# ---------------------------------------------------------------------------
PRIMITIVES = {
    "DI":   {"inputs": 0, "outputs": 1, "in_names": [],         "out_names": ["Q"], "desc": "Digital Input (dau vao so)"},
    "DO":   {"inputs": 1, "outputs": 0, "in_names": ["D"],      "out_names": [],    "desc": "Digital Output (dau ra so)"},
    "AND":  {"inputs": 2, "outputs": 1, "in_names": ["A", "B"], "out_names": ["Q"], "desc": "AND - va logic"},
    "OR":   {"inputs": 2, "outputs": 1, "in_names": ["A", "B"], "out_names": ["Q"], "desc": "OR - hoac logic"},
    "NOT":  {"inputs": 1, "outputs": 1, "in_names": ["A"],      "out_names": ["Q"], "desc": "NOT - dao logic"},
    "XOR":  {"inputs": 2, "outputs": 1, "in_names": ["A", "B"], "out_names": ["Q"], "desc": "XOR - hoac loai tru"},
    "FF":   {"inputs": 2, "outputs": 1, "in_names": ["S", "R"], "out_names": ["Q"], "desc": "Flip-Flop SR (S uu tien)"},
    "TON":  {"inputs": 1, "outputs": 1, "in_names": ["IN"],     "out_names": ["Q"], "desc": "On-Delay Timer (TON)"},
    "MOVE": {"inputs": 1, "outputs": 1, "in_names": ["IN"],     "out_names": ["Q"], "desc": "MOVE - chuyen du lieu"},
}
PRIMITIVE_ORDER = ["DI", "DO", "AND", "OR", "NOT", "XOR", "FF", "TON", "MOVE"]

BLOCK_SPECS = {}
for _k, _v in PRIMITIVES.items():
    _d = dict(_v)
    _d.update(label=_k, generic=False, category="Co ban (Primitive)", code="", short=_k)
    BLOCK_SPECS[_k] = _d

CATALOG_BY_CAT = defaultdict(list)


def _make_names(prefix, n):
    return [prefix + str(i + 1) for i in range(n)]


_MANUAL_TERMS = None


def _manual_terms():
    """code(hex) -> (in_names, out_names) tu core/macro_manual.json."""
    global _MANUAL_TERMS
    if _MANUAL_TERMS is None:
        _MANUAL_TERMS = {}
        p = os.path.join(os.path.dirname(__file__), "macro_manual.json")
        if os.path.exists(p):
            try:
                bc = json.load(open(p, encoding="utf-8")).get("by_code", {})
                for code, v in bc.items():
                    if v.get("in") or v.get("out"):
                        _MANUAL_TERMS[code.upper()] = (v["in"], v["out"])
            except Exception:
                pass
    return _MANUAL_TERMS


def load_catalog(path=None):
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "macro_catalog.json")
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    n = 0
    for m in data.get("macros", []):
        bid = m["id"]
        if not bid or bid in PRIMITIVES:
            continue
        n_in = max(0, int(m.get("inputs", 1)))
        n_out = max(0, int(m.get("outputs", 1)))
        code = (m.get("code", "") or "").upper()
        terms = _manual_terms().get(code)
        in_nm = out_nm = None
        if terms and (terms[0] or terms[1]):
            in_nm, out_nm = terms[0], terms[1]
            n_in, n_out = len(in_nm), len(out_nm)
        label = m.get("short") or bid
        BLOCK_SPECS[bid] = {
            "inputs": n_in, "outputs": n_out,
            "in_names": in_nm if in_nm else _make_names("I", n_in),
            "out_names": out_nm if out_nm else _make_names("O", n_out),
            "desc": m.get("name", label),
            "label": label, "short": m.get("short", label),
            "code": m.get("code", ""), "category": m.get("category", "Khac"),
            "params": int(m.get("params", 0)), "obs": bool(m.get("obs", False)),
            "generic": True,
        }
        CATALOG_BY_CAT[BLOCK_SPECS[bid]["category"]].append(bid)
        n += 1
    return n


CATALOG_COUNT = load_catalog()
BLOCK_ORDER = PRIMITIVE_ORDER


def spec(btype):
    return BLOCK_SPECS.get(btype, {})


def is_primitive(btype):
    return btype in PRIMITIVES


# ---------------------------------------------------------------------------
# 2. MO HINH MACH
# ---------------------------------------------------------------------------
class Block:
    __slots__ = ("id", "btype", "tag", "x", "y", "param")

    def __init__(self, bid, btype, tag="", x=0.0, y=0.0, param=None):
        self.btype = btype
        self.id = bid
        self.tag = tag
        self.x = x
        self.y = y
        self.param = param or {}

    @property
    def spec(self):
        return BLOCK_SPECS.get(self.btype, {"inputs": 0, "outputs": 0, "in_names": [], "out_names": []})

    def to_dict(self):
        return {"id": self.id, "btype": self.btype, "tag": self.tag, "x": self.x, "y": self.y, "param": self.param}

    @staticmethod
    def from_dict(d):
        return Block(d["id"], d["btype"], d.get("tag", ""), d.get("x", 0.0), d.get("y", 0.0), d.get("param", {}))


class Connection:
    __slots__ = ("src", "src_port", "dst", "dst_port")

    def __init__(self, src, src_port, dst, dst_port):
        self.src = src
        self.src_port = src_port
        self.dst = dst
        self.dst_port = dst_port

    def to_dict(self):
        return {"src": self.src, "src_port": self.src_port, "dst": self.dst, "dst_port": self.dst_port}

    @staticmethod
    def from_dict(d):
        return Connection(d["src"], d["src_port"], d["dst"], d["dst_port"])


class Circuit:
    def __init__(self, name="SHEET1"):
        self.name = name
        self.blocks = {}
        self.conns = []
        self._next_id = 1

    def add_block(self, btype, tag="", x=0.0, y=0.0, param=None):
        b = Block(self._next_id, btype, tag, x, y, param)
        self.blocks[b.id] = b
        self._next_id += 1
        return b

    def remove_block(self, bid):
        self.blocks.pop(bid, None)
        self.conns = [c for c in self.conns if c.src != bid and c.dst != bid]

    def connect(self, src, src_port, dst, dst_port):
        self.conns = [c for c in self.conns if not (c.dst == dst and c.dst_port == dst_port)]
        self.conns.append(Connection(src, src_port, dst, dst_port))

    def input_source(self, bid, port):
        for c in self.conns:
            if c.dst == bid and c.dst_port == port:
                return (c.src, c.src_port)
        return None

    def to_dict(self):
        return {"name": self.name, "next_id": self._next_id,
                "blocks": [b.to_dict() for b in self.blocks.values()],
                "conns": [c.to_dict() for c in self.conns]}

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @staticmethod
    def from_dict(d):
        c = Circuit(d.get("name", "SHEET1"))
        c._next_id = d.get("next_id", 1)
        for bd in d.get("blocks", []):
            b = Block.from_dict(bd)
            c.blocks[b.id] = b
        for cd in d.get("conns", []):
            c.conns.append(Connection.from_dict(cd))
        c._next_id = 1 if not c.blocks else max(c._next_id, max(c.blocks) + 1)
        return c

    @staticmethod
    def load(path):
        with open(path, "r", encoding="utf-8") as f:
            return Circuit.from_dict(json.load(f))

    def topo_order(self):
        indeg = {bid: 0 for bid in self.blocks}
        adj = defaultdict(list)
        seen = set()
        for c in self.conns:
            if c.src in self.blocks and c.dst in self.blocks:
                key = (c.src, c.dst)
                if key in seen:
                    continue
                seen.add(key)
                adj[c.src].append(c.dst)
                indeg[c.dst] += 1
        q = deque([b for b in self.blocks if indeg[b] == 0])
        order, visited = [], set()
        while q:
            n = q.popleft()
            if n in visited:
                continue
            visited.add(n)
            order.append(n)
            for m in adj[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    q.append(m)
        for b in self.blocks:
            if b not in visited:
                order.append(b)
        return order


# ---------------------------------------------------------------------------
# 3. BO MO PHONG LOGIC (tin hieu theo tung cong ra)
# ---------------------------------------------------------------------------
class Simulator:
    def __init__(self, circuit):
        self.c = circuit
        self.di_state = {}
        self.out = {}
        self.ff_state = {}
        self.ton_cnt = {}

    def set_di(self, bid, value):
        self.di_state[bid] = bool(value)

    def toggle_di(self, bid):
        self.di_state[bid] = not self.di_state.get(bid, False)

    def _in_val(self, bid, port):
        s = self.c.input_source(bid, port)
        return self.out.get(s, False) if s else False

    def block_value(self, bid):
        b = self.c.blocks[bid]
        sp = BLOCK_SPECS.get(b.btype, {})
        no = sp.get("outputs", 0)
        if no == 0:
            return self._in_val(bid, 0)
        return any(self.out.get((bid, j), False) for j in range(no))

    def scan(self):
        order = self.c.topo_order()
        for _ in range(len(self.c.blocks) + 2):
            changed = False
            for bid in order:
                b = self.c.blocks[bid]
                vals = self._eval_block(b)
                for j, v in enumerate(vals):
                    if self.out.get((bid, j)) != v:
                        self.out[(bid, j)] = v
                        changed = True
            if not changed:
                break
        return self.out

    def _eval_block(self, b):
        t = b.btype
        if t == "DI":
            return [self.di_state.get(b.id, False)]
        if t == "DO":
            return []
        if t == "AND":
            return [self._in_val(b.id, 0) and self._in_val(b.id, 1)]
        if t == "OR":
            return [self._in_val(b.id, 0) or self._in_val(b.id, 1)]
        if t == "NOT":
            return [not self._in_val(b.id, 0)]
        if t == "XOR":
            return [self._in_val(b.id, 0) != self._in_val(b.id, 1)]
        if t == "MOVE":
            return [self._in_val(b.id, 0)]
        if t == "FF":
            s, r = self._in_val(b.id, 0), self._in_val(b.id, 1)
            cur = self.ff_state.get(b.id, False)
            if s:
                cur = True
            elif r:
                cur = False
            self.ff_state[b.id] = cur
            return [cur]
        if t == "TON":
            preset = int(b.param.get("preset", 3))
            self.ton_cnt[b.id] = self.ton_cnt.get(b.id, 0) + 1 if self._in_val(b.id, 0) else 0
            return [self.ton_cnt[b.id] >= preset]
        sp = BLOCK_SPECS.get(t, {})
        n_in = sp.get("inputs", 0)
        n_out = sp.get("outputs", 0)
        any_in = any(self._in_val(b.id, i) for i in range(n_in))
        return [any_in] * n_out


# ---------------------------------------------------------------------------
# 4. BO SINH MA .DEF (tin hieu theo tung cong ra)
# ---------------------------------------------------------------------------
class DefGenerator:
    def __init__(self, circuit):
        self.c = circuit
        self.sig = {}
        self._dw = 0
        self._rw = 0

    def _new_dw(self):
        self._dw += 1
        return "Dw%03d" % self._dw

    def _new_rw(self):
        self._rw += 1
        return "Rw%03d" % self._rw

    def _src(self, bid, port):
        s = self.c.input_source(bid, port)
        if s is None:
            return "0000H"
        return self.sig.get(s, "0000H")

    def generate(self):
        order = self.c.topo_order()
        for bid in order:
            b = self.c.blocks[bid]
            sp = BLOCK_SPECS.get(b.btype, {})
            if b.btype == "DI":
                self.sig[(bid, 0)] = b.tag or ("DI%d" % bid)
            else:
                for j in range(sp.get("outputs", 0)):
                    self.sig[(bid, j)] = self._new_dw()
        lines = [".DEF    %s 8000H 0000H 0000H 0000H 8000" % self.c.name]
        for bid in order:
            lines += self._emit(self.c.blocks[bid])
        lines.append(".DEFEND")
        return "\n".join(lines)

    def _emit(self, b):
        t = b.btype
        if t == "DI":
            return []
        if t == "DO":
            return ["A    %s" % self._src(b.id, 0), "OUT    %s" % (b.tag or ("DO%d" % b.id))]
        o = self.sig.get((b.id, 0)) or self._new_dw()
        if t == "AND":
            return ["A    %s,%s" % (self._src(b.id, 0), self._src(b.id, 1)), "OUT    %s" % o]
        if t == "OR":
            return ["A    %s" % self._src(b.id, 0), "OR    %s" % self._src(b.id, 1), "OUT    %s" % o]
        if t == "NOT":
            return ["A    -%s" % self._src(b.id, 0), "OUT    %s" % o]
        if t == "XOR":
            return ["XOR    %s,%s,%s" % (self._src(b.id, 0), self._src(b.id, 1), self._new_rw()), "OUT    %s" % o]
        if t == "MOVE":
            return ["MV1    %s" % self._src(b.id, 0), "OUT    %s" % o]
        if t == "FF":
            return ["A    %s" % self._src(b.id, 0), "SET    %s" % o,
                    "A    %s" % self._src(b.id, 1), "CL    %s" % o]
        if t == "TON":
            return ["A    %s" % self._src(b.id, 0),
                    "TON    %04dH" % int(b.param.get("preset", 3)), "OUT    %s" % o]
        sp = BLOCK_SPECS.get(t, {})
        code = sp.get("code", "")
        short = sp.get("short", t)
        n_in = sp.get("inputs", 0)
        n_out = sp.get("outputs", 0)
        out = ["; ==== %s  (macro %s, code %s) ====" % (short, t, code)]
        ins = ",".join(self._src(b.id, i) for i in range(n_in)) or "-"
        out.append(".MCR    %s    %s    IN=(%s)" % (short, code, ins))
        for j in range(n_out):
            out.append("OUT    %s" % (self.sig.get((b.id, j)) or self._new_dw()))
        out.append(".MCREND")
        return out
