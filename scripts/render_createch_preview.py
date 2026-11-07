"""Offscreen golden-frame preview for reviewing actual Qt projector visuals."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter
from interactive_surface.game_render import paint_game


def main():
    app=QApplication.instance() or QApplication([])
    canvas=QImage(1600,1000,QImage.Format.Format_ARGB32)
    canvas.fill(0)
    scene={
       "settings":{"theme":"createch","cycle_mode":"manual"},
       "phase":"playing",
       "demo":True,
       "balls":[
            [.50,.29,19,0,.27,5],
            [.42,.45,19,-.19,.10,73],
            [.30,.53,19,-.17,.55,218],
            [.51,.16,19,0,.01,285],
       ],
       "demo_stickers":[[[.431,.50],[.569,.465],[.57,.482],[.432,.517]]],
       "goal":[.25,.705,31],
       "score":3,"target":5,"hits_fx":.8,
    }
    painter=QPainter(canvas)
    try:
        paint_game(painter,scene,[[0,0],[1,0],[1,1],[0,1]],1600,1000,"black")
    finally:
        painter.end()
    out=Path("artifacts/createch-projection-preview.png")
    out.parent.mkdir(parents=True,exist_ok=True)
    if not canvas.save(str(out), "PNG"):
        raise RuntimeError("Unable to save rendered preview")
    print(f"Rendered {out} with real Qt projector renderer")


if __name__=="__main__":
    main()
