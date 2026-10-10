"""Projector-side Qt painter: 60 Hz visuals, independent of camera and physics."""
from __future__ import annotations

import math
import time

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QBrush, QFont, QPainter, QPen, QRadialGradient, QLinearGradient, QTransform


def _color(value: str, fallback="#70e9ff") -> QColor:
    c = QColor(value)
    return c if c.isValid() else QColor(fallback)


def _ring(p: QPainter, x: float, y: float, r: float, color: QColor, thickness: float = 3):
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(color, thickness))
    p.drawEllipse(QPointF(x, y), r, r)


def _glow(p: QPainter, x: float, y: float, radius: float, tint: QColor, opacity: int):
    grad = QRadialGradient(QPointF(x, y), radius)
    inner = QColor(tint)
    inner.setAlpha(opacity)
    transparent = QColor(tint)
    transparent.setAlpha(0)
    grad.setColorAt(0., inner)
    grad.setColorAt(.3, inner)
    grad.setColorAt(1., transparent)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawEllipse(QPointF(x, y), radius, radius)


def paint_game(p: QPainter, snapshot: dict, quad: list, display_w: int, display_h: int, background="black"):
    """Render in calibrated wall units, warped by the wall→projector homography.

    QPainter's projective QTransform applies to ALL circles, HUD and effects. The
    white/black unprojected framebuffer is cleared first; no costly full-frame warp.
    """
    dark = background != "white"
    p.fillRect(QRectF(0, 0, display_w, display_h), QColor("#000000" if dark else "#ffffff"))
    if not snapshot:
        return
    src = np.float32([[0, 0], [1600, 0], [1600, 1000], [0, 1000]])
    dst = np.float32([[x*display_w, y*display_h] for x,y in quad])
    h = cv2.getPerspectiveTransform(src, dst)
    t = QTransform(float(h[0,0]),float(h[1,0]),float(h[2,0]),
                   float(h[0,1]),float(h[1,1]),float(h[2,1]),
                   float(h[0,2]),float(h[1,2]),float(h[2,2]))
    p.save()
    p.setTransform(t, False)
    p.setClipRect(QRectF(0, 0, 1600, 1000))
    settings = snapshot.get("settings") or {}
    visual = settings.get("visual_style", "neon")
    design = settings.get("ball_design", "orbit")
    tint = _color(settings.get("ball_color", "#70e9ff"))
    accent = QColor("#7b61ff") if dark else QColor("#4524a5")
    fg = QColor("#f3fbff") if dark else QColor("#19334b")
    now = time.monotonic()
    phase = snapshot.get("phase", "idle")
    balls = snapshot.get("balls") or []
    if phase in ("playing", "won"):
        gx, gy, gr = snapshot.get("goal", [.78, .72, 45])
        x, y = gx*1600., gy*1000.
        pulse = float(snapshot.get("hits_fx", 0))
        if visual == "neon":
            _glow(p, x, y, gr*2.45+pulse*18, accent, 95+round(60*pulse))
            _glow(p, x, y, gr*1.22, QColor("#000000") if dark else QColor("#c5b8ef"), 210)
            _ring(p, x, y, gr+6+4*math.sin(now*1.8), QColor("#a59bff") if dark else accent, 4.2)
            _ring(p, x, y, gr*.74, QColor("#312766") if dark else QColor("#7865bf"), 4)
            _ring(p, x, y, gr*.43, QColor("#c7c1ff") if dark else QColor("#7865bf"), 1.8)
        else:
            _ring(p, x, y, gr+5+pulse*5, accent, 7)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#0e0d27") if dark else QColor("#e7e6f5"))
            p.drawEllipse(QPointF(x,y), gr-2, gr-2)
            _ring(p, x, y, gr*.58, QColor("#a5a1ec") if dark else QColor("#6654bd"), 3)
        # A restrained target highlight moves in two axes while staying off spawn x.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#fff"))
        p.drawEllipse(QPointF(x-gr*.28, y-gr*.3), 3.4, 3.4)
    for ball in balls:
        x, y, r = ball[0]*1600., ball[1]*1000., float(ball[2])
        if not (-40 < x < 1640 and -40 < y < 1040):
            continue
        if visual == "neon":
            _glow(p, x, y, r*3.0, tint, 50)
            shadow = QRadialGradient(QPointF(x-r*.4, y-r*.45), r*2.)
            shadow.setColorAt(0, tint.lighter(170))
            shadow.setColorAt(.48, tint)
            shadow.setColorAt(1, tint.darker(210))
            p.setBrush(QBrush(shadow))
            p.setPen(QPen(tint.lighter(155), 1.7))
            p.drawEllipse(QPointF(x,y), r, r)
        else:
            p.setBrush(tint)
            p.setPen(QPen(tint.darker(180), 2))
            p.drawEllipse(QPointF(x,y), r, r)
        if design == "orbit":
            _ring(p,x,y,r*.58,QColor("#ffffff" if dark else "#243247"),1.6)
            a = now*3.2 + ball[0]*12
            dot = QPointF(x+math.cos(a)*r*.6,y+math.sin(a)*r*.6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(dot, 2.5, 2.5)
        elif design == "comet":
            vx, vy = float(ball[3]) * 1600., float(ball[4]) * 1000.
            speed = math.hypot(vx,vy)
            if speed > 5:
                travel = min(r*2.5, speed*.038)
                p.setPen(QPen(tint.lighter(150), max(2,r*.26), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(x,y), QPointF(x-vx/speed*travel,y-vy/speed*travel))
        if visual == "neon":
            p.setBrush(QColor(255,255,255,200));p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x-r*.30,y-r*.36),max(2,r*.19),max(2,r*.19))
    # HUD occupies calibrated wall space and is intentionally minimal.
    p.setPen(fg)
    p.setFont(QFont("Sans Serif", 35, QFont.Weight.Bold))
    if phase == "playing":
        # Decorative heading removed; score remains on the operator dashboard.
        p.setFont(QFont("Sans Serif", 28, QFont.Weight.Medium))
        p.drawText(QRectF(40, 78, 400, 55), Qt.AlignmentFlag.AlignLeft,
                   f"{snapshot.get('score',0)} / {snapshot.get('target',5)}")
    elif phase == "won":
        p.setBrush(QColor(15,26,48,236) if dark else QColor(255,255,255,238))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(325,365,950,255),38,38)
        p.setPen(fg)
        p.setFont(QFont("Sans Serif", 72, QFont.Weight.Bold))
        p.drawText(QRectF(350,405,900,100), Qt.AlignmentFlag.AlignCenter, "ОТЛИЧНО!")
        p.setFont(QFont("Sans Serif", 28, QFont.Weight.Medium))
        caption = "Следующий раунд скоро начнётся" if settings.get('cycle_mode') != 'manual' else "Новый раунд запускается с пульта"
        p.drawText(QRectF(390,515,820,75), Qt.AlignmentFlag.AlignCenter,caption)
    p.restore()
