"""Createch visual treatment shared with the real Qt projector.

Rendering only: the circles and physics remain owned by game.py.
"""
from __future__ import annotations

from pathlib import Path
import math
import time

from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtSvg import QSvgRenderer

FUCHSIA = QColor("#f629bb")
SOFT = QColor("#ff91de")
SVG_FILE = Path(__file__).parent / "static" / "createch-director.svg"
_sprite = None


def _director():
    global _sprite
    if _sprite is None:
        _sprite = QSvgRenderer(str(SVG_FILE))
    return _sprite


def letter(p: QPainter, x: float, y: float, radius: float, angle: float = 0):
    """The distinctive angular K + substantial rectangular period."""
    p.save()
    p.translate(x, y)
    p.rotate(angle)
    # Scale within existing circular collider, without affecting its behaviour.
    k = radius / 27.
    p.scale(k, k)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(FUCHSIA)
    polygon = QPolygonF([QPointF(a,b) for a,b in [
        (-24,-23),(-11,-23),(-11,-5),(-4,-5),(12,-23),(27,-23),
        (9,-1),(27,22),(11,22),(-3,5),(-11,5),(-11,22),(-24,22),
        (-24,4),(-13,4),(-13,-5),(-24,-5)
    ]])
    p.drawPolygon(polygon)
    p.drawRect(QRectF(17,12,13,11))
    p.restore()


def paint_createch(p: QPainter, snapshot: dict, dark: bool = True):
    bg = QColor("#090613" if dark else "#fff5fc")
    fg = QColor("#ffecfa" if dark else "#3a1535")
    p.fillRect(QRectF(0,0,1600,1000), bg)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor("#79205b") if dark else QColor("#e7a1d5"),2))
    for x in range(100,1540,96):
        p.drawLine(QPointF(x, 70),QPointF(x,78))
    p.setPen(QPen(QColor("#f629bb"),5))
    p.drawLine(QPointF(45,160),QPointF(45,45))
    p.drawLine(QPointF(45,45),QPointF(240,45))
    p.drawLine(QPointF(1360,45),QPointF(1555,45))
    p.drawLine(QPointF(1555,45),QPointF(1555,160))
    p.drawLine(QPointF(45,840),QPointF(45,955))
    p.drawLine(QPointF(45,955),QPointF(500,955))
    p.drawLine(QPointF(1130,955),QPointF(1555,955))
    p.drawLine(QPointF(1555,955),QPointF(1555,840))
    p.setPen(QPen(QColor("#7b235c"),1.5))
    p.drawLine(QPointF(55,100),QPointF(1545,100))
    p.drawLine(QPointF(55,900),QPointF(1545,900))
    p.setPen(FUCHSIA)
    p.setFont(QFont("DejaVu Sans",23,QFont.Weight.Bold))
    p.drawText(QRectF(75,50,480,40),Qt.AlignmentFlag.AlignLeft,"CREATECH / INTERACTIVE")
    p.setFont(QFont("DejaVu Sans",17,QFont.Weight.Medium))
    p.drawText(QRectF(1230,50,290,40),Qt.AlignmentFlag.AlignRight,"01  /  PLAY")
    p.setPen(QPen(FUCHSIA,1.2))
    for x,y in ((65,180),(1535,180),(65,825),(1535,825)):
        p.drawLine(QPointF(x-10,y),QPointF(x+10,y))
        p.drawLine(QPointF(x,y-10),QPointF(x,y+10))
    phase = snapshot.get("phase", "idle")
    balls = snapshot.get("balls") or []
    if phase in ("playing","won","preview"):
        gx,gy,gr = snapshot.get("goal",[.78,.72,45])
        x,y = gx*1600., gy*1000.
        renderer = _director()
        if renderer.isValid():
            # Bucket rim centre is exactly at goal_x/goal_y.
            renderer.render(p, QRectF(x-95,y-156,190,255))
        else:
            p.setBrush(FUCHSIA)
            p.drawRect(QRectF(x-43,y,86,32))
        if snapshot.get("hits_fx", 0)>0:
            fx=float(snapshot["hits_fx"])
            p.setPen(QPen(SOFT,4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(x,y+10),gr+fx*26,gr+fx*26)
    now=time.monotonic()
    for b in balls:
        x,y,r=b[0]*1600.,b[1]*1000.,float(b[2])
        if -40<x<1640 and -40<y<1040:
            letter(p,x,y,max(r,13)*1.45, math.sin(now*1.2+x*.01)*8)
    p.setPen(fg)
    p.setFont(QFont("DejaVu Sans",30,QFont.Weight.Bold))
    p.drawText(QRectF(75,125,400,65),Qt.AlignmentFlag.AlignLeft,
               f"{snapshot.get('score',0):02d} / {snapshot.get('target',5):02d}")
    p.setPen(FUCHSIA)
    # Bottom-right lockup, safely separated from the bucket and main playfield.
    font=QFont("DejaVu Sans",78,QFont.Weight.Black)
    font.setStretch(90)
    p.setFont(font)
    p.drawText(QRectF(865,847,650,100),Qt.AlignmentFlag.AlignRight,"КРЕАТЕХ.")
    if phase == "preview":
        p.setFont(QFont("DejaVu Sans",20,QFont.Weight.Bold))
        p.drawText(QRectF(65,860,600,45),Qt.AlignmentFlag.AlignLeft,"PREVIEW  /  THEME")
    if snapshot.get("demo"):
        p.setFont(QFont("DejaVu Sans",20,QFont.Weight.Bold))
        p.drawText(QRectF(65,860,650,45),Qt.AlignmentFlag.AlignLeft,"AUTO DEMO  /  SIMULATION")
    if phase=="won":
        p.fillRect(QRectF(450,380,700,160),QColor("#120a23"))
        p.setPen(SOFT)
        p.setFont(QFont("DejaVu Sans",66,QFont.Weight.Black))
        p.drawText(QRectF(460,396,680,132),Qt.AlignmentFlag.AlignCenter,"ПОЙМАНО!")
