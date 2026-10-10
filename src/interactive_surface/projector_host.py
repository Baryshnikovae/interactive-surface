"""Qt display process. The only component allowed to create OS projection windows.

Run `python -m interactive_surface.projector_host --list` for screen discovery.
Otherwise accepts JSON command lines on stdin. QWidget always runs on Qt main thread.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import queue

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QBrush, QLinearGradient
from PySide6.QtWidgets import QApplication, QWidget
from .game_render import paint_game


def screens(app: QApplication) -> list[dict]:
    primary = app.primaryScreen()
    results = []
    for idx, screen in enumerate(app.screens()):
        g = screen.geometry()
        results.append({
            "id": idx, "name": screen.name() or f"Экран {idx + 1}",
            "resolution": [g.width(), g.height()], "position": [g.x(), g.y()],
            "primary": screen == primary, "dpr": screen.devicePixelRatio(),
        })
    return results


class ProjectionWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.mode = "calibrate"
        self.background = "black"
        self.quad = [[.12,.13],[.88,.13],[.88,.87],[.12,.87]]
        self.identity = 1
        self.game_frame = {}
        self.setWindowTitle("Interactive Surface — Проекция")
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def show_screen(self, screen):
        self.winId()
        self.windowHandle().setScreen(screen)
        self.setGeometry(screen.geometry())
        self.showFullScreen()
        self.raise_()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        if self.mode == "game":
            paint_game(painter, self.game_frame, self.quad, w, h, self.background)
            painter.end()
            return
        if self.mode == "background":
            painter.fillRect(self.rect(), QColor("#000000" if self.background == "black" else "#ffffff"))
            return
        if self.mode == "ready":
            background = QLinearGradient(0, 0, w, h)
            background.setColorAt(0, QColor("#09172c"))
            background.setColorAt(1, QColor("#243e5a"))
            painter.fillRect(self.rect(), QBrush(background))
            painter.setPen(QColor("#8ce6c7"))
            painter.setFont(QFont("Sans Serif", max(25, round(min(w, h) * .075)), QFont.Weight.Bold))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "ИГРА ГОТОВА")
            return
        painter.fillRect(self.rect(), QColor("#f5f5f2"))
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        if self.mode == "identify":
            painter.setPen(QColor("#172b4f"))
            painter.setFont(QFont("Sans Serif", max(45, round(min(w, h) * .19)), QFont.Weight.Bold))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self.identity))
            return
        p = [QPointF(x*w, y*h) for x,y in self.quad]
        painter.setPen(QPen(QColor("#40546a"), max(2, min(w,h)*.0025)))
        for i in range(4):
            painter.drawLine(p[i],p[(i+1)%4])
        if self.mode == "verify":
            from .geometry import homography, WALL, transform
            import numpy as np
            matrix = homography(WALL, np.array(self.quad))
            painter.setPen(QPen(QColor("#5d9bb5"), 1.6))
            for i in range(1,9):
                v=i/9
                for start,end in (((v,0),(v,1)),((0,v),(1,v))):
                    coords=transform(matrix, [start,end])
                    painter.drawLine(QPointF(coords[0,0]*w,coords[0,1]*h), QPointF(coords[1,0]*w,coords[1,1]*h))
            painter.setPen(QPen(QColor("#2e5966"), 3))
            center=transform(matrix, [[.5,.5]])[0]
            center=QPointF(center[0]*w,center[1]*h)
            painter.drawEllipse(center, 18, 18)
            painter.drawLine(center+QPointF(-25,0),center+QPointF(25,0))
            painter.drawLine(center+QPointF(0,-25),center+QPointF(0,25))
        for i,point in enumerate(p):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#e04252"))
            painter.drawEllipse(point, 14, 14)
            painter.setPen(QPen(QColor("#172b4f"), 2))
            painter.setFont(QFont("Sans Serif", max(15, round(min(w,h)*.024)), QFont.Weight.Bold))
            painter.drawText(point+QPointF(17,-18), str(i+1))
        painter.end()


def _read_stdin(queue_):
    for line in sys.stdin:
        try:
            payload = json.loads(line)
            if payload.get("action") == "game_frame":
                try:
                    queue_.put_nowait(payload)
                except queue.Full:
                    try: queue_.get_nowait()
                    except queue.Empty: pass
                    queue_.put_nowait(payload)
            else:
                queue_.put(payload)
        except ValueError:
            continue


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--screen", type=int, default=0)
    args=parser.parse_args()
    app=QApplication(sys.argv[:1])
    if args.list:
        print(json.dumps(screens(app), ensure_ascii=False), flush=True)
        return
    allscreens=app.screens()
    if not allscreens:
        print(json.dumps({"error":"Не обнаружены дисплеи"}), flush=True)
        return
    if args.screen < 0 or args.screen >= len(allscreens):
        print(json.dumps({"error":"Экран не найден"}), flush=True)
        return
    win=ProjectionWindow()
    win.identity=args.screen+1
    win.show_screen(allscreens[args.screen])
    print(json.dumps({"ready":True,"screen":args.screen}), flush=True)
    commands=queue.Queue(maxsize=256)
    threading.Thread(target=_read_stdin, args=(commands,), daemon=True).start()

    def poll():
        while not commands.empty():
            cmd=commands.get_nowait()
            typ=cmd.get("action")
            if typ=="quit":
                app.quit()
                return
            if typ=="game_frame":
                win.game_frame=cmd.get("frame") or {}
            if typ=="screen":
                idx=cmd.get("id")
                scr=app.screens()
                if isinstance(idx,int) and 0<=idx<len(scr):
                    win.identity=idx+1
                    win.show_screen(scr[idx])
            if typ=="mode" and cmd.get("mode") in ("calibrate","verify","ready","identify","background","game"):
                win.mode=cmd["mode"]
            if typ=="background" and cmd.get("background") in ("black", "white"):
                win.background=cmd["background"]
            if typ=="quad" and isinstance(cmd.get("points"),list) and len(cmd["points"])==4:
                win.quad=cmd["points"]
            win.update()

    timer=QTimer()
    timer.timeout.connect(poll)
    timer.start(8)
    animation=QTimer()
    animation.timeout.connect(lambda: win.update() if win.mode == "game" else None)
    animation.start(16)
    app.exec()


if __name__=="__main__":
    main()
