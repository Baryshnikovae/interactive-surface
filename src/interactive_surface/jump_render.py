"""SkyHop projection artwork in calibrated 1600×1000 wall coordinates.

Every effect is drawn with QPainter primitives: no network, font downloads,
external textures, or dependency on the browser preview.
"""
from __future__ import annotations

import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QBrush, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

PALETTES = {
    "cloud": ("#e7f5f5", "#b9e0e6", "#26445b", "#ffcb70", "#79c9b6"),
    "coffee": ("#f4e6d1", "#e1c7a4", "#5d3b35", "#d69b61", "#b07a63"),
    "neon": ("#0c1230", "#251d55", "#f3f1ff", "#f9c55c", "#70e4d8"),
}


def _ellipse(p, x, y, rx, ry, color):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(x-rx, y-ry, 2*rx, 2*ry))


def _label(p, value, x, y, width, height, size, color, align=Qt.AlignmentFlag.AlignLeft, bold=True):
    p.setPen(QColor(color))
    p.setFont(QFont("DejaVu Sans", size, QFont.Weight.Bold if bold else QFont.Weight.Medium))
    p.drawText(QRectF(x, y, width, height), align | Qt.AlignmentFlag.AlignVCenter, str(value))


def _cloud(p, x, y, scale, color):
    _ellipse(p, x, y, 90*scale, 24*scale, color)
    _ellipse(p, x-37*scale, y-13*scale, 45*scale, 34*scale, color)
    _ellipse(p, x+15*scale, y-22*scale, 58*scale, 44*scale, color)


def _hero(p, hero, now, fx, theme, phase):
    x, y, radius, vx, vy = hero
    if not -100 < y < 1100:
        return
    body = {"cloud": "#f7ad8c", "coffee": "#ba826a", "neon": "#8e80ff"}[theme]
    shadow = {"cloud": "#d77c79", "coffee": "#85554a", "neon": "#6655cb"}[theme]
    p.save()
    p.translate(x, y)
    tilt = max(-15., min(15., vx * .028))
    p.rotate(tilt)
    squash = 1. + .16*fx
    stretch = 1. - .12*fx
    p.scale(squash, stretch)
    # Two ears, subtly animated by vertical speed.
    sway = max(-6., min(6., vy * .006))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(body))
    p.drawRoundedRect(QRectF(-24, -65+sway, 16, 47), 9, 9)
    p.drawRoundedRect(QRectF(8, -68-sway, 16, 50), 9, 9)
    p.setBrush(QColor(shadow))
    p.drawRoundedRect(QRectF(-19, -59+sway, 6, 30), 3, 3)
    p.drawRoundedRect(QRectF(13, -61-sway, 6, 30), 3, 3)
    # Soft circular body with a restrained gradient.
    grad = QRadialGradient(QPointF(-10,-12), 66)
    grad.setColorAt(0, QColor(body).lighter(120))
    grad.setColorAt(1, QColor(shadow))
    p.setBrush(QBrush(grad))
    p.drawEllipse(QRectF(-35,-35,70,69))
    _ellipse(p,-19,31,13,7,shadow)
    _ellipse(p,19,31,13,7,shadow)
    _ellipse(p,-12,-2,3.5,5,"#322d40")
    _ellipse(p,12,-2,3.5,5,"#322d40")
    _ellipse(p,0,9,3.5,2.7,"#7d4652")
    _ellipse(p,-23,9,7,4,"#f28c96")
    _ellipse(p,23,9,7,4,"#f28c96")
    _ellipse(p,-12,-4,1.3,1.3,"#ffffff")
    _ellipse(p,12,-4,1.3,1.3,"#ffffff")
    p.restore()
    if fx > 0:
        p.setPen(QPen(QColor("#fff5ce"), 4*fx))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(x, y+31), 38+36*(1-fx), 11+13*(1-fx))


def paint_jump(p: QPainter, snapshot: dict, dark=True):
    j = snapshot.get("jump") or {}
    if not j:
        return
    theme = (snapshot.get("settings") or {}).get("jump_theme", "cloud")
    if theme not in PALETTES:
        theme = "cloud"
    bg1, bg2, ink, gold, accent = PALETTES[theme]
    now = float(j.get("elapsed", 0))
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    bg = QLinearGradient(0, 0, 0, 1000)
    bg.setColorAt(0, QColor(bg1))
    bg.setColorAt(1, QColor(bg2))
    p.fillRect(QRectF(0,0,1600,1000), QBrush(bg))
    # Parallax backdrop: cosmetic only, never affects collision geometry.
    offset = float(j.get("camera",0))
    for i in range(11):
        x = 90+(i*307)%1550
        y = ((i*197+offset*.18)%1280)-140
        if theme == "neon":
            p.setPen(QPen(QColor("#5c4b9c"),2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(x,y), 24+(i%4)*12,24+(i%4)*12)
        else:
            _cloud(p,x,y,.45+(i%3)*.24,"#ffffff" if theme=="cloud" else "#fff3df")
    # Finish arch stays in world space.
    finish = float(j.get("finish_y", -999))
    if -130 < finish < 1050:
        p.setPen(QPen(QColor(accent),9,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(240,finish),QPointF(1360,finish))
        _label(p,"ФИНИШ",580,finish-85,440,65,44,ink,Qt.AlignmentFlag.AlignCenter)
    for coin in j.get("coins",()):
        x,y=float(coin["x"]),float(coin["y"])
        if not -65 < y < 1070:
            continue
        pulse = 1+.09*math.sin(now*5+coin["id"])
        _ellipse(p,x,y,23*pulse,23*pulse,"#e6a94e")
        _ellipse(p,x,y-2,19*pulse,19*pulse,gold)
        p.setPen(QPen(QColor("#fff1b5"),3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(x,y-2),12*pulse,12*pulse)
        _ellipse(p,x-6,y-8,4,2,"#fff7cf")
    for poly in j.get("stickers",()):
        path = QPainterPath()
        for i,pt in enumerate(poly):
            if i == 0: path.moveTo(QPointF(*pt))
            else: path.lineTo(QPointF(*pt))
        path.closeSubpath()
        p.setBrush(QColor("#546e83" if theme=="cloud" else "#715b68"))
        p.setPen(QPen(QColor("#ffffff"),3))
        p.drawPath(path)
    _hero(p,j.get("hero",[800,700,30,0,0]),now,float(j.get("bounce_fx",0)),theme,snapshot.get("phase"))
    if float(j.get("coin_fx",0))>0:
        fx=float(j["coin_fx"])
        x,y=j["coin_fx_pos"]
        _label(p,"+1",x-55,y-90-(1-fx)*30,110,60,34,gold,Qt.AlignmentFlag.AlignCenter)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#ffffff" if theme!="neon" else "#1e254c"))
    p.drawRoundedRect(QRectF(50,45,340,100),26,26)
    _label(p,"МОНЕТЫ",75,54,290,32,16,ink)
    _label(p,f'{snapshot.get("score",0)} / {j.get("total_coins",0)}',75,82,290,56,34,ink)
    p.setBrush(QColor("#ffffff" if theme!="neon" else "#1e254c"))
    p.drawRoundedRect(QRectF(1170,50,365,90),23,23)
    _label(p,"ВЫСОТА",1190,54,310,30,16,ink)
    p.setBrush(QColor("#d8e6e8" if theme!="neon" else "#3b3862"))
    p.drawRoundedRect(QRectF(1190,98,320,13),6,6)
    p.setBrush(QColor(accent))
    p.drawRoundedRect(QRectF(1190,98,320*float(j.get("progress",0)),13),6,6)
    phase = snapshot.get("phase")
    if phase in ("won","lost"):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#15243c" if theme=="neon" else "#ffffff"))
        p.drawRoundedRect(QRectF(320,320,960,350),44,44)
        _label(p,"УРОВЕНЬ ПРОЙДЕН!" if phase=="won" else "ПОПРОБУЕМ ЕЩЁ?",
               355,355,890,100,53,ink,Qt.AlignmentFlag.AlignCenter)
        _label(p,f'Собрано монет: {snapshot.get("score",0)} / {j.get("total_coins",0)}',
               400,470,800,70,32,ink,Qt.AlignmentFlag.AlignCenter)
        _label(p,"Новый раунд начнётся автоматически" if snapshot.get("settings",{}).get("jump_auto_restart",True)
               else "Новый раунд запускается с пульта",400,558,800,45,23,ink,Qt.AlignmentFlag.AlignCenter)
    elif phase=="preview":
        _label(p,"SKYHOP / ПРЕДПРОСМОТР",490,65,620,55,28,ink,Qt.AlignmentFlag.AlignCenter)
    p.restore()
