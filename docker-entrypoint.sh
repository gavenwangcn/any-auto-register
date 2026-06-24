#!/bin/bash
set -e

VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
XVFB_DISPLAY="${XVFB_DISPLAY:-:99}"

# 启动虚拟显示
Xvfb "${XVFB_DISPLAY}" -screen 0 1280x800x24 -nolisten tcp &
export DISPLAY="${XVFB_DISPLAY}"

# 等待 Xvfb 就绪（最多 10s）
for _ in $(seq 1 20); do
    if xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done
if ! xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
    echo "[entrypoint] 警告: Xvfb ${DISPLAY} 未就绪，headed 浏览器/noVNC 可能不可用"
fi

# x11vnc 固定 rfbport=5900，避免 display :99 时默认落到 5999 与 websockify 不一致
if [ -n "$VNC_PASSWORD" ]; then
    x11vnc -storepasswd "$VNC_PASSWORD" /tmp/vncpass
    x11vnc -display "${DISPLAY}" -rfbauth /tmp/vncpass -forever -shared -rfbport "${VNC_PORT}" -localhost no &
else
    x11vnc -display "${DISPLAY}" -nopw -forever -shared -rfbport "${VNC_PORT}" -localhost no &
fi

# noVNC: 6080 -> VNC 5900（-localhost no 表示允许容器内 websockify 连接）
websockify --web=/usr/share/novnc "0.0.0.0:${NOVNC_PORT}" "127.0.0.1:${VNC_PORT}" &

echo "[entrypoint] noVNC http://0.0.0.0:${NOVNC_PORT}/vnc.html  ->  VNC 127.0.0.1:${VNC_PORT}  DISPLAY=${DISPLAY}"

# 启动 FastAPI 后端
exec uvicorn main:app --host 0.0.0.0 --port 8000
