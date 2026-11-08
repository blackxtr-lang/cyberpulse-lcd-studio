import os
import sys
import io
import time
import math
import json
import struct
import shutil
import colorsys
import re
import threading
import psutil
from PIL import Image, ImageDraw, ImageFont

# 🔒 SECURITY: Protect against Decompression Bomb (ImageBomb) attacks (max ~8K 7680x4320 = 33.1M pixels)
Image.MAX_IMAGE_PIXELS = 33_177_600

def _is_safe_local_file_path(path_str):
    """
    🔒 SECURITY: Blocks UNC network paths (\\\\server\\share, //server/share) and Windows device paths
    (\\\\.\\, \\\\?\\) to prevent NTLMv2 SMB hash leaks and device handle abuse from untrusted themes.
    """
    if not path_str or not isinstance(path_str, str):
        return False
    norm = path_str.strip()
    if not norm or any(ord(c) < 32 for c in norm):
        return False
    if norm.startswith('\\\\') or norm.startswith('//'):
        return False
    base = os.path.splitext(os.path.basename(norm))[0].upper()
    if base in {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
                'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}:
        return False
    return True

try:
    import cv2
    HAS_CV2 = True
except Exception as e:
    print("OpenCV note:", e)
    HAS_CV2 = False

# ==============================================================================
# 📦 ZERO-EXTRACT SINGLE-FILE THEME ENGINE (.cptheme)
# Layout: [RAW_MEDIA_BYTES (offset 0, media_len)] + [UTF8_JSON_BYTES (json_len)] + [24-BYTE FOOTER]
# Footer: struct '<8s4sQI' -> magic=b'CPTHM100', media_type=b'VID0'|b'IMG0'|b'NON0', media_len, json_len
# OpenCV VideoCapture reads MP4 directly from offset 0 with 0ms extraction overhead!
# ==============================================================================
CPTHEME_MAGIC = b'CPTHM100'
CPTHEME_FOOTER_FMT = '<8s4sQI'
CPTHEME_FOOTER_SIZE = 24
CPTHEME_MAX_MEDIA_LEN = 256 * 1024 * 1024  # 🔒 256 MB max embedded media
CPTHEME_MAX_JSON_LEN = 4 * 1024 * 1024     # 🔒 4 MB max JSON metadata
_CPTHEME_FOOTER_CACHE = {}

def read_cptheme_footer(cptheme_path):
    """Reads and strictly validates the 24-byte footer of a .cptheme file in ~0.05ms (cached by mtime)."""
    try:
        if not _is_safe_local_file_path(cptheme_path) or not os.path.isfile(cptheme_path):
            return None
        st = os.stat(cptheme_path)
        if st.st_size < CPTHEME_FOOTER_SIZE or st.st_size > (CPTHEME_MAX_MEDIA_LEN + CPTHEME_MAX_JSON_LEN + CPTHEME_FOOTER_SIZE):
            return None
        cache_key = (cptheme_path, st.st_mtime_ns, st.st_size)
        if cache_key in _CPTHEME_FOOTER_CACHE:
            return _CPTHEME_FOOTER_CACHE[cache_key]

        with open(cptheme_path, 'rb') as f:
            f.seek(-CPTHEME_FOOTER_SIZE, os.SEEK_END)
            footer_bytes = f.read(CPTHEME_FOOTER_SIZE)
        magic, mtype_bytes, media_len, json_len = struct.unpack(CPTHEME_FOOTER_FMT, footer_bytes)
        if magic != CPTHEME_MAGIC:
            return None
        mtype_str = mtype_bytes.decode('ascii', errors='ignore').strip('\x00')
        if mtype_str not in ('VID0', 'IMG0', 'NON0'):
            return None
        media_len = int(media_len)
        json_len = int(json_len)
        # 🔒 SECURITY: Validate bounds and exact file size equality to prevent OOM / offset spoofing
        if media_len < 0 or media_len > CPTHEME_MAX_MEDIA_LEN:
            return None
        if json_len < 2 or json_len > CPTHEME_MAX_JSON_LEN:
            return None
        if media_len + json_len + CPTHEME_FOOTER_SIZE != st.st_size:
            return None
        res = (mtype_str, media_len, json_len)
        if len(_CPTHEME_FOOTER_CACHE) > 256:
            _CPTHEME_FOOTER_CACHE.clear()
        _CPTHEME_FOOTER_CACHE[cache_key] = res
        return res
    except Exception:
        return None

def read_cptheme_metadata(cptheme_path):
    """Reads only the JSON metadata from the end of a .cptheme file (~0.25ms)."""
    try:
        footer = read_cptheme_footer(cptheme_path)
        if not footer:
            return None
        mtype_str, media_len, json_len = footer
        with open(cptheme_path, 'rb') as f:
            f.seek(media_len, os.SEEK_SET)
            json_bytes = f.read(json_len)
        t_data = json.loads(json_bytes.decode('utf-8'))
        if isinstance(t_data, dict):
            abs_p = os.path.abspath(cptheme_path)
            if mtype_str in ('VID0', 'IMG0'):
                t_data['bg_path'] = abs_p
            else:
                # 🔒 SECURITY: Never allow NON0 packages to reference arbitrary external/UNC bg_path
                t_data['bg_path'] = None
            t_data['_cptheme_path'] = abs_p
            t_data['_cptheme_media_type'] = mtype_str
            return t_data
        return None
    except Exception as e:
        print("read_cptheme_metadata error:", e)
        return None

def read_cptheme_image(cptheme_path):
    """Reads embedded image bytes from offset 0 of a .cptheme file into a PIL Image."""
    try:
        footer = read_cptheme_footer(cptheme_path)
        if not footer or footer[0] != 'IMG0' or footer[1] <= 0 or footer[1] > 64 * 1024 * 1024:
            return None
        media_len = footer[1]
        with open(cptheme_path, 'rb') as f:
            img_bytes = f.read(media_len)
        return Image.open(io.BytesIO(img_bytes)).convert('RGB')
    except Exception as e:
        print("read_cptheme_image error:", e)
        return None

def write_cptheme_file(dst_path, theme_data, media_bytes=b'', media_type='NON0'):
    """Packs media_bytes (at offset 0) + theme_data JSON + 24-byte footer into a single .cptheme file."""
    tmp_path = dst_path + ".tmp"
    try:
        clean_data = dict(theme_data)
        clean_data.pop('_cptheme_path', None)
        clean_data.pop('_cptheme_media_type', None)
        if media_type in ('VID0', 'IMG0') and media_bytes:
            clean_data['bg_path'] = os.path.basename(dst_path)
            clean_data['is_baked'] = True

        json_bytes = json.dumps(clean_data, ensure_ascii=False, indent=2).encode('utf-8')
        mtype_bytes = media_type.encode('ascii')[:4].ljust(4, b'0')
        media_len = len(media_bytes) if media_bytes else 0
        json_len = len(json_bytes)
        footer = struct.pack(CPTHEME_FOOTER_FMT, CPTHEME_MAGIC, mtype_bytes, media_len, json_len)

        with open(tmp_path, 'wb') as f:
            if media_len > 0:
                f.write(media_bytes)
            f.write(json_bytes)
            f.write(footer)

        replaced = False
        last_err = None
        for attempt in range(4):
            try:
                os.replace(tmp_path, dst_path)
                replaced = True
                break
            except PermissionError as pe:
                last_err = pe
                import gc
                gc.collect()
                time.sleep(0.06 * (attempt + 1))
        if not replaced and last_err:
            raise last_err

        _CPTHEME_FOOTER_CACHE.clear()
        return True
    except Exception as e:
        print("write_cptheme_file error:", e)
        return False
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

def update_cptheme_metadata(cptheme_path, updated_theme_data):
    """Updates the JSON metadata inside an existing .cptheme file while preserving its embedded media."""
    try:
        footer = read_cptheme_footer(cptheme_path)
        if not footer:
            return False
        mtype_str, media_len, _ = footer
        media_bytes = b''
        if media_len > 0:
            with open(cptheme_path, 'rb') as f:
                media_bytes = f.read(media_len)
        return write_cptheme_file(cptheme_path, updated_theme_data, media_bytes=media_bytes, media_type=mtype_str)
    except Exception as e:
        print("update_cptheme_metadata error:", e)
        return False

def migrate_legacy_theme_folders(themes_dir):
    """Automatically converts any legacy theme folders in themes_dir into single .cptheme files."""
    if not os.path.exists(themes_dir):
        return 0
    migrated = 0
    backup_root = os.path.join(themes_dir, '_legacy_backup')
    for entry in sorted(os.listdir(themes_dir)):
        if entry.startswith('_'):
            continue
        full_p = os.path.join(themes_dir, entry)
        if not os.path.isdir(full_p):
            continue
        t_json_path = os.path.join(full_p, 'theme.json')
        if not os.path.exists(t_json_path):
            continue
        try:
            with open(t_json_path, 'r', encoding='utf-8') as f:
                t_data = json.load(f)
            t_data['name'] = entry

            media_bytes = b''
            media_type = 'NON0'
            bg_rel = t_data.get('bg_path', '')
            cand_files = []
            if bg_rel:
                cand_files.append(bg_rel if os.path.isabs(bg_rel) else os.path.join(full_p, bg_rel))
            cand_files.append(os.path.join(full_p, 'bg_baked.mp4'))
            cand_files.append(os.path.join(full_p, 'bg_baked.png'))

            for cf in cand_files:
                if cf and _is_safe_local_file_path(cf) and os.path.isfile(cf) and not os.path.islink(cf):
                    try:
                        if os.path.getsize(cf) > CPTHEME_MAX_MEDIA_LEN:
                            continue
                    except Exception:
                        continue
                    ext = os.path.splitext(cf)[1].lower()
                    with open(cf, 'rb') as mf:
                        media_bytes = mf.read()
                    if ext in ('.mp4', '.avi', '.mkv', '.mov', '.webm', '.gif'):
                        media_type = 'VID0'
                    elif ext in ('.png', '.jpg', '.jpeg', '.bmp', '.webp'):
                        media_type = 'IMG0'
                    break

            dst_cptheme = os.path.join(themes_dir, f"{entry}.cptheme")
            if write_cptheme_file(dst_cptheme, t_data, media_bytes=media_bytes, media_type=media_type):
                os.makedirs(backup_root, exist_ok=True)
                dst_backup = os.path.join(backup_root, entry)
                if os.path.exists(dst_backup):
                    shutil.rmtree(dst_backup, ignore_errors=True)
                shutil.move(full_p, dst_backup)
                migrated += 1
        except Exception as e:
            print(f"Migration note for '{entry}':", e)
    return migrated

# 🚀 Windows .NET C# DLL Integration for USB LCD Screen
HAS_HARDWARE_DRIVER = False
DLSDevice = None
# Safe Unicode print helper for Windows Turkish CP1254 environment
def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except Exception:
        try:
            clean_str = " ".join([str(a).encode('ascii', 'ignore').decode('ascii') for a in args])
            print(clean_str, **kwargs)
        except Exception:
            pass

try:
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    import clr
    import System

    if getattr(sys, 'frozen', False):
        dll_dir = os.path.dirname(os.path.abspath(sys.executable))
        bundle_dir = getattr(sys, '_MEIPASS', dll_dir)
    else:
        dll_dir = os.path.dirname(os.path.abspath(__file__))
        bundle_dir = dll_dir
    dll_path = os.path.abspath(os.path.join(dll_dir, "DLS_SDK.dll"))
    if not os.path.isfile(dll_path):
        dll_path = os.path.abspath(os.path.join(bundle_dir, "DLS_SDK.dll"))
    
    if os.path.isfile(dll_path):
        try:
            # 🔒 SECURITY: Load DLL by exact absolute path to prevent CWD/sys.path DLL hijacking
            clr.AddReference(dll_path)
        except Exception:
            try:
                with open(dll_path, "rb") as f:
                    dll_bytes = f.read(16 * 1024 * 1024)
                System.Reflection.Assembly.Load(dll_bytes)
            except Exception as ex_load:
                safe_print("Assembly byte load note:", ex_load)

        from DLS_SDK import DLSDevice, SerialPortHelper
        HAS_HARDWARE_DRIVER = True
        safe_print("[+] DLS_SDK.dll C# Assembly loaded successfully!")
    else:
        safe_print("[-] DLS_SDK.dll missing in directory:", dll_path)
except Exception as e:
    safe_print("C# Hardware Driver DLL load note:", e)

FONT_CACHE = {}

# Windows TTF Font Family Map: (regular, bold, italic, bold_italic)
WINDOWS_FONT_MAP = {
    'arial': ('arial.ttf', 'arialbd.ttf', 'ariali.ttf', 'arialbi.ttf'),
    'segoe ui': ('segoeui.ttf', 'segoeuib.ttf', 'segoeuii.ttf', 'segoeuiz.ttf'),
    'consolas': ('consola.ttf', 'consolab.ttf', 'consolai.ttf', 'consolaz.ttf'),
    'impact': ('impact.ttf', 'impact.ttf', 'impact.ttf', 'impact.ttf'),
    'times new roman': ('times.ttf', 'timesbd.ttf', 'timesi.ttf', 'timesbi.ttf'),
    'courier new': ('cour.ttf', 'courbd.ttf', 'couri.ttf', 'courbi.ttf'),
    'verdana': ('verdana.ttf', 'verdanab.ttf', 'verdanai.ttf', 'verdanaz.ttf'),
    'trebuchet ms': ('trebuc.ttf', 'trebucbd.ttf', 'trebucit.ttf', 'trebucbi.ttf'),
}

def get_custom_font(font_name='Arial', font_size=20, is_bold=False, is_italic=False):
    key = (str(font_name).lower(), int(font_size), bool(is_bold), bool(is_italic))
    if key in FONT_CACHE:
        return FONT_CACHE[key]

    fonts_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    fam_tuple = WINDOWS_FONT_MAP.get(str(font_name).lower().strip(), WINDOWS_FONT_MAP['arial'])
    if is_bold and is_italic:
        style_idx = 3
    elif is_italic:
        style_idx = 2
    elif is_bold:
        style_idx = 1
    else:
        style_idx = 0

    candidates = [fam_tuple[style_idx], fam_tuple[1 if is_bold else 0], fam_tuple[0], "arialbd.ttf" if is_bold else "arial.ttf", "arial.ttf"]
    for font_file in candidates:
        try:
            font_path = os.path.join(fonts_dir, font_file)
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, int(font_size))
                FONT_CACHE[key] = font
                return font
        except Exception:
            pass

    try:
        font = ImageFont.load_default()
        FONT_CACHE[key] = font
        return font
    except Exception:
        return None

def hex_to_rgb(hex_str, default=(255, 255, 255)):
    if not hex_str or not isinstance(hex_str, str):
        return default
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 6:
        try:
            return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))
        except ValueError:
            return default
    return default

def safe_int(val, default=0):
    try:
        if val is None:
            return default
        return int(float(val))
    except (ValueError, TypeError):
        return default

def draw_vector_icon(draw, icon_name, x, y, size=20, color=(255, 255, 255)):
    try:
        cx = x + size // 2
        cy = y + size // 2

        if icon_name == 'down':
            draw.line([(cx, y + 2), (cx, y + size - 6)], fill=color, width=3)
            draw.polygon([(cx - 5, y + size - 8), (cx + 5, y + size - 8), (cx, y + size - 2)], fill=color)
            draw.line([(x + 2, y + size - 2), (x + size - 2, y + size - 2)], fill=color, width=2)

        elif icon_name == 'up':
            draw.line([(cx, y + 6), (cx, y + size - 2)], fill=color, width=3)
            draw.polygon([(cx - 5, y + 8), (cx + 5, y + 8), (cx, y + 2)], fill=color)
            draw.line([(x + 2, y + size - 2), (x + size - 2, y + size - 2)], fill=color, width=2)

        elif icon_name == 'ping':
            bar_w = max(2, size // 5)
            spacing = 2
            for i in range(4):
                bh = int((size - 4) * ((i + 1) / 4.0))
                bx = x + (i * (bar_w + spacing)) + 2
                by = y + size - bh
                draw.rectangle([bx, by, bx + bar_w, y + size], fill=color if i < 3 else (100, 116, 139))

        elif icon_name == 'cpu':
            draw.rectangle([x + 4, y + 4, x + size - 4, y + size - 4], outline=color, width=2)
            draw.rectangle([x + 7, y + 7, x + size - 7, y + size - 7], fill=color)
            for i in range(3):
                px = x + 6 + (i * 4)
                draw.line([(px, y), (px, y + 3)], fill=color, width=2)
                draw.line([(px, y + size - 3), (px, y + size)], fill=color, width=2)

        elif icon_name == 'gpu':
            draw.rectangle([x + 2, y + 4, x + size - 2, y + size - 4], outline=color, width=2)
            draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], outline=color, width=2)
            draw.line([(x + size - 4, y + size - 4), (x + size - 1, y + size - 1)], fill=color, width=2)

        elif icon_name == 'ram':
            draw.rectangle([x + 2, y + 5, x + size - 2, y + size - 5], outline=color, width=2)
            for px in range(x + 5, x + size - 4, 3):
                draw.rectangle([px, y + size - 4, px + 1, y + size - 2], fill=color)

        elif icon_name == 'temp':
            draw.ellipse([cx - 4, y + size - 8, cx + 4, y + size], fill=color)
            draw.rectangle([cx - 2, y + 2, cx + 2, y + size - 5], outline=color, width=1)
            draw.rectangle([cx - 1, y + 6, cx + 1, y + size - 4], fill=color)

        elif icon_name in ['calendar', 'date', 'countdown']:
            draw.rectangle([x + 2, y + 4, x + size - 2, y + size - 2], outline=color, width=2)
            draw.rectangle([x + 2, y + 4, x + size - 2, y + 8], fill=color)
            # 2 top binder rings
            draw.line([(x + 5, y + 1), (x + 5, y + 5)], fill=color, width=2)
            draw.line([(x + size - 5, y + 1), (x + size - 5, y + 5)], fill=color, width=2)
            # Calendar grid dates
            for r in range(2):
                for c in range(3):
                    dx = x + 5 + (c * (size // 4))
                    dy = y + 10 + (r * (size // 4))
                    draw.rectangle([dx, dy, dx + 2, dy + 2], fill=color)

        elif icon_name in ['time', 'clock', 'uptime']:
            draw.ellipse([x + 2, y + 2, x + size - 2, y + size - 2], outline=color, width=2)
            draw.line([(cx, cy), (cx, y + 6)], fill=color, width=2)
            draw.line([(cx, cy), (x + size - 6, cy)], fill=color, width=2)

        elif icon_name == 'fan':
            draw.ellipse([x + 2, y + 2, x + size - 2, y + size - 2], outline=color, width=2)
            draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=color)
            draw.line([(cx, y + 3), (cx, y + size - 3)], fill=color, width=2)
            draw.line([(x + 3, cy), (x + size - 3, cy)], fill=color, width=2)

        elif icon_name == 'disk':
            draw.rectangle([x + 3, y + 3, x + size - 3, y + size - 3], outline=color, width=2)
            draw.ellipse([cx - 4, cy - 5, cx + 4, cy + 3], outline=color, width=2)
            draw.rectangle([x + 6, y + size - 6, x + size - 6, y + size - 4], fill=color)

        elif icon_name == 'freq':
            draw.line([(x + 2, cy), (x + 6, cy), (x + 9, y + 3), (x + 13, y + size - 3), (x + 16, cy), (x + size - 2, cy)], fill=color, width=2)

        else:
            draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=color)
    except Exception:
        pass

def get_dynamic_threshold_color(pct, el_config, default_rgb):
    t_low = safe_int(el_config.get('tLowPct'), 50)
    t_high = safe_int(el_config.get('tHighPct'), 80)
    
    col_low = hex_to_rgb(el_config.get('tLowColor'), (16, 185, 129))
    col_mid = hex_to_rgb(el_config.get('tMidColor'), (251, 191, 36))
    col_high = hex_to_rgb(el_config.get('tHighColor'), (239, 68, 68))

    if pct < t_low:
        return col_low
    elif pct < t_high:
        return col_mid
    else:
        return col_high

def draw_aligned_text(draw, font, text, rect_x, rect_y, rect_w, rect_h, fill, align='left', icon_name=None):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        icon_size = int(text_h * 1.1) if icon_name else 0
        total_w = text_w + (icon_size + 6 if icon_name else 0)

        if align == 'center':
            start_x = rect_x + max(2, (rect_w - total_w) / 2.0)
        elif align == 'right':
            start_x = max(rect_x + 2, rect_x + rect_w - total_w - 6)
        else:
            start_x = rect_x + 6

        y = rect_y + max(2, (rect_h - text_h) / 2.0)

        if icon_name:
            draw_vector_icon(draw, icon_name, int(start_x), int(y + 1), size=icon_size, color=fill)
            draw.text((int(start_x + icon_size + 6), y), text, fill=fill, font=font)
        else:
            draw.text((int(start_x), y), text, fill=fill, font=font)
    except Exception:
        pass

def draw_wrapped_text(draw, font, text, rect_x, rect_y, rect_w, rect_h, fill, line_spacing=2):
    try:
        words = text.split(' ')
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            try:
                bbox = font.getbbox(test_line)
                w = bbox[2] - bbox[0]
            except Exception:
                w = len(test_line) * 8

            if w <= rect_w:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
                    current_line = []
        if current_line:
            lines.append(' '.join(current_line))

        lines = lines[:3]
        
        try:
            bbox = font.getbbox("Ay")
            line_h = bbox[3] - bbox[1] + line_spacing
        except Exception:
            line_h = 16

        total_text_h = len(lines) * line_h
        start_y = rect_y + max(2, (rect_h - total_text_h) / 2.0)

        for i, line in enumerate(lines):
            ly = start_y + (i * line_h)
            if ly + line_h > rect_y + rect_h + 10:
                break
            draw.text((int(rect_x + 2), int(ly)), line, fill=fill, font=font)
    except Exception:
        pass

def draw_weather_vector_icon(draw, icon_key, x, y, size):
    try:
        cx = x + size // 2
        cy = y + size // 2
        r = size // 3

        if icon_key == 'sun':
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(251, 191, 36))
            for angle_deg in range(0, 360, 45):
                rad = math.radians(angle_deg)
                x1 = cx + int((r + 2) * math.cos(rad))
                y1 = cy + int((r + 2) * math.sin(rad))
                x2 = cx + int((r + 6) * math.cos(rad))
                y2 = cy + int((r + 6) * math.sin(rad))
                draw.line([(x1, y1), (x2, y2)], fill=(251, 191, 36), width=2)

        elif icon_key == 'partly_cloudy':
            draw.ellipse([cx - r + 3, cy - r - 2, cx + r + 3, cy + r - 2], fill=(251, 191, 36))
            draw.ellipse([cx - r - 3, cy - 2, cx + r - 3, cy + r + 3], fill=(226, 232, 240))
            draw.ellipse([cx - 2, cy - r + 2, cx + r, cy + r + 3], fill=(241, 245, 249))

        elif icon_key == 'rain':
            draw.ellipse([cx - r - 2, cy - r, cx + r + 2, cy + 2], fill=(148, 163, 184))
            draw.line([(cx - 5, cy + 5), (cx - 7, cy + 10)], fill=(56, 189, 248), width=2)
            draw.line([(cx, cy + 5), (cx - 2, cy + 10)], fill=(56, 189, 248), width=2)
            draw.line([(cx + 5, cy + 5), (cx + 3, cy + 10)], fill=(56, 189, 248), width=2)

        elif icon_key == 'snow':
            draw.line([(cx - r, cy), (cx + r, cy)], fill=(248, 250, 252), width=2)
            draw.line([(cx, cy - r), (cx, cy + r)], fill=(248, 250, 252), width=2)
            draw.line([(cx - r + 2, cy - r + 2), (cx + r - 2, cy + r - 2)], fill=(248, 250, 252), width=1)
            draw.line([(cx - r + 2, cy + r - 2), (cx + r - 2, cy - r + 2)], fill=(248, 250, 252), width=1)

        else:
            draw.ellipse([cx - r, cy - r // 2, cx + r, cy + r], fill=(203, 213, 225))
    except Exception:
        pass

class HardwareDriver:
    """
    ⚡ CYBERPULSE LCD Hardware Streamer:
    Interfaces with motherboard USB LCD Screen via DLS_SDK.dll C# Assembly.
    Supports auto-scan fallback across all COM ports (COM1 - COM32).
    """
    def __init__(self, width=320, height=1480):
        self.width = width
        self.height = height
        self.com_port = None
        self.is_connected = False
        self.ser = None
        self.dls = None
        self.send_data_mi = None

        self.last_rendered_frame = None
        self.latest_metrics = {}

        self.video_cap = None
        self.current_bg_path = None
        self.cached_bg_image = None
        self.cached_final_static_bg = None
        self.cached_static_key = None
        self._cached_overlay = None
        self._cached_overlay_key = None
        self._cached_base_img = None
        self._cached_base_key = None
        self._cached_cover_src = None
        self._cached_cover_size = None
        self._cached_cover_resized = None
        self._custom_image_cache = {}
        self.ram_video_frames = []
        self.ram_video_cache_key = None
        self.ram_frame_idx = 0
        self.last_video_frame_time = 0.0

        self.anim_angle = 0.0
        self.marquee_offset = 0.0
        self.flash_cycle = 0
        self._last_anim_time = time.perf_counter()

        self.render_lock = threading.RLock()
        self._is_sending = False

    def set_resolution(self, width, height):
        with self.render_lock:
            if self.width != width or self.height != height:
                self.width = width
                self.height = height
                self.reset_background_media()

    def reset_background_media(self):
        with self.render_lock:
            self.current_bg_path = None
            self.cached_bg_image = None
            self.cached_final_static_bg = None
            self.cached_static_key = None
            self._cached_overlay = None
            self._cached_overlay_key = None
            self._cached_base_img = None
            self._cached_base_key = None
            self._cached_cover_src = None
            self._cached_cover_size = None
            self._cached_cover_resized = None
            self.ram_video_frames = []
            self.ram_video_cache_key = None
            self.ram_frame_idx = 0
            if self.video_cap:
                try:
                    self.video_cap.release()
                except Exception as e:
                    print("Video cap release note:", e)
                self.video_cap = None

    def release_port_locks(self):
        try:
            current_pid = os.getpid()
            # 🔒 SECURITY: Only terminate exact known vendor LCD controller executables
            allowed_conflict_exes = {'lcd control.exe', 'soeyi.exe', 'soeyilcd.exe'}
            for p in psutil.process_iter(['pid', 'name']):
                try:
                    if p.info['pid'] != current_pid:
                        p_name = str(p.info.get('name') or '').strip().lower()
                        if p_name in allowed_conflict_exes:
                            print(f"Stopping conflicting background process {p.info['name']} (PID: {p.info['pid']})")
                            p.kill()
                            time.sleep(0.3)
                except Exception:
                    pass
        except Exception:
            pass

    @staticmethod
    def list_available_com_ports():
        """
        📋 Scans and returns all active serial ports on the PC.
        Identifies potential LCD screens (VID 0x33C3 or COM11).
        """
        import serial.tools.list_ports
        ports = []
        try:
            for p in serial.tools.list_ports.comports():
                desc = str(p.description or '').strip()
                desc_lower = desc.lower()
                # Skip pure bluetooth / standard serial ports
                if 'bluetooth' in desc_lower or 'standart seri' in desc_lower:
                    continue
                is_lcd = (p.vid == 0x33c3 and p.pid == 0xf101) or p.device == 'COM11'
                ports.append({
                    'device': p.device,
                    'description': desc,
                    'vid': hex(p.vid) if p.vid else None,
                    'pid': hex(p.pid) if p.pid else None,
                    'is_lcd': is_lcd
                })
        except Exception:
            pass
        return ports

    def auto_connect(self, target_port=None):
        """
        🎯 Connects to LCD Hardware on target_port or auto-detects COM11 (VID: 0x33C3, PID: 0xF101).
        Excludes Bluetooth and non-display serial ports.
        """
        if target_port == 'auto' or not target_port:
            target_port = None
        else:
            # 🔒 SECURITY: Strictly validate COM port identifier (COM1..COM256)
            port_str = str(target_port).strip().upper()
            if not re.match(r'^COM([1-9]|[1-9]\d|1\d\d|2[0-4]\d|25[0-6])$', port_str):
                target_port = None
            else:
                target_port = port_str

        # 1. If already cleanly connected to the desired port, reuse immediately!
        if self.is_connected:
            if target_port is None or self.com_port == target_port:
                if self.ser and getattr(self.ser, 'is_open', False):
                    return True
                if self.dls:
                    return True

        # 2. Clean up any lingering handles before reconnecting
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
        if self.dls:
            try:
                self.dls.CloseSerialPort()
            except Exception:
                pass
            self.dls = None
        self.is_connected = False

        import serial
        import serial.tools.list_ports

        self.release_port_locks()

        # Step 1: Detect exact USB LCD port (0x33C3 / 0xF101) or COM11
        lcd_ports = []
        if target_port:
            lcd_ports.append(target_port)

        try:
            for p in serial.tools.list_ports.comports():
                desc = str(p.description).lower()
                # Skip bluetooth and arduino ports
                if 'bluetooth' in desc or 'standart seri' in desc or p.vid == 0x2341:
                    continue
                if p.vid == 0x33c3 and p.pid == 0xf101:
                    lcd_ports.insert(0, p.device)
                elif p.device == 'COM11':
                    if 'COM11' not in lcd_ports:
                        lcd_ports.append('COM11')
                elif 'usb' in desc and p.vid not in [0x2341]:
                    if p.device not in lcd_ports:
                        lcd_ports.append(p.device)
        except Exception:
            pass

        if not target_port and 'COM11' not in lcd_ports:
            lcd_ports.insert(0, 'COM11')

        # Remove duplicates while preserving order
        ports_to_try = []
        if target_port and target_port not in ports_to_try:
            ports_to_try.append(target_port)
        for port in lcd_ports:
            if port not in ports_to_try:
                ports_to_try.append(port)

        safe_print(f"[*] Target USB LCD Ports to connect: {ports_to_try}")

        # Native PySerial Connection Engine
        for port in ports_to_try:
            try:
                ser_conn = serial.Serial(port, 115200, timeout=1)
                if ser_conn.is_open:
                    self.ser = ser_conn
                    self.com_port = port
                    self.is_connected = True
                    safe_print(f"[+] Connected cleanly to LCD Hardware on {self.com_port} via Native PySerial!")
                    return True
            except Exception as e:
                safe_print(f"[-] Could not open {port}: {e}")

        # C# DLS_SDK Assembly Fallback
        if HAS_HARDWARE_DRIVER:
            for port in ports_to_try:
                try:
                    dls_candidate = DLSDevice()
                    init_ok = dls_candidate.InitializeSerialPort(port)
                    if init_ok:
                        self.dls = dls_candidate
                        self.com_port = port
                        self.is_connected = True
                        flags = System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance
                        self.send_data_mi = self.dls.GetType().GetMethod('SendData', flags)
                        safe_print(f"[+] Connected cleanly to LCD Hardware on {self.com_port} via DLS_SDK!")
                        return True
                except Exception:
                    pass

        safe_print("[-] Could not connect to LCD screen. Ensure USB cable is plugged in.")
        self.is_connected = False
        return False

    def _prepare_ram_video_buffer(self, bg_path, w, h, crop_rect, fit_to_screen):
        try:
            cap = cv2.VideoCapture(bg_path)
            if not cap.isOpened():
                return False

            frames = []
            max_frames = 600

            while len(frames) < max_frames:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                fh, fw = frame.shape[:2]
                if fit_to_screen or not crop_rect:
                    resized_frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
                else:
                    x1, y1, x2, y2 = crop_rect
                    x1 = max(0, min(fw - 10, safe_int(x1, 0)))
                    y1 = max(0, min(fh - 10, safe_int(y1, 0)))
                    x2 = min(fw, max(x1 + 10, safe_int(x2, fw)))
                    y2 = min(fh, max(y1 + 10, safe_int(y2, fh)))

                    cropped = frame[y1:y2, x1:x2]
                    if cropped.size > 0:
                        resized_frame = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
                    else:
                        resized_frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)

                frame_rgb = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(frame_rgb)
                frames.append(pil_img)

            cap.release()

            if frames:
                self.ram_video_frames = frames
                self.ram_video_cache_key = (bg_path, w, h, tuple(crop_rect or []), fit_to_screen)
                self.ram_frame_idx = 0
                return True
        except Exception as e:
            print("RAM video buffer preparation note:", e)

        return False

    def load_background_frame(self, bg_path, w, h, crop_rect=None, fit_to_screen=False):
        w = max(64, min(4096, safe_int(w, self.width)))
        h = max(64, min(4096, safe_int(h, self.height)))
        if not bg_path or not _is_safe_local_file_path(bg_path):
            return Image.new('RGB', (w, h), (15, 23, 42))

        # Auto-resolve relative theme path if needed (confined to app directory)
        if not os.path.isabs(bg_path) and not os.path.exists(bg_path):
            app_dir = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            safe_rel = os.path.basename(bg_path)
            cand1 = os.path.join(app_dir, safe_rel)
            cand2 = os.path.join(app_dir, 'themes', safe_rel)
            if os.path.exists(cand1):
                bg_path = cand1
            elif os.path.exists(cand2):
                bg_path = cand2
            else:
                themes_dir = os.path.join(app_dir, 'themes')
                if os.path.exists(themes_dir):
                    for sub in os.listdir(themes_dir):
                        sub_cand = os.path.join(themes_dir, sub, safe_rel)
                        if os.path.exists(sub_cand):
                            bg_path = sub_cand
                            break

        if not _is_safe_local_file_path(bg_path) or not os.path.isfile(bg_path):
            return Image.new('RGB', (w, h), (15, 23, 42))

        ext = os.path.splitext(bg_path)[1].lower()
        cptheme_mtype = None
        if ext == '.cptheme':
            footer = read_cptheme_footer(bg_path)
            if footer:
                cptheme_mtype = footer[0]
            if cptheme_mtype == 'NON0' or footer is None:
                return Image.new('RGB', (w, h), (15, 23, 42))

        is_video_source = (ext in ['.mp4', '.avi', '.mkv', '.mov', '.gif', '.webm'] or cptheme_mtype == 'VID0') and HAS_CV2

        if is_video_source:
            try:
                if self.current_bg_path != bg_path or self.video_cap is None:
                    if self.video_cap:
                        try:
                            self.video_cap.release()
                        except Exception:
                            pass
                    self.video_cap = cv2.VideoCapture(bg_path)
                    self.current_bg_path = bg_path
                    self.video_fps = self.video_cap.get(cv2.CAP_PROP_FPS) or 24.0
                    self.last_video_frame_time = 0.0
                    self.cached_video_frame_pil = None

                if self.video_cap and self.video_cap.isOpened():
                    now = time.perf_counter()
                    # Frame rate throttling based on natural video fps
                    target_delay = 1.0 / max(10.0, min(60.0, getattr(self, 'video_fps', 24.0)))
                    if self.cached_video_frame_pil is not None and (now - self.last_video_frame_time) < target_delay:
                        return self.cached_video_frame_pil

                    ret, frame = self.video_cap.read()
                    if not ret or frame is None:
                        self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = self.video_cap.read()

                    if ret and frame is not None:
                        self.last_video_frame_time = now
                        fh, fw = frame.shape[:2]

                        if fw == w and fh == h and not crop_rect:
                            # ⚡ INSTANT PRE-BAKED FRAME: 0ms CROP, 0ms RESIZE, 0MB RAM OVERHEAD!
                            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            self.cached_video_frame_pil = Image.fromarray(frame_rgb)
                            return self.cached_video_frame_pil
                        else:
                            # Unbaked fallback
                            if fit_to_screen or not crop_rect:
                                resized_frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
                            else:
                                x1, y1, x2, y2 = crop_rect
                                x1 = max(0, min(fw - 10, safe_int(x1, 0)))
                                y1 = max(0, min(fh - 10, safe_int(y1, 0)))
                                x2 = min(fw, max(x1 + 10, safe_int(x2, fw)))
                                y2 = min(fh, max(y1 + 10, safe_int(y2, fh)))
                                cropped = frame[y1:y2, x1:x2]
                                resized_frame = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)

                            frame_rgb = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
                            self.cached_video_frame_pil = Image.fromarray(frame_rgb)
                            return self.cached_video_frame_pil
            except Exception as e:
                print("Video background frame error:", e)
                return Image.new('RGB', (w, h), (15, 23, 42))

        # Static Image Background (supports standard images and .cptheme IMG0)
        static_cache_key = (bg_path, w, h, tuple(crop_rect or []), fit_to_screen)
        if self.cached_static_key == static_cache_key and self.cached_final_static_bg is not None:
            return self.cached_final_static_bg.copy()

        if self.current_bg_path != bg_path or self.cached_bg_image is None:
            try:
                if cptheme_mtype == 'IMG0':
                    raw_img = read_cptheme_image(bg_path)
                    if raw_img is None:
                        return Image.new('RGB', (w, h), (15, 23, 42))
                else:
                    raw_img = Image.open(bg_path).convert('RGB')
                self.cached_bg_image = raw_img
                self.current_bg_path = bg_path
            except Exception as e:
                print("Error loading background image:", e)
                return Image.new('RGB', (w, h), (15, 23, 42))

        if self.cached_bg_image:
            try:
                if fit_to_screen or not crop_rect:
                    res = self.cached_bg_image.resize((w, h), Image.Resampling.BILINEAR)
                else:
                    img_w, img_h = self.cached_bg_image.size
                    x1, y1, x2, y2 = crop_rect
                    x1 = max(0, min(img_w - 10, safe_int(x1, 0)))
                    y1 = max(0, min(img_h - 10, safe_int(y1, 0)))
                    x2 = min(img_w, max(x1 + 10, safe_int(x2, img_w)))
                    y2 = min(img_h, max(y1 + 10, safe_int(y2, img_h)))

                    cropped = self.cached_bg_image.crop((x1, y1, x2, y2))
                    res = cropped.resize((w, h), Image.Resampling.BILINEAR)

                self.cached_final_static_bg = res
                self.cached_static_key = static_cache_key
                return res.copy()
            except Exception as e:
                print("Image crop resize note:", e)

        return Image.new('RGB', (w, h), (15, 23, 42))

    def render_theme_frame(self, theme_data, sensor_metrics, for_hardware=False):
        """
        ⚡ LIGHTNING FAST ULTRA-OPTIMIZED HARDWARE FRAME RENDERER (0% CPU LAG)
        Renders native 320x1480 hardware frame in < 1ms with smooth 60 FPS performance!
        """
        with self.render_lock:
            now_anim = time.perf_counter()
            dt = min(0.25, max(0.0, now_anim - getattr(self, '_last_anim_time', now_anim)))
            self._last_anim_time = now_anim
            self.anim_angle = (self.anim_angle + dt * 240.0) % 360.0
            self.marquee_offset = (self.marquee_offset + dt * 13.0) % 3000.0
            self.flash_cycle = int(now_anim * 20.0) % 20

            # 🔒 SECURITY: Clamp canvas dimensions to prevent OOM image allocation
            w = max(64, min(4096, safe_int(theme_data.get('width'), self.width)))
            h = max(64, min(4096, safe_int(theme_data.get('height'), self.height)))
            bg_path = theme_data.get('bg_path')
            if bg_path and not _is_safe_local_file_path(bg_path):
                bg_path = None
            crop_rect = theme_data.get('crop_rect')
            fit_to_screen = bool(theme_data.get('fit_to_screen', False))
            elements = theme_data.get('elements', [])
            if not isinstance(elements, list):
                elements = []
            elements = elements[:256]  # 🔒 Cap max widget count per theme
            selected_id = theme_data.get('selected_id')
            selected_ids = set(theme_data.get('selected_ids') or [])
            if selected_id:
                selected_ids.add(selected_id)

            ext = os.path.splitext(bg_path)[1].lower() if bg_path else ''
            if ext == '.cptheme':
                footer = read_cptheme_footer(bg_path)
                is_video_bg = (footer is not None and footer[0] == 'VID0') and HAS_CV2
            else:
                is_video_bg = ext in ['.mp4', '.avi', '.mkv', '.mov', '.gif', '.webm'] and HAS_CV2

            # Signature of element layout and darkening boxes
            el_sig = tuple(
                (safe_int(el.get('x'), 20), safe_int(el.get('y'), 60),
                 max(8, min(4096, safe_int(el.get('width'), 260))),
                 max(8, min(4096, safe_int(el.get('height'), 45))),
                 el.get('bgColor'), el.get('bgOpacity', 50), bool(el.get('hidden', False)),
                 safe_int(el.get('cornerRadius'), 0), bool(el.get('glowEnabled', False)), el.get('graphicColor'))
                for el in elements if isinstance(el, dict)
            )
            base_key = (bg_path, w, h, tuple(crop_rect or []), fit_to_screen, for_hardware, el_sig)

            # ⚡ OPTIMIZATION: If static background, reuse pre-composited base frame directly (0ms composite!)
            if not is_video_bg and self._cached_base_key == base_key and self._cached_base_img is not None:
                img = self._cached_base_img.copy()
            else:
                try:
                    img = self.load_background_frame(bg_path, w, h, crop_rect=crop_rect, fit_to_screen=fit_to_screen)
                except Exception as e:
                    img = Image.new('RGB', (w, h), (15, 23, 42))

                # Overlay caching for grid and element boxes
                overlay_key = (w, h, for_hardware, el_sig)
                if self._cached_overlay_key == overlay_key and self._cached_overlay is not None:
                    overlay = self._cached_overlay
                else:
                    overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
                    draw_ov = ImageDraw.Draw(overlay)

                    # Alignment Grid Lines
                    if not for_hardware:
                        for gx in range(40, w, 40):
                            draw_ov.line([(gx, 0), (gx, h)], fill=(255, 255, 255, 25), width=1)
                        for gy in range(40, h, 40):
                            draw_ov.line([(0, gy), (w, gy)], fill=(255, 255, 255, 25), width=1)

                    # Pass 1: Draw background darkening boxes (with rounded corners & neon glow halo)
                    for el in elements:
                        try:
                            if not isinstance(el, dict) or el.get('hidden', False):
                                continue
                            el_x = max(-4096, min(8192, safe_int(el.get('x'), 20)))
                            el_y = max(-4096, min(8192, safe_int(el.get('y'), 60)))
                            el_w = max(8, min(4096, safe_int(el.get('width'), 260)))
                            el_h = max(8, min(4096, safe_int(el.get('height'), 45)))
                            bg_rgb = hex_to_rgb(el.get('bgColor'), (15, 23, 42))
                            bg_opacity = int(safe_int(el.get('bgOpacity', 50)) * 2.55)
                            c_rad = max(0, min(el_w // 2, el_h // 2, safe_int(el.get('cornerRadius'), 0)))
                            glow_on = bool(el.get('glowEnabled', False))

                            if glow_on:
                                g_rgb = hex_to_rgb(el.get('graphicColor'), (56, 189, 248))
                                for g_step, g_alpha in [(6, 22), (4, 42), (2, 70)]:
                                    box_g = [el_x - g_step, el_y - g_step, el_x + el_w + g_step, el_y + el_h + g_step]
                                    if c_rad > 0:
                                        draw_ov.rounded_rectangle(box_g, radius=c_rad + g_step, outline=(g_rgb[0], g_rgb[1], g_rgb[2], g_alpha), width=2)
                                    else:
                                        draw_ov.rectangle(box_g, outline=(g_rgb[0], g_rgb[1], g_rgb[2], g_alpha), width=2)

                            if bg_opacity > 0:
                                if c_rad > 0:
                                    draw_ov.rounded_rectangle([el_x, el_y, el_x + el_w, el_y + el_h], radius=c_rad, fill=(bg_rgb[0], bg_rgb[1], bg_rgb[2], bg_opacity))
                                else:
                                    draw_ov.rectangle([el_x, el_y, el_x + el_w, el_y + el_h], fill=(bg_rgb[0], bg_rgb[1], bg_rgb[2], bg_opacity))
                        except Exception:
                            pass

                    self._cached_overlay = overlay
                    self._cached_overlay_key = overlay_key

                # Composite background darkening boxes with base image
                img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')

                # If static, cache this pre-composited base image for all subsequent frames
                if not is_video_bg:
                    self._cached_base_img = img.copy()
                    self._cached_base_key = base_key

            draw_img = ImageDraw.Draw(img, 'RGBA')

            # Pass 2: Draw crisp text & elements
            for el in elements:
                try:
                    if not isinstance(el, dict) or el.get('hidden', False):
                        continue
                    el_id = el.get('id')
                    el_x = max(-4096, min(8192, safe_int(el.get('x'), 20)))
                    el_y = max(-4096, min(8192, safe_int(el.get('y'), 60)))
                    el_w = max(8, min(4096, safe_int(el.get('width'), 260)))
                    el_h = max(8, min(4096, safe_int(el.get('height'), 45)))
                    c_rad = max(0, min(el_w // 2, el_h // 2, safe_int(el.get('cornerRadius'), 0)))
                    
                    auto_f_size = max(10, min(72, int(el_h * 0.48)))
                    lbl_f_size = max(6, min(200, safe_int(el.get('fontSize'), auto_f_size)))
                    val_f_size = max(6, min(200, safe_int(el.get('valueFontSize'), 24)))
                    
                    font_family = str(el.get('fontFamily', 'Arial'))
                    is_bold = bool(el.get('isBold', False))
                    is_italic = bool(el.get('isItalic', False))

                    lbl_font = get_custom_font(font_family, lbl_f_size, is_bold, is_italic)
                    val_font = get_custom_font(font_family, val_f_size, is_bold, is_italic)

                    text_align = str(el.get('textAlign', 'left'))
                    show_border = bool(el.get('showBorder', True))
                    dynamic_color_enabled = bool(el.get('dynamicColor', False))

                    s_id = el.get('sensorId') or 'cpu_temp'
                    val = str(sensor_metrics.get(s_id, '45%'))

                    bar_pct_override = None
                    vector_icon_name = None
                    if s_id == 'net_down':
                        vector_icon_name = 'down'
                        display_metric = val.replace('DL:', '').strip()
                    elif s_id == 'net_up':
                        vector_icon_name = 'up'
                        display_metric = val.replace('UL:', '').strip()
                    elif s_id == 'net_ping':
                        vector_icon_name = 'ping'
                        display_metric = val.replace('PING:', '').strip()
                    elif s_id == 'cpu_temp':
                        vector_icon_name = 'temp'
                        display_metric = val if '°C' in val else f"{val}°C"
                    elif s_id == 'gpu_temp':
                        vector_icon_name = 'temp'
                        display_metric = val if '°C' in val else f"{val}°C"
                    elif s_id == 'cpu_load':
                        vector_icon_name = 'cpu'
                        display_metric = val if '%' in val else f"{val}%"
                    elif s_id == 'gpu_load':
                        vector_icon_name = 'gpu'
                        display_metric = val if '%' in val else f"{val}%"
                    elif s_id == 'cpu_clock':
                        vector_icon_name = 'freq'
                        display_metric = val if 'MHz' in val else f"{val} MHz"
                    elif s_id == 'gpu_fan':
                        vector_icon_name = 'fan'
                        display_metric = val if ('%' in val or 'RPM' in val) else f"{val}%"
                    elif s_id == 'cpu_fan':
                        vector_icon_name = 'fan'
                        display_metric = val if ('RPM' in val or '%' in val) else f"{val} RPM"
                    elif s_id in ('ram_used', 'ram_load', 'ram_free', 'ram_free_load', 'ram_used_both', 'ram_free_both'):
                        vector_icon_name = 'ram'
                        ram_mode = str(el.get('ramDisplayMode') or '').strip()
                        if ram_mode not in ('used_gb', 'used_pct', 'used_both', 'free_gb', 'free_pct', 'free_both'):
                            default_mode_map = {
                                'ram_used': 'used_gb',
                                'ram_load': 'used_pct',
                                'ram_used_both': 'used_both',
                                'ram_free': 'free_gb',
                                'ram_free_load': 'free_pct',
                                'ram_free_both': 'free_both',
                            }
                            ram_mode = default_mode_map.get(s_id, 'used_gb')

                        raw_used_pct = sensor_metrics.get('_ram_used_pct_num')
                        if raw_used_pct is None:
                            try:
                                raw_rl = str(sensor_metrics.get('ram_load', '50%')).replace('%', '').strip()
                                raw_used_pct = max(0, min(100, int(round(float(raw_rl)))))
                            except Exception:
                                raw_used_pct = 50
                        used_pct_num = max(0, min(100, int(raw_used_pct)))
                        free_pct_num = max(0, min(100, int(sensor_metrics.get('_ram_free_pct_num', 100 - used_pct_num))))

                        if ram_mode == 'used_gb':
                            u_str = str(sensor_metrics.get('ram_used', val))
                            display_metric = u_str if 'GB' in u_str else f"{u_str} GB"
                            bar_pct_override = used_pct_num
                        elif ram_mode == 'used_pct':
                            display_metric = f"{used_pct_num}%"
                            bar_pct_override = used_pct_num
                        elif ram_mode == 'used_both':
                            u_str = str(sensor_metrics.get('ram_used', '16.0 GB'))
                            if 'GB' not in u_str:
                                u_str = f"{u_str} GB"
                            display_metric = str(sensor_metrics.get('ram_used_both') or f"{u_str} ({used_pct_num}%)")
                            bar_pct_override = used_pct_num
                        elif ram_mode == 'free_gb':
                            f_str = str(sensor_metrics.get('ram_free', '8.0 GB'))
                            display_metric = f_str if 'GB' in f_str else f"{f_str} GB"
                            bar_pct_override = free_pct_num
                        elif ram_mode == 'free_pct':
                            display_metric = f"{free_pct_num}%"
                            bar_pct_override = free_pct_num
                        elif ram_mode == 'free_both':
                            f_str = str(sensor_metrics.get('ram_free', '8.0 GB'))
                            if 'GB' not in f_str:
                                f_str = f"{f_str} GB"
                            display_metric = str(sensor_metrics.get('ram_free_both') or f"{f_str} ({free_pct_num}%)")
                            bar_pct_override = free_pct_num
                    elif s_id == 'disk_io':
                        vector_icon_name = 'disk'
                        display_metric = val if 'MB/s' in val else f"{val} MB/s"
                    elif s_id == 'system_uptime':
                        vector_icon_name = 'uptime'
                        display_metric = val
                    elif s_id == 'game_fps':
                        vector_icon_name = 'fps'
                        display_metric = val if 'FPS' in val else f"{val} FPS"
                    elif s_id in ['time_digital', 'date_full', 'date_day_tr']:
                        display_metric = val
                    else:
                        display_metric = val if '%' in val else f"{val}%"

                    num_val = 50
                    if bar_pct_override is not None:
                        num_val = bar_pct_override
                    else:
                        try:
                            num_val = int(''.join(filter(str.isdigit, display_metric.split('.')[0])))
                        except Exception:
                            pass

                    text_rgb = hex_to_rgb(el.get('textColor'), (255, 255, 255))
                    pct_rgb = hex_to_rgb(el.get('percentColor'), (56, 189, 248))
                    gfx_rgb = hex_to_rgb(el.get('graphicColor'), (56, 189, 248))

                    if dynamic_color_enabled:
                        pct_rgb = get_dynamic_threshold_color(num_val, el, pct_rgb)
                        gfx_rgb = pct_rgb

                    # 🎨 ADVANCED ANIMATION & BREATHING EFFECTS ENGINE (APPLIED TO ANY ELEMENT!)
                    anim_effect = el.get('animEffect', 'none')
                    anim_speed = safe_int(el.get('animSpeed', 5), 5)
                    t_now = time.time()
                    
                    if anim_effect == 'pulse':
                        cycle_speed = 0.35 + (anim_speed * 0.45)
                        pulse_fac = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(t_now * cycle_speed))
                        pct_rgb = (int(pct_rgb[0] * pulse_fac), int(pct_rgb[1] * pulse_fac), int(pct_rgb[2] * pulse_fac))
                        text_rgb = (int(text_rgb[0] * pulse_fac), int(text_rgb[1] * pulse_fac), int(text_rgb[2] * pulse_fac))
                        gfx_rgb = (int(gfx_rgb[0] * pulse_fac), int(gfx_rgb[1] * pulse_fac), int(gfx_rgb[2] * pulse_fac))
                    elif anim_effect == 'rainbow':
                        cycle_speed = 0.03 + (anim_speed * 0.05)
                        hue = (t_now * cycle_speed) % 1.0
                        rgb_f = colorsys.hsv_to_rgb(hue, 0.95, 1.0)
                        pct_rgb = (int(rgb_f[0] * 255), int(rgb_f[1] * 255), int(rgb_f[2] * 255))
                        text_rgb = pct_rgb
                        gfx_rgb = pct_rgb
                    elif anim_effect == 'flash':
                        is_lit = (int(t_now * (0.8 + anim_speed * 1.2)) % 2) == 0
                        if not is_lit:
                            pct_rgb = (int(pct_rgb[0] * 0.15), int(pct_rgb[1] * 0.15), int(pct_rgb[2] * 0.15))
                            text_rgb = (int(text_rgb[0] * 0.15), int(text_rgb[1] * 0.15), int(text_rgb[2] * 0.15))
                    elif anim_effect == 'neon':
                        flicker = 0.70 + 0.30 * (0.5 * math.sin(t_now * (1.5 * anim_speed)) + 0.5 * math.sin(t_now * (3.7 * anim_speed)))
                        pct_rgb = (min(255, max(0, int(pct_rgb[0] * flicker))), min(255, max(0, int(pct_rgb[1] * flicker))), min(255, max(0, int(pct_rgb[2] * flicker))))

                    lbl_text = str(el.get('label', ''))
                    el_type = el.get('type', 'sensor')

                    def _draw_el_border():
                        if show_border:
                            if c_rad > 0:
                                draw_img.rounded_rectangle([el_x, el_y, el_x + el_w, el_y + el_h], radius=c_rad, outline=gfx_rgb, width=2)
                            else:
                                draw_img.rectangle([el_x, el_y, el_x + el_w, el_y + el_h], outline=gfx_rgb, width=2)

                    # 📜 MARQUEE ELEMENT
                    if el_type == 'marquee':
                        m_items = el.get('marquee_items', ['cpu_spec', 'gpu_spec', 'ram_spec', 'cpu_temp', 'gpu_temp', 'game_fps', 'net_down', 'net_up', 'net_ping'])
                        m_str_list = []
                        
                        if lbl_text:
                            m_str_list.append(lbl_text)

                        item_label_map = {
                            'cpu_spec': lambda v: f"CPU: {v}",
                            'gpu_spec': lambda v: f"GPU: {v}",
                            'ram_spec': lambda v: f"RAM: {v}",
                            'cpu_temp': lambda v: f"CPU Temp: {v if '°C' in v else v + '°C'}",
                            'gpu_temp': lambda v: f"GPU Temp: {v if '°C' in v else v + '°C'}",
                            'game_fps': lambda v: f"FPS: {v if 'FPS' in v else v + ' FPS'}",
                            'ram_used': lambda v: f"RAM Used: {v if 'GB' in v else v + ' GB'}",
                            'net_down': lambda v: f"DL: {v.replace('DL:', '').strip()}",
                            'net_up': lambda v: f"UL: {v.replace('UL:', '').strip()}",
                            'net_ping': lambda v: f"PING: {v.replace('PING:', '').strip()}",
                            'time_digital': lambda v: f"TIME: {v}",
                            'date_full': lambda v: f"DATE: {v}"
                        }

                        for item_key in m_items:
                            if item_key in sensor_metrics:
                                val = str(sensor_metrics[item_key])
                                if item_key in item_label_map:
                                    m_str_list.append(item_label_map[item_key](val))
                                else:
                                    m_str_list.append(val)

                        full_m_str = "   |   ".join(m_str_list) if m_str_list else "MY GAMING RIG   |   AMD RYZEN 7 7800X3D   |   NVIDIA RTX 5070   |   32GB DDR5"
                        full_m_str = "".join([c for c in full_m_str if ord(c) < 127 or c in '°ÇÇĞĞİÖÖŞŞÜÜçğışöü'])

                        m_x = el_x - int(self.marquee_offset) % 1800
                        draw_img.text((m_x, el_y + 4), full_m_str, fill=text_rgb, font=lbl_font)
                        draw_img.text((m_x + 1800, el_y + 4), full_m_str, fill=text_rgb, font=lbl_font)

                    # 📈 PHASE 3: LIVE TIME-SERIES SPARKLINE GRAPH WIDGET
                    elif el_type == 'sparkline_graph':
                        _draw_el_border()
                        hdr_h = max(18, min(el_h // 2, int(max(lbl_f_size, val_f_size) * 1.25)))
                        if lbl_text:
                            draw_aligned_text(draw_img, lbl_font, lbl_text, el_x + 4, el_y + 2, el_w // 2, hdr_h, fill=text_rgb, align='left', icon_name=vector_icon_name)
                            draw_aligned_text(draw_img, val_font, display_metric, el_x + el_w // 2, el_y + 2, el_w // 2 - 6, hdr_h, fill=pct_rgb, align='right')
                        else:
                            draw_aligned_text(draw_img, val_font, display_metric, el_x + 4, el_y + 2, el_w - 8, hdr_h, fill=pct_rgb, align='right', icon_name=vector_icon_name)

                        gx0 = el_x + 8
                        gy0 = el_y + hdr_h + 4
                        gx1 = el_x + el_w - 8
                        gy1 = el_y + el_h - 6
                        gw = max(16, gx1 - gx0)
                        gh = max(12, gy1 - gy0)

                        # Subtle horizontal reference grid lines
                        for g_div in (0.25, 0.5, 0.75):
                            gy_line = int(gy0 + gh * g_div)
                            draw_img.line([(gx0, gy_line), (gx1, gy_line)], fill=(148, 163, 184, 45), width=1)

                        hist_dict = sensor_metrics.get('_history') or {}
                        hist_key = s_id
                        if s_id in ('ram_used', 'ram_load', 'ram_free', 'ram_free_load', 'ram_used_both', 'ram_free_both'):
                            r_m = str(el.get('ramDisplayMode') or '').strip()
                            if r_m in ('free_gb', 'free_pct', 'free_both') or s_id in ('ram_free', 'ram_free_load', 'ram_free_both'):
                                hist_key = 'ram_free_load'
                            else:
                                hist_key = 'ram_load'
                        series = list(hist_dict.get(hist_key, []))
                        if len(series) < 2:
                            series = [float(num_val)] * 20

                        # Determine dynamic or fixed range
                        if hist_key in ('cpu_load', 'gpu_load', 'ram_load', 'ram_free_load', 'gpu_fan'):
                            lo_v, hi_v = 0.0, 100.0
                        elif s_id in ('cpu_temp', 'gpu_temp'):
                            lo_v, hi_v = 30.0, 95.0
                        else:
                            lo_v = min(series)
                            hi_v = max(series)
                            if hi_v - lo_v < 5.0:
                                mid = (hi_v + lo_v) * 0.5
                                lo_v = max(0.0, mid - 10.0)
                                hi_v = mid + 10.0

                        span_v = max(1e-3, hi_v - lo_v)
                        n_pts = len(series)
                        pts = []
                        for idx_pt, sv in enumerate(series):
                            px = gx0 + int((idx_pt / float(max(1, n_pts - 1))) * gw)
                            norm = min(1.0, max(0.0, (float(sv) - lo_v) / span_v))
                            py = gy1 - int(norm * gh)
                            pts.append((px, py))

                        if len(pts) >= 2:
                            poly_pts = [(pts[0][0], gy1)] + pts + [(pts[-1][0], gy1)]
                            draw_img.polygon(poly_pts, fill=(gfx_rgb[0], gfx_rgb[1], gfx_rgb[2], 70))
                            draw_img.line(pts, fill=gfx_rgb, width=2)
                            lx, ly = pts[-1]
                            draw_img.ellipse([lx - 4, ly - 4, lx + 4, ly + 4], fill=pct_rgb, outline=(255, 255, 255))

                    # 🖼️ PHASE 3: CUSTOM IMAGE / STICKER / LOGO LAYER WIDGET
                    elif el_type == 'custom_image':
                        b64_data = el.get('imageDataB64')
                        img_path = el.get('imagePath', '')
                        cache_sig = (el_id, len(b64_data) if isinstance(b64_data, str) else img_path, el_w, el_h)
                        cached_rgba = self._custom_image_cache.get(cache_sig)
                        if cached_rgba is None:
                            try:
                                import base64
                                src_im = None
                                # 🔒 SECURITY: Cap base64 payload to 8 MB and block UNC/device paths
                                if isinstance(b64_data, str) and 0 < len(b64_data) <= 8 * 1024 * 1024:
                                    raw_bytes = base64.b64decode(b64_data)
                                    src_im = Image.open(io.BytesIO(raw_bytes)).convert('RGBA')
                                elif img_path and _is_safe_local_file_path(img_path) and os.path.isfile(img_path):
                                    src_im = Image.open(img_path).convert('RGBA')
                                if src_im is not None:
                                    cached_rgba = src_im.resize((max(8, min(4096, el_w)), max(8, min(4096, el_h))), Image.Resampling.LANCZOS)
                                else:
                                    cached_rgba = False
                            except Exception:
                                cached_rgba = False
                            if len(self._custom_image_cache) > 64:
                                self._custom_image_cache.clear()
                            self._custom_image_cache[cache_sig] = cached_rgba

                        if cached_rgba:
                            img.paste(cached_rgba, (el_x, el_y), cached_rgba)
                        else:
                            draw_aligned_text(draw_img, lbl_font, lbl_text or "🖼️ Özel Görsel", el_x, el_y, el_w, el_h, fill=text_rgb, align='center')
                        _draw_el_border()

                    # 🌀 ANIMATED FAN
                    elif el_type == 'animated_fan':
                        fan_text_h = max(16, int(lbl_f_size * 1.2)) if lbl_text else 0
                        circle_h = max(20, el_h - fan_text_h - 6)
                        
                        r = max(10, min(el_w, circle_h) // 2 - 6)
                        cx = el_x + el_w // 2
                        cy = el_y + r + 4
                        
                        draw_img.ellipse([cx - r, cy - r, cx + r, cy + r], outline=gfx_rgb, width=4)
                        draw_img.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=gfx_rgb)
                        
                        for b in range(4):
                            rad = math.radians(self.anim_angle + (b * 90))
                            bx = cx + int((r - 4) * math.cos(rad))
                            by = cy + int((r - 4) * math.sin(rad))
                            draw_img.line([(cx, cy), (bx, by)], fill=gfx_rgb, width=4)
                        
                        draw_aligned_text(draw_img, val_font, display_metric, el_x, cy - (val_f_size // 2), el_w, val_f_size + 4, fill=pct_rgb, align='center')
                        
                        if lbl_text:
                            draw_aligned_text(draw_img, lbl_font, lbl_text, el_x, el_y + el_h - fan_text_h, el_w, fan_text_h, fill=text_rgb, align='center', icon_name=vector_icon_name)

                    # 📊 HORIZONTAL PROGRESS GAUGE BAR
                    elif el_type == 'gauge':
                        _draw_el_border()
                        if lbl_text:
                            draw_aligned_text(draw_img, lbl_font, f"{lbl_text}:", el_x, el_y, el_w // 2, el_h - 12, fill=text_rgb, align='left', icon_name=vector_icon_name)
                            draw_aligned_text(draw_img, val_font, display_metric, el_x + el_w // 2, el_y, el_w // 2 - 4, el_h - 12, fill=pct_rgb, align='right')
                        else:
                            draw_aligned_text(draw_img, val_font, display_metric, el_x, el_y, el_w, el_h - 12, fill=pct_rgb, align='left', icon_name=vector_icon_name)
                        
                        bar_y = el_y + el_h - 10
                        bar_w = int((el_w - 12) * min(1.0, max(0.0, num_val / 100.0)))
                        draw_img.rounded_rectangle([el_x + 6, bar_y, el_x + el_w - 6, bar_y + 6], radius=3, fill=(30, 41, 59))
                        if bar_w > 0:
                            draw_img.rounded_rectangle([el_x + 6, bar_y, el_x + 6 + bar_w, bar_y + 6], radius=3, fill=gfx_rgb)

                    # 📶 VERTICAL GAUGE BAR
                    elif el_type == 'vertical_gauge':
                        if c_rad > 0:
                            draw_img.rounded_rectangle([el_x + 6, el_y + 6, el_x + el_w - 6, el_y + el_h - 6], radius=c_rad, outline=gfx_rgb, width=2)
                        else:
                            draw_img.rectangle([el_x + 6, el_y + 6, el_x + el_w - 6, el_y + el_h - 6], outline=gfx_rgb, width=2)
                        v_h = int((el_h - 16) * min(1.0, max(0.0, num_val / 100.0)))
                        if v_h > 0:
                            draw_img.rectangle([el_x + 8, el_y + el_h - 8 - v_h, el_x + el_w - 8, el_y + el_h - 8], fill=gfx_rgb)

                        draw_aligned_text(draw_img, val_font, display_metric, el_x, el_y + (el_h // 2) - (val_f_size // 2), el_w, val_f_size + 4, fill=pct_rgb, align='center')
                        if lbl_text:
                            draw_aligned_text(draw_img, lbl_font, lbl_text, el_x, el_y + 8, el_w, lbl_f_size + 4, fill=text_rgb, align='center', icon_name=vector_icon_name)

                    # ⭕ CIRCULAR GAUGE
                    elif el_type == 'circle_gauge':
                        lbl_h = max(16, int(lbl_f_size * 1.2)) if lbl_text else 0
                        circle_h = max(20, el_h - lbl_h - 6)
                        
                        r = max(10, min(el_w, circle_h) // 2 - 6)
                        cx = el_x + el_w // 2
                        cy = el_y + r + 4
                        
                        draw_img.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(30, 41, 59), width=8)
                        
                        sweep = int(360 * min(1.0, max(0.0, num_val / 100.0)))
                        draw_img.arc([cx - r, cy - r, cx + r, cy + r], start=-90, end=-90 + sweep, fill=gfx_rgb, width=8)
                        
                        draw_aligned_text(draw_img, val_font, display_metric, el_x, cy - (val_f_size // 2), el_w, val_f_size + 4, fill=pct_rgb, align='center')
                        
                        if lbl_text:
                            draw_aligned_text(draw_img, lbl_font, lbl_text, el_x, el_y + el_h - lbl_h, el_w, lbl_h, fill=text_rgb, align='center', icon_name=vector_icon_name)

                    # 🎵 YOUTUBE MUSIC / MEDYA OYNATICI WIDGET (WITH MULTI-LINE WORD WRAPPING)
                    elif el_type == 'music_player':
                        song_title = str(sensor_metrics.get('music_title', 'YouTube Music'))
                        song_artist = str(sensor_metrics.get('music_artist', 'Müzik Bekleniyor...'))
                        cover_img = sensor_metrics.get('music_cover')

                        _draw_el_border()

                        cover_size = max(24, min(el_h - 12, int(el_h * 0.75)))
                        cover_x = el_x + 8
                        cover_y = el_y + (el_h - cover_size) // 2

                        if cover_img:
                            try:
                                if self._cached_cover_src is not cover_img or self._cached_cover_size != cover_size or self._cached_cover_resized is None:
                                    self._cached_cover_src = cover_img
                                    self._cached_cover_size = cover_size
                                    self._cached_cover_resized = cover_img.resize((cover_size, cover_size), Image.Resampling.BILINEAR)
                                img.paste(self._cached_cover_resized, (cover_x, cover_y))
                            except Exception:
                                draw_img.rectangle([cover_x, cover_y, cover_x + cover_size, cover_y + cover_size], fill=gfx_rgb)
                        else:
                            draw_img.rectangle([cover_x, cover_y, cover_x + cover_size, cover_y + cover_size], fill=gfx_rgb)
                            draw_aligned_text(draw_img, lbl_font, "🎵", cover_x, cover_y, cover_size, cover_size, fill=(255, 255, 255), align='center')

                        text_x = cover_x + cover_size + 10
                        text_w = max(10, el_x + el_w - text_x - 6)
                        
                        draw_wrapped_text(draw_img, val_font, song_title, text_x, el_y + 2, text_w, max(14, int(el_h * 0.58)), fill=text_rgb)
                        draw_aligned_text(draw_img, lbl_font, song_artist, text_x, el_y + el_h - max(12, int(el_h * 0.35)), text_w, max(12, int(el_h * 0.35)), fill=pct_rgb, align='left')

                    # 🌦️ CANLI HAVA DURUMU WIDGET'I (WITH CRISP VECTOR ICONS)
                    elif el_type == 'weather_widget':
                        w_city = str(sensor_metrics.get('weather_city', 'İstanbul'))
                        w_temp = str(sensor_metrics.get('weather_temp', '24°C'))
                        w_desc = str(sensor_metrics.get('weather_desc', 'Güneşli'))
                        w_icon_key = str(sensor_metrics.get('weather_icon_key', 'sun'))

                        _draw_el_border()

                        icon_box_w = max(24, min(el_h - 10, int(el_h * 0.7)))
                        icon_x = el_x + 8
                        icon_y = el_y + (el_h - icon_box_w) // 2

                        draw_weather_vector_icon(draw_img, w_icon_key, icon_x, icon_y, icon_box_w)

                        txt_x = icon_x + icon_box_w + 8
                        txt_w = max(10, el_x + el_w - txt_x - 6)

                        draw_aligned_text(draw_img, val_font, f"{w_city} {w_temp}", txt_x, el_y + 4, txt_w, max(12, el_h // 2), fill=pct_rgb, align='left')
                        draw_aligned_text(draw_img, lbl_font, w_desc, txt_x, el_y + el_h // 2, txt_w, max(12, el_h // 2 - 4), fill=text_rgb, align='left')

                    # 📈 CANLI PİNG & OYUN SUNUCUSU MONİTÖRÜ
                    elif el_type == 'ping_monitor':
                        _draw_el_border()

                        ping_str = str(sensor_metrics.get('net_ping', 'PING: 14 ms'))
                        draw_aligned_text(draw_img, lbl_font, "🌐 OYUN PİNG / BANT", el_x, el_y + 4, el_w, el_h // 3, fill=text_rgb, align='center')
                        draw_aligned_text(draw_img, val_font, ping_str, el_x, el_y + el_h // 3, el_w, el_h // 3, fill=pct_rgb, align='center')

                        bar_x = el_x + (el_w - 40) // 2
                        bar_y = el_y + (el_h * 2) // 3 + 2
                        for b_idx in range(4):
                            bh = (b_idx + 1) * 3
                            bx = bar_x + (b_idx * 10)
                            by = bar_y + (12 - bh)
                            draw_img.rectangle([bx, by, bx + 6, bar_y + 12], fill=gfx_rgb)

                    # 🗓️ SMART EVENT COUNTDOWN WIDGET (DYNAMIC RESOLUTION: DAYS -> HOURS -> MINS -> SECONDS)
                    elif el_type == 'event_countdown':
                        _draw_el_border()

                        event_title = str(el.get('label') or '🚀 GERİ SAYIM')
                        target_ts = float(el.get('targetTimestamp', time.time() + 7776000))
                        
                        diff_sec = target_ts - time.time()
                        if diff_sec <= 0:
                            cd_str = "🎉 ZAMAN DOLDU!"
                        elif diff_sec >= 86400:
                            days = int(diff_sec // 86400)
                            cd_str = f"{days} GÜN KALDI"
                        elif diff_sec >= 3600:
                            hrs = int(diff_sec // 3600)
                            mins = int((diff_sec % 3600) // 60)
                            cd_str = f"{hrs} SAAT {mins} DK KALDI"
                        elif diff_sec >= 60:
                            mins = int(diff_sec // 60)
                            secs = int(diff_sec % 60)
                            cd_str = f"{mins} DK {secs} SN KALDI"
                        else:
                            secs = max(0, int(diff_sec))
                            cd_str = f"⚡ {secs} SANİYE KALDI"

                        draw_aligned_text(draw_img, lbl_font, event_title, el_x, el_y + 4, el_w, el_h // 2, fill=text_rgb, align='center', icon_name='calendar')
                        draw_aligned_text(draw_img, val_font, cd_str, el_x, el_y + el_h // 2, el_w, el_h // 2 - 4, fill=pct_rgb, align='center')

                    # 🔲 BOX / BORDER
                    elif el_type == 'box':
                        _draw_el_border()

                    # 🌡️ STANDARD SENSOR TEXT / TIME / DATE / CUSTOM TEXT
                    else:
                        _draw_el_border()
                        if el_type == 'text':
                            draw_aligned_text(draw_img, val_font, lbl_text or "Özel Metin", el_x, el_y, el_w, el_h, fill=text_rgb, align=text_align)
                        elif lbl_text:
                            draw_aligned_text(draw_img, lbl_font, f"{lbl_text}:", el_x, el_y, el_w // 2, el_h, fill=text_rgb, align='left', icon_name=vector_icon_name)
                            draw_aligned_text(draw_img, val_font, display_metric, el_x + el_w // 2, el_y, el_w // 2 - 4, el_h, fill=pct_rgb, align='right')
                        else:
                            draw_aligned_text(draw_img, val_font, display_metric, el_x, el_y, el_w, el_h, fill=pct_rgb, align=text_align, icon_name=vector_icon_name)

                    # Show selection highlight box on GUI canvas (supports single & multi-select + locked indicator)
                    if el_id in selected_ids and not for_hardware:
                        is_locked = bool(el.get('locked', False))
                        if is_locked:
                            border_col = (245, 158, 11)  # Amber border for locked element
                        elif el_id == selected_id:
                            border_col = (16, 185, 129) if len(selected_ids) > 1 else (99, 102, 241)
                        else:
                            border_col = (56, 189, 248)  # Cyan border for secondary multi-selected items
                        draw_img.rectangle([el_x, el_y, el_x + el_w, el_y + el_h], outline=border_col, width=2)
                        if el_id == selected_id and not is_locked:
                            # Draw bottom-right resize grip handle
                            draw_img.rectangle([el_x + el_w - 8, el_y + el_h - 8, el_x + el_w, el_y + el_h], fill=border_col)

                except Exception as e:
                    print("Element render note:", e)

            # 🚨 DONANIM KORUMA AŞIRI ISINMA UYARISI OVERLAY (THERMAL ALERT FILTER)
            try:
                alert_limit = safe_int(theme_data.get('thermal_alert_limit'), 82)
                cpu_temp_raw = sensor_metrics.get('cpu_temp', '50')
                gpu_temp_raw = sensor_metrics.get('gpu_temp', '45')
                
                cpu_t = int(''.join(filter(str.isdigit, str(cpu_temp_raw))))
                gpu_t = int(''.join(filter(str.isdigit, str(gpu_temp_raw))))

                # Only trigger on valid, realistic temperatures (suppress corrupt sensor 206°C spikes)
                if (alert_limit <= cpu_t <= 105) or (alert_limit <= gpu_t <= 105):
                    if self.flash_cycle < 10:
                        alert_ov = Image.new('RGBA', (w, h), (239, 68, 68, 80))
                        draw_a = ImageDraw.Draw(alert_ov)
                        draw_a.rectangle([10, 10, w - 10, h - 10], outline=(239, 68, 68, 255), width=8)
                        
                        alert_font = get_custom_font('Impact', 32, is_bold=True)
                        draw_a.text((w // 2 - 100, h // 2 - 20), "🔥 HIGH TEMP ALERT!", fill=(255, 255, 255, 255), font=alert_font)
                        img = Image.alpha_composite(img.convert('RGBA'), alert_ov).convert('RGB')
            except Exception:
                pass

            # Cache last frame for RGB Ambilight sampling
            self.last_rendered_frame = img
            self.latest_metrics = sensor_metrics

            # Rotate frame for hardware streaming orientation (GUI preview remains 0° upright)
            if for_hardware:
                rot = safe_int(theme_data.get('rotation'), 180)
                if rot == 180:
                    img = img.rotate(180)
                elif rot == 90:
                    img = img.rotate(90, expand=True)
                elif rot == 270:
                    img = img.rotate(270, expand=True)

            return img

    def send_pil_image(self, pil_image):
        if not self.is_connected:
            return False

        try:
            buf = io.BytesIO()
            pil_image.save(buf, format='JPEG', quality=85)
            byte_data = buf.getvalue()
            jpeg_len = len(byte_data)
            
            # Option 1: Native PySerial
            if self.ser and self.ser.is_open:
                lcd_packet_header = bytes([0x55, 0xAA, jpeg_len & 0xFF, (jpeg_len >> 8) & 0xFF, (jpeg_len >> 16) & 0xFF, (jpeg_len >> 24) & 0xFF])
                self.ser.write(lcd_packet_header + byte_data)
                self.ser.flush()
                return True
            # Option 2: C# DLS_SDK
            elif self.dls and self.send_data_mi:
                c_bytes = System.Array[System.Byte](byte_data)
                self.send_data_mi.Invoke(self.dls, [c_bytes])
                return True
        except Exception as e:
            safe_print("Send image note:", e)
            # If serial disconnected, reset
            self.is_connected = False
            try:
                if self.ser:
                    self.ser.close()
            except Exception:
                pass
        return False

    def close(self):
        with self.render_lock:
            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
            if self.dls:
                try:
                    self.dls.CloseSerialPort()
                except Exception:
                    pass
                self.dls = None
            self.is_connected = False
