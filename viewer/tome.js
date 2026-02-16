/**
 * Tome — binary document renderer for the web.
 *
 * Parses .tome byte streams (see PROPOSAL.md) and draws to a <canvas>
 * using the MLModern family of fonts shipped as WOFF2.
 */

const Tome = (() => {
  // --- Opcodes (PROPOSAL.md §4.2) ---
  const OP = {
    NUL:        0x00,
    RIGHT:      0x01,
    DOWN:       0x02,
    MOVETO:     0x03,
    CR:         0x04,
    LF_DOWN:    0x05,
    FONT_DEF:   0x06,
    FONT:       0x07,
    SECTION:    0x08,
    TAB:        0x09,
    NEWLINE:    0x0A,
    PARA:       0x0B,
    LIST_ITEM:  0x0E,
    LINK_DEF:   0x0F,
    LINK_START: 0x10,
    LINK_END:   0x11,
    KERN:       0x12,
    LIGATURE:   0x13,
    RULE:       0x14,
    COLOR:      0x15,
    BG_COLOR:   0x16,
    IMAGE_DEF:  0x17,
    IMAGE:      0x18,
    META:       0x19,
    ANCHOR:     0x1A,
    PUSH:       0x1B,
    POP:        0x1C,
    EXTENSION:  0x1E,
    END:        0xFF,
  };

  // --- PrefixVarint decoder ---

  function decodePrefixVarint(bytes, offset) {
    const first = bytes[offset];
    if (first < 0x80) {
      return { value: first, bytesRead: 1 };
    }
    if (first < 0xC0) {
      const val = ((first & 0x3F) << 8) | bytes[offset + 1];
      return { value: val + 128, bytesRead: 2 };
    }
    if (first < 0xE0) {
      const val = ((first & 0x1F) << 16) | (bytes[offset + 1] << 8) | bytes[offset + 2];
      return { value: val + 16512, bytesRead: 3 };
    }
    if (first < 0xF0) {
      const val = ((first & 0x0F) << 24) | (bytes[offset + 1] << 16) |
                  (bytes[offset + 2] << 8) | bytes[offset + 3];
      return { value: val + 2113664, bytesRead: 4 };
    }
    if (first < 0xF8) {
      // 5 bytes: 3 bits + 32 bits
      const hi = (first & 0x07);
      const lo = (bytes[offset + 1] << 24) | (bytes[offset + 2] << 16) |
                 (bytes[offset + 3] << 8) | bytes[offset + 4];
      return { value: (hi * 0x100000000) + (lo >>> 0) + 270549120, bytesRead: 5 };
    }
    // Larger encodings (6-9 bytes) — unlikely in practice
    throw new Error(`PrefixVarint too large at offset ${offset}`);
  }

  function decodeSignedVarint(bytes, offset) {
    const r = decodePrefixVarint(bytes, offset);
    const zigzag = r.value;
    // Decode zigzag: (zigzag >>> 1) ^ -(zigzag & 1)
    const sign = zigzag & 1;
    const magnitude = Math.floor(zigzag / 2);
    r.value = sign ? -(magnitude + 1) : magnitude;
    return r;
  }

  function decodeString(bytes, offset) {
    const lenResult = decodePrefixVarint(bytes, offset);
    const len = lenResult.value;
    const start = offset + lenResult.bytesRead;
    const strBytes = bytes.subarray(start, start + len);
    const value = new TextDecoder().decode(strBytes);
    return { value, bytesRead: lenResult.bytesRead + len };
  }

  // --- UTF-8 helpers ---

  function utf8CharLength(byte) {
    if (byte < 0x80) return 1;
    if (byte < 0xC0) return 1; // continuation byte (shouldn't be lead)
    if (byte < 0xE0) return 2;
    if (byte < 0xF0) return 3;
    return 4;
  }

  function decodeUtf8Char(bytes, offset) {
    const len = utf8CharLength(bytes[offset]);
    const charBytes = bytes.subarray(offset, offset + len);
    const ch = new TextDecoder().decode(charBytes);
    return { ch, bytesRead: len };
  }

  // --- Font name → CSS font-family mapping ---

  const FONT_CSS = {
    'mlmr10':   '"MLModern", serif',
    'mlmri10':  '"MLModern", serif',
    'mlmbx10':  '"MLModern", serif',
    'mlmbxi10': '"MLModern", serif',
    'mlmtt10':  '"MLModern Mono", monospace',
  };

  const FONT_WEIGHT = {
    'mlmr10':   '400',
    'mlmri10':  '400',
    'mlmbx10':  '700',
    'mlmbxi10': '700',
    'mlmtt10':  '400',
  };

  const FONT_STYLE = {
    'mlmr10':   'normal',
    'mlmri10':  'italic',
    'mlmbx10':  'normal',
    'mlmbxi10': 'italic',
    'mlmtt10':  'normal',
  };

  function cssFontFor(fontName, sizeTu) {
    const sizePx = sizeTu / 64;
    const style = FONT_STYLE[fontName] || 'normal';
    const weight = FONT_WEIGHT[fontName] || '400';
    const family = FONT_CSS[fontName] || '"MLModern", serif';
    return { css: `${style} ${weight} ${sizePx}px ${family}`, sizePx };
  }

  // --- Renderer ---

  function render(canvas, arrayBuffer) {
    const bytes = new Uint8Array(arrayBuffer);
    if (bytes.length === 0) return;

    // Plain-text mode: first byte >= 0x20
    if (bytes[0] >= 0x20) {
      renderPlainText(canvas, bytes);
      return;
    }

    renderTypeset(canvas, bytes);
  }

  function renderPlainText(canvas, bytes) {
    const text = new TextDecoder().decode(bytes);
    const lines = text.split('\n');

    const dpr = window.devicePixelRatio || 1;
    const fontSize = 16;
    const lineHeight = 22;
    const margin = 50;

    const width = 550;
    const height = margin * 2 + lines.length * lineHeight;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = '#333';
    ctx.font = `${fontSize}px "MLModern Mono", monospace`;
    ctx.textBaseline = 'alphabetic';

    let y = margin + fontSize;
    for (const line of lines) {
      ctx.fillText(line, margin, y);
      y += lineHeight;
    }
  }

  function renderTypeset(canvas, bytes) {
    // First pass: scan META for width to size the canvas, and do a
    // quick scan for the max y to determine height.  We'll do a
    // two-pass approach: parse once to get dimensions, then draw.

    // Parse the document into a command list
    const commands = parse(bytes);

    // Determine canvas dimensions from metadata and commands
    let docWidth = 35200;  // default 550 CSS px
    let maxY = 0;
    let curY = 0;

    for (const cmd of commands) {
      if (cmd.type === 'meta' && cmd.key === 'width') {
        docWidth = parseInt(cmd.value, 10) || docWidth;
      }
      if (cmd.type === 'moveto') curY = cmd.y;
      if (cmd.type === 'down') curY += cmd.sv;
      if (cmd.type === 'lf_down') curY += cmd.v;
      if (curY > maxY) maxY = curY;
    }

    const widthPx = docWidth / 64;
    const heightPx = (maxY / 64) + 100;  // padding at bottom

    const dpr = window.devicePixelRatio || 1;
    canvas.width = widthPx * dpr;
    canvas.height = heightPx * dpr;
    canvas.style.width = widthPx + 'px';
    canvas.style.height = heightPx + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    // Background
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, widthPx, heightPx);

    // Execute commands
    const state = {
      x: 0,
      y: 0,
      color: '#333333',
      bgColor: '#ffffff',
      fontSlot: 0,
      fonts: {},          // slot → { name, sizeTu, css, sizePx }
      links: {},          // id → url
      linkRegions: [],    // { x, y, w, h, url }
      currentLink: null,  // id or null
      linkStartX: 0,
      linkStartY: 0,
      stack: [],
    };

    ctx.textBaseline = 'alphabetic';

    for (const cmd of commands) {
      executeCommand(ctx, state, cmd);
    }

    // Make links clickable
    if (state.linkRegions.length > 0) {
      canvas.style.cursor = 'default';
      canvas.onclick = (e) => {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        for (const region of state.linkRegions) {
          if (mx >= region.x && mx <= region.x + region.w &&
              my >= region.y && my <= region.y + region.h) {
            window.open(region.url, '_blank');
            return;
          }
        }
      };
      canvas.onmousemove = (e) => {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        let over = false;
        for (const region of state.linkRegions) {
          if (mx >= region.x && mx <= region.x + region.w &&
              my >= region.y && my <= region.y + region.h) {
            over = true;
            break;
          }
        }
        canvas.style.cursor = over ? 'pointer' : 'default';
      };
    }
  }

  // --- Parser: bytes → command list ---

  function parse(bytes) {
    const commands = [];
    let offset = 0;

    while (offset < bytes.length) {
      const byte = bytes[offset];

      if (byte === OP.END) {
        break;
      }

      // Printable ASCII or UTF-8 lead byte → character
      if (byte >= 0x20 && byte !== 0x7F) {
        const { ch, bytesRead } = decodeUtf8Char(bytes, offset);
        commands.push({ type: 'char', ch });
        offset += bytesRead;
        continue;
      }

      // UTF-8 continuation byte in lead position — shouldn't happen
      // but handle gracefully
      if (byte >= 0x80) {
        const { ch, bytesRead } = decodeUtf8Char(bytes, offset);
        commands.push({ type: 'char', ch });
        offset += bytesRead;
        continue;
      }

      // Opcodes
      offset++;  // consume the opcode byte

      switch (byte) {
        case OP.NUL:
        case 0x0D:    // CR ignored
        case 0x7F:    // DEL ignored
          break;

        case OP.RIGHT: {
          const r = decodeSignedVarint(bytes, offset);
          commands.push({ type: 'right', sv: r.value });
          offset += r.bytesRead;
          break;
        }

        case OP.DOWN: {
          const r = decodeSignedVarint(bytes, offset);
          commands.push({ type: 'down', sv: r.value });
          offset += r.bytesRead;
          break;
        }

        case OP.MOVETO: {
          const rx = decodeSignedVarint(bytes, offset);
          offset += rx.bytesRead;
          const ry = decodeSignedVarint(bytes, offset);
          offset += ry.bytesRead;
          commands.push({ type: 'moveto', x: rx.value, y: ry.value });
          break;
        }

        case OP.CR:
          commands.push({ type: 'cr' });
          break;

        case OP.LF_DOWN: {
          const r = decodePrefixVarint(bytes, offset);
          commands.push({ type: 'lf_down', v: r.value });
          offset += r.bytesRead;
          break;
        }

        case OP.FONT_DEF: {
          const slot = decodePrefixVarint(bytes, offset);
          offset += slot.bytesRead;
          const hashHi = decodePrefixVarint(bytes, offset);
          offset += hashHi.bytesRead;
          const hashLo = decodePrefixVarint(bytes, offset);
          offset += hashLo.bytesRead;
          const size = decodePrefixVarint(bytes, offset);
          offset += size.bytesRead;
          const name = decodeString(bytes, offset);
          offset += name.bytesRead;
          commands.push({
            type: 'font_def',
            slot: slot.value,
            hashHi: hashHi.value,
            hashLo: hashLo.value,
            size: size.value,
            name: name.value,
          });
          break;
        }

        case OP.FONT: {
          const r = decodePrefixVarint(bytes, offset);
          commands.push({ type: 'font', slot: r.value });
          offset += r.bytesRead;
          break;
        }

        case OP.SECTION: {
          const r = decodePrefixVarint(bytes, offset);
          commands.push({ type: 'section', level: r.value });
          offset += r.bytesRead;
          break;
        }

        case OP.TAB:
          commands.push({ type: 'tab' });
          break;

        case OP.NEWLINE:
          commands.push({ type: 'newline' });
          break;

        case OP.PARA:
          commands.push({ type: 'para' });
          break;

        case OP.LIST_ITEM: {
          const r = decodePrefixVarint(bytes, offset);
          commands.push({ type: 'list_item', depth: r.value });
          offset += r.bytesRead;
          break;
        }

        case OP.LINK_DEF: {
          const id = decodePrefixVarint(bytes, offset);
          offset += id.bytesRead;
          const url = decodeString(bytes, offset);
          offset += url.bytesRead;
          commands.push({ type: 'link_def', id: id.value, url: url.value });
          break;
        }

        case OP.LINK_START: {
          const r = decodePrefixVarint(bytes, offset);
          commands.push({ type: 'link_start', id: r.value });
          offset += r.bytesRead;
          break;
        }

        case OP.LINK_END:
          commands.push({ type: 'link_end' });
          break;

        case OP.KERN: {
          const r = decodeSignedVarint(bytes, offset);
          commands.push({ type: 'kern', sv: r.value });
          offset += r.bytesRead;
          break;
        }

        case OP.LIGATURE: {
          const glyph = decodePrefixVarint(bytes, offset);
          offset += glyph.bytesRead;
          const n = decodePrefixVarint(bytes, offset);
          offset += n.bytesRead;
          commands.push({ type: 'ligature', glyph: glyph.value, n: n.value });
          break;
        }

        case OP.RULE: {
          const w = decodePrefixVarint(bytes, offset);
          offset += w.bytesRead;
          const h = decodePrefixVarint(bytes, offset);
          offset += h.bytesRead;
          commands.push({ type: 'rule', w: w.value, h: h.value });
          break;
        }

        case OP.COLOR: {
          const r = decodePrefixVarint(bytes, offset);
          commands.push({ type: 'color', rgba: r.value });
          offset += r.bytesRead;
          break;
        }

        case OP.BG_COLOR: {
          const r = decodePrefixVarint(bytes, offset);
          commands.push({ type: 'bg_color', rgba: r.value });
          offset += r.bytesRead;
          break;
        }

        case OP.IMAGE_DEF: {
          const id = decodePrefixVarint(bytes, offset);
          offset += id.bytesRead;
          const w = decodePrefixVarint(bytes, offset);
          offset += w.bytesRead;
          const h = decodePrefixVarint(bytes, offset);
          offset += h.bytesRead;
          const url = decodeString(bytes, offset);
          offset += url.bytesRead;
          commands.push({ type: 'image_def', id: id.value, w: w.value, h: h.value, url: url.value });
          break;
        }

        case OP.IMAGE: {
          const r = decodePrefixVarint(bytes, offset);
          commands.push({ type: 'image', id: r.value });
          offset += r.bytesRead;
          break;
        }

        case OP.META: {
          const key = decodeString(bytes, offset);
          offset += key.bytesRead;
          const val = decodeString(bytes, offset);
          offset += val.bytesRead;
          commands.push({ type: 'meta', key: key.value, value: val.value });
          break;
        }

        case OP.ANCHOR: {
          const name = decodeString(bytes, offset);
          offset += name.bytesRead;
          commands.push({ type: 'anchor', name: name.value });
          break;
        }

        case OP.PUSH:
          commands.push({ type: 'push' });
          break;

        case OP.POP:
          commands.push({ type: 'pop' });
          break;

        case OP.EXTENSION: {
          const extType = decodePrefixVarint(bytes, offset);
          offset += extType.bytesRead;
          const extLen = decodePrefixVarint(bytes, offset);
          offset += extLen.bytesRead;
          offset += extLen.value;  // skip extension data
          break;
        }

        default:
          // Unknown opcode in 0x01-0x1F range — skip
          console.warn(`Unknown opcode 0x${byte.toString(16)} at offset ${offset - 1}`);
          break;
      }
    }

    return commands;
  }

  // --- Command executor ---

  function rgbaToCSS(rgba) {
    const r = (rgba >>> 24) & 0xFF;
    const g = (rgba >>> 16) & 0xFF;
    const b = (rgba >>> 8) & 0xFF;
    const a = rgba & 0xFF;
    if (a === 255) {
      return `rgb(${r},${g},${b})`;
    }
    return `rgba(${r},${g},${b},${(a / 255).toFixed(3)})`;
  }

  function tu(v) {
    // Convert tome units to CSS pixels
    return v / 64;
  }

  function applyFont(ctx, state) {
    const font = state.fonts[state.fontSlot];
    if (font) {
      ctx.font = font.css;
    }
  }

  function executeCommand(ctx, state, cmd) {
    switch (cmd.type) {
      case 'char': {
        const font = state.fonts[state.fontSlot];
        ctx.fillStyle = state.color;
        applyFont(ctx, state);
        const xPx = tu(state.x);
        const yPx = tu(state.y);
        ctx.fillText(cmd.ch, xPx, yPx);
        // Advance cursor by measured width
        const w = ctx.measureText(cmd.ch).width;
        state.x += w * 64;
        break;
      }

      case 'right':
        state.x += cmd.sv;
        break;

      case 'down':
        state.y += cmd.sv;
        break;

      case 'moveto':
        state.x = cmd.x;
        state.y = cmd.y;
        break;

      case 'cr':
        state.x = 0;
        break;

      case 'lf_down':
        state.x = 0;
        state.y += cmd.v;
        break;

      case 'font_def': {
        const fontInfo = cssFontFor(cmd.name, cmd.size);
        state.fonts[cmd.slot] = {
          name: cmd.name,
          sizeTu: cmd.size,
          css: fontInfo.css,
          sizePx: fontInfo.sizePx,
        };
        break;
      }

      case 'font':
        state.fontSlot = cmd.slot;
        applyFont(ctx, state);
        break;

      case 'section':
      case 'para':
      case 'tab':
      case 'newline':
      case 'list_item':
      case 'anchor':
        // Structural markers — no visual effect in this renderer
        break;

      case 'link_def':
        state.links[cmd.id] = cmd.url;
        break;

      case 'link_start':
        state.currentLink = cmd.id;
        state.linkStartX = tu(state.x);
        state.linkStartY = tu(state.y);
        break;

      case 'link_end': {
        if (state.currentLink !== null) {
          const font = state.fonts[state.fontSlot];
          const h = font ? font.sizePx : 16;
          const endX = tu(state.x);
          const startX = state.linkStartX;
          const startY = state.linkStartY;
          const url = state.links[state.currentLink] || '';
          state.linkRegions.push({
            x: startX,
            y: startY - h,
            w: endX - startX,
            h: h * 1.3,
            url,
          });
          // Draw underline
          ctx.save();
          ctx.strokeStyle = state.color;
          ctx.lineWidth = 0.8;
          ctx.beginPath();
          ctx.moveTo(startX, startY + 2);
          ctx.lineTo(endX, startY + 2);
          ctx.stroke();
          ctx.restore();
        }
        state.currentLink = null;
        break;
      }

      case 'kern':
        state.x += cmd.sv;
        break;

      case 'rule':
        ctx.fillStyle = state.color;
        ctx.fillRect(tu(state.x), tu(state.y), tu(cmd.w), Math.max(tu(cmd.h), 0.5));
        state.x += cmd.w;
        break;

      case 'color':
        state.color = rgbaToCSS(cmd.rgba);
        break;

      case 'bg_color':
        state.bgColor = rgbaToCSS(cmd.rgba);
        break;

      case 'push':
        state.stack.push({
          x: state.x,
          y: state.y,
          color: state.color,
          fontSlot: state.fontSlot,
        });
        break;

      case 'pop': {
        const saved = state.stack.pop();
        if (saved) {
          state.x = saved.x;
          state.y = saved.y;
          state.color = saved.color;
          state.fontSlot = saved.fontSlot;
          applyFont(ctx, state);
        }
        break;
      }

      case 'meta':
        // Metadata handled in sizing pass; could display title
        break;

      case 'image_def':
      case 'image':
        // Image support not yet implemented
        break;
    }
  }

  // --- Public API ---

  async function load(canvas, url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Failed to load ${url}: ${response.status}`);
    const buffer = await response.arrayBuffer();
    render(canvas, buffer);
  }

  return { render, load, parse };
})();
