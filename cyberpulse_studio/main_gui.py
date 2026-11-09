import os
import sys
import json
import copy
import re
import winreg
import random
import psutil
import time
import ctypes
import subprocess

# 🚀 SINGLE INSTANCE MANAGER (Eski / Donmuş Süreçleri Temizleyip Yeni Örneği Açma)
def ensure_single_instance():
    try:
        current_pid = os.getpid()
        parent_pid = os.getppid() if hasattr(os, 'getppid') else None
        this_script = os.path.normcase(os.path.abspath(__file__))
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pid = proc.info['pid']
                if pid == current_pid or pid == parent_pid:
                    continue
                name = (proc.info.get('name') or '').lower()
                if not ('python' in name):
                    continue
                cmd = proc.info.get('cmdline') or []
                if len(cmd) < 2 or any('-c' in str(a) for a in cmd):
                    continue
                # 🔒 SECURITY: Only target python processes running this exact main_gui.py path
                is_same_script = False
                for arg in cmd[1:]:
                    arg_s = str(arg).strip()
                    if arg_s.lower().endswith('main_gui.py'):
                        try:
                            if os.path.normcase(os.path.abspath(arg_s)) == this_script:
                                is_same_script = True
                                break
                        except Exception:
                            pass
                if is_same_script:
                    print(f"Stopping previous background instance PID {pid}...")
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        print("Single instance cleaner note:", e)


# 🚀 OPTIMIZATION: Set process priority to BELOW_NORMAL so games get 100% CPU priority!
try:
    p = psutil.Process()
    p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
except Exception as e:
    print("Process priority note:", e)

try:
    import PyQt5
    qt_plugin_dir = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins', 'platforms')
    if os.path.exists(qt_plugin_dir):
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = qt_plugin_dir
except Exception as e:
    print("Qt Plugin path note:", e)

import io
from PIL import Image, ImageDraw

from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, QSize, QThread, pyqtSignal, QDateTime, QObject, QEvent, QUrl
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush, QIcon, QCursor, QKeySequence, QFont, QDesktopServices
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QSlider, QSpinBox,
    QColorDialog, QFileDialog, QGroupBox, QLineEdit, QComboBox,
    QSplitter, QMessageBox, QFrame, QCheckBox, QSystemTrayIcon, QMenu, QAction, QInputDialog,
    QDateTimeEdit, QKeySequenceEdit, QScrollArea, QSizePolicy, QProgressBar
)
from i18n import apply_language_to_widget_tree, translate_text

try:
    import keyboard
    HAS_KEYBOARD = True
except Exception as e:
    print("Keyboard hook note:", e)
    HAS_KEYBOARD = False

class LanguageEventFilter(QObject):
    """Automatically translates any QDialog or QMainWindow when shown."""
    def __init__(self, gui_ref):
        super().__init__(gui_ref)
        self.gui = gui_ref

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEvent.Show and isinstance(obj, QDialog):
                lang = str(self.gui.app_settings.get('language', 'tr')).lower()
                apply_language_to_widget_tree(obj, lang)
        except Exception:
            pass
        return False


class HotkeyBridge(QObject):
    next_theme_signal = pyqtSignal()
    prev_theme_signal = pyqtSignal()
    toggle_stream_signal = pyqtSignal()
    random_theme_signal = pyqtSignal()
    toggle_window_signal = pyqtSignal()

from sensor_monitor import SensorMonitor
from hardware_driver import (
    HardwareDriver, get_custom_font, _is_safe_local_file_path,
    read_cptheme_footer, read_cptheme_metadata, read_cptheme_image,
    write_cptheme_file, update_cptheme_metadata, migrate_legacy_theme_folders
)
from case_screen_profiles import (
    CASE_SCREEN_PRESETS,
    detect_all_available_screens,
    find_preset_for_resolution,
    adapt_theme_elements_to_resolution,
    HDMICompanionDisplayWindow,
    CaseScreenSelectorDialog
)
from game_profile_manager import (
    GameProfileManagerDialog,
    get_foreground_process_exe,
    sanitize_exe_name
)

if getattr(sys, 'frozen', False):
    APP_USER_DATA_DIR = os.path.dirname(os.path.abspath(sys.executable))
    APP_BUNDLE_DIR = getattr(sys, '_MEIPASS', APP_USER_DATA_DIR)
else:
    APP_USER_DATA_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_BUNDLE_DIR = APP_USER_DATA_DIR

LAST_THEME_FILE = os.path.join(APP_USER_DATA_DIR, 'last_theme.json')
SCREEN_WORKSPACES_FILE = os.path.join(APP_USER_DATA_DIR, 'screen_workspaces.json')
APP_SETTINGS_FILE = os.path.join(APP_USER_DATA_DIR, 'app_settings.json')
PRESET_THEMES_DIR = os.path.join(APP_USER_DATA_DIR, 'themes')
RGB_APP_SCRIPT = os.path.join(APP_BUNDLE_DIR, 'rgb_studio_gui.py')
VERSION_FILE = os.path.join(APP_BUNDLE_DIR, 'version.json')
os.makedirs(PRESET_THEMES_DIR, exist_ok=True)

APP_VERSION = "1.3.0"
try:
    if os.path.isfile(VERSION_FILE) and os.path.getsize(VERSION_FILE) <= 16384:
        with open(VERSION_FILE, 'r', encoding='utf-8') as _vf:
            _vdata = json.load(_vf)
            if isinstance(_vdata, dict) and _vdata.get('version'):
                APP_VERSION = str(_vdata['version']).strip()[:20]
except Exception:
    pass

SPONSOR_URL = "https://github.com/sponsors/blackxtr-lang"
GITHUB_RAW_BASE_URL = "https://raw.githubusercontent.com/blackxtr-lang/cyberpulse-lcd-studio/main/cyberpulse_studio"
_ALLOWED_UPDATE_FILES = (
    "version.json",
    "i18n.py",
    "case_screen_profiles.py",
    "game_profile_manager.py",
    "sensor_monitor.py",
    "hardware_driver.py",
    "main_gui.py",
)


def _parse_semver_tuple(ver_str):
    parts = re.findall(r'\d+', str(ver_str or '0.0.0'))
    nums = [int(x) for x in parts[:4]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


class AutoUpdateWorker(QThread):
    """
    🔄 Background Auto-Update Checker & Installer:
    Checks GitHub (https://github.com/blackxtr-lang/cyberpulse-lcd-studio) on every startup over verified TLS.
    If a newer version exists in version.json, automatically downloads and validates the updated modules
    and notifies the main GUI to restart seamlessly.
    """
    update_result_signal = pyqtSignal(str, str, str)  # (status: 'updated'|'up_to_date'|'exe_update_available'|'error', remote_ver, message)
    update_finished = update_result_signal

    def __init__(self, silent=True, parent=None):
        super().__init__(parent)
        self.silent = bool(silent)

    def run(self):
        import ssl
        import urllib.request
        try:
            ctx = ssl.create_default_context()
            ver_url = f"{GITHUB_RAW_BASE_URL}/version.json?t={int(time.time())}"
            req = urllib.request.Request(ver_url, headers={'User-Agent': f'CyberPulseStudio/{APP_VERSION}'})
            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                raw_json = resp.read(65536).decode('utf-8', errors='replace')
            remote_meta = json.loads(raw_json)
            if not isinstance(remote_meta, dict) or not remote_meta.get('version'):
                if not self.silent:
                    self.update_result_signal.emit('up_to_date', APP_VERSION, "Uygulamanız güncel.")
                return

            remote_ver = str(remote_meta.get('version')).strip()[:20]
            if _parse_semver_tuple(remote_ver) <= _parse_semver_tuple(APP_VERSION):
                if not self.silent:
                    self.update_result_signal.emit('up_to_date', APP_VERSION, f"En güncel sürümü (v{APP_VERSION}) kullanıyorsunuz.")
                return

            # Newer version available! Download and verify whitelisted files atomically
            if getattr(sys, 'frozen', False):
                # For frozen .exe builds, notify and open the latest release page if auto-patch is locked by OS
                self.update_result_signal.emit('exe_update_available', remote_ver, f"Yeni sürüm (v{remote_ver}) yayınlandı!")
                return

            staged_contents = {}
            for fname in _ALLOWED_UPDATE_FILES:
                f_url = f"{GITHUB_RAW_BASE_URL}/{fname}?t={int(time.time())}"
                f_req = urllib.request.Request(f_url, headers={'User-Agent': f'CyberPulseStudio/{APP_VERSION}'})
                with urllib.request.urlopen(f_req, context=ctx, timeout=8) as f_resp:
                    data_bytes = f_resp.read(4 * 1024 * 1024)
                if not data_bytes or len(data_bytes) < 10:
                    raise RuntimeError(f"Eksik dosya verisi: {fname}")
                text_content = data_bytes.decode('utf-8')
                if fname.endswith('.py'):
                    # 🔒 SECURITY & INTEGRITY: Verify Python syntax before touching disk
                    compile(text_content, fname, 'exec')
                elif fname.endswith('.json'):
                    json.loads(text_content)
                staged_contents[fname] = text_content

            # Write all verified files atomically
            for fname, text_content in staged_contents.items():
                dest_path = os.path.join(APP_USER_DATA_DIR, fname)
                tmp_path = dest_path + ".upd_tmp"
                with open(tmp_path, 'w', encoding='utf-8', newline='\n') as wf:
                    wf.write(text_content)
                os.replace(tmp_path, dest_path)

            self.update_result_signal.emit(
                'updated',
                remote_ver,
                f"Yeni güncelleme (v{remote_ver}) otomatik olarak indirildi ve kuruldu!"
            )
        except Exception as e:
            if not self.silent:
                self.update_result_signal.emit('error', APP_VERSION, f"Güncelleme denetimi sırasında bağlantı kurulamadı: {e}")

_RESERVED_WIN_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
}

def _sanitize_theme_filename(raw_name):
    """🔒 SECURITY: Sanitizes theme name against path traversal, control chars, and Windows reserved device names."""
    if not raw_name or not isinstance(raw_name, str):
        return ""
    base_part = os.path.basename(raw_name.replace('\\', '/').strip('/ '))
    if base_part in ('.', '..'):
        return ""
    cleaned = "".join(c for c in base_part if c not in '<>:"/\\|?*' and ord(c) >= 32).strip(" .")[:80].strip(" .")
    if not cleaned or cleaned in ('.', '..'):
        return ""
    stem = os.path.splitext(cleaned)[0].upper()
    if stem in _RESERVED_WIN_NAMES:
        return ""
    return cleaned

# 🚀 Auto-migrate any legacy theme folders into single-file .cptheme packages on startup
try:
    _mig_cnt = migrate_legacy_theme_folders(PRESET_THEMES_DIR)
    if _mig_cnt > 0:
        print(f"[+] Automatically migrated {_mig_cnt} legacy theme folders to single-file .cptheme format!")
except Exception as _mig_err:
    print("Theme auto-migration note:", _mig_err)

def _format_resolution_group_title(w, h):
    """Returns a friendly human-readable resolution category title."""
    w, h = int(w or 320), int(h or 1480)
    known_labels = {
        (320, 1480): "Dikey Kasa Ekranı (8.8\" IPS)",
        (1480, 320): "Yatay Kasa Ekranı (8.8\" IPS)",
        (480, 1920): "Dikey Kasa Ekranı (8.8\" / 12.6\" FHD)",
        (1920, 480): "Yatay Kasa Ekranı (8.8\" / 12.6\" FHD)",
        (1920, 1080): "Full HD 1080p Monitör (16:9 Yatay)",
        (1080, 1920): "Full HD 1080p Monitör (9:16 Dikey)",
        (2560, 1440): "2K QHD Monitör (16:9 Yatay)",
        (1440, 2560): "2K QHD Monitör (9:16 Dikey)",
        (3840, 2160): "4K UHD Monitör (16:9 Yatay)",
        (1280, 720): "HD 720p Ekran (16:9 Yatay)",
        (1280, 800): "WXGA Ekran (16:10 Yatay)",
        (1024, 600): "7\" Mini IPS Ekran (Yatay)",
        (600, 1024): "7\" Mini IPS Ekran (Dikey)",
        (800, 480): "5\" Mini LCD Ekran (Yatay)",
        (480, 800): "5\" Mini LCD Ekran (Dikey)",
        (480, 480): "Kare AIO Sıvı Soğutucu Ekranı (1:1)",
    }
    desc = known_labels.get((w, h))
    if not desc:
        orient = "Dikey" if h > w else ("Kare" if w == h else "Yatay")
        desc = f"{orient} Ekran"
    return f"{w}×{h} ({desc})"


def _extract_theme_resolution_fast(t_info):
    """Reads width and height from a preset theme entry in <0.2ms."""
    tw, th = 320, 1480
    try:
        if t_info.get('is_cptheme') and t_info.get('cptheme_path'):
            meta = read_cptheme_metadata(t_info['cptheme_path'])
            if isinstance(meta, dict):
                tw = max(64, min(4096, int(meta.get('width', 320) or 320)))
                th = max(64, min(4096, int(meta.get('height', 1480) or 1480)))
        else:
            jp = t_info.get('json_path')
            if jp and _is_safe_local_file_path(jp) and os.path.isfile(jp) and os.path.getsize(jp) <= 4 * 1024 * 1024:
                with open(jp, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                if isinstance(meta, dict):
                    tw = max(64, min(4096, int(meta.get('width', 320) or 320)))
                    th = max(64, min(4096, int(meta.get('height', 1480) or 1480)))
    except Exception:
        pass
    return tw, th


def get_all_preset_themes():
    themes = []
    if not os.path.exists(PRESET_THEMES_DIR):
        return themes

    # 1. Native Single-File Themes (.cptheme) - Primary Format (<0.25ms metadata read)
    for entry in sorted(os.listdir(PRESET_THEMES_DIR)):
        if entry.startswith('_'):
            continue
        full_p = os.path.join(PRESET_THEMES_DIR, entry)
        if os.path.isfile(full_p) and entry.lower().endswith('.cptheme'):
            base_name = os.path.splitext(entry)[0]
            t_item = {
                'name': base_name,
                'cptheme_path': full_p,
                'json_path': full_p,
                'folder': None,
                'is_folder': False,
                'is_cptheme': True
            }
            tw, th = _extract_theme_resolution_fast(t_item)
            t_item['width'] = tw
            t_item['height'] = th
            t_item['res_key'] = f"{tw}x{th}"
            themes.append(t_item)

    # 2. Legacy Folder or JSON fallback (if any exist)
    for entry in sorted(os.listdir(PRESET_THEMES_DIR)):
        if entry.startswith('_'):
            continue
        full_p = os.path.join(PRESET_THEMES_DIR, entry)
        if os.path.isdir(full_p):
            if any(t['name'].lower() == entry.lower() for t in themes):
                continue
            t_json = os.path.join(full_p, 'theme.json')
            if os.path.exists(t_json):
                t_item = {
                    'name': entry,
                    'cptheme_path': None,
                    'json_path': t_json,
                    'folder': full_p,
                    'is_folder': True,
                    'is_cptheme': False
                }
                tw, th = _extract_theme_resolution_fast(t_item)
                t_item['width'] = tw
                t_item['height'] = th
                t_item['res_key'] = f"{tw}x{th}"
                themes.append(t_item)
        elif entry.lower().endswith('.json'):
            base_name = os.path.splitext(entry)[0]
            if not any(t['name'].lower() == base_name.lower() for t in themes):
                t_item = {
                    'name': base_name,
                    'cptheme_path': None,
                    'json_path': full_p,
                    'folder': None,
                    'is_folder': False,
                    'is_cptheme': False
                }
                tw, th = _extract_theme_resolution_fast(t_item)
                t_item['width'] = tw
                t_item['height'] = th
                t_item['res_key'] = f"{tw}x{th}"
                themes.append(t_item)
    return themes

def load_preset_theme_data(t_info):
    """Loads theme dictionary from a preset entry (.cptheme or legacy JSON) in ~0.25ms."""
    if not t_info or not isinstance(t_info, dict):
        return None
    if t_info.get('is_cptheme') and t_info.get('cptheme_path'):
        return read_cptheme_metadata(t_info['cptheme_path'])
    path = t_info.get('json_path')
    if path and _is_safe_local_file_path(path) and os.path.isfile(path):
        if path.lower().endswith('.cptheme'):
            return read_cptheme_metadata(path)
        if os.path.getsize(path) > 4 * 1024 * 1024:
            return None
        with open(path, 'r', encoding='utf-8') as f:
            t_json = json.load(f)
        if isinstance(t_json, dict):
            bg = t_json.get('bg_path', '')
            if bg and not _is_safe_local_file_path(bg):
                t_json['bg_path'] = None
            elif bg and not os.path.isabs(bg) and t_info.get('folder'):
                folder_abs = os.path.abspath(t_info['folder'])
                cand = os.path.abspath(os.path.normpath(os.path.join(folder_abs, bg)))
                try:
                    # 🔒 SECURITY: Ensure relative background path cannot escape theme folder
                    if os.path.commonpath([folder_abs, cand]) == folder_abs and os.path.isfile(cand):
                        t_json['bg_path'] = cand
                    else:
                        t_json['bg_path'] = None
                except Exception:
                    t_json['bg_path'] = None
        return t_json
    return None

def bake_video_background(src_path, dst_path, w=320, h=1480, crop_rect=None, fit_to_screen=False, target_fps=24.0, max_frames=450):
    try:
        import cv2
        cap = cv2.VideoCapture(src_path)
        if not cap.isOpened():
            return False

        src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        fps = min(target_fps, src_fps)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(dst_path, fourcc, fps, (w, h))

        frame_count = 0
        while frame_count < max_frames:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            fh, fw = frame.shape[:2]
            if fit_to_screen or not crop_rect:
                resized = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA if fw > w else cv2.INTER_LINEAR)
            else:
                x1, y1, x2, y2 = [int(v) for v in crop_rect]
                x1 = max(0, min(fw - 10, x1))
                y1 = max(0, min(fh - 10, y1))
                x2 = min(fw, max(x1 + 10, x2))
                y2 = min(fh, max(y1 + 10, y2))
                cropped = frame[y1:y2, x1:x2]
                if cropped.size > 0:
                    resized = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_AREA if cropped.shape[1] > w else cv2.INTER_LINEAR)
                else:
                    resized = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA if fw > w else cv2.INTER_LINEAR)

            out.write(resized)
            frame_count += 1

        cap.release()
        out.release()
        return frame_count > 0
    except Exception as e:
        print("Bake video error:", e)
        return False

def bake_image_background(src_path, dst_path=None, w=320, h=1480, crop_rect=None, fit_to_screen=False):
    try:
        if src_path.lower().endswith('.cptheme'):
            img = read_cptheme_image(src_path)
            if img is None:
                return False
        else:
            img = Image.open(src_path).convert('RGB')
        iw, ih = img.size
        if crop_rect and not fit_to_screen:
            x1, y1, x2, y2 = [int(v) for v in crop_rect]
            x1 = max(0, min(iw - 10, x1))
            y1 = max(0, min(ih - 10, y1))
            x2 = min(iw, max(x1 + 10, x2))
            y2 = min(ih, max(y1 + 10, y2))
            img = img.crop((x1, y1, x2, y2))
        res = img.resize((w, h), Image.Resampling.BILINEAR)
        if dst_path:
            res.save(dst_path, format='PNG')
            return True
        buf = io.BytesIO()
        res.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        print("Bake image error:", e)
        return False

def bake_and_save_preset_theme(gui_ref, theme_name, custom_dst_path=None):
    """Bakes background media and saves the entire theme as a single .cptheme file."""
    try:
        clean_name = _sanitize_theme_filename(theme_name)
        if not clean_name:
            return False, "Geçersiz tema adı"

        if custom_dst_path:
            if not _is_safe_local_file_path(custom_dst_path):
                return False, "Geçersiz hedef dosya yolu"
            dst_cptheme = os.path.abspath(custom_dst_path)
        else:
            themes_dir_abs = os.path.abspath(PRESET_THEMES_DIR)
            dst_cptheme = os.path.abspath(os.path.join(themes_dir_abs, f"{clean_name}.cptheme"))
            if os.path.commonpath([themes_dir_abs, dst_cptheme]) != themes_dir_abs:
                return False, "Güvenlik hatası: Hedef dizin dışına çıkılamaz"

        theme_data = dict(gui_ref.theme_data)
        theme_data['name'] = clean_name
        w = max(64, min(4096, int(theme_data.get('width', 320))))
        h = max(64, min(4096, int(theme_data.get('height', 1480))))
        bg_path = theme_data.get('bg_path')
        crop_rect = theme_data.get('crop_rect')
        fit_to_screen = bool(theme_data.get('fit_to_screen', False))

        media_bytes = b''
        media_type = 'NON0'

        if bg_path and _is_safe_local_file_path(bg_path) and os.path.isfile(bg_path):
            ext = os.path.splitext(bg_path)[1].lower()
            # Fast-path: if source is already a baked .cptheme and no new crop is pending, copy embedded media bytes directly!
            if ext == '.cptheme' and not crop_rect:
                footer = read_cptheme_footer(bg_path)
                if footer and footer[0] in ('VID0', 'IMG0') and 0 < footer[1] <= 256 * 1024 * 1024:
                    media_type = footer[0]
                    with open(bg_path, 'rb') as f:
                        media_bytes = f.read(footer[1])
                    theme_data['crop_rect'] = None
                    theme_data['fit_to_screen'] = False
                    theme_data['is_baked'] = True

            if not media_bytes:
                is_vid = ext in ['.mp4', '.avi', '.mkv', '.mov', '.webm', '.gif']
                if ext == '.cptheme':
                    footer = read_cptheme_footer(bg_path)
                    is_vid = (footer is not None and footer[0] == 'VID0')

                if is_vid:
                    tmp_mp4 = os.path.join(PRESET_THEMES_DIR, f"_tmp_bake_{os.getpid()}.mp4")
                    try:
                        ok = bake_video_background(bg_path, tmp_mp4, w=w, h=h, crop_rect=crop_rect, fit_to_screen=fit_to_screen)
                        if ok and os.path.exists(tmp_mp4):
                            with open(tmp_mp4, 'rb') as f:
                                media_bytes = f.read(256 * 1024 * 1024)
                            media_type = 'VID0'
                            theme_data['crop_rect'] = None
                            theme_data['fit_to_screen'] = False
                            theme_data['is_baked'] = True
                    finally:
                        if os.path.exists(tmp_mp4):
                            try:
                                os.remove(tmp_mp4)
                            except Exception:
                                pass
                elif ext in ['.png', '.jpg', '.jpeg', '.bmp', '.webp', '.cptheme']:
                    png_bytes = bake_image_background(bg_path, dst_path=None, w=w, h=h, crop_rect=crop_rect, fit_to_screen=fit_to_screen)
                    if isinstance(png_bytes, (bytes, bytearray)) and len(png_bytes) > 0:
                        media_bytes = bytes(png_bytes)
                        media_type = 'IMG0'
                        theme_data['crop_rect'] = None
                        theme_data['fit_to_screen'] = False
                        theme_data['is_baked'] = True

        ok_write = write_cptheme_file(dst_cptheme, theme_data, media_bytes=media_bytes, media_type=media_type)
        if not ok_write:
            return False, "Dosya yazılamadı"

        if not custom_dst_path:
            gui_ref.theme_data['name'] = clean_name
            if media_type in ('VID0', 'IMG0'):
                gui_ref.theme_data['bg_path'] = os.path.abspath(dst_cptheme)
                gui_ref.theme_data['crop_rect'] = None
                gui_ref.theme_data['fit_to_screen'] = False
                gui_ref.theme_data['is_baked'] = True
            gui_ref.save_theme_to_disk()

        return True, clean_name
    except Exception as e:
        return False, str(e)

def get_python_exe():
    py_dir = os.path.dirname(sys.executable)
    pyw = os.path.join(py_dir, "pythonw.exe")
    if os.path.exists(pyw):
        return pyw
    return sys.executable

def generate_cyberpulse_logo():
    img = Image.new('RGBA', (128, 128), (9, 13, 22, 255))
    draw = ImageDraw.Draw(img)
    
    draw.ellipse([12, 12, 116, 116], outline=(99, 102, 241, 255), width=6)
    draw.ellipse([20, 20, 108, 108], outline=(6, 182, 212, 180), width=3)
    
    points = [(28, 64), (45, 64), (55, 32), (65, 96), (75, 48), (85, 64), (100, 64)]
    draw.line(points, fill=(16, 185, 129, 255), width=5)
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qimg = QImage()
    qimg.loadFromData(buf.getvalue())
    return QIcon(QPixmap.fromImage(qimg)), QPixmap.fromImage(qimg)

def pil_to_pixmap(pil_img):
    """⚡ ZERO-COPY RAW RGB888 CONVERSION (<0.25ms vs 18ms PNG encode)."""
    if pil_img.mode != 'RGB':
        pil_img = pil_img.convert('RGB')
    w, h = pil_img.size
    raw_data = pil_img.tobytes('raw', 'RGB')
    qimg = QImage(raw_data, w, h, w * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)

def set_windows_autostart(enable=True):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
        if getattr(sys, 'frozen', False):
            app_cmd = f'"{os.path.abspath(sys.executable)}" --autostart'
        else:
            py_exe = get_python_exe()
            app_cmd = f'"{py_exe}" "{os.path.abspath(__file__)}" --autostart'
        if enable:
            winreg.SetValueEx(key, "CyberPulseLCDStudio", 0, winreg.REG_SZ, app_cmd)
        else:
            try:
                winreg.DeleteValue(key, "CyberPulseLCDStudio")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print("Autostart registry note:", e)

class HardwareStreamWorker(QThread):
    frame_ready = pyqtSignal(object)
    screen_frame_ready = pyqtSignal(str, object)

    def __init__(self, gui_ref):
        super().__init__()
        self.gui = gui_ref
        self.is_running = True
        self._last_sent_sig = None
        self._last_sent_time = 0.0

    def _theme_has_continuous_motion(self, theme_data):
        bg_path = theme_data.get('bg_path') or ''
        ext = os.path.splitext(bg_path)[1].lower()
        if ext == '.cptheme':
            footer = read_cptheme_footer(bg_path)
            if footer and footer[0] == 'VID0':
                return True
        elif ext in ('.mp4', '.avi', '.mkv', '.mov', '.gif', '.webm'):
            return True

        for el in list(theme_data.get('elements') or []):
            if not isinstance(el, dict):
                continue
            if el.get('type') in ('animated_fan', 'marquee', 'event_countdown'):
                return True
            if el.get('animEffect', 'none') != 'none':
                return True
        return False

    def run(self):
        target_fps = 20  # 20 FPS gives silky smooth animations while keeping CPU footprint near 0%
        frame_interval = 1.0 / target_fps
        while self.is_running:
            try:
                if self.gui.is_streaming and not getattr(self.gui, 'is_cropping', False):
                    t0 = time.perf_counter()
                    metrics = self.gui.sensor.get_sensors(refresh_interval_sec=self.gui.theme_data.get('refresh_sec', 1.0))

                    # 🖥️ Multi-Screen Independent Workspace Streaming Engine:
                    # Each enabled screen workspace renders its own independent theme_data via its own HardwareDriver!
                    streaming_workspaces = (
                        self.gui.get_active_streaming_workspaces()
                        if hasattr(self.gui, 'get_active_streaming_workspaces')
                        else []
                    )

                    if streaming_workspaces:
                        metrics_tuple = None
                        active_edit_slot = str(getattr(self.gui, 'active_screen_slot_id', '') or '')
                        for ws in streaming_workspaces:
                            try:
                                t_data = ws.get('theme_data')
                                hw = ws.get('hardware')
                                if not isinstance(t_data, dict) or hw is None:
                                    continue

                                s_type = ws.get('screen_type', 'usb_serial')
                                slot_id = str(ws.get('slot_id', ''))

                                # Skip rendering for hidden non-active HDMI monitor windows to save CPU/GPU
                                if s_type == 'hdmi_monitor' and slot_id != active_edit_slot:
                                    hdmi_win = ws.get('hdmi_window')
                                    if not (hdmi_win and hdmi_win.isVisible()):
                                        continue

                                has_motion = self._theme_has_continuous_motion(t_data)
                                if not has_motion:
                                    if metrics_tuple is None:
                                        metrics_tuple = tuple(sorted((k, str(v)) for k, v in metrics.items() if k != 'music_cover'))
                                    sig = (
                                        t_data.get('name'),
                                        t_data.get('bg_path'),
                                        t_data.get('width'),
                                        t_data.get('height'),
                                        t_data.get('rotation'),
                                        len(t_data.get('elements') or []),
                                        metrics_tuple
                                    )
                                    if sig == ws.get('_last_sent_sig') and (t0 - ws.get('_last_sent_time', 0.0)) < 1.0:
                                        continue
                                    ws['_last_sent_sig'] = sig
                                    ws['_last_sent_time'] = t0

                                hw_frame = hw.render_theme_frame(t_data, metrics, for_hardware=True)
                                upright_frame = hw.last_rendered_frame or hw_frame

                                if s_type == 'usb_serial':
                                    if not hw.is_connected:
                                        last_reconn = ws.get('_last_usb_reconnect_try', 0.0)
                                        if (t0 - last_reconn) >= 3.0:
                                            ws['_last_usb_reconnect_try'] = t0
                                            port_pref = ws.get('com_port') or self.gui.app_settings.get('selected_com_port', 'auto')
                                            hw.auto_connect(target_port=port_pref)

                                    if hw.is_connected:
                                        if hw_frame.size == (320, 1480):
                                            usb_frame = hw_frame
                                        else:
                                            target_w, target_h = 320, 1480
                                            src_w, src_h = hw_frame.size
                                            scale = min(target_w / max(1, src_w), target_h / max(1, src_h))
                                            scaled_w = max(1, int(src_w * scale))
                                            scaled_h = max(1, int(src_h * scale))
                                            scaled_img = hw_frame.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)
                                            usb_frame = Image.new('RGB', (target_w, target_h), (0, 0, 0))
                                            offset_x = (target_w - scaled_w) // 2
                                            offset_y = (target_h - scaled_h) // 2
                                            usb_frame.paste(scaled_img, (offset_x, offset_y))
                                        hw.send_pil_image(usb_frame)

                                elif s_type == 'hdmi_monitor':
                                    self.screen_frame_ready.emit(slot_id, upright_frame)
                                    self.frame_ready.emit(upright_frame)
                            except Exception as ws_err:
                                print(f"Workspace stream note ({ws.get('slot_id')}):", ws_err)

                    elapsed = time.perf_counter() - t0
                    sleep_time = max(0.008, frame_interval - elapsed)
                    time.sleep(sleep_time)
                else:
                    time.sleep(0.1)
            except Exception as e:
                print("Hardware stream thread note:", e)
                time.sleep(0.3)

    def stop(self):
        self.is_running = False
        self.wait()

class MarqueeCustomizerDialog(QDialog):
    def __init__(self, parent_gui, el_data):
        super().__init__(parent_gui)
        self.gui = parent_gui
        self.el_data = el_data
        self.setWindowTitle("📜 Kayan Yazı İçeriklerini Özel Olarak Seç")
        self.resize(520, 480)
        self.setStyleSheet(get_cyberpulse_global_stylesheet())

        current_items = el_data.get('marquee_items')
        if not current_items:
            current_items = ['cpu_spec', 'gpu_spec', 'ram_spec', 'cpu_temp', 'gpu_temp', 'game_fps', 'net_down', 'net_up', 'net_ping']
        self.current_items = set(current_items)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("📜 Kayan Şeritte Gösterilecek Donanım & Sensör Bilgileri")
        title.setStyleSheet("font-size: 15px; font-weight: 800; color: #818cf8; margin-bottom: 8px;")
        layout.addWidget(title)

        self.checkboxes = {}
        options = [
            ('cpu_spec', 'CPU - İşlemci Detaylı Modeli (Örn: CPU: AMD Ryzen 7 7800X3D)'),
            ('gpu_spec', 'GPU - Ekran Kartı Modeli & VRAM (Örn: GPU: NVIDIA GeForce RTX 5070 12GB)'),
            ('ram_spec', 'RAM - Bellek Modeli & MHz (Örn: RAM: 32 GB DDR5 6000 MHz)'),
            ('cpu_temp', 'CPU Temp - Canlı İşlemci Sıcaklığı (Örn: CPU Temp: 66°C)'),
            ('gpu_temp', 'GPU Temp - Canlı Ekran Kartı Sıcaklığı (Örn: GPU Temp: 48°C)'),
            ('game_fps', 'FPS - Canlı Oyun FPS Göstergesi (Örn: FPS: 144 FPS)'),
            ('ram_used', 'RAM Used - Canlı Bellek Kullanımı (Örn: RAM Used: 16.3 GB)'),
            ('net_down', 'DL - İndirme Hızı (Örn: DL: 12.4 MB/s)'),
            ('net_up', 'UL - Yükleme Hızı (Örn: UL: 2.1 MB/s)'),
            ('net_ping', 'PING - İnternet Gecikme Süresi (Örn: PING: 14 ms)'),
            ('time_digital', 'TIME - Dijital Saat (Örn: TIME: 22:45:00)'),
            ('date_full', 'DATE - Tarih (Örn: DATE: 12.08.2026)')
        ]

        grp_box = QGroupBox("Görüntülenecek Öğeler:")
        grp_layout = QVBoxLayout(grp_box)

        for key, lbl in options:
            chk = QCheckBox(lbl)
            chk.setChecked(key in self.current_items)
            self.checkboxes[key] = chk
            grp_layout.addWidget(chk)

        layout.addWidget(grp_box)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_save = QPushButton("✅ Seçimleri Kaydet ve Uygula")
        btn_save.setStyleSheet("background: #10b981; color: white; font-weight: 700; padding: 9px 20px; border-radius: 6px;")
        btn_save.clicked.connect(self.save_choices)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def save_choices(self):
        selected = [key for key, chk in self.checkboxes.items() if chk.isChecked()]
        self.el_data['marquee_items'] = selected
        self.gui.save_theme_to_disk()
        self.accept()

class ThresholdSettingsDialog(QDialog):
    def __init__(self, parent_gui, el_data):
        super().__init__(parent_gui)
        self.gui = parent_gui
        self.el_data = el_data
        self.setWindowTitle("🎨 Dinamik Yüzde Renk Eşiklerini Özelleştir")
        self.resize(480, 360)
        self.setStyleSheet("""
            QDialog { background-color: #090d16; color: #f8fafc; }
            QLabel { color: #ffffff; font-size: 13px; font-weight: 600; }
            QSpinBox { background: #0f172a; border: 1px solid #6366f1; border-radius: 5px; padding: 6px; color: #ffffff; font-size: 14px; font-weight: bold; }
            QPushButton { background: #1e293b; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 8px 12px; color: #f8fafc; font-weight: 600; }
            QPushButton:hover { background: #334155; border-color: #6366f1; }
        """)

        self.t_low_color = el_data.get('tLowColor', '#10b981')
        self.t_mid_color = el_data.get('tMidColor', '#fbbf24')
        self.t_high_color = el_data.get('tHighColor', '#ef4444')

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("🎨 Renk Değişim Eşikleri & Özel Renkler")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #818cf8; margin-bottom: 10px;")
        layout.addWidget(title)

        low_box = QHBoxLayout()
        low_box.addWidget(QLabel("Düşük Yük / Sıcaklık Eşiği (%):"))
        self.spin_low = QSpinBox()
        self.spin_low.setRange(1, 99)
        self.spin_low.setValue(int(self.el_data.get('tLowPct', 50)))
        low_box.addWidget(self.spin_low)

        self.btn_low_col = QPushButton("🟢 Düşük Renk")
        self.btn_low_col.setStyleSheet(f"background: {self.t_low_color}; color: white; font-weight: bold;")
        self.btn_low_col.clicked.connect(self.pick_low_color)
        low_box.addWidget(self.btn_low_col)
        layout.addLayout(low_box)

        high_box = QHBoxLayout()
        high_box.addWidget(QLabel("Yüksek Yük / Sıcaklık Eşiği (%):"))
        self.spin_high = QSpinBox()
        self.spin_high.setRange(2, 100)
        self.spin_high.setValue(int(self.el_data.get('tHighPct', 80)))
        high_box.addWidget(self.spin_high)

        self.btn_mid_col = QPushButton("🟡 Orta Renk")
        self.btn_mid_col.setStyleSheet(f"background: {self.t_mid_color}; color: black; font-weight: bold;")
        self.btn_mid_col.clicked.connect(self.pick_mid_color)
        high_box.addWidget(self.btn_mid_col)
        layout.addLayout(high_box)

        crit_box = QHBoxLayout()
        crit_box.addWidget(QLabel("Kritik Yüksek Renk (Eşik Üstü):"))
        self.btn_high_col = QPushButton("🔴 Kritik Renk")
        self.btn_high_col.setStyleSheet(f"background: {self.t_high_color}; color: white; font-weight: bold;")
        self.btn_high_col.clicked.connect(self.pick_high_color)
        crit_box.addWidget(self.btn_high_col)
        layout.addLayout(crit_box)

        layout.addStretch()

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_save = QPushButton("✅ Ayarları Kaydet ve Uygula")
        btn_save.setStyleSheet("background: #10b981; color: white; font-weight: 700; padding: 9px 20px; border-radius: 6px;")
        btn_save.clicked.connect(self.save_settings)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def pick_low_color(self):
        col = QColorDialog.getColor()
        if col.isValid():
            self.t_low_color = col.name()
            self.btn_low_col.setStyleSheet(f"background: {self.t_low_color}; color: white; font-weight: bold;")

    def pick_mid_color(self):
        col = QColorDialog.getColor()
        if col.isValid():
            self.t_mid_color = col.name()
            self.btn_mid_col.setStyleSheet(f"background: {self.t_mid_color}; color: black; font-weight: bold;")

    def pick_high_color(self):
        col = QColorDialog.getColor()
        if col.isValid():
            self.t_high_color = col.name()
            self.btn_high_col.setStyleSheet(f"background: {self.t_high_color}; color: white; font-weight: bold;")

    def save_settings(self):
        self.el_data['tLowPct'] = self.spin_low.value()
        self.el_data['tHighPct'] = self.spin_high.value()
        self.el_data['tLowColor'] = self.t_low_color
        self.el_data['tMidColor'] = self.t_mid_color
        self.el_data['tHighColor'] = self.t_high_color
        self.gui.save_theme_to_disk()
        self.accept()

class ThemePresetManagerDialog(QDialog):
    def __init__(self, parent_gui):
        super().__init__(parent_gui)
        self.gui = parent_gui
        self.setWindowTitle("🎨 Tema Şablonları & Tek Dosya (.cptheme) Yöneticisi")
        self.resize(940, 720)
        self.setStyleSheet(get_cyberpulse_global_stylesheet())

        self.selected_theme_data = None
        self._res_filter_updating = False
        self.init_ui()
        self.refresh_theme_list()

    def _get_active_screen_resolution(self):
        td = getattr(self.gui, 'theme_data', None) or {}
        return max(64, int(td.get('width', 320))), max(64, int(td.get('height', 1480)))

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Stitch v2.4 Top Header with .CPTHEME V2.4 Badge
        hdr_row = QHBoxLayout()
        hdr_vbox = QVBoxLayout()
        hdr_vbox.setSpacing(2)

        title_row = QHBoxLayout()
        title = QLabel("🎨 Tema Şablonları Yöneticisi")
        title.setStyleSheet("font-size: 17px; font-weight: 900; color: #f8fafc; letter-spacing: 0.3px;")
        title_row.addWidget(title)
        title_row.addStretch()
        hdr_vbox.addLayout(title_row)

        active_slot_title = getattr(self.gui, 'get_active_screen_title', lambda: "Aktif Ekran")()
        aw, ah = self._get_active_screen_resolution()
        target_badge = QLabel(
            f"Çözünürlüğe göre gruplanmış şablonlar, canlı donanım önizlemesi ve tek dosya paketleme  •  "
            f"🎯 Hedef: {active_slot_title} ({aw}×{ah})"
        )
        target_badge.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600;")
        hdr_vbox.addWidget(target_badge)
        hdr_row.addLayout(hdr_vbox, stretch=1)
        layout.addLayout(hdr_row)

        main_split = QHBoxLayout()
        main_split.setSpacing(14)

        left_vbox = QVBoxLayout()
        left_vbox.setSpacing(8)

        # Search + Resolution Group Filter Row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self.txt_theme_search = QLineEdit()
        self.txt_theme_search.setPlaceholderText("🔍 Tema adı veya çözünürlük ara...")
        self.txt_theme_search.setClearButtonEnabled(True)
        self.txt_theme_search.textChanged.connect(lambda _txt: self.refresh_theme_list(preserve_filter=True))
        filter_row.addWidget(self.txt_theme_search, stretch=2)

        lbl_flt = QLabel("📐 Grup:")
        lbl_flt.setStyleSheet("color: #cbd5e1; font-size: 12px; font-weight: 700;")
        filter_row.addWidget(lbl_flt)

        self.combo_res_filter = QComboBox()
        self.combo_res_filter.currentIndexChanged.connect(self.on_res_filter_changed)
        filter_row.addWidget(self.combo_res_filter, stretch=3)
        left_vbox.addLayout(filter_row)

        self.theme_list = QListWidget()
        self.theme_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.theme_list.setStyleSheet("""
            QListWidget {
                background-color: #060e20;
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 6px;
                outline: none;
            }
            QListWidget::item {
                background-color: transparent;
                padding: 0px;
                margin-bottom: 6px;
                border-radius: 8px;
            }
            QListWidget::item:selected {
                background-color: rgba(128, 131, 255, 0.22);
                border: 1px solid #8083ff;
            }
        """)
        self.theme_list.itemClicked.connect(self.on_theme_selected)
        self.theme_list.itemDoubleClicked.connect(self.on_theme_double_clicked)
        left_vbox.addWidget(self.theme_list, stretch=1)

        btn_save_new = QPushButton(f"💾 Mevcut ({aw}×{ah}) Temayı Tek Dosya (.cptheme) Olarak Kaydet")
        btn_save_new.setStyleSheet(
            "background: #10b981; color: #002113; font-weight: 900; padding: 9px 12px; border-radius: 7px; border: none;"
        )
        btn_save_new.clicked.connect(self.save_current_as_new_preset)
        left_vbox.addWidget(btn_save_new)

        io_box = QHBoxLayout()
        io_box.setSpacing(8)
        btn_import = QPushButton("📥 .cptheme İçe Aktar")
        btn_import.setStyleSheet("background: #171f33; border: 1px solid #334155; color: #38bdf8; font-weight: 800; padding: 8px;")
        btn_import.clicked.connect(self.import_cptheme_file)
        io_box.addWidget(btn_import)

        btn_export = QPushButton("📤 Seçili Temayı Dışa Aktar")
        btn_export.setStyleSheet("background: #171f33; border: 1px solid #334155; color: #c0c1ff; font-weight: 800; padding: 8px;")
        btn_export.clicked.connect(self.export_selected_cptheme)
        io_box.addWidget(btn_export)

        btn_open_rot = QPushButton("🎠 Oto Döngü Havuzu...")
        btn_open_rot.setToolTip("Her ekran için hangi temaların otomatik sırayla/rastgele değişeceğini seçin")
        btn_open_rot.setStyleSheet("background: #222a3d; border: 1px solid #8083ff; color: #e0e7ff; font-weight: 800; padding: 8px;")
        btn_open_rot.clicked.connect(self.open_per_screen_rotation_dialog)
        io_box.addWidget(btn_open_rot)
        left_vbox.addLayout(io_box)

        main_split.addLayout(left_vbox, stretch=3)

        # Right Column: Stitch Live Hardware Render Preview + Preset File Inspector Card
        right_vbox = QVBoxLayout()
        right_vbox.setSpacing(8)

        prev_hdr = QHBoxLayout()
        self.lbl_preview_title = QLabel("CANLI ÖNİZLEME")
        self.lbl_preview_title.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 900; letter-spacing: 0.8px;")
        prev_hdr.addWidget(self.lbl_preview_title)
        prev_hdr.addStretch()
        right_vbox.addLayout(prev_hdr)

        self.lbl_preview = QLabel("Bir tema seçin...")
        self.lbl_preview.setFixedSize(290, 415)
        self.lbl_preview.setStyleSheet(
            "background: #060e20; border: 1px solid #1e293b; border-radius: 10px; color: #64748b;"
        )
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        right_vbox.addWidget(self.lbl_preview, alignment=Qt.AlignCenter)

        # Stitch Preset File Inspector Card
        insp_card = QFrame()
        insp_card.setStyleSheet(
            "QFrame { background-color: #131b2e; border: 1px solid #1e293b; border-radius: 9px; }"
        )
        insp_vbox = QVBoxLayout(insp_card)
        insp_vbox.setContentsMargins(10, 8, 10, 8)
        insp_vbox.setSpacing(6)

        lbl_insp_hdr = QLabel("ⓘ ŞABLON BİLGİLERİ")
        lbl_insp_hdr.setStyleSheet("color: #38bdf8; font-size: 10px; font-weight: 900; letter-spacing: 0.6px; border: none;")
        insp_vbox.addWidget(lbl_insp_hdr)

        grid_row1 = QHBoxLayout()
        grid_row1.setSpacing(6)
        self.lbl_insp_file = QLabel("📦 Dosya: —")
        self.lbl_insp_file.setStyleSheet(
            "background: #171f33; border: 1px solid #222a3d; border-radius: 6px; padding: 5px 8px; "
            "color: #e2e8f0; font-size: 11px; font-weight: 700;"
        )
        grid_row1.addWidget(self.lbl_insp_file, stretch=1)

        self.lbl_insp_layers = QLabel("🎛️ Katman: —")
        self.lbl_insp_layers.setStyleSheet(
            "background: #171f33; border: 1px solid #222a3d; border-radius: 6px; padding: 5px 8px; "
            "color: #c0c1ff; font-size: 11px; font-weight: 700;"
        )
        grid_row1.addWidget(self.lbl_insp_layers, stretch=1)
        insp_vbox.addLayout(grid_row1)

        grid_row2 = QHBoxLayout()
        grid_row2.setSpacing(6)
        self.lbl_insp_res = QLabel("📐 Çözünürlük: —")
        self.lbl_insp_res.setStyleSheet(
            "background: #171f33; border: 1px solid #222a3d; border-radius: 6px; padding: 5px 8px; "
            "color: #38bdf8; font-size: 11px; font-weight: 700;"
        )
        grid_row2.addWidget(self.lbl_insp_res, stretch=1)

        self.lbl_insp_fps = QLabel("⏱️ Yenileme: —")
        self.lbl_insp_fps.setStyleSheet(
            "background: #171f33; border: 1px solid #222a3d; border-radius: 6px; padding: 5px 8px; "
            "color: #4edea3; font-size: 11px; font-weight: 700;"
        )
        grid_row2.addWidget(self.lbl_insp_fps, stretch=1)
        insp_vbox.addLayout(grid_row2)

        right_vbox.addWidget(insp_card)

        main_split.addLayout(right_vbox, stretch=2)
        layout.addLayout(main_split, stretch=1)

        # Bottom Action Footer Bar
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_delete = QPushButton("🗑️ Temayı Sil")
        btn_delete.setStyleSheet(
            "background: #3b1219; border: 1px solid #7f1d1d; color: #ffb4ab; font-weight: 800; padding: 9px 18px; border-radius: 7px;"
        )
        btn_delete.clicked.connect(self.delete_selected_theme)
        btn_box.addWidget(btn_delete)

        btn_box.addStretch()

        btn_apply_all_screens = QPushButton("🖥️ Tüm Ekranlara Uygula")
        btn_apply_all_screens.setToolTip("Seçili temayı tüm bağlı ekranların tema oluşturucularına aynı anda uygular")
        btn_apply_all_screens.setStyleSheet(
            "background: #8083ff; color: #07006c; font-weight: 900; padding: 9px 18px; font-size: 12px; border-radius: 7px; border: none;"
        )
        btn_apply_all_screens.clicked.connect(lambda: self.apply_and_close(apply_to_all_screens=True))
        btn_box.addWidget(btn_apply_all_screens)

        btn_apply = QPushButton("⚡ Seçili Ekrana Yükle ve Kullan")
        btn_apply.setStyleSheet(
            "background: #10b981; color: #002113; font-weight: 900; padding: 9px 22px; font-size: 13px; border-radius: 7px; border: none;"
        )
        btn_apply.clicked.connect(lambda: self.apply_and_close(apply_to_all_screens=False))
        btn_box.addWidget(btn_apply)

        layout.addLayout(btn_box)

    def on_res_filter_changed(self, _idx):
        if self._res_filter_updating:
            return
        self.refresh_theme_list(preserve_filter=True)

    def on_theme_double_clicked(self, item):
        if not item:
            return
        t_info = item.data(Qt.UserRole)
        if not t_info or not isinstance(t_info, dict):
            return
        self.apply_and_close()

    def refresh_theme_list(self, preserve_filter=False):
        try:
            current_filter = self.combo_res_filter.currentData() if (preserve_filter and hasattr(self, 'combo_res_filter')) else "all"
            if not current_filter:
                current_filter = "all"

            search_q = ""
            if hasattr(self, 'txt_theme_search') and self.txt_theme_search:
                search_q = self.txt_theme_search.text().strip().lower()

            self.theme_list.clear()
            themes = get_all_preset_themes()
            aw, ah = self._get_active_screen_resolution()
            active_res_key = f"{aw}x{ah}"

            # Group themes by resolution
            groups = {}
            for t_info in themes:
                mw = int(t_info.get('width', 320))
                mh = int(t_info.get('height', 1480))
                rkey = f"{mw}x{mh}"
                groups.setdefault(rkey, {'w': mw, 'h': mh, 'items': []})['items'].append(t_info)

            # Sort resolution groups: Active screen resolution first, then by total pixel count / orientation
            def _group_sort_key(rk):
                g = groups[rk]
                is_active = 0 if rk == active_res_key else 1
                return (is_active, -(g['w'] * g['h']), rk)

            sorted_rkeys = sorted(groups.keys(), key=_group_sort_key)

            # Populate filter combo
            if hasattr(self, 'combo_res_filter'):
                self._res_filter_updating = True
                self.combo_res_filter.clear()
                self.combo_res_filter.addItem(f"🌐 Tüm Çözünürlükler — Gruplu ({len(themes)} Tema)", "all")
                active_cnt = len(groups.get(active_res_key, {}).get('items', []))
                self.combo_res_filter.addItem(f"🎯 Sadece Aktif Ekran Çözünürlüğü: {aw}×{ah} ({active_cnt} Tema)", "match_active")
                for rk in sorted_rkeys:
                    g = groups[rk]
                    lbl = _format_resolution_group_title(g['w'], g['h'])
                    self.combo_res_filter.addItem(f"📐 {lbl} — {len(g['items'])} Tema", rk)
                f_idx = self.combo_res_filter.findData(current_filter)
                self.combo_res_filter.setCurrentIndex(f_idx if f_idx >= 0 else 0)
                self._res_filter_updating = False
                current_filter = self.combo_res_filter.currentData() or "all"

            if not themes:
                self.theme_list.addItem("Kayıtlı tema bulunamadı.")
                return

            first_selectable_row = -1
            for rk in sorted_rkeys:
                if current_filter == "match_active" and rk != active_res_key:
                    continue
                elif current_filter not in ("all", "match_active") and rk != current_filter:
                    continue

                g = groups[rk]
                matching_items = []
                for t_info in g['items']:
                    if search_q:
                        haystack = f"{t_info.get('name', '')} {g['w']}x{g['h']} {g['w']}×{g['h']}".lower()
                        if search_q not in haystack:
                            continue
                    matching_items.append(t_info)

                if not matching_items:
                    continue

                grp_title = _format_resolution_group_title(g['w'], g['h'])
                is_active_grp = (rk == active_res_key)
                hdr_item = QListWidgetItem("")
                hdr_item.setFlags(Qt.ItemIsEnabled)
                hdr_item.setData(Qt.UserRole, None)
                hdr_item.setSizeHint(QSize(380, 34))
                self.theme_list.addItem(hdr_item)

                hdr_card = QFrame()
                hdr_border_col = "#4edea3" if is_active_grp else "#8083ff"
                hdr_card.setStyleSheet(f"""
                    QFrame {{
                        background-color: #131b2e;
                        border: 1px solid #222a3d;
                        border-left: 3px solid {hdr_border_col};
                        border-radius: 7px;
                    }}
                """)
                hc_lay = QHBoxLayout(hdr_card)
                hc_lay.setContentsMargins(10, 4, 10, 4)
                hc_lay.setSpacing(8)
                lbl_hc_t = QLabel(f"📐 {grp_title} • {len(matching_items)} TEMA")
                lbl_hc_t.setStyleSheet(
                    f"color: {'#4edea3' if is_active_grp else '#c0c1ff'}; font-family: 'Consolas', monospace; font-size: 11px; font-weight: 900; border: none; background: transparent;"
                )
                hc_lay.addWidget(lbl_hc_t)
                hc_lay.addStretch()
                if is_active_grp:
                    act_b = QLabel("★ AKTİF EKRAN ÇÖZÜNÜRLÜĞÜ")
                    act_b.setStyleSheet("background: rgba(78, 222, 163, 0.16); color: #4edea3; border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: 900; border: none;")
                    hc_lay.addWidget(act_b)
                self.theme_list.setItemWidget(hdr_item, hdr_card)

                curr_loaded_name = str(getattr(self.gui, 'theme_data', {}).get('name', '')).strip().lower()
                for t_info in matching_items:
                    mw, mh = g['w'], g['h']
                    t_name = str(t_info.get('name', 'Tema'))
                    is_curr_loaded = (t_name.strip().lower() == curr_loaded_name)
                    item = QListWidgetItem("")
                    item.setData(Qt.UserRole, t_info)
                    item.setSizeHint(QSize(380, 68))
                    self.theme_list.addItem(item)
                    row_idx = self.theme_list.count() - 1
                    if first_selectable_row < 0:
                        first_selectable_row = row_idx

                    # Build Stitch Theme Card Widget (#131b2e / #171f33)
                    t_card = QFrame()
                    left_accent = "border-left: 3px solid #4edea3;" if is_curr_loaded else "border-left: 3px solid #8083ff;"
                    t_card.setStyleSheet(f"""
                        QFrame {{
                            background-color: {'#171f33' if is_curr_loaded else '#131b2e'};
                            border: 1px solid #222a3d;
                            {left_accent}
                            border-radius: 8px;
                        }}
                        QFrame:hover {{
                            background-color: #222a3d;
                            border-color: #8083ff;
                        }}
                    """)
                    tc_lay = QHBoxLayout(t_card)
                    tc_lay.setContentsMargins(10, 6, 10, 6)
                    tc_lay.setSpacing(10)

                    ic_box = QLabel("📦" if t_info.get('is_cptheme') else "🎨")
                    ic_box.setFixedSize(40, 40)
                    ic_box.setAlignment(Qt.AlignCenter)
                    ic_box.setStyleSheet("background: #060e20; border: 1px solid #222a3d; border-radius: 7px; font-size: 16px;")
                    tc_lay.addWidget(ic_box)

                    mid_v = QVBoxLayout()
                    mid_v.setContentsMargins(0, 0, 0, 0)
                    mid_v.setSpacing(2)

                    top_r = QHBoxLayout()
                    top_r.setSpacing(6)
                    lbl_tn = QLabel(t_name)
                    lbl_tn.setStyleSheet("color: #dae2fd; font-size: 12px; font-weight: 900; border: none; background: transparent;")
                    top_r.addWidget(lbl_tn)

                    lbl_res_b = QLabel(f"{mw}×{mh}")
                    lbl_res_b.setStyleSheet("background: #060e20; color: #7bd0ff; border-radius: 4px; padding: 1px 6px; font-family: 'Consolas', monospace; font-size: 9px; font-weight: 800; border: none;")
                    top_r.addWidget(lbl_res_b)

                    if is_curr_loaded:
                        lbl_cur = QLabel("AKTİF YÜKLÜ")
                        lbl_cur.setStyleSheet("background: rgba(78, 222, 163, 0.16); color: #4edea3; border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 900; border: none;")
                        top_r.addWidget(lbl_cur)
                    top_r.addStretch()
                    mid_v.addLayout(top_r)

                    f_path = t_info.get('cptheme_path') or t_info.get('json_path') or ''
                    f_mb = 0.0
                    try:
                        if f_path and os.path.isfile(f_path):
                            f_mb = os.path.getsize(f_path) / (1024.0 * 1024.0)
                    except Exception:
                        pass
                    pkg_type = ".cptheme Tek Dosya Paketi" if t_info.get('is_cptheme') else "JSON Tema Şablonu"
                    sub_txt = f"{pkg_type}  •  {f_mb:.1f} MB" if f_mb > 0 else pkg_type
                    lbl_sub = QLabel(sub_txt)
                    lbl_sub.setStyleSheet("color: #908fa0; font-size: 10px; font-weight: 700; border: none; background: transparent;")
                    mid_v.addWidget(lbl_sub)

                    tc_lay.addLayout(mid_v, stretch=1)

                    btn_quick_load = QPushButton("YÜKLE")
                    btn_quick_load.setStyleSheet(
                        "QPushButton { background: #222a3d; color: #c0c1ff; border: 1px solid rgba(128,131,255,0.35); border-radius: 6px; padding: 5px 10px; font-size: 10px; font-weight: 900; } "
                        "QPushButton:hover { background: #8083ff; color: #07006c; }"
                    )
                    btn_quick_load.clicked.connect(lambda _chk=False, r=row_idx: (self.theme_list.setCurrentRow(r), self.on_theme_selected(self.theme_list.item(r)), self.apply_and_close()))
                    tc_lay.addWidget(btn_quick_load)

                    self.theme_list.setItemWidget(item, t_card)

            if first_selectable_row >= 0:
                self.theme_list.setCurrentRow(first_selectable_row)
                self.on_theme_selected(self.theme_list.currentItem())
            else:
                self.theme_list.addItem(f"Seçili filtrede ({aw}×{ah}) kayıtlı tema bulunamadı.")
        except Exception as e:
            print("Refresh theme list note:", e)

    def on_theme_selected(self, item):
        try:
            if not item:
                return
            t_info = item.data(Qt.UserRole)
            if not t_info or not isinstance(t_info, dict):
                # User clicked a category header row; jump to next selectable item if available
                row = self.theme_list.row(item)
                if row + 1 < self.theme_list.count():
                    nxt = self.theme_list.item(row + 1)
                    if nxt and isinstance(nxt.data(Qt.UserRole), dict):
                        self.theme_list.setCurrentRow(row + 1)
                        t_info = nxt.data(Qt.UserRole)
                if not t_info or not isinstance(t_info, dict):
                    return
            self.selected_theme_data = load_preset_theme_data(t_info)
            if self.selected_theme_data:
                tw = max(64, min(4096, int(self.selected_theme_data.get('width', 320))))
                th = max(64, min(4096, int(self.selected_theme_data.get('height', 1480))))
                if hasattr(self, 'lbl_preview_title'):
                    self.lbl_preview_title.setText(f"CANLI ÖNİZLEME: {t_info.get('name')} ({tw}×{th})")

                # Populate Preset File Inspector telemetry boxes
                if hasattr(self, 'lbl_insp_file'):
                    f_name = f"{t_info.get('name', 'tema')}.cptheme" if t_info.get('is_cptheme') else f"{t_info.get('name', 'tema')}.json"
                    self.lbl_insp_file.setText(f"📦 {f_name[:24]}")
                if hasattr(self, 'lbl_insp_layers'):
                    el_cnt = len(self.selected_theme_data.get('elements', []) or [])
                    self.lbl_insp_layers.setText(f"🎛️ {el_cnt} Aktif Sensör/Öge")
                if hasattr(self, 'lbl_insp_res'):
                    orient = "Dikey" if th > tw else "Yatay"
                    self.lbl_insp_res.setText(f"📐 {tw}×{th} ({orient})")
                if hasattr(self, 'lbl_insp_fps'):
                    ref_s = float(self.selected_theme_data.get('refresh_sec', 1.0) or 1.0)
                    self.lbl_insp_fps.setText(f"⏱️ {ref_s:.1f} sn • Tek Dosya")

                if not hasattr(self, '_preview_hw') or self._preview_hw is None:
                    self._preview_hw = HardwareDriver(width=tw, height=th)
                else:
                    self._preview_hw.reset_background_media()
                    self._preview_hw.set_resolution(tw, th)
                dummy_metrics = {'cpu_temp': '45°C', 'gpu_load': '65%', 'cpu_load': '40%', 'game_fps': '120 FPS'}
                preview_pil = self._preview_hw.render_theme_frame(self.selected_theme_data, dummy_metrics, for_hardware=False)
                # Immediately release any open video_cap file handle so .cptheme files are never locked on Windows!
                self._preview_hw.reset_background_media()
                box_w, box_h = 280, 405
                scale = min(float(box_w) / max(1, tw), float(box_h) / max(1, th))
                sw = max(1, int(tw * scale))
                sh = max(1, int(th * scale))
                scaled_pil = preview_pil.resize((sw, sh), Image.Resampling.BILINEAR)
                canvas_pil = Image.new('RGB', (box_w, box_h), (6, 14, 32))
                canvas_pil.paste(scaled_pil, ((box_w - sw) // 2, (box_h - sh) // 2))
                self.lbl_preview.setPixmap(pil_to_pixmap(canvas_pil))
        except Exception as e:
            print("On theme selected note:", e)

    def open_per_screen_rotation_dialog(self):
        if hasattr(self.gui, 'open_screen_auto_rotate_dialog'):
            self.gui.open_screen_auto_rotate_dialog(parent_widget=self)

    def save_current_as_new_preset(self):
        try:
            tname, ok = QInputDialog.getText(self, "Yeni Tek Dosya Tema Kaydet", "Tema Adı:")
            if ok and tname.strip():
                clean_name = tname.strip()
                ok_bake, msg = bake_and_save_preset_theme(self.gui, clean_name)
                if ok_bake:
                    QMessageBox.information(self, "Başarılı", f"Tema '{clean_name}.cptheme' tek dosya olarak optimize edilip kaydedildi!")
                    self.refresh_theme_list()
                    if hasattr(self.gui, 'refresh_multi_screen_bar_ui'):
                        self.gui.refresh_multi_screen_bar_ui()
                else:
                    QMessageBox.warning(self, "Hata", f"Tema kaydedilemedi: {msg}")
        except Exception as e:
            QMessageBox.critical(self, "Kaydetme Hatası", f"Tema kaydedilirken bir hata oluştu: {e}")

    def import_cptheme_file(self):
        try:
            src_file, _ = QFileDialog.getOpenFileName(self, "Tek Dosya Tema Paketi Seç (.cptheme)", "", "CyberPulse Tema Paketi (*.cptheme)")
            if not src_file or not _is_safe_local_file_path(src_file) or not os.path.isfile(src_file):
                return
            footer = read_cptheme_footer(src_file)
            meta = read_cptheme_metadata(src_file) if footer else None
            if not footer or not isinstance(meta, dict):
                QMessageBox.warning(self, "Geçersiz Dosya", "Seçilen dosya geçerli veya bütünlüğü doğrulanmış bir .cptheme paketi değil!")
                return
            raw_stem = os.path.splitext(os.path.basename(src_file))[0]
            safe_stem = _sanitize_theme_filename(raw_stem) or "ithal_tema"
            import shutil
            themes_dir_abs = os.path.abspath(PRESET_THEMES_DIR)
            dst_file = os.path.abspath(os.path.join(themes_dir_abs, f"{safe_stem}.cptheme"))
            if os.path.commonpath([themes_dir_abs, dst_file]) != themes_dir_abs:
                QMessageBox.warning(self, "Güvenlik Hatası", "Hedef dosya yolu geçersiz!")
                return
            if os.path.abspath(src_file) != dst_file:
                shutil.copy2(src_file, dst_file)
            self.refresh_theme_list()
            if hasattr(self.gui, 'refresh_multi_screen_bar_ui'):
                self.gui.refresh_multi_screen_bar_ui()
            QMessageBox.information(self, "İçe Aktarıldı", f"'{safe_stem}.cptheme' başarıyla temalarınıza eklendi!")
        except Exception as e:
            QMessageBox.critical(self, "İçe Aktarma Hatası", f"Tema içe aktarılırken hata oluştu: {e}")

    def export_selected_cptheme(self):
        try:
            item = self.theme_list.currentItem()
            if not item:
                return
            t_info = item.data(Qt.UserRole)
            if not t_info or not isinstance(t_info, dict):
                return
            t_name = t_info.get('name', 'tema')
            dst_file, _ = QFileDialog.getSaveFileName(self, "Temayı Tek Dosya Olarak Dışa Aktar", f"{t_name}.cptheme", "CyberPulse Tema Paketi (*.cptheme)")
            if not dst_file:
                return
            if not dst_file.lower().endswith('.cptheme'):
                dst_file += '.cptheme'
            import shutil
            if t_info.get('is_cptheme') and t_info.get('cptheme_path') and os.path.exists(t_info['cptheme_path']):
                shutil.copy2(t_info['cptheme_path'], dst_file)
                QMessageBox.information(self, "Dışa Aktarıldı", f"Tema başarıyla dışa aktarıldı:\n{dst_file}")
            else:
                ok_bake, msg = bake_and_save_preset_theme(self.gui, t_name, custom_dst_path=dst_file)
                if ok_bake:
                    QMessageBox.information(self, "Dışa Aktarıldı", f"Tema başarıyla dışa aktarıldı:\n{dst_file}")
                else:
                    QMessageBox.warning(self, "Hata", f"Dışa aktarılamadı: {msg}")
        except Exception as e:
            QMessageBox.critical(self, "Dışa Aktarma Hatası", f"Hata: {e}")

    def delete_selected_theme(self):
        try:
            item = self.theme_list.currentItem()
            if not item and self.theme_list.selectedItems():
                item = self.theme_list.selectedItems()[0]
            if not item:
                QMessageBox.information(self, "Tema Seçilmedi", "Lütfen silmek istediğiniz temayı listeden seçin.")
                return
            t_info = item.data(Qt.UserRole)
            if not t_info or not isinstance(t_info, dict):
                QMessageBox.information(self, "Bilgi", "Silinecek kayıtlı bir tema bulunamadı.")
                return

            t_name = str(t_info.get('name', 'Seçili Tema')).strip()
            reply = QMessageBox.question(
                self,
                "🗑️ Temayı Sil",
                f"'{t_name}' temasını kalıcı olarak silmek istediğinize emin misiniz?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                return

            # 1. Release preview hardware video lock if open
            if hasattr(self, '_preview_hw') and self._preview_hw is not None:
                try:
                    self._preview_hw.reset_background_media()
                except Exception:
                    pass

            # 2. Collect all target paths in PRESET_THEMES_DIR matching this theme
            themes_dir_abs = os.path.abspath(PRESET_THEMES_DIR)
            candidate_paths = set()
            for k in ('cptheme_path', 'folder', 'json_path'):
                p_val = t_info.get(k)
                if p_val and isinstance(p_val, str):
                    p_abs = os.path.abspath(p_val)
                    try:
                        if os.path.commonpath([themes_dir_abs, p_abs]) == themes_dir_abs and p_abs != themes_dir_abs and not os.path.islink(p_abs):
                            candidate_paths.add(p_abs)
                    except Exception:
                        pass

            # Also include any same-named .cptheme, .json, or folder in PRESET_THEMES_DIR so legacy copies don't resurrect it
            if os.path.isdir(themes_dir_abs) and t_name:
                t_lower = t_name.lower()
                for entry in os.listdir(themes_dir_abs):
                    entry_abs = os.path.abspath(os.path.join(themes_dir_abs, entry))
                    stem, ext = os.path.splitext(entry)
                    if entry.lower() == t_lower or (stem.lower() == t_lower and ext.lower() in ('.cptheme', '.json')):
                        candidate_paths.add(entry_abs)

            norm_candidates = {os.path.normcase(p) for p in candidate_paths}

            # 3. Release video_cap locks across all active screen workspaces and main GUI hardware
            all_hw = []
            if hasattr(self.gui, 'hardware') and self.gui.hardware:
                all_hw.append((self.gui.hardware, getattr(self.gui, 'theme_data', None)))
            for ws in list(getattr(self.gui, 'screen_workspaces', {}).values()):
                if ws.get('hardware'):
                    all_hw.append((ws['hardware'], ws.get('theme_data')))
                # Remove deleted theme from per-screen auto-rotation playlist
                rot_list = ws.get('rotate_themes')
                if isinstance(rot_list, list):
                    ws['rotate_themes'] = [x for x in rot_list if str(x).strip().lower() != t_name.lower()]

            for hw_obj, td_obj in all_hw:
                try:
                    cur_bg = os.path.normcase(os.path.abspath(str(getattr(hw_obj, 'current_bg_path', '') or ''))) if getattr(hw_obj, 'current_bg_path', None) else ''
                    td_bg = os.path.normcase(os.path.abspath(str(td_obj.get('bg_path') or ''))) if isinstance(td_obj, dict) and td_obj.get('bg_path') else ''
                    td_name = str(td_obj.get('name') or '').strip().lower() if isinstance(td_obj, dict) else ''
                    if cur_bg in norm_candidates or td_bg in norm_candidates or td_name == t_name.lower():
                        with hw_obj.render_lock:
                            hw_obj.reset_background_media()
                            if isinstance(td_obj, dict) and td_bg in norm_candidates:
                                td_obj['bg_path'] = None
                except Exception:
                    pass

            # 4. Delete files/folders from disk (with short retry in case OS handle is releasing)
            import shutil
            deleted_any = False
            last_err = None
            for target_p in candidate_paths:
                if not os.path.exists(target_p):
                    continue
                for _attempt in range(3):
                    try:
                        if os.path.isdir(target_p):
                            shutil.rmtree(target_p)
                        else:
                            os.remove(target_p)
                        deleted_any = True
                        break
                    except Exception as ex_rm:
                        last_err = ex_rm
                        time.sleep(0.08)

            if not deleted_any and last_err is not None:
                QMessageBox.warning(self, "Silme Hatası", f"Tema dosyası silinemedi:\n{last_err}")
                return

            self.selected_theme_data = None
            self.lbl_preview.clear()
            self.lbl_preview.setText("Bir tema seçin...")
            self.refresh_theme_list()

            if hasattr(self.gui, 'refresh_multi_screen_bar_ui'):
                self.gui.refresh_multi_screen_bar_ui()
            if hasattr(self.gui, 'save_theme_to_disk'):
                self.gui.save_theme_to_disk()

            QMessageBox.information(self, "Silindi", f"'{t_name}' teması başarıyla silindi.")
        except Exception as e:
            QMessageBox.warning(self, "Silme Hatası", f"Tema silinirken bir hata oluştu:\n{e}")

    def apply_and_close(self, apply_to_all_screens=False):
        try:
            if self.selected_theme_data:
                if apply_to_all_screens and hasattr(self.gui, 'screen_workspaces'):
                    for ws in list(self.gui.screen_workspaces.values()):
                        hw = ws.get('hardware')
                        t_copy = copy.deepcopy(self.selected_theme_data)
                        ws_w = int(ws.get('theme_data', {}).get('width', 320))
                        ws_h = int(ws.get('theme_data', {}).get('height', 1480))
                        src_w = int(t_copy.get('width', 320))
                        src_h = int(t_copy.get('height', 1480))
                        if (ws_w, ws_h) != (src_w, src_h):
                            adapt_theme_elements_to_resolution(t_copy, ws_w, ws_h)
                        if hw:
                            hw.reset_background_media()
                            with hw.render_lock:
                                ws['theme_data'].clear()
                                ws['theme_data'].update(t_copy)
                            hw.set_resolution(int(ws['theme_data'].get('width', 320)), int(ws['theme_data'].get('height', 1480)))
                        else:
                            ws['theme_data'].clear()
                            ws['theme_data'].update(t_copy)
                else:
                    t_copy = copy.deepcopy(self.selected_theme_data)
                    curr_w = int(self.gui.theme_data.get('width', 320))
                    curr_h = int(self.gui.theme_data.get('height', 1480))
                    src_w = int(t_copy.get('width', 320))
                    src_h = int(t_copy.get('height', 1480))
                    if (curr_w, curr_h) != (src_w, src_h) and (src_w, src_h) == (320, 1480):
                        adapt_theme_elements_to_resolution(t_copy, curr_w, curr_h)
                    self.gui.hardware.reset_background_media()
                    with self.gui.hardware.render_lock:
                        self.gui.theme_data.clear()
                        self.gui.theme_data.update(t_copy)
                    self.gui.hardware.set_resolution(int(self.gui.theme_data.get('width', 320)), int(self.gui.theme_data.get('height', 1480)))

                self.gui.update_canvas_geometry()
                if hasattr(self.gui, 'auto_adjust_window_to_canvas'):
                    self.gui.auto_adjust_window_to_canvas()
                self.gui.refresh_elements_list()
                self.gui.save_theme_to_disk()
                if hasattr(self.gui, 'refresh_multi_screen_bar_ui'):
                    self.gui.refresh_multi_screen_bar_ui()
                if hasattr(self.gui, 'lbl_bg_info'):
                    if self.gui.theme_data.get('bg_path'):
                        self.gui.lbl_bg_info.setText(f"Arka Plan: {os.path.basename(self.gui.theme_data['bg_path'])[:24]}")
                    else:
                        self.gui.lbl_bg_info.setText("Arka Plan: Varsayılan Koyu Tema")
                msg_target = "tüm ekranlara" if apply_to_all_screens else f"'{self.gui.get_active_screen_title()}' ekranına"
                QMessageBox.information(self, "Tema Yüklendi", f"Seçili tema {msg_target} başarıyla yüklendi!")
                self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Tema Yükleme Hatası", f"Tema yüklenirken hata oluştu: {e}")


class ScreenAutoRotateDialog(QDialog):
    """
    🎠 Her Ekran İçin Bağımsız Otomatik Tema Değişimi (Slayt Döngüsü) ve Özel Tema Seçici.
    Kullanıcı her ekran için ayrı ayrı hangi temaların döneceğini, hangi sırayla ve hangi sürede
    değişeceğini seçebilir.
    """
    def __init__(self, parent_gui, initial_slot_id=None, parent_widget=None):
        super().__init__(parent_widget or parent_gui)
        self.gui = parent_gui
        self.setWindowTitle("🎠 Ekran Bazlı Otomatik Tema Değişimi & Tema Seçici")
        self.resize(920, 680)
        self.setStyleSheet(get_cyberpulse_global_stylesheet())

        # Deep-copy each screen's rotation state into a working dict so switching screen tabs preserves unsaved edits
        self._slot_configs = {}
        all_presets = [t['name'] for t in get_all_preset_themes()]
        for sid, ws in list(getattr(self.gui, 'screen_workspaces', {}).items()):
            saved_list = ws.get('rotate_themes')
            if not isinstance(saved_list, list):
                saved_list = list(all_presets)
            else:
                # Keep only existing themes while preserving user order
                existing_lower = {p.lower(): p for p in all_presets}
                saved_list = [existing_lower[str(x).strip().lower()] for x in saved_list if str(x).strip().lower() in existing_lower]
            self._slot_configs[sid] = {
                'auto_rotate_enabled': bool(ws.get('auto_rotate_enabled', False)),
                'rotate_interval_val': max(1, min(9999, int(ws.get('rotate_interval_val', self.gui.app_settings.get('rotate_val', 30)) or 30))),
                'rotate_interval_unit': str(ws.get('rotate_interval_unit', self.gui.app_settings.get('rotate_unit', 'sec')) or 'sec'),
                'rotate_mode': str(ws.get('rotate_mode', self.gui.app_settings.get('rotate_mode', 'sequential')) or 'sequential'),
                'rotate_themes': saved_list
            }

        self.current_slot_id = initial_slot_id if (initial_slot_id in self._slot_configs) else getattr(self.gui, 'active_screen_slot_id', 'usb_lcd_1')
        if self.current_slot_id not in self._slot_configs and self._slot_configs:
            self.current_slot_id = next(iter(self._slot_configs.keys()))

        self._updating_ui = False
        self._res_filter_updating = False
        self.init_ui()
        self.load_slot_into_ui(self.current_slot_id)

    def _get_slot_resolution(self, slot_id=None):
        sid = slot_id or self.current_slot_id
        ws = getattr(self.gui, 'screen_workspaces', {}).get(sid, {})
        td = ws.get('theme_data', {}) or {}
        return max(64, int(td.get('width', 320))), max(64, int(td.get('height', 1480)))

    def _set_quick_duration(self, val, unit):
        self._updating_ui = True
        self.spin_val.setValue(val)
        for i in range(self.combo_unit.count()):
            if self.combo_unit.itemData(i) == unit:
                self.combo_unit.setCurrentIndex(i)
                break
        self._updating_ui = False
        self.on_ui_field_edited()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Stitch v2.4 Top Header with PLAYLIST ENGINE V2.4 Badge
        hdr_row = QHBoxLayout()
        hdr_vbox = QVBoxLayout()
        hdr_vbox.setSpacing(2)

        title_row = QHBoxLayout()
        hdr = QLabel("🎠 Ekran Bazlı Otomatik Tema Döngüsü")
        hdr.setStyleSheet("font-size: 17px; font-weight: 900; color: #f8fafc; letter-spacing: 0.3px;")
        title_row.addWidget(hdr)
        title_row.addStretch()
        hdr_vbox.addLayout(title_row)

        sub = QLabel(
            "Her ekran için bağımsız tema değişim süresi, ardışık/rastgele sıralama ve çözünürlüğe göre gruplanmış döngü havuzu"
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600;")
        hdr_vbox.addWidget(sub)
        hdr_row.addLayout(hdr_vbox, stretch=1)
        layout.addLayout(hdr_row)

        # Stitch 2-Column Split Layout
        split_row = QHBoxLayout()
        split_row.setSpacing(14)

        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        # 1. Target Hardware Display Card (#131b2e Stitch Card)
        scr_box = QFrame()
        scr_box.setStyleSheet("QFrame { background-color: #131b2e; border: 1px solid #1e293b; border-radius: 10px; }")
        scr_layout = QVBoxLayout(scr_box)
        scr_layout.setContentsMargins(14, 12, 14, 12)
        scr_layout.setSpacing(8)

        lbl_scr_hdr = QLabel("🖥  1. HEDEF EKRAN SEÇİMİ")
        lbl_scr_hdr.setStyleSheet("color: #c0c1ff; font-size: 11px; font-weight: 900; letter-spacing: 0.9px; border: none; background: transparent;")
        scr_layout.addWidget(lbl_scr_hdr)

        lbl_scr_sel = QLabel("YAPILANDIRILACAK EKRAN YUVASI:")
        lbl_scr_sel.setStyleSheet("color: #908fa0; font-size: 10px; font-weight: 800; letter-spacing: 0.6px; border: none; background: transparent;")
        scr_layout.addWidget(lbl_scr_sel)

        self.combo_screen = QComboBox()
        self.combo_screen.setStyleSheet("background: #060e20; border: 1px solid #222a3d; border-radius: 7px; padding: 7px 10px; color: #dae2fd; font-weight: 800;")
        self.combo_screen.currentIndexChanged.connect(self.on_screen_combo_changed)
        scr_layout.addWidget(self.combo_screen)

        self.lbl_slot_hw_summary = QLabel("📐 Aktif Ekran Çözünürlüğü: 320×1480")
        self.lbl_slot_hw_summary.setStyleSheet(
            "background: #060e20; border: 1px solid #1e293b; border-radius: 7px; padding: 7px 10px; "
            "color: #7bd0ff; font-family: 'Consolas', monospace; font-size: 11px; font-weight: 800;"
        )
        scr_layout.addWidget(self.lbl_slot_hw_summary)

        btn_test_now = QPushButton("⚡ Bu Ekranda Şimdi Sonraki Temayı Test Et")
        btn_test_now.setStyleSheet(
            "background: rgba(0, 166, 224, 0.14); border: 1px solid rgba(123, 208, 255, 0.35); color: #7bd0ff; font-weight: 900; padding: 8px 12px; border-radius: 7px;"
        )
        btn_test_now.clicked.connect(self.test_next_theme_on_current_screen)
        scr_layout.addWidget(btn_test_now)
        left_col.addWidget(scr_box)

        # 2. Rotation Timing & Order for Selected Screen (#131b2e Stitch Card)
        cfg_box = QFrame()
        cfg_box.setStyleSheet("QFrame { background-color: #131b2e; border: 1px solid #1e293b; border-radius: 10px; }")
        cfg_vbox = QVBoxLayout(cfg_box)
        cfg_vbox.setContentsMargins(14, 12, 14, 12)
        cfg_vbox.setSpacing(10)

        lbl_cfg_hdr = QLabel("⏱  2. DEĞİŞİM SÜRESİ VE SIRALAMA")
        lbl_cfg_hdr.setStyleSheet("color: #c0c1ff; font-size: 11px; font-weight: 900; letter-spacing: 0.9px; border: none; background: transparent;")
        cfg_vbox.addWidget(lbl_cfg_hdr)

        enable_card = QFrame()
        enable_card.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid #1e293b; border-radius: 8px; }")
        en_lay = QVBoxLayout(enable_card)
        en_lay.setContentsMargins(10, 8, 10, 8)
        self.chk_enabled = QCheckBox("✅ Bu Ekranda Otomatik Tema Değişimini Etkinleştir")
        self.chk_enabled.setStyleSheet("color: #4edea3; font-size: 12px; font-weight: 800; border: none; background: transparent;")
        self.chk_enabled.stateChanged.connect(self.on_ui_field_edited)
        en_lay.addWidget(self.chk_enabled)
        cfg_vbox.addWidget(enable_card)

        lbl_dur_hdr = QLabel("⏱️ TEMA DEĞİŞİM SÜRESİ (INTERVAL):")
        lbl_dur_hdr.setStyleSheet("color: #908fa0; font-size: 10px; font-weight: 800; letter-spacing: 0.6px; border: none; background: transparent;")
        cfg_vbox.addWidget(lbl_dur_hdr)

        row_time = QHBoxLayout()
        row_time.setSpacing(6)
        self.spin_val = QSpinBox()
        self.spin_val.setRange(1, 9999)
        self.spin_val.setStyleSheet("background: #060e20; border: 1px solid #222a3d; border-radius: 6px; padding: 6px 10px; color: #dae2fd; font-family: 'Consolas', monospace; font-size: 13px; font-weight: 900;")
        self.spin_val.valueChanged.connect(self.on_ui_field_edited)
        row_time.addWidget(self.spin_val, stretch=1)

        self.combo_unit = QComboBox()
        self.combo_unit.setStyleSheet("background: #060e20; border: 1px solid #222a3d; border-radius: 6px; padding: 6px 10px; color: #dae2fd; font-weight: 800;")
        self.combo_unit.addItem("⏱️ Saniye", "sec")
        self.combo_unit.addItem("⏱️ Dakika", "min")
        self.combo_unit.addItem("⏱️ Saat", "hour")
        self.combo_unit.currentIndexChanged.connect(self.on_ui_field_edited)
        row_time.addWidget(self.combo_unit, stretch=1)
        cfg_vbox.addLayout(row_time)

        # Stitch Quick Duration Pills (15s, 30s, 1m, 5m)
        quick_dur_row = QHBoxLayout()
        quick_dur_row.setSpacing(6)
        for q_lbl, q_val, q_unit in [("15 sn", 15, "sec"), ("30 sn", 30, "sec"), ("1 dk", 1, "min"), ("5 dk", 5, "min")]:
            q_btn = QPushButton(q_lbl)
            q_btn.setStyleSheet(
                "QPushButton { background: #060e20; border: 1px solid #222a3d; color: #c0c1ff; font-family: 'Consolas', monospace; font-size: 11px; font-weight: 800; padding: 5px 8px; border-radius: 6px; } "
                "QPushButton:hover { background: #8083ff; color: #07006c; }"
            )
            q_btn.clicked.connect(lambda _chk=False, v=q_val, u=q_unit: self._set_quick_duration(v, u))
            quick_dur_row.addWidget(q_btn)
        cfg_vbox.addLayout(quick_dur_row)

        lbl_mode_hdr = QLabel("🔀 DEĞİŞİM SIRALAMA MODU:")
        lbl_mode_hdr.setStyleSheet("color: #908fa0; font-size: 10px; font-weight: 800; letter-spacing: 0.6px; border: none; background: transparent;")
        cfg_vbox.addWidget(lbl_mode_hdr)

        self.combo_mode = QComboBox()
        self.combo_mode.setStyleSheet("background: #060e20; border: 1px solid #222a3d; border-radius: 6px; padding: 6px 10px; color: #dae2fd; font-weight: 800;")
        self.combo_mode.addItem("📋 Sırayla (Seçili Temalar Arasında Ardışık)", "sequential")
        self.combo_mode.addItem("🎲 Karışık (Seçili Temalar Arasında Rastgele)", "random")
        self.combo_mode.currentIndexChanged.connect(self.on_ui_field_edited)
        cfg_vbox.addWidget(self.combo_mode)

        left_col.addWidget(cfg_box)
        left_col.addStretch()
        split_row.addLayout(left_col, stretch=2)

        # 3. Right Column: Checkable Theme Playlist for Selected Screen (#131b2e Stitch Card)
        right_col = QVBoxLayout()
        list_box = QFrame()
        list_box.setStyleSheet("QFrame { background-color: #131b2e; border: 1px solid #1e293b; border-radius: 10px; }")
        list_vbox = QVBoxLayout(list_box)
        list_vbox.setContentsMargins(14, 12, 14, 12)
        list_vbox.setSpacing(8)

        lbl_list_hdr = QLabel("🎶  3. DÖNGÜYE DAHİL EDİLECEK TEMALAR")
        lbl_list_hdr.setStyleSheet("color: #c0c1ff; font-size: 11px; font-weight: 900; letter-spacing: 0.9px; border: none; background: transparent;")
        list_vbox.addWidget(lbl_list_hdr)

        filter_row = QHBoxLayout()
        lbl_flt = QLabel("📐 Çözünürlük Grubu:")
        lbl_flt.setStyleSheet("color: #908fa0; font-weight: 800; font-size: 11px; border: none; background: transparent;")
        filter_row.addWidget(lbl_flt)

        self.combo_res_filter = QComboBox()
        self.combo_res_filter.setStyleSheet("background: #060e20; border: 1px solid #222a3d; border-radius: 6px; padding: 5px 10px; color: #dae2fd; font-weight: 800;")
        self.combo_res_filter.currentIndexChanged.connect(self.on_res_filter_changed)
        filter_row.addWidget(self.combo_res_filter, stretch=1)

        self.lbl_count_info = QLabel("Seçili Tema Sayısı: 0")
        self.lbl_count_info.setStyleSheet(
            "background: rgba(78, 222, 163, 0.14); color: #4edea3; border: 1px solid rgba(78, 222, 163, 0.35); "
            "border-radius: 6px; padding: 4px 10px; font-weight: 900; font-size: 11px;"
        )
        filter_row.addWidget(self.lbl_count_info)
        list_vbox.addLayout(filter_row)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(6)
        btn_sel_match_res = QPushButton("🎯 Eşleşen Çözünürlük")
        btn_sel_match_res.setToolTip("Yalnızca seçili ekranın çözünürlüğüyle birebir aynı olan temaları işaretler")
        btn_sel_match_res.setStyleSheet(
            "background: rgba(0, 166, 224, 0.15); border: 1px solid rgba(123, 208, 255, 0.35); color: #7bd0ff; font-weight: 800; font-size: 11px; padding: 5px 10px; border-radius: 6px;"
        )
        btn_sel_match_res.clicked.connect(self.select_only_matching_resolution_themes)
        tools_row.addWidget(btn_sel_match_res)

        btn_sel_all = QPushButton("☑️ Tümünü Seç")
        btn_sel_all.setStyleSheet("background: #222a3d; border: 1px solid #2d3449; color: #dae2fd; padding: 5px 9px; font-size: 11px; border-radius: 6px;")
        btn_sel_all.clicked.connect(lambda: self.set_all_themes_checked(True))
        tools_row.addWidget(btn_sel_all)

        btn_sel_none = QPushButton("🔲 Temizle")
        btn_sel_none.setStyleSheet("background: #222a3d; border: 1px solid #2d3449; color: #dae2fd; padding: 5px 9px; font-size: 11px; border-radius: 6px;")
        btn_sel_none.clicked.connect(lambda: self.set_all_themes_checked(False))
        tools_row.addWidget(btn_sel_none)

        tools_row.addStretch()

        btn_up = QPushButton("🔼")
        btn_up.setToolTip("Seçili temayı döngü sırasında yukarı taşı")
        btn_up.setFixedWidth(36)
        btn_up.setStyleSheet("background: #222a3d; border: 1px solid #2d3449; border-radius: 6px; padding: 4px;")
        btn_up.clicked.connect(lambda: self.move_selected_theme_row(-1))
        tools_row.addWidget(btn_up)

        btn_down = QPushButton("🔽")
        btn_down.setToolTip("Seçili temayı döngü sırasında aşağı taşı")
        btn_down.setFixedWidth(36)
        btn_down.setStyleSheet("background: #222a3d; border: 1px solid #2d3449; border-radius: 6px; padding: 4px;")
        btn_down.clicked.connect(lambda: self.move_selected_theme_row(1))
        tools_row.addWidget(btn_down)
        list_vbox.addLayout(tools_row)

        self.theme_check_list = QListWidget()
        self.theme_check_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.theme_check_list.setStyleSheet("""
            QListWidget {
                background-color: #060e20;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 6px;
                outline: none;
            }
            QListWidget::item {
                background-color: #131b2e;
                border: 1px solid #222a3d;
                border-radius: 7px;
                padding: 7px 10px;
                margin-bottom: 4px;
                color: #dae2fd;
                font-weight: 800;
            }
            QListWidget::item:hover {
                background-color: #222a3d;
                border-color: #8083ff;
            }
            QListWidget::item:selected {
                background-color: rgba(128, 131, 255, 0.24);
                border: 1px solid #8083ff;
                color: #ffffff;
            }
        """)
        self.theme_check_list.itemChanged.connect(self.on_theme_check_changed)
        list_vbox.addWidget(self.theme_check_list, stretch=1)

        # Stitch Active Cycle Pipeline Preview Strip (#060e20)
        pipe_frame = QFrame()
        pipe_frame.setStyleSheet("QFrame { background: #060e20; border: 1px solid #1e293b; border-radius: 8px; }")
        pipe_row = QHBoxLayout(pipe_frame)
        pipe_row.setContentsMargins(10, 7, 10, 7)
        lbl_pipe_hdr = QLabel("AKTİF DÖNGÜ SIRASI:")
        lbl_pipe_hdr.setStyleSheet("color: #908fa0; font-size: 10px; font-weight: 900; letter-spacing: 0.8px; border: none; background: transparent;")
        pipe_row.addWidget(lbl_pipe_hdr)

        self.lbl_cycle_pipeline = QLabel("—")
        self.lbl_cycle_pipeline.setStyleSheet("color: #7bd0ff; font-family: 'Consolas', monospace; font-size: 11px; font-weight: 800; border: none; background: transparent;")
        pipe_row.addWidget(self.lbl_cycle_pipeline, stretch=1)
        list_vbox.addWidget(pipe_frame)

        right_col.addWidget(list_box, stretch=1)
        split_row.addLayout(right_col, stretch=3)
        layout.addLayout(split_row, stretch=1)

        # Bottom Action Bar
        bot_row = QHBoxLayout()
        bot_row.setSpacing(10)
        btn_copy_all = QPushButton("🖥️ Bu Döngü Ayarlarını Tüm Ekranlara Kopyala")
        btn_copy_all.setToolTip("Şu an seçili ekran için belirlediğiniz tema listesini ve süreyi diğer tüm ekranlara da kopyalar")
        btn_copy_all.setStyleSheet(
            "background: #171f33; border: 1px solid #334155; color: #cbd5e1; font-weight: 800; padding: 8px 14px; border-radius: 7px;"
        )
        btn_copy_all.clicked.connect(self.copy_current_slot_config_to_all)
        bot_row.addWidget(btn_copy_all)

        bot_row.addStretch()

        btn_cancel = QPushButton("İptal")
        btn_cancel.setStyleSheet("padding: 8px 16px; border-radius: 7px;")
        btn_cancel.clicked.connect(self.reject)
        bot_row.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Döngü Havuzunu Kaydet ve Uygula")
        btn_save.setStyleSheet(
            "background: #8083ff; color: #07006c; font-weight: 900; padding: 9px 22px; font-size: 13px; border-radius: 7px; border: none;"
        )
        btn_save.clicked.connect(self.save_and_accept)
        bot_row.addWidget(btn_save)
        layout.addLayout(bot_row)

        self.refresh_screen_combo()

    def refresh_screen_combo(self):
        self._updating_ui = True
        self.combo_screen.clear()
        sel_idx = 0
        for idx, (sid, ws) in enumerate(list(getattr(self.gui, 'screen_workspaces', {}).items())):
            cfg = self._slot_configs.get(sid, {})
            en = cfg.get('auto_rotate_enabled', False)
            cnt = len(cfg.get('rotate_themes', []))
            tw = int(ws.get('theme_data', {}).get('width', 320))
            th = int(ws.get('theme_data', {}).get('height', 1480))
            status_txt = f"🟢 Döngü AÇIK ({cnt} Tema)" if en else "⚪ Döngü KAPALI"
            self.combo_screen.addItem(f"{ws.get('title', sid)} [{tw}×{th}]  —  {status_txt}", sid)
            if sid == self.current_slot_id:
                sel_idx = idx
        self.combo_screen.setCurrentIndex(sel_idx)
        self._updating_ui = False

    def on_screen_combo_changed(self, idx):
        if self._updating_ui or idx < 0:
            return
        self.sync_ui_into_current_slot()
        new_sid = self.combo_screen.itemData(idx)
        if new_sid:
            self.current_slot_id = new_sid
            self.load_slot_into_ui(new_sid)

    def on_res_filter_changed(self, _idx):
        if self._updating_ui or self._res_filter_updating:
            return
        self.sync_ui_into_current_slot()
        self.load_slot_into_ui(self.current_slot_id, preserve_res_filter=True)

    def load_slot_into_ui(self, slot_id, preserve_res_filter=False):
        if slot_id not in self._slot_configs:
            return
        self._updating_ui = True
        cfg = self._slot_configs[slot_id]
        self.chk_enabled.setChecked(bool(cfg.get('auto_rotate_enabled', False)))
        self.spin_val.setValue(max(1, min(9999, int(cfg.get('rotate_interval_val', 30)))))

        u_val = cfg.get('rotate_interval_unit', 'sec')
        for i in range(self.combo_unit.count()):
            if self.combo_unit.itemData(i) == u_val:
                self.combo_unit.setCurrentIndex(i)
                break

        m_val = cfg.get('rotate_mode', 'sequential')
        for i in range(self.combo_mode.count()):
            if self.combo_mode.itemData(i) == m_val:
                self.combo_mode.setCurrentIndex(i)
                break

        current_filter = self.combo_res_filter.currentData() if (preserve_res_filter and hasattr(self, 'combo_res_filter')) else "all"
        if not current_filter:
            current_filter = "all"

        self.theme_check_list.clear()
        presets = get_all_preset_themes()
        preset_map = {p['name'].lower(): p for p in presets}
        selected_names = cfg.get('rotate_themes', [])
        selected_lower_set = {str(s).strip().lower() for s in selected_names}

        sw, sh = self._get_slot_resolution(slot_id)
        slot_res_key = f"{sw}x{sh}"

        # Order: first user's selected themes in their exact order, then remaining unselected themes
        ordered_presets = []
        seen_lower = set()
        for s_name in selected_names:
            k = str(s_name).strip().lower()
            if k in preset_map and k not in seen_lower:
                ordered_presets.append((preset_map[k], True))
                seen_lower.add(k)
        for p in presets:
            k = p['name'].lower()
            if k not in seen_lower:
                ordered_presets.append((p, False))
                seen_lower.add(k)

        # Group by resolution while preserving relative order inside each resolution group
        groups = {}
        for p_info, is_checked in ordered_presets:
            mw = int(p_info.get('width', 320))
            mh = int(p_info.get('height', 1480))
            rk = f"{mw}x{mh}"
            groups.setdefault(rk, {'w': mw, 'h': mh, 'entries': []})['entries'].append((p_info, is_checked))

        def _grp_sort(rk):
            g = groups[rk]
            is_slot_res = 0 if rk == slot_res_key else 1
            return (is_slot_res, -(g['w'] * g['h']), rk)

        sorted_rkeys = sorted(groups.keys(), key=_grp_sort)

        if hasattr(self, 'combo_res_filter'):
            self._res_filter_updating = True
            self.combo_res_filter.clear()
            self.combo_res_filter.addItem(f"🌐 Tüm Çözünürlükler — Gruplu ({len(presets)} Tema)", "all")
            slot_cnt = len(groups.get(slot_res_key, {}).get('entries', []))
            self.combo_res_filter.addItem(f"🎯 Sadece Bu Ekranın Çözünürlüğü: {sw}×{sh} ({slot_cnt} Tema)", "match_slot")
            for rk in sorted_rkeys:
                g = groups[rk]
                lbl = _format_resolution_group_title(g['w'], g['h'])
                self.combo_res_filter.addItem(f"📐 {lbl} — {len(g['entries'])} Tema", rk)
            f_idx = self.combo_res_filter.findData(current_filter)
            self.combo_res_filter.setCurrentIndex(f_idx if f_idx >= 0 else 0)
            self._res_filter_updating = False
            current_filter = self.combo_res_filter.currentData() or "all"

        slot_seq = 1
        for rk in sorted_rkeys:
            if current_filter == "match_slot" and rk != slot_res_key:
                continue
            elif current_filter not in ("all", "match_slot") and rk != current_filter:
                continue

            g = groups[rk]
            grp_title = _format_resolution_group_title(g['w'], g['h'])
            active_tag = "  ★ BU EKRANIN ÇÖZÜNÜRLÜĞÜ (NATIVE MATCH)" if rk == slot_res_key else "  • OTOMATİK ÖLÇEKLENİR"
            checked_in_grp = sum(1 for _, chk in g['entries'] if chk)
            hdr_item = QListWidgetItem(
                f"📐 {grp_title}{active_tag}   [{checked_in_grp}/{len(g['entries'])} SEÇİLİ]"
            )
            hdr_item.setFlags(Qt.ItemIsEnabled)
            hdr_item.setData(Qt.UserRole, None)
            hdr_item.setForeground(QColor("#4edea3" if rk == slot_res_key else "#fbbf24"))
            hdr_item.setBackground(QColor("#0a231e" if rk == slot_res_key else "#231b10"))
            fnt = hdr_item.font()
            fnt.setBold(True)
            hdr_item.setFont(fnt)
            self.theme_check_list.addItem(hdr_item)

            for p_info, is_checked in g['entries']:
                mw, mh = g['w'], g['h']
                pkg_tag = "📦 .cptheme" if p_info.get('is_cptheme') else "🎨 JSON"
                item = QListWidgetItem(f"  #{slot_seq:02d}   {p_info['name']}      [{mw}×{mh} • {pkg_tag}]")
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setCheckState(Qt.Checked if is_checked else Qt.Unchecked)
                item.setData(Qt.UserRole, p_info['name'])
                self.theme_check_list.addItem(item)
                slot_seq += 1

        self._updating_ui = False
        self.update_count_label()

    def sync_ui_into_current_slot(self):
        if not self.current_slot_id or self.current_slot_id not in self._slot_configs:
            return
        prev_selected = list(self._slot_configs[self.current_slot_id].get('rotate_themes', []))
        visible_names_lower = set()
        visible_checked_ordered = []

        for i in range(self.theme_check_list.count()):
            it = self.theme_check_list.item(i)
            if not it:
                continue
            t_name = it.data(Qt.UserRole)
            if not t_name:
                continue
            visible_names_lower.add(str(t_name).strip().lower())
            if it.checkState() == Qt.Checked:
                visible_checked_ordered.append(str(t_name))

        # Preserve any checked themes that were hidden by the active resolution filter
        hidden_checked = [t for t in prev_selected if str(t).strip().lower() not in visible_names_lower]
        final_checked = visible_checked_ordered + hidden_checked

        self._slot_configs[self.current_slot_id] = {
            'auto_rotate_enabled': self.chk_enabled.isChecked(),
            'rotate_interval_val': self.spin_val.value(),
            'rotate_interval_unit': self.combo_unit.currentData() or 'sec',
            'rotate_mode': self.combo_mode.currentData() or 'sequential',
            'rotate_themes': final_checked
        }

    def select_only_matching_resolution_themes(self):
        if not self.current_slot_id or self.current_slot_id not in self._slot_configs:
            return
        sw, sh = self._get_slot_resolution(self.current_slot_id)
        matching_names = [
            p['name'] for p in get_all_preset_themes()
            if int(p.get('width', 320)) == sw and int(p.get('height', 1480)) == sh
        ]
        self._slot_configs[self.current_slot_id]['rotate_themes'] = matching_names
        self.load_slot_into_ui(self.current_slot_id, preserve_res_filter=True)
        self.refresh_screen_combo()

    def on_ui_field_edited(self, *_args):
        if self._updating_ui:
            return
        self.sync_ui_into_current_slot()
        self.update_count_label()
        self.refresh_screen_combo()

    def on_theme_check_changed(self, _item):
        if self._updating_ui:
            return
        self.sync_ui_into_current_slot()
        self.update_count_label()
        self.refresh_screen_combo()

    def update_count_label(self):
        cfg = self._slot_configs.get(self.current_slot_id, {})
        rot_themes = cfg.get('rotate_themes', []) or []
        cnt = len(rot_themes)
        en = cfg.get('auto_rotate_enabled', False)
        sw, sh = self._get_slot_resolution(self.current_slot_id)
        if hasattr(self, 'lbl_slot_hw_summary'):
            ws = getattr(self.gui, 'screen_workspaces', {}).get(self.current_slot_id, {})
            s_type_lbl = "HDMI Monitör" if ws.get('screen_type') == 'hdmi_monitor' else "USB LCD Kasa Ekranı"
            self.lbl_slot_hw_summary.setText(f"📐 Hedef Çözünürlük: {sw}×{sh}  •  🔌 Tip: {s_type_lbl}")
        if hasattr(self, 'lbl_cycle_pipeline'):
            if rot_themes:
                preview_seq = "  →  ".join(str(x)[:18] for x in rot_themes[:4])
                if len(rot_themes) > 4:
                    preview_seq += f"  (+{len(rot_themes) - 4} tema)"
                self.lbl_cycle_pipeline.setText(preview_seq)
            else:
                self.lbl_cycle_pipeline.setText("Henüz döngüye tema seçilmedi")
        if en and cnt == 0:
            self.lbl_count_info.setText("⚠️ Tema Seçilmedi!")
            self.lbl_count_info.setStyleSheet(
                "background: rgba(244, 63, 94, 0.16); color: #ffb4ab; border: 1px solid #f43f5e; "
                "border-radius: 5px; padding: 3px 8px; font-weight: 800; font-size: 11px;"
            )
        else:
            self.lbl_count_info.setText(f"● {cnt} Aktif Tema")
            self.lbl_count_info.setStyleSheet(
                "background: rgba(16, 185, 129, 0.14); color: #4edea3; border: 1px solid rgba(16, 185, 129, 0.35); "
                "border-radius: 5px; padding: 3px 8px; font-weight: 800; font-size: 11px;"
            )

    def set_all_themes_checked(self, checked):
        self._updating_ui = True
        for i in range(self.theme_check_list.count()):
            it = self.theme_check_list.item(i)
            if it and it.data(Qt.UserRole):
                it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._updating_ui = False
        self.sync_ui_into_current_slot()
        self.update_count_label()
        self.refresh_screen_combo()

    def move_selected_theme_row(self, direction):
        row = self.theme_check_list.currentRow()
        if row < 0:
            return
        curr_it = self.theme_check_list.item(row)
        if not curr_it or not curr_it.data(Qt.UserRole):
            return
        new_row = row + direction
        if 0 <= new_row < self.theme_check_list.count():
            target_it = self.theme_check_list.item(new_row)
            if not target_it or not target_it.data(Qt.UserRole):
                return
            self._updating_ui = True
            item = self.theme_check_list.takeItem(row)
            self.theme_check_list.insertItem(new_row, item)
            self.theme_check_list.setCurrentRow(new_row)
            self._updating_ui = False
            self.sync_ui_into_current_slot()

    def copy_current_slot_config_to_all(self):
        self.sync_ui_into_current_slot()
        src_cfg = copy.deepcopy(self._slot_configs.get(self.current_slot_id, {}))
        for sid in list(self._slot_configs.keys()):
            self._slot_configs[sid] = copy.deepcopy(src_cfg)
        self.refresh_screen_combo()
        QMessageBox.information(self, "Tüm Ekranlara Kopyalandı", "Seçili ekranın otomatik tema değişim listesi ve süresi tüm ekranlara kopyalandı!")

    def test_next_theme_on_current_screen(self):
        self.sync_ui_into_current_slot()
        self.apply_configs_to_workspaces()
        if hasattr(self.gui, 'rotate_screen_workspace_theme'):
            ok_rot = self.gui.rotate_screen_workspace_theme(self.current_slot_id, delta=1)
            if not ok_rot:
                QMessageBox.information(self, "Bilgi", "Lütfen bu ekran için listeden en az 1 kayıtlı tema işaretleyin.")

    def apply_configs_to_workspaces(self):
        now_t = time.time()
        any_enabled = False
        for sid, cfg in self._slot_configs.items():
            ws = self.gui.screen_workspaces.get(sid)
            if not ws:
                continue
            ws['auto_rotate_enabled'] = bool(cfg.get('auto_rotate_enabled', False))
            ws['rotate_interval_val'] = max(1, min(9999, int(cfg.get('rotate_interval_val', 30))))
            ws['rotate_interval_unit'] = str(cfg.get('rotate_interval_unit', 'sec'))
            ws['rotate_mode'] = str(cfg.get('rotate_mode', 'sequential'))
            ws['rotate_themes'] = list(cfg.get('rotate_themes', []))
            ws['_last_rotate_time'] = now_t
            if ws['auto_rotate_enabled']:
                any_enabled = True

        # Keep global app_settings synced with active slot for backward compatibility
        active_cfg = self._slot_configs.get(getattr(self.gui, 'active_screen_slot_id', 'usb_lcd_1'))
        if active_cfg:
            self.gui.app_settings['rotate_val'] = active_cfg['rotate_interval_val']
            self.gui.app_settings['rotate_unit'] = active_cfg['rotate_interval_unit']
            self.gui.app_settings['rotate_mode'] = active_cfg['rotate_mode']
        self.gui.app_settings['auto_rotate_themes'] = any_enabled
        self.gui.save_app_settings()
        self.gui.save_screen_workspaces_to_disk()
        if hasattr(self.gui, 'refresh_multi_screen_bar_ui'):
            self.gui.refresh_multi_screen_bar_ui()

    def save_and_accept(self):
        self.sync_ui_into_current_slot()
        for sid, cfg in self._slot_configs.items():
            if cfg.get('auto_rotate_enabled') and len(cfg.get('rotate_themes', [])) == 0:
                ws_title = self.gui.screen_workspaces.get(sid, {}).get('title', sid)
                QMessageBox.warning(
                    self,
                    "Tema Seçilmedi",
                    f"'{ws_title}' ekranında otomatik tema değişimi açık ancak hiçbir tema işaretlenmemiş!\n\n"
                    "Lütfen döngüye dahil edilecek en az 1 tema işaretleyin veya otomatik değişimi kapatın."
                )
                return
        self.apply_configs_to_workspaces()
        self.accept()

class AppSettingsDialog(QDialog):
    def __init__(self, parent_gui):
        super().__init__(parent_gui)
        self.gui = parent_gui
        self.setWindowTitle("⚙️ CYBERPULSE LCD Studio Genel Ayarlar")
        self.resize(920, 660)
        self.setStyleSheet(get_cyberpulse_global_stylesheet())
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Stitch v2.4 Top Header with SYSTEM CORE V2.4 Badge
        hdr_row = QHBoxLayout()
        hdr_vbox = QVBoxLayout()
        hdr_vbox.setSpacing(2)

        title_row = QHBoxLayout()
        title = QLabel("⚙️ Uygulama Ayarları, Kısayollar ve Donanım Kalibrasyonu")
        title.setStyleSheet("font-size: 17px; font-weight: 900; color: #f8fafc; letter-spacing: 0.3px;")
        title_row.addWidget(title)
        title_row.addStretch()
        hdr_vbox.addLayout(title_row)

        sub_lbl = QLabel("Başlangıç servisi, COM veri yolu, global oyun içi kısayollar, termal kalibrasyon ve otomatik döngü tercihleri")
        sub_lbl.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600;")
        hdr_vbox.addWidget(sub_lbl)
        hdr_row.addLayout(hdr_vbox, stretch=1)
        layout.addLayout(hdr_row)

        # Stitch 2-Column Split Layout (#131b2e Cards with #060e20 Sub-Blocks)
        columns_row = QHBoxLayout()
        columns_row.setSpacing(14)

        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        def make_stitch_settings_card(title_text, badge_text=""):
            c = QFrame()
            c.setStyleSheet("""
                QFrame {
                    background-color: #131b2e;
                    border: 1px solid rgba(68, 70, 86, 0.35);
                    border-radius: 10px;
                }
            """)
            lay = QVBoxLayout(c)
            lay.setContentsMargins(14, 12, 14, 12)
            lay.setSpacing(8)
            h_row = QHBoxLayout()
            lbl_t = QLabel(title_text)
            lbl_t.setStyleSheet("color: #c0c1ff; font-size: 11px; font-weight: 800; letter-spacing: 0.6px; border: none;")
            h_row.addWidget(lbl_t)
            h_row.addStretch()
            lay.addLayout(h_row)
            return c, lay

        grp_startup, grp_layout = make_stitch_settings_card("🚀 SİSTEM SERVİSİ & BAŞLANGIÇ DAVRANIŞI", "SERVICE")

        self.chk_autostart = QCheckBox("🚀 Windows Açılışında Otomatik Çalıştır")
        self.chk_autostart.setChecked(bool(self.gui.app_settings.get('autostart', False)))
        grp_layout.addWidget(self.chk_autostart)

        self.chk_tray = QCheckBox("📌 Sistem Tepsisinde (System Tray) Çalıştır")
        self.chk_tray.setChecked(bool(self.gui.app_settings.get('enable_tray', True)))
        grp_layout.addWidget(self.chk_tray)

        self.chk_minimized = QCheckBox("🔽 Başlangıçta Sistem Tepsisine Küçültülmüş Başla")
        self.chk_minimized.setChecked(bool(self.gui.app_settings.get('start_minimized', False)))
        grp_layout.addWidget(self.chk_minimized)

        self.chk_autostream = QCheckBox("⚡ Açılışta Kasa Ekranına Otomatik Yansıtmaya Başla")
        self.chk_autostream.setChecked(bool(self.gui.app_settings.get('auto_stream_on_start', True)))
        grp_layout.addWidget(self.chk_autostream)

        self.chk_auto_update = QCheckBox("🔄 Her Açılışta Güncellemeleri Otomatik Denetle ve Yükle")
        self.chk_auto_update.setChecked(bool(self.gui.app_settings.get('auto_check_updates', True)))
        grp_layout.addWidget(self.chk_auto_update)

        lang_row = QHBoxLayout()
        lbl_lang = QLabel("🌐 Uygulama Dili / Language:")
        lbl_lang.setStyleSheet("color: #dae2fd; font-size: 11px; font-weight: 700; border: none;")
        lang_row.addWidget(lbl_lang)
        self.combo_app_lang = QComboBox()
        self.combo_app_lang.addItem("🇹🇷 Türkçe (Turkish)", "tr")
        self.combo_app_lang.addItem("🇬🇧 English (İngilizce)", "en")
        curr_lang = str(self.gui.app_settings.get('language', 'tr')).lower()
        self.combo_app_lang.setCurrentIndex(1 if curr_lang == 'en' else 0)
        lang_row.addWidget(self.combo_app_lang, stretch=1)

        btn_chk_upd = QPushButton("🔄 Güncelleme Denetle")
        btn_chk_upd.setStyleSheet(
            "background: #171f33; border: 1px solid #38bdf8; color: #38bdf8; font-weight: 800; padding: 5px 10px; border-radius: 6px;"
        )
        btn_chk_upd.clicked.connect(lambda: self.gui.start_update_check(silent=False))
        lang_row.addWidget(btn_chk_upd)
        grp_layout.addLayout(lang_row)

        left_col.addWidget(grp_startup)

        grp_com, com_layout = make_stitch_settings_card("🔌 DONANIM VERİ YOLU & COM PORT BAĞLANTISI", "USB CDC")

        com_inner = QFrame()
        com_inner.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid rgba(68, 70, 86, 0.3); border-radius: 8px; }")
        com_row = QHBoxLayout(com_inner)
        com_row.setContentsMargins(10, 8, 10, 8)
        lbl_com_title = QLabel("COM Portu:")
        lbl_com_title.setStyleSheet("color: #c4c5d9; font-size: 11px; font-weight: 700; border: none;")
        com_row.addWidget(lbl_com_title)
        self.dialog_combo_port = QComboBox()
        self.dialog_combo_port.addItem("⚡ Otomatik Algıla (Önerilen)", "auto")

        ports = HardwareDriver.list_available_com_ports()
        cur_port = self.gui.app_settings.get('selected_com_port', 'auto')
        sel_idx = 0
        for i, p in enumerate(ports, start=1):
            dev = p.get('device', '')
            desc = p.get('description', '')
            is_lcd = p.get('is_lcd', False)
            icon = "🖥️" if is_lcd else "🔌"
            label = f"{icon} {dev} ({desc})"
            self.dialog_combo_port.addItem(label, dev)
            if dev == cur_port:
                sel_idx = i

        if cur_port == 'auto':
            sel_idx = 0
        self.dialog_combo_port.setCurrentIndex(sel_idx)
        com_row.addWidget(self.dialog_combo_port, stretch=1)

        btn_test_port = QPushButton("🔌 Portu Test Et")
        btn_test_port.setStyleSheet(
            "background: #171f33; border: 1px solid #38bdf8; color: #38bdf8; font-weight: 800; padding: 6px 12px; border-radius: 6px;"
        )
        btn_test_port.clicked.connect(self.test_port_connection)
        com_row.addWidget(btn_test_port)

        com_layout.addWidget(com_inner)
        left_col.addWidget(grp_com)

        grp_alert, alert_layout = make_stitch_settings_card("🌡️ TERMAL KALİBRASYON & HAVA DURUMU KONUMU", "SENSORS")

        box_limit = QHBoxLayout()
        lbl_lim = QLabel("🔥 Kritik Uyarı Sıcaklık Eşiği (°C):")
        lbl_lim.setStyleSheet("color: #dae2fd; font-size: 11px; font-weight: 700; border: none;")
        box_limit.addWidget(lbl_lim)
        self.spin_alert_limit = QSpinBox()
        self.spin_alert_limit.setRange(60, 99)
        self.spin_alert_limit.setValue(int(self.gui.theme_data.get('thermal_alert_limit', 82)))
        box_limit.addWidget(self.spin_alert_limit)
        alert_layout.addLayout(box_limit)

        box_offset = QHBoxLayout()
        lbl_off = QLabel("🎯 CPU Sıcaklık Kalibrasyon Ofseti (°C):")
        lbl_off.setStyleSheet("color: #dae2fd; font-size: 11px; font-weight: 700; border: none;")
        box_offset.addWidget(lbl_off)
        self.spin_cpu_offset = QSpinBox()
        self.spin_cpu_offset.setRange(-20, 20)
        self.spin_cpu_offset.setValue(int(self.gui.app_settings.get('cpu_temp_offset', -7)))
        box_offset.addWidget(self.spin_cpu_offset)
        alert_layout.addLayout(box_offset)

        w_box = QHBoxLayout()
        lbl_w = QLabel("📍 Hava Durumu İl/İlçe:")
        lbl_w.setStyleSheet("color: #dae2fd; font-size: 11px; font-weight: 700; border: none;")
        w_box.addWidget(lbl_w)
        self.spin_weather_city = QLineEdit()
        self.spin_weather_city.setPlaceholderText("Otomatik GPS veya şehir adı (Örn: Çorlu)")
        self.spin_weather_city.setText(str(self.gui.app_settings.get('custom_weather_location', '')))
        w_box.addWidget(self.spin_weather_city, stretch=1)

        btn_gps_perm = QPushButton("🎯 Oto GPS")
        btn_gps_perm.setStyleSheet("background: #171f33; border: 1px solid #38bdf8; color: #38bdf8; font-weight: 800; padding: 5px 10px; border-radius: 6px;")
        btn_gps_perm.clicked.connect(lambda: self.spin_weather_city.setText(''))
        w_box.addWidget(btn_gps_perm)
        alert_layout.addLayout(w_box)

        left_col.addWidget(grp_alert)
        left_col.addStretch()

        grp_hotkeys, hk_layout = make_stitch_settings_card("⌨ GLOBAL KISAYOL TUŞLARI (OYUN İÇİ & ARKA PLAN)", "WIN32 HOOK")

        self.chk_enable_hotkeys = QCheckBox("⌨️ Global Kısayol Tuşlarını Etkinleştir (Oyunlarda & Arka Planda Çalışır)")
        self.chk_enable_hotkeys.setChecked(bool(self.gui.app_settings.get('enable_hotkeys', True)))
        hk_layout.addWidget(self.chk_enable_hotkeys)

        def make_hk_row(label_text, default_seq):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setMinimumWidth(210)
            row.addWidget(lbl)
            kse = QKeySequenceEdit()
            kse.setKeySequence(QKeySequence(default_seq))
            row.addWidget(kse)
            return row, kse

        row_next, self.kse_next = make_hk_row("⏭️ Sonraki Tema:", self.gui.app_settings.get('hotkey_next_theme', 'Ctrl+Alt+Right'))
        hk_layout.addLayout(row_next)

        row_prev, self.kse_prev = make_hk_row("⏮️ Önceki Tema:", self.gui.app_settings.get('hotkey_prev_theme', 'Ctrl+Alt+Left'))
        hk_layout.addLayout(row_prev)

        row_stream, self.kse_stream = make_hk_row("🚀 Yansıtma Aç/Kapat:", self.gui.app_settings.get('hotkey_toggle_stream', 'Ctrl+Alt+P'))
        hk_layout.addLayout(row_stream)

        row_rand, self.kse_rand = make_hk_row("🎲 Rastgele Tema Seç:", self.gui.app_settings.get('hotkey_random_theme', 'Ctrl+Alt+R'))
        hk_layout.addLayout(row_rand)

        row_win, self.kse_win = make_hk_row("⚡ Stüdyo Göster / Gizle:", self.gui.app_settings.get('hotkey_toggle_window', 'Ctrl+Alt+S'))
        hk_layout.addLayout(row_win)

        btn_rst_hk = QPushButton("🔄 Kısayolları Varsayılana Sıfırla")
        btn_rst_hk.setStyleSheet("background: #171f33; border: 1px solid #334155; color: #cbd5e1; font-weight: 700; padding: 5px 10px;")
        btn_rst_hk.clicked.connect(self.reset_hotkeys_to_default)
        hk_layout.addWidget(btn_rst_hk)

        right_col.addWidget(grp_hotkeys)

        grp_rotation, rot_layout = make_stitch_settings_card("🎠 OTOMATİK TEMA DÖNGÜSÜ & OYUN PROFİLLERİ", "AUTOMATION")

        self.chk_auto_rotate = QCheckBox("🎠 Kayıtlı Temaları Otomatik Değiştir (Slayt Döngüsü)")
        self.chk_auto_rotate.setChecked(bool(self.gui.app_settings.get('auto_rotate_themes', False)))
        rot_layout.addWidget(self.chk_auto_rotate)

        dur_box = QHBoxLayout()
        dur_box.addWidget(QLabel("⏱️ Süre:"))

        self.spin_rotate_val = QSpinBox()
        self.spin_rotate_val.setRange(1, 9999)
        self.spin_rotate_val.setValue(int(self.gui.app_settings.get('rotate_val', 30)))
        dur_box.addWidget(self.spin_rotate_val)

        self.combo_rotate_unit = QComboBox()
        self.combo_rotate_unit.addItem("⏱️ Saniye", "sec")
        self.combo_rotate_unit.addItem("⏱️ Dakika", "min")
        self.combo_rotate_unit.addItem("⏱️ Saat", "hour")

        unit_val = self.gui.app_settings.get('rotate_unit', 'sec')
        for i in range(self.combo_rotate_unit.count()):
            if self.combo_rotate_unit.itemData(i) == unit_val:
                self.combo_rotate_unit.setCurrentIndex(i)
                break
        dur_box.addWidget(self.combo_rotate_unit)

        self.combo_rotate_mode = QComboBox()
        self.combo_rotate_mode.addItem("📋 Sırayla", "sequential")
        self.combo_rotate_mode.addItem("🎲 Karışık", "random")

        mode_val = self.gui.app_settings.get('rotate_mode', 'sequential')
        for i in range(self.combo_rotate_mode.count()):
            if self.combo_rotate_mode.itemData(i) == mode_val:
                self.combo_rotate_mode.setCurrentIndex(i)
                break
        dur_box.addWidget(self.combo_rotate_mode, stretch=1)
        rot_layout.addLayout(dur_box)

        btn_per_scr_rot = QPushButton("🎠 Her Ekran İçin Otomatik Değişecek Temaları Ayrı Ayrı Seç...")
        btn_per_scr_rot.setStyleSheet(
            "background: #8083ff; color: #07006c; font-weight: 900; padding: 7px 12px; border-radius: 6px; border: none;"
        )
        btn_per_scr_rot.clicked.connect(lambda: self.gui.open_screen_auto_rotate_dialog(parent_widget=self))
        rot_layout.addWidget(btn_per_scr_rot)

        # 🎮 PHASE 3: AUTO GAME / PROCESS THEME SWITCHER & PER-GAME PROFILES
        self.chk_auto_game_theme = QCheckBox("🎮 Oyun Açıldığında Otomatik Oyun Temasına Geç")
        self.chk_auto_game_theme.setChecked(bool(self.gui.app_settings.get('auto_game_theme_enabled', True)))
        self.chk_auto_game_theme.setStyleSheet("color: #38bdf8; font-weight: 800;")
        rot_layout.addWidget(self.chk_auto_game_theme)

        game_theme_box = QHBoxLayout()
        game_theme_box.addWidget(QLabel("🎯 Varsayılan:"))
        self.combo_game_theme = QComboBox()
        self.combo_game_theme.addItem("🚫 Yok (Özel Bağlanan Oyunlar)", "")
        preset_list = get_all_preset_themes()
        saved_game_theme = str(self.gui.app_settings.get('auto_game_theme_name', '')).strip()
        sel_gt_idx = 0
        for idx_t, t_item in enumerate(preset_list, start=1):
            self.combo_game_theme.addItem(f"🎨 {t_item['name']}", t_item['name'])
            if t_item['name'].lower() == saved_game_theme.lower():
                sel_gt_idx = idx_t
        self.combo_game_theme.setCurrentIndex(sel_gt_idx)
        game_theme_box.addWidget(self.combo_game_theme, stretch=1)

        btn_open_game_profiles = QPushButton("🎮 Oyun Profilleri...")
        btn_open_game_profiles.setStyleSheet(
            "background: #171f33; border: 1px solid #8083ff; color: #c0c1ff; font-weight: 800; padding: 6px 10px;"
        )
        btn_open_game_profiles.clicked.connect(self.gui.open_game_profile_manager)
        game_theme_box.addWidget(btn_open_game_profiles)
        rot_layout.addLayout(game_theme_box)

        right_col.addWidget(grp_rotation)
        right_col.addStretch()

        columns_row.addLayout(left_col, stretch=1)
        columns_row.addLayout(right_col, stretch=1)
        layout.addLayout(columns_row, stretch=1)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("İptal")
        btn_cancel.setStyleSheet("padding: 8px 16px; border-radius: 7px;")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("✅ Ayarları Kaydet ve Uygula")
        btn_save.setStyleSheet(
            "background: #10b981; color: #002113; font-weight: 900; padding: 9px 22px; border-radius: 7px; border: none;"
        )
        btn_save.clicked.connect(self.save_settings)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def test_port_connection(self):
        sel = self.dialog_combo_port.currentData()
        target = None if sel == 'auto' else sel
        import serial
        ports = [target] if target else ['COM11', 'COM16']
        success = False
        connected_port = None
        err_msg = ""
        for p in ports:
            try:
                s = serial.Serial(p, 115200, timeout=1)
                if s.is_open:
                    s.close()
                    success = True
                    connected_port = p
                    break
            except Exception as e:
                err_msg = str(e)
        if success:
            QMessageBox.information(self, "Bağlantı Başarılı", f"✅ {connected_port} portu başarıyla açıldı ve LCD ekran yayını için hazır!")
        else:
            QMessageBox.warning(self, "Bağlantı Başarısız", f"Porta bağlanılamadı ({target or 'Otomatik Tarama'}).\n\nHata: {err_msg}\n\nEkran kablosunun takılı olduğundan emin olun.")

    def reset_hotkeys_to_default(self):
        self.kse_next.setKeySequence(QKeySequence("Ctrl+Alt+Right"))
        self.kse_prev.setKeySequence(QKeySequence("Ctrl+Alt+Left"))
        self.kse_stream.setKeySequence(QKeySequence("Ctrl+Alt+P"))
        self.kse_rand.setKeySequence(QKeySequence("Ctrl+Alt+R"))
        self.kse_win.setKeySequence(QKeySequence("Ctrl+Alt+S"))

    def save_settings(self):
        try:
            autostart = self.chk_autostart.isChecked()
            self.gui.app_settings['autostart'] = autostart
            self.gui.app_settings['enable_tray'] = self.chk_tray.isChecked()
            self.gui.app_settings['start_minimized'] = self.chk_minimized.isChecked()
            self.gui.app_settings['auto_stream_on_start'] = self.chk_autostream.isChecked()
            if hasattr(self, 'chk_auto_update'):
                self.gui.app_settings['auto_check_updates'] = self.chk_auto_update.isChecked()
            self.gui.app_settings['selected_com_port'] = self.dialog_combo_port.currentData()
            if hasattr(self, 'combo_app_lang'):
                self.gui.app_settings['language'] = self.combo_app_lang.currentData()
                if hasattr(self.gui, 'apply_current_language'):
                    self.gui.apply_current_language()
            
            self.gui.app_settings['auto_rotate_themes'] = self.chk_auto_rotate.isChecked()
            self.gui.app_settings['rotate_val'] = self.spin_rotate_val.value()
            self.gui.app_settings['rotate_unit'] = self.combo_rotate_unit.currentData()
            self.gui.app_settings['rotate_mode'] = self.combo_rotate_mode.currentData()
            active_ws = getattr(self.gui, 'screen_workspaces', {}).get(getattr(self.gui, 'active_screen_slot_id', ''))
            if active_ws is not None:
                active_ws['auto_rotate_enabled'] = self.chk_auto_rotate.isChecked()
                active_ws['rotate_interval_val'] = self.spin_rotate_val.value()
                active_ws['rotate_interval_unit'] = self.combo_rotate_unit.currentData() or 'sec'
                active_ws['rotate_mode'] = self.combo_rotate_mode.currentData() or 'sequential'
                if not active_ws.get('rotate_themes'):
                    active_ws['rotate_themes'] = [t['name'] for t in get_all_preset_themes()]
            if hasattr(self.gui, 'refresh_multi_screen_bar_ui'):
                self.gui.refresh_multi_screen_bar_ui()
            self.gui.app_settings['auto_game_theme_enabled'] = self.chk_auto_game_theme.isChecked()
            self.gui.app_settings['auto_game_theme_name'] = self.combo_game_theme.currentData() or ''

            self.gui.app_settings['cpu_temp_offset'] = self.spin_cpu_offset.value()
            if hasattr(self.gui, 'sensor'):
                self.gui.sensor.cpu_temp_offset = self.spin_cpu_offset.value()

            w_loc_val = self.spin_weather_city.text().strip()
            self.gui.app_settings['custom_weather_location'] = w_loc_val
            if hasattr(self.gui, 'sensor'):
                self.gui.sensor.custom_location = w_loc_val

            self.gui.app_settings['enable_hotkeys'] = self.chk_enable_hotkeys.isChecked()
            self.gui.app_settings['hotkey_next_theme'] = self.kse_next.keySequence().toString()
            self.gui.app_settings['hotkey_prev_theme'] = self.kse_prev.keySequence().toString()
            self.gui.app_settings['hotkey_toggle_stream'] = self.kse_stream.keySequence().toString()
            self.gui.app_settings['hotkey_random_theme'] = self.kse_rand.keySequence().toString()
            self.gui.app_settings['hotkey_toggle_window'] = self.kse_win.keySequence().toString()

            self.gui.theme_data['thermal_alert_limit'] = self.spin_alert_limit.value()

            set_windows_autostart(autostart)
            self.gui.save_app_settings()
            self.gui.save_theme_to_disk()
            self.gui.setup_global_hotkeys()
            if hasattr(self.gui, 'populate_com_ports'):
                self.gui.populate_com_ports()

            QMessageBox.information(self, "Başarılı", "Genel ayarlar, COM Portu, Kısayol Tuşları ve Kalibrasyon kaydedildi!")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Ayarlar kaydedilemedi: {e}")

class MediaCropDialog(QDialog):
    def __init__(self, parent_gui, bg_path, crop_rect=None, fit_to_screen=False):
        super().__init__(parent_gui)
        self.gui = parent_gui
        self.bg_path = bg_path
        self.fit_to_screen = fit_to_screen
        self.target_w = int(self.gui.theme_data.get('width', 320))
        self.target_h = int(self.gui.theme_data.get('height', 1480))

        self.setWindowTitle("✂️ Arka Plan Medya Kırpma & Ölçeklendirme Stüdyosu")
        self.resize(880, 680)
        self.setStyleSheet("""
            QDialog { background-color: #090d16; color: #f8fafc; font-family: 'Segoe UI', Arial, sans-serif; }
            QLabel { color: #f8fafc; font-size: 13px; font-weight: 600; }
            QPushButton { background: #1e293b; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 7px 14px; color: #f8fafc; font-weight: 600; font-size: 12px; }
            QPushButton:hover { background: #334155; border-color: #6366f1; }
            QPushButton:pressed { background: #4f46e5; }
            QCheckBox { color: #f8fafc; font-weight: 600; font-size: 13px; margin: 4px 0; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #475569; background: #1e293b; }
            QCheckBox::indicator:checked { background: #6366f1; border-color: #818cf8; }
        """)

        self.gui.is_cropping = True
        self.base_pil_img = None
        self.base_pixmap = None
        self.load_media_frame()

        img_w, img_h = self.base_pil_img.size
        target_aspect = float(self.target_w) / float(self.target_h)

        if crop_rect and len(crop_rect) == 4 and crop_rect[2] > crop_rect[0] and crop_rect[3] > crop_rect[1]:
            x1 = max(0, min(img_w - 20, int(crop_rect[0])))
            y1 = max(0, min(img_h - 20, int(crop_rect[1])))
            x2 = min(img_w, max(x1 + 20, int(crop_rect[2])))
            y2 = min(img_h, max(y1 + 20, int(crop_rect[3])))
            self.raw_crop_rect = [x1, y1, x2, y2]
        else:
            box_h = int(img_h * 0.9)
            box_w = int(box_h * target_aspect)
            if box_w > img_w * 0.95:
                box_w = int(img_w * 0.95)
                box_h = int(box_w / target_aspect)
            x1 = max(0, (img_w - box_w) // 2)
            y1 = max(0, (img_h - box_h) // 2)
            self.raw_crop_rect = [x1, y1, x1 + box_w, y1 + box_h]

        self.prepare_base_pixmap()
        self.init_ui()

    def get_scale_factor(self):
        img_w, img_h = self.base_pil_img.size
        return min(840.0 / img_w, 480.0 / img_h)

    def get_display_offsets(self):
        img_w, img_h = self.base_pil_img.size
        scale = self.get_scale_factor()
        disp_w = int(img_w * scale)
        disp_h = int(img_h * scale)
        return (840 - disp_w) // 2, (480 - disp_h) // 2

    def prepare_base_pixmap(self):
        img_w, img_h = self.base_pil_img.size
        scale = self.get_scale_factor()
        disp_w = max(1, int(img_w * scale))
        disp_h = max(1, int(img_h * scale))
        scaled_pil = self.base_pil_img.resize((disp_w, disp_h), Image.Resampling.BILINEAR)
        self.base_pixmap = pil_to_pixmap(scaled_pil)

    def get_display_crop_rect(self):
        scale = self.get_scale_factor()
        offset_x, offset_y = self.get_display_offsets()
        x1, y1, x2, y2 = self.raw_crop_rect

        disp_x1 = offset_x + int(x1 * scale)
        disp_y1 = offset_y + int(y1 * scale)
        disp_x2 = offset_x + int(x2 * scale)
        disp_y2 = offset_y + int(y2 * scale)
        disp_w = max(15, disp_x2 - disp_x1)
        disp_h = max(15, disp_y2 - disp_y1)
        return QRect(disp_x1, disp_y1, disp_w, disp_h)

    def _apply_aspect_preset(self, aw, ah, lock=True):
        self.target_w = max(16, int(aw))
        self.target_h = max(16, int(ah))
        self.chk_lock_aspect.setText(f"🔒 Ekran Oranını Koru ({self.target_w}:{self.target_h})")
        self.chk_lock_aspect.setChecked(bool(lock))
        if hasattr(self, 'lbl_dims'):
            self.lbl_dims.setText(f"📐 Hedef Kırpma Oranı: {self.target_w}×{self.target_h} px")
        if lock:
            self.reset_crop()
        else:
            self.crop_widget.update()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(18, 14, 18, 14)

        hdr_layout = QHBoxLayout()
        title = QLabel("✂️ İnteraktif Arka Plan Medya Kırpıcı & Ölçekleyici")
        title.setStyleSheet("font-size: 17px; font-weight: 900; color: #f8fafc; letter-spacing: 0.3px;")
        hdr_layout.addWidget(title)
        hdr_layout.addStretch()

        self.lbl_dims = QLabel(f"📐 Hedef Ekran: {self.target_w}×{self.target_h} px")
        self.lbl_dims.setStyleSheet(
            "background: rgba(128, 131, 255, 0.16); color: #c0c1ff; padding: 4px 10px; border-radius: 6px; "
            "border: 1px solid rgba(128, 131, 255, 0.4); font-size: 12px; font-weight: 800;"
        )
        hdr_layout.addWidget(self.lbl_dims)
        layout.addLayout(hdr_layout)

        self.crop_widget = MediaCropWidget(self)
        self.crop_widget.setFixedSize(840, 460)
        self.crop_widget.setStyleSheet("border: 2px solid #1e293b; border-radius: 10px; background-color: #060e20;")
        layout.addWidget(self.crop_widget, alignment=Qt.AlignCenter)

        ctrl_box = QHBoxLayout()
        ctrl_box.setSpacing(10)

        self.chk_fit_full = QCheckBox("🖼️ Ekrana Sığdır (Kırpma Olmadan)")
        self.chk_fit_full.setChecked(self.fit_to_screen)
        self.chk_fit_full.stateChanged.connect(self.on_fit_toggle)
        ctrl_box.addWidget(self.chk_fit_full)

        self.chk_lock_aspect = QCheckBox(f"🔒 Ekran Oranını Koru ({self.target_w}:{self.target_h})")
        self.chk_lock_aspect.setChecked(True)
        self.chk_lock_aspect.setToolTip("Açık olduğunda dikdörtgeni büyütüp küçültürken ekranın en/boy oranını korur.")
        ctrl_box.addWidget(self.chk_lock_aspect)

        # Quick Aspect Ratio Presets from Stitch Media Cropper design
        for p_lbl, pw, ph, p_lock in [
            ("320×1480", 320, 1480, True),
            ("1920×1080", 1920, 1080, True),
            ("1920×480", 1920, 480, True),
            ("Serbest", self.target_w, self.target_h, False),
        ]:
            p_btn = QPushButton(p_lbl)
            p_btn.setStyleSheet(
                "background: #171f33; border: 1px solid #334155; color: #38bdf8; font-size: 11px; font-weight: 800; padding: 5px 8px; border-radius: 5px;"
            )
            p_btn.clicked.connect(lambda _c=False, w=pw, h=ph, lk=p_lock: self._apply_aspect_preset(w, h, lk))
            ctrl_box.addWidget(p_btn)

        ctrl_box.addStretch()

        btn_center = QPushButton("🎯 Ortala")
        btn_center.setToolTip("Kırpma kutusunu merkeze hizalar")
        btn_center.clicked.connect(self.center_crop)
        ctrl_box.addWidget(btn_center)

        btn_max = QPushButton("📐 Maksimum")
        btn_max.setToolTip("Kırpma kutusunu ekran oranında en büyük boyuta getirir")
        btn_max.clicked.connect(self.maximize_crop)
        ctrl_box.addWidget(btn_max)

        btn_reset = QPushButton("🔄 Sıfırla")
        btn_reset.setToolTip("Varsayılan kırpma konumuna geri döndürür")
        btn_reset.clicked.connect(self.reset_crop)
        ctrl_box.addWidget(btn_reset)

        layout.addLayout(ctrl_box)

        btn_box = QHBoxLayout()
        hint_lbl = QLabel("💡 İpucu: Çizgilerden ve tutma kulplarından çekerek boyutu ayarlayın, içinden tutarak taşıyın.")
        hint_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        btn_box.addWidget(hint_lbl)
        btn_box.addStretch()

        btn_close = QPushButton("İptal")
        btn_close.clicked.connect(self.close_crop_dialog)
        btn_box.addWidget(btn_close)

        btn_save = QPushButton("✅ Kırpmayı Kaydet ve Tuvale Uygula")
        btn_save.setStyleSheet(
            "background: #10b981; color: #002113; font-weight: 900; padding: 9px 22px; border-radius: 7px; font-size: 13px; border: none;"
        )
        btn_save.clicked.connect(self.apply_crop_live)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def close_crop_dialog(self):
        self.gui.is_cropping = False
        self.accept()

    def closeEvent(self, event):
        self.gui.is_cropping = False
        event.accept()

    def on_fit_toggle(self, state):
        self.fit_to_screen = (state == Qt.Checked)
        self.crop_widget.update()

    def load_media_frame(self):
        if not self.bg_path or not os.path.exists(self.bg_path):
            self.base_pil_img = Image.new('RGB', (1920, 1080), (15, 23, 42))
            return

        ext = os.path.splitext(self.bg_path)[1].lower()
        cpt_type = None
        if ext == '.cptheme':
            footer = read_cptheme_footer(self.bg_path)
            if footer:
                cpt_type = footer[0]

        if ext in ['.mp4', '.avi', '.mkv', '.mov', '.gif', '.webm'] or cpt_type == 'VID0':
            try:
                import cv2
                cap = cv2.VideoCapture(self.bg_path)
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    self.base_pil_img = Image.fromarray(frame_rgb)
                else:
                    self.base_pil_img = Image.new('RGB', (1920, 1080), (15, 23, 42))
            except Exception:
                self.base_pil_img = Image.new('RGB', (1920, 1080), (15, 23, 42))
        elif cpt_type == 'IMG0':
            img = read_cptheme_image(self.bg_path)
            self.base_pil_img = img if img is not None else Image.new('RGB', (1920, 1080), (15, 23, 42))
        else:
            try:
                self.base_pil_img = Image.open(self.bg_path).convert('RGB')
            except Exception:
                self.base_pil_img = Image.new('RGB', (1920, 1080), (15, 23, 42))

    def center_crop(self):
        x1, y1, x2, y2 = self.raw_crop_rect
        w = x2 - x1
        h = y2 - y1
        img_w, img_h = self.base_pil_img.size
        nx1 = max(0, (img_w - w) // 2)
        ny1 = max(0, (img_h - h) // 2)
        self.raw_crop_rect = [nx1, ny1, nx1 + w, ny1 + h]
        self.crop_widget.update()

    def maximize_crop(self):
        img_w, img_h = self.base_pil_img.size
        target_aspect = float(self.target_w) / float(self.target_h)
        box_h = img_h
        box_w = int(box_h * target_aspect)
        if box_w > img_w:
            box_w = img_w
            box_h = int(box_w / target_aspect)
        x1 = max(0, (img_w - box_w) // 2)
        y1 = max(0, (img_h - box_h) // 2)
        self.raw_crop_rect = [x1, y1, x1 + box_w, y1 + box_h]
        self.fit_to_screen = False
        self.chk_fit_full.setChecked(False)
        self.crop_widget.update()

    def reset_crop(self):
        img_w, img_h = self.base_pil_img.size
        target_aspect = float(self.target_w) / float(self.target_h)
        box_h = int(img_h * 0.9)
        box_w = int(box_h * target_aspect)
        if box_w > img_w * 0.95:
            box_w = int(img_w * 0.95)
            box_h = int(box_w / target_aspect)
        x1 = max(0, (img_w - box_w) // 2)
        y1 = max(0, (img_h - box_h) // 2)
        self.raw_crop_rect = [x1, y1, x1 + box_w, y1 + box_h]
        self.fit_to_screen = False
        self.chk_fit_full.setChecked(False)
        self.crop_widget.update()

    def apply_crop_live(self):
        try:
            self.gui.hardware.reset_background_media()
            self.gui.theme_data['crop_rect'] = self.raw_crop_rect
            self.gui.theme_data['fit_to_screen'] = self.fit_to_screen

            self.gui.save_theme_to_disk()
            QMessageBox.information(self, "Başarılı", "Kırpma bölgesi kasa ekranına ve önizlemeye uygulandı!")
        except Exception as e:
            print("Apply crop live note:", e)


class MediaCropWidget(QWidget):
    def __init__(self, dialog_ref):
        super().__init__()
        self.dialog = dialog_ref
        self.setMouseTracking(True)
        self.drag_edge = None
        self.drag_start_pos = QPoint()
        self.start_rect = [0, 0, 320, 1480]
        self.hover_handle = None

    def get_hit_edge(self, pos):
        if self.dialog.fit_to_screen:
            return None, Qt.ArrowCursor

        box = self.dialog.get_display_crop_rect()
        x, y = pos.x(), pos.y()

        # 1. Corner Handles (radius 14px)
        c_rad = 14
        if abs(x - box.left()) <= c_rad and abs(y - box.top()) <= c_rad:
            return 'top_left', Qt.SizeFDiagCursor
        if abs(x - box.right()) <= c_rad and abs(y - box.top()) <= c_rad:
            return 'top_right', Qt.SizeBDiagCursor
        if abs(x - box.left()) <= c_rad and abs(y - box.bottom()) <= c_rad:
            return 'bottom_left', Qt.SizeBDiagCursor
        if abs(x - box.right()) <= c_rad and abs(y - box.bottom()) <= c_rad:
            return 'bottom_right', Qt.SizeFDiagCursor

        # 2. Edge Handles (margin 12px)
        edge_margin = 12
        if abs(x - box.left()) <= edge_margin and (box.top() - 6) <= y <= (box.bottom() + 6):
            return 'left', Qt.SizeHorCursor
        if abs(x - box.right()) <= edge_margin and (box.top() - 6) <= y <= (box.bottom() + 6):
            return 'right', Qt.SizeHorCursor
        if abs(y - box.top()) <= edge_margin and (box.left() - 6) <= x <= (box.right() + 6):
            return 'top', Qt.SizeVerCursor
        if abs(y - box.bottom()) <= edge_margin and (box.left() - 6) <= x <= (box.right() + 6):
            return 'bottom', Qt.SizeVerCursor

        # 3. Inside Box (Drag Entire Area)
        if box.contains(pos):
            return 'body', Qt.SizeAllCursor

        return None, Qt.ArrowCursor

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edge, _ = self.get_hit_edge(event.pos())
            if edge:
                self.drag_edge = edge
                self.drag_start_pos = event.pos()
                self.start_rect = list(self.dialog.raw_crop_rect)
                self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        if not self.drag_edge:
            edge, cursor_shape = self.get_hit_edge(pos)
            self.setCursor(cursor_shape)
            if self.hover_handle != edge:
                self.hover_handle = edge
                self.update()
        else:
            scale = self.dialog.get_scale_factor()
            if scale <= 0:
                return

            dx = int((pos.x() - self.drag_start_pos.x()) / scale)
            dy = int((pos.y() - self.drag_start_pos.y()) / scale)

            x1, y1, x2, y2 = self.start_rect
            w0 = x2 - x1
            h0 = y2 - y1
            img_w, img_h = self.dialog.base_pil_img.size
            lock_ratio = self.dialog.chk_lock_aspect.isChecked()
            R = float(self.dialog.target_w) / float(self.dialog.target_h)

            if self.drag_edge == 'body':
                nx1 = max(0, min(img_w - w0, x1 + dx))
                ny1 = max(0, min(img_h - h0, y1 + dy))
                self.dialog.raw_crop_rect = [nx1, ny1, nx1 + w0, ny1 + h0]

            elif lock_ratio:
                min_w = 40
                min_h = max(40, int(min_w / R))

                if self.drag_edge == 'bottom_right':
                    delta = (dx * R + dy) / (R * R + 1.0)
                    new_h = max(min_h, h0 + delta)
                    new_w = new_h * R
                    if x1 + new_w > img_w:
                        new_w = img_w - x1
                        new_h = new_w / R
                    if y1 + new_h > img_h:
                        new_h = img_h - y1
                        new_w = new_h * R
                    self.dialog.raw_crop_rect = [x1, y1, int(x1 + new_w), int(y1 + new_h)]

                elif self.drag_edge == 'bottom_left':
                    delta = (-dx * R + dy) / (R * R + 1.0)
                    new_h = max(min_h, h0 + delta)
                    new_w = new_h * R
                    if new_w > x2:
                        new_w = x2
                        new_h = new_w / R
                    if y1 + new_h > img_h:
                        new_h = img_h - y1
                        new_w = new_h * R
                    self.dialog.raw_crop_rect = [int(x2 - new_w), y1, x2, int(y1 + new_h)]

                elif self.drag_edge == 'top_right':
                    delta = (dx * R - dy) / (R * R + 1.0)
                    new_h = max(min_h, h0 + delta)
                    new_w = new_h * R
                    if x1 + new_w > img_w:
                        new_w = img_w - x1
                        new_h = new_w / R
                    if new_h > y2:
                        new_h = y2
                        new_w = new_h * R
                    self.dialog.raw_crop_rect = [x1, int(y2 - new_h), int(x1 + new_w), y2]

                elif self.drag_edge == 'top_left':
                    delta = (-dx * R - dy) / (R * R + 1.0)
                    new_h = max(min_h, h0 + delta)
                    new_w = new_h * R
                    if new_w > x2:
                        new_w = x2
                        new_h = new_w / R
                    if new_h > y2:
                        new_h = y2
                        new_w = new_h * R
                    self.dialog.raw_crop_rect = [int(x2 - new_w), int(y2 - new_h), x2, y2]

                elif self.drag_edge == 'right':
                    new_w = max(min_w, min(img_w - x1, w0 + dx))
                    new_h = new_w / R
                    cy = (y1 + y2) / 2.0
                    ny1 = cy - new_h / 2.0
                    ny2 = ny1 + new_h
                    if ny1 < 0:
                        ny1 = 0
                        ny2 = min(float(img_h), new_h)
                    if ny2 > img_h:
                        ny2 = img_h
                        ny1 = max(0.0, img_h - new_h)
                    if ny2 - ny1 < new_h:
                        new_h = ny2 - ny1
                        new_w = new_h * R
                    self.dialog.raw_crop_rect = [x1, int(ny1), int(x1 + new_w), int(ny2)]

                elif self.drag_edge == 'left':
                    new_w = max(min_w, min(x2, w0 - dx))
                    new_h = new_w / R
                    cy = (y1 + y2) / 2.0
                    ny1 = cy - new_h / 2.0
                    ny2 = ny1 + new_h
                    if ny1 < 0:
                        ny1 = 0
                        ny2 = min(float(img_h), new_h)
                    if ny2 > img_h:
                        ny2 = img_h
                        ny1 = max(0.0, img_h - new_h)
                    if ny2 - ny1 < new_h:
                        new_h = ny2 - ny1
                        new_w = new_h * R
                    self.dialog.raw_crop_rect = [int(x2 - new_w), int(ny1), x2, int(ny2)]

                elif self.drag_edge == 'bottom':
                    new_h = max(min_h, min(img_h - y1, h0 + dy))
                    new_w = new_h * R
                    cx = (x1 + x2) / 2.0
                    nx1 = cx - new_w / 2.0
                    nx2 = nx1 + new_w
                    if nx1 < 0:
                        nx1 = 0
                        nx2 = min(float(img_w), new_w)
                    if nx2 > img_w:
                        nx2 = img_w
                        nx1 = max(0.0, img_w - new_w)
                    if nx2 - nx1 < new_w:
                        new_w = nx2 - nx1
                        new_h = new_w / R
                    self.dialog.raw_crop_rect = [int(nx1), y1, int(nx2), int(y1 + new_h)]

                elif self.drag_edge == 'top':
                    new_h = max(min_h, min(y2, h0 - dy))
                    new_w = new_h * R
                    cx = (x1 + x2) / 2.0
                    nx1 = cx - new_w / 2.0
                    nx2 = nx1 + new_w
                    if nx1 < 0:
                        nx1 = 0
                        nx2 = min(float(img_w), new_w)
                    if nx2 > img_w:
                        nx2 = img_w
                        nx1 = max(0.0, img_w - new_w)
                    if nx2 - nx1 < new_w:
                        new_w = nx2 - nx1
                        new_h = new_w / R
                    self.dialog.raw_crop_rect = [int(nx1), int(y2 - new_h), int(nx2), y2]

            else:
                min_size = 30
                if self.drag_edge == 'right':
                    nx2 = max(x1 + min_size, min(img_w, x2 + dx))
                    self.dialog.raw_crop_rect = [x1, y1, nx2, y2]
                elif self.drag_edge == 'left':
                    nx1 = max(0, min(x2 - min_size, x1 + dx))
                    self.dialog.raw_crop_rect = [nx1, y1, x2, y2]
                elif self.drag_edge == 'bottom':
                    ny2 = max(y1 + min_size, min(img_h, y2 + dy))
                    self.dialog.raw_crop_rect = [x1, y1, x2, ny2]
                elif self.drag_edge == 'top':
                    ny1 = max(0, min(y2 - min_size, y1 + dy))
                    self.dialog.raw_crop_rect = [x1, ny1, x2, y2]
                elif self.drag_edge == 'top_left':
                    nx1 = max(0, min(x2 - min_size, x1 + dx))
                    ny1 = max(0, min(y2 - min_size, y1 + dy))
                    self.dialog.raw_crop_rect = [nx1, ny1, x2, y2]
                elif self.drag_edge == 'top_right':
                    nx2 = max(x1 + min_size, min(img_w, x2 + dx))
                    ny1 = max(0, min(y2 - min_size, y1 + dy))
                    self.dialog.raw_crop_rect = [x1, ny1, nx2, y2]
                elif self.drag_edge == 'bottom_left':
                    nx1 = max(0, min(x2 - min_size, x1 + dx))
                    ny2 = max(y1 + min_size, min(img_h, y2 + dy))
                    self.dialog.raw_crop_rect = [nx1, y1, x2, ny2]
                elif self.drag_edge == 'bottom_right':
                    nx2 = max(x1 + min_size, min(img_w, x2 + dx))
                    ny2 = max(y1 + min_size, min(img_h, y2 + dy))
                    self.dialog.raw_crop_rect = [x1, y1, nx2, ny2]

            self.update()

    def mouseReleaseEvent(self, event):
        self.drag_edge = None
        edge, cursor_shape = self.get_hit_edge(event.pos())
        self.setCursor(cursor_shape)
        self.hover_handle = edge
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. Dark empty area background
        painter.fillRect(self.rect(), QColor(11, 15, 25))

        offset_x, offset_y = self.dialog.get_display_offsets()
        if hasattr(self.dialog, 'base_pixmap') and self.dialog.base_pixmap:
            painter.drawPixmap(offset_x, offset_y, self.dialog.base_pixmap)

        img_w, img_h = self.dialog.base_pil_img.size
        scale = self.dialog.get_scale_factor()
        disp_w = int(img_w * scale)
        disp_h = int(img_h * scale)
        img_rect = QRect(offset_x, offset_y, disp_w, disp_h)

        if self.dialog.fit_to_screen:
            painter.fillRect(img_rect, QColor(0, 0, 0, 150))
            painter.setPen(QColor(248, 250, 252))
            painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
            painter.drawText(img_rect, Qt.AlignCenter, "🖼️ Tüm Medya Ekrana Sığdırılacaktır (Kırpma Devre Dışı)")
            return

        box = self.dialog.get_display_crop_rect()

        # 2. Scrim (darkened area outside crop box)
        scrim = QColor(0, 0, 0, 165)
        # Top strip
        if box.top() > img_rect.top():
            painter.fillRect(QRect(img_rect.left(), img_rect.top(), img_rect.width(), box.top() - img_rect.top()), scrim)
        # Bottom strip
        if box.bottom() < img_rect.bottom():
            painter.fillRect(QRect(img_rect.left(), box.bottom() + 1, img_rect.width(), img_rect.bottom() - box.bottom()), scrim)
        # Left strip
        if box.left() > img_rect.left():
            top_bound = max(box.top(), img_rect.top())
            bot_bound = min(box.bottom(), img_rect.bottom())
            painter.fillRect(QRect(img_rect.left(), top_bound, box.left() - img_rect.left(), bot_bound - top_bound + 1), scrim)
        # Right strip
        if box.right() < img_rect.right():
            top_bound = max(box.top(), img_rect.top())
            bot_bound = min(box.bottom(), img_rect.bottom())
            painter.fillRect(QRect(box.right() + 1, top_bound, img_rect.right() - box.right(), bot_bound - top_bound + 1), scrim)

        # 3. Rule-of-thirds grid
        grid_pen = QPen(QColor(255, 255, 255, 45), 1, Qt.DashLine)
        painter.setPen(grid_pen)
        w3 = box.width() / 3.0
        h3 = box.height() / 3.0
        painter.drawLine(int(box.left() + w3), box.top(), int(box.left() + w3), box.bottom())
        painter.drawLine(int(box.left() + 2 * w3), box.top(), int(box.left() + 2 * w3), box.bottom())
        painter.drawLine(box.left(), int(box.top() + h3), box.right(), int(box.top() + h3))
        painter.drawLine(box.left(), int(box.top() + 2 * h3), box.right(), int(box.top() + 2 * h3))

        # 4. Crop box borders
        border_pen = QPen(QColor(99, 102, 241, 255), 2)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(box)

        inner_pen = QPen(QColor(255, 255, 255, 120), 1)
        painter.setPen(inner_pen)
        painter.drawRect(box.adjusted(1, 1, -1, -1))

        # 5. Visual Handles (Corners & Edges)
        active_handle = self.drag_edge if self.drag_edge else self.hover_handle
        normal_bg = QColor(255, 255, 255)
        hover_bg = QColor(16, 185, 129)  # High-contrast emerald green on hover/drag
        border_color = QPen(QColor(67, 56, 202), 2)

        def draw_corner(cx, cy, name):
            bg = hover_bg if active_handle == name else normal_bg
            painter.setPen(border_color)
            painter.setBrush(QBrush(bg))
            painter.drawRoundedRect(QRect(cx - 6, cy - 6, 12, 12), 3, 3)

        def draw_edge_pill(x, y, w, h, name):
            bg = hover_bg if active_handle == name else normal_bg
            painter.setPen(border_color)
            painter.setBrush(QBrush(bg))
            painter.drawRoundedRect(QRect(x, y, w, h), 4, 4)

        # 4 Corner Handles
        draw_corner(box.left(), box.top(), 'top_left')
        draw_corner(box.right(), box.top(), 'top_right')
        draw_corner(box.left(), box.bottom(), 'bottom_left')
        draw_corner(box.right(), box.bottom(), 'bottom_right')

        # 4 Edge Pill Handles
        cx = box.center().x()
        cy = box.center().y()
        draw_edge_pill(cx - 14, box.top() - 4, 28, 8, 'top')
        draw_edge_pill(cx - 14, box.bottom() - 4, 28, 8, 'bottom')
        draw_edge_pill(box.left() - 4, cy - 14, 8, 28, 'left')
        draw_edge_pill(box.right() - 4, cy - 14, 8, 28, 'right')

        # 6. Dimensions Badge
        x1, y1, x2, y2 = self.dialog.raw_crop_rect
        info_txt = f"{x2 - x1} × {y2 - y1} px"
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        fm = painter.fontMetrics()
        txt_w = fm.horizontalAdvance(info_txt) + 16
        txt_h = fm.height() + 8

        badge_y = box.top() - txt_h - 6
        if badge_y < img_rect.top() + 4:
            badge_y = box.top() + 8
        badge_x = max(img_rect.left() + 4, min(img_rect.right() - txt_w - 4, box.center().x() - txt_w // 2))

        badge_rect = QRect(badge_x, badge_y, txt_w, txt_h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(15, 23, 42, 220)))
        painter.drawRoundedRect(badge_rect, 4, 4)

        painter.setPen(QColor(248, 250, 252))
        painter.drawText(badge_rect, Qt.AlignCenter, info_txt)

class InteractiveCanvasWidget(QWidget):
    SNAP_THRESHOLD = 5

    def __init__(self, app_reference):
        super().__init__()
        self.app = app_reference
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.dragging_el_idx = None
        self.resizing_el_idx = None
        self.drag_start_pos = QPoint()
        self.el_start_x = 0
        self.el_start_y = 0
        self.el_start_w = 0
        self.el_start_h = 0
        self.group_drag_starts = {}
        self._drag_undo_pushed = False
        self.active_snap_guides = []  # List of ('v', x_px, color_q) or ('h', y_px, color_q)
        self.rubber_band_start = None
        self.rubber_band_rect = None
        self.current_pixmap = None
        self.scale_factor = 1.0
        self.update_geometry_for_theme()

    def update_geometry_for_theme(self, tw=None, th=None):
        if tw is not None and th is not None:
            theme_w = float(tw)
            theme_h = float(th)
        else:
            theme_w = float(self.app.theme_data.get('width', 320))
            theme_h = float(self.app.theme_data.get('height', 1480))

        # Scale canvas proportionally to fill the available center stage viewport
        stage = getattr(self.app, 'canvas_stage', None)
        if stage is not None and stage.width() > 120 and stage.height() > 120:
            max_w = max(80, stage.width() - 20)
            max_h = max(80, stage.height() - 20)
        else:
            max_w = 480
            max_h = 620

        scale = min(float(max_w) / max(1.0, theme_w), float(max_h) / max(1.0, theme_h))
        canvas_w = max(60, int(round(theme_w * scale)))
        canvas_h = max(60, int(round(theme_h * scale)))

        self.setFixedSize(canvas_w, canvas_h)
        self.scale_factor = float(canvas_w) / max(1.0, theme_w)
        if hasattr(self.app, 'lbl_canvas_res_badge'):
            self.app.lbl_canvas_res_badge.setText(f"📐 {int(theme_w)}×{int(theme_h)}")
        self.update()

    def update_pixmap(self, pixmap):
        self.current_pixmap = pixmap
        self.update()

    def _compute_snap(self, target_idx, raw_x, raw_y, el_w, el_h, theme_w, theme_h, modifiers):
        """
        🧲 Smart Magnetic Snap Engine:
        Snaps element edges & center to canvas center, safe margins (20px), and other elements!
        Hold Alt to temporarily bypass snapping.
        """
        self.active_snap_guides = []
        snap_enabled = getattr(self.app, 'snap_to_guides_enabled', True)
        if not snap_enabled or (modifiers & Qt.AltModifier):
            return raw_x, raw_y

        thresh = self.SNAP_THRESHOLD
        snapped_x = raw_x
        snapped_y = raw_y

        # Vertical guide candidates (X positions): (coord, is_center_line)
        v_targets = [
            (theme_w // 2, True),
            (20, False),
            (theme_w - 20, False)
        ]
        # Horizontal guide candidates (Y positions): (coord, is_center_line)
        h_targets = [
            (theme_h // 2, True),
            (20, False),
            (theme_h - 20, False)
        ]

        selected_indices = getattr(self.app, 'selected_element_indices', set())
        elements = self.app.theme_data.get('elements', [])
        for idx, other in enumerate(elements):
            if idx == target_idx or idx in selected_indices or other.get('hidden', False):
                continue
            ox = int(other.get('x', 0))
            oy = int(other.get('y', 0))
            ow = int(other.get('width', 100))
            oh = int(other.get('height', 40))
            v_targets.extend([(ox, False), (ox + ow // 2, True), (ox + ow, False)])
            h_targets.extend([(oy, False), (oy + oh // 2, True), (oy + oh, False)])

        # Check X snap (left, center, right of dragged element)
        best_dx = thresh + 1
        matched_vx = None
        matched_v_center = False
        my_x_points = [(raw_x, 0), (raw_x + el_w // 2, el_w // 2), (raw_x + el_w, el_w)]
        for my_val, offset in my_x_points:
            for tx, is_c in v_targets:
                dist = abs(my_val - tx)
                if dist <= thresh and dist < best_dx:
                    best_dx = dist
                    snapped_x = tx - offset
                    matched_vx = tx
                    matched_v_center = is_c

        if matched_vx is not None:
            col = QColor(244, 63, 94, 230) if matched_v_center else QColor(6, 182, 212, 220)
            self.active_snap_guides.append(('v', matched_vx, col))

        # Check Y snap (top, center, bottom of dragged element)
        best_dy = thresh + 1
        matched_hy = None
        matched_h_center = False
        my_y_points = [(raw_y, 0), (raw_y + el_h // 2, el_h // 2), (raw_y + el_h, el_h)]
        for my_val, offset in my_y_points:
            for ty, is_c in h_targets:
                dist = abs(my_val - ty)
                if dist <= thresh and dist < best_dy:
                    best_dy = dist
                    snapped_y = ty - offset
                    matched_hy = ty
                    matched_h_center = is_c

        if matched_hy is not None:
            col = QColor(244, 63, 94, 230) if matched_h_center else QColor(6, 182, 212, 220)
            self.active_snap_guides.append(('h', matched_hy, col))

        snapped_x = max(0, min(theme_w - el_w, snapped_x))
        snapped_y = max(0, min(theme_h - el_h, snapped_y))
        return snapped_x, snapped_y

    def mousePressEvent(self, event):
        self.setFocus()
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            modifiers = event.modifiers()
            elements = self.app.theme_data.get('elements', [])
            self._drag_undo_pushed = False
            self.active_snap_guides = []

            for idx in reversed(range(len(elements))):
                el = elements[idx]
                if el.get('hidden', False):
                    continue
                canvas_x = int(el.get('x', 30) * self.scale_factor)
                canvas_y = int(el.get('y', 60) * self.scale_factor)
                canvas_w = int(el.get('width', 260) * self.scale_factor)
                canvas_h = int(el.get('height', 45) * self.scale_factor)
                is_locked = bool(el.get('locked', False))

                # 1. Check bottom-right resize handle (if unlocked)
                handle_x = canvas_x + canvas_w - 14
                handle_y = canvas_y + canvas_h - 14
                if not is_locked and handle_x <= pos.x() <= handle_x + 24 and handle_y <= pos.y() <= handle_y + 24:
                    self.resizing_el_idx = idx
                    self.drag_start_pos = pos
                    self.el_start_w = el.get('width', 260)
                    self.el_start_h = el.get('height', 45)
                    self.app.select_element_by_index(idx, clear_others=True)
                    return

                # 2. Check element body hit
                if canvas_x <= pos.x() <= canvas_x + canvas_w and canvas_y <= pos.y() <= canvas_y + canvas_h:
                    if modifiers & (Qt.ControlModifier | Qt.ShiftModifier):
                        self.app.toggle_element_multi_selection(idx)
                    else:
                        if idx not in getattr(self.app, 'selected_element_indices', set()):
                            self.app.select_element_by_index(idx, clear_others=True)
                        else:
                            self.app.select_element_by_index(idx, clear_others=False)

                    if not is_locked:
                        self.dragging_el_idx = idx
                        self.drag_start_pos = pos
                        self.el_start_x = el.get('x', 30)
                        self.el_start_y = el.get('y', 60)
                        self.group_drag_starts = {
                            sel_i: (
                                self.app.theme_data['elements'][sel_i].get('x', 30),
                                self.app.theme_data['elements'][sel_i].get('y', 60)
                            )
                            for sel_i in getattr(self.app, 'selected_element_indices', {idx})
                            if 0 <= sel_i < len(elements) and not elements[sel_i].get('locked', False)
                        }
                    return

            # Clicked empty space -> start rubber-band marquee selection
            if not (modifiers & (Qt.ControlModifier | Qt.ShiftModifier)):
                self.app.deselect_element()
            self.rubber_band_start = pos
            self.rubber_band_rect = QRect(pos, pos)

    def mouseMoveEvent(self, event):
        pos = event.pos()
        try:
            theme_w = int(self.app.theme_data.get('width', 320))
            theme_h = int(self.app.theme_data.get('height', 1480))
            elements = self.app.theme_data.get('elements', [])

            if self.dragging_el_idx is not None and 0 <= self.dragging_el_idx < len(elements):
                el = elements[self.dragging_el_idx]
                if el.get('locked', False):
                    return
                if not self._drag_undo_pushed:
                    self.app.push_undo_state("Öge Taşıma")
                    self._drag_undo_pushed = True

                dx = int((pos.x() - self.drag_start_pos.x()) / self.scale_factor)
                dy = int((pos.y() - self.drag_start_pos.y()) / self.scale_factor)
                el_w = el.get('width', 260)
                el_h = el.get('height', 45)
                raw_x = max(0, min(theme_w - el_w, self.el_start_x + dx))
                raw_y = max(0, min(theme_h - el_h, self.el_start_y + dy))

                snapped_x, snapped_y = self._compute_snap(
                    self.dragging_el_idx, raw_x, raw_y, el_w, el_h, theme_w, theme_h, event.modifiers()
                )
                eff_dx = snapped_x - self.el_start_x
                eff_dy = snapped_y - self.el_start_y

                if len(self.group_drag_starts) > 1:
                    for sel_i, (sx, sy) in self.group_drag_starts.items():
                        if 0 <= sel_i < len(elements):
                            s_el = elements[sel_i]
                            sw = s_el.get('width', 260)
                            sh = s_el.get('height', 45)
                            s_el['x'] = max(0, min(theme_w - sw, sx + eff_dx))
                            s_el['y'] = max(0, min(theme_h - sh, sy + eff_dy))
                else:
                    el['x'] = snapped_x
                    el['y'] = snapped_y

                if hasattr(self.app, '_sync_selected_element_geom_spinboxes'):
                    self.app._sync_selected_element_geom_spinboxes(el)
                self.app.save_theme_to_disk()
                self.update()

            elif self.resizing_el_idx is not None and 0 <= self.resizing_el_idx < len(elements):
                el = elements[self.resizing_el_idx]
                if el.get('locked', False):
                    return
                if not self._drag_undo_pushed:
                    self.app.push_undo_state("Öge Boyutlandırma")
                    self._drag_undo_pushed = True

                dw = int((pos.x() - self.drag_start_pos.x()) / self.scale_factor)
                dh = int((pos.y() - self.drag_start_pos.y()) / self.scale_factor)
                new_w = max(30, min(theme_w - el.get('x', 0), self.el_start_w + dw))
                new_h = max(20, min(theme_h - el.get('y', 0), self.el_start_h + dh))
                el['width'] = new_w
                el['height'] = new_h
                if hasattr(self.app, '_sync_selected_element_geom_spinboxes'):
                    self.app._sync_selected_element_geom_spinboxes(el)
                self.app.save_theme_to_disk()
                self.update()

            elif self.rubber_band_start is not None:
                self.rubber_band_rect = QRect(self.rubber_band_start, pos).normalized()
                self.update()
            else:
                # Update cursor shape on hover
                for idx in reversed(range(len(elements))):
                    el = elements[idx]
                    if el.get('hidden', False) or el.get('locked', False):
                        continue
                    cx = int(el.get('x', 30) * self.scale_factor)
                    cy = int(el.get('y', 60) * self.scale_factor)
                    cw = int(el.get('width', 260) * self.scale_factor)
                    ch = int(el.get('height', 45) * self.scale_factor)
                    if cx + cw - 14 <= pos.x() <= cx + cw + 10 and cy + ch - 14 <= pos.y() <= cy + ch + 10:
                        self.setCursor(Qt.SizeFDiagCursor)
                        return
                    if cx <= pos.x() <= cx + cw and cy <= pos.y() <= cy + ch:
                        self.setCursor(Qt.SizeAllCursor)
                        return
                self.setCursor(Qt.ArrowCursor)
        except Exception as e:
            print("Canvas move note:", e)

    def mouseReleaseEvent(self, event):
        if self.rubber_band_rect is not None and self.rubber_band_rect.width() > 6 and self.rubber_band_rect.height() > 6:
            # Select all elements intersecting rubber_band_rect
            elements = self.app.theme_data.get('elements', [])
            hit_indices = []
            for idx, el in enumerate(elements):
                if el.get('hidden', False):
                    continue
                rx = int(el.get('x', 30) * self.scale_factor)
                ry = int(el.get('y', 60) * self.scale_factor)
                rw = int(el.get('width', 260) * self.scale_factor)
                rh = int(el.get('height', 45) * self.scale_factor)
                if self.rubber_band_rect.intersects(QRect(rx, ry, rw, rh)):
                    hit_indices.append(idx)
            if hit_indices:
                self.app.set_multi_selection(hit_indices)

        self.dragging_el_idx = None
        self.resizing_el_idx = None
        self.group_drag_starts = {}
        self.active_snap_guides = []
        self.rubber_band_start = None
        self.rubber_band_rect = None
        self.update()

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        step = 10 if (mods & Qt.ShiftModifier) else 1

        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            dx = -step if key == Qt.Key_Left else (step if key == Qt.Key_Right else 0)
            dy = -step if key == Qt.Key_Up else (step if key == Qt.Key_Down else 0)
            self.app.nudge_selected_elements(dx, dy)
            event.accept()
            return
        elif key == Qt.Key_Delete:
            self.app.delete_selected_element()
            event.accept()
            return
        elif key == Qt.Key_Z and (mods & Qt.ControlModifier):
            if mods & Qt.ShiftModifier:
                self.app.redo_action()
            else:
                self.app.undo_action()
            event.accept()
            return
        elif key == Qt.Key_Y and (mods & Qt.ControlModifier):
            self.app.redo_action()
            event.accept()
            return
        elif key == Qt.Key_D and (mods & Qt.ControlModifier):
            self.app.duplicate_selected_element()
            event.accept()
            return
        elif key == Qt.Key_A and (mods & Qt.ControlModifier):
            all_idx = [i for i, el in enumerate(self.app.theme_data.get('elements', [])) if not el.get('hidden', False)]
            self.app.set_multi_selection(all_idx)
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.current_pixmap:
            painter.drawPixmap(0, 0, self.current_pixmap)

        # 🧲 Draw Smart Magnetic Alignment Snap Guides
        for g_type, coord, col in self.active_snap_guides:
            pen = QPen(col, 1.8, Qt.DashLine)
            painter.setPen(pen)
            if g_type == 'v':
                cx = int(coord * self.scale_factor)
                painter.drawLine(cx, 0, cx, self.height())
            elif g_type == 'h':
                cy = int(coord * self.scale_factor)
                painter.drawLine(0, cy, self.width(), cy)

        # 📐 Draw Live Coordinate & Size HUD Badge while dragging or resizing
        active_idx = self.dragging_el_idx if self.dragging_el_idx is not None else self.resizing_el_idx
        elements = self.app.theme_data.get('elements', [])
        if active_idx is not None and 0 <= active_idx < len(elements):
            el = elements[active_idx]
            ex = int(el.get('x', 0))
            ey = int(el.get('y', 0))
            ew = int(el.get('width', 0))
            eh = int(el.get('height', 0))
            hud_text = f"X:{ex} Y:{ey} | {ew}×{eh}"
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(hud_text) + 12
            th = fm.height() + 6
            bx = max(2, min(self.width() - tw - 2, int((ex + ew / 2) * self.scale_factor) - tw // 2))
            by = int(ey * self.scale_factor) - th - 4
            if by < 2:
                by = min(self.height() - th - 2, int((ey + eh) * self.scale_factor) + 4)
            badge_rect = QRect(bx, by, tw, th)
            painter.setPen(QPen(QColor(99, 102, 241, 220), 1))
            painter.setBrush(QBrush(QColor(15, 23, 42, 235)))
            painter.drawRoundedRect(badge_rect, 4, 4)
            painter.setPen(QColor(248, 250, 252))
            painter.drawText(badge_rect, Qt.AlignCenter, hud_text)

        # 🔲 Draw Rubber-Band Marquee Selection Box
        if self.rubber_band_rect is not None:
            painter.setPen(QPen(QColor(56, 189, 248, 220), 1.5, Qt.DashLine))
            painter.setBrush(QBrush(QColor(56, 189, 248, 45)))
            painter.drawRect(self.rubber_band_rect)

CHECKMARK_PNG = os.path.join(APP_BUNDLE_DIR, "checkmark.png")
RADIO_PNG = os.path.join(APP_BUNDLE_DIR, "radio_checked.png")
if not os.path.exists(CHECKMARK_PNG):
    CHECKMARK_PNG = os.path.join(APP_USER_DATA_DIR, "checkmark.png")
if not os.path.exists(RADIO_PNG):
    RADIO_PNG = os.path.join(APP_USER_DATA_DIR, "radio_checked.png")

def ensure_ui_icons():
    try:
        if not os.path.exists(CHECKMARK_PNG):
            img = Image.new('RGBA', (24, 24), (16, 185, 129, 255))
            draw = ImageDraw.Draw(img)
            draw.line([(4, 12), (9, 17), (19, 6)], fill=(255, 255, 255, 255), width=3)
            img.save(CHECKMARK_PNG)

        if not os.path.exists(RADIO_PNG):
            img = Image.new('RGBA', (24, 24), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([1, 1, 22, 22], outline=(99, 102, 241, 255), width=2)
            draw.ellipse([6, 6, 17, 17], fill=(16, 185, 129, 255))
            img.save(RADIO_PNG)
    except Exception as e:
        print("UI icons note:", e)

ensure_ui_icons()
CHECKMARK_QSS_PATH = CHECKMARK_PNG.replace('\\', '/')
RADIO_QSS_PATH = RADIO_PNG.replace('\\', '/')

def get_cyberpulse_global_stylesheet():
    return f"""
        QMainWindow, QDialog {{
            background-color: #060e20;
        }}
        QWidget {{
            color: #dae2fd;
            font-family: 'Segoe UI', Arial, sans-serif;
        }}
        QGroupBox {{
            background-color: #0b1326;
            border: 1px solid #1e293b;
            border-radius: 10px;
            margin-top: 12px;
            padding-top: 8px;
            font-weight: 800;
            font-size: 12px;
            color: #c0c1ff;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 6px;
            color: #38bdf8;
        }}
        QPushButton {{
            background-color: #171f33;
            border: 1px solid #2d3748;
            border-radius: 6px;
            padding: 7px 12px;
            color: #f8fafc;
            font-weight: 700;
        }}
        QPushButton:hover {{
            background-color: #222a3d;
            border-color: #8083ff;
        }}
        QPushButton:pressed {{
            background-color: #2d3449;
        }}
        QListWidget {{
            background-color: #0b1326;
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 5px;
            color: #f8fafc;
        }}
        QListWidget::item {{
            padding: 7px 8px;
            border-radius: 6px;
            margin-bottom: 3px;
            color: #e2e8f0;
        }}
        QListWidget::item:hover {{
            background-color: #171f33;
        }}
        QListWidget::item:selected {{
            background-color: #8083ff;
            color: #07006c;
            font-weight: 800;
        }}
        QLineEdit, QSpinBox, QKeySequenceEdit {{
            background-color: #171f33;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 6px 8px;
            color: #ffffff;
            font-weight: 700;
        }}
        QLineEdit:focus, QSpinBox:focus, QKeySequenceEdit:focus {{
            border: 1px solid #38bdf8;
            background-color: #1e293b;
        }}
        /* 🚀 STITCH V2.4 HIGH-CONTRAST QCOMBOBOX DROPDOWN STYLES */
        QComboBox {{
            background-color: #171f33;
            border: 1px solid #434655;
            border-radius: 6px;
            padding: 5px 10px;
            color: #ffffff;
            font-weight: 700;
            font-size: 12px;
            min-height: 22px;
        }}
        QComboBox:hover {{
            border-color: #8083ff;
            background-color: #222a3d;
        }}
        QComboBox QAbstractItemView {{
            background-color: #0b1326;
            color: #ffffff;
            selection-background-color: #8083ff;
            selection-color: #07006c;
            border: 1px solid #8083ff;
            outline: none;
            padding: 4px;
        }}
        QComboBox::item {{
            color: #ffffff;
            background-color: #0b1326;
            padding: 7px 12px;
            font-size: 12px;
            font-weight: 700;
        }}
        QComboBox::item:selected {{
            background-color: #8083ff;
            color: #07006c;
            font-weight: 800;
        }}
        /* 🚀 STITCH V2.4 HIGH-CONTRAST QCHECKBOX & INDICATOR STYLES */
        QCheckBox {{
            color: #f8fafc;
            font-weight: 700;
            font-size: 12px;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 19px;
            height: 19px;
            background-color: #171f33;
            border: 2px solid #8083ff;
            border-radius: 5px;
        }}
        QCheckBox::indicator:hover {{
            border-color: #38bdf8;
            background-color: #222a3d;
        }}
        QCheckBox::indicator:checked {{
            background-color: #10b981;
            border: 2px solid #10b981;
            image: url("{CHECKMARK_QSS_PATH}");
        }}
        /* 🚀 STITCH V2.4 HIGH-CONTRAST QRADIOBUTTON INDICATOR STYLES */
        QRadioButton {{
            color: #f8fafc;
            font-weight: 700;
            font-size: 12px;
            spacing: 8px;
        }}
        QRadioButton::indicator {{
            width: 19px;
            height: 19px;
            background-color: #171f33;
            border: 2px solid #8083ff;
            border-radius: 10px;
        }}
        QRadioButton::indicator:hover {{
            border-color: #38bdf8;
            background-color: #222a3d;
        }}
        QRadioButton::indicator:checked {{
            background-color: #0b1326;
            border: 2px solid #10b981;
            image: url("{RADIO_QSS_PATH}");
        }}
        QScrollBar:vertical {{
            background: #060e20;
            width: 6px;
            margin: 0px;
            border-radius: 3px;
        }}
        QScrollBar::handle:vertical {{
            background: #222a3d;
            min-height: 24px;
            border-radius: 3px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #8083ff;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: #060e20;
        }}
        QScrollBar:horizontal {{
            background: #060e20;
            height: 6px;
            margin: 0px;
            border-radius: 3px;
        }}
        QScrollBar::handle:horizontal {{
            background: #222a3d;
            min-width: 24px;
            border-radius: 3px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: #8083ff;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: #060e20;
        }}
        QSplitter::handle {{
            background-color: #0b1326;
        }}
        QSplitter::handle:hover {{
            background-color: #8083ff;
        }}
        /* 🚀 HIGH-CONTRAST QMENU & TRAY MENU STYLES */
        QMenu {{
            background-color: #0b1326;
            color: #ffffff;
            border: 1px solid #8083ff;
            border-radius: 8px;
            padding: 6px;
        }}
        QMenu::item {{
            padding: 8px 24px 8px 12px;
            color: #ffffff;
            font-weight: 700;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background-color: #8083ff;
            color: #07006c;
        }}
        QMessageBox, QInputDialog {{
            background-color: #0b1326;
            color: #ffffff;
            font-size: 13px;
        }}
        QMessageBox QLabel, QInputDialog QLabel {{
            color: #ffffff;
            font-size: 13px;
            font-weight: 700;
            padding: 8px;
        }}
        QMessageBox QPushButton, QInputDialog QPushButton {{
            background-color: #8083ff;
            color: #07006c;
            font-size: 13px;
            font-weight: 900;
            padding: 6px 16px;
            border-radius: 6px;
            min-width: 80px;
        }}
        QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {{
            background-color: #a5b4fc;
        }}
        /* 🚀 HIGH-CONTRAST QDATETIMEEDIT & QCALENDARWIDGET STYLES (CRYSTAL CLEAR NUMBERS & HEADERS) */
        QDateTimeEdit {{
            background-color: #0f172a;
            border: 2px solid #6366f1;
            border-radius: 6px;
            padding: 6px 10px;
            color: #ffffff;
            font-weight: bold;
            font-size: 13px;
        }}
        QDateTimeEdit::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 26px;
            border-left-width: 1px;
            border-left-color: #6366f1;
            border-left-style: solid;
        }}
        QCalendarWidget {{
            background-color: #0f172a;
            color: #ffffff;
        }}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background-color: #1e293b;
            min-height: 40px;
        }}
        QCalendarWidget QToolButton {{
            color: #ffffff;
            background-color: #334155;
            font-size: 13px;
            font-weight: 800;
            border-radius: 6px;
            padding: 6px 12px;
            margin: 2px;
        }}
        QCalendarWidget QToolButton:hover {{
            background-color: #6366f1;
            color: #ffffff;
        }}
        QCalendarWidget QMenu {{
            background-color: #0f172a;
            color: #ffffff;
            font-weight: bold;
        }}
        QCalendarWidget QSpinBox {{
            background-color: #0f172a;
            color: #ffffff;
            font-size: 13px;
            font-weight: bold;
            selection-background-color: #6366f1;
            selection-color: #ffffff;
        }}
        QCalendarWidget QTableView {{
            background-color: #090d16;
            color: #f8fafc;
            selection-background-color: #6366f1;
            selection-color: #ffffff;
            font-size: 13px;
            font-weight: 800;
            alternate-background-color: #1e293b;
            gridline-color: #334155;
        }}
        QCalendarWidget QTableView:enabled {{
            color: #ffffff;
            background-color: #090d16;
        }}
        QCalendarWidget QAbstractItemView:enabled {{
            color: #ffffff;
            background-color: #090d16;
            selection-background-color: #6366f1;
            selection-color: #ffffff;
        }}
        QCalendarWidget QAbstractItemView:disabled {{
            color: #64748b;
        }}
    """

class CyberPulseStudioGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"⚡ CYBERPULSE LCD Studio v{APP_VERSION}")
        self.setMinimumSize(900, 580)
        self.resize(1100, 860)
        
        self.app_icon, self.app_pixmap = generate_cyberpulse_logo()
        self.setWindowIcon(self.app_icon)

        self.setStyleSheet(get_cyberpulse_global_stylesheet())

        self.app_settings = {
            'autostart': False,
            'enable_tray': True,
            'start_minimized': False,
            'auto_stream_on_start': True,
            'auto_check_updates': True,
            'auto_rotate_themes': False,
            'rotate_val': 30,
            'rotate_unit': 'sec',
            'rotate_mode': 'sequential',
            'auto_game_theme_enabled': True,
            'keep_game_theme_on_alttab': True,
            'auto_game_theme_name': '',
            'game_profiles': {}
        }
        self.load_app_settings()

        self.theme_data = {
            'name': 'Cyberpunk320x1480',
            'width': 320,
            'height': 1480,
            'rotation': 180,
            'bg_path': None,
            'crop_rect': None,
            'fit_to_screen': False,
            'refresh_sec': 1.0,
            'thermal_alert_limit': 82,
            'selected_id': None,
            'elements': [
                {'id': 'el_1', 'type': 'marquee', 'sensorId': 'sistem_ozellikleri', 'label': 'MY GAMING RIG', 'x': 20, 'y': 40, 'width': 280, 'height': 40, 'textColor': '#06b6d4', 'percentColor': '#06b6d4', 'graphicColor': '#06b6d4', 'bgColor': '#0f172a', 'bgOpacity': 60, 'fontSize': 24, 'fontFamily': 'Arial', 'isBold': True, 'isItalic': False, 'textAlign': 'center', 'showBorder': True, 'layoutStyle': 'side'},
                {'id': 'el_2', 'type': 'sensor', 'sensorId': 'cpu_temp', 'label': 'CPU Sıcaklığı', 'x': 40, 'y': 140, 'width': 240, 'height': 50, 'textColor': '#ffffff', 'percentColor': '#38bdf8', 'graphicColor': '#f43f5e', 'bgColor': '#0f172a', 'bgOpacity': 50, 'fontSize': 32, 'fontFamily': 'Segoe UI', 'isBold': True, 'isItalic': False, 'textAlign': 'left', 'showBorder': True, 'layoutStyle': 'side'},
                {'id': 'el_3', 'type': 'animated_fan', 'sensorId': 'gpu_load', 'label': 'GPU FAN', 'x': 60, 'y': 300, 'width': 180, 'height': 180, 'textColor': '#ffffff', 'percentColor': '#38bdf8', 'graphicColor': '#fbbf24', 'bgColor': '#0f172a', 'bgOpacity': 40, 'fontSize': 20, 'fontFamily': 'Arial', 'isBold': False, 'isItalic': False, 'textAlign': 'center', 'showBorder': False, 'layoutStyle': 'side'},
                {'id': 'el_4', 'type': 'gauge', 'sensorId': 'cpu_load', 'label': 'CPU YÜKÜ', 'x': 20, 'y': 800, 'width': 280, 'height': 45, 'textColor': '#ffffff', 'percentColor': '#ffffff', 'graphicColor': '#38bdf8', 'bgColor': '#0f172a', 'bgOpacity': 60, 'fontSize': 16, 'fontFamily': 'Segoe UI', 'isBold': False, 'isItalic': False, 'textAlign': 'left', 'showBorder': True, 'layoutStyle': 'side'}
            ]
        }
        self.selected_element_idx = None
        self.selected_element_indices = set()
        self.undo_stack = []
        self.redo_stack = []
        self.snap_to_guides_enabled = True
        self.is_streaming = False
        self.is_cropping = False
        
        self.last_theme_rotate_time = time.time()
        self.current_theme_rotate_idx = 0

        self.sensor = SensorMonitor()
        self.sensor.cpu_temp_offset = self.app_settings.get('cpu_temp_offset', 0)
        self.sensor.custom_location = self.app_settings.get('custom_weather_location', '')
        self.primary_usb_hardware = HardwareDriver(width=320, height=1480)
        self.hardware = self.primary_usb_hardware

        self.load_theme_from_disk()

        # 🖥️ Multi-Screen Independent Theme Workspaces (Portable across any PC)
        self.screen_workspaces = {}
        self.active_screen_slot_id = 'usb_lcd_1'
        self.init_screen_workspaces()

        # Connect live Qt monitor hotplug signals so plugging/unplugging screens on any PC auto-updates tabs
        try:
            app_inst = QApplication.instance()
            if app_inst:
                app_inst.screenAdded.connect(self.on_system_screens_changed)
                app_inst.screenRemoved.connect(self.on_system_screens_changed)
        except Exception:
            pass

        self.init_ui()
        try:
            app_inst = QApplication.instance()
            if app_inst:
                self._lang_event_filter = LanguageEventFilter(self)
                app_inst.installEventFilter(self._lang_event_filter)
        except Exception:
            pass
        self.refresh_multi_screen_bar_ui()
        self.auto_adjust_window_to_canvas()
        self.update_canvas_geometry()
        self.populate_com_ports()
        self.update_stream_status_ui()
        self.apply_current_language()
        self.setup_system_tray()
        self.setup_global_hotkeys()

        self.stream_worker = HardwareStreamWorker(self)
        self.stream_worker.frame_ready.connect(self.on_hdmi_frame_ready)
        self.stream_worker.screen_frame_ready.connect(self.on_screen_frame_ready)
        self.stream_worker.start()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_gui_tick)
        self.timer.start(50)

        if self.app_settings.get('auto_detect_screens', True):
            QTimer.singleShot(1500, self.check_and_prompt_case_screens_on_startup)

        if self.app_settings.get('auto_stream_on_start', True):
            QTimer.singleShot(1000, self.auto_start_streaming)

        if self.app_settings.get('auto_check_updates', True):
            QTimer.singleShot(2200, lambda: self.start_update_check(silent=True))

        is_boot_autostart = ('--autostart' in sys.argv or '--minimized' in sys.argv)
        if is_boot_autostart and self.app_settings.get('start_minimized', False):
            QTimer.singleShot(500, self.hide)

    def setup_global_hotkeys(self):
        if not HAS_KEYBOARD:
            return
        
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

        if not self.app_settings.get('enable_hotkeys', True):
            return

        self.hotkey_bridge = HotkeyBridge()
        self.hotkey_bridge.next_theme_signal.connect(lambda: self.switch_theme_relative(1))
        self.hotkey_bridge.prev_theme_signal.connect(lambda: self.switch_theme_relative(-1))
        self.hotkey_bridge.toggle_stream_signal.connect(self.toggle_live_stream)
        self.hotkey_bridge.random_theme_signal.connect(self.switch_to_random_theme)
        self.hotkey_bridge.toggle_window_signal.connect(self.toggle_window_visibility)

        # In-App QShortcuts for zero-overhead window focus
        try:
            from PyQt5.QtWidgets import QShortcut
            QShortcut(QKeySequence("Ctrl+Right"), self, lambda: self.switch_theme_relative(1))
            QShortcut(QKeySequence("Ctrl+Left"), self, lambda: self.switch_theme_relative(-1))
            QShortcut(QKeySequence("Space"), self, self.toggle_live_stream)
            QShortcut(QKeySequence("Ctrl+Z"), self, self.undo_action)
            QShortcut(QKeySequence("Ctrl+Y"), self, self.redo_action)
            QShortcut(QKeySequence("Ctrl+D"), self, self.duplicate_selected_element)
            QShortcut(QKeySequence("Delete"), self, self.delete_selected_element)
        except Exception:
            pass

        def register_safe_hotkey(hk_str, signal):
            if not hk_str or not isinstance(hk_str, str):
                return
            try:
                clean_hk = hk_str.strip().lower()
                # 🔒 SECURITY: Validate hotkey length, allowed chars, and require a modifier or function key
                if len(clean_hk) > 40 or not re.match(r'^[a-z0-9\+\-\s_]+$', clean_hk):
                    return
                parts = [p.strip() for p in clean_hk.split('+') if p.strip()]
                has_modifier = any(m in parts for m in ('ctrl', 'control', 'alt', 'shift', 'win', 'windows'))
                has_fkey = any(re.match(r'^f([1-9]|1[0-2])$', p) for p in parts)
                if not (has_modifier or has_fkey):
                    return
                keyboard.add_hotkey(clean_hk, lambda: signal.emit(), suppress=False)
            except Exception as e:
                print(f"Hotkey '{hk_str}' registration note:", e)

        register_safe_hotkey(self.app_settings.get('hotkey_next_theme', 'Ctrl+Alt+Right'), self.hotkey_bridge.next_theme_signal)
        register_safe_hotkey(self.app_settings.get('hotkey_prev_theme', 'Ctrl+Alt+Left'), self.hotkey_bridge.prev_theme_signal)
        register_safe_hotkey(self.app_settings.get('hotkey_toggle_stream', 'Ctrl+Alt+P'), self.hotkey_bridge.toggle_stream_signal)
        register_safe_hotkey(self.app_settings.get('hotkey_random_theme', 'Ctrl+Alt+R'), self.hotkey_bridge.random_theme_signal)
        register_safe_hotkey(self.app_settings.get('hotkey_toggle_window', 'Ctrl+Alt+S'), self.hotkey_bridge.toggle_window_signal)

    def switch_to_random_theme(self):
        try:
            themes = get_all_preset_themes()
            if themes:
                target = random.choice(themes)
                t_json = load_preset_theme_data(target)

                if t_json and isinstance(t_json, dict):
                    self.hardware.reset_background_media()
                    with self.hardware.render_lock:
                        self.theme_data.clear()
                        self.theme_data.update(t_json)
                    self.hardware.set_resolution(self.theme_data.get('width', 320), self.theme_data.get('height', 1480))
                    self.update_canvas_geometry()
                    self.refresh_elements_list()
                    self.save_theme_to_disk()
        except Exception as e:
            print("Random theme note:", e)

    def toggle_window_visibility(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()

    def load_app_settings(self):
        try:
            if os.path.isfile(APP_SETTINGS_FILE) and os.path.getsize(APP_SETTINGS_FILE) <= 512 * 1024:
                with open(APP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    if loaded and isinstance(loaded, dict):
                        self.app_settings.update(loaded)
        except Exception as e:
            print("Load app settings note:", e)

    def save_app_settings(self):
        try:
            tmp_file = APP_SETTINGS_FILE + ".tmp"
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(self.app_settings, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, APP_SETTINGS_FILE)
        except Exception as e:
            print("Save app settings note:", e)

    def setup_system_tray(self):
        if self.app_settings.get('enable_tray', True):
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(self.app_icon)
            self.tray_icon.setToolTip("CYBERPULSE LCD Studio")

            tray_menu = QMenu()
            show_action = QAction("⚡ Stüdyoyu Göster", self)
            show_action.triggered.connect(self.showNormal)
            tray_menu.addAction(show_action)

            toggle_stream_action = QAction("🚀 Yansıtmayı Başlat / Durdur", self)
            toggle_stream_action.triggered.connect(self.toggle_live_stream)
            tray_menu.addAction(toggle_stream_action)

            tray_menu.addSeparator()

            next_theme_action = QAction("⏭️ Sonraki Tema", self)
            next_theme_action.triggered.connect(lambda: self.switch_theme_relative(1))
            tray_menu.addAction(next_theme_action)

            prev_theme_action = QAction("⏮️ Önceki Tema", self)
            prev_theme_action.triggered.connect(lambda: self.switch_theme_relative(-1))
            tray_menu.addAction(prev_theme_action)

            tray_menu.addSeparator()

            quit_action = QAction("❌ Çıkış", self)
            quit_action.triggered.connect(QApplication.instance().quit)
            tray_menu.addAction(quit_action)

            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self.on_tray_activated)
            self.tray_icon.show()

    def switch_theme_relative(self, delta):
        try:
            active_sid = getattr(self, 'active_screen_slot_id', 'usb_lcd_1')
            if hasattr(self, 'rotate_screen_workspace_theme') and active_sid in getattr(self, 'screen_workspaces', {}):
                ok = self.rotate_screen_workspace_theme(active_sid, delta=delta)
                if ok:
                    theme_disp_name = self.theme_data.get('name', 'Tema')
                    if hasattr(self, 'tray_icon') and self.tray_icon:
                        self.tray_icon.showMessage(
                            "🎨 Tema Değiştirildi",
                            f"Aktif Tema: {theme_disp_name}",
                            QSystemTrayIcon.Information,
                            2000
                        )
                return

            themes = get_all_preset_themes()
            if not themes:
                return

            current_name = str(self.theme_data.get('name', '')).strip().lower()
            curr_idx = 0
            for i, item in enumerate(themes):
                if item['name'].strip().lower() == current_name:
                    curr_idx = i
                    break

            new_idx = (curr_idx + delta) % len(themes)
            target = themes[new_idx]

            t_json = load_preset_theme_data(target)

            if t_json and isinstance(t_json, dict):
                self.hardware.reset_background_media()
                with self.hardware.render_lock:
                    self.theme_data.clear()
                    self.theme_data.update(t_json)
                self.hardware.set_resolution(self.theme_data.get('width', 320), self.theme_data.get('height', 1480))
                self.update_canvas_geometry()
                self.refresh_elements_list()
                self.save_theme_to_disk()

                theme_disp_name = t_json.get('name', target['name'])
                if hasattr(self, 'tray_icon') and self.tray_icon:
                    self.tray_icon.showMessage(
                        "🎨 Tema Değiştirildi",
                        f"Aktif Tema: {theme_disp_name}",
                        QSystemTrayIcon.Information,
                        2000
                    )
        except Exception as e:
            print("Switch theme relative note:", e)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()
                self.activateWindow()

    _ALLOWED_BG_EXTS = {'.cptheme', '.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif', '.mp4', '.avi', '.mkv', '.mov', '.webm'}
    _ALLOWED_IMG_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif'}
    _VALID_HDMI_VIEW_MODES = {'ambient_dashboard', 'ambient_fit', 'letterbox', 'stretch', 'canvas'}
    MAX_SCREEN_WORKSPACES = 12

    def load_theme_from_disk(self):
        try:
            if os.path.isfile(LAST_THEME_FILE) and os.path.getsize(LAST_THEME_FILE) <= 4 * 1024 * 1024:
                with open(LAST_THEME_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    if loaded and isinstance(loaded, dict):
                        self._normalize_portable_theme_paths(loaded)
                        with self.hardware.render_lock:
                            self.theme_data.update(loaded)
                        self.hardware.set_resolution(self.theme_data.get('width', 320), self.theme_data.get('height', 1480))
                        print("✅ Auto-loaded saved theme from disk!")
        except Exception as e:
            print("Auto load note:", e)

    def _normalize_portable_theme_paths(self, theme_dict):
        """🔒 SECURITY & PORTABILITY: Resolves relative/portable bg_path across different PCs while blocking UNC/device/traversal paths."""
        if not isinstance(theme_dict, dict):
            return

        # Clamp resolution & elements bounds on disk-loaded themes
        try:
            theme_dict['width'] = max(64, min(4096, int(theme_dict.get('width', 320) or 320)))
        except (ValueError, TypeError):
            theme_dict['width'] = 320
        try:
            theme_dict['height'] = max(64, min(4096, int(theme_dict.get('height', 1480) or 1480)))
        except (ValueError, TypeError):
            theme_dict['height'] = 1480

        raw_elements = theme_dict.get('elements')
        if isinstance(raw_elements, list):
            clean_elements = []
            for el in raw_elements[:256]:
                if not isinstance(el, dict):
                    continue
                img_p = el.get('imagePath')
                if img_p:
                    if not isinstance(img_p, str) or not _is_safe_local_file_path(img_p) or os.path.splitext(img_p)[1].lower() not in self._ALLOWED_IMG_EXTS:
                        el['imagePath'] = ''
                clean_elements.append(el)
            theme_dict['elements'] = clean_elements
        else:
            theme_dict['elements'] = []

        bg = str(theme_dict.get('bg_path') or '').strip()
        t_name = _sanitize_theme_filename(str(theme_dict.get('name', '')).strip())
        app_dir = APP_USER_DATA_DIR
        cptheme_cand = os.path.join(app_dir, 'themes', f"{t_name}.cptheme") if t_name else ''

        if bg and not _is_safe_local_file_path(bg):
            theme_dict['bg_path'] = None
            bg = ''

        resolved_bg = None
        if bg:
            ext = os.path.splitext(bg)[1].lower()
            if ext not in self._ALLOWED_BG_EXTS:
                bg = ''
            elif os.path.isabs(bg) and os.path.isfile(bg):
                resolved_bg = bg
            else:
                bg_base = os.path.basename(bg)
                bg_ext = os.path.splitext(bg_base)[1].lower()
                if bg_base and bg_ext in self._ALLOWED_BG_EXTS:
                    cands = [
                        os.path.join(app_dir, bg_base),
                        os.path.join(app_dir, 'themes', bg_base),
                    ]
                    if t_name:
                        cands.append(os.path.join(app_dir, 'themes', t_name, bg_base))
                    for cand in cands:
                        try:
                            abs_cand = os.path.abspath(cand)
                            if os.path.commonpath([app_dir, abs_cand]) == app_dir and os.path.isfile(abs_cand):
                                resolved_bg = abs_cand
                                break
                        except Exception:
                            pass
                if not resolved_bg and cptheme_cand and os.path.isfile(cptheme_cand):
                    resolved_bg = cptheme_cand

        if not resolved_bg and not bg and cptheme_cand and os.path.isfile(cptheme_cand):
            footer = read_cptheme_footer(cptheme_cand)
            if footer and footer[0] in ('VID0', 'IMG0'):
                resolved_bg = cptheme_cand

        theme_dict['bg_path'] = resolved_bg

    def save_theme_to_disk(self):
        try:
            with self.hardware.render_lock:
                temp_path = LAST_THEME_FILE + ".tmp"
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(self.theme_data, f, ensure_ascii=False, indent=2)
                if os.path.exists(temp_path):
                    os.replace(temp_path, LAST_THEME_FILE)
            self.save_screen_workspaces_to_disk()
        except Exception as e:
            print("Save theme note:", e)

    def _create_workspace_runtime_objects(self, ws, is_primary_usb=False):
        """Creates dedicated HardwareDriver renderer and HDMICompanionDisplayWindow for a screen workspace."""
        t_data = ws.get('theme_data')
        if not isinstance(t_data, dict):
            t_data = copy.deepcopy(self.theme_data)
            ws['theme_data'] = t_data
        self._normalize_portable_theme_paths(t_data)
        tw = max(64, min(4096, int(t_data.get('width', 320))))
        th = max(64, min(4096, int(t_data.get('height', 1480))))
        if is_primary_usb:
            hw = self.primary_usb_hardware
            hw.set_resolution(tw, th)
        else:
            hw = ws.get('hardware')
            if hw is None or hw is self.primary_usb_hardware:
                hw = HardwareDriver(width=tw, height=th)
            else:
                hw.set_resolution(tw, th)
        ws['hardware'] = hw
        ws.setdefault('undo_stack', [])
        ws.setdefault('redo_stack', [])
        ws.setdefault('auto_rotate_enabled', False)
        ws.setdefault('rotate_interval_val', max(1, min(9999, int(self.app_settings.get('rotate_val', 30) or 30))))
        ws.setdefault('rotate_interval_unit', str(self.app_settings.get('rotate_unit', 'sec') or 'sec'))
        ws.setdefault('rotate_mode', str(self.app_settings.get('rotate_mode', 'sequential') or 'sequential'))
        if not isinstance(ws.get('rotate_themes'), list):
            ws['rotate_themes'] = [t['name'] for t in get_all_preset_themes()]
        ws.setdefault('_last_rotate_time', time.time())
        ws.setdefault('_rotate_idx', 0)

        if ws.get('screen_type') == 'hdmi_monitor':
            if ws.get('hdmi_window') is None:
                win = HDMICompanionDisplayWindow(self, slot_config=ws)
                slot_id_val = ws.get('slot_id', '')
                win.closed_signal.connect(lambda sid=slot_id_val: self.on_hdmi_companion_closed(sid))
                ws['hdmi_window'] = win
        return ws

    def init_screen_workspaces(self):
        """
        🖥️ Loads per-screen theme workspaces from disk and automatically synchronizes with all
        detected screens on the current PC (works portably across any PC!).
        """
        loaded_slots = []
        saved_active = 'usb_lcd_1'
        try:
            if os.path.isfile(SCREEN_WORKSPACES_FILE) and os.path.getsize(SCREEN_WORKSPACES_FILE) <= 16 * 1024 * 1024:
                with open(SCREEN_WORKSPACES_FILE, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    saved_active = str(raw.get('active_slot_id') or 'usb_lcd_1').strip()
                    w_list = raw.get('workspaces', [])
                    if isinstance(w_list, list):
                        for item in w_list[:self.MAX_SCREEN_WORKSPACES]:
                            if isinstance(item, dict) and item.get('slot_id') and isinstance(item.get('theme_data'), dict):
                                sid = re.sub(r'[^a-zA-Z0-9_\-]', '', str(item['slot_id']))[:40]
                                if not sid:
                                    continue
                                s_type = item.get('screen_type', 'usb_serial')
                                if s_type not in ('usb_serial', 'hdmi_monitor'):
                                    s_type = 'usb_serial'
                                try:
                                    mon_idx = max(0, min(16, int(item.get('monitor_index', 1) if item.get('monitor_index') is not None else 1)))
                                except (ValueError, TypeError):
                                    mon_idx = 1
                                try:
                                    h_rot = int(item.get('hdmi_rotation', 0) if item.get('hdmi_rotation') is not None else 0) % 360
                                except (ValueError, TypeError):
                                    h_rot = 0
                                if h_rot not in (0, 90, 180, 270):
                                    h_rot = 0
                                v_mode = str(item.get('hdmi_view_mode') or 'ambient_dashboard').strip()
                                if v_mode not in self._VALID_HDMI_VIEW_MODES:
                                    v_mode = 'ambient_dashboard'
                                raw_rot_themes = item.get('rotate_themes')
                                clean_rot_themes = (
                                    [str(x).strip()[:80] for x in raw_rot_themes[:200] if str(x).strip()]
                                    if isinstance(raw_rot_themes, list) else None
                                )
                                try:
                                    r_val = max(1, min(9999, int(item.get('rotate_interval_val', 30) or 30)))
                                except (ValueError, TypeError):
                                    r_val = 30
                                r_unit = str(item.get('rotate_interval_unit') or 'sec').strip()
                                if r_unit not in ('sec', 'min', 'hour'):
                                    r_unit = 'sec'
                                r_mode = str(item.get('rotate_mode') or 'sequential').strip()
                                if r_mode not in ('sequential', 'random'):
                                    r_mode = 'sequential'
                                ws_entry = {
                                    'slot_id': sid,
                                    'title': str(item.get('title') or sid)[:80],
                                    'screen_type': s_type,
                                    'com_port': str(item.get('com_port') or 'auto')[:20],
                                    'monitor_index': mon_idx,
                                    'hdmi_view_mode': v_mode,
                                    'hdmi_rotation': h_rot,
                                    'stream_enabled': bool(item.get('stream_enabled', True)),
                                    'is_custom_slot': bool(item.get('is_custom_slot', False)),
                                    'user_locked_resolution': bool(item.get('user_locked_resolution', False)),
                                    'auto_rotate_enabled': bool(item.get('auto_rotate_enabled', False)),
                                    'rotate_interval_val': r_val,
                                    'rotate_interval_unit': r_unit,
                                    'rotate_mode': r_mode,
                                    'rotate_themes': clean_rot_themes,
                                    'native_width': max(64, min(4096, int(item.get('native_width') or item['theme_data'].get('width', 320)))),
                                    'native_height': max(64, min(4096, int(item.get('native_height') or item['theme_data'].get('height', 1480)))),
                                    'theme_data': item['theme_data']
                                }
                                loaded_slots.append(ws_entry)
        except Exception as e:
            print("Load screen workspaces note:", e)

        self.screen_workspaces = {}
        for idx, ws in enumerate(loaded_slots):
            sid = ws['slot_id']
            self._create_workspace_runtime_objects(ws, is_primary_usb=(sid == 'usb_lcd_1' or idx == 0 and ws['screen_type'] == 'usb_serial'))
            self.screen_workspaces[sid] = ws

        # Synchronize with actual hardware screens detected on this PC (or any new PC)
        self.sync_screen_workspaces_with_hardware(initial_boot=True)

        if saved_active in self.screen_workspaces:
            self.active_screen_slot_id = saved_active
        elif self.screen_workspaces:
            self.active_screen_slot_id = next(iter(self.screen_workspaces.keys()))

        active_ws = self.screen_workspaces.get(self.active_screen_slot_id)
        if active_ws:
            self.theme_data = active_ws['theme_data']
            self.hardware = active_ws['hardware']
            self.undo_stack = active_ws['undo_stack']
            self.redo_stack = active_ws['redo_stack']

        # Link primary hdmi_companion_window attribute to the first HDMI workspace window
        first_hdmi_ws = next((w for w in self.screen_workspaces.values() if w.get('screen_type') == 'hdmi_monitor'), None)
        if first_hdmi_ws and first_hdmi_ws.get('hdmi_window'):
            self.hdmi_companion_window = first_hdmi_ws['hdmi_window']
        else:
            self.hdmi_companion_window = HDMICompanionDisplayWindow(self)
            self.hdmi_companion_window.closed_signal.connect(self.on_hdmi_companion_closed)

        self.save_screen_workspaces_to_disk()

    def sync_screen_workspaces_with_hardware(self, initial_boot=False, detected=None):
        """
        🔍 Automatically discovers all USB LCD COM ports and HDMI/DisplayPort monitors on the current PC
        and ensures every screen has its own independent Theme Creator Workspace!
        Works automatically when moved to any other computer.
        """
        try:
            if not isinstance(detected, dict):
                detected = detect_all_available_screens(self.primary_usb_hardware)
            com_ports = detected.get('com_ports', [])
            lcd_ports = [c for c in com_ports if c.get('is_lcd')]
            monitors = detected.get('monitors', [])

            # 1. Primary USB Case Screen Workspace (usb_lcd_1)
            if 'usb_lcd_1' not in self.screen_workspaces:
                port_lbl = lcd_ports[0]['port'] if lcd_ports else self.app_settings.get('selected_com_port', 'auto')
                ws_usb1 = {
                    'slot_id': 'usb_lcd_1',
                    'title': f"📟 1. Ekran: USB Kasa Ekranı ({port_lbl if port_lbl != 'auto' else '320×1480'})",
                    'screen_type': 'usb_serial',
                    'com_port': lcd_ports[0]['port'] if lcd_ports else 'auto',
                    'monitor_index': 0,
                    'hdmi_view_mode': 'ambient_dashboard',
                    'hdmi_rotation': 0,
                    'stream_enabled': True,
                    'is_custom_slot': False,
                    'theme_data': copy.deepcopy(self.theme_data)
                }
                self._create_workspace_runtime_objects(ws_usb1, is_primary_usb=True)
                self.screen_workspaces['usb_lcd_1'] = ws_usb1
            else:
                ws_usb1 = self.screen_workspaces['usb_lcd_1']
                if lcd_ports:
                    det_p = lcd_ports[0]['port']
                    ws_usb1['title'] = f"📟 1. Ekran: USB Kasa Ekranı ({det_p} • {ws_usb1['theme_data'].get('width', 320)}×{ws_usb1['theme_data'].get('height', 1480)})"

            # 2. Additional physical USB LCD screens if multiple USB LCDs are connected on this PC
            for extra_i, c_info in enumerate(lcd_ports[1:], start=2):
                sid = f"usb_lcd_{extra_i}"
                p_name = c_info.get('port', 'auto')
                if sid not in self.screen_workspaces:
                    ws_extra_usb = {
                        'slot_id': sid,
                        'title': f"📟 {extra_i}. USB Kasa Ekranı ({p_name})",
                        'screen_type': 'usb_serial',
                        'com_port': p_name,
                        'monitor_index': 0,
                        'hdmi_view_mode': 'ambient_dashboard',
                        'hdmi_rotation': 0,
                        'stream_enabled': True,
                        'is_custom_slot': False,
                        'theme_data': copy.deepcopy(self.theme_data)
                    }
                    self._create_workspace_runtime_objects(ws_extra_usb, is_primary_usb=False)
                    self.screen_workspaces[sid] = ws_extra_usb

            # 3. HDMI / DisplayPort Monitors on the current PC
            # Create a dedicated workspace for every secondary monitor (index >= 1), or a default hdmi_mon_1 workspace
            def _optimal_hdmi_res(mon_w, mon_h, is_case=False):
                if not is_case and (mon_w, mon_h) == (800, 600):
                    return 1920, 1080
                if mon_w > mon_h and mon_w >= 1920 and mon_h >= 1080 and abs((float(mon_w) / max(1, mon_h)) - (16.0 / 9.0)) < 0.15 and not is_case:
                    return 1920, 1080
                return max(64, min(4096, int(mon_w))), max(64, min(4096, int(mon_h)))

            secondary_monitors = [m for m in monitors if int(m.get('index', 0)) >= 1]
            if secondary_monitors:
                for m in secondary_monitors:
                    m_idx = int(m.get('index', 1))
                    sid = f"hdmi_mon_{m_idx}"
                    m_name = str(m.get('name', f'Monitör {m_idx + 1}')).strip()
                    mw = int(m.get('width', 1920))
                    mh = int(m.get('height', 1080))
                    target_tw, target_th = _optimal_hdmi_res(mw, mh, is_case=bool(m.get('is_case_screen')))
                    if sid not in self.screen_workspaces:
                        # Pick a different preset theme by default if available so the user immediately sees independent themes
                        default_hdmi_theme = copy.deepcopy(self.theme_data)
                        presets = get_all_preset_themes()
                        curr_name_lower = str(self.theme_data.get('name', '')).strip().lower()
                        alt_preset = next((p for p in presets if p['name'].strip().lower() != curr_name_lower), None)
                        if alt_preset:
                            loaded_alt = load_preset_theme_data(alt_preset)
                            if isinstance(loaded_alt, dict):
                                default_hdmi_theme = loaded_alt
                        # Automatically adapt theme to this screen's own resolution (e.g. 1920x1080 Full HD or case panel resolution)
                        if default_hdmi_theme.get('width') != target_tw or default_hdmi_theme.get('height') != target_th:
                            adapt_theme_elements_to_resolution(default_hdmi_theme, target_tw, target_th)

                        ws_hdmi = {
                            'slot_id': sid,
                            'title': f"🖥️ Ekran {m_idx + 1}: {m_name} ({target_tw}×{target_th})",
                            'screen_type': 'hdmi_monitor',
                            'com_port': 'auto',
                            'monitor_index': m_idx,
                            'hdmi_view_mode': self.app_settings.get('hdmi_view_mode', 'ambient_dashboard'),
                            'hdmi_rotation': int(self.app_settings.get('hdmi_rotation', 0)),
                            'stream_enabled': (self.app_settings.get('output_mode', 'usb_serial') in ('hdmi_monitor', 'both') or bool(m.get('is_case_screen'))),
                            'is_custom_slot': False,
                            'user_locked_resolution': False,
                            'native_width': mw,
                            'native_height': mh,
                            'theme_data': default_hdmi_theme
                        }
                        self._create_workspace_runtime_objects(ws_hdmi, is_primary_usb=False)
                        self.screen_workspaces[sid] = ws_hdmi
                    else:
                        ws_hdmi = self.screen_workspaces[sid]
                        ws_hdmi['monitor_index'] = m_idx
                        ws_hdmi['native_width'] = mw
                        ws_hdmi['native_height'] = mh
                        # If existing workspace still had legacy 320x1480 on a widescreen monitor, upgrade to native resolution automatically
                        curr_tw = int(ws_hdmi['theme_data'].get('width', 320))
                        curr_th = int(ws_hdmi['theme_data'].get('height', 1480))
                        if (curr_tw, curr_th) in ((320, 1480), (800, 600)) and (target_tw, target_th) != (curr_tw, curr_th) and not ws_hdmi.get('user_locked_resolution', False):
                            adapt_theme_elements_to_resolution(ws_hdmi['theme_data'], target_tw, target_th)
                            if ws_hdmi.get('hardware'):
                                ws_hdmi['hardware'].set_resolution(target_tw, target_th)
                            curr_tw, curr_th = target_tw, target_th
                        ws_hdmi['title'] = f"🖥️ Ekran {m_idx + 1}: {m_name} ({curr_tw}×{curr_th})"
            else:
                # Even if the PC currently has 1 main monitor + USB LCD, ensure hdmi_mon_1 workspace exists at native 1080p
                prim_w = int(monitors[0].get('width', 1920)) if monitors else 1920
                prim_h = int(monitors[0].get('height', 1080)) if monitors else 1080
                target_tw, target_th = _optimal_hdmi_res(prim_w, prim_h, is_case=False)
                if not any(w.get('screen_type') == 'hdmi_monitor' for w in self.screen_workspaces.values()):
                    default_hdmi_theme = copy.deepcopy(self.theme_data)
                    presets = get_all_preset_themes()
                    curr_name_lower = str(self.theme_data.get('name', '')).strip().lower()
                    alt_preset = next((p for p in presets if p['name'].strip().lower() != curr_name_lower), None)
                    if alt_preset:
                        loaded_alt = load_preset_theme_data(alt_preset)
                        if isinstance(loaded_alt, dict):
                            default_hdmi_theme = loaded_alt
                    if default_hdmi_theme.get('width') != target_tw or default_hdmi_theme.get('height') != target_th:
                        adapt_theme_elements_to_resolution(default_hdmi_theme, target_tw, target_th)

                    ws_hdmi1 = {
                        'slot_id': 'hdmi_mon_1',
                        'title': f"🖥️ 2. Ekran: HDMI / Monitör ({target_tw}×{target_th})",
                        'screen_type': 'hdmi_monitor',
                        'com_port': 'auto',
                        'monitor_index': max(0, len(monitors) - 1),
                        'hdmi_view_mode': self.app_settings.get('hdmi_view_mode', 'ambient_dashboard'),
                        'hdmi_rotation': int(self.app_settings.get('hdmi_rotation', 0)),
                        'stream_enabled': (self.app_settings.get('output_mode', 'usb_serial') in ('hdmi_monitor', 'both')),
                        'is_custom_slot': False,
                        'user_locked_resolution': False,
                        'native_width': prim_w,
                        'native_height': prim_h,
                        'theme_data': default_hdmi_theme
                    }
                    self._create_workspace_runtime_objects(ws_hdmi1, is_primary_usb=False)
                    self.screen_workspaces['hdmi_mon_1'] = ws_hdmi1
                else:
                    for ws_hdmi in self.screen_workspaces.values():
                        if ws_hdmi.get('screen_type') == 'hdmi_monitor':
                            curr_tw = int(ws_hdmi['theme_data'].get('width', 320))
                            curr_th = int(ws_hdmi['theme_data'].get('height', 1480))
                            if (curr_tw, curr_th) in ((320, 1480), (800, 600)) and (target_tw, target_th) != (curr_tw, curr_th) and not ws_hdmi.get('user_locked_resolution', False):
                                adapt_theme_elements_to_resolution(ws_hdmi['theme_data'], target_tw, target_th)
                                if ws_hdmi.get('hardware'):
                                    ws_hdmi['hardware'].set_resolution(target_tw, target_th)
                                ws_hdmi['title'] = f"🖥️ 2. Ekran: HDMI / Monitör ({target_tw}×{target_th})"
        except Exception as e:
            print("sync_screen_workspaces_with_hardware note:", e)

    def on_system_screens_changed(self, _screen=None):
        """Triggered live when a monitor/HDMI screen is connected or disconnected on any PC."""
        try:
            self.sync_screen_workspaces_with_hardware(initial_boot=False)
            self.refresh_multi_screen_bar_ui()
            self.save_screen_workspaces_to_disk()
        except Exception as e:
            print("on_system_screens_changed note:", e)

    def save_screen_workspaces_to_disk(self):
        """Atomically saves all per-screen independent themes and settings to screen_workspaces.json."""
        try:
            if not hasattr(self, 'screen_workspaces') or not self.screen_workspaces:
                return
            serializable_list = []
            for sid, ws in list(self.screen_workspaces.items()):
                t_clean = dict(ws.get('theme_data', {}))
                t_clean.pop('_cptheme_path', None)
                t_clean.pop('_cptheme_media_type', None)
                serializable_list.append({
                    'slot_id': sid,
                    'title': ws.get('title', sid),
                    'screen_type': ws.get('screen_type', 'usb_serial'),
                    'com_port': ws.get('com_port', 'auto'),
                    'monitor_index': int(ws.get('monitor_index', 1)),
                    'hdmi_view_mode': ws.get('hdmi_view_mode', 'ambient_dashboard'),
                    'hdmi_rotation': int(ws.get('hdmi_rotation', 0)),
                    'stream_enabled': bool(ws.get('stream_enabled', True)),
                    'is_custom_slot': bool(ws.get('is_custom_slot', False)),
                    'user_locked_resolution': bool(ws.get('user_locked_resolution', False)),
                    'auto_rotate_enabled': bool(ws.get('auto_rotate_enabled', False)),
                    'rotate_interval_val': int(ws.get('rotate_interval_val', 30)),
                    'rotate_interval_unit': str(ws.get('rotate_interval_unit', 'sec')),
                    'rotate_mode': str(ws.get('rotate_mode', 'sequential')),
                    'rotate_themes': list(ws.get('rotate_themes') or []),
                    'native_width': int(ws.get('native_width', t_clean.get('width', 320))),
                    'native_height': int(ws.get('native_height', t_clean.get('height', 1480))),
                    'theme_data': t_clean
                })
            payload = {
                'active_slot_id': getattr(self, 'active_screen_slot_id', 'usb_lcd_1'),
                'workspaces': serializable_list
            }
            tmp_p = SCREEN_WORKSPACES_FILE + ".tmp"
            with open(tmp_p, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_p, SCREEN_WORKSPACES_FILE)
        except Exception as e:
            print("save_screen_workspaces_to_disk note:", e)

    def get_active_screen_title(self):
        ws = getattr(self, 'screen_workspaces', {}).get(getattr(self, 'active_screen_slot_id', ''))
        if ws:
            return ws.get('title', 'Aktif Ekran')
        return "Aktif Ekran"

    def get_preset_theme_names(self):
        return [t['name'] for t in get_all_preset_themes()]

    def get_active_streaming_workspaces(self):
        """Returns a thread-safe snapshot list of screen workspaces that should be rendered and streamed right now."""
        if not hasattr(self, 'screen_workspaces') or not self.screen_workspaces:
            return []
        ws_snapshot = list(self.screen_workspaces.values())
        output_mode = self.app_settings.get('output_mode', 'usb_serial')
        active_list = []
        for ws in ws_snapshot:
            if not ws.get('stream_enabled', True):
                continue
            active_list.append(ws)
        # Fallback if nothing is enabled: filter by output_mode or active workspace
        if not active_list:
            for ws in ws_snapshot:
                s_type = ws.get('screen_type', 'usb_serial')
                if output_mode == 'usb_serial' and s_type == 'usb_serial':
                    active_list.append(ws)
                elif output_mode == 'hdmi_monitor' and s_type == 'hdmi_monitor':
                    active_list.append(ws)
                elif output_mode == 'both':
                    active_list.append(ws)
        if not active_list:
            curr_ws = self.screen_workspaces.get(self.active_screen_slot_id)
            if curr_ws:
                active_list.append(curr_ws)
        return active_list

    def _sync_output_mode_from_workspaces(self):
        """Synchronizes app_settings['output_mode'] based on which screen workspaces have stream_enabled=True."""
        ws_snapshot = list(self.screen_workspaces.values())
        has_usb = any(ws.get('stream_enabled', True) and ws.get('screen_type') == 'usb_serial' for ws in ws_snapshot)
        has_hdmi = any(ws.get('stream_enabled', True) and ws.get('screen_type') == 'hdmi_monitor' for ws in ws_snapshot)
        if has_usb and has_hdmi:
            self.app_settings['output_mode'] = 'both'
        elif has_hdmi:
            self.app_settings['output_mode'] = 'hdmi_monitor'
        elif has_usb:
            self.app_settings['output_mode'] = 'usb_serial'
        self.save_app_settings()
        self.update_stream_status_ui()

    def switch_active_screen_workspace(self, slot_id):
        """
        🎯 Switches the entire Theme Creator Studio (Canvas, Element List, Properties, Media, Undo/Redo)
        to the specified screen workspace so each screen has its own independent theme creator!
        """
        if not slot_id or slot_id not in self.screen_workspaces:
            return
        try:
            self.deselect_element()
            self.active_screen_slot_id = slot_id
            ws = self.screen_workspaces[slot_id]
            self.theme_data = ws['theme_data']
            self.hardware = ws['hardware']
            self.undo_stack = ws.setdefault('undo_stack', [])
            self.redo_stack = ws.setdefault('redo_stack', [])

            if ws.get('screen_type') == 'hdmi_monitor' and ws.get('hdmi_window'):
                self.hdmi_companion_window = ws['hdmi_window']

            tw = int(self.theme_data.get('width', 320))
            th = int(self.theme_data.get('height', 1480))
            self.hardware.set_resolution(tw, th)

            # Sync left panel controls (Refresh speed, Rotation, Background info) without firing change signals
            if hasattr(self, 'spin_refresh'):
                self.spin_refresh.blockSignals(True)
                self.spin_refresh.setValue(max(1, min(10, int(self.theme_data.get('refresh_sec', 1)))))
                self.spin_refresh.blockSignals(False)

            if hasattr(self, 'combo_rot'):
                rot_val = int(self.theme_data.get('rotation', 180))
                rot_idx_map = {180: 0, 0: 1, 90: 2, 270: 3}
                self.combo_rot.blockSignals(True)
                self.combo_rot.setCurrentIndex(rot_idx_map.get(rot_val, 0))
                self.combo_rot.blockSignals(False)

            if hasattr(self, 'lbl_bg_info'):
                bg_p = self.theme_data.get('bg_path')
                if bg_p:
                    self.lbl_bg_info.setText(f"🎞 {os.path.basename(bg_p)[:26]}")
                else:
                    self.lbl_bg_info.setText("🎞 Varsayılan Koyu Arka Plan")
            if hasattr(self, 'lbl_bg_res_tag'):
                self.lbl_bg_res_tag.setText(f"{tw}×{th}")

            if hasattr(self, 'lbl_center_ws_title'):
                t_name = self.theme_data.get('name', 'Özel Tema')
                self.lbl_center_ws_title.setText(f"🎨 {t_name}")
            elif hasattr(self, 'center_box') and hasattr(self.center_box, 'setTitle'):
                t_name = self.theme_data.get('name', 'Özel Tema')
                self.center_box.setTitle(f"📺 [{ws.get('title', slot_id)}] — {tw}×{th} Canlı Tuval (Tema: {t_name})")

            if hasattr(self, 'update_undo_redo_ui'):
                self.update_undo_redo_ui()
            self.auto_adjust_window_to_canvas(tw, th)
            self.update_canvas_geometry()
            self.refresh_elements_list()
            if self.theme_data.get('elements'):
                self.select_element_by_index(0)
            self.refresh_multi_screen_bar_ui()
            self.save_screen_workspaces_to_disk()
        except Exception as e:
            print("switch_active_screen_workspace note:", e)

    def apply_preset_theme_to_slot(self, slot_id, theme_name, preserve_editor_if_inactive=True):
        """Loads a saved .cptheme preset directly into a specific screen slot's theme creator."""
        if not theme_name:
            return False
        target_sid = slot_id if (slot_id and slot_id in self.screen_workspaces) else self.active_screen_slot_id
        ws = self.screen_workspaces.get(target_sid)
        if not ws:
            return False
        try:
            themes = get_all_preset_themes()
            matched = next((t for t in themes if t['name'].strip().lower() == str(theme_name).strip().lower()), None)
            if not matched:
                return False
            t_json = load_preset_theme_data(matched)
            if not t_json or not isinstance(t_json, dict):
                return False

            prev_w = int(ws['theme_data'].get('width', 320))
            prev_h = int(ws['theme_data'].get('height', 1480))
            new_w = int(t_json.get('width', 320))
            new_h = int(t_json.get('height', 1480))

            # During background auto-rotation, keep the screen's locked resolution;
            # when explicitly selected by the user, switch to the theme's native canvas resolution!
            if preserve_editor_if_inactive and (prev_w, prev_h) != (new_w, new_h):
                adapt_theme_elements_to_resolution(t_json, prev_w, prev_h)
            elif not preserve_editor_if_inactive:
                ws['user_locked_resolution'] = True

            hw = ws.get('hardware')
            if hw:
                hw.reset_background_media()
                with hw.render_lock:
                    ws['theme_data'].clear()
                    ws['theme_data'].update(t_json)
                hw.set_resolution(int(ws['theme_data'].get('width', 320)), int(ws['theme_data'].get('height', 1480)))
            else:
                ws['theme_data'].clear()
                ws['theme_data'].update(t_json)

            if target_sid == self.active_screen_slot_id:
                self.switch_active_screen_workspace(target_sid)
            else:
                self.refresh_multi_screen_bar_ui()
                self.save_screen_workspaces_to_disk()
            return True
        except Exception as e:
            print("apply_preset_theme_to_slot note:", e)
            return False

    def open_screen_auto_rotate_dialog(self, slot_id=None, parent_widget=None):
        """Opens the Per-Screen Selective Auto Theme Rotation dialog."""
        try:
            target_sid = slot_id if (slot_id and slot_id in self.screen_workspaces) else self.active_screen_slot_id
            dlg = ScreenAutoRotateDialog(self, initial_slot_id=target_sid, parent_widget=parent_widget or self)
            dlg.exec_()
            self.refresh_multi_screen_bar_ui()
        except Exception as e:
            QMessageBox.warning(self, "Döngü Seçici Hatası", f"Ekran bazlı tema döngüsü penceresi açılamadı:\n{e}")

    def rotate_screen_workspace_theme(self, slot_id, delta=1):
        """
        🎠 Advances the specified screen workspace to its next (or random) theme from its own
        selected `rotate_themes` playlist, keeping that screen's native resolution intact.
        """
        ws = self.screen_workspaces.get(slot_id)
        if not ws:
            return False
        try:
            all_presets = get_all_preset_themes()
            if not all_presets:
                return False
            preset_lookup = {p['name'].strip().lower(): p['name'] for p in all_presets}

            raw_selected = ws.get('rotate_themes')
            selected_names = []
            if isinstance(raw_selected, list) and raw_selected:
                for name_item in raw_selected:
                    k = str(name_item).strip().lower()
                    if k in preset_lookup and preset_lookup[k] not in selected_names:
                        selected_names.append(preset_lookup[k])
            if not selected_names:
                selected_names = [p['name'] for p in all_presets]

            if not selected_names:
                return False

            curr_name = str(ws.get('theme_data', {}).get('name', '')).strip().lower()
            mode = str(ws.get('rotate_mode', 'sequential')).strip()

            if mode == 'random' and len(selected_names) > 1:
                candidates = [n for n in selected_names if n.strip().lower() != curr_name]
                target_name = random.choice(candidates if candidates else selected_names)
            else:
                curr_idx = -1
                for i, n in enumerate(selected_names):
                    if n.strip().lower() == curr_name:
                        curr_idx = i
                        break
                if curr_idx < 0:
                    curr_idx = int(ws.get('_rotate_idx', -1))
                next_idx = (curr_idx + delta) % len(selected_names)
                ws['_rotate_idx'] = next_idx
                target_name = selected_names[next_idx]

            ws['_last_rotate_time'] = time.time()
            return self.apply_preset_theme_to_slot(slot_id, target_name, preserve_editor_if_inactive=True)
        except Exception as e:
            print("rotate_screen_workspace_theme note:", e)
            return False

    def clone_theme_from_another_screen(self):
        """Copies another screen's theme into the currently active screen workspace (scaling if needed)."""
        try:
            other_slots = [(sid, ws) for sid, ws in list(self.screen_workspaces.items()) if sid != self.active_screen_slot_id]
            if not other_slots:
                QMessageBox.information(self, "Bilgi", "Kopyalanacak başka bir ekran yuvası bulunamadı.")
                return
            items = [f"{ws['title']} (Tema: {ws['theme_data'].get('name', 'Özel')})" for _, ws in other_slots]
            choice, ok = QInputDialog.getItem(
                self,
                "📋 Diğer Ekrandan Temayı Kopyala",
                f"'{self.get_active_screen_title()}' ekranına hangi ekranın temasını kopyalamak istersiniz?",
                items,
                0,
                False
            )
            if not ok or not choice:
                return
            sel_idx = items.index(choice)
            _, src_ws = other_slots[sel_idx]
            cloned_theme = copy.deepcopy(src_ws['theme_data'])

            curr_w = int(self.theme_data.get('width', 320))
            curr_h = int(self.theme_data.get('height', 1480))
            src_w = int(cloned_theme.get('width', 320))
            src_h = int(cloned_theme.get('height', 1480))
            if (curr_w, curr_h) != (src_w, src_h):
                ans = QMessageBox.question(
                    self,
                    "Çözünürlük Uyarlama",
                    f"Kaynak ekran çözünürlüğü ({src_w}×{src_h}) ile bu ekranın çözünürlüğü ({curr_w}×{curr_h}) farklı.\n\n"
                    f"Ögeler bu ekranın ({curr_w}×{curr_h}) boyutuna otomatik ölçeklensin mi?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if ans == QMessageBox.Yes:
                    adapt_theme_elements_to_resolution(cloned_theme, curr_w, curr_h)

            self.push_undo_state("Diğer Ekrandan Tema Kopyala")
            self.hardware.reset_background_media()
            with self.hardware.render_lock:
                self.theme_data.clear()
                self.theme_data.update(cloned_theme)
            self.hardware.set_resolution(int(self.theme_data.get('width', 320)), int(self.theme_data.get('height', 1480)))
            self.switch_active_screen_workspace(self.active_screen_slot_id)
            self.save_theme_to_disk()
        except Exception as e:
            QMessageBox.warning(self, "Kopyalama Hatası", f"Tema kopyalanırken hata oluştu: {e}")

    def add_custom_screen_workspace_dialog(self):
        """Allows adding a new independent Screen Theme Creator workspace for any monitor, USB LCD, or Catalog Model."""
        try:
            if len(self.screen_workspaces) >= self.MAX_SCREEN_WORKSPACES:
                QMessageBox.warning(
                    self,
                    "Maksimum Ekran Sınırı",
                    f"Sistem performansı ve bellek güvenliği için en fazla {self.MAX_SCREEN_WORKSPACES} adet bağımsız ekran tema çalışma alanı eklenebilir."
                )
                return
            options = [
                "🖥️ Yeni HDMI Monitör / İkincil Ekran Yuvası (1920×1080 / Geniş Ekran)",
                "📟 Yeni USB Kasa Ekranı Yuvası (320×1480 Dikey Bar)"
            ]
            for p in CASE_SCREEN_PRESETS:
                options.append(f"📐 {p['brand']} {p['model']} ({p['width']}×{p['height']} • {p['diagonal']})")

            choice, ok = QInputDialog.getItem(
                self,
                "➕ Yeni Ekran Tema Oluşturucu Ekle",
                "Ayrı özel tema tasarlamak istediğiniz ekran modelini veya bağlantı tipini seçin:",
                options,
                0,
                False
            )
            if not ok or not choice:
                return

            sel_i = options.index(choice)
            custom_idx = len(self.screen_workspaces) + 1
            while f"custom_screen_{custom_idx}" in self.screen_workspaces:
                custom_idx += 1
            sid = f"custom_screen_{custom_idx}"

            new_theme = copy.deepcopy(self.theme_data)
            if sel_i == 0:
                s_type = 'hdmi_monitor'
                tw, th = 1920, 1080
                title = f"🖥️ {custom_idx}. Ekran: Özel HDMI Monitör (1920×1080)"
            elif sel_i == 1:
                s_type = 'usb_serial'
                tw, th = 320, 1480
                title = f"📟 {custom_idx}. Ekran: Özel USB LCD (320×1480)"
            else:
                preset = CASE_SCREEN_PRESETS[sel_i - 2]
                s_type = 'hdmi_monitor' if preset.get('conn_type') == 'hdmi_monitor' else 'usb_serial'
                tw = int(preset.get('width', 320))
                th = int(preset.get('height', 1480))
                title = f"📐 {custom_idx}. {preset['brand']} {preset['model'][:22]} ({tw}×{th})"

            if (int(new_theme.get('width', 320)), int(new_theme.get('height', 1480))) != (tw, th):
                adapt_theme_elements_to_resolution(new_theme, tw, th)

            new_ws = {
                'slot_id': sid,
                'title': title,
                'screen_type': s_type,
                'com_port': 'auto',
                'monitor_index': 1,
                'hdmi_view_mode': 'ambient_dashboard',
                'hdmi_rotation': 0,
                'stream_enabled': True,
                'is_custom_slot': True,
                'user_locked_resolution': True,
                'native_width': tw,
                'native_height': th,
                'theme_data': new_theme
            }
            self._create_workspace_runtime_objects(new_ws, is_primary_usb=False)
            self.screen_workspaces[sid] = new_ws
            self.switch_active_screen_workspace(sid)
            self.save_screen_workspaces_to_disk()
        except Exception as e:
            QMessageBox.warning(self, "Ekran Ekleme Hatası", f"Yeni ekran yuvası eklenirken hata oluştu: {e}")

    def remove_active_custom_screen_workspace(self):
        """Removes a user-added custom screen workspace (keeps hardware-detected primary USB/HDMI workspaces)."""
        ws = self.screen_workspaces.get(self.active_screen_slot_id)
        if not ws:
            return
        if len(self.screen_workspaces) <= 1 or self.active_screen_slot_id in ('usb_lcd_1', 'hdmi_mon_1'):
            QMessageBox.information(
                self,
                "Ana Ekran Yuvası",
                "Birincil USB Kasa Ekranı ve Birincil HDMI Monitör yuvaları sistemin temel ekranlarıdır ve silinemez.\n"
                "Bu ekranların temasını dilediğiniz gibi değiştirebilir veya 'Yayına Dahil Et' kutusunu kapatabilirsiniz."
            )
            return
        ans = QMessageBox.question(
            self,
            "Ekran Yuvasını Kaldır",
            f"'{ws.get('title')}' ekran yuvasını ve özel tema çalışma alanını kaldırmak istediğinize emin misiniz?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ans != QMessageBox.Yes:
            return
        old_sid = self.active_screen_slot_id
        rem_ws = self.screen_workspaces.pop(old_sid, None)
        if rem_ws:
            if rem_ws.get('hdmi_window'):
                try:
                    rem_ws['hdmi_window'].close()
                except Exception:
                    pass
            if rem_ws.get('hardware') and rem_ws['hardware'] is not self.primary_usb_hardware:
                try:
                    rem_ws['hardware'].close()
                except Exception:
                    pass
        next_sid = next(iter(self.screen_workspaces.keys()), 'usb_lcd_1')
        self.switch_active_screen_workspace(next_sid)
        self.save_screen_workspaces_to_disk()

    def populate_com_ports(self):
        try:
            saved_port = self.app_settings.get('selected_com_port', 'auto')
            if not hasattr(self, 'combo_port'):
                return
            self.combo_port.blockSignals(True)
            self.combo_port.clear()
            self.combo_port.addItem("⚡ Otomatik Algıla", "auto")

            ports = HardwareDriver.list_available_com_ports()
            target_idx = 0
            for i, p in enumerate(ports, start=1):
                dev = p.get('device', '')
                desc = p.get('description', '')
                is_lcd = p.get('is_lcd', False)
                icon = "🖥️" if is_lcd else "🔌"
                label = f"{icon} {dev} ({desc})"
                self.combo_port.addItem(label, dev)
                if dev == saved_port:
                    target_idx = i

            if saved_port == 'auto':
                target_idx = 0

            self.combo_port.setCurrentIndex(target_idx)
            self.combo_port.blockSignals(False)
        except Exception as e:
            print("Populate COM ports error:", e)

    def on_output_target_changed(self, idx):
        if idx < 0 or not hasattr(self, 'combo_output_target'):
            return
        new_mode = self.combo_output_target.itemData(idx)
        self.app_settings['output_mode'] = new_mode
        self.save_app_settings()

        # Sync per-screen stream_enabled checkboxes with the selected output target mode
        for ws in getattr(self, 'screen_workspaces', {}).values():
            s_type = ws.get('screen_type', 'usb_serial')
            if new_mode == 'usb_serial':
                ws['stream_enabled'] = (s_type == 'usb_serial')
            elif new_mode == 'hdmi_monitor':
                ws['stream_enabled'] = (s_type == 'hdmi_monitor')
            else:
                ws['stream_enabled'] = True

        # When switching to USB LCD on a USB slot, ensure theme resolution is 320x1480 if active slot is usb_serial
        active_ws = getattr(self, 'screen_workspaces', {}).get(getattr(self, 'active_screen_slot_id', ''))
        if new_mode in ('usb_serial', 'both') and active_ws and active_ws.get('screen_type') == 'usb_serial':
            curr_w = int(self.theme_data.get('width', 320))
            curr_h = int(self.theme_data.get('height', 1480))
            if curr_w != 320 or curr_h != 1480:
                adapt_theme_elements_to_resolution(self.theme_data, 320, 1480)
                self.hardware.set_resolution(320, 1480)
                self.update_canvas_geometry()
                self.refresh_elements_list()
                self.save_theme_to_disk()

        if self.is_streaming:
            if new_mode in ['usb_serial', 'both']:
                target_port = self.app_settings.get('selected_com_port', 'auto')
                self.primary_usb_hardware.auto_connect(target_port=target_port)

            for ws in getattr(self, 'screen_workspaces', {}).values():
                if ws.get('screen_type') == 'hdmi_monitor' and ws.get('hdmi_window'):
                    if new_mode in ['hdmi_monitor', 'both'] and ws.get('stream_enabled', True):
                        ws['hdmi_window'].show_on_monitor(monitor_index=ws.get('monitor_index', 1))
                    else:
                        ws['hdmi_window'].hide()

        self.refresh_multi_screen_bar_ui()
        self.save_screen_workspaces_to_disk()
        self.update_stream_status_ui()

    def update_stream_status_ui(self):
        output_mode = self.app_settings.get('output_mode', 'usb_serial')
        mon_name = self.app_settings.get('selected_monitor_name', 'HDMI Monitör')
        com_p = getattr(self.hardware, 'com_port', None) or self.app_settings.get('selected_com_port', 'COM')

        if hasattr(self, 'combo_output_target'):
            target_idx = self.combo_output_target.findData(output_mode)
            if target_idx >= 0 and self.combo_output_target.currentIndex() != target_idx:
                self.combo_output_target.blockSignals(True)
                self.combo_output_target.setCurrentIndex(target_idx)
                self.combo_output_target.blockSignals(False)

        if not self.is_streaming:
            if output_mode == 'usb_serial':
                btn_txt = "🚀 CANLI YANSIT (USB)"
                bg_col = "#00885d"
            elif output_mode == 'hdmi_monitor':
                btn_txt = "🚀 CANLI YANSIT (HDMI)"
                bg_col = "#00885d"
            else:
                btn_txt = "🚀 CANLI YANSIT (ÇİFT EKRAN)"
                bg_col = "#00885d"

            if hasattr(self, 'btn_stream'):
                self.btn_stream.setText(btn_txt)
                self.btn_stream.setStyleSheet(
                    f"background: {bg_col}; color: #eafff6; font-size: 11px; font-weight: 900; padding: 6px 14px; border-radius: 7px; border: none;"
                )
            if hasattr(self, 'lbl_port_status'):
                self.lbl_port_status.setText("● HAZIR [BEKLEMEDE]")
                self.lbl_port_status.setStyleSheet(
                    "background: #060e20; color: #908fa0; border: 1px solid #222a3d; border-radius: 6px; padding: 4px 8px; font-weight: 800; font-size: 10px;"
                )
        else:
            if hasattr(self, 'btn_stream'):
                self.btn_stream.setText("⏹ YANSITMAYI DURDUR")
                self.btn_stream.setStyleSheet(
                    "background: #ef4444; color: #ffffff; font-size: 11px; font-weight: 900; padding: 6px 14px; border-radius: 7px; border: none;"
                )
            if hasattr(self, 'lbl_port_status'):
                if output_mode == 'usb_serial':
                    if self.hardware.is_connected:
                        self.lbl_port_status.setText(f"● BAĞLI [{self.hardware.com_port}]")
                        self.lbl_port_status.setStyleSheet(
                            "background: rgba(0, 136, 93, 0.16); color: #4edea3; border: 1px solid rgba(78, 222, 163, 0.35); border-radius: 6px; padding: 4px 8px; font-weight: 800; font-size: 10px;"
                        )
                    else:
                        self.lbl_port_status.setText(f"● BAĞLI DEĞİL [{com_p}]")
                        self.lbl_port_status.setStyleSheet(
                            "background: rgba(239, 68, 68, 0.16); color: #ffb4ab; border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 6px; padding: 4px 8px; font-weight: 800; font-size: 10px;"
                        )
                elif output_mode == 'hdmi_monitor':
                    self.lbl_port_status.setText(f"● AKTİF [{mon_name[:14]}]")
                    self.lbl_port_status.setStyleSheet(
                        "background: rgba(0, 166, 224, 0.16); color: #7bd0ff; border: 1px solid rgba(123, 208, 255, 0.35); border-radius: 6px; padding: 4px 8px; font-weight: 800; font-size: 10px;"
                    )
                else:
                    self.lbl_port_status.setText("● BAĞLI [60 FPS]")
                    self.lbl_port_status.setStyleSheet(
                        "background: rgba(0, 136, 93, 0.16); color: #4edea3; border: 1px solid rgba(78, 222, 163, 0.35); border-radius: 6px; padding: 4px 8px; font-weight: 800; font-size: 10px;"
                    )
        if hasattr(self, 'apply_current_language'):
            self.apply_current_language()

    def on_port_selection_changed(self, idx):
        if idx < 0 or not hasattr(self, 'combo_port'):
            return
        selected_data = self.combo_port.itemData(idx)
        self.app_settings['selected_com_port'] = selected_data
        
        # When selecting a COM port explicitly, ensure output_mode includes USB!
        current_mode = self.app_settings.get('output_mode', 'usb_serial')
        if current_mode == 'hdmi_monitor':
            self.app_settings['output_mode'] = 'usb_serial'
            if hasattr(self, 'combo_output_target'):
                t_idx = self.combo_output_target.findData('usb_serial')
                if t_idx >= 0:
                    self.combo_output_target.blockSignals(True)
                    self.combo_output_target.setCurrentIndex(t_idx)
                    self.combo_output_target.blockSignals(False)

        self.save_app_settings()
        self.update_stream_status_ui()

        # If currently streaming, reconnect to selected port
        if self.is_streaming:
            self.hardware.auto_connect(target_port=selected_data)

    def launch_separate_rgb_app(self):
        try:
            py_exe = get_python_exe()
            subprocess.Popen([py_exe, RGB_APP_SCRIPT])
            print("Launched Standalone RGB Studio App in separate process!")
        except Exception as e:
            QMessageBox.critical(self, "RGB Uygulaması Başlatılamadı", f"Ayrı RGB stüdyosu başlatılırken hata oluştu: {e}")

    def filter_sensor_library_list(self, text):
        q = str(text or '').strip().lower()
        if not hasattr(self, 'sensor_list'):
            return
        for i in range(self.sensor_list.count()):
            it = self.sensor_list.item(i)
            if it:
                data = it.data(Qt.UserRole) or {}
                search_haystack = f"{data.get('search_title', '')} {data.get('sensorId', '')} {it.text()}".lower()
                it.setHidden(bool(q and q not in search_haystack))

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        init_w = int(self.theme_data.get('width', 320))
        init_h = int(self.theme_data.get('height', 1480))

        # ═══════════════════════════════════════════════════════════════════════════
        # MAIN SHELL: Unified Left Navigation Sidebar (#131b2e) + Right Studio (#0b1326)
        # ═══════════════════════════════════════════════════════════════════════════
        shell_body = QHBoxLayout()
        shell_body.setContentsMargins(0, 0, 0, 0)
        shell_body.setSpacing(0)

        # Left Navigation Sidebar (ONLY Menu Location — Spans Full Height)
        nav_rail = QFrame()
        nav_rail.setObjectName("stitchNavRail")
        nav_rail.setFixedWidth(232)
        nav_rail.setStyleSheet("""
            QFrame#stitchNavRail {
                background-color: #131b2e;
                border-right: 1px solid #1e293b;
                border-radius: 0px;
            }
        """)
        rail_vbox = QVBoxLayout(nav_rail)
        rail_vbox.setContentsMargins(10, 14, 10, 12)
        rail_vbox.setSpacing(6)

        # Clean App Brand Header at Top of Left Sidebar
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(2, 0, 2, 8)
        brand_row.setSpacing(10)
        brand_icon_box = QFrame()
        brand_icon_box.setFixedSize(32, 32)
        brand_icon_box.setStyleSheet("QFrame { background: #222a3d; border: 1px solid #334155; border-radius: 7px; }")
        b_icon_lay = QVBoxLayout(brand_icon_box)
        b_icon_lay.setContentsMargins(0, 0, 0, 0)
        logo_lbl = QLabel()
        logo_lbl.setPixmap(self.app_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo_lbl.setAlignment(Qt.AlignCenter)
        logo_lbl.setStyleSheet("border: none; background: transparent;")
        b_icon_lay.addWidget(logo_lbl)
        brand_row.addWidget(brand_icon_box)

        lbl_brand_main = QLabel("CYBERPULSE")
        lbl_brand_main.setStyleSheet("color: #dae2fd; font-size: 14px; font-weight: 900; letter-spacing: 0.8px; border: none; background: transparent;")
        brand_row.addWidget(lbl_brand_main)
        brand_row.addStretch()
        rail_vbox.addLayout(brand_row)

        btn_rail_studio = QPushButton("⊞  Tuval Stüdyosu")
        btn_rail_studio.setStyleSheet("""
            QPushButton {
                background-color: #222a3d;
                color: #c0c1ff;
                border: none;
                border-left: 3px solid #8083ff;
                border-radius: 6px;
                padding: 9px 12px;
                font-size: 11px;
                font-weight: 900;
                text-align: left;
                letter-spacing: 0.4px;
            }
        """)
        rail_vbox.addWidget(btn_rail_studio)

        rail_nav_items = [
            ("🎨  Tema Şablonları", "Kayıtlı temaları çözünürlüğe göre gruplanmış olarak önizleyin, yükleyin, silin veya dışa/içe aktarın", self.open_theme_manager),
            ("🖥  Ekran Kataloğu", "Bağlı USB kasa ekranlarını ve HDMI monitörleri algılayın veya katalogdan model seçin", self.open_case_screen_selector),
            ("↻  Oto Döngü Havuzu", "Bu ekran (ve diğer ekranlar) için hangi temaların hangi sürede otomatik değişeceğini seçin", lambda: self.open_screen_auto_rotate_dialog(self.active_screen_slot_id)),
            ("🎮  Oyun Profilleri", "Sistemde yüklü oyunları istediğiniz temalara bağlayın — oyun açıldığında otomatik o temaya geçsin", self.open_game_profile_manager),
            ("💾  Şablona Kaydet", "Mevcut ekranın temasını kendi çözünürlüğünde tek dosya (.cptheme) olarak kaydeder", self.save_theme_to_preset_folder),
            ("✂  Medya Kırpıcı", "Arka plan medyasını ekran oranına göre kırpın veya tam sığdırın", self.open_media_crop_dialog),
        ]
        for r_text, r_tip, r_cb in rail_nav_items:
            r_btn = QPushButton(r_text)
            r_btn.setToolTip(r_tip)
            r_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #c7c4d7;
                    border: none;
                    border-radius: 6px;
                    padding: 9px 12px;
                    font-size: 11px;
                    font-weight: 800;
                    text-align: left;
                    letter-spacing: 0.3px;
                }
                QPushButton:hover {
                    background: rgba(34, 42, 61, 0.85);
                    color: #dae2fd;
                }
            """)
            r_btn.clicked.connect(r_cb)
            rail_vbox.addWidget(r_btn)

        # Batch Apply Layout to Same-Resolution Themes (Single Placement in Left Sidebar)
        self.btn_apply_full_layout = QPushButton(f"🔄  Düzeni Uygula ({init_w}×{init_h})")
        self.btn_apply_full_layout.setToolTip("Mevcut ekrandaki tüm ögeleri ve düzeni yalnızca bu ekranla aynı çözünürlükteki kayıtlı temalarınıza aktarır")
        self.btn_apply_full_layout.setStyleSheet("""
            QPushButton {
                background: rgba(0, 166, 224, 0.14);
                color: #7bd0ff;
                border: 1px solid rgba(123, 208, 255, 0.30);
                border-radius: 6px;
                padding: 9px 12px;
                font-size: 11px;
                font-weight: 800;
                text-align: left;
            }
            QPushButton:hover {
                background: rgba(0, 166, 224, 0.28);
                color: #ffffff;
            }
        """)
        self.btn_apply_full_layout.clicked.connect(self.apply_full_layout_to_all_themes)
        rail_vbox.addWidget(self.btn_apply_full_layout)

        rail_vbox.addStretch()

        # Memory Usage Card at Bottom of Left Sidebar (#060e20)
        ram_card = QFrame()
        ram_card.setStyleSheet("QFrame { background: #060e20; border: 1px solid #1e293b; border-radius: 8px; }")
        ram_vbox = QVBoxLayout(ram_card)
        ram_vbox.setContentsMargins(10, 8, 10, 8)
        ram_vbox.setSpacing(5)

        ram_top = QHBoxLayout()
        lbl_ram_title = QLabel("BELLEK YÜKÜ")
        lbl_ram_title.setStyleSheet("color: #908fa0; font-size: 9px; font-weight: 900; border: none; background: transparent;")
        ram_top.addWidget(lbl_ram_title)
        ram_top.addStretch()
        self.lbl_rail_ram_val = QLabel("-- GB")
        self.lbl_rail_ram_val.setMinimumWidth(68)
        self.lbl_rail_ram_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_rail_ram_val.setStyleSheet("color: #7bd0ff; font-family: 'Consolas', monospace; font-size: 10px; font-weight: 900; border: none; background: transparent;")
        ram_top.addWidget(self.lbl_rail_ram_val)
        ram_vbox.addLayout(ram_top)

        self.bar_rail_ram = QProgressBar()
        self.bar_rail_ram.setRange(0, 100)
        self.bar_rail_ram.setValue(35)
        self.bar_rail_ram.setTextVisible(False)
        self.bar_rail_ram.setFixedHeight(5)
        self.bar_rail_ram.setStyleSheet("""
            QProgressBar { background: #222a3d; border: none; border-radius: 2px; }
            QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8083ff, stop:1 #00a6e0); border-radius: 2px; }
        """)
        ram_vbox.addWidget(self.bar_rail_ram)
        rail_vbox.addWidget(ram_card)

        self.btn_rail_coffee = QPushButton("☕  Bana Bir Kahve Ismarla")
        self.btn_rail_coffee.setToolTip("Projeyi desteklemek için GitHub Sponsors sayfasını tarayıcıda açar")
        self.btn_rail_coffee.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(245, 158, 11, 0.22), stop:1 rgba(217, 119, 6, 0.16));
                color: #fbbf24;
                border: 1px solid rgba(251, 191, 36, 0.45);
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 11px;
                font-weight: 900;
                text-align: left;
                letter-spacing: 0.3px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f59e0b, stop:1 #d97706);
                color: #0b1326;
                border-color: #fde68a;
            }
        """)
        self.btn_rail_coffee.clicked.connect(self.open_buy_me_a_coffee)
        rail_vbox.addWidget(self.btn_rail_coffee)

        self.btn_rail_lang = QPushButton("🌐  Dil: TR | EN")
        self.btn_rail_lang.setToolTip("Uygulama dilini değiştir (Türkçe / English)")
        self.btn_rail_lang.setStyleSheet("""
            QPushButton {
                background: #060e20;
                color: #7bd0ff;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 7px 12px;
                font-size: 11px;
                font-weight: 800;
                text-align: left;
                letter-spacing: 0.3px;
            }
            QPushButton:hover {
                background: #222a3d;
                color: #ffffff;
                border-color: #8083ff;
            }
        """)
        self.btn_rail_lang.clicked.connect(self.toggle_app_language)
        rail_vbox.addWidget(self.btn_rail_lang)

        btn_rail_prefs = QPushButton("⚙  Sistem Ayarları")
        btn_rail_prefs.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #908fa0;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 11px;
                font-weight: 800;
                text-align: left;
                letter-spacing: 0.3px;
            }
            QPushButton:hover {
                background: #222a3d;
                color: #dae2fd;
            }
        """)
        btn_rail_prefs.clicked.connect(self.open_app_settings)
        rail_vbox.addWidget(btn_rail_prefs)

        shell_body.addWidget(nav_rail)

        # Right Main Studio Container (#0b1326)
        right_studio_container = QWidget()
        right_studio_container.setStyleSheet("background-color: #0b1326;")
        studio_vbox = QVBoxLayout(right_studio_container)
        studio_vbox.setContentsMargins(10, 8, 10, 8)
        studio_vbox.setSpacing(8)

        # ───────────────────────────────────────────────────────────────────────────
        # ROW 1: LIVE TELEMETRY & STREAM OUTPUT BAR (#131b2e, No Duplicate Menus)
        # ───────────────────────────────────────────────────────────────────────────
        header_frame = QFrame()
        header_frame.setObjectName("stitchStudioHeaderCard")
        header_frame.setStyleSheet("""
            QFrame#stitchStudioHeaderCard {
                background-color: #131b2e;
                border-radius: 10px;
            }
        """)
        nav_box = QHBoxLayout(header_frame)
        nav_box.setContentsMargins(10, 6, 10, 6)
        nav_box.setSpacing(8)

        # Left Telemetry Pill Container (#060e20)
        telem_pill = QFrame()
        telem_pill.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid #1e293b; border-radius: 7px; }")
        tp_hbox = QHBoxLayout(telem_pill)
        tp_hbox.setContentsMargins(10, 4, 10, 4)
        tp_hbox.setSpacing(12)

        self.lbl_top_gpu_pill = QLabel("GPU: --°C (--%)")
        self.lbl_top_gpu_pill.setMinimumWidth(112)
        self.lbl_top_gpu_pill.setStyleSheet("color: #7bd0ff; font-family: 'Consolas', monospace; font-size: 11px; font-weight: 800; border: none; background: transparent;")
        tp_hbox.addWidget(self.lbl_top_gpu_pill)

        self.lbl_top_cpu_pill = QLabel("CPU: --°C (--%)")
        self.lbl_top_cpu_pill.setMinimumWidth(112)
        self.lbl_top_cpu_pill.setStyleSheet("color: #c0c1ff; font-family: 'Consolas', monospace; font-size: 11px; font-weight: 800; border: none; background: transparent;")
        tp_hbox.addWidget(self.lbl_top_cpu_pill)

        self.lbl_top_ram_pill = QLabel("RAM: -- GB")
        self.lbl_top_ram_pill.setMinimumWidth(96)
        self.lbl_top_ram_pill.setStyleSheet("color: #4edea3; font-family: 'Consolas', monospace; font-size: 11px; font-weight: 800; border: none; background: transparent;")
        tp_hbox.addWidget(self.lbl_top_ram_pill)

        tp_sep2 = QLabel("|")
        tp_sep2.setStyleSheet("color: #2d3449; font-weight: 900; border: none; background: transparent;")
        tp_hbox.addWidget(tp_sep2)

        self.lbl_top_res_pill = QLabel(f"{init_w}×{init_h}")
        self.lbl_top_res_pill.setMinimumWidth(75)
        self.lbl_top_res_pill.setStyleSheet("color: #908fa0; font-family: 'Consolas', monospace; font-size: 10px; font-weight: 800; border: none; background: transparent;")
        tp_hbox.addWidget(self.lbl_top_res_pill)

        nav_box.addWidget(telem_pill)
        nav_box.addStretch()

        # Right Stream Deck Pills (#060e20)
        target_pill = QFrame()
        target_pill.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid #1e293b; border-radius: 7px; }")
        tp_lay = QHBoxLayout(target_pill)
        tp_lay.setContentsMargins(7, 2, 4, 2)
        tp_lay.setSpacing(4)
        lbl_target = QLabel("HEDEF:")
        lbl_target.setStyleSheet("font-weight: 900; color: #908fa0; font-size: 9px; border: none; background: transparent;")
        tp_lay.addWidget(lbl_target)

        self.combo_output_target = QComboBox()
        self.combo_output_target.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_output_target.setStyleSheet("background: #131b2e; border: none; border-radius: 4px; padding: 2px 6px; color: #dae2fd; font-size: 11px; font-weight: 800;")
        self.combo_output_target.addItem("📟 Kasa LCD (USB)", "usb_serial")
        self.combo_output_target.addItem("🖥 Monitör (HDMI)", "hdmi_monitor")
        self.combo_output_target.addItem("⚡ Çift Çıkış (USB+HDMI)", "both")
        curr_out_mode = self.app_settings.get('output_mode', 'usb_serial')
        for i in range(self.combo_output_target.count()):
            if self.combo_output_target.itemData(i) == curr_out_mode:
                self.combo_output_target.setCurrentIndex(i)
                break
        self.combo_output_target.currentIndexChanged.connect(self.on_output_target_changed)
        tp_lay.addWidget(self.combo_output_target)
        nav_box.addWidget(target_pill)

        port_pill = QFrame()
        port_pill.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid #1e293b; border-radius: 7px; }")
        pp_lay = QHBoxLayout(port_pill)
        pp_lay.setContentsMargins(7, 2, 4, 2)
        pp_lay.setSpacing(4)
        lbl_port = QLabel("PORT:")
        lbl_port.setStyleSheet("font-weight: 900; color: #908fa0; font-size: 9px; border: none; background: transparent;")
        pp_lay.addWidget(lbl_port)

        self.combo_port = QComboBox()
        self.combo_port.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_port.setMinimumContentsLength(14)
        self.combo_port.setStyleSheet("background: #131b2e; border: none; border-radius: 4px; padding: 2px 6px; color: #4edea3; font-family: 'Consolas', monospace; font-size: 11px; font-weight: 800;")
        self.combo_port.currentIndexChanged.connect(self.on_port_selection_changed)
        pp_lay.addWidget(self.combo_port)

        btn_rescan_ports = QPushButton("↻")
        btn_rescan_ports.setToolTip("Kullanılabilir COM portlarını yeniden tara")
        btn_rescan_ports.setStyleSheet("background: #222a3d; border: none; border-radius: 4px; padding: 2px 6px; color: #dae2fd; font-weight: 900; font-size: 11px;")
        btn_rescan_ports.clicked.connect(self.populate_com_ports)
        pp_lay.addWidget(btn_rescan_ports)
        nav_box.addWidget(port_pill)

        self.lbl_port_status = QLabel("● HAZIR")
        self.lbl_port_status.setStyleSheet(
            "background: #060e20; color: #908fa0; border: 1px solid #222a3d; border-radius: 6px; padding: 4px 8px; font-weight: 800; font-size: 10px;"
        )
        nav_box.addWidget(self.lbl_port_status)

        self.btn_stream = QPushButton("🚀 CANLI YANSIT")
        self.btn_stream.setStyleSheet("background: #00885d; color: #eafff6; font-size: 11px; font-weight: 900; padding: 6px 14px; border-radius: 7px; border: none;")
        self.btn_stream.clicked.connect(lambda: self.toggle_live_stream(silent_on_fail=False))
        nav_box.addWidget(self.btn_stream)

        studio_vbox.addWidget(header_frame)

        # ───────────────────────────────────────────────────────────────────────────
        # ROW 2: MULTI-SCREEN WORKSPACE CONTROLLER CARD (#131b2e, 2-Row Stitch Layout)
        # ───────────────────────────────────────────────────────────────────────────
        self.multi_screen_frame = QFrame()
        self.multi_screen_frame.setObjectName("multiScreenCard")
        self.multi_screen_frame.setStyleSheet("""
            QFrame#multiScreenCard {
                background-color: #131b2e;
                border-radius: 10px;
            }
        """)
        ms_outer_vbox = QVBoxLayout(self.multi_screen_frame)
        ms_outer_vbox.setContentsMargins(10, 6, 10, 6)
        ms_outer_vbox.setSpacing(5)

        # Sub-row 1: Screen Workspace Switcher Tabs + Add / Remove Screen
        ms_row1 = QHBoxLayout()
        ms_row1.setContentsMargins(0, 0, 0, 0)
        ms_row1.setSpacing(6)

        lbl_ms_hdr = QLabel("🖥 EKRANLAR:")
        lbl_ms_hdr.setStyleSheet("color: #908fa0; font-weight: 900; font-size: 10px; letter-spacing: 0.9px; border: none; background: transparent;")
        ms_row1.addWidget(lbl_ms_hdr)

        self.screen_tabs_container = QWidget()
        self.screen_tabs_container.setStyleSheet("border: none; background: transparent;")
        self.screen_tabs_layout = QHBoxLayout(self.screen_tabs_container)
        self.screen_tabs_layout.setContentsMargins(0, 0, 0, 0)
        self.screen_tabs_layout.setSpacing(6)
        ms_row1.addWidget(self.screen_tabs_container)

        ms_row1.addStretch()

        btn_add_scr = QPushButton("＋ Ekran Ekle")
        btn_add_scr.setToolTip("Yeni bir ekran veya Kasa Ekranı Kataloğundan özel bir ekran modeli için ayrı tema oluşturucu açar")
        btn_add_scr.setStyleSheet(
            "background: rgba(0, 166, 224, 0.14); border: 1px solid rgba(123, 208, 255, 0.35); color: #7bd0ff; "
            "border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 800;"
        )
        btn_add_scr.clicked.connect(self.add_custom_screen_workspace_dialog)
        ms_row1.addWidget(btn_add_scr)

        self.btn_rem_scr = QPushButton("🗑")
        self.btn_rem_scr.setToolTip("Seçili özel ekran yuvasını kaldır")
        self.btn_rem_scr.setStyleSheet("background: #060e20; border: 1px solid #222a3d; color: #908fa0; border-radius: 6px; padding: 4px 8px; font-size: 11px;")
        self.btn_rem_scr.clicked.connect(self.remove_active_custom_screen_workspace)
        ms_row1.addWidget(self.btn_rem_scr)

        ms_outer_vbox.addLayout(ms_row1)

        # Sub-row 2: Inner Dark Control Strip (#060e20)
        ms_row2_strip = QFrame()
        ms_row2_strip.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid #1e293b; border-radius: 8px; }")
        ms_row2 = QHBoxLayout(ms_row2_strip)
        ms_row2.setContentsMargins(10, 4, 10, 4)
        ms_row2.setSpacing(10)

        self.chk_slot_stream_enabled = QCheckBox("Yayına Dahil Et")
        self.chk_slot_stream_enabled.setToolTip("Bu ekranı çoklu ekran canlı yansıtmasına dahil eder")
        self.chk_slot_stream_enabled.setChecked(True)
        self.chk_slot_stream_enabled.setStyleSheet("color: #dae2fd; font-weight: 800; font-size: 11px; border: none; background: transparent;")
        self.chk_slot_stream_enabled.stateChanged.connect(self.on_slot_stream_enabled_toggled)
        ms_row2.addWidget(self.chk_slot_stream_enabled)

        lbl_slot_res = QLabel("📐 Çözünürlük:")
        lbl_slot_res.setStyleSheet("color: #908fa0; font-weight: 800; font-size: 10px; border: none; background: transparent;")
        ms_row2.addWidget(lbl_slot_res)

        self.combo_slot_resolution = QComboBox()
        self.combo_slot_resolution.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_slot_resolution.setMinimumContentsLength(18)
        self.combo_slot_resolution.setStyleSheet("background: #171f33; border: 1px solid #2d3449; border-radius: 5px; padding: 3px 8px; color: #dae2fd; font-size: 11px; font-weight: 800;")
        self.combo_slot_resolution.setToolTip("Seçili ekranın kendi tema tasarım çözünürlüğünü (örn. 1920×1080 Full HD, 320×1480, 2K, 4K veya Özel) belirler")
        self.combo_slot_resolution.currentIndexChanged.connect(self.on_slot_resolution_selected)
        ms_row2.addWidget(self.combo_slot_resolution, stretch=1)

        lbl_quick_t = QLabel("🎨 Tema:")
        lbl_quick_t.setStyleSheet("color: #908fa0; font-weight: 800; font-size: 10px; border: none; background: transparent;")
        ms_row2.addWidget(lbl_quick_t)

        self.combo_slot_quick_theme = QComboBox()
        self.combo_slot_quick_theme.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_slot_quick_theme.setMinimumContentsLength(16)
        self.combo_slot_quick_theme.setStyleSheet("background: #171f33; border: 1px solid #2d3449; border-radius: 5px; padding: 3px 8px; color: #dae2fd; font-size: 11px; font-weight: 800;")
        self.combo_slot_quick_theme.setToolTip("Yalnızca seçili ekran için hızlıca farklı bir .cptheme teması yükler (Çözünürlüğe göre gruplanmıştır)")
        self.combo_slot_quick_theme.currentIndexChanged.connect(self.on_slot_quick_theme_selected)
        ms_row2.addWidget(self.combo_slot_quick_theme, stretch=1)

        self.chk_slot_auto_rotate = QCheckBox("Oto Döngü")
        self.chk_slot_auto_rotate.setToolTip("Bu ekranda seçili temaların otomatik olarak sırayla/rastgele değişmesini açar/kapatır")
        self.chk_slot_auto_rotate.setStyleSheet("color: #dae2fd; font-weight: 800; font-size: 11px; border: none; background: transparent;")
        self.chk_slot_auto_rotate.stateChanged.connect(self.on_slot_auto_rotate_toggled)
        ms_row2.addWidget(self.chk_slot_auto_rotate)

        btn_clone_scr = QPushButton("📋 Kopyala")
        btn_clone_scr.setToolTip("Başka bir ekranın özel temasını bu ekrana kopyalar ve boyuta uyarlar")
        btn_clone_scr.setStyleSheet("background: #171f33; border: 1px solid #2d3449; color: #c7c4d7; border-radius: 5px; padding: 3px 9px; font-size: 11px; font-weight: 700;")
        btn_clone_scr.clicked.connect(self.clone_theme_from_another_screen)
        ms_row2.addWidget(btn_clone_scr)

        ms_outer_vbox.addWidget(ms_row2_strip)
        studio_vbox.addWidget(self.multi_screen_frame)

        # ───────────────────────────────────────────────────────────────────────────
        # ROW 3: 3-COLUMN STUDIO WORKSPACE (Clean #131b2e Stitch Cards, No QGroupBox!)
        # ───────────────────────────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)
        splitter.setChildrenCollapsible(False)
        splitter.splitterMoved.connect(lambda _pos, _idx: self.update_canvas_geometry())
        self.main_splitter = splitter

        # ═══════════════════════════════════════════════════════════════════════════
        # COLUMN 1: LEFT PANEL — MEDIA LAYER & SENSOR MODULES (#131b2e Stitch Card)
        # ═══════════════════════════════════════════════════════════════════════════
        left_box = QFrame()
        left_box.setObjectName("stitchLeftColCard")
        left_box.setMinimumWidth(310)
        left_box.setStyleSheet("""
            QFrame#stitchLeftColCard {
                background-color: #131b2e;
                border-radius: 10px;
            }
        """)
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(6)

        # Media Layer Header Row
        media_hdr_row = QHBoxLayout()
        lbl_media_sec = QLabel("ARKA PLAN MEDYASI")
        lbl_media_sec.setStyleSheet("color: #c0c1ff; font-size: 10px; font-weight: 900; letter-spacing: 0.8px; border: none; background: transparent;")
        media_hdr_row.addWidget(lbl_media_sec)
        media_hdr_row.addStretch()
        left_layout.addLayout(media_hdr_row)

        media_btn_row = QHBoxLayout()
        media_btn_row.setSpacing(6)
        btn_select_bg = QPushButton("🖼 Medya Seç")
        btn_select_bg.setToolTip("Arka plan resmi, GIF veya MP4 videosu seçin")
        btn_select_bg.setStyleSheet("background: #222a3d; border: 1px solid #334155; color: #dae2fd; font-weight: 800; padding: 6px; border-radius: 7px; font-size: 11px;")
        btn_select_bg.clicked.connect(self.select_background_media)
        media_btn_row.addWidget(btn_select_bg)

        btn_open_crop = QPushButton("✂ Kırp / Sığdır")
        btn_open_crop.setToolTip("Arka plan medyasını ekran oranına göre kırpın veya tam sığdırın")
        btn_open_crop.setStyleSheet("background: #222a3d; border: 1px solid #334155; color: #dae2fd; font-weight: 800; padding: 6px; border-radius: 7px; font-size: 11px;")
        btn_open_crop.clicked.connect(self.open_media_crop_dialog)
        media_btn_row.addWidget(btn_open_crop)
        left_layout.addLayout(media_btn_row)

        # Dark Background File Pill (#060e20)
        bg_pill_frame = QFrame()
        bg_pill_frame.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid #1e293b; border-radius: 6px; }")
        bg_pill_lay = QHBoxLayout(bg_pill_frame)
        bg_pill_lay.setContentsMargins(8, 5, 8, 5)
        self.lbl_bg_info = QLabel("🎞 Varsayılan Koyu Arka Plan")
        self.lbl_bg_info.setStyleSheet("color: #4edea3; font-family: 'Consolas', monospace; font-size: 10px; font-weight: 800; border: none; background: transparent;")
        if self.theme_data.get('bg_path'):
            self.lbl_bg_info.setText(f"🎞 {os.path.basename(self.theme_data['bg_path'])[:26]}")
        bg_pill_lay.addWidget(self.lbl_bg_info)
        bg_pill_lay.addStretch()
        self.lbl_bg_res_tag = QLabel(f"{init_w}×{init_h}")
        self.lbl_bg_res_tag.setStyleSheet("color: #908fa0; font-family: 'Consolas', monospace; font-size: 9px; font-weight: 800; border: none; background: transparent;")
        bg_pill_lay.addWidget(self.lbl_bg_res_tag)
        left_layout.addWidget(bg_pill_frame)

        # 2-Column Hardware Refresh & Orientation Sub-Cards (#060e20)
        hw_cfg_row = QHBoxLayout()
        hw_cfg_row.setSpacing(6)

        ref_subcard = QFrame()
        ref_subcard.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid #1e293b; border-radius: 7px; }")
        ref_v = QVBoxLayout(ref_subcard)
        ref_v.setContentsMargins(7, 4, 7, 5)
        ref_v.setSpacing(2)
        lbl_ref_cap = QLabel("YENİLEME HIZI")
        lbl_ref_cap.setStyleSheet("color: #908fa0; font-size: 8px; font-weight: 900; letter-spacing: 0.7px; border: none; background: transparent;")
        ref_v.addWidget(lbl_ref_cap)
        self.spin_refresh = QSpinBox()
        self.spin_refresh.setRange(1, 10)
        self.spin_refresh.setValue(int(self.theme_data.get('refresh_sec', 1)))
        self.spin_refresh.setSuffix(" sn")
        self.spin_refresh.setStyleSheet("background: #131b2e; border: 1px solid #222a3d; border-radius: 4px; padding: 2px 5px; font-size: 11px;")
        self.spin_refresh.valueChanged.connect(self.on_refresh_speed_changed)
        ref_v.addWidget(self.spin_refresh)
        hw_cfg_row.addWidget(ref_subcard, stretch=1)

        rot_subcard = QFrame()
        rot_subcard.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid #1e293b; border-radius: 7px; }")
        rot_v = QVBoxLayout(rot_subcard)
        rot_v.setContentsMargins(7, 4, 7, 5)
        rot_v.setSpacing(2)
        lbl_rot_cap = QLabel("EKRAN YÖNÜ")
        lbl_rot_cap.setStyleSheet("color: #908fa0; font-size: 8px; font-weight: 900; letter-spacing: 0.7px; border: none; background: transparent;")
        rot_v.addWidget(lbl_rot_cap)
        self.combo_rot = QComboBox()
        self.combo_rot.addItems(["180° (Düz)", "0° (Normal)", "90° (Yan)", "270° (Ters)"])
        self.combo_rot.setStyleSheet("background: #131b2e; border: 1px solid #222a3d; border-radius: 4px; padding: 2px 5px; font-size: 11px;")
        self.combo_rot.currentIndexChanged.connect(self.on_rotation_changed)
        rot_v.addWidget(self.combo_rot)
        hw_cfg_row.addWidget(rot_subcard, stretch=1)

        left_layout.addLayout(hw_cfg_row)

        # Sensor & Widget Modules Header Row
        sen_hdr_row = QHBoxLayout()
        lbl_sen_sec = QLabel("SENSÖR VE BİLEŞENLER")
        lbl_sen_sec.setStyleSheet("color: #c0c1ff; font-size: 10px; font-weight: 900; letter-spacing: 0.8px; border: none; background: transparent; margin-top: 2px;")
        sen_hdr_row.addWidget(lbl_sen_sec)
        sen_hdr_row.addStretch()
        left_layout.addLayout(sen_hdr_row)

        # Stitch Sensor Search Input (#060e20)
        self.txt_sensor_filter = QLineEdit()
        self.txt_sensor_filter.setPlaceholderText("🔍 Sensör veya bileşen ara...")
        self.txt_sensor_filter.setClearButtonEnabled(True)
        self.txt_sensor_filter.setStyleSheet("background: #060e20; border: 1px solid #1e293b; border-radius: 7px; padding: 6px 10px; color: #dae2fd; font-size: 11px;")
        self.txt_sensor_filter.textChanged.connect(self.filter_sensor_library_list)
        left_layout.addWidget(self.txt_sensor_filter)

        self.sensor_list = QListWidget()
        self.sensor_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sensor_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                padding: 0px;
                outline: none;
            }
            QListWidget::item {
                background-color: transparent;
                padding: 0px;
                margin-bottom: 4px;
                border-radius: 8px;
            }
            QListWidget::item:selected {
                background-color: rgba(128, 131, 255, 0.22);
                border: 1px solid #8083ff;
            }
        """)
        sensor_items = [
            ("📈 Canlı Çizgi Grafik (Sparkline)", "cpu_temp", "sparkline_graph", "60s Geçmiş", "#8083ff", "rgba(128,131,255,0.18)"),
            ("🖼️ Özel Resim / Logo / İkon Katmanı", "custom_image", "custom_image", "PNG / WebP / GIF", "#c0c1ff", "rgba(128,131,255,0.18)"),
            ("🎮 FPS Göstergesi", "game_fps", "sensor", "RTSS Hook", "#4edea3", "rgba(0,136,93,0.20)"),
            ("🌡️ CPU Sıcaklığı", "cpu_temp", "sensor", "Core Tctl/Tdie", "#7bd0ff", "rgba(0,166,224,0.18)"),
            ("⚡ CPU Kullanımı (%)", "cpu_load", "sensor", "Tüm Çekirdekler", "#7bd0ff", "rgba(0,166,224,0.18)"),
            ("🚀 CPU Frekansı (MHz)", "cpu_clock", "sensor", "Boost Saati", "#7bd0ff", "rgba(0,166,224,0.18)"),
            ("🌀 CPU Fan Hızı (RPM)", "cpu_fan", "sensor", "PWM Anakart", "#7bd0ff", "rgba(0,166,224,0.18)"),
            ("🔥 GPU Sıcaklığı", "gpu_temp", "sensor", "GPU Çekirdek", "#ffb4ab", "rgba(239,68,68,0.18)"),
            ("🎮 GPU Kullanımı (%)", "gpu_load", "sensor", "3D Motor Yükü", "#ffb4ab", "rgba(239,68,68,0.18)"),
            ("🌀 GPU Fan Hızı (%)", "gpu_fan", "sensor", "Soğutucu Fan", "#ffb4ab", "rgba(239,68,68,0.18)"),
            ("💾 RAM Kullanımı (GB)", "ram_used", "sensor", "Kullanılan Bellek", "#c0c1ff", "rgba(128,131,255,0.18)"),
            ("💾 Kalan / Boş RAM (GB)", "ram_free", "sensor", "Kalan Boş Bellek", "#4edea3", "rgba(0,136,93,0.20)"),
            ("💿 Disk Okuma/Yazma (MB/s)", "disk_io", "sensor", "NVMe / SATA I/O", "#4edea3", "rgba(0,136,93,0.20)"),
            ("⏳ Sistem Açık Kalma Süresi", "system_uptime", "sensor", "Çalışma Süresi", "#908fa0", "rgba(144,143,160,0.16)"),
            ("📥 İndirme Hızı (Download)", "net_down", "sensor", "Canlı Ağ Akışı", "#4edea3", "rgba(0,136,93,0.20)"),
            ("📤 Yükleme Hızı (Upload)", "net_up", "sensor", "Canlı Ağ Akışı", "#7bd0ff", "rgba(0,166,224,0.18)"),
            ("📶 İnternet Ping (ms)", "net_ping", "sensor", "Gecikme (ms)", "#4edea3", "rgba(0,136,93,0.20)"),
            ("⏰ Dijital Saat", "time_digital", "time", "Sistem Saati", "#c0c1ff", "rgba(128,131,255,0.18)"),
            ("📅 Tarih (GG.AA.YYYY)", "date_full", "date", "Takvim", "#c0c1ff", "rgba(128,131,255,0.18)"),
            ("🗓️ Türkçe Gün & Tarih", "date_day_tr", "date", "Yerel Takvim", "#c0c1ff", "rgba(128,131,255,0.18)"),
            ("📊 Yatay İlerleme Çubuğu", "cpu_load", "gauge", "Progress Bar", "#7bd0ff", "rgba(0,166,224,0.18)"),
            ("📶 Dikey İlerleme Çubuğu", "ram_load", "vertical_gauge", "Dikey Bar", "#c0c1ff", "rgba(128,131,255,0.18)"),
            ("⭕ Dairesel Gösterge", "gpu_load", "circle_gauge", "Radial Kadran", "#8083ff", "rgba(128,131,255,0.18)"),
            ("🌀 Canlı Döner Fan Göstergesi", "gpu_load", "animated_fan", "60 FPS Animasyon", "#4edea3", "rgba(0,136,93,0.20)"),
            ("📜 Kayan LED Metin (Marquee)", "sistem_ozellikleri", "marquee", "Granular Kayan Yazı", "#7bd0ff", "rgba(0,166,224,0.18)"),
            ("🎵 YouTube Music / Medya Kartı", "music_title", "music_player", "SMTC Medya Bilgisi", "#ffb4ab", "rgba(239,68,68,0.18)"),
            ("🌦️ Canlı Hava Durumu Kartı", "weather_temp", "weather_widget", "Otomatik Konum", "#7bd0ff", "rgba(0,166,224,0.18)"),
            ("📈 Canlı Ping Monitörü", "net_ping", "ping_monitor", "Ağ Grafiği", "#4edea3", "rgba(0,136,93,0.20)"),
            ("🗓️ Akıllı Etkinlik Geri Sayım", "countdown", "event_countdown", "Hedef Tarih Sayacı", "#c0c1ff", "rgba(128,131,255,0.18)"),
            ("✍️ Özel Düz Metin", "text", "text", "Serbest Başlık", "#dae2fd", "rgba(144,143,160,0.16)"),
            ("🔲 Arka Plan Kutusu / Çizgisi", "box", "box", "HUD Çerçeve / Panel", "#908fa0", "rgba(144,143,160,0.16)")
        ]

        default_lbl_map = {
            "game_fps": "FPS",
            "cpu_temp": "CPU",
            "cpu_load": "CPU YÜK",
            "cpu_clock": "CPU MHZ",
            "cpu_fan": "CPU FAN",
            "gpu_temp": "GPU",
            "gpu_load": "GPU YÜK",
            "gpu_fan": "GPU FAN",
            "ram_used": "RAM",
            "ram_load": "RAM",
            "ram_free": "BOŞ RAM",
            "ram_free_load": "BOŞ RAM",
            "disk_io": "DİSK",
            "system_uptime": "AÇIK SÜRE",
            "net_down": "İNDİRME",
            "net_up": "YÜKLEME",
            "net_ping": "PING",
        }
        self._sensor_card_value_labels = []
        for label, s_id, s_type, sub_desc, accent_fg, icon_bg in sensor_items:
            item = QListWidgetItem("")
            if s_type in ("custom_image", "time", "date", "box", "music_player", "weather_widget", "ping_monitor"):
                default_lbl = ""
            else:
                default_lbl = default_lbl_map.get(s_id, label.split()[-1])
            item.setData(Qt.UserRole, {
                "sensorId": s_id,
                "label": default_lbl,
                "type": s_type,
                "search_title": f"{label} {sub_desc}"
            })
            item.setSizeHint(QSize(260, 50))
            self.sensor_list.addItem(item)

            # Build Stitch Sensor Module Card Widget (#171f33)
            parts = label.split(" ", 1)
            icon_ch = parts[0] if len(parts) > 1 else "◈"
            clean_title = parts[1] if len(parts) > 1 else label

            s_card = QFrame()
            s_card.setStyleSheet("""
                QFrame {
                    background-color: #171f33;
                    border: 1px solid #222a3d;
                    border-radius: 8px;
                }
                QFrame:hover {
                    background-color: #222a3d;
                    border-color: #8083ff;
                }
            """)
            sc_lay = QHBoxLayout(s_card)
            sc_lay.setContentsMargins(7, 4, 7, 4)
            sc_lay.setSpacing(6)

            ic_lbl = QLabel(icon_ch)
            ic_lbl.setFixedSize(26, 26)
            ic_lbl.setAlignment(Qt.AlignCenter)
            ic_lbl.setStyleSheet(f"background: {icon_bg}; color: {accent_fg}; border-radius: 6px; font-size: 12px; border: none;")
            sc_lay.addWidget(ic_lbl)

            txt_stack = QVBoxLayout()
            txt_stack.setContentsMargins(0, 0, 0, 0)
            txt_stack.setSpacing(1)
            t_lbl = QLabel(clean_title)
            t_lbl.setStyleSheet("color: #dae2fd; font-size: 10px; font-weight: 800; border: none; background: transparent;")
            sub_lbl = QLabel(sub_desc)
            sub_lbl.setStyleSheet("color: #908fa0; font-size: 9px; font-weight: 700; border: none; background: transparent;")
            txt_stack.addWidget(t_lbl)
            txt_stack.addWidget(sub_lbl)
            sc_lay.addLayout(txt_stack, stretch=1)

            val_badge = QLabel("WIDGET" if s_type not in ("sensor", "time", "date") else "--")
            val_badge.setMinimumWidth(74)
            val_badge.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_badge.setStyleSheet(
                f"color: {accent_fg}; font-family: 'Consolas', monospace; font-size: 9px; font-weight: 900; border: none; background: transparent;"
            )
            sc_lay.addWidget(val_badge)
            self._sensor_card_value_labels.append((s_id, s_type, val_badge))
            self.sensor_list.setItemWidget(item, s_card)

        self.sensor_list.itemDoubleClicked.connect(self.add_sensor_element)
        left_layout.addWidget(self.sensor_list, stretch=1)

        btn_add = QPushButton("➕ SEÇİLİ ÖGEYİ TUVALE EKLE")
        btn_add.setStyleSheet(
            "background: #8083ff; color: #07006c; font-weight: 900; padding: 9px; border-radius: 8px; border: none; font-size: 11px;"
        )
        btn_add.clicked.connect(lambda: self.add_sensor_element(self.sensor_list.currentItem()))
        left_layout.addWidget(btn_add)

        splitter.addWidget(left_box)

        # ═══════════════════════════════════════════════════════════════════════════
        # COLUMN 2: CENTER PANEL — INTERACTIVE CANVAS STAGE (#131b2e Stitch Card)
        # ═══════════════════════════════════════════════════════════════════════════
        self.center_box = QFrame()
        self.center_box.setObjectName("stitchCenterStageCard")
        center_box = self.center_box
        center_box.setMinimumWidth(360)
        center_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        center_box.setStyleSheet("""
            QFrame#stitchCenterStageCard {
                background-color: #131b2e;
                border-radius: 10px;
            }
        """)
        center_layout = QVBoxLayout(center_box)
        center_layout.setContentsMargins(10, 10, 10, 10)
        center_layout.setSpacing(8)

        # Top Mini Stage Toolbar (#060e20)
        stage_top_bar = QFrame()
        stage_top_bar.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid #1e293b; border-radius: 8px; }")
        canvas_toolbar = QHBoxLayout(stage_top_bar)
        canvas_toolbar.setContentsMargins(8, 4, 8, 4)
        canvas_toolbar.setSpacing(6)

        self.btn_undo = QPushButton("↶ Geri Al")
        self.btn_undo.setToolTip("Son işlemi geri al (Ctrl+Z)")
        self.btn_undo.setEnabled(False)
        self.btn_undo.setStyleSheet("background: #171f33; color: #dae2fd; border: none; border-radius: 5px; padding: 4px 8px; font-size: 11px; font-weight: 800;")
        self.btn_undo.clicked.connect(self.undo_action)
        canvas_toolbar.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("↷ İleri Al")
        self.btn_redo.setToolTip("Geri alınan işlemi yinele (Ctrl+Y)")
        self.btn_redo.setEnabled(False)
        self.btn_redo.setStyleSheet("background: #171f33; color: #dae2fd; border: none; border-radius: 5px; padding: 4px 8px; font-size: 11px; font-weight: 800;")
        self.btn_redo.clicked.connect(self.redo_action)
        canvas_toolbar.addWidget(self.btn_redo)

        self.chk_snap_guides = QCheckBox("⊞ Mıknatıs")
        self.chk_snap_guides.setChecked(True)
        self.chk_snap_guides.setToolTip("Sürüklerken tuval merkezine ve diğer ögelere otomatik hizala (Alt tuşu ile geçici devre dışı bırakılır)")
        self.chk_snap_guides.setStyleSheet("color: #7bd0ff; font-weight: 800; font-size: 10px; border: none; background: transparent;")
        self.chk_snap_guides.stateChanged.connect(lambda st: setattr(self, 'snap_to_guides_enabled', st == Qt.Checked))
        canvas_toolbar.addWidget(self.chk_snap_guides)

        canvas_toolbar.addStretch()

        self.lbl_center_ws_title = QLabel(f"🎨 {self.theme_data.get('name', 'Özel')}")
        self.lbl_center_ws_title.setStyleSheet("color: #908fa0; font-size: 11px; font-weight: 800; border: none; background: transparent;")
        canvas_toolbar.addWidget(self.lbl_center_ws_title)

        canvas_toolbar.addStretch()

        self.lbl_canvas_res_badge = QLabel(f"📐 {init_w}×{init_h}")
        self.lbl_canvas_res_badge.setStyleSheet(
            "background: rgba(128, 131, 255, 0.16); color: #c0c1ff; border: 1px solid rgba(128, 131, 255, 0.35); "
            "border-radius: 5px; padding: 3px 9px; font-family: 'Consolas', monospace; font-size: 10px; font-weight: 900;"
        )
        canvas_toolbar.addWidget(self.lbl_canvas_res_badge)

        center_layout.addWidget(stage_top_bar)

        # Viewport Stage Backdrop (#060e20) with Hardware Bezel Frame
        self.canvas_stage = QFrame()
        self.canvas_stage.setObjectName("canvasStageBackdrop")
        self.canvas_stage.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas_stage.setStyleSheet("""
            QFrame#canvasStageBackdrop {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.85, fx:0.5, fy:0.5, stop:0 #131b2e, stop:1 #060e20);
                border: 1px solid #1e293b;
                border-radius: 10px;
            }
        """)
        stage_layout = QVBoxLayout(self.canvas_stage)
        stage_layout.setContentsMargins(10, 8, 10, 8)
        stage_layout.setSpacing(4)

        self.canvas_widget = InteractiveCanvasWidget(self)
        stage_layout.addWidget(self.canvas_widget, stretch=1, alignment=Qt.AlignCenter)
        center_layout.addWidget(self.canvas_stage, stretch=1)

        splitter.addWidget(center_box)

        # ═══════════════════════════════════════════════════════════════════════════
        # COLUMN 3: RIGHT PANEL — LAYER STACK & SELECTED ELEMENT INSPECTOR (#131b2e)
        # ═══════════════════════════════════════════════════════════════════════════
        right_box = QFrame()
        right_box.setObjectName("stitchRightColCard")
        right_box.setMinimumWidth(355)
        right_box.setStyleSheet("""
            QFrame#stitchRightColCard {
                background-color: #131b2e;
                border-radius: 10px;
            }
        """)
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(6)

        # Layer Stack Header + Compact Icon Buttons Row
        layer_hdr_row = QHBoxLayout()
        layer_hdr_row.setSpacing(4)
        self.lbl_layer_stack_hdr = QLabel(f"KATMANLAR ({len(self.theme_data.get('elements', []))} ÖGE)")
        self.lbl_layer_stack_hdr.setStyleSheet("color: #c0c1ff; font-size: 10px; font-weight: 900; letter-spacing: 0.8px; border: none; background: transparent;")
        layer_hdr_row.addWidget(self.lbl_layer_stack_hdr)
        layer_hdr_row.addStretch()

        compact_btn_qss = """
            QPushButton {
                background: #222a3d;
                color: #dae2fd;
                border: 1px solid #2d3449;
                border-radius: 5px;
                padding: 3px;
                font-size: 11px;
                font-weight: 800;
            }
            QPushButton:hover {
                background: #8083ff;
                color: #07006c;
            }
        """
        btn_layer_up = QPushButton("↑")
        btn_layer_up.setToolTip("Katmanı bir üste taşı (Öne getir)")
        btn_layer_up.setFixedSize(26, 24)
        btn_layer_up.setStyleSheet(compact_btn_qss)
        btn_layer_up.clicked.connect(lambda: self.move_selected_element_layer(1))
        layer_hdr_row.addWidget(btn_layer_up)

        btn_layer_down = QPushButton("↓")
        btn_layer_down.setToolTip("Katmanı bir alta taşı (Arkaya gönder)")
        btn_layer_down.setFixedSize(26, 24)
        btn_layer_down.setStyleSheet(compact_btn_qss)
        btn_layer_down.clicked.connect(lambda: self.move_selected_element_layer(-1))
        layer_hdr_row.addWidget(btn_layer_down)

        btn_dup = QPushButton("❐")
        btn_dup.setToolTip("Seçili ögeyi çoğalt (Ctrl+D)")
        btn_dup.setFixedSize(26, 24)
        btn_dup.setStyleSheet(compact_btn_qss)
        btn_dup.clicked.connect(self.duplicate_selected_element)
        layer_hdr_row.addWidget(btn_dup)

        self.btn_lock_el = QPushButton("🔒")
        self.btn_lock_el.setToolTip("Seçili ögeyi kilitle / kilidi aç")
        self.btn_lock_el.setFixedSize(26, 24)
        self.btn_lock_el.setStyleSheet(compact_btn_qss)
        self.btn_lock_el.clicked.connect(self.toggle_lock_selected_element)
        layer_hdr_row.addWidget(self.btn_lock_el)

        self.btn_hide_el = QPushButton("👁")
        self.btn_hide_el.setToolTip("Seçili ögeyi gizle / göster")
        self.btn_hide_el.setFixedSize(26, 24)
        self.btn_hide_el.setStyleSheet(compact_btn_qss)
        self.btn_hide_el.clicked.connect(self.toggle_hide_selected_element)
        layer_hdr_row.addWidget(self.btn_hide_el)

        btn_del = QPushButton("🗑")
        btn_del.setToolTip("Seçili öge(ler)i sil (Delete)")
        btn_del.setFixedSize(26, 24)
        btn_del.setStyleSheet("QPushButton { background: rgba(239, 68, 68, 0.18); color: #ffb4ab; border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 5px; padding: 3px; font-size: 11px; } QPushButton:hover { background: #ef4444; color: white; }")
        btn_del.clicked.connect(self.delete_selected_element)
        layer_hdr_row.addWidget(btn_del)

        right_layout.addLayout(layer_hdr_row)

        self.element_list = QListWidget()
        self.element_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.element_list.setMaximumHeight(168)
        self.element_list.setStyleSheet("""
            QListWidget {
                background-color: #060e20;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 6px;
                margin-bottom: 3px;
                background-color: #171f33;
                color: #c7c4d7;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                font-weight: 700;
            }
            QListWidget::item:hover {
                background-color: #222a3d;
                color: #ffffff;
            }
            QListWidget::item:selected {
                background-color: #8083ff;
                color: #07006c;
                font-weight: 900;
            }
        """)
        self.element_list.itemClicked.connect(self.on_element_selected)
        right_layout.addWidget(self.element_list)

        # Quick Alignment & Distribution Strip (#060e20)
        align_strip = QFrame()
        align_strip.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid #1e293b; border-radius: 7px; }")
        align_bar_box = QHBoxLayout(align_strip)
        align_bar_box.setContentsMargins(8, 4, 8, 4)
        align_bar_box.setSpacing(4)

        lbl_align_tag = QLabel("HİZALA")
        lbl_align_tag.setStyleSheet("color: #908fa0; font-size: 9px; font-weight: 900; letter-spacing: 0.8px; border: none; background: transparent;")
        align_bar_box.addWidget(lbl_align_tag)
        align_bar_box.addStretch()

        align_btn_qss = "QPushButton { background: #131b2e; color: #c7c4d7; border: 1px solid #222a3d; border-radius: 4px; padding: 3px 7px; font-size: 10px; font-weight: 800; } QPushButton:hover { background: #222a3d; color: #ffffff; border-color: #8083ff; }"

        btn_al_left = QPushButton("⬅ Sol")
        btn_al_left.setToolTip("Sol kenara hizala")
        btn_al_left.setStyleSheet(align_btn_qss)
        btn_al_left.clicked.connect(lambda: self.align_selected_elements('left'))
        align_bar_box.addWidget(btn_al_left)

        btn_al_hcenter = QPushButton("↔ Orta")
        btn_al_hcenter.setToolTip("Yatay ortala")
        btn_al_hcenter.setStyleSheet(align_btn_qss)
        btn_al_hcenter.clicked.connect(lambda: self.align_selected_elements('hcenter'))
        align_bar_box.addWidget(btn_al_hcenter)

        btn_al_right = QPushButton("➡ Sağ")
        btn_al_right.setToolTip("Sağ kenara hizala")
        btn_al_right.setStyleSheet(align_btn_qss)
        btn_al_right.clicked.connect(lambda: self.align_selected_elements('right'))
        align_bar_box.addWidget(btn_al_right)

        btn_al_vcenter = QPushButton("↕ Dikey")
        btn_al_vcenter.setToolTip("Dikey ortala")
        btn_al_vcenter.setStyleSheet(align_btn_qss)
        btn_al_vcenter.clicked.connect(lambda: self.align_selected_elements('vcenter'))
        align_bar_box.addWidget(btn_al_vcenter)

        btn_distribute = QPushButton("🟰 Dağıt")
        btn_distribute.setToolTip("Dikey boşlukları eşit dağıt")
        btn_distribute.setStyleSheet("QPushButton { background: #131b2e; color: #7bd0ff; border: 1px solid #222a3d; border-radius: 4px; padding: 3px 7px; font-size: 10px; font-weight: 800; } QPushButton:hover { background: #222a3d; color: #ffffff; }")
        btn_distribute.clicked.connect(self.distribute_selected_elements)
        align_bar_box.addWidget(btn_distribute)

        right_layout.addWidget(align_strip)

        lbl_insp_sec = QLabel("SEÇİLİ ÖGE AYARLARI")
        lbl_insp_sec.setStyleSheet("color: #c0c1ff; font-size: 10px; font-weight: 900; letter-spacing: 0.8px; border: none; background: transparent; margin-top: 2px;")
        right_layout.addWidget(lbl_insp_sec)

        # Empty Selection Placeholder (Visible when no element is selected)
        self.lbl_empty_prop = QLabel("ℹ️ Düzenlemek için tuvalden veya katman listesinden bir öge seçin")
        self.lbl_empty_prop.setWordWrap(True)
        self.lbl_empty_prop.setStyleSheet("color: #908fa0; font-size: 11px; font-weight: 700; background: #060e20; border: 1px dashed #222a3d; border-radius: 8px; padding: 18px 12px;")
        self.lbl_empty_prop.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.lbl_empty_prop)

        # Properties Editor Container inside a Smooth Scroll Area
        self.prop_scroll = QScrollArea()
        self.prop_scroll.setWidgetResizable(True)
        self.prop_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.prop_scroll.setFrameShape(QFrame.NoFrame)
        self.prop_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.prop_box = QFrame()
        self.prop_box.setObjectName("stitchPropInspectorBox")
        self.prop_box.setStyleSheet("""
            QFrame#stitchPropInspectorBox {
                background-color: #060e20;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
        """)
        prop_layout = QVBoxLayout(self.prop_box)
        prop_layout.setContentsMargins(8, 8, 8, 8)
        prop_layout.setSpacing(6)

        # 1. Sensor Type Selector (allows switching sensor mapped to element at any time!)
        self.widget_sensor_type = QWidget()
        sensor_type_layout = QHBoxLayout(self.widget_sensor_type)
        sensor_type_layout.setContentsMargins(0, 0, 0, 0)
        sensor_type_layout.addWidget(QLabel("Bağlı Sensör:"))
        self.combo_sensor_type = QComboBox()
        self.combo_sensor_type.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_sensor_type.setMinimumContentsLength(14)
        sensor_options = [
            ("🎮 FPS Göstergesi", "game_fps"),
            ("🌡️ CPU Sıcaklığı", "cpu_temp"),
            ("⚡ CPU Kullanımı (%)", "cpu_load"),
            ("🚀 CPU Frekansı (MHz)", "cpu_clock"),
            ("🌀 CPU Fan Hızı (RPM)", "cpu_fan"),
            ("🔥 GPU Sıcaklığı", "gpu_temp"),
            ("🎮 GPU Kullanımı (%)", "gpu_load"),
            ("🌀 GPU Fan Hızı (%)", "gpu_fan"),
            ("💾 RAM Kullanımı (GB)", "ram_used"),
            ("📊 RAM Kullanımı (%)", "ram_load"),
            ("💾 Kalan / Boş RAM (GB)", "ram_free"),
            ("📊 Kalan / Boş RAM (%)", "ram_free_load"),
            ("💿 Disk Okuma/Yazma (MB/s)", "disk_io"),
            ("⏳ Sistem Açık Kalma Süresi", "system_uptime"),
            ("📥 İndirme Hızı (Download)", "net_down"),
            ("📤 Yükleme Hızı (Upload)", "net_up"),
            ("📶 İnternet Ping (ms)", "net_ping"),
            ("⏰ Dijital Saat", "time_digital"),
            ("📅 Tarih (GG.AA.YYYY)", "date_full"),
            ("🗓️ Türkçe Gün & Tarih", "date_day_tr")
        ]
        for s_lbl, s_key in sensor_options:
            self.combo_sensor_type.addItem(s_lbl, s_key)
        self.combo_sensor_type.currentIndexChanged.connect(self.on_sensor_type_changed)
        sensor_type_layout.addWidget(self.combo_sensor_type, stretch=1)
        prop_layout.addWidget(self.widget_sensor_type)

        # 1.2 RAM Display & Bar Sync Mode Selector (Visible when any RAM sensor is selected!)
        self.widget_ram_mode = QWidget()
        ram_mode_layout = QHBoxLayout(self.widget_ram_mode)
        ram_mode_layout.setContentsMargins(0, 0, 0, 0)
        ram_mode_layout.addWidget(QLabel("💾 RAM Gösterimi:"))
        self.combo_ram_mode = QComboBox()
        self.combo_ram_mode.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_ram_mode.setMinimumContentsLength(14)
        self.combo_ram_mode.setToolTip("RAM ögesinin ve ilerleme çubuğunun (bar) Kullanılan RAM'i mi yoksa Kalan/Boş RAM'i mi göstereceğini seçin")
        ram_mode_options = [
            ("Kullanılan RAM (GB) — Çubuk: Kullanılan %", "used_gb"),
            ("Kullanılan RAM (%) — Çubuk: Kullanılan %", "used_pct"),
            ("Kullanılan RAM (GB + %) — Çubuk: Kullanılan %", "used_both"),
            ("Kalan / Boş RAM (GB) — Çubuk: Kalan %", "free_gb"),
            ("Kalan / Boş RAM (%) — Çubuk: Kalan %", "free_pct"),
            ("Kalan / Boş RAM (GB + %) — Çubuk: Kalan %", "free_both"),
        ]
        for rm_lbl, rm_key in ram_mode_options:
            self.combo_ram_mode.addItem(rm_lbl, rm_key)
        self.combo_ram_mode.currentIndexChanged.connect(self.on_ram_mode_changed)
        ram_mode_layout.addWidget(self.combo_ram_mode, stretch=1)
        prop_layout.addWidget(self.widget_ram_mode)

        # 1.5 Custom Image Layer Picker (Visible when custom_image is selected)
        self.widget_custom_image = QWidget()
        custom_img_layout = QHBoxLayout(self.widget_custom_image)
        custom_img_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_pick_custom_image = QPushButton("🖼️ Özel Görsel / Logo Seç (PNG / WebP / JPG)")
        self.btn_pick_custom_image.setStyleSheet("background: #6366f1; color: white; font-weight: bold; padding: 5px 8px; font-size: 11px;")
        self.btn_pick_custom_image.clicked.connect(self.pick_custom_image_layer)
        custom_img_layout.addWidget(self.btn_pick_custom_image)
        prop_layout.addWidget(self.widget_custom_image)

        # 2. Text / Label Input
        self.widget_txt_lbl = QWidget()
        txt_lbl_layout = QHBoxLayout(self.widget_txt_lbl)
        txt_lbl_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_txt_title = QLabel("Etiket / Başlık:")
        txt_lbl_layout.addWidget(self.lbl_txt_title)
        self.txt_label = QLineEdit()
        self.txt_label.textChanged.connect(self.on_label_changed)
        txt_lbl_layout.addWidget(self.txt_label, stretch=1)
        prop_layout.addWidget(self.widget_txt_lbl)

        # 2.5 Exact Pixel Coordinates & Dimensions (X, Y, W, H — 2x2 Grid so spinboxes never clip)
        self.widget_geom_controls = QWidget()
        geom_layout = QGridLayout(self.widget_geom_controls)
        geom_layout.setContentsMargins(0, 0, 0, 0)
        geom_layout.setHorizontalSpacing(6)
        geom_layout.setVerticalSpacing(4)
        geom_layout.addWidget(QLabel("X:"), 0, 0)
        self.spin_el_x = QSpinBox()
        self.spin_el_x.setRange(0, 4096)
        self.spin_el_x.valueChanged.connect(self.on_element_geom_spin_changed)
        geom_layout.addWidget(self.spin_el_x, 0, 1)

        geom_layout.addWidget(QLabel("Y:"), 0, 2)
        self.spin_el_y = QSpinBox()
        self.spin_el_y.setRange(0, 4096)
        self.spin_el_y.valueChanged.connect(self.on_element_geom_spin_changed)
        geom_layout.addWidget(self.spin_el_y, 0, 3)

        geom_layout.addWidget(QLabel("G:"), 1, 0)
        self.spin_el_w = QSpinBox()
        self.spin_el_w.setRange(20, 4096)
        self.spin_el_w.valueChanged.connect(self.on_element_geom_spin_changed)
        geom_layout.addWidget(self.spin_el_w, 1, 1)

        geom_layout.addWidget(QLabel("Yük:"), 1, 2)
        self.spin_el_h = QSpinBox()
        self.spin_el_h.setRange(16, 4096)
        self.spin_el_h.valueChanged.connect(self.on_element_geom_spin_changed)
        geom_layout.addWidget(self.spin_el_h, 1, 3)
        geom_layout.setColumnStretch(1, 1)
        geom_layout.setColumnStretch(3, 1)
        prop_layout.addWidget(self.widget_geom_controls)

        # 3. Font Family & Size
        self.widget_font_controls = QWidget()
        font_ctrl_layout = QVBoxLayout(self.widget_font_controls)
        font_ctrl_layout.setContentsMargins(0, 0, 0, 0)
        font_ctrl_layout.setSpacing(4)

        font_box = QHBoxLayout()
        font_box.addWidget(QLabel("Font Ailesi:"))
        self.combo_font = QComboBox()
        self.combo_font.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_font.setMinimumContentsLength(12)
        self.combo_font.addItems(["Arial", "Segoe UI", "Consolas", "Impact", "Times New Roman", "Courier New", "Verdana", "Trebuchet MS"])
        self.combo_font.currentIndexChanged.connect(self.on_font_changed)
        font_box.addWidget(self.combo_font, stretch=1)
        font_ctrl_layout.addLayout(font_box)

        style_box = QHBoxLayout()
        self.chk_bold = QCheckBox("Kalın (Bold)")
        self.chk_bold.stateChanged.connect(self.on_style_changed)
        style_box.addWidget(self.chk_bold)

        self.chk_italic = QCheckBox("İtalik")
        self.chk_italic.stateChanged.connect(self.on_style_changed)
        style_box.addWidget(self.chk_italic)
        style_box.addStretch()

        font_ctrl_layout.addLayout(style_box)

        size_box = QHBoxLayout()
        size_box.setSpacing(6)
        size_box.addWidget(QLabel("Etiket:"))
        self.spin_fsize = QSpinBox()
        self.spin_fsize.setRange(8, 250)
        self.spin_fsize.valueChanged.connect(self.on_fsize_changed)
        size_box.addWidget(self.spin_fsize, stretch=1)

        size_box.addWidget(QLabel("Değer:"))
        self.spin_val_fsize = QSpinBox()
        self.spin_val_fsize.setRange(8, 250)
        self.spin_val_fsize.valueChanged.connect(self.on_val_fsize_changed)
        size_box.addWidget(self.spin_val_fsize, stretch=1)
        font_ctrl_layout.addLayout(size_box)

        align_row = QHBoxLayout()
        align_row.setSpacing(6)
        align_row.addWidget(QLabel("Hiza:"))
        self.combo_align = QComboBox()
        self.combo_align.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_align.setMinimumContentsLength(10)
        self.combo_align.addItems(["Sol (left)", "Orta (center)", "Sağ (right)"])
        self.combo_align.currentIndexChanged.connect(self.on_align_changed)
        align_row.addWidget(self.combo_align, stretch=1)
        font_ctrl_layout.addLayout(align_row)

        prop_layout.addWidget(self.widget_font_controls)

        # 3.5 Border Visibility, Corner Radius & Neon Glow Option (2 rows so checkboxes & spinbox never clip)
        self.widget_border_option = QWidget()
        border_opt_vbox = QVBoxLayout(self.widget_border_option)
        border_opt_vbox.setContentsMargins(0, 0, 0, 0)
        border_opt_vbox.setSpacing(4)
        border_opt_row1 = QHBoxLayout()
        border_opt_row1.setSpacing(8)
        self.chk_border = QCheckBox("🔲 Çerçeve")
        self.chk_border.stateChanged.connect(self.on_style_changed)
        border_opt_row1.addWidget(self.chk_border)

        self.chk_glow = QCheckBox("✨ Neon Glow")
        self.chk_glow.setToolTip("Kutu etrafına yumuşak neon ışık halesi ekler")
        self.chk_glow.stateChanged.connect(self.on_style_changed)
        border_opt_row1.addWidget(self.chk_glow)
        border_opt_row1.addStretch()
        border_opt_vbox.addLayout(border_opt_row1)

        border_opt_row2 = QHBoxLayout()
        border_opt_row2.setSpacing(6)
        border_opt_row2.addWidget(QLabel("Köşe Yuvarlatma:"))
        self.spin_corner_radius = QSpinBox()
        self.spin_corner_radius.setRange(0, 60)
        self.spin_corner_radius.setSuffix(" px")
        self.spin_corner_radius.setToolTip("Kutu ve çerçeve köşelerini yuvarlatır (0 = Keskin)")
        self.spin_corner_radius.valueChanged.connect(self.on_corner_radius_changed)
        border_opt_row2.addWidget(self.spin_corner_radius, stretch=1)
        border_opt_vbox.addLayout(border_opt_row2)
        prop_layout.addWidget(self.widget_border_option)

        # 4. Color Buttons
        self.widget_colors = QWidget()
        color_layout = QHBoxLayout(self.widget_colors)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.setSpacing(4)
        self.btn_txt_col = QPushButton("🎨 Yazı")
        self.btn_txt_col.clicked.connect(self.pick_text_color)
        color_layout.addWidget(self.btn_txt_col, stretch=1)

        self.btn_pct_col = QPushButton("🎨 Değer")
        self.btn_pct_col.clicked.connect(self.pick_percent_color)
        color_layout.addWidget(self.btn_pct_col, stretch=1)

        self.btn_gfx_col = QPushButton("🎨 Grafik")
        self.btn_gfx_col.clicked.connect(self.pick_graphic_color)
        color_layout.addWidget(self.btn_gfx_col, stretch=1)
        prop_layout.addWidget(self.widget_colors)

        # 5. Dynamic Threshold Colors
        self.widget_dynamic_col = QWidget()
        dynamic_col_layout = QHBoxLayout(self.widget_dynamic_col)
        dynamic_col_layout.setContentsMargins(0, 0, 0, 0)
        dynamic_col_layout.setSpacing(6)
        self.chk_dynamic_color = QCheckBox("🎨 Dinamik Renk")
        self.chk_dynamic_color.stateChanged.connect(self.on_dynamic_color_toggle)
        dynamic_col_layout.addWidget(self.chk_dynamic_color)

        self.btn_custom_thresholds = QPushButton("⚙️ Renk Eşikleri")
        self.btn_custom_thresholds.setStyleSheet("background: #6366f1; color: white; font-weight: bold; padding: 5px 8px; font-size: 11px;")
        self.btn_custom_thresholds.clicked.connect(self.open_threshold_settings)
        dynamic_col_layout.addWidget(self.btn_custom_thresholds, stretch=1)
        prop_layout.addWidget(self.widget_dynamic_col)

        # 3.7 Animation & Breathing Effects
        self.widget_anim_effects = QWidget()
        anim_eff_layout = QHBoxLayout(self.widget_anim_effects)
        anim_eff_layout.setContentsMargins(0, 0, 0, 0)
        anim_eff_layout.setSpacing(6)
        anim_eff_layout.addWidget(QLabel("✨ Efekt:"))
        self.combo_anim_effect = QComboBox()
        self.combo_anim_effect.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_anim_effect.setMinimumContentsLength(10)
        self.combo_anim_effect.addItem("Sabit (Kapalı)", "none")
        self.combo_anim_effect.addItem("💨 Nefes Alma (Pulse)", "pulse")
        self.combo_anim_effect.addItem("🌈 RGB Rainbow Spektrum", "rainbow")
        self.combo_anim_effect.addItem("⚡ Yanıp Sönme (Flash)", "flash")
        self.combo_anim_effect.addItem("✨ Neon Parıltı", "neon")
        self.combo_anim_effect.currentIndexChanged.connect(self.on_anim_effect_changed)
        anim_eff_layout.addWidget(self.combo_anim_effect, stretch=1)

        anim_eff_layout.addWidget(QLabel("Hız:"))
        self.spin_anim_speed = QSpinBox()
        self.spin_anim_speed.setRange(1, 10)
        self.spin_anim_speed.setValue(5)
        self.spin_anim_speed.valueChanged.connect(self.on_anim_speed_changed)
        anim_eff_layout.addWidget(self.spin_anim_speed)
        prop_layout.addWidget(self.widget_anim_effects)

        # 3.8 Countdown Date/Time Picker
        self.widget_countdown_settings = QWidget()
        cd_layout = QHBoxLayout(self.widget_countdown_settings)
        cd_layout.setContentsMargins(0, 0, 0, 0)
        cd_layout.addWidget(QLabel("🗓️ Hedef Tarih:"))
        self.date_event_target = QDateTimeEdit()
        self.date_event_target.setCalendarPopup(True)
        self.date_event_target.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.date_event_target.setDateTime(QDateTime.currentDateTime().addDays(90))
        self.date_event_target.dateTimeChanged.connect(self.on_countdown_date_changed)
        cd_layout.addWidget(self.date_event_target, stretch=1)
        prop_layout.addWidget(self.widget_countdown_settings)

        # 3.9 Weather Location Settings
        self.widget_weather_settings = QWidget()
        w_loc_layout = QHBoxLayout(self.widget_weather_settings)
        w_loc_layout.setContentsMargins(0, 0, 0, 0)
        w_loc_layout.setSpacing(6)
        w_loc_layout.addWidget(QLabel("📍 Konum/İlçe:"))
        self.txt_weather_loc = QLineEdit()
        self.txt_weather_loc.setPlaceholderText("Örn: Çorlu, Kadıköy")
        self.txt_weather_loc.textChanged.connect(self.on_weather_loc_changed)
        w_loc_layout.addWidget(self.txt_weather_loc, stretch=1)
        self.btn_auto_loc = QPushButton("🎯 Otomatik")
        self.btn_auto_loc.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 4px 8px; font-size: 11px;")
        self.btn_auto_loc.clicked.connect(self.on_auto_weather_loc_clicked)
        w_loc_layout.addWidget(self.btn_auto_loc)
        prop_layout.addWidget(self.widget_weather_settings)

        # 6. Granular Marquee Builder Button
        self.btn_custom_marquee = QPushButton("📜 Kayan Yazı İçeriklerini Seç")
        self.btn_custom_marquee.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 5px 8px; font-size: 11px;")
        self.btn_custom_marquee.clicked.connect(self.open_marquee_customizer)
        prop_layout.addWidget(self.btn_custom_marquee)

        # 7. Box Background & Opacity
        self.widget_bg_box = QWidget()
        bg_col_layout = QHBoxLayout(self.widget_bg_box)
        bg_col_layout.setContentsMargins(0, 0, 0, 0)
        bg_col_layout.setSpacing(6)
        bg_col_layout.addWidget(QLabel("Arka Plan:"))
        self.btn_bg_col = QPushButton("🎨 Renk")
        self.btn_bg_col.clicked.connect(self.pick_bg_color)
        bg_col_layout.addWidget(self.btn_bg_col)

        bg_col_layout.addWidget(QLabel("Opaklık (%):"))
        self.slider_bg_opacity = QSlider(Qt.Horizontal)
        self.slider_bg_opacity.setRange(0, 100)
        self.slider_bg_opacity.valueChanged.connect(self.on_bg_opacity_changed)
        bg_col_layout.addWidget(self.slider_bg_opacity, stretch=1)
        prop_layout.addWidget(self.widget_bg_box)

        # 8. Deselect Button
        btn_deselect = QPushButton("❌ Seçimi Kaldır")
        btn_deselect.setStyleSheet("background: #334155; color: #94a3b8; font-weight: 600; margin-top: 4px; padding: 5px 8px;")
        btn_deselect.clicked.connect(self.deselect_element)
        prop_layout.addWidget(btn_deselect)

        self.prop_scroll.setWidget(self.prop_box)
        right_layout.addWidget(self.prop_scroll, stretch=1)
        self.prop_scroll.setVisible(False)
        self.prop_box.setVisible(False) # Default hidden if nothing is selected!

        splitter.addWidget(right_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([315, 420, 365])
        studio_vbox.addWidget(splitter, stretch=1)
        shell_body.addWidget(right_studio_container, stretch=1)
        main_layout.addLayout(shell_body, stretch=1)

        self.refresh_elements_list()
        if self.theme_data.get('elements') and self.selected_element_idx is None:
            self.select_element_by_index(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'canvas_widget') and hasattr(self.canvas_widget, 'update_geometry_for_theme'):
            self.canvas_widget.update_geometry_for_theme()

    def auto_adjust_window_to_canvas(self, tw=None, th=None):
        """
        📐 Automatically adjusts the main studio window size to fit the currently selected
        canvas resolution/aspect ratio (e.g. compact narrow window for 320x1480 vertical strip,
        wider window for 1920x1080 landscape), while keeping the window freely resizable by hand.
        """
        try:
            if tw is None:
                tw = max(64, int(self.theme_data.get('width', 320)))
            if th is None:
                th = max(64, int(self.theme_data.get('height', 1480)))
            ratio = float(tw) / max(1.0, float(th))

            # Ideal window dimensions depending on canvas aspect ratio:
            # Left rail (232) + Left panel (310) + Center stage (360+) + Right inspector (355) + margins (~40) = ~1300 px
            if ratio <= 0.35:
                # Tall vertical strip (e.g. 320x1480, 480x1920) -> compact width, tall height
                target_w, target_h = 1310, 860
            elif ratio < 0.85:
                # Portrait 9:16 (e.g. 1080x1920) -> medium width, tall height
                target_w, target_h = 1380, 860
            elif ratio <= 1.25:
                # Square-ish
                target_w, target_h = 1420, 840
            elif ratio <= 2.2:
                # Standard 16:9 / 16:10 Landscape (e.g. 1920x1080, 1024x600, 800x480)
                target_w, target_h = 1540, 840
            else:
                # Ultra-wide horizontal strip (e.g. 1920x480, 1280x400)
                target_w, target_h = 1580, 780

            screen = QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                if avail.width() >= 1024 and avail.height() >= 720:
                    target_w = min(target_w, max(1180, avail.width() - 30))
                    target_h = min(target_h, max(640, avail.height() - 30))

            if not self.isMaximized() and not self.isFullScreen():
                self.resize(int(target_w), int(target_h))

            if hasattr(self, 'main_splitter'):
                avail_split_w = max(900, int(target_w) - 255)
                lw = max(310, int(avail_split_w * 0.27))
                rw = max(355, int(avail_split_w * 0.31))
                cw = max(360, avail_split_w - lw - rw)
                self.main_splitter.setSizes([lw, cw, rw])

            QTimer.singleShot(25, self.update_canvas_geometry)
        except Exception as e:
            print("auto_adjust_window_to_canvas note:", e)

    def open_buy_me_a_coffee(self):
        """☕ Opens the developer's GitHub Sponsors / Buy Me a Coffee support page in the user's browser."""
        try:
            QDesktopServices.openUrl(QUrl(SPONSOR_URL))
        except Exception as e:
            print("open_buy_me_a_coffee error:", e)

    def start_update_check(self, silent=True):
        """🔄 Checks GitHub for a newer version and automatically installs it if available."""
        try:
            if getattr(self, '_update_worker', None) is not None and self._update_worker.isRunning():
                return
            self._update_worker = AutoUpdateWorker(silent=silent, parent=self)
            self._update_worker.update_result_signal.connect(
                lambda status, remote_ver, msg, s=silent: self.on_auto_update_result(status, remote_ver, msg, s)
            )
            self._update_worker.start()
        except Exception as e:
            print("start_update_check note:", e)

    def on_auto_update_result(self, status, remote_ver, msg, silent=True):
        try:
            lang = str(self.app_settings.get('language', 'tr')).lower()
            if status == 'updated':
                title = "✅ Otomatik Güncelleme Tamamlandı" if lang != 'en' else "✅ Auto-Update Installed"
                body = (
                    f"{msg}\n\nYeni sürümün (v{remote_ver}) etkinleşmesi için uygulama şimdi yeniden başlatılsın mı?"
                    if lang != 'en' else
                    f"{msg}\n\nWould you like to restart the application now to activate v{remote_ver}?"
                )
                ans = QMessageBox.question(self, title, body, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if ans == QMessageBox.Yes:
                    self.restart_application()
            elif status == 'exe_update_available':
                title = "🆕 Yeni Sürüm Mevcut" if lang != 'en' else "🆕 New Version Available"
                body = (
                    f"Yeni bir güncelleme (v{remote_ver}) yayınlandı!\n\nİndirme sayfasını şimdi açmak ister misiniz?"
                    if lang != 'en' else
                    f"A new update (v{remote_ver}) is available!\n\nWould you like to open the download page now?"
                )
                ans = QMessageBox.question(self, title, body, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if ans == QMessageBox.Yes:
                    QDesktopServices.openUrl(QUrl("https://github.com/blackxtr-lang/cyberpulse-lcd-studio/releases/latest"))
            elif not silent:
                if status == 'up_to_date':
                    title = "✅ Güncel Sürüm" if lang != 'en' else "✅ Up to Date"
                    QMessageBox.information(self, title, msg)
                else:
                    title = "⚠️ Güncelleme Denetimi" if lang != 'en' else "⚠️ Update Check"
                    QMessageBox.warning(self, title, msg)
        except Exception as e:
            print("on_auto_update_result note:", e)

    def restart_application(self):
        """Safely saves state and restarts the application process after an auto-update."""
        try:
            self.save_theme_to_disk()
            self.save_screen_workspaces_to_disk()
            self.save_app_settings()
            if getattr(sys, 'frozen', False):
                exe_path = os.path.abspath(sys.executable)
                subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
            else:
                python_exe = os.path.abspath(sys.executable)
                script_path = os.path.abspath(__file__)
                subprocess.Popen([python_exe, script_path], cwd=os.path.dirname(script_path))
            QApplication.quit()
        except Exception as e:
            print("restart_application error:", e)

    def toggle_app_language(self):
        curr = str(self.app_settings.get('language', 'tr')).lower()
        new_lang = 'en' if curr == 'tr' else 'tr'
        self.app_settings['language'] = new_lang
        self.save_app_settings()
        self.apply_current_language()

    def apply_current_language(self):
        try:
            lang = str(self.app_settings.get('language', 'tr')).lower()
            if hasattr(self, 'btn_rail_lang'):
                lbl = "🌐  Language: EN 🇬🇧" if lang == 'en' else "🌐  Dil: TR 🇹🇷"
                self.btn_rail_lang.setProperty("_cp_orig_tr_text", lbl)
                self.btn_rail_lang.setText(lbl)
            apply_language_to_widget_tree(self, lang)
        except Exception as e:
            print("apply_current_language note:", e)

    def apply_full_layout_to_all_themes(self):
        """
        🔄 Applies the current screen's elements and layout ONLY to saved preset themes that have
        the exact same resolution (width × height) as the currently active screen workspace.
        """
        try:
            curr_w = max(64, int(self.theme_data.get('width', 320)))
            curr_h = max(64, int(self.theme_data.get('height', 1480)))
            themes_list = get_all_preset_themes()
            matching_themes = [
                t for t in themes_list
                if int(t.get('width', 320)) == curr_w and int(t.get('height', 1480)) == curr_h
            ]

            if not matching_themes:
                QMessageBox.information(
                    self,
                    "Bu Çözünürlükte Kayıtlı Tema Yok",
                    f"Arşivinizde şu an aktif ekran çözünürlüğünüz olan {curr_w}×{curr_h} boyutunda kayıtlı bir şablon tema bulunamadı.\n\n"
                    f"Önce '💾 Şablona Kaydet' butonuyla {curr_w}×{curr_h} çözünürlüğünde tema kaydedebilirsiniz."
                )
                return

            reply = QMessageBox.question(
                self,
                f"🔄 Düzeni {curr_w}×{curr_h} Çözünürlükteki Temalara Uygula",
                f"Mevcut ekrandaki ({curr_w}×{curr_h}) TÜM ÖĞELER, KONUMLAR ve DÜZEN,\n"
                f"arşivinizde yalnızca aynı çözünürlüğe ({curr_w}×{curr_h}) sahip {len(matching_themes)} adet kayıtlı temaya aktarılacaktır.\n\n"
                f"(Farklı çözünürlükteki temalarınız hiçbir şekilde değiştirilmeyecektir.)\n\n"
                f"Devam etmek istiyor musunuz?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply != QMessageBox.Yes:
                return

            self.save_theme_to_disk()

            current_elements = json.loads(json.dumps(self.theme_data.get('elements', [])))
            refresh_sec = self.theme_data.get('refresh_sec', 1.0)
            rotation = self.theme_data.get('rotation', 180)
            thermal_limit = self.theme_data.get('thermal_alert_limit', 82)

            updated_count = 0
            updated_names_lower = set()

            prev_cropping = getattr(self, 'is_cropping', False)
            self.is_cropping = True
            try:
                # Release any open cv2.VideoCapture handles on .cptheme files before atomic metadata replacement on Windows
                if hasattr(self, 'hardware') and self.hardware:
                    self.hardware.reset_background_media()
                for ws in list(getattr(self, 'screen_workspaces', {}).values()):
                    hw = ws.get('hardware')
                    if hw:
                        hw.reset_background_media()

                for t_item in matching_themes:
                    try:
                        t_json = load_preset_theme_data(t_item)
                        if not t_json or not isinstance(t_json, dict):
                            continue

                        tw = int(t_json.get('width', 320) or 320)
                        th = int(t_json.get('height', 1480) or 1480)
                        if tw != curr_w or th != curr_h:
                            continue

                        t_json['elements'] = json.loads(json.dumps(current_elements))
                        t_json['refresh_sec'] = refresh_sec
                        t_json['rotation'] = rotation
                        t_json['thermal_alert_limit'] = thermal_limit

                        if t_item.get('is_cptheme') and t_item.get('cptheme_path'):
                            if hasattr(self, 'hardware') and self.hardware:
                                self.hardware.reset_background_media()
                            for ws in list(getattr(self, 'screen_workspaces', {}).values()):
                                hw = ws.get('hardware')
                                if hw:
                                    hw.reset_background_media()
                            if update_cptheme_metadata(t_item['cptheme_path'], t_json):
                                updated_count += 1
                                updated_names_lower.add(str(t_item.get('name', '')).strip().lower())
                        else:
                            f_path = t_item.get('json_path')
                            if f_path and _is_safe_local_file_path(f_path) and os.path.exists(f_path):
                                tmp_f = f_path + ".tmp"
                                with open(tmp_f, 'w', encoding='utf-8') as f:
                                    json.dump(t_json, f, ensure_ascii=False, indent=2)
                                os.replace(tmp_f, f_path)
                                updated_count += 1
                                updated_names_lower.add(str(t_item.get('name', '')).strip().lower())
                    except Exception as ex:
                        print(f"Theme batch sync note for {t_item.get('name')}:", ex)
            finally:
                self.is_cropping = prev_cropping

            # Also sync any in-memory screen workspaces that have the same resolution and one of those themes loaded
            for sid, ws in list(getattr(self, 'screen_workspaces', {}).items()):
                if sid == getattr(self, 'active_screen_slot_id', ''):
                    continue
                ws_td = ws.get('theme_data')
                if isinstance(ws_td, dict):
                    w_tw = int(ws_td.get('width', 320))
                    w_th = int(ws_td.get('height', 1480))
                    w_name = str(ws_td.get('name', '')).strip().lower()
                    if w_tw == curr_w and w_th == curr_h and (not updated_names_lower or w_name in updated_names_lower):
                        ws_td['elements'] = json.loads(json.dumps(current_elements))
                        ws_td['refresh_sec'] = refresh_sec
                        ws_td['rotation'] = rotation
                        ws_td['thermal_alert_limit'] = thermal_limit

            self.save_screen_workspaces_to_disk()

            QMessageBox.information(
                self,
                "✅ Başarıyla Senkronize Edildi!",
                f"Tebrikler! Mevcut ekran düzeniniz ve tüm öğeleriniz {curr_w}×{curr_h} çözünürlüğündeki {updated_count} adet temanın tamamına başarıyla aktarıldı!"
            )
        except Exception as e:
            QMessageBox.critical(self, "Senkronizasyon Hatası", f"Düzen temalara aktarılırken bir hata oluştu: {e}")

    def open_theme_manager(self):
        dlg = ThemePresetManagerDialog(self)
        dlg.exec_()

    def open_app_settings(self):
        dlg = AppSettingsDialog(self)
        dlg.exec_()

    def open_marquee_customizer(self):
        if self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(self.theme_data['elements']):
            el = self.theme_data['elements'][self.selected_element_idx]
            dlg = MarqueeCustomizerDialog(self, el)
            dlg.exec_()

    def open_threshold_settings(self):
        if self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(self.theme_data['elements']):
            el = self.theme_data['elements'][self.selected_element_idx]
            dlg = ThresholdSettingsDialog(self, el)
            dlg.exec_()

    def select_background_media(self):
        path, _ = QFileDialog.getOpenFileName(self, "Arka Plan Görseli veya Videosu Seç", "", "Medya Dosyaları (*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.avi *.mkv *.mov)")
        if path:
            self.hardware.reset_background_media()
            self.theme_data['bg_path'] = path
            self.lbl_bg_info.setText(f"Arka Plan: {os.path.basename(path)[:24]}")
            self.save_theme_to_disk()
            self.open_media_crop_dialog()

    def open_media_crop_dialog(self):
        bg_path = self.theme_data.get('bg_path')
        if not bg_path or not os.path.exists(bg_path):
            QMessageBox.warning(self, "Medya Yok", "Lütfen önce bir resim veya video arka planı seçin.")
            return

        dlg = MediaCropDialog(self, bg_path, crop_rect=self.theme_data.get('crop_rect'), fit_to_screen=self.theme_data.get('fit_to_screen', False))
        dlg.exec_()

    def save_theme_to_preset_folder(self):
        tname, ok = QInputDialog.getText(self, "Şablon Olarak Kaydet", "Tema Adı:")
        if ok and tname.strip():
            clean_name = tname.strip()
            ok_bake, msg = bake_and_save_preset_theme(self, clean_name)
            if ok_bake:
                QMessageBox.information(self, "Başarılı", f"Tema '{clean_name}' optimize edilip şablon klasörüne kaydedildi!")
            else:
                QMessageBox.warning(self, "Hata", f"Tema kaydedilemedi: {msg}")

    def on_refresh_speed_changed(self, val):
        self.theme_data['refresh_sec'] = float(val)
        self.save_theme_to_disk()

    def on_rotation_changed(self, idx):
        rotations = [180, 0, 90, 270]
        self.theme_data['rotation'] = rotations[idx]
        self.save_theme_to_disk()

    # ==========================================================
    # ↩️ PHASE 2: UNDO / REDO HISTORY ENGINE
    # ==========================================================
    def push_undo_state(self, action_label="Düzenleme"):
        try:
            snap = json.loads(json.dumps(self.theme_data.get('elements', [])))
            if self.undo_stack and self.undo_stack[-1]['elements'] == snap:
                return
            self.undo_stack.append({
                'label': action_label,
                'elements': snap,
                'selected_idx': self.selected_element_idx,
                'selected_indices': list(self.selected_element_indices)
            })
            if len(self.undo_stack) > 50:
                self.undo_stack.pop(0)
            self.redo_stack.clear()
            self.update_undo_redo_ui()
        except Exception as e:
            print("Push undo note:", e)

    def undo_action(self):
        if not self.undo_stack:
            return
        try:
            current_snap = {
                'label': 'Redo',
                'elements': json.loads(json.dumps(self.theme_data.get('elements', []))),
                'selected_idx': self.selected_element_idx,
                'selected_indices': list(self.selected_element_indices)
            }
            self.redo_stack.append(current_snap)
            prev = self.undo_stack.pop()
            self.theme_data['elements'] = prev['elements']
            self.selected_element_indices = set(prev.get('selected_indices', []))
            self.refresh_elements_list()
            prev_idx = prev.get('selected_idx')
            if prev_idx is not None and 0 <= prev_idx < len(self.theme_data['elements']):
                self.select_element_by_index(prev_idx, clear_others=False)
            else:
                self.deselect_element()
            self.update_undo_redo_ui()
            self.save_theme_to_disk()
        except Exception as e:
            print("Undo error:", e)

    def redo_action(self):
        if not self.redo_stack:
            return
        try:
            current_snap = {
                'label': 'Undo',
                'elements': json.loads(json.dumps(self.theme_data.get('elements', []))),
                'selected_idx': self.selected_element_idx,
                'selected_indices': list(self.selected_element_indices)
            }
            self.undo_stack.append(current_snap)
            nxt = self.redo_stack.pop()
            self.theme_data['elements'] = nxt['elements']
            self.selected_element_indices = set(nxt.get('selected_indices', []))
            self.refresh_elements_list()
            nxt_idx = nxt.get('selected_idx')
            if nxt_idx is not None and 0 <= nxt_idx < len(self.theme_data['elements']):
                self.select_element_by_index(nxt_idx, clear_others=False)
            else:
                self.deselect_element()
            self.update_undo_redo_ui()
            self.save_theme_to_disk()
        except Exception as e:
            print("Redo error:", e)

    def update_undo_redo_ui(self):
        if hasattr(self, 'btn_undo'):
            self.btn_undo.setEnabled(len(self.undo_stack) > 0)
            self.btn_undo.setText(f"↩️ Geri Al ({len(self.undo_stack)})" if self.undo_stack else "↩️ Geri Al")
        if hasattr(self, 'btn_redo'):
            self.btn_redo.setEnabled(len(self.redo_stack) > 0)
            self.btn_redo.setText(f"↪️ İleri Al ({len(self.redo_stack)})" if self.redo_stack else "↪️ İleri Al")

    def add_sensor_element(self, item):
        if not item:
            return
        self.push_undo_state("Öge Ekle")
        data = item.data(Qt.UserRole)
        new_id = f"el_{int(time.time()*1000) % 10000}"

        tw = max(64, int(self.theme_data.get('width', 320)))
        th = max(64, int(self.theme_data.get('height', 1480)))
        is_landscape = (tw > th)
        scale_f = max(1.0, min(2.2, th / 720.0)) if is_landscape else max(0.85, min(2.0, tw / 320.0))

        el_type = data.get('type', 'sensor')
        auto_w, auto_h = int(260 * scale_f), int(48 * scale_f)
        if el_type in ['animated_fan', 'circle_gauge']:
            side = int(180 * scale_f)
            auto_w, auto_h = side, side
        elif el_type == 'vertical_gauge':
            auto_w, auto_h = int(64 * scale_f), int(280 * scale_f)
        elif el_type == 'sparkline_graph':
            auto_w, auto_h = int(300 * scale_f), int(105 * scale_f)
        elif el_type == 'custom_image':
            side = int(140 * scale_f)
            auto_w, auto_h = side, side
        elif el_type in ['box', 'music_player']:
            auto_w, auto_h = int(300 * scale_f), int((80 if el_type == 'music_player' else 130) * scale_f)
        elif el_type in ['weather_widget', 'event_countdown']:
            auto_w, auto_h = int(280 * scale_f), int(70 * scale_f)
        elif el_type == 'ping_monitor':
            auto_w, auto_h = int(280 * scale_f), int(78 * scale_f)
        elif el_type == 'marquee' and is_landscape:
            auto_w, auto_h = max(320, int(tw * 0.6)), int(56 * scale_f)

        auto_w = min(tw - 20, max(40, auto_w))
        auto_h = min(th - 20, max(24, auto_h))
        idx_cnt = len(self.theme_data.get('elements', []))
        if is_landscape:
            start_x = min(max(0, tw - auto_w), 40 + (idx_cnt % 3) * max(160, (tw - 80) // 3))
            start_y = min(max(0, th - auto_h), 80 + ((idx_cnt // 3) * (auto_h + 24)) % max(120, th - 120))
        else:
            start_x = min(max(0, tw - auto_w), 30)
            start_y = min(max(0, th - auto_h), 100 + (idx_cnt * 24) % max(100, th - 140))

        new_el = {
            'id': new_id,
            'type': el_type,
            'sensorId': data['sensorId'],
            'label': data['label'] if el_type != 'event_countdown' else 'GTA 6 ÇIKIŞI',
            'targetTimestamp': time.time() + (90 * 86400),
            'animEffect': 'none',
            'animSpeed': 5,
            'x': start_x,
            'y': start_y,
            'width': auto_w,
            'height': auto_h,
            'textColor': '#ffffff',
            'percentColor': '#38bdf8',
            'graphicColor': '#38bdf8',
            'bgColor': '#0f172a',
            'bgOpacity': 0 if el_type == 'custom_image' else 50,
            'cornerRadius': 8 if el_type == 'sparkline_graph' else 0,
            'glowEnabled': False,
            'fontSize': max(12, int(round(18 * scale_f))),
            'valueFontSize': max(16, int(round(24 * scale_f))),
            'fontFamily': 'Arial',
            'isBold': True,
            'isItalic': False,
            'textAlign': 'left',
            'showBorder': False if el_type == 'custom_image' else True,
            'dynamicColor': False,
            'tLowPct': 50,
            'tHighPct': 80,
            'tLowColor': '#10b981',
            'tMidColor': '#fbbf24',
            'tHighColor': '#ef4444',
            'marquee_items': ['cpu_spec', 'gpu_spec', 'ram_spec', 'cpu_temp', 'gpu_temp', 'game_fps', 'net_down', 'net_up', 'net_ping']
        }
        self.theme_data['elements'].append(new_el)
        self.refresh_elements_list()
        self.select_element_by_index(len(self.theme_data['elements']) - 1)
        self.save_theme_to_disk()
        if el_type == 'custom_image':
            self.pick_custom_image_layer()

    def refresh_elements_list(self):
        self.element_list.clear()
        els = self.theme_data.get('elements', [])
        if hasattr(self, 'lbl_layer_stack_hdr'):
            self.lbl_layer_stack_hdr.setText(f"KATMANLAR ({len(els)} ÖGE)")
        for idx, el in enumerate(els):
            badges = ""
            if el.get('locked', False):
                badges += "🔒 "
            if el.get('hidden', False):
                badges += "👁️‍🗨️ "
            el_type_tag = str(el.get('type', 'sensor')).upper()
            el_lbl_str = str(el.get('label') or el.get('sensorId') or '').strip()
            coords_tag = f"({int(el.get('x', 0))},{int(el.get('y', 0))})"
            lbl = f"[{idx+1:02d}] {badges}{el_type_tag} - {el_lbl_str}  {coords_tag}"
            item = QListWidgetItem(lbl)
            item.setData(Qt.UserRole, idx)
            if el.get('hidden', False):
                item.setForeground(QColor("#64748b"))
            elif el.get('locked', False):
                item.setForeground(QColor("#fbbf24"))
            self.element_list.addItem(item)

        if self.selected_element_idx is not None and 0 <= self.selected_element_idx < self.element_list.count():
            self.element_list.setCurrentRow(self.selected_element_idx)
        if hasattr(self, 'apply_current_language'):
            self.apply_current_language()

    def _sync_multi_selection_ids(self):
        els = self.theme_data.get('elements', [])
        valid_indices = {i for i in self.selected_element_indices if 0 <= i < len(els)}
        self.selected_element_indices = valid_indices
        self.theme_data['selected_ids'] = [els[i].get('id') for i in sorted(valid_indices) if els[i].get('id')]

    def deselect_element(self):
        """
        ❌ Clears selection when no element is selected or clicked empty canvas area.
        Hides property editor and shows clean empty placeholder!
        """
        self.selected_element_idx = None
        self.selected_element_indices.clear()
        self.theme_data['selected_id'] = None
        self.theme_data['selected_ids'] = []
        self.element_list.clearSelection()
        if hasattr(self, 'prop_scroll'):
            self.prop_scroll.setVisible(False)
        self.prop_box.setVisible(False)
        self.lbl_empty_prop.setVisible(True)
        self.save_theme_to_disk()

    def select_element_by_index(self, idx, clear_others=True):
        if 0 <= idx < len(self.theme_data['elements']):
            self.selected_element_idx = idx
            if clear_others:
                self.selected_element_indices = {idx}
            else:
                self.selected_element_indices.add(idx)
            self.theme_data['selected_id'] = self.theme_data['elements'][idx]['id']
            self._sync_multi_selection_ids()
            self.element_list.setCurrentRow(idx)
            self.lbl_empty_prop.setVisible(False)
            if hasattr(self, 'prop_scroll'):
                self.prop_scroll.setVisible(True)
            self.prop_box.setVisible(True)
            el = self.theme_data['elements'][idx]
            if hasattr(self, 'btn_lock_el'):
                self.btn_lock_el.setText("🔓" if el.get('locked', False) else "🔒")
            if hasattr(self, 'btn_hide_el'):
                self.btn_hide_el.setText("🚫" if el.get('hidden', False) else "👁️")
            self.load_element_properties(el)
            self.save_theme_to_disk()
        else:
            self.deselect_element()

    def toggle_element_multi_selection(self, idx):
        if not (0 <= idx < len(self.theme_data['elements'])):
            return
        if idx in self.selected_element_indices:
            self.selected_element_indices.discard(idx)
            if self.selected_element_idx == idx:
                self.selected_element_idx = next(iter(self.selected_element_indices), None)
        else:
            self.selected_element_indices.add(idx)
            self.selected_element_idx = idx

        if self.selected_element_idx is not None:
            self.select_element_by_index(self.selected_element_idx, clear_others=False)
        else:
            self.deselect_element()

    def set_multi_selection(self, indices):
        valid = [i for i in indices if 0 <= i < len(self.theme_data['elements'])]
        if not valid:
            self.deselect_element()
            return
        self.selected_element_indices = set(valid)
        self.select_element_by_index(valid[-1], clear_others=False)

    def on_element_selected(self, item):
        if item:
            idx = item.data(Qt.UserRole)
            mods = QApplication.keyboardModifiers()
            if mods & (Qt.ControlModifier | Qt.ShiftModifier):
                self.toggle_element_multi_selection(idx)
            else:
                self.select_element_by_index(idx, clear_others=True)
        else:
            self.deselect_element()

    # ==========================================================
    # 📐 PHASE 2: NUDGE, ALIGN, DISTRIBUTE, LAYER, LOCK & HIDE
    # ==========================================================
    def nudge_selected_elements(self, dx, dy):
        targets = self.selected_element_indices if self.selected_element_indices else (
            {self.selected_element_idx} if self.selected_element_idx is not None else set()
        )
        if not targets:
            return
        self.push_undo_state("Ok Tuşu İle Kaydır")
        cw = self.theme_data.get('width', 320)
        ch = self.theme_data.get('height', 1480)
        els = self.theme_data.get('elements', [])
        for i in targets:
            if 0 <= i < len(els) and not els[i].get('locked', False):
                el = els[i]
                w, h = el.get('width', 200), el.get('height', 45)
                el['x'] = int(max(0, min(cw - w, el.get('x', 0) + dx)))
                el['y'] = int(max(0, min(ch - h, el.get('y', 0) + dy)))
        self.save_theme_to_disk()

    def align_selected_elements(self, mode):
        els = self.theme_data.get('elements', [])
        targets = sorted(i for i in self.selected_element_indices if 0 <= i < len(els) and not els[i].get('locked', False))
        if not targets and self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(els):
            if not els[self.selected_element_idx].get('locked', False):
                targets = [self.selected_element_idx]
        if not targets:
            return

        self.push_undo_state(f"Hizala ({mode})")
        cw = self.theme_data.get('width', 320)
        ch = self.theme_data.get('height', 1480)

        if len(targets) == 1:
            el = els[targets[0]]
            w, h = el.get('width', 200), el.get('height', 45)
            if mode == 'left':
                el['x'] = 20
            elif mode == 'hcenter':
                el['x'] = int((cw - w) // 2)
            elif mode == 'right':
                el['x'] = max(0, cw - 20 - w)
            elif mode == 'vcenter':
                el['y'] = int((ch - h) // 2)
        else:
            min_x = min(els[i].get('x', 0) for i in targets)
            max_r = max(els[i].get('x', 0) + els[i].get('width', 200) for i in targets)
            min_y = min(els[i].get('y', 0) for i in targets)
            max_b = max(els[i].get('y', 0) + els[i].get('height', 45) for i in targets)
            center_x = (min_x + max_r) / 2.0
            center_y = (min_y + max_b) / 2.0
            for i in targets:
                el = els[i]
                w, h = el.get('width', 200), el.get('height', 45)
                if mode == 'left':
                    el['x'] = int(min_x)
                elif mode == 'hcenter':
                    el['x'] = int(round(center_x - w / 2.0))
                elif mode == 'right':
                    el['x'] = int(max_r - w)
                elif mode == 'vcenter':
                    el['y'] = int(round(center_y - h / 2.0))

        self.save_theme_to_disk()

    def distribute_selected_elements(self):
        els = self.theme_data.get('elements', [])
        targets = [i for i in self.selected_element_indices if 0 <= i < len(els) and not els[i].get('locked', False)]
        if len(targets) < 3:
            targets = [i for i, el in enumerate(els) if not el.get('locked', False) and not el.get('hidden', False)]
        if len(targets) < 3:
            return

        self.push_undo_state("Eşit Dağıt")
        targets.sort(key=lambda i: els[i].get('y', 0))
        top_y = els[targets[0]].get('y', 0)
        bottom_el = els[targets[-1]]
        bottom_end = bottom_el.get('y', 0) + bottom_el.get('height', 45)
        total_heights = sum(els[i].get('height', 45) for i in targets)
        available_space = (bottom_end - top_y) - total_heights
        gap = available_space / float(len(targets) - 1)

        curr_y = float(top_y)
        for i in targets:
            els[i]['y'] = int(round(curr_y))
            curr_y += els[i].get('height', 45) + gap

        self.save_theme_to_disk()

    def move_selected_element_layer(self, delta):
        idx = self.selected_element_idx
        els = self.theme_data.get('elements', [])
        if idx is None or not (0 <= idx < len(els)):
            return
        new_idx = idx + delta
        if not (0 <= new_idx < len(els)):
            return
        self.push_undo_state("Katman Sırası Değiştir")
        els[idx], els[new_idx] = els[new_idx], els[idx]
        self.refresh_elements_list()
        self.select_element_by_index(new_idx, clear_others=True)
        self.save_theme_to_disk()

    def toggle_lock_selected_element(self):
        els = self.theme_data.get('elements', [])
        targets = self.selected_element_indices if self.selected_element_indices else (
            {self.selected_element_idx} if self.selected_element_idx is not None else set()
        )
        if not targets:
            return
        self.push_undo_state("Kilitle / Kilit Aç")
        first_idx = next(iter(targets))
        new_lock = not els[first_idx].get('locked', False)
        for i in targets:
            if 0 <= i < len(els):
                els[i]['locked'] = new_lock
        self.refresh_elements_list()
        if self.selected_element_idx is not None:
            self.select_element_by_index(self.selected_element_idx, clear_others=False)
        self.save_theme_to_disk()

    def toggle_hide_selected_element(self):
        els = self.theme_data.get('elements', [])
        targets = self.selected_element_indices if self.selected_element_indices else (
            {self.selected_element_idx} if self.selected_element_idx is not None else set()
        )
        if not targets:
            return
        self.push_undo_state("Gizle / Göster")
        first_idx = next(iter(targets))
        new_hide = not els[first_idx].get('hidden', False)
        for i in targets:
            if 0 <= i < len(els):
                els[i]['hidden'] = new_hide
        self.refresh_elements_list()
        if self.selected_element_idx is not None:
            self.select_element_by_index(self.selected_element_idx, clear_others=False)
        self.save_theme_to_disk()

    def update_prop_panel_visibility(self, el_type):
        """
        🎛️ Dynamically shows ONLY the controls relevant to the selected element type!
        Keeps the right settings panel clean, uncluttered, and focused.
        """
        self.widget_border_option.setVisible(True)
        self.widget_anim_effects.setVisible(el_type not in ['box', 'custom_image'])
        self.widget_countdown_settings.setVisible(el_type == 'event_countdown')
        self.widget_weather_settings.setVisible(el_type == 'weather_widget')
        if hasattr(self, 'widget_custom_image'):
            self.widget_custom_image.setVisible(el_type == 'custom_image')
        if hasattr(self, 'widget_ram_mode'):
            curr_el = None
            if self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(self.theme_data.get('elements', [])):
                curr_el = self.theme_data['elements'][self.selected_element_idx]
            curr_sid = str((curr_el or {}).get('sensorId', ''))
            is_ram_sensor = (
                el_type in ['sensor', 'gauge', 'vertical_gauge', 'circle_gauge', 'animated_fan', 'sparkline_graph']
                and curr_sid in ('ram_used', 'ram_load', 'ram_free', 'ram_free_load', 'ram_used_both', 'ram_free_both')
            )
            self.widget_ram_mode.setVisible(is_ram_sensor)

        if el_type == 'box':
            self.widget_sensor_type.setVisible(False)
            self.widget_txt_lbl.setVisible(False)
            self.widget_font_controls.setVisible(False)
            self.widget_colors.setVisible(True)
            self.btn_txt_col.setVisible(False)
            self.btn_pct_col.setVisible(False)
            self.widget_dynamic_col.setVisible(False)
            self.btn_custom_marquee.setVisible(False)
            self.widget_bg_box.setVisible(True)
        elif el_type == 'custom_image':
            self.widget_sensor_type.setVisible(False)
            self.widget_txt_lbl.setVisible(True)
            self.lbl_txt_title.setText("Görsel Adı:")
            self.widget_font_controls.setVisible(False)
            self.widget_colors.setVisible(True)
            self.btn_txt_col.setVisible(False)
            self.btn_pct_col.setVisible(False)
            self.widget_dynamic_col.setVisible(False)
            self.btn_custom_marquee.setVisible(False)
            self.widget_bg_box.setVisible(True)
        elif el_type in ['music_player', 'ping_monitor']:
            self.widget_sensor_type.setVisible(False)
            self.widget_txt_lbl.setVisible(False)
            self.widget_font_controls.setVisible(True)
            self.widget_colors.setVisible(True)
            self.btn_txt_col.setVisible(True)
            self.btn_pct_col.setVisible(True)
            self.widget_dynamic_col.setVisible(False)
            self.btn_custom_marquee.setVisible(False)
            self.widget_bg_box.setVisible(True)
        elif el_type == 'weather_widget':
            self.widget_sensor_type.setVisible(False)
            self.widget_txt_lbl.setVisible(False)
            self.widget_font_controls.setVisible(True)
            self.widget_colors.setVisible(True)
            self.btn_txt_col.setVisible(True)
            self.btn_pct_col.setVisible(True)
            self.widget_dynamic_col.setVisible(False)
            self.btn_custom_marquee.setVisible(False)
            self.widget_bg_box.setVisible(True)
        elif el_type == 'event_countdown':
            self.widget_sensor_type.setVisible(False)
            self.widget_txt_lbl.setVisible(True)
            self.lbl_txt_title.setText("Etkinlik Başlığı:")
            self.widget_font_controls.setVisible(True)
            self.widget_colors.setVisible(True)
            self.btn_txt_col.setVisible(True)
            self.btn_pct_col.setVisible(True)
            self.widget_dynamic_col.setVisible(False)
            self.btn_custom_marquee.setVisible(False)
            self.widget_bg_box.setVisible(True)
        elif el_type == 'marquee':
            self.widget_sensor_type.setVisible(False)
            self.widget_txt_lbl.setVisible(True)
            self.lbl_txt_title.setText("Öne Eklenecek Metin:")
            self.widget_font_controls.setVisible(True)
            self.widget_colors.setVisible(True)
            self.btn_txt_col.setVisible(True)
            self.btn_pct_col.setVisible(False)
            self.widget_dynamic_col.setVisible(False)
            self.btn_custom_marquee.setVisible(True)
            self.widget_bg_box.setVisible(True)
        elif el_type in ['sensor', 'gauge', 'vertical_gauge', 'circle_gauge', 'animated_fan', 'sparkline_graph']:
            self.widget_sensor_type.setVisible(True)
            self.widget_txt_lbl.setVisible(True)
            self.lbl_txt_title.setText("Etiket / Başlık:")
            self.widget_font_controls.setVisible(True)
            self.widget_colors.setVisible(True)
            self.btn_txt_col.setVisible(True)
            self.btn_pct_col.setVisible(True)
            self.widget_dynamic_col.setVisible(True)
            self.btn_custom_marquee.setVisible(False)
            self.widget_bg_box.setVisible(True)
        elif el_type == 'text':
            self.widget_sensor_type.setVisible(False)
            self.widget_txt_lbl.setVisible(True)
            self.lbl_txt_title.setText("Metin İçeriği:")
            self.widget_font_controls.setVisible(True)
            self.widget_colors.setVisible(True)
            self.btn_txt_col.setVisible(True)
            self.btn_pct_col.setVisible(False)
            self.widget_dynamic_col.setVisible(False)
            self.btn_custom_marquee.setVisible(False)
            self.widget_bg_box.setVisible(True)
        else:
            self.widget_sensor_type.setVisible(True)
            self.widget_txt_lbl.setVisible(True)
            self.lbl_txt_title.setText("Etiket / Başlık:")
            self.widget_font_controls.setVisible(True)
            self.widget_colors.setVisible(True)
            self.btn_txt_col.setVisible(True)
            self.btn_pct_col.setVisible(True)
            self.widget_dynamic_col.setVisible(False)
            self.btn_custom_marquee.setVisible(False)
            self.widget_bg_box.setVisible(True)

    def load_element_properties(self, el):
        self.txt_label.blockSignals(True)
        self.combo_sensor_type.blockSignals(True)
        self.combo_font.blockSignals(True)
        self.chk_bold.blockSignals(True)
        self.chk_italic.blockSignals(True)
        self.chk_border.blockSignals(True)
        if hasattr(self, 'chk_glow'):
            self.chk_glow.blockSignals(True)
        if hasattr(self, 'spin_corner_radius'):
            self.spin_corner_radius.blockSignals(True)
        self.combo_anim_effect.blockSignals(True)
        self.spin_anim_speed.blockSignals(True)
        self.date_event_target.blockSignals(True)
        self.txt_weather_loc.blockSignals(True)
        self.spin_fsize.blockSignals(True)
        self.spin_val_fsize.blockSignals(True)
        self.combo_align.blockSignals(True)
        self.chk_dynamic_color.blockSignals(True)
        self.slider_bg_opacity.blockSignals(True)
        self._sync_selected_element_geom_spinboxes(el)

        el_type = el.get('type', 'sensor')
        self.update_prop_panel_visibility(el_type)

        self.txt_label.setText(str(el.get('label', '')))

        current_sensor = el.get('sensorId', 'cpu_temp')
        s_idx = self.combo_sensor_type.findData(current_sensor)
        if s_idx >= 0:
            self.combo_sensor_type.setCurrentIndex(s_idx)

        if hasattr(self, 'combo_ram_mode'):
            self.combo_ram_mode.blockSignals(True)
            ram_mode = str(el.get('ramDisplayMode', '')).strip()
            if not ram_mode:
                if current_sensor == 'ram_load':
                    ram_mode = 'used_pct'
                elif current_sensor == 'ram_free':
                    ram_mode = 'free_gb'
                elif current_sensor == 'ram_free_load':
                    ram_mode = 'free_pct'
                elif current_sensor == 'ram_used_both':
                    ram_mode = 'used_both'
                elif current_sensor == 'ram_free_both':
                    ram_mode = 'free_both'
                else:
                    ram_mode = 'used_gb'
            rm_idx = self.combo_ram_mode.findData(ram_mode)
            if rm_idx >= 0:
                self.combo_ram_mode.setCurrentIndex(rm_idx)
            self.combo_ram_mode.blockSignals(False)

        font_name = el.get('fontFamily', 'Arial')
        idx = self.combo_font.findText(font_name)
        if idx >= 0:
            self.combo_font.setCurrentIndex(idx)

        self.chk_bold.setChecked(bool(el.get('isBold', True)))
        self.chk_italic.setChecked(bool(el.get('isItalic', False)))
        self.chk_border.setChecked(bool(el.get('showBorder', True)))
        if hasattr(self, 'chk_glow'):
            self.chk_glow.setChecked(bool(el.get('glowEnabled', False)))
        if hasattr(self, 'spin_corner_radius'):
            self.spin_corner_radius.setValue(int(el.get('cornerRadius', 0)))

        anim_eff = el.get('animEffect', 'none')
        eff_idx = self.combo_anim_effect.findData(anim_eff)
        self.combo_anim_effect.setCurrentIndex(eff_idx if eff_idx >= 0 else 0)
        self.spin_anim_speed.setValue(int(el.get('animSpeed', 5)))

        target_ts = float(el.get('targetTimestamp', time.time() + 7776000))
        self.date_event_target.setDateTime(QDateTime.fromSecsSinceEpoch(int(target_ts)))

        if hasattr(self, 'sensor'):
            self.txt_weather_loc.setText(str(getattr(self.sensor, 'custom_location', '')))
        
        if 'valueFontSize' not in el:
            el['valueFontSize'] = 24

        lbl_size = int(el.get('fontSize', 18))
        val_size = int(el.get('valueFontSize', 24))
        self.spin_fsize.setValue(lbl_size)
        self.spin_val_fsize.setValue(val_size)

        align_map = {'left': 0, 'center': 1, 'right': 2}
        self.combo_align.setCurrentIndex(align_map.get(el.get('textAlign', 'left'), 0))

        self.chk_dynamic_color.setChecked(bool(el.get('dynamicColor', False)))
        self.slider_bg_opacity.setValue(int(el.get('bgOpacity', 50)))

        self.btn_txt_col.setStyleSheet(f"background: {el.get('textColor', '#ffffff')}; color: black; padding: 5px 6px; font-size: 11px;")
        self.btn_pct_col.setStyleSheet(f"background: {el.get('percentColor', '#38bdf8')}; color: black; padding: 5px 6px; font-size: 11px;")
        self.btn_gfx_col.setStyleSheet(f"background: {el.get('graphicColor', '#38bdf8')}; color: black; padding: 5px 6px; font-size: 11px;")
        self.btn_bg_col.setStyleSheet(f"background: {el.get('bgColor', '#0f172a')}; color: white; padding: 5px 8px; font-size: 11px;")

        self.txt_label.blockSignals(False)
        self.combo_sensor_type.blockSignals(False)
        self.combo_font.blockSignals(False)
        self.chk_bold.blockSignals(False)
        self.chk_italic.blockSignals(False)
        self.chk_border.blockSignals(False)
        if hasattr(self, 'chk_glow'):
            self.chk_glow.blockSignals(False)
        if hasattr(self, 'spin_corner_radius'):
            self.spin_corner_radius.blockSignals(False)
        self.combo_anim_effect.blockSignals(False)
        self.spin_anim_speed.blockSignals(False)
        self.date_event_target.blockSignals(False)
        self.txt_weather_loc.blockSignals(False)
        self.spin_fsize.blockSignals(False)
        self.spin_val_fsize.blockSignals(False)
        self.combo_align.blockSignals(False)
        self.chk_dynamic_color.blockSignals(False)
        self.slider_bg_opacity.blockSignals(False)

    def _sync_selected_element_geom_spinboxes(self, el=None):
        """Syncs X, Y, W, H spinboxes in the properties panel with the selected element."""
        if not hasattr(self, 'spin_el_x'):
            return
        if el is None:
            if self.selected_element_idx is None or not (0 <= self.selected_element_idx < len(self.theme_data.get('elements', []))):
                return
            el = self.theme_data['elements'][self.selected_element_idx]
        tw = max(64, int(self.theme_data.get('width', 320)))
        th = max(64, int(self.theme_data.get('height', 1480)))
        for sp in (self.spin_el_x, self.spin_el_y, self.spin_el_w, self.spin_el_h):
            sp.blockSignals(True)
        self.spin_el_x.setRange(0, max(4096, tw))
        self.spin_el_y.setRange(0, max(4096, th))
        self.spin_el_w.setRange(16, max(4096, tw))
        self.spin_el_h.setRange(16, max(4096, th))
        self.spin_el_x.setValue(int(el.get('x', 0)))
        self.spin_el_y.setValue(int(el.get('y', 0)))
        self.spin_el_w.setValue(int(el.get('width', el.get('w', 260))))
        self.spin_el_h.setValue(int(el.get('height', el.get('h', 45))))
        for sp in (self.spin_el_x, self.spin_el_y, self.spin_el_w, self.spin_el_h):
            sp.blockSignals(False)

    def on_element_geom_spin_changed(self, _val=0):
        """Applies exact pixel coordinates/dimensions from X, Y, W, H spinboxes to the selected element."""
        if self.selected_element_idx is None or not (0 <= self.selected_element_idx < len(self.theme_data.get('elements', []))):
            return
        tw = max(64, int(self.theme_data.get('width', 320)))
        th = max(64, int(self.theme_data.get('height', 1480)))
        el = self.theme_data['elements'][self.selected_element_idx]
        w = max(16, min(tw, int(self.spin_el_w.value())))
        h = max(16, min(th, int(self.spin_el_h.value())))
        x = max(0, min(tw - w, int(self.spin_el_x.value())))
        y = max(0, min(th - h, int(self.spin_el_y.value())))
        el['x'] = x
        el['y'] = y
        el['width'] = w
        el['height'] = h
        self.save_theme_to_disk()
        if hasattr(self, 'canvas_widget'):
            self.canvas_widget.update()

    def on_anim_effect_changed(self, idx):
        if self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(self.theme_data['elements']):
            eff = self.combo_anim_effect.itemData(idx)
            self.theme_data['elements'][self.selected_element_idx]['animEffect'] = eff
            self.save_theme_to_disk()

    def on_anim_speed_changed(self, val):
        if self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(self.theme_data['elements']):
            self.theme_data['elements'][self.selected_element_idx]['animSpeed'] = val
            self.save_theme_to_disk()

    def on_countdown_date_changed(self, qdt):
        if self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(self.theme_data['elements']):
            ts = qdt.toSecsSinceEpoch()
            self.theme_data['elements'][self.selected_element_idx]['targetTimestamp'] = ts
            self.save_theme_to_disk()

    def on_weather_loc_changed(self, text):
        if hasattr(self, 'sensor'):
            self.sensor.custom_location = text.strip()
            self.app_settings['custom_weather_location'] = text.strip()
            self.save_app_settings()

    def on_auto_weather_loc_clicked(self):
        if hasattr(self, 'sensor'):
            self.sensor.custom_location = ''
            self.txt_weather_loc.setText('')
            self.app_settings['custom_weather_location'] = ''
            self.save_app_settings()
            QMessageBox.information(self, "Konum", "Konum GPS / Windows Otomatik Algılamaya sıfırlandı!")

    def on_sensor_type_changed(self, idx):
        if self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(self.theme_data['elements']):
            self.push_undo_state("Sensör Tipi Değiştir")
            new_sensor = self.combo_sensor_type.itemData(idx)
            el = self.theme_data['elements'][self.selected_element_idx]
            el['sensorId'] = new_sensor
            if new_sensor == 'ram_used':
                el['ramDisplayMode'] = 'used_gb'
            elif new_sensor == 'ram_load':
                el['ramDisplayMode'] = 'used_pct'
            elif new_sensor == 'ram_free':
                el['ramDisplayMode'] = 'free_gb'
            self.load_element_properties(el)
            self.refresh_elements_list()
            self.save_theme_to_disk()

    def on_ram_mode_changed(self, idx):
        """Allows the user to choose whether a RAM widget displays Used vs Free RAM (GB, %, or Both) with matching bar fill."""
        if self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(self.theme_data['elements']):
            if not hasattr(self, 'combo_ram_mode'):
                return
            mode = self.combo_ram_mode.itemData(idx)
            if not mode:
                return
            self.push_undo_state("RAM Gösterim Modu Değiştir")
            el = self.theme_data['elements'][self.selected_element_idx]
            el['ramDisplayMode'] = mode
            # Keep sensorId in sync for clarity & sparkline history
            if mode == 'used_gb':
                el['sensorId'] = 'ram_used'
            elif mode == 'used_pct':
                el['sensorId'] = 'ram_load'
            elif mode == 'used_both':
                el['sensorId'] = 'ram_used'
            elif mode == 'free_gb':
                el['sensorId'] = 'ram_free'
            elif mode == 'free_pct':
                el['sensorId'] = 'ram_free'
            elif mode == 'free_both':
                el['sensorId'] = 'ram_free'

            # Auto-update default Turkish/English RAM label if the user hasn't customized it to something unrelated
            curr_lbl = str(el.get('label', '')).strip()
            default_ram_labels = {
                'RAM Kullanımı (GB)', 'RAM Yükü (%)', 'Kalan / Boş RAM (GB)',
                'RAM Kullanımı', 'Kalan RAM', 'Boş RAM', 'RAM Used (GB)', 'RAM Load (%)', 'Free RAM (GB)'
            }
            if curr_lbl in default_ram_labels:
                if mode.startswith('free_'):
                    el['label'] = 'Kalan / Boş RAM (GB)' if mode == 'free_gb' else 'Kalan RAM'
                else:
                    el['label'] = 'RAM Kullanımı (GB)' if mode == 'used_gb' else 'RAM Kullanımı'
                self.txt_label.blockSignals(True)
                self.txt_label.setText(el['label'])
                self.txt_label.blockSignals(False)

            self.combo_sensor_type.blockSignals(True)
            s_idx = self.combo_sensor_type.findData(el['sensorId'])
            if s_idx >= 0:
                self.combo_sensor_type.setCurrentIndex(s_idx)
            self.combo_sensor_type.blockSignals(False)

            self.refresh_elements_list()
            self.save_theme_to_disk()
            if hasattr(self, 'canvas_widget'):
                self.canvas_widget.update()

    def on_label_changed(self, text):
        if self.selected_element_idx is not None:
            self.theme_data['elements'][self.selected_element_idx]['label'] = text
            self.refresh_elements_list()
            self.save_theme_to_disk()

    def on_font_changed(self, idx):
        if self.selected_element_idx is not None:
            self.push_undo_state("Yazı Tipi Değiştir")
            self.theme_data['elements'][self.selected_element_idx]['fontFamily'] = self.combo_font.currentText()
            self.save_theme_to_disk()

    def on_style_changed(self):
        if self.selected_element_idx is not None:
            self.push_undo_state("Stil Değiştir")
            el = self.theme_data['elements'][self.selected_element_idx]
            el['isBold'] = self.chk_bold.isChecked()
            el['isItalic'] = self.chk_italic.isChecked()
            el['showBorder'] = self.chk_border.isChecked()
            if hasattr(self, 'chk_glow'):
                el['glowEnabled'] = self.chk_glow.isChecked()
            self.save_theme_to_disk()

    def on_corner_radius_changed(self, val):
        if self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(self.theme_data['elements']):
            self.theme_data['elements'][self.selected_element_idx]['cornerRadius'] = int(val)
            self.save_theme_to_disk()

    def pick_custom_image_layer(self):
        if self.selected_element_idx is None or not (0 <= self.selected_element_idx < len(self.theme_data['elements'])):
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Özel Görsel / Logo / Sticker Seç",
            "",
            "Görsel Dosyaları (*.png *.webp *.jpg *.jpeg *.bmp *.gif)"
        )
        if not file_path:
            return
        try:
            import base64
            self.push_undo_state("Özel Görsel Seç")
            tw = max(320, int(self.theme_data.get('width', 320)))
            th = max(320, int(self.theme_data.get('height', 1480)))
            src = Image.open(file_path).convert('RGBA')
            src.thumbnail((max(320, min(1920, tw)), max(320, min(1080, th))), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            src.save(buf, format='PNG', optimize=True)
            b64_str = base64.b64encode(buf.getvalue()).decode('ascii')
            el = self.theme_data['elements'][self.selected_element_idx]
            el['imageDataB64'] = b64_str
            el['imagePath'] = file_path
            if not el.get('label'):
                el['label'] = os.path.splitext(os.path.basename(file_path))[0][:18]
                self.txt_label.setText(el['label'])
            self.refresh_elements_list()
            self.save_theme_to_disk()
        except Exception as e:
            QMessageBox.warning(self, "Görsel Hatası", f"Görsel yüklenemedi: {e}")

    def on_fsize_changed(self, val):
        if self.selected_element_idx is not None:
            self.theme_data['elements'][self.selected_element_idx]['fontSize'] = val
            self.save_theme_to_disk()

    def on_val_fsize_changed(self, val):
        if self.selected_element_idx is not None:
            self.theme_data['elements'][self.selected_element_idx]['valueFontSize'] = val
            self.save_theme_to_disk()

    def on_align_changed(self, idx):
        if self.selected_element_idx is not None:
            aligns = ['left', 'center', 'right']
            self.theme_data['elements'][self.selected_element_idx]['textAlign'] = aligns[idx]
            self.save_theme_to_disk()

    def on_dynamic_color_toggle(self, state):
        if self.selected_element_idx is not None:
            self.theme_data['elements'][self.selected_element_idx]['dynamicColor'] = (state == Qt.Checked)
            self.save_theme_to_disk()

    def pick_text_color(self):
        col = QColorDialog.getColor()
        if col.isValid() and self.selected_element_idx is not None:
            self.push_undo_state("Metin Rengi Değiştir")
            self.theme_data['elements'][self.selected_element_idx]['textColor'] = col.name()
            self.btn_txt_col.setStyleSheet(f"background: {col.name()}; color: black;")
            self.save_theme_to_disk()

    def pick_percent_color(self):
        col = QColorDialog.getColor()
        if col.isValid() and self.selected_element_idx is not None:
            self.push_undo_state("Değer Rengi Değiştir")
            self.theme_data['elements'][self.selected_element_idx]['percentColor'] = col.name()
            self.btn_pct_col.setStyleSheet(f"background: {col.name()}; color: black;")
            self.save_theme_to_disk()

    def pick_graphic_color(self):
        col = QColorDialog.getColor()
        if col.isValid() and self.selected_element_idx is not None:
            self.push_undo_state("Grafik Rengi Değiştir")
            self.theme_data['elements'][self.selected_element_idx]['graphicColor'] = col.name()
            self.btn_gfx_col.setStyleSheet(f"background: {col.name()}; color: black;")
            self.save_theme_to_disk()

    def pick_bg_color(self):
        col = QColorDialog.getColor()
        if col.isValid() and self.selected_element_idx is not None:
            self.push_undo_state("Kutu Rengi Değiştir")
            self.theme_data['elements'][self.selected_element_idx]['bgColor'] = col.name()
            self.btn_bg_col.setStyleSheet(f"background: {col.name()}; color: white;")
            self.save_theme_to_disk()

    def on_bg_opacity_changed(self, val):
        if self.selected_element_idx is not None:
            self.theme_data['elements'][self.selected_element_idx]['bgOpacity'] = val
            self.save_theme_to_disk()

    def delete_selected_element(self):
        els = self.theme_data.get('elements', [])
        targets = sorted(
            (i for i in self.selected_element_indices if 0 <= i < len(els)),
            reverse=True
        )
        if not targets and self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(els):
            targets = [self.selected_element_idx]
        if not targets:
            return
        self.push_undo_state("Öge Sil")
        for i in targets:
            self.theme_data['elements'].pop(i)
        self.deselect_element()
        self.refresh_elements_list()
        self.save_theme_to_disk()

    def duplicate_selected_element(self):
        if self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(self.theme_data['elements']):
            self.push_undo_state("Öge Çoğalt")
            tw = max(64, int(self.theme_data.get('width', 320)))
            th = max(64, int(self.theme_data.get('height', 1480)))
            el_copy = json.loads(json.dumps(self.theme_data['elements'][self.selected_element_idx]))
            el_copy['id'] = f"el_{int(time.time()*1000) % 10000}"
            ew = max(16, int(el_copy.get('width', el_copy.get('w', 260))))
            eh = max(16, int(el_copy.get('height', el_copy.get('h', 45))))
            el_copy['x'] = min(max(0, tw - ew), int(el_copy.get('x', 0)) + 20)
            el_copy['y'] = min(max(0, th - eh), int(el_copy.get('y', 0)) + 20)
            self.theme_data['elements'].append(el_copy)
            self.refresh_elements_list()
            self.select_element_by_index(len(self.theme_data['elements']) - 1)
            self.save_theme_to_disk()

    def refresh_multi_screen_bar_ui(self):
        """Rebuilds the Multi-Screen Theme Creator Bar tabs and syncs quick controls."""
        try:
            if not hasattr(self, 'screen_tabs_layout'):
                return

            while self.screen_tabs_layout.count():
                item = self.screen_tabs_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            for idx_s, (sid, ws) in enumerate(list(self.screen_workspaces.items()), start=1):
                is_active = (sid == self.active_screen_slot_id)
                t_name = str(ws.get('theme_data', {}).get('name', 'Özel'))[:14]
                tw = int(ws.get('theme_data', {}).get('width', 320))
                th = int(ws.get('theme_data', {}).get('height', 1480))
                stream_dot = "🟢" if ws.get('stream_enabled', True) else "⚪"
                rot_badge = " 🎠" if ws.get('auto_rotate_enabled', False) else ""
                s_icon = "📟" if ws.get('screen_type') == 'usb_serial' else "🖥️"
                s_tag = "USB LCD" if ws.get('screen_type') == 'usb_serial' else f"Ekran {idx_s}"
                btn_lbl = f"{stream_dot} {s_icon} {s_tag} ({tw}×{th}){rot_badge}"

                btn = QPushButton(btn_lbl)
                rot_status_tip = "AÇIK" if ws.get('auto_rotate_enabled', False) else "KAPALI"
                btn.setToolTip(
                    f"Ekran Yuvası: {ws.get('title', sid)}\n"
                    f"Kendi Özel Çözünürlüğü: {tw}×{th} px\n"
                    f"Aktif Tema: {t_name}\n"
                    f"Otomatik Tema Döngüsü: {rot_status_tip}\n"
                    f"Bu ekranın özel temasını düzenlemek için tıklayın!"
                )
                if is_active:
                    btn.setStyleSheet("""
                        QPushButton {
                            background: #222a3d;
                            color: #ffffff;
                            border: 1px solid #8083ff;
                            border-radius: 7px;
                            padding: 4px 9px;
                            font-size: 11px;
                            font-weight: 900;
                        }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #060e20;
                            color: #908fa0;
                            border: 1px solid #1e293b;
                            border-radius: 7px;
                            padding: 4px 9px;
                            font-size: 11px;
                            font-weight: 700;
                        }
                        QPushButton:hover {
                            background-color: #171f33;
                            color: #dae2fd;
                            border-color: #8083ff;
                        }
                    """)
                btn.clicked.connect(lambda checked=False, target_sid=sid: self.switch_active_screen_workspace(target_sid))
                self.screen_tabs_layout.addWidget(btn)

            active_ws = self.screen_workspaces.get(self.active_screen_slot_id)
            if active_ws:
                if hasattr(self, 'chk_slot_stream_enabled'):
                    self.chk_slot_stream_enabled.blockSignals(True)
                    self.chk_slot_stream_enabled.setChecked(bool(active_ws.get('stream_enabled', True)))
                    self.chk_slot_stream_enabled.blockSignals(False)

                if hasattr(self, 'combo_slot_resolution'):
                    self.combo_slot_resolution.blockSignals(True)
                    self.combo_slot_resolution.clear()
                    curr_w = int(active_ws.get('theme_data', {}).get('width', 320))
                    curr_h = int(active_ws.get('theme_data', {}).get('height', 1480))
                    res_presets = [
                        ("320×1480 (Dikey USB LCD Şerit)", (320, 1480)),
                        ("1920×1080 (Full HD 1080p Yatay)", (1920, 1080)),
                        ("1080×1920 (Full HD 1080p Dikey)", (1080, 1920)),
                        ("2560×1440 (2K QHD Yatay)", (2560, 1440)),
                        ("3840×2160 (4K UHD Yatay)", (3840, 2160)),
                        ("1920×480 (8.8\" Yatay Kasa Şerit)", (1920, 480)),
                        ("480×1920 (8.8\" Dikey Kasa Şerit)", (480, 1920)),
                        ("1280×400 (7.9\" Yatay Kasa Şerit)", (1280, 400)),
                        ("1024×600 (7\" Mini HDMI Ekran)", (1024, 600)),
                        ("800×480 (5\" Mini Kasa Ekranı)", (800, 480)),
                        ("480×320 (3.5\" IPS USB Ekran)", (480, 320)),
                    ]
                    matched_res_idx = -1
                    for r_idx, (r_label, (rw, rh)) in enumerate(res_presets):
                        self.combo_slot_resolution.addItem(f"📐 {r_label}", (rw, rh))
                        if rw == curr_w and rh == curr_h:
                            matched_res_idx = r_idx
                    if matched_res_idx == -1:
                        custom_idx = self.combo_slot_resolution.count()
                        self.combo_slot_resolution.addItem(f"📐 {curr_w}×{curr_h} (Özel Çözünürlük)", (curr_w, curr_h))
                        matched_res_idx = custom_idx
                    self.combo_slot_resolution.addItem("⚙️ Özel Çözünürlük Gir...", "custom")
                    self.combo_slot_resolution.setCurrentIndex(matched_res_idx)
                    self.combo_slot_resolution.blockSignals(False)

                if hasattr(self, 'combo_slot_quick_theme'):
                    self.combo_slot_quick_theme.blockSignals(True)
                    self.combo_slot_quick_theme.clear()
                    curr_t_name = str(active_ws.get('theme_data', {}).get('name', '')).strip()
                    curr_w = int(active_ws.get('theme_data', {}).get('width', 320))
                    curr_h = int(active_ws.get('theme_data', {}).get('height', 1480))
                    active_rk = f"{curr_w}x{curr_h}"
                    presets = get_all_preset_themes()

                    groups = {}
                    for p in presets:
                        pw = int(p.get('width', 320))
                        ph = int(p.get('height', 1480))
                        rk = f"{pw}x{ph}"
                        groups.setdefault(rk, {'w': pw, 'h': ph, 'items': []})['items'].append(p)

                    sorted_rkeys = sorted(
                        groups.keys(),
                        key=lambda rk: (0 if rk == active_rk else 1, -(groups[rk]['w'] * groups[rk]['h']), rk)
                    )

                    matched_idx = -1
                    model = self.combo_slot_quick_theme.model()
                    for rk in sorted_rkeys:
                        g = groups[rk]
                        hdr_lbl = f"━━ 📐 {g['w']}×{g['h']} ({len(g['items'])} Tema) ━━"
                        self.combo_slot_quick_theme.addItem(hdr_lbl, None)
                        hdr_row = self.combo_slot_quick_theme.count() - 1
                        if model and hasattr(model, 'item'):
                            m_item = model.item(hdr_row)
                            if m_item:
                                m_item.setEnabled(False)
                                m_item.setForeground(QColor("#38bdf8" if rk == active_rk else "#818cf8"))

                        for p in g['items']:
                            self.combo_slot_quick_theme.addItem(f"  📦 {p['name']} [{g['w']}×{g['h']}]", p['name'])
                            if p['name'].strip().lower() == curr_t_name.lower():
                                matched_idx = self.combo_slot_quick_theme.count() - 1

                    if matched_idx >= 0:
                        self.combo_slot_quick_theme.setCurrentIndex(matched_idx)
                    elif self.combo_slot_quick_theme.count() > 1:
                        self.combo_slot_quick_theme.setCurrentIndex(1)
                    self.combo_slot_quick_theme.blockSignals(False)

                if hasattr(self, 'chk_slot_auto_rotate'):
                    self.chk_slot_auto_rotate.blockSignals(True)
                    self.chk_slot_auto_rotate.setChecked(bool(active_ws.get('auto_rotate_enabled', False)))
                    self.chk_slot_auto_rotate.blockSignals(False)

                if hasattr(self, 'btn_slot_rotate_themes'):
                    rot_list = active_ws.get('rotate_themes') or []
                    all_names = {p['name'].strip().lower() for p in get_all_preset_themes()}
                    valid_cnt = len([x for x in rot_list if str(x).strip().lower() in all_names])
                    self.btn_slot_rotate_themes.setText(f"🎠 Döngü ({valid_cnt} Tema)")

                if hasattr(self, 'btn_rem_scr'):
                    self.btn_rem_scr.setEnabled(self.active_screen_slot_id not in ('usb_lcd_1', 'hdmi_mon_1'))

                tw = int(active_ws.get('theme_data', {}).get('width', 320))
                th = int(active_ws.get('theme_data', {}).get('height', 1480))
                if hasattr(self, 'btn_apply_full_layout'):
                    self.btn_apply_full_layout.setText(f"🔄  Düzeni Uygula ({tw}×{th})")
                if hasattr(self, 'lbl_top_res_pill'):
                    self.lbl_top_res_pill.setText(f"{tw}×{th}")
                if hasattr(self, 'lbl_bg_res_tag'):
                    self.lbl_bg_res_tag.setText(f"{tw}×{th}")

                t_name = active_ws.get('theme_data', {}).get('name', 'Özel Tema')
                if hasattr(self, 'lbl_center_ws_title'):
                    self.lbl_center_ws_title.setText(f"🎨 {t_name}")
            if hasattr(self, 'apply_current_language'):
                self.apply_current_language()
        except Exception as e:
            print("refresh_multi_screen_bar_ui note:", e)

    def on_slot_auto_rotate_toggled(self, state):
        ws = self.screen_workspaces.get(self.active_screen_slot_id)
        if not ws:
            return
        enabled = (state == Qt.Checked)
        ws['auto_rotate_enabled'] = enabled
        ws['_last_rotate_time'] = time.time()
        if enabled and not ws.get('rotate_themes'):
            ws['rotate_themes'] = [p['name'] for p in get_all_preset_themes()]
        self.app_settings['auto_rotate_themes'] = any(
            bool(w.get('auto_rotate_enabled', False)) for w in self.screen_workspaces.values()
        )
        self.save_app_settings()
        self.refresh_multi_screen_bar_ui()
        self.save_screen_workspaces_to_disk()

    def on_slot_resolution_selected(self, idx):
        """Triggered when the user selects a target resolution for the active screen workspace."""
        if idx < 0 or not hasattr(self, 'combo_slot_resolution'):
            return
        data = self.combo_slot_resolution.itemData(idx)
        if data == "custom":
            curr_w = int(self.theme_data.get('width', 1920))
            curr_h = int(self.theme_data.get('height', 1080))
            txt, ok = QInputDialog.getText(
                self,
                "Özel Ekran Çözünürlüğü",
                "Bu ekran için hedef tema çözünürlüğünü (Genişlik x Yükseklik) girin (Örn: 1920x1080, 2560x1080, 1280x800):",
                text=f"{curr_w}x{curr_h}"
            )
            if ok and txt.strip():
                parts = txt.lower().replace('×', 'x').replace('*', 'x').split('x')
                if len(parts) == 2:
                    try:
                        nw = max(64, min(4096, int(parts[0].strip())))
                        nh = max(64, min(4096, int(parts[1].strip())))
                        self.change_active_screen_resolution(nw, nh)
                        return
                    except Exception:
                        pass
            self.refresh_multi_screen_bar_ui()
            return
        if isinstance(data, (tuple, list)) and len(data) == 2:
            self.change_active_screen_resolution(int(data[0]), int(data[1]))

    def change_active_screen_resolution(self, new_w, new_h):
        """Adapts ONLY the active screen workspace's theme to (new_w, new_h) and updates the live canvas."""
        new_w = max(64, min(4096, int(new_w)))
        new_h = max(64, min(4096, int(new_h)))
        old_w = int(self.theme_data.get('width', 320))
        old_h = int(self.theme_data.get('height', 1480))
        if new_w == old_w and new_h == old_h:
            return

        self.push_undo_state(f"Çözünürlük Değiştir ({new_w}×{new_h})")
        adapt_theme_elements_to_resolution(self.theme_data, new_w, new_h)

        ws = self.screen_workspaces.get(self.active_screen_slot_id)
        if ws:
            ws['theme_data'] = self.theme_data
            ws['user_locked_resolution'] = True
            if ws.get('hardware'):
                ws['hardware'].reset_background_media()
                ws['hardware'].set_resolution(new_w, new_h)

        self.hardware.reset_background_media()
        self.hardware.set_resolution(new_w, new_h)
        self.auto_adjust_window_to_canvas(new_w, new_h)
        self.update_canvas_geometry()

        if self.selected_element_idx is not None and 0 <= self.selected_element_idx < len(self.theme_data.get('elements', [])):
            self.load_element_properties(self.theme_data['elements'][self.selected_element_idx])

        self.refresh_multi_screen_bar_ui()
        self.save_theme_to_disk()
        if hasattr(self, 'canvas_widget'):
            self.canvas_widget.update()

    def on_slot_stream_enabled_toggled(self, state):
        ws = self.screen_workspaces.get(self.active_screen_slot_id)
        if not ws:
            return
        enabled = (state == Qt.Checked)
        ws['stream_enabled'] = enabled
        self._sync_output_mode_from_workspaces()
        if self.is_streaming and ws.get('screen_type') == 'hdmi_monitor' and ws.get('hdmi_window'):
            if enabled:
                ws['hdmi_window'].show_on_monitor(monitor_index=ws.get('monitor_index', 1))
            else:
                ws['hdmi_window'].hide()
        self.refresh_multi_screen_bar_ui()
        self.save_screen_workspaces_to_disk()

    def on_slot_quick_theme_selected(self, idx):
        if idx < 0 or not hasattr(self, 'combo_slot_quick_theme'):
            return
        t_name = self.combo_slot_quick_theme.itemData(idx)
        if t_name:
            self.apply_preset_theme_to_slot(self.active_screen_slot_id, t_name, preserve_editor_if_inactive=False)

    def auto_start_streaming(self):
        if not self.is_streaming:
            self.toggle_live_stream(silent_on_fail=True)

    def toggle_live_stream(self, silent_on_fail=False):
        output_mode = self.app_settings.get('output_mode', 'usb_serial')
        if not self.is_streaming:
            target_port = self.app_settings.get('selected_com_port', 'auto')
            
            # 1. Connect USB LCD workspace(s) if usb_serial or both mode
            if output_mode in ['usb_serial', 'both']:
                usb_ok = self.primary_usb_hardware.auto_connect(target_port=target_port)
                for ws in list(self.screen_workspaces.values()):
                    if ws.get('screen_type') == 'usb_serial' and ws.get('stream_enabled', True):
                        hw = ws.get('hardware')
                        if hw and hw is not self.primary_usb_hardware:
                            hw.auto_connect(target_port=ws.get('com_port', 'auto'))

                if not usb_ok and output_mode == 'usb_serial':
                    self.is_streaming = False
                    if hasattr(self, 'lbl_port_status'):
                        self.lbl_port_status.setText("🔴 Bağlı Değil")
                        self.lbl_port_status.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 12px; margin-right: 8px;")
                        if hasattr(self, 'apply_current_language'):
                            self.apply_current_language()
                    if silent_on_fail:
                        self.showNormal()
                        self.activateWindow()
                    else:
                        curr_p = target_port if target_port and target_port != 'auto' else 'COM'
                        QMessageBox.warning(
                            self,
                            "Bağlantı Hatası",
                            f"USB Kasa ekranına ({curr_p}) bağlanılamadı.\n\n"
                            "Çözüm Adımları:\n"
                            "1. Üst bardaki '🔌 Port' kutusundan doğru COM portunu seçin.\n"
                            "2. '🖥️ Kasa Ekranı Seçici' butonuna basarak HDMI çıkışını veya ekranınızı seçin.\n"
                            "3. USB kablosunun kasaya tam takılı olduğundan emin olun."
                        )
                    return

            # 2. Show HDMI companion windows for all enabled hdmi_monitor workspaces if hdmi_monitor or both mode
            if output_mode in ['hdmi_monitor', 'both']:
                try:
                    shown_any_hdmi = False
                    for ws in list(self.screen_workspaces.values()):
                        if ws.get('screen_type') == 'hdmi_monitor' and ws.get('stream_enabled', True):
                            win = ws.get('hdmi_window')
                            mon_idx = int(ws.get('monitor_index', self.app_settings.get('selected_monitor_index', 1)))
                            if win:
                                win.show_on_monitor(monitor_index=mon_idx)
                                shown_any_hdmi = True
                    if not shown_any_hdmi and hasattr(self, 'hdmi_companion_window') and self.hdmi_companion_window:
                        target_mon_idx = self.app_settings.get('selected_monitor_index', 1)
                        self.hdmi_companion_window.show_on_monitor(monitor_index=target_mon_idx)
                except Exception as ex_hdmi:
                    print("HDMI companion show error:", ex_hdmi)

            self.is_streaming = True
            self.update_stream_status_ui()

            if hasattr(self, 'combo_port') and self.primary_usb_hardware.com_port:
                for i in range(self.combo_port.count()):
                    if self.combo_port.itemData(i) == self.primary_usb_hardware.com_port:
                        self.combo_port.blockSignals(True)
                        self.combo_port.setCurrentIndex(i)
                        self.combo_port.blockSignals(False)
                        break
        else:
            self.is_streaming = False
            self.update_stream_status_ui()
            for ws in list(self.screen_workspaces.values()):
                if ws.get('hdmi_window'):
                    try:
                        ws['hdmi_window'].hide()
                    except Exception:
                        pass
            if hasattr(self, 'hdmi_companion_window') and self.hdmi_companion_window:
                try:
                    self.hdmi_companion_window.hide()
                except Exception:
                    pass

    def on_screen_frame_ready(self, slot_id, pil_frame):
        """Routes each screen workspace's independently rendered frame to its own HDMI Companion Window."""
        try:
            if not self.is_streaming:
                return
            ws = self.screen_workspaces.get(slot_id)
            if ws and ws.get('hdmi_window') and ws['hdmi_window'].isVisible():
                ws['hdmi_window'].update_frame(pil_frame)
        except Exception:
            pass

    def on_hdmi_frame_ready(self, pil_frame):
        """Fallback handler if primary hdmi_companion_window is not bound to a slot."""
        try:
            if self.is_streaming and hasattr(self, 'hdmi_companion_window') and self.hdmi_companion_window.isVisible():
                # Only update if not already handled by a workspace slot
                if getattr(self.hdmi_companion_window, 'slot_config', None) is None:
                    self.hdmi_companion_window.update_frame(pil_frame)
        except Exception:
            pass

    def on_hdmi_companion_closed(self, closed_slot_id=None):
        """HDMI yansıtma penceresi Esc veya çift tıklama ile kapatıldığında tetiklenir"""
        any_hdmi_still_visible = any(
            ws.get('hdmi_window') and ws['hdmi_window'].isVisible()
            for ws in getattr(self, 'screen_workspaces', {}).values()
            if ws.get('screen_type') == 'hdmi_monitor' and ws.get('slot_id') != closed_slot_id
        )
        if any_hdmi_still_visible:
            return
        output_mode = self.app_settings.get('output_mode', 'usb_serial')
        if output_mode == 'hdmi_monitor' and self.is_streaming:
            self.toggle_live_stream()
        elif output_mode == 'both' and self.is_streaming:
            # Keep USB Case Screen running and switch output_mode to usb_serial
            self.app_settings['output_mode'] = 'usb_serial'
            self.save_app_settings()
            self.update_stream_status_ui()

    def update_canvas_geometry(self):
        """Önizleme tuvalini temanın en-boy oranına göre dinamik ölçeklendirir"""
        tw = self.theme_data.get('width', 320)
        th = self.theme_data.get('height', 1480)
        if hasattr(self, 'canvas_widget') and hasattr(self.canvas_widget, 'update_geometry_for_theme'):
            self.canvas_widget.update_geometry_for_theme(tw, th)

    def open_case_screen_selector(self):
        """Piyasadaki kasa ekranları kataloğu ve canlı algılama penceresini açar"""
        try:
            dialog = CaseScreenSelectorDialog(self, current_theme_data=self.theme_data, app_settings=self.app_settings)
            
            def handle_screen_selected(screen_info):
                try:
                    out_mode = screen_info.get('output_mode') or screen_info.get('type') or 'usb_serial'
                    self.app_settings['output_mode'] = out_mode
                    self.app_settings['selected_screen_id'] = screen_info.get('unique_id', screen_info.get('id', ''))
                    self.app_settings['selected_screen_title'] = screen_info.get('label', screen_info.get('title', ''))
                    
                    if 'qt_index' in screen_info or 'monitor_index' in screen_info or out_mode == 'hdmi_monitor':
                        mon_idx = screen_info.get('qt_index', screen_info.get('monitor_index', 1))
                        self.app_settings['selected_monitor_index'] = mon_idx
                        self.app_settings['hdmi_screen_index'] = mon_idx
                        self.app_settings['selected_monitor_name'] = screen_info.get('name', 'HDMI Monitör')
                    if 'port' in screen_info:
                        self.app_settings['selected_com_port'] = screen_info['port']
                        
                    self.save_app_settings()

                    # Note: Resolution adaptation is already safely handled inside CaseScreenSelectorDialog.select_target_screen
                    # Never overwrite self.theme_data['rotation'] or unscaled width/height here!

                    # Update combo_output_target in main GUI
                    if hasattr(self, 'combo_output_target'):
                        target_idx = self.combo_output_target.findData(out_mode)
                        if target_idx >= 0:
                            self.combo_output_target.blockSignals(True)
                            self.combo_output_target.setCurrentIndex(target_idx)
                            self.combo_output_target.blockSignals(False)

                    # Update combo_port in main GUI if port is set
                    if hasattr(self, 'combo_port') and 'port' in screen_info:
                        for p_i in range(self.combo_port.count()):
                            if self.combo_port.itemData(p_i) == screen_info['port']:
                                self.combo_port.blockSignals(True)
                                self.combo_port.setCurrentIndex(p_i)
                                self.combo_port.blockSignals(False)
                                break

                    if self.is_streaming:
                        if out_mode in ['usb_serial', 'both']:
                            target_port = self.app_settings.get('selected_com_port', 'auto')
                            self.hardware.auto_connect(target_port=target_port)

                        if out_mode in ['hdmi_monitor', 'both']:
                            self.hdmi_companion_window.show_on_monitor(monitor_index=self.app_settings.get('selected_monitor_index', 1))
                        else:
                            self.hdmi_companion_window.hide()

                    self.update_stream_status_ui()
                except Exception as ex:
                    print("handle_screen_selected note:", ex)

            def handle_theme_adapted(new_theme_data):
                try:
                    self.theme_data.clear()
                    self.theme_data.update(new_theme_data)
                    w = self.theme_data.get('width', 320)
                    h = self.theme_data.get('height', 1480)
                    self.hardware.set_resolution(w, h)
                    self.update_canvas_geometry()
                    self.refresh_elements_list()
                    self.save_theme_to_disk()
                except Exception as ex:
                    print("handle_theme_adapted note:", ex)

            dialog.screen_selected_signal.connect(handle_screen_selected)
            dialog.theme_adapted_signal.connect(handle_theme_adapted)
            dialog.exec_()
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Hata", f"Kasa Ekranı Seçici açılırken bir hata oluştu:\n{e}")

    def check_and_prompt_case_screens_on_startup(self):
        """Uygulama açıldığında veya farklı bilgisayara taşındığında yeni ekranları tespit eder"""
        try:
            detected = detect_all_available_screens()
            self.sync_screen_workspaces_with_hardware(detected=detected)
            curr_hash_items = []
            for m in detected.get('monitors', []):
                curr_hash_items.append(f"{m.get('index')}:{m.get('width')}x{m.get('height')}")
            for c in detected.get('com_ports', []):
                curr_hash_items.append(f"{c.get('port')}:{c.get('description')}")
            
            curr_signature = "|".join(curr_hash_items)
            last_signature = self.app_settings.get('last_hardware_signature', '')

            self.app_settings['last_hardware_signature'] = curr_signature
            self.save_app_settings()

            if last_signature and last_signature != curr_signature:
                total_screens = len(detected.get('monitors', [])) + len([c for c in detected.get('com_ports', []) if c.get('is_lcd')])
                if total_screens > 1:
                    reply = QMessageBox.question(
                        self,
                        "🖥️ Yeni Donanım / Ekran Yapılandırması Algılandı",
                        "Bilgisayarınızda yeni bir kasa ekranı veya monitör değişikliği algılandı!\n"
                        "Üstteki '🖥️ EKRANLAR' çubuğunda her ekran için ayrı tema çalışma alanı otomatik olarak aktif edildi.\n\n"
                        "Ekran ayarlarını yönetmek için 'Kasa Ekranı Seçici' penceresini açmak ister misiniz?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes
                    )
                    if reply == QMessageBox.Yes:
                        self.open_case_screen_selector()
        except Exception as e:
            print("Auto-detect startup check note:", e)

    def open_game_profile_manager(self):
        try:
            dlg = GameProfileManagerDialog(self)
            dlg.profiles_updated_signal.connect(lambda: setattr(self, '_last_bound_proc_scan_t', 0.0))
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Oyun Profili Yöneticisi açılırken bir hata oluştu:\n{e}")

    def _resolve_active_game_and_theme(self):
        """
        🎯 Resolves whether a bound game (from game_profiles) or a 3D RTSS game is currently active.
        Returns (exe_name, display_game_name, target_theme_name) or (None, None, None).
        """
        raw_profiles = self.app_settings.get('game_profiles', {})
        profiles = raw_profiles if isinstance(raw_profiles, dict) else {}

        # 1. Instant Foreground Window Process Check (<0.05ms)
        fg_exe = get_foreground_process_exe()
        if fg_exe and fg_exe in profiles:
            prof = profiles[fg_exe]
            t_name = str(prof.get('theme_name') or '').strip() if isinstance(prof, dict) else ''
            if t_name:
                return fg_exe, str(prof.get('game_name') or fg_exe), t_name

        # 2. RTSS Active 3D Game Process Check
        rtss_exe = sanitize_exe_name(str(self.sensor.cached_sensors.get('active_game_exe', '')).strip())
        if rtss_exe and rtss_exe in profiles:
            prof = profiles[rtss_exe]
            t_name = str(prof.get('theme_name') or '').strip() if isinstance(prof, dict) else ''
            if t_name:
                return rtss_exe, str(prof.get('game_name') or rtss_exe), t_name

        # 3. Background Running Bound Game Check (throttled every 1.5s for 0% CPU impact, keeps theme on Alt+Tab)
        if profiles and bool(self.app_settings.get('keep_game_theme_on_alttab', True)):
            now_t = time.perf_counter()
            if (now_t - getattr(self, '_last_bound_proc_scan_t', 0.0)) >= 1.5:
                self._last_bound_proc_scan_t = now_t
                found_bg_exe = None
                # Prefer currently active bound game if it is still running
                prev_exe = getattr(self, '_active_game_exe_name', None)
                try:
                    running_names = {
                        sanitize_exe_name(p.info.get('name') or '')
                        for p in psutil.process_iter(['name'])
                    }
                    running_names.discard('')
                    if prev_exe and prev_exe in profiles and prev_exe in running_names:
                        found_bg_exe = prev_exe
                    else:
                        for cand_exe in profiles.keys():
                            if cand_exe in running_names:
                                found_bg_exe = cand_exe
                                break
                except Exception:
                    pass
                self._cached_running_bound_exe = found_bg_exe

            bg_exe = getattr(self, '_cached_running_bound_exe', None)
            if bg_exe and bg_exe in profiles:
                prof = profiles[bg_exe]
                t_name = str(prof.get('theme_name') or '').strip() if isinstance(prof, dict) else ''
                if t_name:
                    return bg_exe, str(prof.get('game_name') or bg_exe), t_name

        # 4. Fallback Default 3D Game Theme (for unbound 3D games detected via RTSS)
        fallback_theme = str(self.app_settings.get('auto_game_theme_name', '')).strip()
        if rtss_exe and fallback_theme:
            return rtss_exe, rtss_exe, fallback_theme

        return None, None, None

    def on_gui_tick(self):
        # 🎮 Automatic Per-Game Profile & 3D Game Theme Switcher
        if self.app_settings.get('auto_game_theme_enabled', True):
            try:
                det_exe, det_label, target_game_theme_name = self._resolve_active_game_and_theme()
                in_game_mode = getattr(self, '_in_auto_game_theme', False)
                applied_theme = getattr(self, '_active_game_theme_applied', '')

                if det_exe and target_game_theme_name and (not in_game_mode or applied_theme.lower() != target_game_theme_name.lower()):
                    themes = get_all_preset_themes()
                    matched_item = next(
                        (t for t in themes if t['name'].strip().lower() == target_game_theme_name.lower()),
                        None
                    )
                    if matched_item:
                        t_json = load_preset_theme_data(matched_item)
                        if t_json and isinstance(t_json, dict):
                            if not in_game_mode:
                                with self.hardware.render_lock:
                                    self._pre_game_theme_snapshot = copy.deepcopy(self.theme_data)
                            self._in_auto_game_theme = True
                            self._active_game_exe_name = det_exe
                            self._active_game_theme_applied = matched_item['name']
                            self.hardware.reset_background_media()
                            with self.hardware.render_lock:
                                self.theme_data.clear()
                                self.theme_data.update(t_json)
                            self.hardware.set_resolution(self.theme_data.get('width', 320), self.theme_data.get('height', 1480))
                            self.update_canvas_geometry()
                            self.refresh_elements_list()
                            self.refresh_multi_screen_bar_ui()
                            if hasattr(self, 'tray_icon') and self.tray_icon:
                                self.tray_icon.showMessage(
                                    "🎮 Oyun Profili Aktif",
                                    f"{det_label} ({det_exe}) algılandı — '{matched_item['name']}' temasına otomatik geçildi.",
                                    QSystemTrayIcon.Information,
                                    2500
                                )
                elif not det_exe and in_game_mode:
                    self._in_auto_game_theme = False
                    self._active_game_exe_name = None
                    self._active_game_theme_applied = ''
                    prev_snapshot = getattr(self, '_pre_game_theme_snapshot', None)
                    if prev_snapshot and isinstance(prev_snapshot, dict):
                        self.hardware.reset_background_media()
                        with self.hardware.render_lock:
                            self.theme_data.clear()
                            self.theme_data.update(copy.deepcopy(prev_snapshot))
                        self.hardware.set_resolution(self.theme_data.get('width', 320), self.theme_data.get('height', 1480))
                        self.update_canvas_geometry()
                        self.refresh_elements_list()
                        self.refresh_multi_screen_bar_ui()
                        if hasattr(self, 'tray_icon') and self.tray_icon:
                            self.tray_icon.showMessage(
                                "🖥️ Masaüstü Temasına Dönüldü",
                                f"Oyun kapandı — '{self.theme_data.get('name', 'Masaüstü')}' teması geri yüklendi.",
                                QSystemTrayIcon.Information,
                                2500
                            )
            except Exception as e_game:
                print("Auto game theme switcher note:", e_game)

        # 🎠 Per-Screen Selective Automatic Theme Rotation (paused while in automatic game theme mode)
        if not getattr(self, '_in_auto_game_theme', False):
            try:
                now = time.time()
                any_ws_enabled = any(
                    bool(ws.get('auto_rotate_enabled', False))
                    for ws in getattr(self, 'screen_workspaces', {}).values()
                )
                for sid, ws in list(getattr(self, 'screen_workspaces', {}).items()):
                    ws_rot_on = bool(ws.get('auto_rotate_enabled', False))
                    if not ws_rot_on and not (self.app_settings.get('auto_rotate_themes', False) and not any_ws_enabled and sid == self.active_screen_slot_id):
                        continue
                    rot_val = max(1, min(9999, int(ws.get('rotate_interval_val', self.app_settings.get('rotate_val', 30)) or 30)))
                    unit = str(ws.get('rotate_interval_unit', self.app_settings.get('rotate_unit', 'sec')) or 'sec')
                    mult = 60 if unit == 'min' else (3600 if unit == 'hour' else 1)
                    interval_sec = rot_val * mult
                    last_rot = float(ws.get('_last_rotate_time') or self.last_theme_rotate_time)
                    if now - last_rot >= interval_sec:
                        ws['_last_rotate_time'] = now
                        self.last_theme_rotate_time = now
                        self.rotate_screen_workspace_theme(sid, delta=1)
            except Exception as e:
                print("Auto rotate note:", e)

        # ⚡ CRITICAL OPTIMIZATION: If GUI is hidden, minimized, or preview not visible, SKIP canvas rendering completely!
        if not self.isVisible() or self.isMinimized() or not self.canvas_widget.isVisible():
            return

        # Update GUI Preview Canvas & Stitch Telemetry Ribbon
        try:
            # If streaming is already running, reuse the upright frame rendered by HardwareStreamWorker!
            if self.is_streaming and self.hardware.last_rendered_frame is not None:
                frame_pil = self.hardware.last_rendered_frame
                metrics = getattr(self.sensor, 'cached_sensors', {}) or {}
            else:
                metrics = self.sensor.get_sensors(refresh_interval_sec=self.theme_data.get('refresh_sec', 1.0))
                frame_pil = self.hardware.render_theme_frame(self.theme_data, metrics, for_hardware=False)

            if isinstance(metrics, dict):
                if hasattr(self, 'lbl_top_cpu_pill'):
                    self.lbl_top_cpu_pill.setText(f"CPU: {metrics.get('cpu_temp', '--°C')} ({metrics.get('cpu_load', '--%')})")
                if hasattr(self, 'lbl_top_gpu_pill'):
                    self.lbl_top_gpu_pill.setText(f"GPU: {metrics.get('gpu_temp', '--°C')} ({metrics.get('gpu_load', '--%')})")
                if hasattr(self, 'lbl_top_ram_pill'):
                    self.lbl_top_ram_pill.setText(f"RAM: {metrics.get('ram_used', '-- GB')}")
                if hasattr(self, 'lbl_rail_ram_val'):
                    self.lbl_rail_ram_val.setText(str(metrics.get('ram_used', '-- GB')))
                if hasattr(self, 'bar_rail_ram'):
                    raw_rl = str(metrics.get('ram_load', '35')).replace('%', '').strip()
                    try:
                        self.bar_rail_ram.setValue(max(0, min(100, int(float(raw_rl)))))
                    except Exception:
                        pass
                if hasattr(self, '_sensor_card_value_labels'):
                    for s_id, s_type, v_lbl in self._sensor_card_value_labels:
                        if s_type in ("sensor", "time", "date") and s_id in metrics:
                            v_lbl.setText(str(metrics.get(s_id, '--'))[:14])

            cw = max(100, self.canvas_widget.width())
            ch = max(100, self.canvas_widget.height())
            scaled_pil = frame_pil.resize((cw, ch), Image.Resampling.BILINEAR)
            self.canvas_widget.update_pixmap(pil_to_pixmap(scaled_pil))
        except Exception as e:
            print("GUI tick note:", e)

    def closeEvent(self, event):
        if self.app_settings.get('enable_tray', True) and self.tray_icon and self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            try:
                self.save_screen_workspaces_to_disk()
            except Exception:
                pass
            self.sensor.stop()
            self.stream_worker.stop()
            for ws in getattr(self, 'screen_workspaces', {}).values():
                win = ws.get('hdmi_window')
                if win:
                    try:
                        win.close()
                    except Exception:
                        pass
                hw = ws.get('hardware')
                if hw:
                    try:
                        hw.close()
                    except Exception:
                        pass
            if hasattr(self, 'hdmi_companion_window'):
                try:
                    self.hdmi_companion_window.close()
                except Exception:
                    pass
            try:
                self.hardware.close()
            except Exception:
                pass
            event.accept()

if __name__ == '__main__':
    try:
        ensure_single_instance()
        time.sleep(0.3)
        app = QApplication(sys.argv)
        gui = CyberPulseStudioGUI()
        gui.show()
        gui.raise_()
        gui.activateWindow()
        sys.exit(app.exec_())
    except Exception as e:
        print("Fatal launch error:", e)
