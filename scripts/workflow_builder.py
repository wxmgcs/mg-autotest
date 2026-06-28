"""
Web 版工作流编排工具

在浏览器中拖拽 templates/ 中的模板图片，编排自动化操作流程。
支持保存/加载工作流，导出可执行的 Python 脚本。

流程:
  1. 连接设备
  2. 浏览器打开编排界面
  3. 从左侧模板列表拖拽图片到工作流区域
  4. 配置每个步骤的阈值、超时、描述等参数
  5. 拖拽排序、增删步骤
  6. 保存工作流 / 导出 Python 脚本
"""

import sys
import os
import json
import base64
import webbrowser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from core.device import get_device
from core.logger import get_logger
from scripts.workflow_runner import execute_single_step

logger = get_logger(__name__)

TEMPLATE_DIR = "templates"
WORKFLOW_DIR = "workflows"
HOST = "127.0.0.1"
PORT = 18990


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>工作流编排工具</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #1a1a2e; color: #eee; font-family: -apple-system, "Microsoft YaHei", sans-serif; min-height: 100vh; }

  #header {
    display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
    padding: 12px 20px; background: #16213e; border-bottom: 1px solid #0f3460;
  }
  #header h1 { font-size: 18px; color: #00d4aa; white-space: nowrap; }
  #header .actions { display: flex; gap: 6px; margin-left: auto; flex-wrap: wrap; }
  #header .actions button {
    background: #0f3460; color: #eee; border: 1px solid #1a4a8a; padding: 6px 14px;
    border-radius: 5px; cursor: pointer; font-size: 13px; transition: 0.2s;
  }
  #header .actions button:hover { background: #1a4a8a; }
  #header .actions .btn-primary { background: #00d4aa; color: #1a1a2e; font-weight: bold; border-color: #00d4aa; }
  #header .actions .btn-primary:hover { background: #00f5c8; }
  #header .actions .btn-danger { background: #e94560; color: #fff; border-color: #e94560; }
  #header .actions .btn-danger:hover { background: #ff6b81; }
  .btn-add-step {
    background: #0f3460; color: #aaa; border: 1px solid #1a4a8a;
    padding: 3px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; transition: 0.2s;
  }
  .btn-add-step:hover { background: #1a4a8a; color: #eee; }
  .btn-batch {
    background: none; border: 1px solid #0f3460; border-radius: 3px; color: #888;
    cursor: pointer; font-size: 11px; padding: 1px 6px; transition: 0.15s;
  }
  .btn-batch:hover { border-color: #00d4aa; color: #eee; }
  #header .device-info { font-size: 12px; color: #888; margin-left: 12px; }

  #main { display: flex; height: calc(100vh - 56px); }
  #main .resize-handle {
    width: 4px; cursor: col-resize; background: #0f3460; flex-shrink: 0;
  }
  #main .resize-handle:hover { background: #00d4aa; }

  /* ── 左侧模板列表 ── */
  #tpl-panel {
    width: 220px; min-width: 160px; flex-shrink: 0;
    background: #0d1b2a; border-right: 1px solid #0f3460;
    display: flex; flex-direction: column; overflow: hidden;
  }
  #tpl-panel .panel-title {
    padding: 10px 12px; font-size: 13px; color: #00d4aa; font-weight: bold;
    border-bottom: 1px solid #0f3460; flex-shrink: 0;
    display: flex; align-items: center; gap: 6px;
  }
  #tpl-panel .panel-title span { color: #888; font-weight: normal; }
  #tpl-panel .panel-refresh {
    margin-left: auto; background: none; border: none; color: #555;
    cursor: pointer; font-size: 16px; line-height: 1; padding: 2px 6px; border-radius: 3px;
  }
  #tpl-panel .panel-refresh:hover { color: #00d4aa; background: rgba(0,212,170,0.1); }
  #tpl-search-wrap { padding: 6px 8px; flex-shrink: 0; }
  #tpl-search {
    width: 100%; background: #0d1b2a; border: 1px solid #0f3460; border-radius: 5px;
    padding: 6px 10px; color: #eee; font-size: 12px; outline: none;
  }
  #tpl-search:focus { border-color: #00d4aa; }
  #tpl-search::placeholder { color: #555; }
  #tpl-list {
    flex: 1; overflow-y: auto; padding: 8px;
    display: flex; flex-direction: column; gap: 6px;
  }
  .tpl-item {
    background: #16213e; border: 1px solid #0f3460; border-radius: 6px;
    padding: 6px; cursor: pointer; transition: 0.15s; user-select: none;
    display: flex; align-items: center; gap: 8px;
  }
  .tpl-item:hover { border-color: #00d4aa; background: #1a2a50; }
  .tpl-item:active { opacity: 0.7; }
  .tpl-item.dragging { opacity: 0.4; }
  .tpl-item img {
    width: 80px; height: 80px; object-fit: contain; border-radius: 4px;
    background: #0d1b2a; flex-shrink: 0;
  }
  .tpl-item .name { font-size: 12px; word-break: break-all; line-height: 1.3; }

  /* ── 右侧工作流区 ── */
  #workflow-panel {
    flex: 1; display: flex; flex-direction: column; overflow: hidden;
    background: #1a1a2e;
  }
  #workflow-panel .panel-title {
    padding: 10px 14px; font-size: 13px; color: #00d4aa; font-weight: bold;
    border-bottom: 1px solid #0f3460; flex-shrink: 0;
    display: flex; align-items: center; gap: 12px;
  }
  #workflow-panel .panel-title .count { color: #888; font-weight: normal; }

  #step-list {
    flex: 1; overflow-y: auto; padding: 12px;
    display: flex; flex-direction: column; gap: 8px;
  }
  #drop-hint {
    border: 2px dashed #0f3460; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    min-height: 120px; color: #555; font-size: 14px;
    transition: 0.2s; flex: 1;
  }
  #drop-hint.drag-over { border-color: #00d4aa; color: #00d4aa; background: rgba(0,212,170,0.05); }

  .step-card {
    background: #16213e; border: 1px solid #0f3460; border-radius: 8px;
    padding: 10px 14px; transition: 0.15s; position: relative;
  }
  .step-card.disabled { opacity: 0.5; border-color: #333; }
  .step-card .enable-cb { cursor: pointer; flex-shrink: 0; }
  .step-card.active-step { border-color: #ff8800; box-shadow: 0 0 10px rgba(255,136,0,0.3); }
  .step-card .step-header {
    display: flex; align-items: center; gap: 10px; margin-bottom: 6px;
  }
  .step-card .step-num {
    background: #0f3460; color: #00d4aa; width: 22px; height: 22px;
    border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: bold; flex-shrink: 0;
  }
  .step-card .run-btn {
    background: none; border: none; color: #00d4aa; cursor: pointer;
    font-size: 12px; padding: 0 4px; line-height: 1;
  }
  .step-card .run-btn:hover { color: #00ff88; }
  .step-card .move-btn {
    background: none; border: none; color: #555; cursor: pointer;
    font-size: 12px; padding: 0 3px; line-height: 1;
  }
  .step-card .move-btn:hover { color: #00d4aa; }
  .step-card .move-btn:disabled { color: #333; cursor: default; }
  .step-card .step-img {
    width: 72px; height: 72px; object-fit: contain; border-radius: 4px;
    background: #0d1b2a; border: 1px solid #0f3460; flex-shrink: 0;
  }
  .step-card .step-desc {
    flex: 1; background: #0d1b2a; border: 1px solid #0f3460; border-radius: 4px;
    padding: 4px 8px; color: #eee; font-size: 13px; outline: none; min-width: 60px;
  }
  .step-card .step-desc:focus { border-color: #00d4aa; }
  .step-card .step-body {
    display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-left: 36px;
  }
  .step-card .step-body label { font-size: 11px; color: #888; }
  .step-card .step-body input {
    width: 52px; background: #0d1b2a; border: 1px solid #0f3460; border-radius: 3px;
    padding: 3px 5px; color: #eee; font-size: 12px; outline: none;
  }
  .step-card .step-body input:focus { border-color: #00d4aa; }
  .step-card .step-body .offset-input { width: 44px; }
  .step-card .step-actions { margin-left: auto; display: flex; gap: 4px; }
  .step-card .step-actions button {
    background: none; border: none; color: #888; cursor: pointer; font-size: 14px; padding: 2px 4px;
  }
  .step-card .step-actions button:hover { color: #eee; }
  .step-card .step-actions .del-btn:hover { color: #e94560; }
  .step-card .tpl-name-tag {
    font-size: 11px; color: #888; margin-left: 36px; margin-bottom: 4px;
  }
  .step-card .type-select {
    background: #0d1b2a; color: #eee; border: 1px solid #0f3460;
    border-radius: 3px; padding: 2px 4px; font-size: 11px; outline: none;
    margin-left: 36px; margin-bottom: 6px; cursor: pointer;
  }
  .step-card .type-select:focus { border-color: #00d4aa; }
  .step-card .text-input-wide {
    flex: 1; min-width: 600px; background: #0d1b2a; border: 1px solid #0f3460;
    border-radius: 3px; padding: 3px 6px; color: #eee; font-size: 12px; outline: none;
  }
  .step-card .text-input-wide:focus { border-color: #00d4aa; }
  .step-body .type-badge {
    font-size: 10px; padding: 1px 6px; border-radius: 3px;
    background: #0f3460; color: #888;
  }
  .step-body .type-badge.click { background: #1a4a8a; color: #5af; }
  .step-body .type-badge.text { background: #3a2a1a; color: #fa5; }
  .step-body .type-badge.long_click { background: #3a1a2a; color: #f5a; }
  .step-body .type-badge.wait { background: #1a2a3a; color: #5af; }
  .step-body .type-badge.back { background: #3a2a1a; color: #fa5; }
  .step-body .type-badge.swipe { background: #1a3a2a; color: #5fa; }

  /* ── Modal ── */
  .modal-overlay {
    display: none; position: fixed; top:0;left:0;right:0;bottom:0;
    background: rgba(0,0,0,0.6); z-index: 999; align-items:center; justify-content:center;
  }
  .modal-overlay.show { display: flex; }
  .modal-box {
    background: #16213e; border: 1px solid #0f3460; border-radius: 10px;
    padding: 20px; min-width: 560px; max-width: 800px; max-height: 70vh;
    display: flex; flex-direction: column;
  }
  .modal-box h3 { color: #00d4aa; margin-bottom: 12px; font-size: 15px; }
  .modal-list {
    flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px;
  }
  .modal-list .item {
    padding: 8px 12px; background: #0d1b2a; border: 1px solid #0f3460;
    border-radius: 5px; cursor: pointer; font-size: 13px; transition: 0.15s;
  }
  .modal-list .item:hover { border-color: #00d4aa; background: #1a2a50; }
  .modal-list .empty {
    padding: 20px; text-align: center; color: #555; font-size: 13px;
  }
  .modal-close {
    margin-top: 10px; text-align: right;
  }
  .modal-close button {
    background: #0f3460; color: #eee; border: 1px solid #1a4a8a;
    padding: 6px 16px; border-radius: 5px; cursor: pointer; font-size: 13px;
  }
  .modal-close button:hover { background: #1a4a8a; }

  /* ── Toast ── */
  #toast {
    position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
    background: #00d4aa; color: #1a1a2e; padding: 10px 24px; border-radius: 8px;
    font-weight: bold; opacity: 0; transition: opacity 0.3s; pointer-events: none; z-index: 999;
  }
  #toast.show { opacity: 1; }
  #toast.error { background: #e94560; color: #fff; }

  /* ── 滚动条 ── */
  ::-webkit-scrollbar { width: 5px; height: 5px; }
  ::-webkit-scrollbar-track { background: #0d1b2a; }
  ::-webkit-scrollbar-thumb { background: #0f3460; border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: #1a4a8a; }
</style>
</head>
<body>

<div id="header">
  <h1>Workflow Builder</h1>
  <span class="device-info" id="device-info">-</span>
  <div class="actions">
    <button onclick="saveWorkflow()">Save</button>
    <button onclick="showLoadDialog()">Load</button>
    <button class="btn-primary" onclick="runAllSteps()">▶ Run All</button>
    <button class="btn-primary" onclick="runAllWithInitEnv()" style="background:#e94560;border-color:#e94560;color:#fff">▶ 恢复环境并运行</button>
    <button class="btn-primary" onclick="exportScript()">Export Script</button>
    <button class="btn-danger" onclick="clearAll()">Clear</button>
  </div>
</div>

<div id="main">
  <!-- Left: Template list -->
  <div id="tpl-panel">
    <div class="panel-title">
      Templates <span id="tpl-count"></span>
      <button class="panel-refresh" onclick="loadTemplates()" title="Refresh templates">&#x21bb;</button>
    </div>
    <div id="tpl-search-wrap"><input id="tpl-search" type="text" placeholder="Search templates..." oninput="filterTemplates()" /></div>
    <div id="tpl-list"></div>
  </div>
  <div class="resize-handle" id="resize-handle"></div>

  <!-- Right: Workflow -->
  <div id="workflow-panel">
    <div class="panel-title">
      Steps <span class="count" id="step-count">(0)</span>
      <span style="display:flex;gap:3px;font-size:11px;color:#555">
        <button class="btn-batch" onclick="enableAll()" title="Enable all steps">Enable All</button>
        <button class="btn-batch" onclick="invertEnabled()" title="Toggle enable/disable all">Invert</button>
        <button class="btn-batch" onclick="deleteDisabled()" title="Delete disabled steps" style="color:#e94560">Del Off</button>
      </span>
      <span style="margin-left:auto;display:flex;gap:4px">
        <button class="btn-add-step" onclick="addClickStep()" title="Add click step (from template)">+ Click</button>
        <button class="btn-add-step" onclick="addTextStep()" title="Add text input step">+ Text</button>
        <button class="btn-add-step" onclick="addLongClickStep()" title="Add long click step">+ LongClick</button>
        <button class="btn-add-step" onclick="addBackStep()" title="Add back step">+ Back</button>
        <button class="btn-add-step" onclick="addWaitStep()" title="Add wait step">+ Wait</button>
        <button class="btn-add-step" onclick="addSwipeStep('down')" title="Add swipe down step">+ 下滑</button>
        <button class="btn-add-step" onclick="addSwipeStep('up')" title="Add swipe up step">+ 上滑</button>
        <button class="btn-add-step" onclick="addScreenrecordStep()" title="Add screenrecord step">+ Screenrecord</button>
      </span>
    </div>
    <div id="step-list">
      <div id="drop-hint">Click or drag templates from the left panel</div>
    </div>
  </div>
</div>

<div class="modal-overlay" id="load-modal">
  <div class="modal-box">
    <h3>Load Workflow</h3>
    <div class="modal-list" id="load-modal-list">
      <div class="empty">Loading...</div>
    </div>
    <div class="modal-close"><button onclick="closeLoadDialog()">Cancel</button></div>
  </div>
</div>

<div id="toast"></div>

<script>
// ── State ──
var steps = [];  // each: { type:'click'|'text'|'long_click'|'wait'|'back', desc, ...fields }
var currentTemplates = [];
var currentWorkflowFile = null;
var insertPos = -1;
var _activeStep = -1;  // step index for template change target
var _allTemplateItems = [];  // {name, el} for filtering

// ── Init ──
window.addEventListener('load', function() {
  loadTemplates();
  fetch('/api/device').then(r => r.json()).then(d => {
    if (d.success) document.getElementById('device-info').textContent = d.name + ' ' + d.resolution;
  });
  setupResize();
});

// ── Templates ──
async function loadTemplates() {
  var resp = await fetch('/api/templates');
  var data = await resp.json();
  currentTemplates = data.templates || [];
  _allTemplateItems = [];
  var list = document.getElementById('tpl-list');
  list.innerHTML = '';
  document.getElementById('tpl-count').textContent = '(' + currentTemplates.length + ')';
  currentTemplates.forEach(function(t) {
    var el = document.createElement('div');
    el.className = 'tpl-item';
    el.draggable = true;
    el.innerHTML = '<img src="/api/template_img/' + encodeURIComponent(t) + '" alt="" />' +
      '<div class="name">' + t.replace('.png','') + '</div>' +
      '<span style="margin-left:auto;color:#0f3460;font-size:11px">+</span>';
    el.addEventListener('dragstart', function(e) {
      e.dataTransfer.setData('text/plain', t);
      el.classList.add('dragging');
    });
    el.addEventListener('dragend', function(e) {
      el.classList.remove('dragging');
    });
    el.addEventListener('click', function() {
      if (_activeStep >= 0 && _activeStep < steps.length) {
        addStep(t);
      } else {
        toast('Click a step first, or double-click to add', false);
      }
    });
    el.addEventListener('dblclick', function() {
      // 双击始终追加到末尾
      _activeStep = -1;
      insertPos = -1;
      addStep(t);
    });
    list.appendChild(el);
    _allTemplateItems.push({ name: t.replace('.png','').toLowerCase(), el: el });
  });
}

// ── Filter Templates ──
function filterTemplates() {
  var q = document.getElementById('tpl-search').value.trim().toLowerCase();
  var visible = 0;
  _allTemplateItems.forEach(function(item) {
    if (!q || item.name.indexOf(q) >= 0) {
      item.el.style.display = '';
      visible++;
    } else {
      item.el.style.display = 'none';
    }
  });
  document.getElementById('tpl-count').textContent = '(' + visible + '/' + _allTemplateItems.length + ')';
}

// ── Add Step ──
function addStep(templateName) {
  // 如果有待插入位置，先插入
  if (insertPos >= 0) {
    doInsertStep(templateName);
    return;
  }
  // 如果有激活的步骤，更换其模板
  if (_activeStep >= 0 && _activeStep < steps.length) {
    var s = steps[_activeStep];
    s.template = templateName;
    s.type = 'click';
    s.desc = templateName.replace('.png','');
    if (s.threshold === undefined) s.threshold = 0.8;
    if (s.timeout === undefined) s.timeout = 10;
    if (s.offsetX === undefined) s.offsetX = 0;
    if (s.offsetY === undefined) s.offsetY = 0;
    renderSteps();
    toast('Template changed: ' + templateName);
    return;
  }
  var already = steps.filter(function(s) { return s.template === templateName; }).length;
  steps.push({
    type: 'click', enabled: true, template: templateName,
    desc: templateName.replace('.png','') + (already > 0 ? '_' + (already+1) : ''),
    threshold: 0.8, timeout: 10, offsetX: 0, offsetY: 0,
  });
  renderSteps();
  toast('Added: ' + templateName);
}
function addTextStep() {
  steps.push({ type: 'text', enabled: true, desc: 'input text', text: '' });
  renderSteps();
  toast('Added text step');
}
function addLongClickStep() {
  var tmpl = currentTemplates.length > 0 ? currentTemplates[0] : 'unknown.png';
  steps.push({ type: 'long_click', enabled: true, template: tmpl, desc: 'long press ' + tmpl.replace('.png',''),
    threshold: 0.8, timeout: 10, offsetX: 0, offsetY: 0, duration: 1.0 });
  renderSteps();
  toast('Added long click step');
}
function addClickStep() {
  if (currentTemplates.length === 0) { toast('No templates available', true); return; }
  addStep(currentTemplates[0]);
}
function addWaitStep() {
  steps.push({ type: 'wait', enabled: true, desc: 'wait', seconds: 2 });
  renderSteps();
  toast('Added wait step');
}
function addBackStep() {
  steps.push({ type: 'back', enabled: true, desc: 'back' });
  renderSteps();
  toast('Added back step');
}
function addScreenrecordStep() {
  steps.push({ type: 'screenrecord', enabled: true, desc: 'screenrecord' });
  renderSteps();
  toast('Added screenrecord step');
}
function addSwipeStep(dir) {
  if (dir === 'down') {
    steps.push({ type: 'swipe', enabled: true, desc: '下滑', sx: 100, sy: 300, ex: 100, ey: 800, duration: 0.3 });
  } else {
    steps.push({ type: 'swipe', enabled: true, desc: '上滑', sx: 100, sy: 800, ex: 100, ey: 300, duration: 0.3 });
  }
  renderSteps();
  toast('Added ' + (dir === 'down' ? 'swipe down' : 'swipe up') + ' step');
}

// ── Render Steps ──
function renderSteps() {
  var container = document.getElementById('step-list');
  container.innerHTML = '';
  document.getElementById('step-count').textContent = '(' + steps.length + ')';

  if (steps.length === 0) {
    container.innerHTML = '<div id="drop-hint">Drop templates here to build workflow</div>';
    setupDropZone(container);
    return;
  }

  steps.forEach(function(step, idx) {
    var card = document.createElement('div');
    card.className = 'step-card';
    card.dataset.index = idx;

    // -- header (common) --
    var enabled = step.enabled !== false;
    var headerHtml =
      '<div class="step-header">' +
        '<input class="enable-cb" type="checkbox" ' + (enabled ? 'checked' : '') +
          ' onchange="toggleStep(' + idx + ', this.checked)" title="Enable/disable step" />' +
        '<span class="step-num">' + (idx + 1) + '</span>';

    // type-specific header icon
    if (step.type === 'click') {
      headerHtml += '<img class="step-img" src="/api/template_img/' + encodeURIComponent(step.template) + '" />';
    } else if (step.type === 'text') {
      headerHtml += '<span style="font-size:18px;width:36px;text-align:center;flex-shrink:0">&#x2328;</span>';
    } else if (step.type === 'long_click') {
      headerHtml += '<img class="step-img" src="/api/template_img/' + encodeURIComponent(step.template) + '" />';
    } else if (step.type === 'wait') {
      headerHtml += '<span style="font-size:18px;width:36px;text-align:center;flex-shrink:0">&#x23F1;</span>';
    } else if (step.type === 'back') {
      headerHtml += '<span style="font-size:18px;width:36px;text-align:center;flex-shrink:0">&#x21A9;</span>';
    } else if (step.type === 'swipe') {
      headerHtml += '<span style="font-size:18px;width:36px;text-align:center;flex-shrink:0">&#x21C5;</span>';
    } else if (step.type === 'screenrecord') {
      headerHtml += '<span style="font-size:18px;width:36px;text-align:center;flex-shrink:0">&#x25CF;</span>';
    }

    headerHtml +=
        '<input class="step-desc" type="text" value="' + escHtml(step.desc) + '" placeholder="description" ' +
          'onchange="updateStep(' + idx + ', \'desc\', this.value)" />' +
        '<div class="step-actions">' +
          '<button class="run-btn" onclick="runStep(' + idx + ')" title="Run this step now">&#x25B6;</button>' +
          '<button class="move-btn" onclick="moveStep(' + idx + ', -1)" title="Move up">&#x25B2;</button>' +
          '<button class="move-btn" onclick="moveStep(' + idx + ', 1)" title="Move down">&#x25BC;</button>' +
          '<button class="del-btn" onclick="removeStep(' + idx + ')" title="Delete">&#x2716;</button>' +
        '</div>' +
      '</div>';

    // -- type selector --
    var typeOpts = ['click', 'text', 'long_click', 'swipe', 'wait', 'back', 'screenrecord'];
    var typeSel = '<select class="type-select" onchange="changeStepType(' + idx + ', this.value)">';
    typeOpts.forEach(function(t) {
      typeSel += '<option value="' + t + '"' + (step.type === t ? ' selected' : '') + '>' + t + '</option>';
    });
    typeSel += '</select>';

    // -- body (type-specific) --
    var bodyHtml = '';
    if (step.type === 'click') {
      bodyHtml += '<div class="tpl-name-tag">' + step.template + '</div>';
      bodyHtml += '<div class="step-body">' +
        '<label>threshold <input type="number" step="0.05" min="0" max="1" value="' + (step.threshold || 0.8) + '" ' +
          'onchange="updateStep(' + idx + ', \'threshold\', +this.value)" /></label>' +
        '<label>timeout <input type="number" step="1" min="1" value="' + (step.timeout || 10) + '" ' +
          'onchange="updateStep(' + idx + ', \'timeout\', +this.value)" /></label>' +
        '<label>offsetX <input class="offset-input" type="number" step="1" value="' + (step.offsetX || 0) + '" ' +
          'onchange="updateStep(' + idx + ', \'offsetX\', +this.value)" /></label>' +
        '<label>offsetY <input class="offset-input" type="number" step="1" value="' + (step.offsetY || 0) + '" ' +
          'onchange="updateStep(' + idx + ', \'offsetY\', +this.value)" /></label>' +
      '</div>';
    } else if (step.type === 'text') {
      bodyHtml += '<div class="step-body">' +
        '<span class="type-badge text">text</span>' +
        '<label>send_keys <input class="text-input-wide" type="text" value="' + escHtml(step.text || '') + '" ' +
          'placeholder="text to input" onchange="updateStep(' + idx + ', \'text\', this.value)" /></label>' +
      '</div>';
    } else if (step.type === 'swipe') {
      bodyHtml += '<div class="step-body">' +
        '<span class="type-badge swipe">swipe</span>' +
        '<label>sx <input type="number" step="1" value="' + (step.sx || 0) + '" ' +
          'onchange="updateStep(' + idx + ', \'sx\', +this.value)" /></label>' +
        '<label>sy <input type="number" step="1" value="' + (step.sy || 0) + '" ' +
          'onchange="updateStep(' + idx + ', \'sy\', +this.value)" /></label>' +
        '<label>ex <input type="number" step="1" value="' + (step.ex || 0) + '" ' +
          'onchange="updateStep(' + idx + ', \'ex\', +this.value)" /></label>' +
        '<label>ey <input type="number" step="1" value="' + (step.ey || 0) + '" ' +
          'onchange="updateStep(' + idx + ', \'ey\', +this.value)" /></label>' +
        '<label>duration <input type="number" step="0.1" min="0" value="' + (step.duration || 0.1) + '" ' +
          'onchange="updateStep(' + idx + ', \'duration\', +this.value)" /></label>' +
      '</div>';
    } else if (step.type === 'long_click') {
      bodyHtml += '<div class="tpl-name-tag">' + step.template + '</div>';
      bodyHtml += '<div class="step-body">' +
        '<span class="type-badge long_click">long_click</span>' +
        '<label>threshold <input type="number" step="0.05" min="0" max="1" value="' + (step.threshold || 0.8) + '" ' +
          'onchange="updateStep(' + idx + ', \'threshold\', +this.value)" /></label>' +
        '<label>timeout <input type="number" step="1" min="1" value="' + (step.timeout || 10) + '" ' +
          'onchange="updateStep(' + idx + ', \'timeout\', +this.value)" /></label>' +
        '<label>offsetX <input class="offset-input" type="number" step="1" value="' + (step.offsetX || 0) + '" ' +
          'onchange="updateStep(' + idx + ', \'offsetX\', +this.value)" /></label>' +
        '<label>offsetY <input class="offset-input" type="number" step="1" value="' + (step.offsetY || 0) + '" ' +
          'onchange="updateStep(' + idx + ', \'offsetY\', +this.value)" /></label>' +
        '<label>duration <input type="number" step="0.1" min="0.1" value="' + (step.duration || 1.0) + '" ' +
          'onchange="updateStep(' + idx + ', \'duration\', +this.value)" /></label>' +
      '</div>';
    } else if (step.type === 'wait') {
      bodyHtml += '<div class="step-body">' +
        '<span class="type-badge wait">wait</span>' +
        '<label>seconds <input type="number" step="0.5" min="0.1" value="' + (step.seconds || 2) + '" ' +
          'onchange="updateStep(' + idx + ', \'seconds\', +this.value)" /></label>' +
      '</div>';
    } else if (step.type === 'back') {
      bodyHtml += '<div class="step-body"><span class="type-badge back">back</span></div>';
    } else if (step.type === 'screenrecord') {
      bodyHtml += '<div class="step-body"><span class="type-badge screenrecord" style="background:#e94560">screenrecord</span></div>';
    }

    // -- insert bar before each step --
    container.appendChild(createInsertBar(idx));

    if (!enabled) card.classList.add('disabled');
    if (_activeStep === idx) card.classList.add('active-step');
    card.innerHTML = headerHtml + typeSel + bodyHtml;

    // 点击卡片设为激活步骤（用于更换模板）
    card.addEventListener('click', function(e) {
      // 点击输入框/按钮时不触发
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON' || e.target.tagName === 'SELECT') return;
      _activeStep = idx;
      renderSteps();
    });

    container.appendChild(card);
  });

  // 点击空白区取消激活
  container.addEventListener('click', function(e) {
    if (e.target === container || e.target.id === 'drop-hint') {
      _activeStep = -1;
      renderSteps();
    }
  });

  // 底部插入条 + 拖入区
  container.appendChild(createInsertBar(steps.length));
  var dropEnd = document.createElement('div');
  dropEnd.style.cssText = 'border:2px dashed #0f3460;border-radius:8px;min-height:60px;display:flex;align-items:center;justify-content:center;color:#555;font-size:13px;transition:0.2s;';
  dropEnd.textContent = 'Drop or click template from left panel';
  setupDropZone(dropEnd);
  container.appendChild(dropEnd);
}

// ── 指定位置插入 ──
function createInsertBar(pos) {
  var bar = document.createElement('div');
  bar.style.cssText = 'display:flex;align-items:center;gap:6px;margin:2px 0;transition:0.15s;cursor:default;';
  var line = document.createElement('div');
  line.style.cssText = 'flex:1;height:1px;background:#0f3460;transition:0.2s;';
  var btn = document.createElement('button');
  btn.textContent = '+';
  btn.style.cssText = 'background:none;border:1px solid #0f3460;color:#555;width:20px;height:20px;border-radius:50%;cursor:pointer;font-size:13px;line-height:1;padding:0;transition:0.2s;flex-shrink:0;';
  btn.title = 'Insert step here';
  btn.addEventListener('click', function() { insertClickStep(pos); });
  bar.appendChild(btn);
  bar.appendChild(line);
  // hover 高亮
  bar.addEventListener('mouseenter', function() {
    line.style.background = '#00d4aa';
    btn.style.borderColor = '#00d4aa';
    btn.style.color = '#00d4aa';
  });
  bar.addEventListener('mouseleave', function() {
    line.style.background = '#0f3460';
    btn.style.borderColor = '#0f3460';
    btn.style.color = '#555';
  });
  return bar;
}
function insertClickStep(pos) {
  insertPos = pos;
  // 如果有模板则直接插入，否则等待点选模板
  if (currentTemplates.length > 0) {
    doInsertStep(currentTemplates[0]);
  } else {
    toast('No templates available', true);
    insertPos = -1;
  }
}
function doInsertStep(templateName) {
  var pos = insertPos >= 0 ? insertPos : steps.length;
  insertPos = -1;
  var already = steps.filter(function(s) { return s.template === templateName; }).length;
  steps.splice(pos, 0, {
    type: 'click', enabled: true, template: templateName,
    desc: templateName.replace('.png','') + (already > 0 ? '_' + (already+1) : ''),
    threshold: 0.8, timeout: 10, offsetX: 0, offsetY: 0,
  });
  _activeStep = pos;
  renderSteps();
  toast('Inserted: ' + templateName + ' at position ' + (pos + 1));
}

function setupDropZone(el) {
  el.addEventListener('dragover', function(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    el.classList.add('drag-over');
  });
  el.addEventListener('dragleave', function() { el.classList.remove('drag-over'); });
  el.addEventListener('drop', function(e) {
    e.preventDefault();
    el.classList.remove('drag-over');
    var tpl = e.dataTransfer.getData('text/plain');
    if (tpl && tpl !== 'reorder') { addStep(tpl); }
  });
}

function escHtml(s) { return String(s).replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

// ── Step Operations ──
function updateStep(idx, key, val) {
  if (idx >= 0 && idx < steps.length) { steps[idx][key] = val; }
}
function toggleStep(idx, checked) {
  if (idx >= 0 && idx < steps.length) { steps[idx].enabled = checked; renderSteps(); }
}
// ── Run Single Step ──
async function runStep(idx) {
  if (idx < 0 || idx >= steps.length) return;
  var step = steps[idx];
  if (step.enabled === false) { toast('Step is disabled', true); return; }
  try {
    var resp = await fetch('/api/run_step', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ step: step }),
    });
    var data = await resp.json();
    if (data.success) {
      toast('Step ' + (idx+1) + ' OK: ' + (data.result || ''));
    } else {
      toast('Step ' + (idx+1) + ' failed: ' + data.error, true);
    }
  } catch(e) {
    toast('Run error: ' + e.message, true);
  }
}

// ── Run All Steps ──
async function runAllSteps() {
  var active = steps.filter(function(s) { return s.enabled !== false; });
  if (active.length === 0) { toast('No active steps to run', true); return; }
  if (!confirm('Run ' + active.length + ' step(s) on device?')) return;
  var btn = document.querySelector('button[onclick="runAllSteps()"]');
  btn.disabled = true;
  btn.textContent = 'Running...';
  try {
    var resp = await fetch('/api/run_all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ steps: steps }),
    });
    var data = await resp.json();
    if (data.success) {
      toast('Done: ' + data.results);
    } else {
      toast('Failed at step ' + (data.failed_at || '?') + ': ' + data.error, true);
    }
  } catch(e) {
    toast('Run error: ' + e.message, true);
  }
  btn.disabled = false;
  btn.textContent = 'Run All';
}

// ── Run All Steps with InitEnv ──
async function runAllWithInitEnv() {
  var active = steps.filter(function(s) { return s.enabled !== false; });
  if (active.length === 0) { toast('No active steps to run', true); return; }
  if (!confirm('恢复环境后执行 ' + active.length + ' 步?')) return;
  var btn = document.querySelector('button[onclick="runAllWithInitEnv()"]');
  btn.disabled = true;
  btn.textContent = '恢复环境并运行中...';
  try {
    var resp = await fetch('/api/run_all_initenv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ steps: steps }),
    });
    var data = await resp.json();
    if (data.success) {
      toast('Done: ' + data.results);
    } else {
      toast('Failed at step ' + (data.failed_at || '?') + ': ' + (data.error || ''), true);
    }
  } catch(e) {
    toast('Run error: ' + e.message, true);
  }
  btn.disabled = false;
  btn.textContent = '恢复环境并运行';
}

// ── Batch Operations ──
function enableAll() {
  steps.forEach(function(s) { s.enabled = true; });
  renderSteps();
  toast('All steps enabled');
}
function invertEnabled() {
  steps.forEach(function(s) { s.enabled = !s.enabled; });
  renderSteps();
  toast('Inverted enable states');
}
function deleteDisabled() {
  var disabled = steps.filter(function(s) { return s.enabled === false; });
  if (disabled.length === 0) { toast('No disabled steps', true); return; }
  if (!confirm('Delete ' + disabled.length + ' disabled step(s)?')) return;
  steps = steps.filter(function(s) { return s.enabled !== false; });
  renderSteps();
  toast('Deleted ' + disabled.length + ' step(s)');
}
function changeStepType(idx, newType) {
  if (idx < 0 || idx >= steps.length) return;
  var s = steps[idx];
  if (s.type === newType) return;
  // preserve common fields
  var desc = s.desc || '';
  var enabled = s.enabled !== false;
  if (newType === 'click') {
    var tmpl = s.template || (currentTemplates.length > 0 ? currentTemplates[0] : 'unknown.png');
    var th = s.threshold !== undefined ? s.threshold : 0.8;
    var to = s.timeout !== undefined ? s.timeout : 10;
    var ox = s.offsetX !== undefined ? s.offsetX : 0;
    var oy = s.offsetY !== undefined ? s.offsetY : 0;
    steps[idx] = { type:'click', enabled:enabled, template:tmpl, desc:desc, threshold:th, timeout:to, offsetX:ox, offsetY:oy };
  } else if (newType === 'text') {
    steps[idx] = { type:'text', enabled:enabled, desc:desc, text:'' };
  } else if (newType === 'long_click') {
    // 保留来自 click 的模板和匹配参数
    var tmpl = s.template || (currentTemplates.length > 0 ? currentTemplates[0] : 'unknown.png');
    var th = s.threshold !== undefined ? s.threshold : 0.8;
    var to = s.timeout !== undefined ? s.timeout : 10;
    var ox = s.offsetX !== undefined ? s.offsetX : 0;
    var oy = s.offsetY !== undefined ? s.offsetY : 0;
    steps[idx] = { type:'long_click', enabled:enabled, template:tmpl, desc:desc, threshold:th, timeout:to, offsetX:ox, offsetY:oy, duration:1.0 };
  } else if (newType === 'swipe') {
    steps[idx] = { type:'swipe', enabled:enabled, desc:desc || '上滑', sx:100, sy:800, ex:100, ey:300, duration:0.3 };
  } else if (newType === 'wait') {
    steps[idx] = { type:'wait', enabled:enabled, desc:desc, seconds:2 };
  } else if (newType === 'back') {
    steps[idx] = { type:'back', enabled:enabled, desc:desc || 'back' };
  } else if (newType === 'screenrecord') {
    steps[idx] = { type:'screenrecord', enabled:enabled, desc:desc || 'screenrecord' };
  }
  renderSteps();
  toast('Changed to ' + newType);
}
function removeStep(idx) {
  if (idx >= 0 && idx < steps.length) { steps.splice(idx, 1); renderSteps(); }
}
function moveStep(idx, dir) {
  var to = idx + dir;
  if (to < 0 || to >= steps.length) return;
  var item = steps.splice(idx, 1)[0];
  steps.splice(to, 0, item);
  renderSteps();
}
function clearAll() {
  if (steps.length === 0) return;
  if (!confirm('Clear all steps?')) return;
  steps = []; renderSteps(); toast('Cleared');
}

// ── Save / Load ──
async function saveWorkflow() {
  if (steps.length === 0) { toast('No steps to save', true); return; }
  var defaultName = currentWorkflowFile || ('workflow_' + new Date().toISOString().slice(0,10) + '.json');
  var name = prompt('Workflow filename:', defaultName);
  if (!name) return;
  if (!name.endsWith('.json')) name += '.json';
  try {
    var resp = await fetch('/api/save_workflow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, steps: steps }),
    });
    var data = await resp.json();
    if (data.success) {
      currentWorkflowFile = name;
      toast('Saved: ' + data.path);
    } else { toast('Save failed: ' + data.error, true); }
  } catch(e) { toast('Error: ' + e.message, true); }
}

// ── Load Dialog ──
function showLoadDialog() {
  var list = document.getElementById('load-modal-list');
  list.innerHTML = '<div class="empty">Loading...</div>';
  document.getElementById('load-modal').classList.add('show');
  fetch('/api/list_workflows').then(function(r) { return r.json(); }).then(function(data) {
    list.innerHTML = '';
    if (!data.success || !data.workflows || data.workflows.length === 0) {
      list.innerHTML = '<div class="empty">No workflow files in workflows/</div>';
      return;
    }
    data.workflows.forEach(function(f) {
      var el = document.createElement('div');
      el.className = 'item';
      el.textContent = f;
      el.addEventListener('click', function() { loadWorkflowFile(f); });
      list.appendChild(el);
    });
  }).catch(function(e) {
    list.innerHTML = '<div class="empty">Error: ' + e.message + '</div>';
  });
}
function closeLoadDialog() {
  document.getElementById('load-modal').classList.remove('show');
}
async function loadWorkflowFile(filename) {
  closeLoadDialog();
  try {
    var resp = await fetch('/api/load_workflow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: filename }),
    });
    var data = await resp.json();
    if (data.success && data.steps && Array.isArray(data.steps)) {
      steps = data.steps;
      currentWorkflowFile = filename;
      renderSteps();
      toast('Loaded: ' + filename);
    } else { toast('Load failed: ' + (data.error || 'invalid file'), true); }
  } catch(e) { toast('Error: ' + e.message, true); }
}

// ── Export Script ──
async function exportScript() {
  if (steps.length === 0) { toast('No steps to export', true); return; }
  var name = prompt('Script filename:', 'workflow.py');
  if (!name) return;
  if (!name.endsWith('.py')) name += '.py';
  try {
    var resp = await fetch('/api/export_script', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ steps: steps, filename: name }),
    });
    var data = await resp.json();
    if (data.success) {
      // 下载脚本
      var blob = new Blob([data.script], { type: 'text/python;charset=utf-8' });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = data.filename || 'workflow.py';
      a.click();
      toast('Script exported: ' + (data.filename || 'workflow.py'));
    } else { toast('Export failed: ' + data.error, true); }
  } catch(e) { toast('Error: ' + e.message, true); }
}

// ── Resize ──
function setupResize() {
  var handle = document.getElementById('resize-handle');
  var panel = document.getElementById('tpl-panel');
  var isResizing = false;
  handle.addEventListener('mousedown', function(e) {
    isResizing = true; e.preventDefault();
  });
  document.addEventListener('mousemove', function(e) {
    if (!isResizing) return;
    var w = Math.max(120, Math.min(400, e.clientX));
    panel.style.width = w + 'px'; panel.style.minWidth = w + 'px';
  });
  document.addEventListener('mouseup', function() { isResizing = false; });
}

// ── Toast ──
function toast(msg, isError) {
  var el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show' + (isError ? ' error' : '');
  clearTimeout(el._timer);
  el._timer = setTimeout(function() { el.classList.remove('show'); }, 2500);
}
</script>
</body>
</html>
"""


# ─────────────── HTTP 请求处理 ───────────────

class RequestHandler(BaseHTTPRequestHandler):
    # 设备引用由 main() 启动时设置，所有请求共享
    device = None
    device_name = None

    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send_html(HTML_PAGE)

        elif path == "/api/templates":
            self._handle_templates()

        elif path == "/api/device":
            self._handle_device_info()

        elif path == "/api/list_workflows":
            self._handle_list_workflows()

        elif path.startswith("/api/template_img/"):
            name = path[len("/api/template_img/"):]
            self._handle_template_image(name)

        else:
            self._send_json({"success": False, "error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len)) if content_len else {}

        if path == "/api/run_step":
            self._handle_run_step(body)
        elif path == "/api/run_all":
            self._handle_run_all(body)
        elif path == "/api/run_all_initenv":
            self._handle_run_all_initenv(body)
        elif path == "/api/save_workflow":
            self._handle_save_workflow(body)
        elif path == "/api/load_workflow":
            self._handle_load_workflow(body)
        elif path == "/api/export_script":
            self._handle_export_script(body)
        else:
            self._send_json({"success": False, "error": "Not found"}, 404)

    # ── Handlers ──

    def _handle_templates(self):
        try:
            os.makedirs(TEMPLATE_DIR, exist_ok=True)
            files = sorted(f for f in os.listdir(TEMPLATE_DIR) if f.lower().endswith(".png"))
            self._send_json({"success": True, "templates": files})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _handle_template_image(self, name):
        try:
            path = os.path.join(TEMPLATE_DIR, name)
            if not os.path.isfile(path):
                # 防范路径穿越
                path = os.path.normpath(os.path.join(TEMPLATE_DIR, os.path.basename(name)))
            if not os.path.isfile(path):
                self._send_json({"success": False, "error": "Not found"}, 404)
                return
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "max-age=30")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_device_info(self):
        d = RequestHandler.device
        if d is None:
            self._send_json({"success": False, "error": "Not connected"})
            return
        w, h = d.window_size()
        self._send_json({
            "success": True,
            "name": RequestHandler.device_name or "Android",
            "resolution": f"{w}x{h}",
        })

    def _handle_list_workflows(self):
        try:
            os.makedirs(WORKFLOW_DIR, exist_ok=True)
            files = sorted(f for f in os.listdir(WORKFLOW_DIR) if f.lower().endswith(".json"))
            self._send_json({"success": True, "workflows": files})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _handle_load_workflow(self, body):
        filename = body.get("filename", "").strip()
        if not filename:
            self._send_json({"success": False, "error": "No filename"})
            return
        # 防范路径穿越
        safe_name = os.path.basename(filename)
        filepath = os.path.join(WORKFLOW_DIR, safe_name)
        if not os.path.isfile(filepath):
            self._send_json({"success": False, "error": f"File not found: {safe_name}"})
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            steps = data.get("steps", [])
            self._send_json({"success": True, "steps": steps})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _handle_run_step(self, body):
        d = RequestHandler.device
        step = body.get("step", {})
        if d is None:
            self._send_json({"success": False, "error": "Device not connected"})
            return
        try:
            result = execute_single_step(d, step)
            self._send_json(result)
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _handle_run_all(self, body):
        d = RequestHandler.device
        steps = body.get("steps", [])
        if d is None:
            self._send_json({"success": False, "error": "Device not connected"})
            return
        ok_count = 0
        fail_count = 0
        for i, step in enumerate(steps):
            if step.get("enabled", True) is False:
                continue
            result = execute_single_step(d, step)
            if result.get("success"):
                ok_count += 1
            else:
                fail_count += 1
                self._send_json({
                    "success": False,
                    "error": result.get("error", "unknown"),
                    "failed_at": i + 1,
                    "results": f"{ok_count} ok, {fail_count} failed",
                })
                return
        self._send_json({
            "success": True,
            "results": f"{ok_count} steps completed",
        })

    def _handle_run_all_initenv(self, body):
        d = RequestHandler.device
        steps = body.get("steps", [])
        if d is None:
            self._send_json({"success": False, "error": "Device not connected"})
            return

        # initenv: press back repeatedly until wx_filetranshelper.png appears
        INITENV_TEMPLATE = "wx_filetranshelper.png"
        INITENV_MAX_ATTEMPTS = 10
        INITENV_INTERVAL = 0.5
        import time as _time
        import cv2

        tpl_path = os.path.join("templates", INITENV_TEMPLATE)
        if not os.path.isfile(tpl_path):
            self._send_json({"success": False, "error": f"Init template not found: {tpl_path}"})
            return
        template_cv = cv2.imread(tpl_path)
        if template_cv is None:
            self._send_json({"success": False, "error": f"Cannot read template: {tpl_path}"})
            return

        logger.info("开始环境恢复 (initenv)...")
        found = False
        for i in range(1, INITENV_MAX_ATTEMPTS + 1):
            logger.info(f"  [{i}/{INITENV_MAX_ATTEMPTS}] 检测 '{INITENV_TEMPLATE}'...")
            try:
                screenshot = d.screenshot(format="opencv")
                if screenshot is not None:
                    result = cv2.matchTemplate(screenshot, template_cv, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                    if max_val >= 0.8:
                        h, w = template_cv.shape[:2]
                        cx = max_loc[0] + w // 2
                        cy = max_loc[1] + h // 2
                        logger.info(f"  检测到 '{INITENV_TEMPLATE}' ({cx},{cy}) 置信度: {max_val:.3f}")
                        found = True
                        break
            except Exception as e:
                logger.warning(f"  截图/匹配异常: {e}")

            logger.info(f"  未检测到 '{INITENV_TEMPLATE}', 执行 back")
            d.press("back")
            _time.sleep(INITENV_INTERVAL)

        if not found:
            self._send_json({
                "success": False,
                "error": f"环境恢复失败: {INITENV_MAX_ATTEMPTS} 次尝试后仍未检测到 '{INITENV_TEMPLATE}'",
            })
            return

        logger.info("环境恢复成功，开始执行步骤...")

        # 再执行所有步骤（同 run_all）
        ok_count = 0
        fail_count = 0
        for i, step in enumerate(steps):
            if step.get("enabled", True) is False:
                continue
            result = execute_single_step(d, step)
            if result.get("success"):
                ok_count += 1
            else:
                fail_count += 1
                self._send_json({
                    "success": False,
                    "error": result.get("error", "unknown"),
                    "failed_at": i + 1,
                    "results": f"环境恢复 ✓, 步骤: {ok_count} ok, {fail_count} failed",
                })
                return
        self._send_json({
            "success": True,
            "results": f"环境恢复 ✓, 步骤: {ok_count} completed",
        })

    def _handle_save_workflow(self, body):
        name = body.get("name", "").strip()
        steps = body.get("steps", [])
        if not name: name = f"workflow_{int(__import__('time').time())}"
        if not name.endswith(".json"):
            name += ".json"

        os.makedirs(WORKFLOW_DIR, exist_ok=True)
        filepath = os.path.join(WORKFLOW_DIR, name)
        data = {"name": name, "steps": steps}
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"工作流已保存: {filepath} ({len(steps)} steps)")
        self._send_json({"success": True, "path": os.path.abspath(filepath)})

    def _handle_export_script(self, body):
        steps = body.get("steps", [])
        if not steps:
            self._send_json({"success": False, "error": "No steps"})
            return

        lines = []
        lines.append('"""')
        lines.append('Auto-generated workflow script')
        lines.append('Run: python workflow.py')
        lines.append('"""')
        lines.append('')
        lines.append('import sys')
        lines.append('from pathlib import Path')
        lines.append('sys.path.insert(0, str(Path(__file__).resolve().parent))')
        lines.append('')
        lines.append('from core.logger import get_logger')
        lines.append('from core.device import get_device')
        lines.append('from core.image_matcher import find_and_click, find_image')
        lines.append('from core.watchers import setup_watchers')
        lines.append('import time')
        lines.append('')
        lines.append('logger = get_logger(__name__)')
        lines.append('')
        lines.append('')
        lines.append('def run():')
        lines.append('    d = get_device()')
        lines.append('    setup_watchers(d)')
        lines.append('    time.sleep(1)')
        lines.append('')

        for i, step in enumerate(steps):
            desc = step.get("desc", f"Step {i+1}")
            enabled = step.get("enabled", True)

            if not enabled:
                lines.append(f'    # Step {i+1}: {desc} [disabled - skipped]')
                lines.append(f'    # logger.info("Step {i+1}: {desc} [disabled]")')
                lines.append(f'    # pass')
                lines.append('')
                continue

            lines.append(f'    # Step {i+1}: {desc}')
            lines.append(f'    logger.info("Step {i+1}: {desc}")')

            step_type = step.get("type", "click")

            if step_type == "click":
                tmpl = step.get("template", "unknown.png")
                threshold = float(step.get("threshold", 0.8))
                timeout = float(step.get("timeout", 10))
                ox = int(step.get("offsetX", 0))
                oy = int(step.get("offsetY", 0))
                tpl_path = f"templates/{tmpl}"
                if ox or oy:
                    lines.append(f'    find_and_click(d, "{tpl_path}", threshold={threshold}, timeout={timeout}, offset_x={ox}, offset_y={oy})')
                else:
                    lines.append(f'    find_and_click(d, "{tpl_path}", threshold={threshold}, timeout={timeout})')

            elif step_type == "text":
                text_val = step.get("text", "")
                lines.append(f'    d.send_keys({json.dumps(text_val, ensure_ascii=False)})')

            elif step_type == "long_click":
                tmpl = step.get("template", "unknown.png")
                threshold = float(step.get("threshold", 0.8))
                timeout = float(step.get("timeout", 10))
                ox = int(step.get("offsetX", 0))
                oy = int(step.get("offsetY", 0))
                duration = float(step.get("duration", 1.0))
                tpl_path = f"templates/{tmpl}"
                lines.append(f'    result = find_image(d, "{tpl_path}", threshold={threshold}, timeout={timeout})')
                lines.append(f'    if result:')
                lines.append(f'        cx, cy, _ = result')
                lines.append(f'        d.long_click(cx + {ox}, cy + {oy}, duration={duration})')

            elif step_type == "swipe":
                sx = int(step.get("sx", 0))
                sy = int(step.get("sy", 0))
                ex = int(step.get("ex", 0))
                ey = int(step.get("ey", 0))
                duration = float(step.get("duration", 0.1))
                lines.append(f'    d.swipe({sx}, {sy}, {ex}, {ey}, duration={duration})')

            elif step_type == "wait":
                seconds = float(step.get("seconds", 2))
                lines.append(f'    time.sleep({seconds})')

            elif step_type == "back":
                lines.append(f'    d.press("back")')

            elif step_type == "screenrecord":
                lines.append(f'    # screenrecord marker: pass --record to enable recording')

            else:
                lines.append(f'    # unknown step type: {step_type}')

            lines.append('')

        lines.append('    logger.info("Workflow completed")')
        lines.append('    return True')
        lines.append('')
        lines.append('')
        lines.append('if __name__ == "__main__":')
        lines.append('    run()')

        script = "\n".join(lines)
        filename = body.get("filename") or f"workflow_{int(__import__('time').time())}.py"
        self._send_json({
            "success": True,
            "script": script,
            "filename": filename,
        })


# ─────────────── 启动 ───────────────

def start_server():
    server = HTTPServer((HOST, PORT), RequestHandler)
    logger.info(f"Workflow Builder: http://{HOST}:{PORT}")
    webbrowser.open(f"http://{HOST}:{PORT}")
    server.serve_forever()


def main():
    print("=" * 50)
    print("  Workflow Builder")
    print("=" * 50)

    print("\n[Device] Connecting...")
    try:
        d = get_device()
        w, h = d.window_size()
        RequestHandler.device = d
        RequestHandler.device_name = d.info.get("productName", "Android")
        print(f"   [OK] {RequestHandler.device_name} ({w}x{h})")
    except Exception as e:
        print(f"   [Warn] Device connection failed: {e}")
        print("   Workflow editing still available, click/run needs device.")

    print("\n[Server] http://{}:{}".format(HOST, PORT))
    print("\nInstructions:")
    print("   1. Drag templates from left panel to workflow area")
    print("   2. Configure each step's threshold, timeout, offsets")
    print("   3. Reorder by dragging step handle (&#x2630;)")
    print("   4. Save / Load workflow files")
    print("   5. Export as runnable Python script")
    print("\nPress Ctrl+C to exit\n")

    try:
        start_server()
    except KeyboardInterrupt:
        print("\n[Exit] Stopped")


if __name__ == "__main__":
    main()
