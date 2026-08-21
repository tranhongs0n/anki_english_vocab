import os
import uuid
from typing import Union, Optional
try:
    from aqt import mw
    from aqt.qt import QImage, QPainter, QColor, Qt
except ImportError:
    mw, QImage, QPainter, QColor, Qt = None, None, None, None, None
from .deck_utils import get_addon_config

def get_image_cfg() -> dict:
    return get_addon_config().get('image', {})

def normalize_image(src: Union[str, QImage], target_size: Optional[int] = None) -> Optional[QImage]:
    dim = target_size or get_image_cfg().get('target_height', 300)
    if isinstance(src, str):
        if not os.path.exists(src): return None
        img = QImage(src)
        if img.isNull(): return None
        if os.path.splitext(src)[1].lower() == '.webp' and img.height() <= dim and not img.hasAlphaChannel() and (img.width() >= img.height() or img.width() == dim):
            return None
    elif isinstance(src, QImage):
        img = src
        if img.isNull(): return None
    else: return None

    w, h, alpha = img.width(), img.height(), img.hasAlphaChannel()
    if alpha or h > w:
        sc = img.scaled(dim, dim, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        sw, sh = sc.width(), sc.height()
        cw, ch = (dim, dim) if h > w else (sw, sh)
        cv = QImage(cw, ch, QImage.Format.Format_RGB32)
        cv.fill(QColor(255, 255, 255))
        p = QPainter(cv)
        p.drawImage((cw - sw) // 2, (ch - sh) // 2, sc)
        p.end()
        return cv
    if h > dim: return img.scaledToHeight(dim, Qt.TransformationMode.SmoothTransformation)
    return img if (isinstance(src, str) and os.path.splitext(src)[1].lower() != '.webp') else None

def save_media_webp(qimg: QImage, prefix: str = '') -> str:
    if not mw or not mw.col or not qimg or qimg.isNull(): return ''
    name = f'{prefix}{uuid.uuid4().hex[:8]}.webp'
    out = os.path.join(mw.col.media.dir(), name)
    return name if qimg.save(out, 'WEBP', get_image_cfg().get('webp_quality', 80)) else ''