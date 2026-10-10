"""Isolate Qt in a subprocess so the FastAPI service is independent of GUI threads."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time


def discover() -> list[dict]:
    try:
        p = subprocess.run([sys.executable, "-m", "interactive_surface.projector_host", "--list"], capture_output=True, text=True, timeout=7)
        if p.returncode != 0:
            return []
        screens = json.loads(p.stdout.strip().splitlines()[-1])
        return screens if isinstance(screens, list) else []
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return []


def prefer_display(items: list[dict]) -> int | None:
    if not items:
        return None
    return next((d["id"] for d in items if not d["primary"]), items[0]["id"])


class ProjectorService:
    def __init__(self):
        self.proc = None
        self.lock = threading.RLock()
        self.screen_id = None
        self.mode = "calibrate"
        self.quad = [[.12,.13],[.88,.13],[.88,.87],[.12,.87]]
        self.virtual = False
        self.background = "black"
        self.error = ""

    def screens(self):
        return discover()

    def open(self, screen_id: int | str):
        with self.lock:
            if screen_id == "virtual":
                self.close()
                self.virtual = True
                self.screen_id = "virtual"
                self.error = ""
                return self.status()
            screens = self.screens()
            if not isinstance(screen_id, int) or screen_id not in [x["id"] for x in screens]:
                raise ValueError("Указанный дисплей недоступен")
            if self.proc and self.proc.poll() is None:
                self._send({"action":"screen","id":screen_id})
                self.screen_id=screen_id
                return self.status()
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-u", "-m", "interactive_surface.projector_host", "--screen", str(screen_id)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1,
                )
                responses = queue.Queue()
                threading.Thread(target=lambda: responses.put(proc.stdout.readline()), daemon=True).start()
                try:
                    response = json.loads(responses.get(timeout=7))
                except (queue.Empty, ValueError) as exc:
                    proc.terminate()
                    raise ValueError("Не удалось открыть проекционное окно. Проверьте поддержку Qt/дисплея") from exc
                if not response.get("ready"):
                    proc.terminate()
                    raise ValueError(response.get("error", "Ошибка проекционного окна"))
            except OSError as exc:
                raise ValueError(f"Не удалось запустить проектор: {exc}") from exc
            self.proc = proc
            self.screen_id = screen_id
            self.virtual = False
            self.error = ""
            self._send({"action":"quad","points":self.quad})
            self._send({"action":"mode","mode":self.mode})
            self._send({"action":"background","background":self.background})
            return self.status()

    def _send(self, payload: dict):
        if self.proc and self.proc.poll() is None and self.proc.stdin:
            try:
                self.proc.stdin.write(json.dumps(payload, ensure_ascii=False)+"\n")
                self.proc.stdin.flush()
            except (OSError, BrokenPipeError):
                self.error = "Проекционное окно отключилось"

    def set_mode(self, mode: str):
        if mode not in ("identify","calibrate","verify","ready","background"):
            raise ValueError("Неизвестный режим проекции")
        with self.lock:
            self.mode=mode
            self._send({"action":"mode","mode":mode})

    def set_background(self, background: str):
        if background not in ("black", "white"):
            raise ValueError("Некорректный цвет фона")
        with self.lock:
            self.background = background
            self._send({"action":"background","background":background})

    def set_quad(self, quad: list):
        with self.lock:
            self.quad=quad
            self._send({"action":"quad","points":quad})

    def close(self):
        with self.lock:
            self._send({"action":"quit"})
            if self.proc:
                try:
                    self.proc.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    self.proc.terminate()
            self.proc=None
            self.virtual=False
            self.screen_id=None

    def status(self):
        with self.lock:
            active=self.virtual or (self.proc is not None and self.proc.poll() is None)
            return {"active":active, "screen":self.screen_id if active else None, "virtual":self.virtual, "mode":self.mode, "quad":self.quad, "background":self.background, "error":self.error}
