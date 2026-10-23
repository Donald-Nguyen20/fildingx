"""core/cuda_setup.py -- make the pip CUDA wheels usable by onnxruntime-gpu.

onnxruntime-gpu's CUDA provider loads cublas / cudnn / cudart at session time
through the native loader, which ignores os.add_dll_directory for those transitive
dependencies -- only PATH reaches them. So setup() prepends the nvidia-*-cu12 wheel
bin directories to PATH; call it before any onnxruntime session is created.

cuda_works() then reports whether CUDA actually initialises -- it creates a real
probe session rather than trusting get_available_providers(), which lists the
provider even when its DLLs are missing (the default onnxruntime-gpu build ships
the CUDA provider but needs CUDA 12 + cuDNN 9 present to use it).

Qt-free; everything is lazy and wrapped, so a machine without the wheels just
falls back to the CPU and nothing here raises.
"""
import os
import sys
import glob
import importlib.util

_setup_done = False
_cuda_works = None


def _wheel_roots():
    """Directories that may hold the nvidia-*-cu12 wheel bin folders."""
    roots = []
    # Frozen build: PyInstaller collects the DLLs under _internal/.
    if getattr(sys, "frozen", False):
        roots.append(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    # Dev / venv: the wheels sit in the same site-packages as onnxruntime.
    try:
        spec = importlib.util.find_spec("onnxruntime")
        if spec is not None and spec.origin:
            roots.append(os.path.dirname(os.path.dirname(spec.origin)))
    except Exception:
        pass
    return roots


def setup():
    """Put the pip CUDA wheel DLLs on the search path. Idempotent, never raises."""
    global _setup_done
    if _setup_done:
        return
    _setup_done = True
    if sys.platform != "win32":
        return
    try:
        bins = []
        for root in _wheel_roots():
            bins += glob.glob(os.path.join(root, "nvidia", "*", "bin"))
        bins = sorted(set(bins))
        if not bins:
            return
        os.environ["PATH"] = os.pathsep.join(bins) + os.pathsep + os.environ.get("PATH", "")
        for b in bins:
            try:
                os.add_dll_directory(b)
            except Exception:
                pass
    except Exception:
        pass


def _probe_model():
    """A small ONNX model to test a CUDA session with -- RapidOCR ships one."""
    try:
        import rapidocr_onnxruntime as r
        cands = glob.glob(os.path.join(os.path.dirname(r.__file__), "models", "*.onnx"))
        return cands[0] if cands else None
    except Exception:
        return None


def cuda_works():
    """True only when onnxruntime can really create a CUDA session, not merely
    list the provider. Cached after the first call."""
    global _cuda_works
    if _cuda_works is not None:
        return _cuda_works
    setup()
    try:
        import onnxruntime as ort
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            _cuda_works = False
            return _cuda_works
        model = _probe_model()
        if model is None:
            # Nothing to probe with; trust the provider list.
            _cuda_works = True
            return _cuda_works
        import io
        import contextlib
        with contextlib.redirect_stderr(io.StringIO()):
            sess = ort.InferenceSession(
                model, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        _cuda_works = "CUDAExecutionProvider" in sess.get_providers()
    except Exception:
        _cuda_works = False
    return _cuda_works
