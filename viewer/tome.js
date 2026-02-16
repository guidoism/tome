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

  const OP_NAMES = {};
  for (const [name, code] of Object.entries(OP)) OP_NAMES[code] = name;

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
      const hi = (first & 0x07);
      const lo = (bytes[offset + 1] << 24) | (bytes[offset + 2] << 16) |
                 (bytes[offset + 3] << 8) | bytes[offset + 4];
      return { value: (hi * 0x100000000) + (lo >>> 0) + 270549120, bytesRead: 5 };
    }
    throw new Error(`PrefixVarint too large at offset ${offset}`);
  }

  function decodeSignedVarint(bytes, offset) {
    const r = decodePrefixVarint(bytes, offset);
    const zigzag = r.value;
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
    if (byte < 0xC0) return 1;
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
    return { css: `${style} ${weight} ${sizePx}px ${family}`, sizePx, style, weight, family };
  }

  // --- Renderer ---

  /**
   * Render a .tome buffer to a canvas.
   * Returns { textPlacements, linkRegions, links } for building overlays.
   */
  function render(canvas, arrayBuffer) {
    const bytes = new Uint8Array(arrayBuffer);
    if (bytes.length === 0) return { textPlacements: [], linkRegions: [], links: {} };

    if (bytes[0] >= 0x20) {
      return renderPlainText(canvas, bytes);
    }

    return renderTypeset(canvas, bytes);
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
    const fontCSS = `${fontSize}px "MLModern Mono", monospace`;
    ctx.font = fontCSS;
    ctx.textBaseline = 'alphabetic';

    const textPlacements = [];
    let y = margin + fontSize;
    for (const line of lines) {
      ctx.fillText(line, margin, y);
      if (line.length > 0) {
        textPlacements.push({
          text: line, xPx: margin, yPx: y, css: fontCSS, sizePx: fontSize,
          style: 'normal', weight: '400', family: '"MLModern Mono", monospace',
        });
      }
      y += lineHeight;
    }

    return { textPlacements, linkRegions: [], links: {} };
  }

  function renderTypeset(canvas, bytes) {
    const commands = parse(bytes);

    // Determine canvas dimensions
    let docWidth = 35200;
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
    const heightPx = (maxY / 64) + 100;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = widthPx * dpr;
    canvas.height = heightPx * dpr;
    canvas.style.width = widthPx + 'px';
    canvas.style.height = heightPx + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, widthPx, heightPx);

    const state = {
      x: 0, y: 0,
      color: '#333333',
      bgColor: '#ffffff',
      fontSlot: 0,
      fonts: {},
      links: {},
      linkRegions: [],
      currentLink: null,
      linkStartX: 0, linkStartY: 0,
      stack: [],
      textPlacements: [],
    };

    ctx.textBaseline = 'alphabetic';

    for (const cmd of commands) {
      executeCommand(ctx, state, cmd);
    }

    return {
      textPlacements: state.textPlacements,
      linkRegions: state.linkRegions,
      links: state.links,
    };
  }

  // --- Parser ---

  function parse(bytes) {
    const commands = [];
    let offset = 0;

    while (offset < bytes.length) {
      const byte = bytes[offset];
      if (byte === OP.END) break;

      if (byte >= 0x20 && byte !== 0x7F) {
        const { ch, bytesRead } = decodeUtf8Char(bytes, offset);
        commands.push({ type: 'char', ch });
        offset += bytesRead;
        continue;
      }
      if (byte >= 0x80) {
        const { ch, bytesRead } = decodeUtf8Char(bytes, offset);
        commands.push({ type: 'char', ch });
        offset += bytesRead;
        continue;
      }

      offset++;

      switch (byte) {
        case OP.NUL: case 0x0D: case 0x7F: break;

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
          const slot = decodePrefixVarint(bytes, offset); offset += slot.bytesRead;
          const hashHi = decodePrefixVarint(bytes, offset); offset += hashHi.bytesRead;
          const hashLo = decodePrefixVarint(bytes, offset); offset += hashLo.bytesRead;
          const size = decodePrefixVarint(bytes, offset); offset += size.bytesRead;
          const name = decodeString(bytes, offset); offset += name.bytesRead;
          commands.push({ type: 'font_def', slot: slot.value, hashHi: hashHi.value,
            hashLo: hashLo.value, size: size.value, name: name.value });
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
        case OP.TAB: commands.push({ type: 'tab' }); break;
        case OP.NEWLINE: commands.push({ type: 'newline' }); break;
        case OP.PARA: commands.push({ type: 'para' }); break;
        case OP.LIST_ITEM: {
          const r = decodePrefixVarint(bytes, offset);
          commands.push({ type: 'list_item', depth: r.value });
          offset += r.bytesRead;
          break;
        }
        case OP.LINK_DEF: {
          const id = decodePrefixVarint(bytes, offset); offset += id.bytesRead;
          const url = decodeString(bytes, offset); offset += url.bytesRead;
          commands.push({ type: 'link_def', id: id.value, url: url.value });
          break;
        }
        case OP.LINK_START: {
          const r = decodePrefixVarint(bytes, offset);
          commands.push({ type: 'link_start', id: r.value });
          offset += r.bytesRead;
          break;
        }
        case OP.LINK_END: commands.push({ type: 'link_end' }); break;
        case OP.KERN: {
          const r = decodeSignedVarint(bytes, offset);
          commands.push({ type: 'kern', sv: r.value });
          offset += r.bytesRead;
          break;
        }
        case OP.LIGATURE: {
          const glyph = decodePrefixVarint(bytes, offset); offset += glyph.bytesRead;
          const n = decodePrefixVarint(bytes, offset); offset += n.bytesRead;
          commands.push({ type: 'ligature', glyph: glyph.value, n: n.value });
          break;
        }
        case OP.RULE: {
          const w = decodePrefixVarint(bytes, offset); offset += w.bytesRead;
          const h = decodePrefixVarint(bytes, offset); offset += h.bytesRead;
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
          const id = decodePrefixVarint(bytes, offset); offset += id.bytesRead;
          const w = decodePrefixVarint(bytes, offset); offset += w.bytesRead;
          const h = decodePrefixVarint(bytes, offset); offset += h.bytesRead;
          const url = decodeString(bytes, offset); offset += url.bytesRead;
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
          const key = decodeString(bytes, offset); offset += key.bytesRead;
          const val = decodeString(bytes, offset); offset += val.bytesRead;
          commands.push({ type: 'meta', key: key.value, value: val.value });
          break;
        }
        case OP.ANCHOR: {
          const name = decodeString(bytes, offset); offset += name.bytesRead;
          commands.push({ type: 'anchor', name: name.value });
          break;
        }
        case OP.PUSH: commands.push({ type: 'push' }); break;
        case OP.POP: commands.push({ type: 'pop' }); break;
        case OP.EXTENSION: {
          const extType = decodePrefixVarint(bytes, offset); offset += extType.bytesRead;
          const extLen = decodePrefixVarint(bytes, offset); offset += extLen.bytesRead;
          offset += extLen.value;
          break;
        }
        default:
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
    if (a === 255) return `rgb(${r},${g},${b})`;
    return `rgba(${r},${g},${b},${(a / 255).toFixed(3)})`;
  }

  function tu(v) { return v / 64; }

  function applyFont(ctx, state) {
    const font = state.fonts[state.fontSlot];
    if (font) ctx.font = font.css;
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
        const w = ctx.measureText(cmd.ch).width;
        state.x += w * 64;
        // Record for text overlay
        if (font) {
          state.textPlacements.push({
            ch: cmd.ch, xPx, yPx,
            css: font.css, sizePx: font.sizePx,
            style: font.style, weight: font.weight, family: font.family,
          });
        }
        break;
      }
      case 'right': state.x += cmd.sv; break;
      case 'down': state.y += cmd.sv; break;
      case 'moveto': state.x = cmd.x; state.y = cmd.y; break;
      case 'cr': state.x = 0; break;
      case 'lf_down': state.x = 0; state.y += cmd.v; break;
      case 'font_def': {
        const fi = cssFontFor(cmd.name, cmd.size);
        state.fonts[cmd.slot] = {
          name: cmd.name, sizeTu: cmd.size,
          css: fi.css, sizePx: fi.sizePx,
          style: fi.style, weight: fi.weight, family: fi.family,
        };
        break;
      }
      case 'font':
        state.fontSlot = cmd.slot;
        applyFont(ctx, state);
        break;
      case 'section': case 'para': case 'tab': case 'newline':
      case 'list_item': case 'anchor':
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
            x: startX, y: startY - h,
            w: endX - startX, h: h * 1.3, url,
          });
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
      case 'kern': state.x += cmd.sv; break;
      case 'rule':
        ctx.fillStyle = state.color;
        ctx.fillRect(tu(state.x), tu(state.y), tu(cmd.w), Math.max(tu(cmd.h), 0.5));
        state.x += cmd.w;
        break;
      case 'color': state.color = rgbaToCSS(cmd.rgba); break;
      case 'bg_color': state.bgColor = rgbaToCSS(cmd.rgba); break;
      case 'push':
        state.stack.push({ x: state.x, y: state.y, color: state.color, fontSlot: state.fontSlot });
        break;
      case 'pop': {
        const saved = state.stack.pop();
        if (saved) {
          state.x = saved.x; state.y = saved.y;
          state.color = saved.color; state.fontSlot = saved.fontSlot;
          applyFont(ctx, state);
        }
        break;
      }
      case 'meta': case 'image_def': case 'image': break;
    }
  }

  // --- Hex dump annotator ---

  /**
   * Annotate each byte in the stream with its semantic role.
   * Returns an array of { role, label? } per byte.
   */
  function annotateBytes(bytes) {
    const ann = new Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) ann[i] = { role: 'unknown' };

    function markVarint(offset, role) {
      const r = decodePrefixVarint(bytes, offset);
      for (let i = 0; i < r.bytesRead; i++) ann[offset + i].role = role;
      return r.bytesRead;
    }

    function markSignedVarint(offset, role) {
      const r = decodeSignedVarint(bytes, offset);
      // bytesRead is on the underlying PrefixVarint
      const pr = decodePrefixVarint(bytes, offset);
      for (let i = 0; i < pr.bytesRead; i++) ann[offset + i].role = role;
      return pr.bytesRead;
    }

    function markString(offset) {
      const lenR = decodePrefixVarint(bytes, offset);
      for (let i = 0; i < lenR.bytesRead; i++) ann[offset + i].role = 'strlen';
      const dataStart = offset + lenR.bytesRead;
      for (let i = 0; i < lenR.value; i++) ann[dataStart + i].role = 'strdata';
      return lenR.bytesRead + lenR.value;
    }

    let offset = 0;
    while (offset < bytes.length) {
      const byte = bytes[offset];

      if (byte === OP.END) {
        ann[offset].role = 'end';
        ann[offset].label = 'END';
        break;
      }

      // Text character
      if (byte >= 0x20 && byte !== 0x7F) {
        const len = utf8CharLength(byte);
        for (let i = 0; i < len; i++) ann[offset + i].role = 'text';
        offset += len;
        continue;
      }
      if (byte >= 0x80) {
        const len = utf8CharLength(byte);
        for (let i = 0; i < len; i++) ann[offset + i].role = 'text';
        offset += len;
        continue;
      }

      // Opcode
      ann[offset].role = 'opcode';
      ann[offset].label = OP_NAMES[byte] || `0x${byte.toString(16)}`;
      offset++;

      switch (byte) {
        case OP.NUL: case 0x0D: case 0x7F: break;
        case OP.RIGHT: case OP.DOWN: case OP.KERN:
          offset += markSignedVarint(offset, 'param');
          break;
        case OP.MOVETO:
          offset += markSignedVarint(offset, 'param');
          offset += markSignedVarint(offset, 'param');
          break;
        case OP.CR: case OP.PARA: case OP.TAB: case OP.NEWLINE:
        case OP.LINK_END: case OP.PUSH: case OP.POP:
          break;
        case OP.LF_DOWN: case OP.FONT: case OP.SECTION:
        case OP.LIST_ITEM: case OP.IMAGE:
          offset += markVarint(offset, 'param');
          break;
        case OP.LINK_START:
          offset += markVarint(offset, 'param');
          break;
        case OP.COLOR: case OP.BG_COLOR:
          offset += markVarint(offset, 'param');
          break;
        case OP.FONT_DEF:
          offset += markVarint(offset, 'param');   // slot
          offset += markVarint(offset, 'param');   // hash_hi
          offset += markVarint(offset, 'param');   // hash_lo
          offset += markVarint(offset, 'param');   // size
          offset += markString(offset);            // name
          break;
        case OP.LINK_DEF:
          offset += markVarint(offset, 'param');   // id
          offset += markString(offset);            // url
          break;
        case OP.LIGATURE:
          offset += markVarint(offset, 'param');   // glyph
          offset += markVarint(offset, 'param');   // n
          break;
        case OP.RULE:
          offset += markVarint(offset, 'param');   // w
          offset += markVarint(offset, 'param');   // h
          break;
        case OP.META:
          offset += markString(offset);            // key
          offset += markString(offset);            // value
          break;
        case OP.ANCHOR:
          offset += markString(offset);
          break;
        case OP.IMAGE_DEF:
          offset += markVarint(offset, 'param');   // id
          offset += markVarint(offset, 'param');   // w
          offset += markVarint(offset, 'param');   // h
          offset += markString(offset);            // url
          break;
        case OP.EXTENSION: {
          offset += markVarint(offset, 'param');   // type
          const lenR = decodePrefixVarint(bytes, offset);
          for (let i = 0; i < lenR.bytesRead; i++) ann[offset + i].role = 'param';
          offset += lenR.bytesRead;
          for (let i = 0; i < lenR.value; i++) ann[offset + i].role = 'strdata';
          offset += lenR.value;
          break;
        }
        default: break;
      }
    }
    return ann;
  }

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /**
   * Generate an HTML hex dump with color-coded bytes.
   */
  function hexDumpHTML(arrayBuffer) {
    const bytes = new Uint8Array(arrayBuffer);
    const ann = annotateBytes(bytes);
    const lines = [];

    for (let i = 0; i < bytes.length; i += 16) {
      let hex = '';
      let ascii = '';
      for (let j = 0; j < 16; j++) {
        if (i + j < bytes.length) {
          const b = bytes[i + j];
          const a = ann[i + j];
          const cls = a.role;
          const title = a.label ? ` title="${escapeHtml(a.label)}"` : '';
          hex += `<span class="hd-${cls}"${title}>${b.toString(16).padStart(2, '0')}</span>`;
          hex += j === 7 ? '  ' : ' ';
          const ch = (b >= 0x20 && b < 0x7F) ? escapeHtml(String.fromCharCode(b)) : '\u00b7';
          ascii += `<span class="hd-${cls}"${title}>${ch}</span>`;
        } else {
          hex += '   ';
          ascii += ' ';
        }
      }
      const off = i.toString(16).padStart(4, '0');
      lines.push(`<span class="hd-off">${off}</span>  ${hex} ${ascii}`);
    }
    return lines.join('\n');
  }

  // --- Disassembler (dvitype-style) ---

  function pxNote(tu) {
    return (tu / 64).toFixed(1) + 'px';
  }

  function truncStr(s, max) {
    if (s.length <= max) return s;
    return s.slice(0, max - 1) + '\u2026';
  }

  /**
   * Disassemble a .tome byte stream into human-readable instructions.
   * Returns HTML string.
   */
  function disassembleHTML(arrayBuffer) {
    const bytes = new Uint8Array(arrayBuffer);
    const lines = [];
    let offset = 0;

    // State tracking for richer annotations
    const fonts = {};   // slot → { name, size }
    let currentFont = null;

    function off() { return offset.toString(16).padStart(4, '0'); }

    function readVarint() {
      const r = decodePrefixVarint(bytes, offset);
      offset += r.bytesRead;
      return r.value;
    }
    function readSigned() {
      const pr = decodePrefixVarint(bytes, offset);
      const r = decodeSignedVarint(bytes, offset);
      offset += pr.bytesRead;
      return r.value;
    }
    function readStr() {
      const r = decodeString(bytes, offset);
      offset += r.bytesRead;
      return r.value;
    }

    function emit(startOffset, cls, opName, detail, note) {
      const offStr = startOffset.toString(16).padStart(4, '0');
      const nameHtml = `<span class="da-op">${escapeHtml(opName.padEnd(12))}</span>`;
      const detailHtml = detail ? `<span class="da-${cls}">${escapeHtml(detail)}</span>` : '';
      const noteHtml = note ? `  <span class="da-note">${escapeHtml(note)}</span>` : '';
      lines.push(`<span class="da-off">${offStr}</span>  ${nameHtml}${detailHtml}${noteHtml}`);
    }

    // Collect runs of text characters
    function flushText() {
      if (offset >= bytes.length) return;
      const byte = bytes[offset];
      if (byte < 0x20 || byte === 0x7F) return;
      if (byte < 0x20) return;

      const startOff = offset;
      let text = '';
      while (offset < bytes.length) {
        const b = bytes[offset];
        if (b < 0x20 || b === 0x7F || b === 0xFF) break;
        if (b >= 0x80 && b < 0xC0) break;
        const { ch, bytesRead } = decodeUtf8Char(bytes, offset);
        text += ch;
        offset += bytesRead;
      }
      if (text.length > 0) {
        const display = truncStr(text, 60);
        emit(startOff, 'str', 'text', `"${display}"`, `${text.length} chars`);
      }
    }

    while (offset < bytes.length) {
      const byte = bytes[offset];

      if (byte === OP.END) {
        emit(offset, 'op', 'END', '', '');
        break;
      }

      // Text characters — group into a single entry
      if (byte >= 0x20 && byte !== 0x7F) {
        flushText();
        continue;
      }
      if (byte >= 0x80) {
        flushText();
        continue;
      }

      // Opcode
      const instrOff = offset;
      offset++;

      switch (byte) {
        case OP.NUL:
          emit(instrOff, 'op', 'NUL', '', '');
          break;
        case 0x0D:
          emit(instrOff, 'op', 'CR_IGNORE', '', 'Windows line ending');
          break;

        case OP.RIGHT: {
          const sv = readSigned();
          emit(instrOff, 'param', 'RIGHT', `${sv}`, pxNote(sv));
          break;
        }
        case OP.DOWN: {
          const sv = readSigned();
          emit(instrOff, 'param', 'DOWN', `${sv}`, pxNote(sv));
          break;
        }
        case OP.MOVETO: {
          const x = readSigned();
          const y = readSigned();
          emit(instrOff, 'param', 'MOVETO', `x=${x} y=${y}`, `(${pxNote(x)}, ${pxNote(y)})`);
          break;
        }
        case OP.CR:
          emit(instrOff, 'op', 'CR', '', 'x := 0');
          break;
        case OP.LF_DOWN: {
          const v = readVarint();
          emit(instrOff, 'param', 'LF_DOWN', `${v}`, `CR + down ${pxNote(v)}`);
          break;
        }

        case OP.FONT_DEF: {
          const slot = readVarint();
          const hashHi = readVarint();
          const hashLo = readVarint();
          const size = readVarint();
          const name = readStr();
          fonts[slot] = { name, size };
          emit(instrOff, 'str', 'FONT_DEF', `slot=${slot} size=${size} "${name}"`,
               `${pxNote(size)} hash=${hashHi}:${hashLo}`);
          break;
        }
        case OP.FONT: {
          const slot = readVarint();
          const f = fonts[slot];
          currentFont = f || null;
          const note = f ? `current font is ${f.name}` : '';
          emit(instrOff, 'param', 'FONT', `slot=${slot}`, note);
          break;
        }

        case OP.SECTION: {
          const level = readVarint();
          emit(instrOff, 'param', 'SECTION', `level=${level}`, `h${level}`);
          break;
        }
        case OP.TAB:
          emit(instrOff, 'op', 'TAB', '', '');
          break;
        case OP.NEWLINE:
          emit(instrOff, 'op', 'NEWLINE', '', '');
          break;
        case OP.PARA:
          emit(instrOff, 'op', 'PARA', '', 'paragraph boundary');
          break;
        case OP.LIST_ITEM: {
          const depth = readVarint();
          emit(instrOff, 'param', 'LIST_ITEM', `depth=${depth}`, '');
          break;
        }

        case OP.LINK_DEF: {
          const id = readVarint();
          const url = readStr();
          emit(instrOff, 'str', 'LINK_DEF', `id=${id} "${truncStr(url, 50)}"`, '');
          break;
        }
        case OP.LINK_START: {
          const id = readVarint();
          emit(instrOff, 'param', 'LINK_START', `id=${id}`, '');
          break;
        }
        case OP.LINK_END:
          emit(instrOff, 'op', 'LINK_END', '', '');
          break;

        case OP.KERN: {
          const sv = readSigned();
          emit(instrOff, 'param', 'KERN', `${sv}`, pxNote(sv));
          break;
        }
        case OP.LIGATURE: {
          const glyph = readVarint();
          const n = readVarint();
          emit(instrOff, 'param', 'LIGATURE', `glyph=${glyph} n=${n}`, '');
          break;
        }
        case OP.RULE: {
          const w = readVarint();
          const h = readVarint();
          emit(instrOff, 'param', 'RULE', `w=${w} h=${h}`, `${pxNote(w)} \u00d7 ${pxNote(h)}`);
          break;
        }

        case OP.COLOR: {
          const rgba = readVarint();
          const hex = '#' + (rgba >>> 0).toString(16).padStart(8, '0');
          emit(instrOff, 'param', 'COLOR', hex, '');
          break;
        }
        case OP.BG_COLOR: {
          const rgba = readVarint();
          const hex = '#' + (rgba >>> 0).toString(16).padStart(8, '0');
          emit(instrOff, 'param', 'BG_COLOR', hex, '');
          break;
        }

        case OP.IMAGE_DEF: {
          const id = readVarint();
          const w = readVarint();
          const h = readVarint();
          const url = readStr();
          emit(instrOff, 'str', 'IMAGE_DEF', `id=${id} ${w}\u00d7${h} "${truncStr(url, 40)}"`, '');
          break;
        }
        case OP.IMAGE: {
          const id = readVarint();
          emit(instrOff, 'param', 'IMAGE', `id=${id}`, '');
          break;
        }

        case OP.META: {
          const key = readStr();
          const val = readStr();
          emit(instrOff, 'str', 'META', `"${key}" "${truncStr(val, 50)}"`, '');
          break;
        }
        case OP.ANCHOR: {
          const name = readStr();
          emit(instrOff, 'str', 'ANCHOR', `"${name}"`, '');
          break;
        }

        case OP.PUSH:
          emit(instrOff, 'op', 'PUSH', '', 'save state');
          break;
        case OP.POP:
          emit(instrOff, 'op', 'POP', '', 'restore state');
          break;

        case OP.EXTENSION: {
          const extType = readVarint();
          const extLen = readVarint();
          offset += extLen;
          emit(instrOff, 'param', 'EXTENSION', `type=${extType} len=${extLen}`, '');
          break;
        }

        default:
          emit(instrOff, 'op', `0x${byte.toString(16)}`, '', 'unknown opcode');
          break;
      }
    }

    return lines.join('\n');
  }

  // --- Public API ---

  async function load(canvas, url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Failed to load ${url}: ${response.status}`);
    const buffer = await response.arrayBuffer();
    return { result: render(canvas, buffer), buffer };
  }

  return { render, load, parse, hexDumpHTML, disassembleHTML, annotateBytes };
})();
