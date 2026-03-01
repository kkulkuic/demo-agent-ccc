"""Agent behavior visualization: dot cursor, element highlight overlay, and helpers."""
from typing import Optional, List

# Dot overlay that follows DOM mousemove (from Borderering-cursor.txt)
DOT_JS = r"""
(() => {
  try {
    const old = document.getElementById('__pw_dot');
    if (old) old.remove();
    const dot = document.createElement('div');
    dot.id = '__pw_dot';
    dot.style.cssText = `
      position: fixed;
      left: 200px; top: 200px;
      width: 18px; height: 18px;
      border-radius: 50%;
      background: red;
      z-index: 2147483647;
      pointer-events: none;
      transform: translate(-50%, -50%);
      box-shadow: 0 0 0 4px rgba(255,0,0,0.35), 0 0 14px rgba(255,0,0,0.85);
    `;
    document.documentElement.appendChild(dot);
    if (!window.__pw_dot_follow_installed) {
      window.__pw_dot_follow_installed = true;
      window.addEventListener('mousemove', (e) => {
        const d = document.getElementById('__pw_dot');
        if (!d) return;
        d.style.left = e.clientX + 'px';
        d.style.top  = e.clientY + 'px';
      }, true);
      window.addEventListener('mousedown', (e) => {
        const ring = document.createElement('div');
        ring.style.cssText = `
          position: fixed;
          left:${e.clientX}px; top:${e.clientY}px;
          width: 16px; height: 16px;
          border: 3px solid red;
          border-radius: 50%;
          z-index: 2147483647;
          pointer-events: none;
          transform: translate(-50%, -50%);
          opacity: 0.9;
        `;
        document.documentElement.appendChild(ring);
        setTimeout(() => { try { ring.remove(); } catch(e) {} }, 550);
      }, true);
    }
    return true;
  } catch (e) {
    return false;
  }
})();
"""

# Border/highlight overlay (from Borderering-cursor.txt); __pw_highlight_element used from Python
HILITE_JS = r"""
((opts) => {
  try {
    const {
      borderColor,
      borderWidth,
      borderRadius,
      showLabel,
      lockOnClick,
      ignoreSelectors,
    } = opts || {};
    const oldBox = document.getElementById('__pw_hilite_box');
    if (oldBox) oldBox.remove();
    const oldLab = document.getElementById('__pw_hilite_label');
    if (oldLab) oldLab.remove();
    const box = document.createElement('div');
    box.id = '__pw_hilite_box';
    box.style.cssText = `
      position: fixed;
      left: 0; top: 0;
      width: 0; height: 0;
      border: ${borderWidth || 3}px solid ${borderColor || 'deepskyblue'};
      border-radius: ${borderRadius || 6}px;
      z-index: 2147483646;
      pointer-events: none;
      box-sizing: border-box;
      background: rgba(0, 191, 255, 0.06);
    `;
    document.documentElement.appendChild(box);
    let label = null;
    if (showLabel) {
      label = document.createElement('div');
      label.id = '__pw_hilite_label';
      label.style.cssText = `
        position: fixed;
        left: 0; top: 0;
        max-width: 70vw;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
        font-size: 12px;
        line-height: 1.2;
        color: white;
        background: rgba(0,0,0,0.78);
        padding: 4px 6px;
        border-radius: 6px;
        z-index: 2147483647;
        pointer-events: none;
        box-shadow: 0 6px 18px rgba(0,0,0,0.25);
      `;
      document.documentElement.appendChild(label);
    }
    const ignored = new Set(['__pw_dot', '__pw_hilite_box', '__pw_hilite_label']);
    function shouldIgnore(el) {
      if (!el) return true;
      if (ignored.has(el.id)) return true;
      if (ignoreSelectors && Array.isArray(ignoreSelectors)) {
        for (const sel of ignoreSelectors) {
          try {
            if (sel && el.matches && el.matches(sel)) return true;
          } catch (_) {}
        }
      }
      return false;
    }
    function describe(el) {
      if (!el) return '';
      let s = el.tagName ? el.tagName.toLowerCase() : 'element';
      if (el.id) s += `#${el.id}`;
      if (el.classList && el.classList.length) {
        const cls = Array.from(el.classList).slice(0, 3).join('.');
        if (cls) s += `.${cls}`;
      }
      const role = el.getAttribute && el.getAttribute('role');
      const aria = el.getAttribute && (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby'));
      if (role) s += ` [role=${role}]`;
      if (aria && typeof aria === 'string') s += ` [aria=${aria}]`;
      return s;
    }
    let locked = false;
    let last = null;
    let rafPending = false;
    let lastXY = { x: 0, y: 0 };
    function placeOverlay(el, x, y) {
      if (!el) {
        box.style.width = '0px';
        box.style.height = '0px';
        if (label) label.style.display = 'none';
        return;
      }
      const r = el.getBoundingClientRect();
      const w = Math.max(0, r.width);
      const h = Math.max(0, r.height);
      box.style.left = `${Math.round(r.left)}px`;
      box.style.top = `${Math.round(r.top)}px`;
      box.style.width = `${Math.round(w)}px`;
      box.style.height = `${Math.round(h)}px`;
      if (label) {
        label.style.display = 'block';
        label.textContent = describe(el);
        const pad = 10;
        let lx = (x || r.left) + pad;
        let ly = (y || r.top) + pad;
        lx = Math.min(Math.max(0, lx), window.innerWidth - 20);
        ly = Math.min(Math.max(0, ly), window.innerHeight - 20);
        label.style.left = `${Math.round(lx)}px`;
        label.style.top = `${Math.round(ly)}px`;
      }
    }
    function pickElementAt(x, y) {
      const prevDisplay = box.style.display;
      box.style.display = 'none';
      if (label) label.style.display = 'none';
      let el = document.elementFromPoint(x, y);
      box.style.display = prevDisplay;
      while (el && el.nodeType !== 1) el = el.parentElement;
      if (shouldIgnore(el)) return null;
      return el;
    }
    function onMove(e) {
      if (locked) return;
      lastXY = { x: e.clientX, y: e.clientY };
      if (rafPending) return;
      rafPending = true;
      requestAnimationFrame(() => {
        rafPending = false;
        const el = pickElementAt(lastXY.x, lastXY.y);
        last = el;
        placeOverlay(el, lastXY.x, lastXY.y);
      });
    }
    function onDown(e) {
      if (!lockOnClick) return;
      const el = pickElementAt(e.clientX, e.clientY);
      last = el;
      placeOverlay(el, e.clientX, e.clientY);
      locked = true;
    }
    window.__pw_highlight_element = (el, labelText) => {
      try {
        if (!el) return false;
        last = el;
        locked = true;
        placeOverlay(el, 20, 20);
        if (label && labelText) label.textContent = String(labelText);
        return true;
      } catch (_) {
        return false;
      }
    };
    window.__pw_highlight_unlock = () => { locked = false; };
    if (!window.__pw_hilite_installed) {
      window.__pw_hilite_installed = true;
      window.addEventListener('mousemove', onMove, true);
      window.addEventListener('mousedown', onDown, true);
      window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') locked = false;
      }, true);
    }
    window.__pw_hilite_opts = opts;
    return true;
  } catch (e) {
    return false;
  }
})
"""


def highlight_locator(locator) -> None:
    """Visually highlight an element by styling the DOM node (e.g. for consent buttons)."""
    try:
        locator.evaluate(r"""
        (node) => {
          node.style.outline = '4px solid red';
          node.style.outlineOffset = '2px';
          node.style.backgroundColor = 'yellow';
          node.style.boxShadow = '0 0 0 6px rgba(255,0,0,0.35)';
          node.style.transition = 'all 150ms ease-in-out';
        }
        """)
    except Exception:
        pass


def install_dot(page) -> None:
    page.evaluate(DOT_JS)
    try:
        page.mouse.move(200, 200, steps=1)
    except Exception:
        pass


def install_highlighter(
    page,
    *,
    border_color: str = "deepskyblue",
    border_width: int = 3,
    border_radius: int = 6,
    show_label: bool = False,
    lock_on_click: bool = False,
    ignore_selectors: Optional[List[str]] = None,
) -> None:
    opts = {
        "borderColor": border_color,
        "borderWidth": int(border_width),
        "borderRadius": int(border_radius),
        "showLabel": bool(show_label),
        "lockOnClick": bool(lock_on_click),
        "ignoreSelectors": ignore_selectors or [],
    }
    page.evaluate(HILITE_JS, opts)


def ensure_overlays_installed(page, show_label: bool = True) -> None:
    """Inject dot and highlighter overlays if not already present (e.g. after navigation)."""
    try:
        has_dot = page.evaluate("() => !!document.getElementById('__pw_dot')")
        if not has_dot:
            install_dot(page)
    except Exception:
        install_dot(page)
    try:
        has_hilite = page.evaluate("() => !!document.getElementById('__pw_hilite_box')")
        if not has_hilite:
            install_highlighter(page, show_label=show_label)
    except Exception:
        install_highlighter(page, show_label=show_label)


def highlight_element_for_agent(page, locator_or_handle, label_text: Optional[str] = None) -> bool:
    """Highlight a specific element via overlay (requires install_highlighter already run)."""
    try:
        if hasattr(locator_or_handle, "element_handle"):
            handle = locator_or_handle.element_handle(timeout=2000)
        else:
            handle = locator_or_handle
        if handle is None:
            return False
        return page.evaluate(
            "(el, labelText) => window.__pw_highlight_element && window.__pw_highlight_element(el, labelText)",
            handle,
            label_text or "",
        )
    except Exception:
        return False
