import os
import re
import json
import ctypes
import psutil

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QComboBox, QCheckBox, QScrollArea, QFrame, QFileDialog,
    QMessageBox, QGroupBox, QInputDialog
)

from hardware_driver import _is_safe_local_file_path

# 🔒 SECURITY: Limits for manifest & directory scanning
MAX_MANIFEST_READ_BYTES = 512 * 1024  # 512 KB max per manifest file
MAX_SCAN_DIRS = 300                   # Cap number of game folders scanned
MAX_FILES_PER_GAME_DIR = 80           # Cap files inspected per game folder

# Known non-game helper / installer / crash-reporter executables to ignore when picking a game's main .exe
NON_GAME_EXE_KEYWORDS = (
    'unins', 'crash', 'setup', 'redist', 'dxsetup', 'vcredist', 'vc_redist',
    'easyanticheat', 'eac_', 'battleye', 'beclient', 'beservice', 'launcher_helper',
    'unitycrashhandler', 'unrealcefsubprocess', 'cefprocess', 'crs-handler',
    'dotnet', 'directx', 'physx', 'cleanup', 'touchup', 'activation', 'updater',
    'update', 'patcher', 'repair', 'benchmark', 'config', 'settings', 'server',
    'dedicated', 'modtools', 'editor', 'sdk', 'compiler', 'steamerrorreporter'
)

# Strict regex for valid Windows executable filenames
VALID_EXE_REGEX = re.compile(r'^[a-zA-Z0-9_\-\.\(\)\s\+]{1,100}\.exe$', re.IGNORECASE)


def sanitize_exe_name(exe_str):
    """🔒 SECURITY: Extracts and validates a clean lowercase .exe filename."""
    if not exe_str or not isinstance(exe_str, str):
        return ""
    base = os.path.basename(exe_str.replace('\\', '/').strip()).lower()
    if not VALID_EXE_REGEX.match(base):
        return ""
    if any(ord(c) < 32 for c in base):
        return ""
    return base


def _find_best_game_exe_in_folder(folder_path, game_title=""):
    """
    Scans a game installation folder (up to depth 2) to find the primary game .exe.
    Uses file size and title similarity heuristics while ignoring crash handlers & redistributables.
    """
    if not folder_path or not _is_safe_local_file_path(folder_path) or not os.path.isdir(folder_path):
        return None, None

    candidates = []
    title_tokens = [t.lower() for t in re.split(r'[^a-zA-Z0-9]+', game_title or '') if len(t) >= 3]
    folder_abs = os.path.abspath(folder_path)

    def _scan_dir(cur_dir, depth):
        if depth > 2 or len(candidates) >= MAX_FILES_PER_GAME_DIR:
            return
        try:
            entries = os.scandir(cur_dir)
        except Exception:
            return
        with entries:
            count = 0
            for entry in entries:
                count += 1
                if count > MAX_FILES_PER_GAME_DIR:
                    break
                try:
                    if entry.is_symlink():
                        continue
                    st = entry.stat(follow_symlinks=False)
                    # 🔒 SECURITY: Skip NTFS reparse points / directory junctions (FILE_ATTRIBUTE_REPARSE_POINT = 0x400)
                    if getattr(st, 'st_file_attributes', 0) & 0x400:
                        continue
                    if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith('.exe'):
                        ename_lower = entry.name.lower()
                        if any(kw in ename_lower for kw in NON_GAME_EXE_KEYWORDS):
                            continue
                        if not VALID_EXE_REGEX.match(entry.name):
                            continue
                        sz = st.st_size
                        if sz < 100 * 1024:  # Ignore tiny stub exes < 100 KB
                            continue
                        # Score candidate by size + name match + shipping binary bonus
                        score = min(sz / (1024.0 * 1024.0), 150.0)
                        stem = os.path.splitext(ename_lower)[0]
                        if 'launcher' in ename_lower:
                            score -= 120.0
                        if 'shipping' in ename_lower:
                            score += 80.0
                        for tok in title_tokens:
                            if tok in stem:
                                score += 45.0
                        if depth == 0:
                            score += 20.0
                        candidates.append((score, entry.name, os.path.abspath(entry.path)))
                    elif entry.is_dir(follow_symlinks=False) and depth < 2:
                        dname = entry.name.lower()
                        if dname not in ('redist', '_commonredist', 'directx', 'vcredist', 'support', 'installers', 'easyanticheat', 'battleye', 'mono', 'logs', 'crashes'):
                            _scan_dir(entry.path, depth + 1)
                except Exception:
                    pass

    _scan_dir(folder_abs, 0)
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[0], reverse=True)
    _, best_name, best_path = candidates[0]
    return best_name.lower(), best_path


def _scan_steam_games():
    """Scans Steam libraryfolders.vdf and appmanifest_*.acf across all disks."""
    games = []
    steam_paths = set()
    try:
        import winreg
        for hive, subkey in [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")
        ]:
            try:
                with winreg.OpenKey(hive, subkey) as k:
                    val, _ = winreg.QueryValueEx(k, "SteamPath")
                    if val and isinstance(val, str) and _is_safe_local_file_path(val):
                        steam_paths.add(os.path.normpath(val))
            except Exception:
                pass
    except Exception:
        pass

    for default_p in [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam", r"D:\Steam", r"E:\Steam", r"L:\Steam"]:
        if os.path.isdir(default_p):
            steam_paths.add(default_p)

    library_dirs = set()
    for sp in steam_paths:
        if os.path.isdir(sp):
            library_dirs.add(sp)
            vdf_p = os.path.join(sp, "steamapps", "libraryfolders.vdf")
            if os.path.isfile(vdf_p) and _is_safe_local_file_path(vdf_p):
                try:
                    with open(vdf_p, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(MAX_MANIFEST_READ_BYTES)
                    for m in re.finditer(r'"path"\s+"([^"]+)"', content, re.IGNORECASE):
                        raw_lib = m.group(1).replace("\\\\", "\\")
                        if _is_safe_local_file_path(raw_lib) and os.path.isdir(raw_lib):
                            library_dirs.add(os.path.normpath(raw_lib))
                except Exception:
                    pass

    # Also check standard <Drive>:\SteamLibrary folders on fixed drives
    try:
        for part in psutil.disk_partitions(all=False):
            mp = part.mountpoint
            if mp and os.path.isdir(mp):
                for sub in ("SteamLibrary", "Steam", r"Games\SteamLibrary"):
                    cand_lib = os.path.join(mp, sub)
                    if os.path.isdir(cand_lib):
                        library_dirs.add(os.path.normpath(cand_lib))
    except Exception:
        pass

    seen_install_dirs = set()
    for lib in sorted(library_dirs):
        steamapps = os.path.join(lib, "steamapps")
        if not os.path.isdir(steamapps):
            continue
        try:
            files = os.listdir(steamapps)
        except Exception:
            continue
        for fname in files:
            if not (fname.startswith("appmanifest_") and fname.endswith(".acf")):
                continue
            acf_path = os.path.join(steamapps, fname)
            if not _is_safe_local_file_path(acf_path) or not os.path.isfile(acf_path):
                continue
            try:
                with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
                    acf_data = f.read(MAX_MANIFEST_READ_BYTES)
                name_m = re.search(r'"name"\s+"([^"]+)"', acf_data)
                dir_m = re.search(r'"installdir"\s+"([^"]+)"', acf_data)
                if not name_m or not dir_m:
                    continue
                g_name = name_m.group(1).strip()
                install_sub = os.path.basename(dir_m.group(1).strip())
                if any(skip in g_name.lower() for skip in ("steamworks common redistributables", "proton", "steam linux runtime", "soundtrack", "dedicated server")):
                    continue
                common_dir = os.path.abspath(os.path.join(steamapps, "common"))
                game_dir = os.path.abspath(os.path.join(common_dir, install_sub))
                if os.path.commonpath([common_dir, game_dir]) != common_dir or not os.path.isdir(game_dir):
                    continue
                if game_dir.lower() in seen_install_dirs:
                    continue
                seen_install_dirs.add(game_dir.lower())
                exe_name, exe_path = _find_best_game_exe_in_folder(game_dir, g_name)
                if exe_name:
                    games.append({
                        'game_name': g_name[:80],
                        'exe_name': exe_name,
                        'exe_path': exe_path,
                        'platform': 'Steam'
                    })
            except Exception:
                pass
    return games


def _scan_epic_games():
    """Scans Epic Games Launcher manifests in C:\\ProgramData\\Epic\\EpicGamesLauncher\\Data\\Manifests."""
    games = []
    manifest_dir = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
    if not os.path.isdir(manifest_dir):
        return games
    try:
        for fname in os.listdir(manifest_dir):
            if not fname.lower().endswith(".item"):
                continue
            fpath = os.path.join(manifest_dir, fname)
            if not _is_safe_local_file_path(fpath) or not os.path.isfile(fpath):
                continue
            try:
                if os.path.getsize(fpath) > MAX_MANIFEST_READ_BYTES:
                    continue
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                disp_name = str(data.get("DisplayName") or "").strip()
                install_loc = str(data.get("InstallLocation") or "").strip()
                launch_exe = str(data.get("LaunchExecutable") or "").strip()
                if not disp_name or not install_loc or not _is_safe_local_file_path(install_loc):
                    continue
                install_abs = os.path.abspath(install_loc)
                exe_name = sanitize_exe_name(launch_exe)
                exe_path = None
                if launch_exe:
                    cand_exe = os.path.abspath(os.path.join(install_abs, launch_exe))
                    # 🔒 SECURITY: Prevent path traversal outside InstallLocation
                    if _is_safe_local_file_path(cand_exe) and os.path.commonpath([install_abs, cand_exe]) == install_abs:
                        exe_path = cand_exe
                    else:
                        exe_name = ""
                if (not exe_name or any(k in exe_name for k in NON_GAME_EXE_KEYWORDS)) and os.path.isdir(install_abs):
                    exe_name, exe_path = _find_best_game_exe_in_folder(install_abs, disp_name)
                if exe_name:
                    games.append({
                        'game_name': disp_name[:80],
                        'exe_name': exe_name,
                        'exe_path': exe_path if (exe_path and _is_safe_local_file_path(exe_path) and os.path.isfile(exe_path)) else "",
                        'platform': 'Epic Games'
                    })
            except Exception:
                pass
    except Exception:
        pass
    return games


def _scan_standalone_and_registry_games():
    """Scans common game directories on local drives (Riot Games, XboxGames, Ubisoft, EA, Games) and Uninstall Registry."""
    games = []
    candidate_folders = []

    try:
        for part in psutil.disk_partitions(all=False):
            mp = part.mountpoint
            if not mp or not os.path.isdir(mp):
                continue
            for root_name, platform_label in [
                ("XboxGames", "Xbox / PC Game Pass"),
                ("Riot Games", "Riot Games"),
                ("Games", "Yerel Oyun"),
                ("GOG Games", "GOG"),
                (r"Program Files\Epic Games", "Epic Games"),
                (r"Program Files\EA Games", "EA App"),
                (r"Program Files (x86)\Ubisoft\Ubisoft Game Launcher\games", "Ubisoft"),
                (r"Program Files (x86)\Battle.net\Games", "Battle.net"),
            ]:
                parent_dir = os.path.join(mp, root_name)
                if os.path.isdir(parent_dir) and _is_safe_local_file_path(parent_dir):
                    try:
                        for sub in os.listdir(parent_dir)[:60]:
                            if sub.lower() in ('riot client', 'directx', 'redist'):
                                continue
                            sub_p = os.path.join(parent_dir, sub)
                            if os.path.isdir(sub_p):
                                candidate_folders.append((sub, sub_p, platform_label))
                    except Exception:
                        pass
    except Exception:
        pass

    for g_title, folder_p, plat in candidate_folders[:MAX_SCAN_DIRS]:
        exe_name, exe_path = _find_best_game_exe_in_folder(folder_p, g_title)
        if exe_name:
            games.append({
                'game_name': g_title[:80],
                'exe_name': exe_name,
                'exe_path': exe_path or "",
                'platform': plat
            })

    return games


def scan_installed_games():
    """
    🔍 Scans Steam, Epic Games, Xbox/Riot/EA/Ubisoft/GOG folders and returns a deduplicated list of installed games.
    """
    all_games = []
    seen_exes = set()

    for scanner in (_scan_steam_games, _scan_epic_games, _scan_standalone_and_registry_games):
        try:
            for item in scanner():
                exe = sanitize_exe_name(item.get('exe_name', ''))
                if not exe or exe in seen_exes:
                    continue
                seen_exes.add(exe)
                all_games.append({
                    'game_name': str(item.get('game_name') or exe).strip()[:80],
                    'exe_name': exe,
                    'exe_path': str(item.get('exe_path') or ''),
                    'platform': str(item.get('platform') or 'PC')
                })
        except Exception:
            pass

    all_games.sort(key=lambda g: g['game_name'].lower())
    return all_games


# 🔒 SECURITY: Explicit 64-bit Win32 API signatures to prevent pointer truncation on 64-bit HWNDs
try:
    _user32 = ctypes.windll.user32
    _user32.GetForegroundWindow.argtypes = []
    _user32.GetForegroundWindow.restype = ctypes.c_void_p
    _user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    _user32.GetWindowThreadProcessId.restype = ctypes.c_uint32
except Exception:
    _user32 = None

_fg_cache_hwnd = None
_fg_cache_pid = 0
_fg_cache_exe = ""


def get_foreground_process_exe():
    """
    ⚡ Returns the lowercase .exe name of the currently active foreground window in <0.01ms.
    Caches (hwnd, pid, exe_name) so psutil.Process is only queried when the focused window changes.
    """
    global _fg_cache_hwnd, _fg_cache_pid, _fg_cache_exe
    try:
        if _user32 is None:
            return ""
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid_dword = ctypes.c_uint32(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_dword))
        fg_pid = pid_dword.value
        if fg_pid <= 4:
            return ""
        if hwnd == _fg_cache_hwnd and fg_pid == _fg_cache_pid and _fg_cache_exe:
            return _fg_cache_exe
        proc = psutil.Process(fg_pid)
        exe_clean = sanitize_exe_name(proc.name())
        _fg_cache_hwnd = hwnd
        _fg_cache_pid = fg_pid
        _fg_cache_exe = exe_clean
        return exe_clean
    except Exception:
        return ""


class GameProfileManagerDialog(QDialog):
    """
    🎮 Oyun Profili ve Otomatik Tema Yöneticisi
    Sistemde yüklü oyunları otomatik bulur, istenilen .cptheme temasına bağlar ve oyun açıldığında otomatik geçiş sağlar.
    """
    profiles_updated_signal = pyqtSignal()

    def __init__(self, parent_gui):
        super().__init__(parent_gui)
        self.gui = parent_gui
        self.setWindowTitle("🎮 Oyun Profilleri ve Otomatik Tema Bağlayıcı")
        self.setMinimumSize(1020, 680)
        self.setStyleSheet("""
            QDialog { background-color: #060e20; color: #dae2fd; font-family: 'Segoe UI', Arial, sans-serif; }
            QLabel { color: #dae2fd; font-size: 13px; }
            QGroupBox {
                border: 1px solid rgba(68, 70, 86, 0.25);
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 14px;
                background-color: #0b1326;
                font-weight: 800;
                color: #38bdf8;
                letter-spacing: 0.4px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QPushButton {
                background: #171f33;
                border: 1px solid rgba(68, 70, 86, 0.35);
                border-radius: 6px;
                padding: 7px 13px;
                color: #dae2fd;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover { background: #222a3d; border-color: #8083ff; color: #ffffff; }
            QLineEdit {
                background: #131b2e;
                border: 1px solid rgba(68, 70, 86, 0.35);
                border-radius: 6px;
                padding: 7px 12px;
                color: #dae2fd;
                font-size: 13px;
            }
            QLineEdit:focus { border: 1px solid #38bdf8; background: #171f33; }
            QComboBox {
                background: #131b2e;
                border: 1px solid rgba(68, 70, 86, 0.35);
                border-radius: 6px;
                padding: 5px 10px;
                color: #dae2fd;
                font-weight: 600;
                font-size: 12px;
            }
            QComboBox:hover { border-color: #8083ff; }
            QCheckBox { color: #dae2fd; font-weight: 600; font-size: 13px; }
            QScrollBar:vertical { background: #060e20; width: 6px; margin: 0px; border-radius: 3px; }
            QScrollBar::handle:vertical { background: #222a3d; min-height: 24px; border-radius: 3px; }
            QScrollBar::handle:vertical:hover { background: #8083ff; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: #060e20; }
            QScrollBar:horizontal { background: #060e20; height: 6px; margin: 0px; border-radius: 3px; }
            QScrollBar::handle:horizontal { background: #222a3d; min-width: 24px; border-radius: 3px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: #060e20; }
        """)

        # Load current profiles dict: { 'cs2.exe': {'game_name': 'Counter-Strike 2', 'exe_name': 'cs2.exe', 'theme_name': '...', 'platform': 'Steam'} }
        raw_profiles = self.gui.app_settings.get('game_profiles', {})
        self.game_profiles = {}
        if isinstance(raw_profiles, dict):
            for k, v in raw_profiles.items():
                clean_k = sanitize_exe_name(k)
                if clean_k and isinstance(v, dict):
                    self.game_profiles[clean_k] = dict(v)

        self.discovered_games = []
        self.row_widgets = []
        self.active_quick_filter = "all"
        self.init_ui()
        self.rescan_system_games()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(18, 16, 18, 16)

        # Header
        hdr = QHBoxLayout()
        title_col = QVBoxLayout()
        lbl_t = QLabel("🎮 Oyun Profili ve Otomatik Tema Bağlayıcı")
        lbl_t.setStyleSheet("font-size: 18px; font-weight: 900; color: #dae2fd;")
        lbl_s = QLabel("Sisteminizde yüklü oyunları istediğiniz temaya bağlayın — oyun açıldığında kasa ekranı otomatik olarak o temaya geçsin, kapandığında masaüstü temanıza dönsün.")
        lbl_s.setStyleSheet("font-size: 12px; color: #c4c5d9;")
        title_col.addWidget(lbl_t)
        title_col.addWidget(lbl_s)
        hdr.addLayout(title_col)
        hdr.addStretch()
        main_layout.addLayout(hdr)

        # Top General Game Mode Settings — Stitch Card (#131b2e) with #060e20 sub-blocks
        grp_top = QFrame()
        grp_top.setStyleSheet("""
            QFrame {
                background-color: #131b2e;
                border: 1px solid rgba(68, 70, 86, 0.35);
                border-radius: 10px;
            }
        """)
        top_layout = QVBoxLayout(grp_top)
        top_layout.setContentsMargins(14, 12, 14, 12)
        top_layout.setSpacing(10)

        top_hdr = QHBoxLayout()
        lbl_top_title = QLabel("⚡ OTOMATİK OYUN ALGILAMA VE GEÇİŞ AYARLARI")
        lbl_top_title.setStyleSheet("color: #c0c1ff; font-size: 11px; font-weight: 800; letter-spacing: 0.6px; border: none;")
        top_hdr.addWidget(lbl_top_title)
        top_hdr.addStretch()
        top_layout.addLayout(top_hdr)

        row_toggles = QHBoxLayout()
        row_toggles.setSpacing(10)

        blk_toggle1 = QFrame()
        blk_toggle1.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid rgba(68, 70, 86, 0.3); border-radius: 8px; }")
        bt1_lay = QHBoxLayout(blk_toggle1)
        bt1_lay.setContentsMargins(10, 8, 10, 8)
        self.chk_enable_game_profiles = QCheckBox("🎮 Oyun Açıldığında Otomatik Tema Değişimini Etkinleştir")
        self.chk_enable_game_profiles.setChecked(bool(self.gui.app_settings.get('auto_game_theme_enabled', True)))
        self.chk_enable_game_profiles.setStyleSheet("color: #4edea3; font-weight: 800; font-size: 12px; border: none;")
        bt1_lay.addWidget(self.chk_enable_game_profiles)
        row_toggles.addWidget(blk_toggle1, stretch=1)

        blk_toggle2 = QFrame()
        blk_toggle2.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid rgba(68, 70, 86, 0.3); border-radius: 8px; }")
        bt2_lay = QHBoxLayout(blk_toggle2)
        bt2_lay.setContentsMargins(10, 8, 10, 8)
        self.chk_keep_on_alttab = QCheckBox("🔒 Alt+Tab Yapıldığında da Oyun Kapanana Kadar Oyun Temasını Koru")
        self.chk_keep_on_alttab.setChecked(bool(self.gui.app_settings.get('keep_game_theme_on_alttab', True)))
        self.chk_keep_on_alttab.setStyleSheet("color: #dae2fd; font-weight: 700; font-size: 12px; border: none;")
        self.chk_keep_on_alttab.setToolTip("Açık olduğunda, bağlı oyun arka planda çalışmaya devam ettiği sürece masaüstüne Alt+Tab yapsanız bile oyun teması ekranda kalır.")
        bt2_lay.addWidget(self.chk_keep_on_alttab)
        row_toggles.addWidget(blk_toggle2, stretch=1)

        top_layout.addLayout(row_toggles)

        blk_fallback = QFrame()
        blk_fallback.setStyleSheet("QFrame { background-color: #060e20; border: 1px solid rgba(68, 70, 86, 0.3); border-radius: 8px; }")
        row_fallback = QHBoxLayout(blk_fallback)
        row_fallback.setContentsMargins(10, 6, 10, 6)
        lbl_fb = QLabel("🎯 Özel Tema Bağlanmamış Diğer 3D Oyunlar İçin Varsayılan Tema:")
        lbl_fb.setStyleSheet("color: #c4c5d9; font-size: 11px; font-weight: 700; border: none;")
        row_fallback.addWidget(lbl_fb)
        self.combo_fallback_theme = QComboBox()
        self.combo_fallback_theme.setMinimumWidth(280)
        self.combo_fallback_theme.addItem("🚫 Yok (Yalnızca Özel Bağlanan Oyunlarda Değiştir)", "")

        from main_gui import get_all_preset_themes
        self.preset_themes = get_all_preset_themes()
        saved_fallback = str(self.gui.app_settings.get('auto_game_theme_name', '')).strip()
        sel_fb_idx = 0
        for idx_t, t_item in enumerate(self.preset_themes, start=1):
            tname = t_item['name']
            self.combo_fallback_theme.addItem(f"🎨 {tname}", tname)
            if tname.lower() == saved_fallback.lower():
                sel_fb_idx = idx_t
        self.combo_fallback_theme.setCurrentIndex(sel_fb_idx)
        row_fallback.addWidget(self.combo_fallback_theme)
        row_fallback.addStretch()
        top_layout.addWidget(blk_fallback)

        main_layout.addWidget(grp_top)

        # Toolbar: Search + Quick Filter Pills + Rescan + Add Custom .exe + Add Running Process
        bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Yüklü oyunlarda veya .exe adlarında ara (Örn: Counter-Strike, Valorant, Cyberpunk, cs2.exe)...")
        self.search_input.textChanged.connect(self.filter_game_rows)
        bar.addWidget(self.search_input, stretch=1)

        self.filter_pill_btns = {}
        for f_key, f_lbl in [("all", "Tümü"), ("bound", "🔗 Bağlı"), ("unbound", "⚪ Bağsız"), ("steam", "Steam"), ("epic", "Epic")]:
            b_f = QPushButton(f_lbl)
            b_f.setCheckable(True)
            b_f.setChecked(f_key == "all")
            b_f.setStyleSheet("""
                QPushButton { background: #131b2e; color: #c4c5d9; border: 1px solid rgba(68, 70, 86, 0.35); border-radius: 6px; padding: 6px 10px; font-size: 11px; font-weight: 700; }
                QPushButton:checked { background: #8083ff; color: #07006c; border: 1px solid #c0c1ff; font-weight: 800; }
            """)
            b_f.clicked.connect(lambda checked, k=f_key: self.set_quick_filter_mode(k))
            self.filter_pill_btns[f_key] = b_f
            bar.addWidget(b_f)

        btn_rescan = QPushButton("🔄 Yüklü Oyunları Tara")
        btn_rescan.setStyleSheet("background: #171f33; color: #38bdf8; font-weight: 700; border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 6px; padding: 6px 12px;")
        btn_rescan.clicked.connect(self.rescan_system_games)
        bar.addWidget(btn_rescan)

        btn_add_exe = QPushButton("📂 Oyun (.exe) Seç")
        btn_add_exe.setStyleSheet("background: #8083ff; color: #07006c; font-weight: 800; border: none; border-radius: 6px; padding: 6px 12px;")
        btn_add_exe.clicked.connect(self.add_custom_game_exe)
        bar.addWidget(btn_add_exe)

        btn_add_running = QPushButton("⚡ Açık Uygulamalardan Ekle")
        btn_add_running.setStyleSheet("background: #171f33; color: #4edea3; font-weight: 700; border: 1px solid rgba(78, 222, 163, 0.35); border-radius: 6px; padding: 6px 12px;")
        btn_add_running.clicked.connect(self.add_from_running_processes)
        bar.addWidget(btn_add_running)

        main_layout.addLayout(bar)

        # Main Body: Left Scrollable Game List + Right Live Theme Preview
        body = QHBoxLayout()
        body.setSpacing(12)

        # Left Scroll Area
        left_col = QVBoxLayout()
        self.lbl_count = QLabel("Yüklü oyunlar taranıyor...")
        self.lbl_count.setStyleSheet("color: #c0c1ff; font-size: 11px; font-weight: 800; letter-spacing: 0.4px;")
        left_col.addWidget(self.lbl_count)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid rgba(68, 70, 86, 0.35); border-radius: 10px; background: #060e20; }")
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: #060e20;")
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setSpacing(8)
        self.list_layout.setContentsMargins(10, 10, 10, 10)
        self.scroll_area.setWidget(self.scroll_content)
        left_col.addWidget(self.scroll_area, stretch=1)

        body.addLayout(left_col, stretch=3)

        # Right Preview Panel — Stitch Selected Game Inspector Card (#131b2e)
        right_frame = QFrame()
        right_frame.setFixedWidth(265)
        right_frame.setStyleSheet("QFrame { background: #131b2e; border: 1px solid rgba(68, 70, 86, 0.35); border-radius: 10px; }")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)

        lbl_prev_hdr = QLabel("👁 BAĞLI TEMA ÖNİZLEMESİ")
        lbl_prev_hdr.setAlignment(Qt.AlignCenter)
        lbl_prev_hdr.setStyleSheet("font-size: 11px; font-weight: 800; color: #c0c1ff; letter-spacing: 0.5px; border: none;")
        right_layout.addWidget(lbl_prev_hdr)

        self.lbl_preview_img = QLabel("Önizlemek için bir oyuna\ntema seçin")
        self.lbl_preview_img.setFixedSize(215, 390)
        self.lbl_preview_img.setAlignment(Qt.AlignCenter)
        self.lbl_preview_img.setStyleSheet("background: #060e20; border: 1px solid rgba(68, 70, 86, 0.45); border-radius: 8px; color: #8e90a2; font-size: 11px;")
        right_layout.addWidget(self.lbl_preview_img, alignment=Qt.AlignCenter)

        self.lbl_preview_name = QLabel("Henüz oyun seçilmedi")
        self.lbl_preview_name.setAlignment(Qt.AlignCenter)
        self.lbl_preview_name.setWordWrap(True)
        self.lbl_preview_name.setStyleSheet("background: #060e20; color: #4edea3; font-weight: 800; font-size: 11px; border: 1px solid rgba(78, 222, 163, 0.3); border-radius: 6px; padding: 6px;")
        right_layout.addWidget(self.lbl_preview_name)

        right_layout.addStretch()
        body.addWidget(right_frame)

        main_layout.addLayout(body, stretch=1)

        # Bottom Save / Close Bar
        ftr = QHBoxLayout()
        lbl_tip = QLabel("💡 İpucu: İstediğiniz oyunun karşısındaki açılır menüden bir tema seçtiğinizde otomatik olarak eşleştirilir.")
        lbl_tip.setStyleSheet("color: #8e90a2; font-size: 11px;")
        ftr.addWidget(lbl_tip)
        ftr.addStretch()

        btn_save = QPushButton("✅ Oyun Profillerini Kaydet ve Uygula")
        btn_save.setStyleSheet("background: #00885d; color: #ffffff; font-weight: 800; padding: 8px 20px; font-size: 12px; border: 1px solid #4edea3; border-radius: 7px;")
        btn_save.clicked.connect(self.save_and_close)
        ftr.addWidget(btn_save)

        btn_cancel = QPushButton("❌ Kapat")
        btn_cancel.setStyleSheet("background: #171f33; color: #c4c5d9; font-weight: 700; padding: 8px 16px; font-size: 12px; border: 1px solid rgba(68, 70, 86, 0.4); border-radius: 7px;")
        btn_cancel.clicked.connect(self.reject)
        ftr.addWidget(btn_cancel)

        main_layout.addLayout(ftr)

    def rescan_system_games(self):
        scanned = scan_installed_games()
        merged = {}

        # 1. Include all saved user bindings first so custom games are always preserved
        for exe_k, prof in self.game_profiles.items():
            merged[exe_k] = {
                'game_name': prof.get('game_name', exe_k),
                'exe_name': exe_k,
                'exe_path': prof.get('exe_path', ''),
                'platform': prof.get('platform', 'Özel Oyun'),
                'theme_name': prof.get('theme_name', '')
            }

        # 2. Merge auto-discovered games from Steam, Epic, Riot, Xbox, etc.
        for g in scanned:
            exe_k = g['exe_name']
            if exe_k in merged:
                if not merged[exe_k].get('exe_path') and g.get('exe_path'):
                    merged[exe_k]['exe_path'] = g['exe_path']
                if merged[exe_k].get('platform') in ('', 'Özel Oyun') and g.get('platform'):
                    merged[exe_k]['platform'] = g['platform']
            else:
                merged[exe_k] = {
                    'game_name': g['game_name'],
                    'exe_name': exe_k,
                    'exe_path': g.get('exe_path', ''),
                    'platform': g.get('platform', 'PC'),
                    'theme_name': ''
                }

        # Sort: Bound games first, then alphabetically by game_name
        self.discovered_games = sorted(
            merged.values(),
            key=lambda x: (0 if x.get('theme_name') else 1, x.get('game_name', '').lower())
        )
        self.rebuild_game_list_ui()

    def rebuild_game_list_ui(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.row_widgets.clear()

        bound_count = sum(1 for g in self.discovered_games if g.get('theme_name'))
        self.lbl_count.setText(
            f"📦 Sistemde {len(self.discovered_games)} oyun listeleniyor  |  🔗 Temaya Bağlı Oyun Sayısı: {bound_count}"
        )

        platform_colors = {
            'Steam': '#0284c7',
            'Epic Games': '#475569',
            'Riot Games': '#e11d48',
            'Xbox / PC Game Pass': '#16a34a',
            'Battle.net': '#2563eb',
            'Ubisoft': '#4f46e5',
            'EA App': '#ea580c',
            'GOG': '#7c3aed',
        }

        for game in self.discovered_games:
            exe_name = game['exe_name']
            game_name = game['game_name']
            plat = game.get('platform', 'PC')
            bound_theme = game.get('theme_name', '')

            card = QFrame()
            is_bound = bool(bound_theme)
            border_col = "#4edea3" if is_bound else "rgba(68, 70, 86, 0.35)"
            bg_col = "#171f33" if is_bound else "#131b2e"
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_col};
                    border: 1px solid {border_col};
                    border-left: 3px solid {border_col};
                    border-radius: 8px;
                }}
            """)
            row = QHBoxLayout(card)
            row.setContentsMargins(10, 8, 10, 8)
            row.setSpacing(10)

            # Stitch 38x38 Game Initials Box (#060e20)
            initials = "".join([w[0].upper() for w in game_name.split() if w and w[0].isalnum()][:2]) or "GM"
            lbl_initials = QLabel(initials)
            lbl_initials.setFixedSize(38, 38)
            lbl_initials.setAlignment(Qt.AlignCenter)
            lbl_initials.setStyleSheet(
                f"background: #060e20; color: {'#4edea3' if is_bound else '#c0c1ff'}; "
                f"border: 1px solid {'rgba(78, 222, 163, 0.4)' if is_bound else 'rgba(192, 193, 255, 0.25)'}; "
                f"border-radius: 7px; font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 12px; font-weight: 800;"
            )
            row.addWidget(lbl_initials)

            # Platform badge
            badge_col = platform_colors.get(plat, '#6366f1')
            lbl_plat = QLabel(plat)
            lbl_plat.setFixedWidth(92)
            lbl_plat.setAlignment(Qt.AlignCenter)
            lbl_plat.setStyleSheet(f"background: {badge_col}; color: white; font-size: 10px; font-weight: 800; padding: 4px 6px; border-radius: 5px; border: none;")
            row.addWidget(lbl_plat)

            # Game Title & Exe Info
            info_col = QVBoxLayout()
            info_col.setSpacing(2)
            lbl_title = QLabel(game_name)
            lbl_title.setStyleSheet("font-size: 12px; font-weight: 800; color: #dae2fd; border: none;")
            lbl_exe = QLabel(f"⚙ {exe_name}" + (f"  •  ⇄ BOUND: {bound_theme}" if is_bound else ""))
            lbl_exe.setStyleSheet(f"font-size: 10px; color: {'#4edea3' if is_bound else '#8e90a2'}; font-family: 'JetBrains Mono', 'Consolas', monospace; border: none;")
            info_col.addWidget(lbl_title)
            info_col.addWidget(lbl_exe)
            row.addLayout(info_col, stretch=1)

            # Theme selector dropdown for this game
            combo = QComboBox()
            combo.setMinimumWidth(175)
            combo.addItem("⚪ Tema Bağlı Değil (Varsayılan)", "")
            sel_idx = 0
            for i_t, t_item in enumerate(self.preset_themes, start=1):
                t_name = t_item['name']
                combo.addItem(f"🎨 {t_name}", t_name)
                if bound_theme and t_name.lower() == bound_theme.lower():
                    sel_idx = i_t
            combo.setCurrentIndex(sel_idx)
            combo.currentIndexChanged.connect(
                lambda idx, ex=exe_name, gn=game_name, pl=plat, ep=game.get('exe_path', ''), cb=combo, crd=card:
                self.on_game_theme_changed(ex, gn, pl, ep, cb, crd)
            )
            row.addWidget(combo)

            # Test / Preview button
            btn_test = QPushButton("👁 Önizle")
            btn_test.setStyleSheet("background: #060e20; color: #c0c1ff; border: 1px solid rgba(192, 193, 255, 0.3); border-radius: 6px; padding: 5px 10px; font-size: 10px; font-weight: 800;")
            btn_test.setToolTip("Bu oyuna bağlı temayı sağ panelde önizle")
            btn_test.clicked.connect(lambda _, cb=combo, gn=game_name: self.preview_theme_ByName(cb.currentData(), gn))
            row.addWidget(btn_test)

            self.list_layout.addWidget(card)
            self.row_widgets.append((card, f"{game_name} {exe_name} {plat}".lower(), game))

        self.list_layout.addStretch()
        self.filter_game_rows(self.search_input.text())
        first_bound = next((g for g in self.discovered_games if g.get('theme_name')), None)
        if first_bound:
            self.preview_theme_ByName(first_bound['theme_name'], first_bound.get('game_name', ''))

    def on_game_theme_changed(self, exe_name, game_name, platform, exe_path, combo, card_widget):
        chosen_theme = str(combo.currentData() or '').strip()
        if chosen_theme:
            self.game_profiles[exe_name] = {
                'game_name': game_name,
                'exe_name': exe_name,
                'exe_path': exe_path,
                'platform': platform,
                'theme_name': chosen_theme
            }
            card_widget.setStyleSheet("QFrame { background-color: #171f33; border: 1px solid #4edea3; border-left: 3px solid #4edea3; border-radius: 8px; }")
            self.preview_theme_ByName(chosen_theme, game_name)
        else:
            self.game_profiles.pop(exe_name, None)
            card_widget.setStyleSheet("QFrame { background-color: #131b2e; border: 1px solid rgba(68, 70, 86, 0.35); border-left: 3px solid rgba(68, 70, 86, 0.35); border-radius: 8px; }")

        for g in self.discovered_games:
            if g['exe_name'] == exe_name:
                g['theme_name'] = chosen_theme
                break

        bound_count = sum(1 for g in self.discovered_games if g.get('theme_name'))
        self.lbl_count.setText(
            f"📦 Sistemde {len(self.discovered_games)} oyun listeleniyor  |  🔗 Temaya Bağlı Oyun Sayısı: {bound_count}"
        )
        self.filter_game_rows(self.search_input.text())

    def preview_theme_ByName(self, theme_name, game_name=""):
        if not theme_name:
            self.lbl_preview_img.setText("Bu oyun için henüz\nözel bir tema seçilmedi")
            self.lbl_preview_name.setText("")
            return
        try:
            from main_gui import load_preset_theme_data, pil_to_pixmap
            from hardware_driver import HardwareDriver
            from PIL import Image
            matched = next((t for t in self.preset_themes if t['name'].lower() == theme_name.lower()), None)
            if not matched:
                return
            t_data = load_preset_theme_data(matched)
            if not t_data:
                return
            tw = max(64, min(4096, int(t_data.get('width', 320) or 320)))
            th = max(64, min(4096, int(t_data.get('height', 1480) or 1480)))
            if not hasattr(self, '_preview_hw') or self._preview_hw is None:
                self._preview_hw = HardwareDriver(width=tw, height=th)
            else:
                self._preview_hw.reset_background_media()
                self._preview_hw.set_resolution(tw, th)
            dummy_metrics = {'cpu_temp': '52°C', 'gpu_temp': '61°C', 'gpu_load': '88%', 'cpu_load': '45%', 'game_fps': '165 FPS'}
            try:
                pil_img = self._preview_hw.render_theme_frame(t_data, dummy_metrics, for_hardware=False)
            finally:
                self._preview_hw.reset_background_media()
            box_w, box_h = 190, 420
            scale = min(float(box_w) / max(1, tw), float(box_h) / max(1, th))
            sw = max(1, int(tw * scale))
            sh = max(1, int(th * scale))
            scaled = pil_img.resize((sw, sh), Image.Resampling.BILINEAR)
            canvas_pil = Image.new('RGB', (box_w, box_h), (6, 14, 32))
            canvas_pil.paste(scaled, ((box_w - sw) // 2, (box_h - sh) // 2))
            self.lbl_preview_img.setPixmap(pil_to_pixmap(canvas_pil))
            self.lbl_preview_name.setText(f"{game_name}\n➔ 🎨 {theme_name}")
        except Exception as e:
            print("Game theme preview note:", e)

    def set_quick_filter_mode(self, mode_key):
        self.active_quick_filter = str(mode_key or "all")
        for k, btn in getattr(self, 'filter_pill_btns', {}).items():
            btn.setChecked(k == self.active_quick_filter)
        self.filter_game_rows(self.search_input.text())

    def filter_game_rows(self, query_text=""):
        q = str(query_text or '').strip().lower()
        mode = getattr(self, 'active_quick_filter', 'all')
        for row_tuple in self.row_widgets:
            card = row_tuple[0]
            search_blob = row_tuple[1]
            game_obj = row_tuple[2] if len(row_tuple) > 2 else {}
            is_bound = bool(game_obj.get('theme_name'))
            plat_l = str(game_obj.get('platform', '')).lower()
            matches_q = (not q) or (q in search_blob)
            matches_m = True
            if mode == "bound":
                matches_m = is_bound
            elif mode == "unbound":
                matches_m = not is_bound
            elif mode == "steam":
                matches_m = "steam" in plat_l
            elif mode == "epic":
                matches_m = "epic" in plat_l
            card.setVisible(matches_q and matches_m)

    def add_custom_game_exe(self):
        exe_file, _ = QFileDialog.getOpenFileName(
            self,
            "Oyunun Çalıştırılabilir Dosyasını (.exe) Seçin",
            "C:\\",
            "Oyun Çalıştırılabilir Dosyası (*.exe)"
        )
        if not exe_file or not _is_safe_local_file_path(exe_file) or not os.path.isfile(exe_file):
            return
        exe_name = sanitize_exe_name(exe_file)
        if not exe_name:
            QMessageBox.warning(self, "Geçersiz Dosya", "Seçilen dosya geçerli bir .exe adı taşımıyor.")
            return

        default_title = os.path.splitext(os.path.basename(exe_file))[0].replace('_', ' ').title()
        title, ok = QInputDialog.getText(self, "Oyun Adı", f"'{exe_name}' için görünür oyun adı:", text=default_title)
        if not ok:
            return
        clean_title = (title.strip() or default_title)[:80]

        default_theme = self.preset_themes[0]['name'] if self.preset_themes else ''
        self.game_profiles[exe_name] = {
            'game_name': clean_title,
            'exe_name': exe_name,
            'exe_path': os.path.abspath(exe_file),
            'platform': 'Özel .exe',
            'theme_name': default_theme
        }
        self.rescan_system_games()
        if default_theme:
            self.preview_theme_ByName(default_theme, clean_title)

    def add_from_running_processes(self):
        """Lists currently running applications so the user can pick an open game in 1 click."""
        ignore_procs = {
            'svchost.exe', 'explorer.exe', 'system', 'registry', 'smss.exe', 'csrss.exe',
            'wininit.exe', 'services.exe', 'lsass.exe', 'winlogon.exe', 'dwm.exe',
            'taskhostw.exe', 'sihost.exe', 'fontdrvhost.exe', 'ctfmon.exe', 'conhost.exe',
            'runtimebroker.exe', 'searchhost.exe', 'startmenuexperiencehost.exe',
            'textinputhost.exe', 'applicationframehost.exe', 'dllhost.exe', 'WmiPrvSE.exe',
            'python.exe', 'pythonw.exe', 'powershell.exe', 'cmd.exe', 'securityhealthservice.exe',
            'audiodg.exe', 'spoolsv.exe'
        }
        running_exes = {}
        try:
            for p in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    pname = sanitize_exe_name(p.info.get('name') or '')
                    if not pname or pname in ignore_procs:
                        continue
                    pexe = str(p.info.get('exe') or '')
                    if pexe and r'\windows\system32' in pexe.lower():
                        continue
                    running_exes[pname] = pexe
                except Exception:
                    pass
        except Exception:
            pass

        if not running_exes:
            QMessageBox.information(self, "Bilgi", "Listelenecek aktif uygulama bulunamadı.")
            return

        items = sorted(running_exes.keys())
        chosen, ok = QInputDialog.getItem(
            self,
            "⚡ Açık Uygulamalardan Oyun Seç",
            "Listeden temaya bağlamak istediğiniz oyunun (.exe) sürecini seçin:",
            items,
            0,
            False
        )
        if ok and chosen:
            exe_name = sanitize_exe_name(chosen)
            if exe_name:
                default_title = os.path.splitext(exe_name)[0].replace('_', ' ').title()
                default_theme = self.preset_themes[0]['name'] if self.preset_themes else ''
                self.game_profiles[exe_name] = {
                    'game_name': default_title,
                    'exe_name': exe_name,
                    'exe_path': running_exes.get(exe_name, ''),
                    'platform': 'Açık Süreç',
                    'theme_name': default_theme
                }
                self.rescan_system_games()
                if default_theme:
                    self.preview_theme_ByName(default_theme, default_title)

    def save_and_close(self):
        # Clean up only profiles that have a valid theme_name selected
        clean_profiles = {}
        for exe_k, prof in self.game_profiles.items():
            clean_k = sanitize_exe_name(exe_k)
            t_name = str(prof.get('theme_name') or '').strip()
            if clean_k and t_name:
                clean_profiles[clean_k] = {
                    'game_name': str(prof.get('game_name') or clean_k)[:80],
                    'exe_name': clean_k,
                    'exe_path': str(prof.get('exe_path') or '')[:260],
                    'platform': str(prof.get('platform') or 'PC')[:40],
                    'theme_name': t_name[:80]
                }

        self.gui.app_settings['game_profiles'] = clean_profiles
        self.gui.app_settings['auto_game_theme_enabled'] = self.chk_enable_game_profiles.isChecked()
        self.gui.app_settings['keep_game_theme_on_alttab'] = self.chk_keep_on_alttab.isChecked()
        self.gui.app_settings['auto_game_theme_name'] = str(self.combo_fallback_theme.currentData() or '').strip()
        self.gui.save_app_settings()
        self.profiles_updated_signal.emit()
        self.accept()
