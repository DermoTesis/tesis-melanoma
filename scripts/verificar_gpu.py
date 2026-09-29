#!/usr/bin/env python3
"""Verifica que la GPU sirva para entrenar: TensorFlow (plan A) y Keras 3 + PyTorch (plan B).

Uso, dentro del contenedor de Docker con GPU (ver README) o en Colab:

    python scripts/verificar_gpu.py --backend tensorflow
    python scripts/verificar_gpu.py --backend torch
    python scripts/verificar_gpu.py --allow-cpu         # prueba el script en una máquina sin GPU

Para cada backend comprueba que vea la GPU, si trae kernels compilados para su arquitectura
(la RTX 5060 es Blackwell, sm_120), que un matmul en GPU coincida con el de CPU y que Keras
entrene unos pasos de MobileNetV3-Large con precisión mixta, que es lo que hará EXP-02.
En TensorFlow prueba con y sin XLA, porque XLA compila con el ptxas de CUDA y es lo primero que
falla en una GPU más nueva que el toolkit.

Cada backend corre en un subproceso propio porque Keras fija el backend al importarse. Solo usa
la biblioteca estándar fuera de los subprocesos, así que corre sin instalar el paquete del repo.
El reporte queda en resultados/entorno/.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT_MARKER = "@@RESULTADO@@"
PROGRESS_PREFIX = ">> "
MIN_DRIVER_BLACKWELL = 570
MATMUL_TOLERANCE = 1e-2  # TF32 está activo por defecto en Ampere o posterior

# Mensajes del log de CUDA/TF que explican la mayoría de fallas en GPUs nuevas.
LOG_HINTS = {
    "ptx_jit": re.compile(r"jit-compiled from PTX|not built with CUDA kernel binaries", re.I),
    "ptxas": re.compile(r"ptxas", re.I),
    "no_kernel_image": re.compile(r"no kernel image is available", re.I),
    "cuda_error": re.compile(r"CUDA_ERROR_\w+"),
    "cudnn_error": re.compile(r"(cudnn|dnn).*(fail|error|not found)", re.I),
    "oom": re.compile(r"out of memory|ResourceExhausted", re.I),
}


# --------------------------------------------------------------------------------------------
# Subprocesos (uno por backend)
# --------------------------------------------------------------------------------------------

def worker_tensorflow(args: argparse.Namespace) -> dict:
    info: dict = {"backend": "tensorflow"}
    t0 = time.perf_counter()
    import tensorflow as tf
    info["import_s"] = round(time.perf_counter() - t0, 1)
    info["version"] = tf.__version__
    build = dict(tf.sysconfig.get_build_info())
    info["built_with_cuda"] = tf.test.is_built_with_cuda()
    info["cuda_build"] = build.get("cuda_version")
    info["cudnn_build"] = build.get("cudnn_version")
    info["build_archs"] = build.get("cuda_compute_capabilities")

    gpus = tf.config.list_physical_devices("GPU")
    info["gpus"] = []
    for gpu in gpus:
        tf.config.experimental.set_memory_growth(gpu, True)
        details = tf.config.experimental.get_device_details(gpu)
        info["gpus"].append({"name": details.get("device_name"),
                             "compute_capability": details.get("compute_capability")})
    if gpus:
        cc = info["gpus"][0]["compute_capability"]
        if cc:
            info["arch"] = f"sm_{cc[0]}{cc[1]}"
            info["native_kernels"] = info["arch"] in (info["build_archs"] or [])
    elif not args.allow_cpu:
        info["error"] = "TensorFlow no ve ninguna GPU"
        return info

    device = "/GPU:0" if gpus else "/CPU:0"
    try:
        with tf.device("/CPU:0"):
            a = tf.random.stateless_uniform((2048, 2048), seed=(1, 2))
            b = tf.random.stateless_uniform((2048, 2048), seed=(3, 4))
            ref = tf.linalg.matmul(a, b)
        with tf.device(device):
            out = tf.linalg.matmul(a, b)
        info["matmul_rel_error"] = float(tf.reduce_max(tf.abs(out - ref)) / tf.reduce_max(tf.abs(ref)))
    except Exception as exc:  # noqa: BLE001 - se reporta cualquier falla del runtime
        info["matmul_error"] = _describe(exc)

    info["training"] = {}
    for jit in (False, True):
        key = "xla" if jit else "sin_xla"
        _progress(f"entrenando MobileNetV3-Large {'con' if jit else 'sin'} XLA en {device}")
        info["training"][key] = _train_keras(args, jit_compile=jit, use_gpu=bool(gpus))
        if gpus:
            info["training"][key]["peak_memory_mb"] = round(
                tf.config.experimental.get_memory_info("GPU:0")["peak"] / 2**20)
            tf.config.experimental.reset_memory_stats("GPU:0")
    return info


def worker_torch(args: argparse.Namespace) -> dict:
    info: dict = {"backend": "torch"}
    t0 = time.perf_counter()
    import torch
    info["import_s"] = round(time.perf_counter() - t0, 1)
    info["version"] = torch.__version__
    info["cuda_build"] = torch.version.cuda
    info["cudnn_build"] = torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else None
    info["build_archs"] = torch.cuda.get_arch_list() if torch.version.cuda else []

    has_gpu = torch.cuda.is_available()
    info["gpus"] = []
    if has_gpu:
        major, minor = torch.cuda.get_device_capability(0)
        info["gpus"].append({"name": torch.cuda.get_device_name(0), "compute_capability": [major, minor]})
        info["arch"] = f"sm_{major}{minor}"
        info["native_kernels"] = info["arch"] in info["build_archs"]
    elif not args.allow_cpu:
        info["error"] = "PyTorch no ve ninguna GPU (torch.cuda.is_available() es False)"
        return info

    try:
        gen = torch.Generator().manual_seed(0)
        a = torch.rand(2048, 2048, generator=gen)
        b = torch.rand(2048, 2048, generator=gen)
        ref = a @ b
        out = (a.cuda() @ b.cuda()).cpu() if has_gpu else ref
        info["matmul_rel_error"] = float((out - ref).abs().max() / ref.abs().max())
    except Exception as exc:  # noqa: BLE001
        info["matmul_error"] = _describe(exc)

    _progress(f"entrenando MobileNetV3-Large en {'cuda' if has_gpu else 'cpu'}")
    info["training"] = {"sin_xla": _train_keras(args, jit_compile=False, use_gpu=has_gpu)}
    if has_gpu:
        info["training"]["sin_xla"]["peak_memory_mb"] = round(torch.cuda.max_memory_allocated() / 2**20)
    return info


def _train_keras(args: argparse.Namespace, jit_compile: bool, use_gpu: bool) -> dict:
    """Entrena pasos de MobileNetV3-Large + cabeza sigmoide sobre un lote aleatorio."""
    result: dict = {"jit_compile": jit_compile}
    try:
        try:
            import keras
        except ImportError:  # imágenes con TensorFlow que solo traen tf.keras
            from tensorflow import keras
        import numpy as np

        result["keras"] = keras.__version__
        mixed = use_gpu and not args.no_mixed_precision
        keras.mixed_precision.set_global_policy("mixed_float16" if mixed else "float32")
        result["mixed_precision"] = mixed
        keras.utils.set_random_seed(0)
        weights = None if args.no_weights else "imagenet"
        try:
            base = keras.applications.MobileNetV3Large(
                input_shape=(224, 224, 3), include_top=False, weights=weights, pooling="avg")
        except Exception as exc:  # noqa: BLE001 - sin red no hay pesos, pero se sigue probando
            result["weights_error"] = _describe(exc)
            weights = None
            base = keras.applications.MobileNetV3Large(
                input_shape=(224, 224, 3), include_top=False, weights=None, pooling="avg")
        result["weights"] = weights
        output = keras.layers.Dense(1, activation="sigmoid", dtype="float32")(base.output)
        model = keras.Model(base.input, output)
        model.compile(optimizer=keras.optimizers.Adam(1e-4), loss="binary_crossentropy",
                      jit_compile=jit_compile)

        rng = np.random.default_rng(0)
        x = rng.uniform(0, 255, (args.batch_size, 224, 224, 3)).astype("float32")
        y = rng.integers(0, 2, (args.batch_size, 1)).astype("float32")

        t0 = time.perf_counter()
        for _ in range(args.warmup_steps):
            model.train_on_batch(x, y)
        result["warmup_s"] = round(time.perf_counter() - t0, 1)

        t0 = time.perf_counter()
        losses = [float(np.asarray(model.train_on_batch(x, y)).ravel()[0]) for _ in range(args.steps)]
        elapsed = time.perf_counter() - t0
        result["images_per_s"] = round(args.batch_size * args.steps / elapsed, 1)
        result["final_loss"] = losses[-1]
        result["ok"] = all(math.isfinite(v) for v in losses)
        if not result["ok"]:
            result["error"] = "la pérdida no es finita (NaN/Inf)"
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        result["error"] = _describe(exc)
    return result


def _progress(message: str) -> None:
    print(PROGRESS_PREFIX + message, file=sys.stderr, flush=True)


def _describe(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return text if len(text) <= 1500 else text[:1500] + " [...]"


WORKERS = {"tensorflow": worker_tensorflow, "torch": worker_torch}


# --------------------------------------------------------------------------------------------
# Proceso principal
# --------------------------------------------------------------------------------------------

def run_worker(backend: str, args: argparse.Namespace) -> dict:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", backend,
           "--batch-size", str(args.batch_size), "--steps", str(args.steps),
           "--warmup-steps", str(args.warmup_steps)]
    cmd += [flag for flag, on in (("--allow-cpu", args.allow_cpu), ("--no-weights", args.no_weights),
                                  ("--no-mixed-precision", args.no_mixed_precision)) if on]
    env = dict(os.environ, KERAS_BACKEND=backend, PYTHONUNBUFFERED="1")
    # Si CUDA compila PTX en tiempo de ejecución, la caché por defecto (256 MB) es chica y se
    # recompila en cada corrida.
    env.setdefault("CUDA_CACHE_MAXSIZE", str(4 * 2**30))

    print(f"\n=== {backend} === (puede tardar varios minutos; --verbose muestra el log completo)",
          flush=True)
    try:
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, errors="replace")
    except OSError as exc:
        return {"backend": backend, "error": _describe(exc)}

    out_lines: list[str] = []
    log_lines: list[str] = []

    def pump(stream, sink: list[str]) -> None:
        for line in stream:
            sink.append(line.rstrip("\n"))
            if line.startswith(PROGRESS_PREFIX) or (args.verbose and not line.startswith(RESULT_MARKER)):
                sys.stderr.write(f"[{backend}] {line}")

    readers = [threading.Thread(target=pump, args=(proc.stdout, out_lines), daemon=True),
               threading.Thread(target=pump, args=(proc.stderr, log_lines), daemon=True)]
    for reader in readers:
        reader.start()
    try:
        proc.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        result = {"backend": backend,
                  "error": f"tiempo agotado ({args.timeout} s); si el log menciona PTX, la primera "
                           "compilación puede tardar mucho: reintentar con --timeout mayor"}
    else:
        for reader in readers:
            reader.join(timeout=10)
        result = _parse_worker_output(backend, out_lines, proc.returncode)

    hints = {name: [l for l in log_lines if rx.search(l)][:3] for name, rx in LOG_HINTS.items()}
    result["log_hints"] = {k: v for k, v in hints.items() if v}
    if "error" in result or result.get("returncode"):
        result["log_tail"] = log_lines[-40:]
    return result


def _parse_worker_output(backend: str, stdout: list[str], returncode: int) -> dict:
    for line in reversed(stdout):
        if line.startswith(RESULT_MARKER):
            result = json.loads(line[len(RESULT_MARKER):])
            if returncode:
                result["returncode"] = returncode
            return result
    return {"backend": backend, "returncode": returncode,
            "error": f"el subproceso terminó sin reporte (código {returncode}); "
                     "probablemente falta el paquete o el runtime de CUDA se cayó"}


def system_info() -> dict:
    info = {
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "wsl": _read("/proc/version").lower().count("microsoft") > 0,
        "docker": Path("/.dockerenv").exists(),
        "colab": "COLAB_RELEASE_TAG" in os.environ,
        "ram_gb": _ram_gb(),
    }
    smi = _cmd(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader"])
    info["nvidia_smi"] = smi.splitlines() if smi else []
    header = _cmd(["nvidia-smi"]) or ""
    match = re.search(r"CUDA Version:\s*([\d.]+)", header)
    info["driver_max_cuda"] = match.group(1) if match else None
    return info


def _read(path: str) -> str:
    try:
        return Path(path).read_text()
    except OSError:
        return ""


def _ram_gb() -> float | None:
    match = re.search(r"MemTotal:\s+(\d+) kB", _read("/proc/meminfo"))
    return round(int(match.group(1)) / 2**20, 1) if match else None


def _cmd(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def backend_status(result: dict) -> tuple[bool, str]:
    """(apto, explicación) para entrenar con ese backend."""
    if "error" in result:
        return False, result["error"]
    if "matmul_error" in result:
        return False, f"matmul falló: {result['matmul_error']}"
    if result.get("matmul_rel_error", 0) > MATMUL_TOLERANCE:
        return False, f"matmul GPU difiere de CPU (error relativo {result['matmul_rel_error']:.2e})"
    training = result.get("training", {})
    plain, xla = training.get("sin_xla", {}), training.get("xla")
    if not plain.get("ok"):
        return False, f"el entrenamiento falló: {plain.get('error')}"
    note = f"{plain['images_per_s']} img/s" + ("" if result.get("gpus") else " en CPU")
    if xla is not None:
        note += (f", con XLA {xla['images_per_s']} img/s" if xla.get("ok")
                 else "; XLA falla: entrenar con jit_compile=False")
    return True, note


def summarize(report: dict) -> str:
    system = report["system"]
    lines = ["", "=== Resumen ==="]
    lines.append(f"Sistema: {system['platform']} | WSL2: {system['wsl']} | Docker: {system['docker']} "
                 f"| RAM: {system['ram_gb']} GB")
    if platform.system() == "Windows":
        lines.append("Aviso: TensorFlow no usa la GPU en Windows nativo desde la 2.10. Correr dentro "
                     "de Docker Desktop con --gpus all.")
    if system["nvidia_smi"]:
        lines.append(f"GPU (nvidia-smi): {'; '.join(system['nvidia_smi'])} | "
                     f"CUDA máx. del driver: {system['driver_max_cuda']}")
        driver = system["nvidia_smi"][0].split(",")[1].strip()
        if driver.split(".")[0].isdigit() and int(driver.split(".")[0]) < MIN_DRIVER_BLACKWELL:
            lines.append(f"Aviso: driver {driver}; Blackwell (RTX 50xx) necesita {MIN_DRIVER_BLACKWELL} "
                         "o superior. Se actualiza en Windows, no dentro del contenedor.")
    else:
        lines.append("nvidia-smi no responde: no hay GPU visible o falta el driver.")

    usable = {}
    for backend, result in report["backends"].items():
        ok, note = backend_status(result)
        usable[backend] = ok
        version = result.get("version", "?")
        cuda = result.get("cuda_build")
        lines.append(f"- {backend} {version} (CUDA {cuda}): {'APTO' if ok else 'NO APTO'}. {note}")
        if result.get("native_kernels") is False:
            lines.append(f"  Sin kernels nativos para {result['arch']} (compilado para "
                         f"{result.get('build_archs')}): CUDA compila PTX al vuelo; la primera "
                         "corrida puede tardar mucho. En Docker, montar un volumen en ~/.nv para "
                         "no perder esa caché entre contenedores.")
        for hint, examples in result.get("log_hints", {}).items():
            lines.append(f"  log [{hint}]: {examples[0][:200]}")
        if not ok and result.get("log_tail"):
            lines.append(f"  última línea del log: {result['log_tail'][-1][:200]}")

    on_gpu = any(r.get("gpus") for r in report["backends"].values())
    if not on_gpu and any(usable.values()):
        verdict = "Sin GPU: la prueba corrió en CPU y solo valida el script, no el entorno de entrenamiento."
    elif usable.get("tensorflow"):
        verdict = "Plan A: entrenar con TensorFlow/Keras en esta GPU."
    elif usable.get("torch"):
        verdict = ("Plan B: entrenar con Keras 3 sobre PyTorch (KERAS_BACKEND=torch) y usar "
                   "TensorFlow solo para exportar el .tflite.")
    elif "torch" not in report["backends"]:
        verdict = "TensorFlow no sirve aquí. Probar el plan B: --backend torch (ver README)."
    else:
        verdict = "Ningún backend entrena en esta GPU. Revisar driver y CUDA, o entrenar en Colab."
    lines.append(f"Veredicto: {verdict}")
    report["verdict"] = verdict
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--backend", choices=["tensorflow", "torch", "all"], default="all")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--steps", type=int, default=20, help="pasos medidos (tras el calentamiento)")
    parser.add_argument("--warmup-steps", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=3600, help="segundos por backend")
    parser.add_argument("--allow-cpu", action="store_true", help="entrenar en CPU si no hay GPU")
    parser.add_argument("--no-weights", action="store_true", help="no descargar pesos de ImageNet")
    parser.add_argument("--no-mixed-precision", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="mostrar el log completo de cada backend")
    parser.add_argument("--worker", choices=sorted(WORKERS), help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.worker:
        result = WORKERS[args.worker](args)
        print(RESULT_MARKER + json.dumps(result, default=str), flush=True)
        return 0

    backends = ["tensorflow", "torch"] if args.backend == "all" else [args.backend]
    report = {"system": system_info(), "args": vars(args), "backends": {}}
    for backend in backends:
        report["backends"][backend] = run_worker(backend, args)
    print(summarize(report))

    out_dir = ROOT / "resultados" / "entorno"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir / f"verificacion_gpu_{stamp}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"Reporte: {out.relative_to(ROOT)}")
    return 0 if any(backend_status(r)[0] for r in report["backends"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
