import re
from aqt import mw
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QImage, QPixmap, QPainter, QColor, QPen, QBrush, QKeyEvent, Qt
)
from ..core.media_utils import normalize_image, save_media_webp

RE_IMG_SRC = re.compile(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)

class ImageCropDialog(QDialog):
    AXES = ("bottom", "top", "left", "right")

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.orig_img = QImage(path)
        self.setWindowTitle("Image Cropper")
        self.resize(640, 720)
        self.preview_base = self.orig_img.scaled(580, 480, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.crop_pcts = {"bottom": 10.0, "top": 0.0, "left": 0.0, "right": 0.0}
        self.axis_idx = 0
        self.init_ui()

    def init_ui(self):
        l = QVBoxLayout(self)
        l.setContentsMargins(12, 12, 12, 12); l.setSpacing(8)
        
        help_box = QLabel("[Q] Axis | [W/Up] +2% | [S/Down] -2% | [R] Reset | [SPACE] 10% Bottom | [ENTER] Save", self)
        help_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        help_box.setStyleSheet("background: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.3); padding: 5px; border-radius: 6px; font-size: 11px; color: #a5b4fc;")
        l.addWidget(help_box)
        
        self.preview = QLabel(self)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background: #111; border: 1px solid #333; border-radius: 8px; min-height: 420px;")
        l.addWidget(self.preview, stretch=1)
        
        self.status = QLabel(self)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("font-weight: bold; font-size: 13px; color: #fbbf24;")
        l.addWidget(self.status)
        
        btn_box = QHBoxLayout()
        btn_r, btn_c, btn_s = QPushButton("Reset (R)", self), QPushButton("Cancel (Esc)", self), QPushButton("Apply (Enter)", self)
        btn_r.clicked.connect(self.reset_crops)
        btn_c.clicked.connect(self.reject)
        btn_s.setStyleSheet("background: #6366f1; color: white; font-weight: bold; padding: 6px 16px; border-radius: 6px;")
        btn_s.clicked.connect(self.accept)
        for b in (btn_r, btn_c, btn_s): btn_box.addWidget(b)
        l.addLayout(btn_box)
        self.update_preview()

    @property
    def cur_axis(self) -> str: return self.AXES[self.axis_idx]

    def reset_crops(self):
        self.crop_pcts = {"bottom": 0.0, "top": 0.0, "left": 0.0, "right": 0.0}
        self.update_preview()

    def keyPressEvent(self, e: QKeyEvent):
        k = e.key()
        if k == Qt.Key.Key_Q: self.axis_idx = (self.axis_idx + 1) % len(self.AXES)
        elif k in (Qt.Key.Key_W, Qt.Key.Key_Up): self.crop_pcts[self.cur_axis] = min(45.0, self.crop_pcts[self.cur_axis] + 2.0)
        elif k in (Qt.Key.Key_S, Qt.Key.Key_Down): self.crop_pcts[self.cur_axis] = max(0.0, self.crop_pcts[self.cur_axis] - 2.0)
        elif k == Qt.Key.Key_R: self.reset_crops()
        elif k == Qt.Key.Key_Space: self.crop_pcts["bottom"] = 0.0 if self.crop_pcts["bottom"] == 10.0 else 10.0
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter): self.accept()
        elif k == Qt.Key.Key_Escape: self.reject()
        else: super().keyPressEvent(e)
        self.update_preview()

    def get_cropped_image(self) -> QImage:
        w, h = self.orig_img.width(), self.orig_img.height()
        top, bot = int(h * (self.crop_pcts["top"] / 100.0)), int(h * (self.crop_pcts["bottom"] / 100.0))
        left, right = int(w * (self.crop_pcts["left"] / 100.0)), int(w * (self.crop_pcts["right"] / 100.0))
        return self.orig_img.copy(left, top, max(10, w - left - right), max(10, h - top - bot))

    def update_preview(self):
        if self.preview_base.isNull(): return
        cv = self.preview_base.copy()
        p = QPainter(cv)
        w, h = cv.width(), cv.height()
        top, bot = int(h * (self.crop_pcts["top"] / 100.0)), int(h * (self.crop_pcts["bottom"] / 100.0))
        left, right = int(w * (self.crop_pcts["left"] / 100.0)), int(w * (self.crop_pcts["right"] / 100.0))
        kw, kh = max(10, w - left - right), max(10, h - top - bot)
        
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(QColor(0, 0, 0, 150)))
        if top > 0: p.drawRect(0, 0, w, top)
        if bot > 0: p.drawRect(0, h - bot, w, bot)
        if left > 0: p.drawRect(0, top, left, kh)
        if right > 0: p.drawRect(w - right, top, right, kh)
        p.setPen(QPen(QColor(245, 158, 11), 3)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(left, top, kw, kh); p.end()
        
        self.preview.setPixmap(QPixmap.fromImage(cv))
        self.status.setText(f"Axis: {self.cur_axis.upper()} | T:{self.crop_pcts['top']:.0f}% B:{self.crop_pcts['bottom']:.0f}% L:{self.crop_pcts['left']:.0f}% R:{self.crop_pcts['right']:.0f}%")