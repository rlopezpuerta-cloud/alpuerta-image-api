"""
Alpuerta Premiaciones — Image Generator API
POST /api/generate
Body: { "tipo": "2", "copy": "...", "cta": "...", "asset_id": "medalla_01" (opcional) }
Returns: { "image_url": "https://..." }
"""
from http.server import BaseHTTPRequestHandler
import json, base64, urllib.request, io, random, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from scipy.ndimage import gaussian_filter
import textwrap

CLOUDINARY_CLOUD = os.environ.get("CLOUDINARY_CLOUD", "dx4wlvbxt")
CLOUDINARY_PRESET = os.environ.get("CLOUDINARY_UPLOAD_PRESET", "alpuerta_test")

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
OUTFIT_FONT = os.path.join(ASSETS_DIR, "Outfit.ttf")
LOGO_FILE   = os.path.join(ASSETS_DIR, "logo.png")

ASSETS_MEDALLAS = [f"medalla_{str(i).zfill(2)}" for i in range(1, 23)]
ASSETS_TROFEOS  = [f"trofeo_{str(i).zfill(2)}"  for i in range(1, 19)]

TAG_MAP = {
    "1": "medalla", "2": "medalla", "3": "trofeo",
    "4": "trofeo",  "5": "medalla", "6": "trofeo", "7": "medalla"
}

def get_asset(tipo, asset_id=None):
    if asset_id:
        return asset_id
    pool = ASSETS_MEDALLAS if TAG_MAP.get(str(tipo), "medalla") == "medalla" else ASSETS_TROFEOS
    return random.choice(pool)

def editar_foto(img):
    """Edición fotográfica: limpiar fondo, mejorar contraste y nitidez."""
    # Rotar si es necesario por EXIF
    try:
        from PIL import ExifTags
        exif = img._getexif()
        if exif:
            for tag, val in exif.items():
                if ExifTags.TAGS.get(tag) == "Orientation":
                    if val == 6: img = img.rotate(-90, expand=True)
                    elif val == 8: img = img.rotate(90, expand=True)
                    elif val == 3: img = img.rotate(180, expand=True)
    except:
        pass

    # Crop cuadrado centrado
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side)//2, (h - side)//2, (w + side)//2, (h + side)//2))

    # Limpiar fondo gris/blanco → blanco puro
    arr = np.array(img).astype(float)
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    lum = (r + g + b) / 3
    max_c = np.maximum(np.maximum(r, g), b)
    min_c = np.minimum(np.minimum(r, g), b)
    with np.errstate(divide="ignore", invalid="ignore"):
        sat = np.where(max_c > 0, (max_c - min_c) / max_c, 0)
    fondo = gaussian_filter(((lum > 200) & (sat < 0.15)).astype(float), sigma=2)
    fondo = np.clip(fondo, 0, 1)
    for ch in range(3):
        arr[:,:,ch] = arr[:,:,ch] * (1 - fondo) + 255 * fondo
    img = Image.fromarray(arr.astype(np.uint8))

    # Contraste, nitidez, saturación, brillo
    img = ImageEnhance.Contrast(img).enhance(1.35)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=80, threshold=2))
    img = ImageEnhance.Color(img).enhance(1.25)
    img = ImageEnhance.Brightness(img).enhance(1.08)

    return img.resize((1080, 1080), Image.LANCZOS)

def aplicar_template(photo, copy_text, cta_text):
    """Compone la imagen final 1080x1350 con template de marca Alpuerta."""
    canvas = Image.new("RGB", (1080, 1350), (255, 255, 255))
    canvas.paste(photo, (0, 0))
    draw = ImageDraw.Draw(canvas)

    # Línea dorada divisora
    draw.rectangle([0, 1080, 1080, 1083], fill=(244, 196, 48))

    # Fuentes
    font_copy = ImageFont.truetype(OUTFIT_FONT, 27)
    font_cta  = ImageFont.truetype(OUTFIT_FONT, 23)

    # Logo sin fondo
    logo = Image.open(LOGO_FILE).convert("RGBA")
    la = np.array(logo)
    la[(la[:,:,0] > 240) & (la[:,:,1] > 240) & (la[:,:,2] > 240), 3] = 0
    logo = Image.fromarray(la).resize((105, 105), Image.LANCZOS)

    FRANJA_TOP = 1083
    FRANJA_H   = 267
    LOGO_X     = 1080 - 105 - 35
    LOGO_Y     = FRANJA_TOP + (FRANJA_H // 2) - 52

    # Bloque de texto centrado verticalmente en la franja
    lines = textwrap.wrap(copy_text, width=48)
    total_h = len(lines) * 36 + 14 + 30
    y = FRANJA_TOP + (FRANJA_H - total_h) // 2

    for line in lines:
        draw.text((50, y), line, fill=(26, 26, 26), font=font_copy)
        y += 36

    draw.text((50, y + 14), cta_text, fill=(196, 154, 26), font=font_cta)
    canvas.paste(logo, (LOGO_X, LOGO_Y), logo)

    return canvas

def subir_a_cloudinary(img):
    """Sube la imagen generada a Cloudinary y devuelve la URL pública."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    b64 = base64.b64encode(buf.getvalue()).decode()

    import time
    public_id = f"alpuerta_posts/post_{int(time.time())}"
    payload = json.dumps({
        "upload_preset": CLOUDINARY_PRESET,
        "public_id": public_id,
        "tags": "alpuerta_post,generado",
        "file": f"data:image/jpeg;base64,{b64}"
    }).encode()

    req = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD}/image/upload",
        data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["secure_url"]

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))

            tipo     = str(body.get("tipo", "2"))
            copy_txt = body.get("copy", "")
            cta_txt  = body.get("cta", "")
            asset_id = body.get("asset_id", None)

            # Seleccionar asset
            asset = get_asset(tipo, asset_id)

            # Descargar foto de Cloudinary
            url = f"https://res.cloudinary.com/{CLOUDINARY_CLOUD}/image/upload/alpuerta_assets/{asset}.jpg"
            with urllib.request.urlopen(url, timeout=30) as r:
                foto = Image.open(io.BytesIO(r.read())).convert("RGB")

            # Procesar
            foto_ed = editar_foto(foto)
            post    = aplicar_template(foto_ed, copy_txt, cta_txt)
            img_url = subir_a_cloudinary(post)

            self._respond(200, {"image_url": img_url, "asset_used": asset})

        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._respond(200, {"status": "ok", "service": "Alpuerta Image Generator"})
