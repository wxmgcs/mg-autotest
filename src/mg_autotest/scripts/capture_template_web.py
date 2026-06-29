"""
Web 版模板截图工具

在浏览器中打开画布，拖拽框选区域保存为模板。
零额外依赖，仅使用 Python 标准库 + 已安装的 opencv/numpy。

流程:
  1. 连接设备 → 截图
  2. 启动本地 HTTP 服务器 → 自动打开浏览器
  3. 在浏览器中用鼠标拖拽框出目标区域
  4. 点击保存 → 裁剪并写入 templates/
"""

import os
import json
import io
import base64
import webbrowser
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import cv2
import numpy as np

from mg_autotest.core.device import get_device
from mg_autotest.core.logger import get_logger

logger = get_logger(__name__)

TEMPLATE_DIR = "templates"
HOST = "127.0.0.1"
PORT = 18989

# 全局变量
_current_screenshot = None  # numpy array (BGR)
_current_device = None      # uiautomator2 Device 对象
_current_size = None        # (width, height)


# ─────────────── HTML 页面 ───────────────

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>模板截图工具</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #1a1a2e;
    color: #eee;
    font-family: -apple-system, "Microsoft YaHei", sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    min-height: 100vh;
    padding: 16px;
  }
  h1 { font-size: 20px; margin: 10px 0 6px; color: #00d4aa; }

  #toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin: 8px 0;
  }
  #toolbar button, #toolbar input {
    background: #16213e;
    color: #eee;
    border: 1px solid #0f3460;
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    transition: 0.2s;
  }
  #toolbar button:hover { background: #0f3460; border-color: #00d4aa; }
  #toolbar button:disabled { opacity: 0.4; cursor: not-allowed; }
  #toolbar input { background: #0d1b2a; outline: none; width: 180px; }
  #toolbar input:focus { border-color: #00d4aa; }
  #toolbar .btn-primary { background: #00d4aa; color: #1a1a2e; font-weight: bold; border-color: #00d4aa; }
  #toolbar .btn-primary:hover { background: #00f5c8; }
  #toolbar .btn-danger { background: #e94560; color: #fff; border-color: #e94560; }
  #toolbar .btn-danger:hover { background: #ff6b81; }
  #toolbar label { font-size: 13px; color: #aaa; }

  #status-bar {
    display: flex;
    gap: 16px;
    font-size: 13px;
    color: #888;
    margin: 4px 0 8px;
    flex-wrap: wrap;
    justify-content: center;
  }
  #status-bar .highlight { color: #00d4aa; font-weight: bold; }

  .canvas-wrapper {
    position: relative;
    border: 2px solid #0f3460;
    border-radius: 8px;
    overflow: hidden;
    max-width: 100%;
    background: #0d1b2a;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  }
  .canvas-wrapper canvas {
    display: block;
    max-width: 100%;
    height: auto;
    cursor: crosshair;
  }

  #preview-area {
    display: none;
    margin-top: 12px;
    padding: 12px;
    background: #16213e;
    border-radius: 8px;
    border: 1px solid #0f3460;
    text-align: center;
  }
  #preview-area.visible { display: block; }
  #preview-area img {
    max-width: 300px;
    max-height: 200px;
    border-radius: 4px;
    border: 1px solid #333;
  }
  #preview-area .info {
    font-size: 13px;
    color: #aaa;
    margin-top: 6px;
  }

  #toast {
    position: fixed;
    bottom: 30px;
    left: 50%;
    transform: translateX(-50%);
    background: #00d4aa;
    color: #1a1a2e;
    padding: 10px 24px;
    border-radius: 8px;
    font-weight: bold;
    opacity: 0;
    transition: opacity 0.3s;
    pointer-events: none;
  }
  #toast.show { opacity: 1; }
  #toast.error { background: #e94560; color: #fff; }

  /* --- template test --- */
  #test-area {
    margin-top: 10px;
    padding: 10px 14px;
    background: #16213e;
    border-radius: 8px;
    border: 1px solid #0f3460;
    width: 100%;
    max-width: 900px;
  }
  #test-area .row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  #test-area select {
    background: #0d1b2a;
    color: #eee;
    border: 1px solid #0f3460;
    padding: 7px 10px;
    border-radius: 5px;
    font-size: 13px;
    min-width: 160px;
    outline: none;
  }
  #test-area select:focus { border-color: #00d4aa; }
  #test-area .conf-label { font-size: 12px; color: #888; }
  #test-area .match-found { color: #00d4aa; font-weight: bold; font-size: 13px; }
  #test-area .match-low { color: #e9a545; font-weight: bold; font-size: 13px; }
  #test-area .match-none { color: #e94560; font-size: 13px; }
  #test-area .btn-test {
    background: #e9a545; color: #1a1a2e; font-weight: bold;
    border-color: #e9a545;
  }
  #test-area .btn-test:hover { background: #f5b855; }
  #test-area .btn-test:disabled { opacity: 0.4; cursor: not-allowed; }
  #test-area .btn-click {
    background: #00d4aa; color: #1a1a2e; font-weight: bold;
    border-color: #00d4aa;
  }
  #test-area .btn-click:hover { background: #00f5c8; }
  #test-area .btn-click:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
</head>
<body>

<h1>📷 模板截图工具</h1>

<div id="toolbar">
  <button id="btn-refresh" onclick="refreshScreenshot()">🔄 刷新截图</button>
  <button id="btn-save" class="btn-primary" onclick="saveTemplate()" disabled>💾 保存模板</button>
  <button id="btn-clear" class="btn-danger" onclick="clearSelection()">✕ 清除选区</button>
  <input type="text" id="template-name" placeholder="模板名称 (自动生成)" />
  <label><input type="checkbox" id="chk-auto-name" checked /> 自动命名</label>
</div>

<div id="status-bar">
  <span id="device-info">⏳ 正在加载...</span>
  <span id="coord-info">鼠标移入画布查看坐标</span>
  <span id="size-info"></span>
</div>

<div class="canvas-wrapper">
  <canvas id="mainCanvas"></canvas>
</div>

<div id="preview-area">
  <img id="preview-img" alt="裁剪预览" />
  <div class="info" id="preview-info"></div>
</div>

<div id="test-area">
  <div class="row">
    <select id="template-select">
      <option value="">-- 选择模板 --</option>
    </select>
    <button id="btn-refresh-tpl" onclick="loadTemplateList()">🔄 刷新列表</button>
    <span class="conf-label">阈值:</span>
    <input type="number" id="match-threshold" value="0.8" min="0.1" max="1.0" step="0.05" style="width:60px;background:#0d1b2a;color:#eee;border:1px solid #0f3460;padding:5px 8px;border-radius:4px;outline:none" />
    <button id="btn-test-match" class="btn-test" onclick="testMatch()" disabled>🎯 测试匹配</button>
    <span id="match-result"></span>
    <button id="btn-click-match" class="btn-click" onclick="clickMatch()" disabled>👆 点击</button>
  </div>
</div>

<div id="toast"></div>

<script>
const canvas = document.getElementById('mainCanvas');
const ctx = canvas.getContext('2d');
let imageDataUrl = null;

// 拖拽状态
let isDragging = false;
let startX = 0, startY = 0;
let endX = 0, endY = 0;
let hasSelection = false;

// 缩放比例 (canvas 实际像素 / 图片原始像素)
let scaleRatio = 1;

// 模板匹配结果
let matchResult = null; // { x, y, w, h, confidence }

// ── 加载截图 ──
async function refreshScreenshot() {
  try {
    document.getElementById('device-info').textContent = '正在截图...';

    // 1. 通知后端重新截图
    const refreshResp = await fetch('/api/refresh');
    const refreshData = await refreshResp.json();
    if (!refreshData.success) { toast('刷新失败: ' + refreshData.error, true); return; }

    // 2. 获取新的截图数据
    const resp = await fetch('/api/screenshot');
    const data = await resp.json();
    if (!data.success) { toast(data.error, true); return; }

    // 显示设备信息
    document.getElementById('device-info').textContent =
      `${data.device || '设备'}  ${data.width}x${data.height}`;

    // 加载图片到 canvas
    imageDataUrl = 'data:image/png;base64,' + data.image;
    const img = new Image();
    img.onload = () => {
      updateCanvasSize(img.width, img.height);
      ctx.drawImage(img, 0, 0);
      clearSelection();
      clearMatchResult();
      toast('截图已刷新');
    };
    img.src = imageDataUrl;
  } catch (e) {
    toast('截图失败: ' + e.message, true);
  }
}

function updateCanvasSize(naturalW, naturalH) {
  // 自适应窗口宽度
  const maxW = window.innerWidth - 64;
  const maxH = window.innerHeight - 280;
  const scale = Math.min(1, maxW / naturalW, maxH / naturalH);
  canvas.width = Math.round(naturalW * scale);
  canvas.height = Math.round(naturalH * scale);
  scaleRatio = scale;
}

// ── 鼠标事件 ──
function getCanvasPos(e) {
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) * (canvas.width / rect.width);
  const y = (e.clientY - rect.top) * (canvas.height / rect.height);
  return { x: Math.max(0, Math.min(canvas.width, x)),
           y: Math.max(0, Math.min(canvas.height, y)) };
}

canvas.addEventListener('mousedown', (e) => {
  const pos = getCanvasPos(e);
  isDragging = true;
  startX = pos.x; startY = pos.y;
  endX = pos.x; endY = pos.y;
  hasSelection = false;
  document.getElementById('btn-save').disabled = true;
});

canvas.addEventListener('mousemove', (e) => {
  const pos = getCanvasPos(e);
  if (isDragging) {
    endX = pos.x; endY = pos.y;
    drawCanvas();
    drawSelection();
    updateCoordInfo();
  } else {
    // 鼠标悬浮坐标
    const realX = Math.round(pos.x / scaleRatio);
    const realY = Math.round(pos.y / scaleRatio);
    document.getElementById('coord-info').textContent =
      `鼠标: (${realX}, ${realY})`;
  }
});

canvas.addEventListener('mouseup', () => {
  if (!isDragging) return;
  isDragging = false;
  hasSelection = true;

  const w = Math.abs(endX - startX);
  const h = Math.abs(endY - startY);
  if (w < 3 || h < 3) {
    clearSelection();
    toast('选区太小，请重新框选', true);
    return;
  }

  document.getElementById('btn-save').disabled = false;
  updateCoordInfo();
  showPreview();
});

canvas.addEventListener('mouseleave', () => {
  if (isDragging) {
    isDragging = false;
    if (hasSelection) drawSelection();
  }
});

// ── 触摸事件 ──
canvas.addEventListener('touchstart', (e) => {
  e.preventDefault();
  const touch = e.touches[0];
  const pos = getCanvasPos(touch);
  isDragging = true;
  startX = pos.x; startY = pos.y;
  endX = pos.x; endY = pos.y;
  hasSelection = false;
  document.getElementById('btn-save').disabled = true;
}, { passive: false });

canvas.addEventListener('touchmove', (e) => {
  e.preventDefault();
  if (!isDragging) return;
  const touch = e.touches[0];
  const pos = getCanvasPos(touch);
  endX = pos.x; endY = pos.y;
  drawCanvas();
  drawSelection();
  updateCoordInfo();
}, { passive: false });

canvas.addEventListener('touchend', (e) => {
  e.preventDefault();
  if (!isDragging) return;
  isDragging = false;
  hasSelection = true;
  const w = Math.abs(endX - startX);
  const h = Math.abs(endY - startY);
  if (w < 3 || h < 3) { clearSelection(); toast('选区太小', true); return; }
  document.getElementById('btn-save').disabled = false;
  updateCoordInfo();
  showPreview();
}, { passive: false });

// ── 绘制 ──
function drawCanvas() {
  if (!imageDataUrl) return;
  const img = new Image();
  img.src = imageDataUrl;
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
}

function drawSelection() {
  const x = Math.min(startX, endX);
  const y = Math.min(startY, endY);
  const w = Math.abs(endX - startX);
  const h = Math.abs(endY - startY);

  // 半透明遮罩
  ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // 擦除选中区域
  ctx.clearRect(x, y, w, h);

  // 把原图画回来
  if (imageDataUrl) {
    const img = new Image();
    img.src = imageDataUrl;
    ctx.drawImage(img, x, y, w, h, x, y, w, h);
  }

  // 边框
  ctx.strokeStyle = '#00ff88';
  ctx.lineWidth = 2;
  ctx.setLineDash([5, 4]);
  ctx.strokeRect(x, y, w, h);
  ctx.setLineDash([]);

  // 角标
  const cornerLen = 10;
  ctx.strokeStyle = '#00ff88';
  ctx.lineWidth = 2;
  ctx.beginPath();
  // 左上
  ctx.moveTo(x, y + cornerLen); ctx.lineTo(x, y); ctx.lineTo(x + cornerLen, y);
  // 右上
  ctx.moveTo(x + w - cornerLen, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + cornerLen);
  // 右下
  ctx.moveTo(x + w, y + h - cornerLen); ctx.lineTo(x + w, y + h); ctx.lineTo(x + w - cornerLen, y + h);
  // 左下
  ctx.moveTo(x + cornerLen, y + h); ctx.lineTo(x, y + h); ctx.lineTo(x, y + h - cornerLen);
  ctx.stroke();

  // 尺寸标签
  const realW = Math.round(w / scaleRatio);
  const realH = Math.round(h / scaleRatio);
  ctx.fillStyle = '#00ff88';
  ctx.font = '13px sans-serif';
  ctx.fillText(`${realW} × ${realH}`, x + 6, y - 8);
}

function updateCoordInfo() {
  const x1 = Math.round(Math.min(startX, endX) / scaleRatio);
  const y1 = Math.round(Math.min(startY, endY) / scaleRatio);
  const x2 = Math.round(Math.max(startX, endX) / scaleRatio);
  const y2 = Math.round(Math.max(startY, endY) / scaleRatio);
  const w = x2 - x1, h = y2 - y1;
  document.getElementById('coord-info').textContent =
    `选区: (${x1}, ${y1}) → (${x2}, ${y2})  [${w} × ${h}]`;
  document.getElementById('size-info').textContent =
    `📐 ${w} × ${h}`;

  // 自动生成模板名称
  if (document.getElementById('chk-auto-name').checked) {
    const now = new Date();
    const ts = now.getFullYear() +
      String(now.getMonth()+1).padStart(2,'0') +
      String(now.getDate()).padStart(2,'0') + '_' +
      String(now.getHours()).padStart(2,'0') +
      String(now.getMinutes()).padStart(2,'0') +
      String(now.getSeconds()).padStart(2,'0');
    const nameInput = document.getElementById('template-name');
    if (!nameInput.value || nameInput.dataset.auto === '1') {
      nameInput.value = `template_${ts}`;
      nameInput.dataset.auto = '1';
    }
  }
}

function clearSelection() {
  hasSelection = false;
  isDragging = false;
  document.getElementById('btn-save').disabled = true;
  document.getElementById('coord-info').textContent = '鼠标移入画布查看坐标';
  document.getElementById('size-info').textContent = '';
  document.getElementById('preview-area').classList.remove('visible');
  drawCanvas();
  if (matchResult) drawMatchResult(); // 保留匹配结果
}

function showPreview() {
  const x = Math.min(startX, endX);
  const y = Math.min(startY, endY);
  const w = Math.abs(endX - startX);
  const h = Math.abs(endY - endY);

  // 从 canvas 截取选区
  const imgData = ctx.getImageData(x, y, w, h);
  const tmpCanvas = document.createElement('canvas');
  tmpCanvas.width = w;
  tmpCanvas.height = h;
  const tmpCtx = tmpCanvas.getContext('2d');
  tmpCtx.putImageData(imgData, 0, 0);

  document.getElementById('preview-img').src = tmpCanvas.toDataURL();
  document.getElementById('preview-info').textContent =
    `裁剪区域: ${Math.round(w/scaleRatio)} × ${Math.round(h/scaleRatio)} 像素`;
  document.getElementById('preview-area').classList.add('visible');
}

// ── 保存 ──
async function saveTemplate() {
  if (!hasSelection) return;

  const nameInput = document.getElementById('template-name');
  let name = nameInput.value.trim();
  if (!name) {
    const now = new Date();
    name = `template_${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}_${String(now.getHours()).padStart(2,'0')}${String(now.getMinutes()).padStart(2,'0')}${String(now.getSeconds()).padStart(2,'0')}`;
    nameInput.value = name;
  }

  const x1 = Math.round(Math.min(startX, endX) / scaleRatio);
  const y1 = Math.round(Math.min(startY, endY) / scaleRatio);
  const x2 = Math.round(Math.max(startX, endX) / scaleRatio);
  const y2 = Math.round(Math.max(startY, endY) / scaleRatio);

  document.getElementById('btn-save').disabled = true;
  document.getElementById('btn-save').textContent = '⏳ 保存中...';

  try {
    const resp = await fetch('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, x1, y1, x2, y2 }),
    });
    const data = await resp.json();
    if (data.success) {
      toast(`✅ 模板已保存: ${data.path}`);
      nameInput.dataset.auto = '1';
      // refresh template list & auto test
      var savedName = name;
      if (!savedName.endsWith('.png')) savedName += '.png';
      loadTemplateList(savedName);
    } else {
      toast('❌ 保存失败: ' + data.error, true);
    }
  } catch (e) {
    toast('❌ 请求失败: ' + e.message, true);
  }

  document.getElementById('btn-save').textContent = '💾 保存模板';
  document.getElementById('btn-save').disabled = false;
}

// ── toast ──
function toast(msg, isError) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show' + (isError ? ' error' : '');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('show'), 2500);
}

// ── 模板匹配测试 ──

function clearMatchResult() {
  matchResult = null;
  document.getElementById('match-result').textContent = '';
  document.getElementById('btn-click-match').disabled = true;
  // 测试匹配按钮保持启用（只要下拉框有模板可选）
  var sel = document.getElementById('template-select');
  document.getElementById('btn-test-match').disabled = !sel || sel.value === '';
  drawCanvas();
  if (hasSelection) drawSelection();
}

function drawMatchResult() {
  if (!matchResult) return;
  var mx = matchResult.x * scaleRatio;
  var my = matchResult.y * scaleRatio;
  var mw = matchResult.w * scaleRatio;
  var mh = matchResult.h * scaleRatio;

  // 橙色边框
  ctx.strokeStyle = '#ff8800';
  ctx.lineWidth = 3;
  ctx.strokeRect(mx, my, mw, mh);

  // 十字准心
  ctx.strokeStyle = '#ff8800';
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(mx + mw/2, my); ctx.lineTo(mx + mw/2, my + mh);
  ctx.moveTo(mx, my + mh/2); ctx.lineTo(mx + mw, my + mh/2);
  ctx.stroke();
  ctx.setLineDash([]);

  // 置信度标签
  var label = 'Match: ' + (matchResult.confidence * 100).toFixed(1) + '%';
  ctx.fillStyle = '#ff8800';
  ctx.font = 'bold 14px sans-serif';
  var tw = ctx.measureText(label).width;
  ctx.fillStyle = 'rgba(0,0,0,0.7)';
  ctx.fillRect(mx, my - 22, tw + 12, 22);
  ctx.fillStyle = '#ff8800';
  ctx.fillText(label, mx + 6, my - 6);
}

async function loadTemplateList(selectName) {
  try {
    var resp = await fetch('/api/templates');
    var data = await resp.json();
    var sel = document.getElementById('template-select');
    sel.innerHTML = '<option value="">-- 选择模板 --</option>';
    if (data.templates && data.templates.length > 0) {
      data.templates.forEach(function(t) {
        var opt = document.createElement('option');
        opt.value = t;
        opt.textContent = t;
        sel.appendChild(opt);
      });

      // 指定选中或默认第一个
      var targetName = selectName || data.templates[0];
      if (data.templates.indexOf(targetName) >= 0) {
        sel.value = targetName;
      } else {
        sel.value = data.templates[0];
      }
      document.getElementById('btn-test-match').disabled = false;

      // 指定了模板名 → 自动测试匹配
      if (selectName) {
        testMatch();
      }
    } else {
      document.getElementById('btn-test-match').disabled = true;
    }
  } catch (e) {
    toast('加载模板列表失败', true);
  }
}

async function testMatch() {
  var sel = document.getElementById('template-select');
  var templateName = sel.value;
  if (!templateName) { toast('请先选择一个模板', true); return; }

  var threshold = parseFloat(document.getElementById('match-threshold').value) || 0.8;
  document.getElementById('btn-test-match').disabled = true;
  document.getElementById('match-result').textContent = '匹配中...';
  document.getElementById('match-result').className = '';

  try {
    var resp = await fetch('/api/test_match', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template: templateName, threshold: threshold }),
    });
    var data = await resp.json();
    if (!data.success) { toast('匹配失败: ' + data.error, true); return; }

    var resultEl = document.getElementById('match-result');
    if (data.found) {
      matchResult = { x: data.x, y: data.y, w: data.width, h: data.height, confidence: data.confidence };
      document.getElementById('btn-click-match').disabled = false;
      drawCanvas();
      if (hasSelection) drawSelection();
      drawMatchResult();
      var confPct = (data.confidence * 100).toFixed(1);
      if (data.confidence >= threshold) {
        resultEl.textContent = 'Found: (' + data.x + ',' + data.y + ')  ' + confPct + '%';
        resultEl.className = 'match-found';
        toast('匹配成功: ' + confPct + '%');
      } else {
        resultEl.textContent = 'Low match: ' + confPct + '% (阈值 ' + (threshold*100).toFixed(0) + '%)';
        resultEl.className = 'match-low';
        toast('匹配度偏低: ' + confPct + '%', true);
      }
    } else {
      matchResult = null;
      document.getElementById('btn-click-match').disabled = true;
      resultEl.textContent = '未找到匹配 (最佳: ' + (data.confidence * 100).toFixed(1) + '%)';
      resultEl.className = 'match-none';
      toast('未找到匹配', true);
    }
  } catch (e) {
    toast('匹配请求失败: ' + e.message, true);
  }

  document.getElementById('btn-test-match').disabled = false;
}

// ── 点击匹配区域 ──
async function clickMatch() {
  if (!matchResult) { toast('请先测试匹配', true); return; }

  var cx = Math.round(matchResult.x + matchResult.w / 2);
  var cy = Math.round(matchResult.y + matchResult.h / 2);

  document.getElementById('btn-click-match').disabled = true;
  document.getElementById('btn-click-match').textContent = '点击中...';

  try {
    var resp = await fetch('/api/click', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ x: cx, y: cy }),
    });
    var data = await resp.json();
    if (data.success) {
      toast('已点击: (' + cx + ', ' + cy + ')');
      setTimeout(refreshScreenshot, 500);
    } else {
      toast('点击失败: ' + data.error, true);
    }
  } catch (e) {
    toast('点击请求失败: ' + e.message, true);
  }

  document.getElementById('btn-click-match').textContent = '👆 点击';
  document.getElementById('btn-click-match').disabled = false;
}

// ── 键盘快捷键 ──
document.addEventListener('keydown', (e) => {
  // 输入框中打字时不触发全局快捷键
  var tag = e.target.tagName.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); saveTemplate(); }
  if (e.key === 'Escape') { clearSelection(); clearMatchResult(); }
  if (e.key === 'r' || e.key === 'R') refreshScreenshot();
  if (e.key === 't' || e.key === 'T') testMatch();
  if (e.key === 'c' || e.key === 'C') { clickMatch(); }
});

// ── 自动加载 ──
window.addEventListener('load', function() {
  refreshScreenshot();
  loadTemplateList();
});
</script>
</body>
</html>
"""


# ─────────────── HTTP 请求处理 ───────────────

class RequestHandler(BaseHTTPRequestHandler):
    """处理浏览器的 API 请求"""

    def log_message(self, format, *args):
        """静默日志，避免控制台刷屏"""
        pass

    def _send_json(self, data: dict, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_html(self, html: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_png(self, img_bytes: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(img_bytes)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send_html(HTML_PAGE)

        elif path == "/api/screenshot":
            self._handle_screenshot()

        elif path == "/api/refresh":
            self._handle_refresh()

        elif path == "/api/templates":
            self._handle_templates()

        else:
            self._send_json({"success": False, "error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/save":
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len))
            self._handle_save(body)

        elif path == "/api/test_match":
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len))
            self._handle_test_match(body)

        elif path == "/api/click":
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len))
            self._handle_click(body)

        else:
            self._send_json({"success": False, "error": "Not found"}, 404)

    # ── 截图 ──

    def _handle_screenshot(self):
        global _current_screenshot, _current_size

        try:
            screenshot_cv = _current_screenshot
            if screenshot_cv is None:
                self._send_json({"success": False, "error": "截图未就绪"})
                return

            h, w = screenshot_cv.shape[:2]
            # OpenCV BGR → PNG (OpenCV 的 imencode 期望 BGR)
            _, buf = cv2.imencode(".png", screenshot_cv)
            img_b64 = base64.b64encode(buf).decode("utf-8")

            self._send_json({
                "success": True,
                "image": img_b64,
                "width": w,
                "height": h,
                "device": _current_device_name or "Android",
            })
        except Exception as e:
            logger.error(f"截图 API 错误: {e}")
            self._send_json({"success": False, "error": str(e)})

    # ── 重新截图 ──

    def _handle_refresh(self):
        global _current_screenshot, _current_device, _current_device_name

        try:
            if _current_device is None:
                self._send_json({"success": False, "error": "设备未连接"})
                return

            # 重新截取屏幕
            _current_screenshot = _current_device.screenshot(format="opencv")
            if _current_screenshot is None:
                raise RuntimeError("截图返回空")

            h, w = _current_screenshot.shape[:2]
            logger.info(f"截图已刷新: {w}x{h}")
            self._send_json({"success": True, "width": w, "height": h})
        except Exception as e:
            logger.error(f"刷新截图失败: {e}")
            self._send_json({"success": False, "error": str(e)})

    # ── 模板列表 ──

    def _handle_templates(self):
        try:
            os.makedirs(TEMPLATE_DIR, exist_ok=True)
            files = sorted([
                f for f in os.listdir(TEMPLATE_DIR)
                if f.lower().endswith(".png")
            ])
            self._send_json({"success": True, "templates": files})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    # ── 模板匹配测试 ──

    def _handle_test_match(self, body):
        global _current_screenshot

        template_name = body.get("template", "")
        threshold = float(body.get("threshold", 0.8))

        if not template_name:
            self._send_json({"success": False, "error": "模板名称为空"})
            return

        if _current_screenshot is None:
            self._send_json({"success": False, "error": "截图数据丢失"})
            return

        template_path = os.path.join(TEMPLATE_DIR, template_name)
        if not os.path.isfile(template_path):
            # 尝试不加目录前缀
            alt = os.path.join(TEMPLATE_DIR, template_name)
            if os.path.isfile(alt):
                template_path = alt
            else:
                self._send_json({"success": False, "error": f"模板文件不存在: {template_name}"})
                return

        template = cv2.imread(template_path)
        if template is None:
            self._send_json({"success": False, "error": "无法读取模板图片"})
            return

        th, tw = template.shape[:2]
        if th > _current_screenshot.shape[0] or tw > _current_screenshot.shape[1]:
            self._send_json({"success": False, "error": "模板大于截图，无法匹配"})
            return

        try:
            result = cv2.matchTemplate(_current_screenshot, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            self._send_json({
                "success": True,
                "found": bool(max_val >= threshold),
                "x": int(max_loc[0]),
                "y": int(max_loc[1]),
                "width": int(tw),
                "height": int(th),
                "confidence": round(float(max_val), 4),
            })
        except Exception as e:
            logger.error(f"模板匹配失败: {e}")
            self._send_json({"success": False, "error": str(e)})

    # ── 点击 ──

    def _handle_click(self, body):
        global _current_device

        x = int(body.get("x", 0))
        y = int(body.get("y", 0))

        if _current_device is None:
            self._send_json({"success": False, "error": "设备未连接"})
            return

        try:
            _current_device.click(x, y)
            logger.info(f"点击坐标: ({x}, {y})")
            self._send_json({"success": True})
        except Exception as e:
            logger.error(f"点击失败: {e}")
            self._send_json({"success": False, "error": str(e)})

    # ── 保存模板 ──

    def _handle_save(self, body):
        global _current_screenshot

        name = body.get("name", "").strip()
        x1, y1 = int(body["x1"]), int(body["y1"])
        x2, y2 = int(body["x2"]), int(body["y2"])

        if not name:
            self._send_json({"success": False, "error": "模板名称为空"})
            return

        if _current_screenshot is None:
            self._send_json({"success": False, "error": "截图数据丢失，请刷新"})
            return

        h, w = _current_screenshot.shape[:2]
        x1 = max(0, min(x1, w - 2))
        y1 = max(0, min(y1, h - 2))
        x2 = max(x1 + 1, min(x2, w))
        y2 = max(y1 + 1, min(y2, h))

        if (x2 - x1) < 3 or (y2 - y1) < 3:
            self._send_json({"success": False, "error": "选区太小 (至少 3x3)"})
            return

        # 裁剪
        cropped = _current_screenshot[y1:y2, x1:x2].copy()

        # 确保目录存在
        os.makedirs(TEMPLATE_DIR, exist_ok=True)

        if not name.endswith(".png"):
            name += ".png"

        filepath = os.path.join(TEMPLATE_DIR, name)

        # 检查重名
        if os.path.exists(filepath):
            self._send_json({
                "success": False,
                "error": f"文件已存在: {name}",
                "path": filepath,
                "exists": True,
            })
            return

        cv2.imwrite(filepath, cropped)
        logger.info(f"模板已保存: {filepath} ({x2-x1}x{y2-y1})")
        self._send_json({
            "success": True,
            "path": os.path.abspath(filepath),
            "size": f"{x2-x1}x{y2-y1}",
        })


# ─────────────── 启动服务 ───────────────

_current_device_name = None


def start_server():
    """启动 HTTP 服务器"""
    server = HTTPServer((HOST, PORT), RequestHandler)
    logger.info(f"Web 服务已启动: http://{HOST}:{PORT}")
    webbrowser.open(f"http://{HOST}:{PORT}")
    server.serve_forever()


def main():
    global _current_screenshot, _current_device, _current_device_name

    print("=" * 50)
    print("  Web 版模板截图工具")
    print("=" * 50)

    # 1. 连接设备并截图
    print("\n[Device] 正在连接设备...")
    try:
        d = get_device()
        width, height = d.window_size()
        _current_device = d
        _current_device_name = d.info.get("productName", "Android")
        print(f"   [OK] 已连接: {_current_device_name} ({width}x{height})")
    except Exception as e:
        print(f"   [Fail] 连接失败: {e}")
        input("\n按 Enter 退出...")
        return

    print("[Screenshot] 正在截图...")
    try:
        _current_screenshot = d.screenshot(format="opencv")
        if _current_screenshot is None:
            raise RuntimeError("截图返回空")
        h, w = _current_screenshot.shape[:2]
        print(f"   [OK] 截图完成: {w}x{h}")
    except Exception as e:
        print(f"   [Fail] 截图失败: {e}")
        input("\n按 Enter 退出...")
        return

    # 2. 启动 Web 服务
    print(f"\n🌐 正在启动 Web 服务...")
    print(f"   http://{HOST}:{PORT}")
    print(f"\n使用说明:")
    print(f"   1. 浏览器自动打开，显示设备截图")
    print(f"   2. 鼠标拖拽框选目标区域")
    print(f"   3. 点击「保存模板」或 Ctrl+S")
    print(f"   4. 按 R 重新截图 | ESC 清除选区")
    print(f"\n按 Ctrl+C 退出服务\n")

    try:
        start_server()
    except KeyboardInterrupt:
        print("\n\n[Exit] 服务已停止")
    except Exception as e:
        logger.error(f"服务异常: {e}")


if __name__ == "__main__":
    main()
