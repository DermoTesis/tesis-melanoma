"""Genera las imágenes fuente del ícono de Dermavía (assets/icon/).

El ícono es el mismo logo de la app (`DermaviaLogo` en lib/features/auth/auth_widgets.dart):
un cuadrado verde `AppColors.primary` con esquinas redondeadas y una «D» blanca en
Figtree Bold, con la misma proporción (letra de 0.46 del lado, radio de 0.29 del lado).

Uso (Figtree se descarga de https://github.com/google/fonts/tree/main/ofl/figtree):

    python assets/icon/generar_icono.py ruta/a/Figtree[wght].ttf
    dart run flutter_launcher_icons

Salidas:
- icon.png: ícono completo, para Android 7 (sin íconos adaptables).
- foreground.png: la «D» sobre fondo transparente, para el ícono adaptable (Android 8+);
  el fondo verde lo pone `adaptive_icon_background` en pubspec.yaml.
- monochrome.png: la misma «D», para los íconos temáticos de Android 13+.
- android/app/src/main/res/drawable-*/ic_notification.png: la «D» sola, para la barra de
  estado en las alertas push (Android pinta de blanco todo lo que no es transparente, así
  que el ícono completo se vería como un cuadrado). Se escribe directamente en Android.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PRIMARY = (0x1D, 0x6B, 0x4F, 255)
WHITE = (255, 255, 255, 255)
SIZE = 1024
SS = 4  # sobremuestreo para bordes suaves
OUT = Path(__file__).resolve().parent
RES = OUT.parent.parent / "android" / "app" / "src" / "main" / "res"

# Ícono de notificación: 24 dp, con la letra ocupando unos 20 dp de alto.
NOTIFICATION_DP = 24
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}


def glyph(canvas: Image.Image, font_path: str, logo_side: float) -> None:
    """Dibuja la «D» centrada en el lienzo, a escala de un logo de lado `logo_side`."""
    font = ImageFont.truetype(font_path, round(logo_side * 0.46))
    font.set_variation_by_name("Bold")
    draw = ImageDraw.Draw(canvas)
    left, top, right, bottom = draw.textbbox((0, 0), "D", font=font)
    w, h = canvas.size
    draw.text(((w - (right - left)) / 2 - left, (h - (bottom - top)) / 2 - top), "D",
              font=font, fill=WHITE)


def render(font_path: str, *, background: bool, logo_side: float, inset: float = 0) -> Image.Image:
    big = SIZE * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    if background:
        pad = inset * big
        ImageDraw.Draw(img).rounded_rectangle(
            (pad, pad, big - pad, big - pad), radius=(big - 2 * pad) * 0.29, fill=PRIMARY)
    glyph(img, font_path, logo_side * SS)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    font = sys.argv[1]
    # Ícono heredado: el logo con un margen como el de los íconos de Android.
    inset = 0.06
    render(font, background=True, logo_side=SIZE * (1 - 2 * inset), inset=inset).save(OUT / "icon.png")
    # Adaptable: solo se ve el círculo/forma central de 72/108 del lienzo; la «D» guarda la
    # proporción del logo respecto de esa zona visible.
    visible = SIZE * 72 / 108
    fg = render(font, background=False, logo_side=visible)
    fg.save(OUT / "foreground.png")
    fg.save(OUT / "monochrome.png")
    # Notificación: la «D» ocupa unos 19 de los 24 dp de alto (zona útil de Material).
    note = render(font, background=False, logo_side=SIZE * 2.2)
    for density, scale in DENSITIES.items():
        px = round(NOTIFICATION_DP * scale)
        folder = RES / f"drawable-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        note.resize((px, px), Image.LANCZOS).save(folder / "ic_notification.png")


if __name__ == "__main__":
    main()
