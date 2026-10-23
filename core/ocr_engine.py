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


def _get_rapid():
    global _rapid
    if _rapid is None:
        _cuda_setup().setup()   # CUDA wheel DLLs on PATH before the sessions build
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
    return _rapid


def ocr_image_paddle(pil_img) -> str:
    """OCR one PIL image with RapidOCR (PaddleOCR models); lines joined by newline.

    RapidOCR runs its own detection, so the image is passed as-is rather than
    through the Tesseract-tuned preprocessing.
    """
    import numpy as np
    res, _ = _get_rapid()(np.array(pil_img.convert("RGB")))
    if not res:
        return ""
    return "\n".join(line[1] for line in res)
