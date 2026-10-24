"""core/ocr_engine.py -- OCR backend picker.

PaddleOCR's models (via RapidOCR on ONNX Runtime) when a CUDA GPU is present,
Tesseract on the CPU otherwise. Qt-free; both backends are imported lazily, so
importing this module costs nothing and a machine without RapidOCR just uses
Tesseract. RapidOCR reuses the onnxruntime-gpu already installed for the semantic
layer, so no PaddlePaddle framework is pulled in.

Recognition uses PaddleOCR's English model (paths.ocr_rec_model) when it is
installed. RapidOCR's bundled recogniser is the Chinese one, which drops the
spaces between English words -- "checklistwillbefilledout" -- so those words
cannot be searched; on a test set it read 81% of the words to the English
model's 96%. Without the model file OCR still runs, on the Chinese recogniser,
and the notice says so.
"""

_rapid = None


def english_model():
    """Path of the English recognition model, or None when it is not installed."""
    try:
        import paths
    except ImportError:          # run as a script from inside core/
        return None
    return paths.ocr_rec_model()


def _cuda_setup():
    try:
        from core import cuda_setup
    except ImportError:
        import cuda_setup
    return cuda_setup


def gpu_available() -> bool:
    """True only when a CUDA session can really be created (DLLs load), not merely
    when onnxruntime lists the provider."""
    return _cuda_setup().cuda_works()


def rapidocr_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def use_paddle() -> bool:
    """True when the PaddleOCR (RapidOCR/GPU) path should run."""
    return gpu_available() and rapidocr_available()


def engine_label() -> str:
    return "PaddleOCR" if use_paddle() else "Tesseract"


def advice() -> tuple:
    """(engine, message) for a UI notice about which OCR will run."""
    if use_paddle():
        if english_model():
            return ("PaddleOCR",
                    "GPU detected - OCR uses PaddleOCR (English model), far better on "
                    "scanned, rotated and title-block text.")
        return ("PaddleOCR",
                "GPU detected - OCR uses PaddleOCR, but the English model is missing "
                "(models/ocr/en_PP-OCRv4_rec_mobile.onnx): English words may run "
                "together and be hard to search.")
    if gpu_available() and not rapidocr_available():
        return ("Tesseract",
                "GPU present but RapidOCR is not installed - OCR uses Tesseract "
                "(pip install rapidocr-onnxruntime to enable PaddleOCR).")
    return ("Tesseract", "No GPU - OCR uses Tesseract on the CPU.")


def _float32_normalise():
    """Make RapidOCR's detector input normalisation stay in float32.

    It divides by mean/std arrays held as float64, so every pixel of every page
    went through float64 and back -- 16% of the time a drawing sheet took.
    The same arithmetic in float32 agrees to 1e-5 and measured: A3 2.30 ->
    2.00 s a page, an A1 drawing 36 -> 26 s, A4 within run-to-run noise
    (0.72 -> 0.70 s), with the same words and tags read. Patched on the class
    at runtime (the package itself is not edited); a mean or std that differs
    by channel keeps the original."""
    import numpy as np
    from rapidocr_onnxruntime.ch_ppocr_det.utils import DetPreProcess
    if getattr(DetPreProcess, "_float32", False):
        return
    original = DetPreProcess.__call__

    def call(self, img):
        if len(set(np.ravel(self.mean))) != 1 or len(set(np.ravel(self.std))) != 1:
            return original(self, img)
        resized = self.resize(img)
        if resized is None:
            return None
        x = resized.astype(np.float32)
        x *= np.float32(self.scale / np.ravel(self.std)[0])
        x -= np.float32(np.ravel(self.mean)[0] / np.ravel(self.std)[0])
        return np.ascontiguousarray(x.transpose(2, 0, 1))[None]

    DetPreProcess.__call__ = call
    DetPreProcess._float32 = True


def _get_rapid():
    global _rapid
    if _rapid is None:
        _cuda_setup().setup()   # CUDA wheel DLLs on PATH before the sessions build
        _float32_normalise()
        from rapidocr_onnxruntime import RapidOCR
        use_cuda = gpu_available()
        # Per-component flags are the knob that works in rapidocr-onnxruntime;
        # the global use_cuda= is ignored by this build. Verified: det/cls/rec
        # sessions get CUDAExecutionProvider only with these.
        kw = dict(det_use_cuda=use_cuda, cls_use_cuda=use_cuda, rec_use_cuda=use_cuda)
        model = english_model()
        if model:
            kw["rec_model_path"] = model   # its character list is embedded in the file
        try:
            _rapid = RapidOCR(**kw)
        except Exception:
            _rapid = RapidOCR()
        # RapidOCR shrinks any image whose long side passes 2,000 px before it
        # looks for text. Measured on text-layer pages rendered at 200 dpi:
        # A4 (2,339 px) read 92.4% of the words shrunk and 98.2% whole; A3 read
        # 71.9% shrunk, 67.2% whole (and VRAM rose to 7.8 GB) but 96.2% in
        # tiles; an A1 drawing read next to nothing whole. So a page up to
        # SINGLE_MAX is read whole and unshrunk, anything larger in tiles.
        _rapid.max_side_len = SINGLE_MAX
    return _rapid


SINGLE_MAX = 2400                 # an A4 page at 200 dpi is 2,339 px
TILE, TILE_OVERLAP = 1800, 250    # tiles stay under SINGLE_MAX, so none is shrunk

# A drawing sheet read at 600 dpi carries text three times taller than a page
# at 200 dpi, so text can be *found* on a shrunk copy of each tile (the lines
# are still read from the full-size tile), and more lines go to the GPU at a
# time. Measured on the drawing set (A1 sheets at 600 dpi): 26 -> 18 s a sheet
# with every tag still found. At 300 dpi the same lost tags (74 against 79 on
# the MAW P&ID), and on document pages it lost words (89.9% of an A4 page's
# words against 98.2%), so it applies to sheets read at DRAWING_MIN_DPI or finer.
DRAWING_DET_SIDE = 1280
DRAWING_BATCH = 16
DRAWING_MIN_DPI = 600


class drawing_mode:
    """with drawing_mode(dpi): ... -- OCR settings for a drawing sheet read at
    dpi, restored after. Below DRAWING_MIN_DPI it changes nothing."""

    def __init__(self, dpi):
        self.on = dpi >= DRAWING_MIN_DPI

    def __enter__(self):
        if not self.on:
            return self
        from rapidocr_onnxruntime.ch_ppocr_det.utils import DetPreProcess
        eng = _get_rapid()
        det = eng.text_det
        self._batches = (eng.text_rec.rec_batch_num, eng.text_cls.cls_batch_num)
        det.get_preprocess = lambda max_wh: DetPreProcess(
            DRAWING_DET_SIDE, "max", det.mean, det.std)
        eng.text_rec.rec_batch_num = eng.text_cls.cls_batch_num = DRAWING_BATCH
        return self

    def __exit__(self, *exc):
        if not self.on:
            return False
        eng = _get_rapid()
        eng.text_det.__dict__.pop("get_preprocess", None)
        eng.text_rec.rec_batch_num, eng.text_cls.cls_batch_num = self._batches
        return False


def _read(img) -> list:
    """One OCR pass: [(x0, y0, x1, y1, text, score), ...]."""
    res, _ = _get_rapid()(img)
    out = []
    for box, text, score in res or []:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append((min(xs), min(ys), max(xs), max(ys), text, float(score)))
    return out


def read_regions(width, height, render, on_tile=None) -> list:
    """OCR a width x height px area in overlapping tiles, drawing each with
    render(x0, y0, x1, y1) -> RGB array -- so a sheet rendered at 600 dpi (an
    A1 sheet is 19,867 x 14,034 px, about 800 MB as one image) never exists
    whole. Each tile keeps only the boxes whose centre lies in its own share of
    the overlaps: a line read twice is kept once, and a line cut by a tile
    edge is taken from the tile that holds it. on_tile(done, of) follows along.
    Returns boxes (x0, y0, x1, y1, text, score) in the area's coordinates."""
    step = TILE - TILE_OVERLAP
    ys = list(range(0, max(height - TILE_OVERLAP, 1), step))
    xs = list(range(0, max(width - TILE_OVERLAP, 1), step))
    half = TILE_OVERLAP / 2
    out = []
    n = 0
    for yi, y0 in enumerate(ys):
        top = y0 + half if yi else 0
        bottom = y0 + step + half if yi < len(ys) - 1 else height
        for xi, x0 in enumerate(xs):
            left = x0 + half if xi else 0
            right = x0 + step + half if xi < len(xs) - 1 else width
            tile = render(x0, y0, min(x0 + TILE, width), min(y0 + TILE, height))
            for bx0, by0, bx1, by1, text, score in _read(tile):
                cx, cy = (bx0 + bx1) / 2 + x0, (by0 + by1) / 2 + y0
                if left <= cx < right and top <= cy < bottom:
                    out.append((bx0 + x0, by0 + y0, bx1 + x0, by1 + y0, text, score))
            n += 1
            if on_tile is not None:
                on_tile(n, len(xs) * len(ys))
    return out


def _read_tiled(img) -> list:
    """OCR an image whole when it fits SINGLE_MAX, else in tiles."""
    H, W = img.shape[:2]
    if max(H, W) <= SINGLE_MAX:
        return _read(img)
    return read_regions(W, H, lambda x0, y0, x1, y1: img[y0:y1, x0:x1])


def _vertical_share(boxes) -> float:
    if not boxes:
        return 0.0
    return sum((b[3] - b[1]) > 1.5 * (b[2] - b[0]) for b in boxes) / len(boxes)


def _weight(boxes) -> float:
    """How much confidently read, horizontal text a reading produced."""
    return sum(len(b[4]) * b[5] for b in boxes if (b[3] - b[1]) <= 1.5 * (b[2] - b[0]))


def reading_order(boxes) -> list:
    """Top to bottom by line, left to right within a line."""
    if not boxes:
        return []
    heights = sorted(b[3] - b[1] for b in boxes)
    line = max(heights[len(heights) // 2] * 0.8, 1.0)
    return sorted(boxes, key=lambda b: (round(((b[1] + b[3]) / 2) / line), b[0]))


def _read_upright(img):
    """(boxes in reading order, k): the image read as it stands, or turned by
    np.rot90(img, k) when most of it reads vertically and turning reads better;
    the boxes are then in the turned image's frame."""
    import numpy as np
    boxes, k = _read_tiled(img), 0
    if len(boxes) >= 8 and _vertical_share(boxes) >= 0.6:
        for turn in (1, 3):
            turned = _read_tiled(np.ascontiguousarray(np.rot90(img, turn)))
            if _weight(turned) > _weight(boxes):
                boxes, k = turned, turn
    return reading_order(boxes), k


def ocr_image_boxes(pil_img) -> list:
    """ocr_image_paddle's reading as boxes (x0, y0, x1, y1, text, score), in
    reading order -- for callers that need to know where each line sits."""
    import numpy as np
    return _read_upright(np.array(pil_img.convert("RGB")))[0]


def ocr_image_read(pil_img) -> tuple:
    """(boxes, place): ocr_image_boxes's reading, and place(x0, y0, x1, y1),
    which gives a rectangle in the boxes' frame as fractions (0-1) of pil_img
    as it was handed in -- turned back, for a page that was read turned."""
    import numpy as np
    img = np.array(pil_img.convert("RGB"))
    H, W = img.shape[:2]
    boxes, k = _read_upright(img)

    def place(x0, y0, x1, y1):
        if k == 1:      # np.rot90 once: (x, y) on the page is (W - y', x')
            x0, y0, x1, y1 = W - y1, x0, W - y0, x1
        elif k == 3:    # three times: (x, y) is (y', H - x')
            x0, y0, x1, y1 = y0, H - x1, y1, H - x0
        return (x0 / W, y0 / H, x1 / W, y1 / H)

    return boxes, place


def ocr_image_paddle(pil_img) -> str:
    """OCR one PIL image with RapidOCR (PaddleOCR models); lines in reading order.

    Large images are read in tiles (see SINGLE_MAX). A page lying on its side --
    most of what was found reads vertically -- is turned both ways and read
    again, keeping whichever reads best: measured, such pages read 65-80% of
    their words as they stood against 98% upright. A drawing, with its vertical
    labels among horizontal text, does not trip it. RapidOCR runs its own
    detection, so no Tesseract-style preprocessing is applied.
    """
    return "\n".join(b[4] for b in ocr_image_boxes(pil_img))
