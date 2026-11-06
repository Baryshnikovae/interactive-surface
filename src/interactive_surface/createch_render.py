"""Createch event projection visuals (calibrated wall coordinates, 1600×1000).

Visual scene is shared in design with the browser projector. Gameplay, collision
and scoring are exclusively owned by game.py. Keep generated portrait optional
to allow visual review independently of the deployment.
"""
from __future__ import annotations
from pathlib import Path
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QImage, QPainter, QPainterPath,
                          QPen, QPolygonF)
from PySide6.QtSvg import QSvgRenderer

PINK = QColor("#f629bb")
SOFT = QColor("#ff90de")
ASSET_ROOT = Path(__file__).parent / "static"
_portrait = None
_fallback = None


def _sprite():
    global _portrait, _fallback
    if _portrait is None:
        file = ASSET_ROOT / "createch-director.png"
        _portrait = QImage(str(file)) if file.is_file() else QImage()
        _fallback = QSvgRenderer(str(ASSET_ROOT / "createch-director.svg"))
    return _portrait, _fallback


def _line(p, points, color, width=2):
    p.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    p.drawPath(path)


def _text(p, text, rect, size, color, weight=QFont.Weight.Bold, align=Qt.AlignmentFlag.AlignLeft):
    p.setPen(QColor(color))
    font = QFont("DejaVu Sans", size, weight)
    p.setFont(font)
    p.drawText(QRectF(*rect), align | Qt.AlignmentFlag.AlignVCenter, text)


def _frame(p, dark):
    p.fillRect(QRectF(0, 0, 1600, 1000), QColor("#0b0518" if dark else "#fff7fc"))
    _line(p, [(62,25),(1538,25),(1570,57),(1570,944),(1541,976),
              (60,976),(30,944),(30,58),(62,25)], "#f324b4", 4)
    _line(p, [(75,94),(415,94),(467,43)], "#f629bb", 4)
    _line(p, [(1296,43),(1520,43)], "#a82d87", 2)
    _line(p, [(70,934),(1030,934),(1050,922),(1518,922)], "#92166c", 2)
    _text(p, "CREATECH  /  INTERACTIVE", (82,47,550,42), 22, "#ff4fc9")
    _text(p, "01 / INTERACTIVE PLAY", (1040,48,472,37), 16, "#c9a6c3",
          QFont.Weight.Medium, Qt.AlignmentFlag.AlignRight)
    _text(p, "КРЕАТЕХ.", (1000,827,515,92), 70, "#f629bb",
          QFont.Weight.Black, Qt.AlignmentFlag.AlignRight)


def letter(p, x, y, radius, angle=0):
    p.save()
    p.translate(x,y)
    p.rotate(angle)
    scale = radius / 29.
    p.scale(scale,scale)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(PINK)
    p.drawPolygon(QPolygonF([QPointF(a,b) for a,b in
        [(-26,-23),(-13,-23),(-13,-4),(-6,-4),(10,-23),(26,-23),
        (7,-2),(25,21),(9,21),(-5,5),(-13,5),(-13,21),(-26,21)]]))
    # The dot is detached and visibly rectangular even at small sizes.
    p.drawRect(QRectF(17,11,12,11))
    p.restore()


def _actor(p, goal, hits):
    x, y = goal[0]*1600, goal[1]*1000
    img, fallback = _sprite()
    w, h = 275., 366.
    # PNG bucket rim is approximately (0.60w, 0.325h) in the full sprite.
    rect = QRectF(x - .60*w, y - .325*h, w, h)
    p.save()
    if not img.isNull():
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawImage(rect, img)
    elif fallback and fallback.isValid():
        fallback.render(p, rect)
    p.restore()
    if hits:
        p.save()
        p.setPen(QPen(SOFT, 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(x,y+9), 35+24*hits, 14+15*hits)
        p.restore()


def _sticker(p, corners):
    if not corners:
        return
    polygon=QPolygonF([QPointF(x*1600,y*1000) for x,y in corners])
    p.save()
    p.setBrush(QColor("#5b174a"))
    p.setPen(QPen(SOFT,4))
    p.drawPolygon(polygon)
    for j in range(4):
        a=polygon[j]
        b=polygon[(j+1)%4]
        if j==0:
            _line(p,[(a.x(),a.y()),(b.x(),b.y())],"#fff3fd",3)
    cx=sum(pt.x() for pt in polygon)/4.
    cy=sum(pt.y() for pt in polygon)/4.
    _text(p,"СТИКЕР / ОТСКОК",(cx-120,cy-70,245,35),17,"#ff7bd5")
    p.restore()


def paint_createch(p: QPainter, snapshot: dict, dark=True):
    p.save()
    _frame(p, dark)
    phase=snapshot.get("phase","idle")
    goal=snapshot.get("goal", [.25,.705,31.])
    for sticker in snapshot.get("demo_stickers",()):
        _sticker(p,sticker)
    if phase in ("playing","won","preview"):
        _actor(p, goal, float(snapshot.get("hits_fx",0)))
    for ball in snapshot.get("balls") or ():
        x,y,r=ball[0]*1600,ball[1]*1000,float(ball[2])
        if 120<y<940 and -25<x<1625:
            letter(p,x,y,min(30,r),float(ball[5] if len(ball)>5 else 0))
    fg="#ffebf9" if dark else "#421935"
    _text(p,f"{snapshot.get('score',0):02d} / {snapshot.get('target',5):02d}",
          (83,125,310,62),32,fg)
    if snapshot.get("demo"):
        _text(p,"AUTO DEMO  •  СТИКЕР ОТКЛОНЯЕТ БУКВУ",
              (1000,107,520,45),18,"#ff8bd9",QFont.Weight.Bold,Qt.AlignmentFlag.AlignRight)
    elif phase=="preview":
        _text(p,"PREVIEW  •  CREATECH",(1010,107,505,45),18,"#ff8bd9",QFont.Weight.Bold,Qt.AlignmentFlag.AlignRight)
    if phase=="won":
        p.fillRect(QRectF(485,375,630,145),QColor("#180920"))
        _text(p,"ПОЙМАНО!",(510,380,590,128),62,"#ff67ce",
              QFont.Weight.Black,Qt.AlignmentFlag.AlignCenter)
    p.restore()
