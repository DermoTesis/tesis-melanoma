"""Descarga del ISIC Archive las fotos de prueba y crea copias de 1366x1024 para la galería."""

import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image

LESIONES = [
    # (carpeta, foto 1, foto 2)
    ("1_HAM_0001974_melanoma_alto", "ISIC_0033533", "ISIC_0033807"),
    ("2_HAM_0007538_melanoma_intermedio", "ISIC_0024315", "ISIC_0031941"),
    ("3_HAM_0003176_melanoma_bajo", "ISIC_0028148", "ISIC_0030756"),
    ("4_HAM_0001726_melanoma_falso_negativo", "ISIC_0024367", "ISIC_0024700"),
    ("5_HAM_0002701_nevus_falso_positivo", "ISIC_0024328", "ISIC_0026764"),
    ("6_HAM_0000181_nevus_sin_alerta", "ISIC_0033543", "ISIC_0034185"),
]


def obtener(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "dermavia-pruebas"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main(destino: Path) -> None:
    creditos = []
    for carpeta, *ids in LESIONES:
        d = destino / carpeta
        d.mkdir(parents=True, exist_ok=True)
        for n, isic in enumerate(ids, start=1):
            meta = json.loads(obtener(f"https://api.isic-archive.com/api/v2/images/{isic}/"))
            assert meta["isic_id"] == isic
            assert meta["metadata"]["acquisition"].get("image_type") == "dermoscopic"
            original = d / f"foto{n}_{isic}.jpg"
            original.write_bytes(obtener(meta["files"]["full"]["url"]))
            img = Image.open(original)
            img.load()
            ampliada = img.convert("RGB").resize((1366, 1024), Image.LANCZOS)
            ampliada.save(d / f"foto{n}_{isic}_1024.jpg", quality=95)
            creditos.append(f"{isic}: {meta.get('attribution')} ({meta.get('copyright_license')})")
            print(carpeta, isic, img.size, "->", ampliada.size)
    (destino / "creditos.txt").write_text("\n".join(creditos) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
