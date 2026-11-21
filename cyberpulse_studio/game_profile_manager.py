import os
import re
import json
import ctypes
import sqlite3
import xml.etree.ElementTree as ET
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
MAX_SCAN_DIRS = 500                   # Cap number of game folders scanned
MAX_FILES_PER_GAME_DIR = 120          # Cap files inspected per game folder

# Known non-game helper / installer / crash-reporter executables to ignore when picking a game's main .exe
NON_GAME_EXE_KEYWORDS = (
    'unins', 'crash', 'setup', 'redist', 'dxsetup', 'vcredist', 'vc_redist',
    'easyanticheat', 'eac_', 'battleye', 'beclient', 'beservice', 'launcher_helper',
    'unitycrashhandler', 'unrealcefsubprocess', 'cefprocess', 'crs-handler',
    'dotnet', 'directx', 'physx', 'cleanup', 'touchup', 'activation', 'updater',
    'update', 'patcher', 'repair', 'benchmark', 'config', 'settings', 'server',
    'dedicated', 'modtools', 'editor', 'sdk', 'compiler', 'steamerrorreporter',
    'socialclubhelper', 'rockstarservice', 'rockstarsteamhelper', 'eaanticheat',
    'link2ea', 'activationui', 'uplaywebcore', 'ubisoftgamelauncher', 'riotclient',
    'gamelaunchhelper', 'zfgamebrowser', 'qtwebengineprocess', 'webhelper',
    'bugreport', 'errorreporter', 'prerequisite', 'notification_helper',
    'battle.net', 'bnetlauncher', 'epicgameslauncher', 'eadesktop', 'eabackgroundservice',
    'galaxyclient', 'goggalaxy', 'steamservice', 'steamwebhelper'
)

# Priority subdirectories where modern engines (Unreal, REDengine, Frostbite, Source 2, Unity) store main binaries
PRIORITY_ENGINE_SUBDIRS = {
    'binaries', 'win64', 'x64', 'game', 'bin', 'retail', 'content',
    'shootergame', 'engine', 'client', 'release', 'win32'
}

SKIP_SUBDIRS = {
    'redist', '_commonredist', 'directx', 'vcredist', 'support', 'installers',
    'easyanticheat', 'battleye', 'mono', 'logs', 'crashes', '__installer',
    'shader', 'shadercache', 'movies', 'audio', 'sound', 'localization',
    'locales', 'licenses', 'docs', 'manual', 'bonus', 'ost', 'soundtrack',
    'mods', 'workshop', 'plugins', 'streamingassets', 'paks', 'cooked'
}

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


def _find_best_game_exe_in_folder(folder_path, game_title="", max_depth=4):
    """
    Scans a game installation folder (up to depth 4 for Unreal Engine Binaries/Win64 etc.)
    to find the primary game .exe. Uses file size and title similarity heuristics while
    ignoring crash handlers, anti-cheat stubs, & redistributables.
    """
    if not folder_path or not _is_safe_local_file_path(folder_path) or not os.path.isdir(folder_path):
        return None, None

    candidates = []
    title_tokens = [t.lower() for t in re.split(r'[^a-zA-Z0-9]+', game_title or '') if len(t) >= 3]
    acronym = "".join([w[0].lower() for w in re.split(r'[^a-zA-Z0-9]+', game_title or '') if w])
    folder_abs = os.path.abspath(folder_path)
    inspected_files = [0]

    def _scan_dir(cur_dir, depth):
        if depth > max_depth or inspected_files[0] >= MAX_FILES_PER_GAME_DIR:
            return
        try:
            entries = os.scandir(cur_dir)
        except Exception:
            return
        with entries:
            count = 0
            subdirs_to_visit = []
            for entry in entries:
                count += 1
                if count > MAX_FILES_PER_GAME_DIR or inspected_files[0] >= MAX_FILES_PER_GAME_DIR:
                    break
                try:
                    if entry.is_symlink():
                        continue
                    st = entry.stat(follow_symlinks=False)
                    # 🔒 SECURITY: Skip NTFS reparse points / directory junctions (FILE_ATTRIBUTE_REPARSE_POINT = 0x400)
                    if getattr(st, 'st_file_attributes', 0) & 0x400:
                        continue
                    if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith('.exe'):
                        inspected_files[0] += 1
                        ename_lower = entry.name.lower()
                        if any(kw in ename_lower for kw in NON_GAME_EXE_KEYWORDS):
                            continue
                        if not VALID_EXE_REGEX.match(entry.name):
                            continue
                        sz = st.st_size
                        if sz < 100 * 1024:  # Ignore tiny stub exes < 100 KB
                            continue
                        # Score candidate by size + name match + shipping binary bonus
                        score = min(sz / (1024.0 * 1024.0), 160.0)
                        stem = os.path.splitext(ename_lower)[0]
                        if 'launcher' in ename_lower:
                            score -= 130.0
                        if 'shipping' in ename_lower:
                            score += 95.0
                        if 'win64' in ename_lower or 'x64' in ename_lower:
                            score += 25.0
                        for tok in title_tokens:
                            if tok in stem:
                                score += 45.0
                        if len(acronym) >= 3 and (stem == acronym or stem.startswith(acronym)):
                            score += 40.0
                        if depth == 0:
                            score += 18.0
                        candidates.append((score, entry.name, os.path.abspath(entry.path)))
                    elif entry.is_dir(follow_symlinks=False) and depth < max_depth:
                        dname = entry.name.lower()
                        if dname in SKIP_SUBDIRS or dname.startswith('.'):
                            continue
                        # Prioritize engine binary directories even at deeper levels
                        is_prio = (dname in PRIORITY_ENGINE_SUBDIRS) or any(tok in dname for tok in title_tokens)
                        if depth < 2 or is_prio:
                            subdirs_to_visit.append((0 if is_prio else 1, entry.path))
                except Exception:
                    pass

            subdirs_to_visit.sort(key=lambda x: x[0])
            for _, s_path in subdirs_to_visit[:25]:
                _scan_dir(s_path, depth + 1)

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
                if any(skip in g_name.lower() for skip in (
                    "steamworks common redistributables", "proton", "steam linux runtime",
                    "soundtrack", "dedicated server", "wallpaper engine", "driver booster",
                    "lossless scaling", "soundpad", "borderless gaming", "crosshair x"
                )):
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


def _get_local_drive_roots():
    """Returns a list of valid local drive mountpoints (e.g. ['C:\\', 'D:\\', 'L:\\'])."""
    roots = []
    try:
        for part in psutil.disk_partitions(all=False):
            mp = part.mountpoint
            if mp and os.path.isdir(mp):
                roots.append(mp)
    except Exception:
        pass
    for drv in ("C:\\", "D:\\", "E:\\", "F:\\", "G:\\", "H:\\", "L:\\"):
        if drv not in roots and os.path.isdir(drv):
            roots.append(drv)
    return roots


def _scan_xbox_gamepass_games():
    """
    Scans Xbox / PC Game Pass / Microsoft Store games:
    - Reads .GamingRoot on every drive to locate custom Xbox library folders
    - Inspects XboxGames, WindowsApps (accessible game subfolders), and ModifiableWindowsApps
    - Parses MicrosoftGame.Config and AppxManifest.xml for exact game titles and primary executables
    """
    games = []
    xbox_roots = set()
    for mp in _get_local_drive_roots():
        for default_sub in ("XboxGames", "PC Game Pass", r"Games\XboxGames", r"Program Files\ModifiableWindowsApps"):
            cand = os.path.join(mp, default_sub)
            if os.path.isdir(cand) and _is_safe_local_file_path(cand):
                xbox_roots.add(os.path.normpath(cand))
        # Parse .GamingRoot binary pointer file (UTF-16LE path after 8-byte RGBX header)
        groot_file = os.path.join(mp, ".GamingRoot")
        if os.path.isfile(groot_file) and _is_safe_local_file_path(groot_file):
            try:
                with open(groot_file, "rb") as f:
                    raw = f.read(1024)
                if len(raw) > 8:
                    rel_path = raw[8:].decode("utf-16-le", errors="ignore").strip("\x00").strip("\\/")
                    if rel_path:
                        custom_xbox_dir = os.path.normpath(os.path.join(mp, rel_path))
                        if _is_safe_local_file_path(custom_xbox_dir) and os.path.isdir(custom_xbox_dir):
                            xbox_roots.add(custom_xbox_dir)
            except Exception:
                pass

    seen_dirs = set()
    for xroot in sorted(xbox_roots):
        try:
            subdirs = os.listdir(xroot)[:100]
        except Exception:
            continue
        for sub in subdirs:
            game_dir = os.path.abspath(os.path.join(xroot, sub))
            if not os.path.isdir(game_dir) or game_dir.lower() in seen_dirs:
                continue
            seen_dirs.add(game_dir.lower())
            content_dir = os.path.join(game_dir, "Content")
            scan_base = content_dir if os.path.isdir(content_dir) else game_dir

            disp_name = sub
            exe_name = ""
            exe_path = ""

            # Check MicrosoftGame.Config
            mgc_path = os.path.join(scan_base, "MicrosoftGame.Config")
            if not os.path.isfile(mgc_path):
                mgc_path = os.path.join(game_dir, "MicrosoftGame.Config")
            if os.path.isfile(mgc_path) and _is_safe_local_file_path(mgc_path):
                try:
                    with open(mgc_path, "r", encoding="utf-8", errors="ignore") as f:
                        xml_txt = f.read(MAX_MANIFEST_READ_BYTES)
                    root = ET.fromstring(xml_txt)
                    sv = root.find(".//ShellVisuals")
                    if sv is not None and sv.attrib.get("DefaultDisplayName"):
                        disp_name = sv.attrib.get("DefaultDisplayName").strip()
                    for ex_node in root.findall(".//Executable"):
                        raw_ex = ex_node.attrib.get("Name", "").strip()
                        clean_ex = sanitize_exe_name(raw_ex)
                        if clean_ex and not any(k in clean_ex for k in NON_GAME_EXE_KEYWORDS):
                            cand_p = os.path.abspath(os.path.join(scan_base, raw_ex))
                            if _is_safe_local_file_path(cand_p) and os.path.commonpath([game_dir, cand_p]) == game_dir and os.path.isfile(cand_p):
                                exe_name = clean_ex
                                exe_path = cand_p
                                break
                except Exception:
                    pass

            if not exe_name:
                exe_name, exe_path = _find_best_game_exe_in_folder(scan_base, disp_name)
            if exe_name:
                games.append({
                    'game_name': disp_name[:80],
                    'exe_name': exe_name,
                    'exe_path': exe_path or "",
                    'platform': 'Xbox / PC Game Pass'
                })
    return games


def _scan_riot_games():
    """
    Scans Riot Games installations:
    - C:\\ProgramData\\Riot Games\\Metadata\\*\\*.product_settings.yaml
    - C:\\ProgramData\\Riot Games\\RiotClientInstalls.json
    - Riot Games folders across all drives (VALORANT, League of Legends, Legends of Runeterra, 2XKO)
    """
    games = []
    riot_product_dirs = []
    meta_root = r"C:\ProgramData\Riot Games\Metadata"
    if os.path.isdir(meta_root):
        try:
            for prod_folder in os.listdir(meta_root):
                p_dir = os.path.join(meta_root, prod_folder)
                if not os.path.isdir(p_dir):
                    continue
                for fn in os.listdir(p_dir):
                    if fn.endswith(".product_settings.yaml"):
                        ypath = os.path.join(p_dir, fn)
                        if _is_safe_local_file_path(ypath) and os.path.isfile(ypath):
                            try:
                                with open(ypath, "r", encoding="utf-8", errors="ignore") as f:
                                    ycontent = f.read(65536)
                                m = re.search(r'product_install_full_path:\s*"?([^"\r\n]+)"?', ycontent)
                                if m:
                                    inst_p = os.path.normpath(m.group(1).strip())
                                    if _is_safe_local_file_path(inst_p) and os.path.isdir(inst_p):
                                        riot_product_dirs.append(inst_p)
                            except Exception:
                                pass
        except Exception:
            pass

    for mp in _get_local_drive_roots():
        rg_root = os.path.join(mp, "Riot Games")
        if os.path.isdir(rg_root) and _is_safe_local_file_path(rg_root):
            try:
                for sub in os.listdir(rg_root):
                    if sub.lower() == "riot client":
                        continue
                    sub_p = os.path.join(rg_root, sub)
                    if os.path.isdir(sub_p):
                        riot_product_dirs.append(sub_p)
            except Exception:
                pass

    seen_dirs = set()
    for pdir in riot_product_dirs:
        p_abs = os.path.abspath(pdir)
        if p_abs.lower() in seen_dirs or not os.path.isdir(p_abs):
            continue
        seen_dirs.add(p_abs.lower())
        base_name = os.path.basename(p_abs)
        low_path = p_abs.lower()

        # Known Riot game direct binary layouts
        if "valorant" in low_path:
            title = "VALORANT"
            ship_p = os.path.join(p_abs, "ShooterGame", "Binaries", "Win64", "VALORANT-Win64-Shipping.exe")
            if not os.path.isfile(ship_p):
                ship_p = os.path.join(p_abs, "live", "ShooterGame", "Binaries", "Win64", "VALORANT-Win64-Shipping.exe")
            if os.path.isfile(ship_p):
                games.append({'game_name': title, 'exe_name': 'valorant-win64-shipping.exe', 'exe_path': ship_p, 'platform': 'Riot Games'})
                continue
        elif "league of legends" in low_path:
            title = "League of Legends"
            lol_p = os.path.join(p_abs, "Game", "League of Legends.exe")
            if os.path.isfile(lol_p):
                games.append({'game_name': title, 'exe_name': 'league of legends.exe', 'exe_path': lol_p, 'platform': 'Riot Games'})
                continue
        elif "lor" in low_path or "bacon" in low_path or "runeterra" in low_path:
            title = "Legends of Runeterra"
        else:
            title = "VALORANT" if base_name.lower() == "live" and "valorant" in low_path else base_name

        exe_name, exe_path = _find_best_game_exe_in_folder(p_abs, title)
        if exe_name:
            games.append({
                'game_name': title[:80],
                'exe_name': exe_name,
                'exe_path': exe_path or "",
                'platform': 'Riot Games'
            })
    return games


def _scan_ubisoft_games():
    """
    Scans Ubisoft Connect / Uplay games via Windows Registry (SOFTWARE\\WOW6432Node\\Ubisoft\\Launcher\\Installs)
    and %LOCALAPPDATA%\\Ubisoft Game Launcher\\settings.yml + game directories across drives.
    """
    games = []
    install_dirs = []
    try:
        import winreg
        for hive, subkey in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Ubisoft\Launcher\Installs"),
        ]:
            try:
                with winreg.OpenKey(hive, subkey) as k:
                    i = 0
                    while i < 200:
                        try:
                            app_id = winreg.EnumKey(k, i)
                            i += 1
                            with winreg.OpenKey(k, app_id) as sk:
                                inst_dir, _ = winreg.QueryValueEx(sk, "InstallDir")
                                if inst_dir and isinstance(inst_dir, str):
                                    norm_d = os.path.normpath(inst_dir.strip())
                                    if _is_safe_local_file_path(norm_d) and os.path.isdir(norm_d):
                                        install_dirs.append((os.path.basename(norm_d), norm_d))
                        except OSError:
                            break
            except Exception:
                pass
    except Exception:
        pass

    # Check Ubisoft settings.yml for custom game_installation_path
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        ubi_yml = os.path.join(local_app, "Ubisoft Game Launcher", "settings.yml")
        if os.path.isfile(ubi_yml) and _is_safe_local_file_path(ubi_yml):
            try:
                with open(ubi_yml, "r", encoding="utf-8", errors="ignore") as f:
                    yml_txt = f.read(65536)
                m = re.search(r'game_installation_path:\s*"?([^"\r\n]+)"?', yml_txt)
                if m:
                    g_root = os.path.normpath(m.group(1).strip())
                    if _is_safe_local_file_path(g_root) and os.path.isdir(g_root):
                        for sub in os.listdir(g_root)[:80]:
                            sp = os.path.join(g_root, sub)
                            if os.path.isdir(sp):
                                install_dirs.append((sub, sp))
            except Exception:
                pass

    for mp in _get_local_drive_roots():
        for rel in (
            r"Program Files (x86)\Ubisoft\Ubisoft Game Launcher\games",
            r"Program Files\Ubisoft\Ubisoft Game Launcher\games",
            "Ubisoft Games",
            r"Games\Ubisoft"
        ):
            p = os.path.join(mp, rel)
            if os.path.isdir(p) and _is_safe_local_file_path(p):
                try:
                    for sub in os.listdir(p)[:80]:
                        sp = os.path.join(p, sub)
                        if os.path.isdir(sp):
                            install_dirs.append((sub, sp))
                except Exception:
                    pass

    seen = set()
    for title, folder in install_dirs:
        f_abs = os.path.abspath(folder)
        if f_abs.lower() in seen:
            continue
        seen.add(f_abs.lower())
        exe_name, exe_path = _find_best_game_exe_in_folder(f_abs, title)
        if exe_name:
            games.append({
                'game_name': title[:80],
                'exe_name': exe_name,
                'exe_path': exe_path or "",
                'platform': 'Ubisoft'
            })
    return games


def _scan_ea_origin_games():
    """
    Scans EA App / Origin games via Windows Registry (SOFTWARE\\WOW6432Node\\EA Games, Electronic Arts),
    __Installer\\installerdata.xml manifests, and EA Games / Origin Games folders across all drives.
    """
    games = []
    ea_folders = []
    try:
        import winreg
        for hive, base_key in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\EA Games"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EA Games"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Electronic Arts"),
        ]:
            try:
                with winreg.OpenKey(hive, base_key) as k:
                    i = 0
                    while i < 200:
                        try:
                            sub_name = winreg.EnumKey(k, i)
                            i += 1
                            with winreg.OpenKey(k, sub_name) as sk:
                                inst_dir = ""
                                disp_name = sub_name
                                for val_name in ("Install Dir", "InstallDir", "Path"):
                                    try:
                                        v, _ = winreg.QueryValueEx(sk, val_name)
                                        if v and isinstance(v, str):
                                            inst_dir = v.strip()
                                            break
                                    except Exception:
                                        pass
                                try:
                                    dn, _ = winreg.QueryValueEx(sk, "DisplayName")
                                    if dn and isinstance(dn, str):
                                        disp_name = dn.strip()
                                except Exception:
                                    pass
                                if inst_dir and _is_safe_local_file_path(inst_dir) and os.path.isdir(inst_dir):
                                    ea_folders.append((disp_name, os.path.normpath(inst_dir)))
                        except OSError:
                            break
            except Exception:
                pass
    except Exception:
        pass

    for mp in _get_local_drive_roots():
        for rel in (
            r"Program Files\EA Games",
            r"Program Files (x86)\Origin Games",
            "EA Games",
            "Origin Games",
            r"Games\EA Games"
        ):
            p = os.path.join(mp, rel)
            if os.path.isdir(p) and _is_safe_local_file_path(p):
                try:
                    for sub in os.listdir(p)[:80]:
                        sp = os.path.join(p, sub)
                        if os.path.isdir(sp):
                            ea_folders.append((sub, sp))
                except Exception:
                    pass

    seen = set()
    for title, folder in ea_folders:
        f_abs = os.path.abspath(folder)
        if f_abs.lower() in seen:
            continue
        seen.add(f_abs.lower())

        exe_name = ""
        exe_path = ""
        # Check __Installer/installerdata.xml for explicit runtime executable
        xml_p = os.path.join(f_abs, "__Installer", "installerdata.xml")
        if os.path.isfile(xml_p) and _is_safe_local_file_path(xml_p):
            try:
                with open(xml_p, "r", encoding="utf-8", errors="ignore") as f:
                    xml_txt = f.read(MAX_MANIFEST_READ_BYTES)
                for m in re.finditer(r'<filePath>([^<]+\.exe)</filePath>', xml_txt, re.IGNORECASE):
                    raw_rel = re.sub(r'^\[[^\]]+\]\\?', '', m.group(1).strip())
                    clean_ex = sanitize_exe_name(raw_rel)
                    if clean_ex and not any(k in clean_ex for k in NON_GAME_EXE_KEYWORDS) and 'trial' not in clean_ex:
                        cand_p = os.path.abspath(os.path.join(f_abs, raw_rel))
                        if _is_safe_local_file_path(cand_p) and os.path.commonpath([f_abs, cand_p]) == f_abs and os.path.isfile(cand_p):
                            exe_name = clean_ex
                            exe_path = cand_p
                            break
            except Exception:
                pass

        if not exe_name:
            exe_name, exe_path = _find_best_game_exe_in_folder(f_abs, title)
        if exe_name:
            games.append({
                'game_name': title[:80],
                'exe_name': exe_name,
                'exe_path': exe_path or "",
                'platform': 'EA App'
            })
    return games


def _scan_battlenet_games():
    """
    Scans Blizzard Battle.net games via %APPDATA%\\Battle.net\\Battle.net.config,
    Windows Uninstall Registry (Blizzard Entertainment), and Battle.net folders across drives.
    """
    games = []
    bnet_folders = []

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        cfg_path = os.path.join(appdata, "Battle.net", "Battle.net.config")
        if os.path.isfile(cfg_path) and _is_safe_local_file_path(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
                    cfg = json.load(f)
                client_block = cfg.get("Client", {}) if isinstance(cfg, dict) else {}
                inst_block = client_block.get("Install", {}) if isinstance(client_block, dict) else {}
                for k_name in ("DefaultInstallPath", "SavedInstallPath"):
                    p_val = str(inst_block.get(k_name) or "").strip()
                    if p_val and _is_safe_local_file_path(p_val) and os.path.isdir(p_val):
                        for sub in os.listdir(p_val)[:50]:
                            sp = os.path.join(p_val, sub)
                            if os.path.isdir(sp) and sub.lower() != "battle.net":
                                bnet_folders.append((sub, sp))
            except Exception:
                pass

    for mp in _get_local_drive_roots():
        for rel in (
            r"Program Files (x86)\Battle.net\Games",
            r"Program Files (x86)",
            "Battle.net",
            r"Games\Battle.net"
        ):
            p = os.path.join(mp, rel)
            if not os.path.isdir(p) or not _is_safe_local_file_path(p):
                continue
            if rel == r"Program Files (x86)":
                for known_bnet in ("Diablo IV", "Diablo III", "Diablo II Resurrected", "Overwatch", "World of Warcraft", "StarCraft II", "Hearthstone", "Heroes of the Storm", "Call of Duty"):
                    kp = os.path.join(p, known_bnet)
                    if os.path.isdir(kp):
                        bnet_folders.append((known_bnet, kp))
            else:
                try:
                    for sub in os.listdir(p)[:50]:
                        if sub.lower() == "battle.net":
                            continue
                        sp = os.path.join(p, sub)
                        if os.path.isdir(sp):
                            bnet_folders.append((sub, sp))
                except Exception:
                    pass

    seen = set()
    for title, folder in bnet_folders:
        f_abs = os.path.abspath(folder)
        if f_abs.lower() in seen:
            continue
        seen.add(f_abs.lower())
        # Check _retail_ subfolder for World of Warcraft / Overwatch
        retail_dir = os.path.join(f_abs, "_retail_")
        scan_dir = retail_dir if os.path.isdir(retail_dir) else f_abs
        exe_name, exe_path = _find_best_game_exe_in_folder(scan_dir, title)
        if exe_name:
            games.append({
                'game_name': title[:80],
                'exe_name': exe_name,
                'exe_path': exe_path or "",
                'platform': 'Battle.net'
            })
    return games


def _scan_gog_galaxy_games():
    """
    Scans GOG Galaxy games via Registry (SOFTWARE\\WOW6432Node\\GOG.com\\Games)
    and goggame-*.info JSON files in GOG Games folders.
    """
    games = []
    seen_dirs = set()
    try:
        import winreg
        for hive, base_key in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\GOG.com\Games"),
        ]:
            try:
                with winreg.OpenKey(hive, base_key) as k:
                    i = 0
                    while i < 300:
                        try:
                            gid = winreg.EnumKey(k, i)
                            i += 1
                            with winreg.OpenKey(k, gid) as sk:
                                g_name, _ = winreg.QueryValueEx(sk, "gameName")
                                g_path, _ = winreg.QueryValueEx(sk, "path")
                                g_exe = ""
                                try:
                                    g_exe, _ = winreg.QueryValueEx(sk, "exe")
                                except Exception:
                                    pass
                                if g_name and g_path and _is_safe_local_file_path(g_path) and os.path.isdir(g_path):
                                    p_abs = os.path.abspath(g_path)
                                    seen_dirs.add(p_abs.lower())
                                    exe_name = sanitize_exe_name(g_exe)
                                    exe_path = g_exe if (g_exe and _is_safe_local_file_path(g_exe) and os.path.isfile(g_exe)) else ""
                                    if not exe_name or any(kw in exe_name for kw in NON_GAME_EXE_KEYWORDS):
                                        exe_name, exe_path = _find_best_game_exe_in_folder(p_abs, str(g_name))
                                    if exe_name:
                                        games.append({
                                            'game_name': str(g_name).strip()[:80],
                                            'exe_name': exe_name,
                                            'exe_path': exe_path or "",
                                            'platform': 'GOG'
                                        })
                        except OSError:
                            break
            except Exception:
                pass
    except Exception:
        pass

    for mp in _get_local_drive_roots():
        for rel in ("GOG Games", r"Program Files (x86)\GOG Galaxy\Games", r"Games\GOG Games"):
            p = os.path.join(mp, rel)
            if os.path.isdir(p) and _is_safe_local_file_path(p):
                try:
                    for sub in os.listdir(p)[:80]:
                        sp = os.path.abspath(os.path.join(p, sub))
                        if os.path.isdir(sp) and sp.lower() not in seen_dirs:
                            seen_dirs.add(sp.lower())
                            exe_name, exe_path = _find_best_game_exe_in_folder(sp, sub)
                            if exe_name:
                                games.append({
                                    'game_name': sub[:80],
                                    'exe_name': exe_name,
                                    'exe_path': exe_path or "",
                                    'platform': 'GOG'
                                })
                except Exception:
                    pass
    return games


def _scan_rockstar_games():
    """
    Scans Rockstar Games Launcher titles via Registry (SOFTWARE\\WOW6432Node\\Rockstar Games)
    and Rockstar Games directories across drives.
    """
    games = []
    rstar_folders = []
    try:
        import winreg
        for hive, base_key in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Rockstar Games"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Rockstar Games"),
        ]:
            try:
                with winreg.OpenKey(hive, base_key) as k:
                    i = 0
                    while i < 50:
                        try:
                            sub_name = winreg.EnumKey(k, i)
                            i += 1
                            if sub_name.lower() in ("launcher", "rockstar games social club", "social club"):
                                continue
                            with winreg.OpenKey(k, sub_name) as sk:
                                for vname in ("InstallFolder", "InstallFolderEpic", "InstallDir"):
                                    try:
                                        inst_p, _ = winreg.QueryValueEx(sk, vname)
                                        if inst_p and isinstance(inst_p, str) and _is_safe_local_file_path(inst_p) and os.path.isdir(inst_p):
                                            rstar_folders.append((sub_name, os.path.normpath(inst_p)))
                                            break
                                    except Exception:
                                        pass
                        except OSError:
                            break
            except Exception:
                pass
    except Exception:
        pass

    for mp in _get_local_drive_roots():
        for rel in (r"Program Files\Rockstar Games", "Rockstar Games", r"Games\Rockstar Games"):
            p = os.path.join(mp, rel)
            if os.path.isdir(p) and _is_safe_local_file_path(p):
                try:
                    for sub in os.listdir(p)[:40]:
                        if sub.lower() in ("launcher", "social club"):
                            continue
                        sp = os.path.join(p, sub)
                        if os.path.isdir(sp):
                            rstar_folders.append((sub, sp))
                except Exception:
                    pass

    seen = set()
    for title, folder in rstar_folders:
        f_abs = os.path.abspath(folder)
        if f_abs.lower() in seen:
            continue
        seen.add(f_abs.lower())
        exe_name, exe_path = _find_best_game_exe_in_folder(f_abs, title)
        if exe_name:
            games.append({
                'game_name': title[:80],
                'exe_name': exe_name,
                'exe_path': exe_path or "",
                'platform': 'Rockstar Games'
            })
    return games


def _scan_other_launchers_games():
    """
    Scans additional PC Game Launchers:
    - Amazon Games (%LOCALAPPDATA%\\Amazon Games\\Data\\Games\\Sql\\GameInstallInfo.sqlite)
    - Heroic Games Launcher (%APPDATA%\\heroic\\...\\installed.json)
    - itch.io (%APPDATA%\\itch\\db\\butler.db)
    - HoYoPlay / Cognosphere / miHoYo (Genshin Impact, Honkai: Star Rail, Zenless Zone Zero)
    - Wargaming.net Game Center (%ProgramData%\\Wargaming.net\\GameCenter\\apps)
    """
    games = []
    local_app = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")

    # 1. Amazon Games SQLite DB
    if local_app:
        amz_db = os.path.join(local_app, "Amazon Games", "Data", "Games", "Sql", "GameInstallInfo.sqlite")
        if os.path.isfile(amz_db) and _is_safe_local_file_path(amz_db):
            try:
                conn = sqlite3.connect(f"file:{amz_db}?mode=ro", uri=True, timeout=1.5)
                cur = conn.cursor()
                cur.execute("SELECT ProductTitle, InstallDirectory FROM DbSet WHERE Installed = 1 LIMIT 200")
                for p_title, inst_dir in cur.fetchall():
                    if p_title and inst_dir and _is_safe_local_file_path(inst_dir) and os.path.isdir(inst_dir):
                        exe_name, exe_path = _find_best_game_exe_in_folder(inst_dir, str(p_title))
                        if exe_name:
                            games.append({
                                'game_name': str(p_title).strip()[:80],
                                'exe_name': exe_name,
                                'exe_path': exe_path or "",
                                'platform': 'Amazon Games'
                            })
                conn.close()
            except Exception:
                pass

    # 2. Heroic Games Launcher (Epic / Legendary, GOG, Amazon / Nile)
    if appdata:
        heroic_root = os.path.join(appdata, "heroic")
        if os.path.isdir(heroic_root):
            for rel_json in (
                os.path.join("legendaryConfig", "legendary", "installed.json"),
                os.path.join("gog_store", "installed.json"),
                os.path.join("nile_config", "nile", "installed.json"),
            ):
                jpath = os.path.join(heroic_root, rel_json)
                if os.path.isfile(jpath) and _is_safe_local_file_path(jpath):
                    try:
                        with open(jpath, "r", encoding="utf-8", errors="ignore") as f:
                            hdata = json.load(f)
                        items = []
                        if isinstance(hdata, dict):
                            items = list(hdata.get("installed", [])) if isinstance(hdata.get("installed"), list) else list(hdata.values())
                        elif isinstance(hdata, list):
                            items = hdata
                        for entry in items[:150]:
                            if not isinstance(entry, dict):
                                continue
                            g_title = str(entry.get("title") or entry.get("app_name") or "").strip()
                            inst_p = str(entry.get("install_path") or "").strip()
                            if g_title and inst_p and _is_safe_local_file_path(inst_p) and os.path.isdir(inst_p):
                                exe_name, exe_path = _find_best_game_exe_in_folder(inst_p, g_title)
                                if exe_name:
                                    games.append({
                                        'game_name': g_title[:80],
                                        'exe_name': exe_name,
                                        'exe_path': exe_path or "",
                                        'platform': 'Heroic'
                                    })
                    except Exception:
                        pass

    # 3. itch.io App (butler.db)
    if appdata:
        itch_db = os.path.join(appdata, "itch", "db", "butler.db")
        if os.path.isfile(itch_db) and _is_safe_local_file_path(itch_db):
            try:
                conn = sqlite3.connect(f"file:{itch_db}?mode=ro", uri=True, timeout=1.5)
                cur = conn.cursor()
                cur.execute("""
                    SELECT g.title, il.path, c.install_folder
                    FROM caves c
                    JOIN games g ON c.game_id = g.id
                    JOIN install_locations il ON c.install_location_id = il.id
                    LIMIT 150
                """)
                for g_title, base_p, sub_f in cur.fetchall():
                    if g_title and base_p and sub_f:
                        full_dir = os.path.join(str(base_p), str(sub_f))
                        if _is_safe_local_file_path(full_dir) and os.path.isdir(full_dir):
                            exe_name, exe_path = _find_best_game_exe_in_folder(full_dir, str(g_title))
                            if exe_name:
                                games.append({
                                    'game_name': str(g_title).strip()[:80],
                                    'exe_name': exe_name,
                                    'exe_path': exe_path or "",
                                    'platform': 'itch.io'
                                })
                conn.close()
            except Exception:
                pass

    # 4. HoYoPlay / Cognosphere (Genshin Impact, Honkai: Star Rail, Zenless Zone Zero)
    for mp in _get_local_drive_roots():
        for rel in (
            r"Program Files\HoYoPlay\games",
            r"HoYoPlay\games",
            "Genshin Impact",
            "Star Rail",
            "ZenlessZoneZero Game",
        ):
            p = os.path.join(mp, rel)
            if os.path.isdir(p) and _is_safe_local_file_path(p):
                try:
                    if p.lower().endswith("games"):
                        for sub in os.listdir(p)[:20]:
                            sp = os.path.join(p, sub)
                            if os.path.isdir(sp):
                                exe_name, exe_path = _find_best_game_exe_in_folder(sp, sub)
                                if exe_name:
                                    games.append({'game_name': sub.replace(" Game", "")[:80], 'exe_name': exe_name, 'exe_path': exe_path or "", 'platform': 'HoYoPlay'})
                    else:
                        title = os.path.basename(p).replace(" Game", "")
                        exe_name, exe_path = _find_best_game_exe_in_folder(p, title)
                        if exe_name:
                            games.append({'game_name': title[:80], 'exe_name': exe_name, 'exe_path': exe_path or "", 'platform': 'HoYoPlay'})
                except Exception:
                    pass

    # 5. Wargaming.net Game Center (World of Tanks, World of Warships, World of Warplanes)
    for mp in _get_local_drive_roots():
        wg_dir = os.path.join(mp, "Games")
        if os.path.isdir(wg_dir) and _is_safe_local_file_path(wg_dir):
            for wg_title in ("World_of_Tanks", "World_of_Tanks_EU", "World_of_Warships", "World_of_Warships_EU", "World_of_Warplanes"):
                w_p = os.path.join(wg_dir, wg_title)
                if os.path.isdir(w_p):
                    clean_t = wg_title.replace("_EU", "").replace("_", " ")
                    exe_name, exe_path = _find_best_game_exe_in_folder(w_p, clean_t)
                    if exe_name:
                        games.append({'game_name': clean_t, 'exe_name': exe_name, 'exe_path': exe_path or "", 'platform': 'Wargaming'})

    return games


def _scan_standalone_and_registry_games(custom_dirs=None):
    """
    Scans common game directories on local drives (Games, Oyunlar, PC Games),
    user-added custom directories, and Windows Uninstall Registry entries located inside game folders.
    """
    games = []
    candidate_folders = []

    for mp in _get_local_drive_roots():
        for root_name, platform_label in [
            ("Games", "Yerel Oyun"),
            ("Oyunlar", "Yerel Oyun"),
            ("PC Games", "Yerel Oyun"),
            (r"Program Files\Epic Games", "Epic Games"),
        ]:
            parent_dir = os.path.join(mp, root_name)
            if os.path.isdir(parent_dir) and _is_safe_local_file_path(parent_dir):
                try:
                    for sub in os.listdir(parent_dir)[:80]:
                        if sub.lower() in ('riot client', 'directx', 'redist', 'steamlibrary', 'xboxgames', 'gog games', 'ea games'):
                            continue
                        sub_p = os.path.join(parent_dir, sub)
                        if os.path.isdir(sub_p):
                            candidate_folders.append((sub, sub_p, platform_label))
                except Exception:
                    pass

    # User-specified custom game library directories
    if custom_dirs and isinstance(custom_dirs, (list, tuple)):
        for c_dir in custom_dirs:
            if not c_dir or not isinstance(c_dir, str) or not _is_safe_local_file_path(c_dir) or not os.path.isdir(c_dir):
                continue
            try:
                # Check if c_dir itself is a single game folder or a parent directory of games
                direct_exe, direct_path = _find_best_game_exe_in_folder(c_dir, os.path.basename(c_dir), max_depth=1)
                subdirs = [os.path.join(c_dir, s) for s in os.listdir(c_dir)[:120] if os.path.isdir(os.path.join(c_dir, s))]
                if direct_exe and len(subdirs) <= 6:
                    candidate_folders.append((os.path.basename(c_dir), c_dir, "Özel Klasör"))
                else:
                    for s_p in subdirs:
                        s_name = os.path.basename(s_p)
                        if s_name.lower() not in SKIP_SUBDIRS:
                            candidate_folders.append((s_name, s_p, "Özel Klasör"))
            except Exception:
                pass

    # Windows Uninstall Registry scan for standalone games installed in Games/Oyunlar or known game publishers
    known_game_publishers = (
        'ubisoft', 'electronic arts', 'ea ', 'rockstar', 'blizzard', 'activision',
        'bethesda', 'cd projekt', 'capcom', 'bandai namco', 'square enix', 'sega',
        'konami', 'sony interactive', 'playstation', 'xbox game studios', '2k ',
        'take-two', 'paradox', 'focus entertainment', 'thq nordic', 'deep silver',
        'devolver', 'larian', 'remedy', 'techland', 'fromsoftware', 'kojima',
        'wb games', 'warner bros', 'cognosphere', 'mihoyo', 'kuro games', 'wargaming',
        'gaijin', 'bossa', 'klei', 're-logic', 'mojang', 'coffee stain', 'frontier',
        'bohemia interactive', 'crytek', 'id software', 'bungie', 'Embark', 'pearl abyss'
    )
    try:
        import winreg
        for hive, reg_path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]:
            try:
                with winreg.OpenKey(hive, reg_path) as k:
                    num_sub = winreg.QueryInfoKey(k)[0]
                    for i in range(min(num_sub, 600)):
                        try:
                            sk_name = winreg.EnumKey(k, i)
                            with winreg.OpenKey(k, sk_name) as sk:
                                disp_name = ""
                                inst_loc = ""
                                publisher = ""
                                try:
                                    disp_name, _ = winreg.QueryValueEx(sk, "DisplayName")
                                except Exception:
                                    continue
                                try:
                                    inst_loc, _ = winreg.QueryValueEx(sk, "InstallLocation")
                                except Exception:
                                    pass
                                try:
                                    publisher, _ = winreg.QueryValueEx(sk, "Publisher")
                                except Exception:
                                    pass
                                disp_str = str(disp_name or "").strip()
                                loc_str = str(inst_loc or "").strip().strip('"')
                                pub_low = str(publisher or "").strip().lower()
                                if not disp_str or not loc_str or not _is_safe_local_file_path(loc_str) or not os.path.isdir(loc_str):
                                    continue
                                loc_low = loc_str.lower()
                                is_game_path = any(g_tok in loc_low for g_tok in (r'\games\\', r'\oyunlar\\', r'\pc games\\', r'\gog games\\', r'\ea games\\', r'\ubisoft\\'))
                                is_game_pub = any(pub_tok in pub_low for pub_tok in known_game_publishers)
                                if is_game_path or is_game_pub:
                                    if any(skip_w in disp_str.lower() for skip_w in (
                                        'launcher', 'sdk', 'redistributable', 'driver', 'runtime',
                                        'social club', 'game center', 'battle.net', 'ubisoft connect',
                                        'ea app', 'gog galaxy', 'epic games', 'online services'
                                    )):
                                        continue
                                    candidate_folders.append((disp_str, os.path.normpath(loc_str), "PC Oyunu"))
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception:
        pass

    seen_folders = set()
    for g_title, folder_p, plat in candidate_folders[:MAX_SCAN_DIRS]:
        f_abs = os.path.abspath(folder_p)
        if f_abs.lower() in seen_folders:
            continue
        seen_folders.add(f_abs.lower())
        exe_name, exe_path = _find_best_game_exe_in_folder(f_abs, g_title)
        if exe_name:
            games.append({
                'game_name': g_title[:80],
                'exe_name': exe_name,
                'exe_path': exe_path or "",
                'platform': plat
            })

    return games


def scan_installed_games(custom_dirs=None):
    """
    🔍 Scans all major PC Game Launchers (Steam, Epic Games, Xbox/PC Game Pass, Riot Games,
    EA App/Origin, Ubisoft Connect, Battle.net, GOG Galaxy, Rockstar Games, Amazon Games,
    Heroic, itch.io, HoYoPlay, Wargaming, Windows Registry, and Custom Folders) and returns
    a deduplicated list of installed games.
    """
    all_games = []
    seen_exes = set()

    scanners = (
        _scan_steam_games,
        _scan_epic_games,
        _scan_xbox_gamepass_games,
        _scan_riot_games,
        _scan_ea_origin_games,
        _scan_ubisoft_games,
        _scan_battlenet_games,
        _scan_gog_galaxy_games,
        _scan_rockstar_games,
        _scan_other_launchers_games,
        lambda: _scan_standalone_and_registry_games(custom_dirs=custom_dirs),
    )

    for scanner in scanners:
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

        raw_custom_dirs = self.gui.app_settings.get('custom_game_scan_dirs', [])
        self.custom_scan_dirs = [
            d for d in (raw_custom_dirs if isinstance(raw_custom_dirs, list) else [])
            if isinstance(d, str) and _is_safe_local_file_path(d) and os.path.isdir(d)
        ]

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

        # Toolbar: Search + Quick Filter Pills + Platform Launcher Filter + Rescan + Add Custom Folder + Add Custom .exe + Add Running Process
        bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Yüklü oyunlarda veya .exe adlarında ara (Örn: Counter-Strike, Valorant, Cyberpunk, cs2.exe)...")
        self.search_input.textChanged.connect(self.filter_game_rows)
        bar.addWidget(self.search_input, stretch=1)

        self.filter_pill_btns = {}
        for f_key, f_lbl in [("all", "Tümü"), ("bound", "🔗 Bağlı"), ("unbound", "⚪ Bağsız")]:
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

        self.combo_platform_filter = QComboBox()
        self.combo_platform_filter.setMinimumWidth(145)
        self.combo_platform_filter.setToolTip("Oyun Başlatıcısına (Launcher) Göre Filtrele")
        for p_key, p_lbl in [
            ("all", "🌐 Tüm Başlatıcılar"),
            ("steam", "🟦 Steam"),
            ("epic", "⬛ Epic Games"),
            ("xbox", "🟩 Xbox / Game Pass"),
            ("riot", "🟥 Riot Games"),
            ("ea", "🟧 EA App / Origin"),
            ("ubisoft", "🟪 Ubisoft Connect"),
            ("battle.net", "🟦 Battle.net"),
            ("gog", "🟪 GOG Galaxy"),
            ("rockstar", "🟨 Rockstar Games"),
            ("amazon", "🟧 Amazon Games"),
            ("heroic", "🟦 Heroic Launcher"),
            ("itch", "🟥 itch.io"),
            ("hoyo", "🟦 HoYoPlay"),
            ("wargaming", "🟧 Wargaming"),
            ("local", "📁 Yerel / Özel"),
        ]:
            self.combo_platform_filter.addItem(p_lbl, p_key)
        self.combo_platform_filter.currentIndexChanged.connect(lambda _: self.filter_game_rows(self.search_input.text()))
        bar.addWidget(self.combo_platform_filter)

        btn_rescan = QPushButton("🔄 Yüklü Oyunları Tara")
        btn_rescan.setStyleSheet("background: #171f33; color: #38bdf8; font-weight: 700; border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 6px; padding: 6px 12px;")
        btn_rescan.clicked.connect(self.rescan_system_games)
        bar.addWidget(btn_rescan)

        btn_add_folder = QPushButton("📁 Klasör Tara")
        btn_add_folder.setToolTip("Özel bir oyun klasörünü (Örn: D:\\Oyunlar) tarama listesine ekle")
        btn_add_folder.setStyleSheet("background: #171f33; color: #fbbf24; font-weight: 700; border: 1px solid rgba(251, 191, 36, 0.35); border-radius: 6px; padding: 6px 12px;")
        btn_add_folder.clicked.connect(self.add_custom_game_scan_folder)
        bar.addWidget(btn_add_folder)

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
        scanned = scan_installed_games(custom_dirs=getattr(self, 'custom_scan_dirs', None))
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

        # 2. Merge auto-discovered games from Steam, Epic, Riot, Xbox, EA, Ubisoft, Battle.net, GOG, Rockstar, etc.
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

    def _update_game_count_banner(self):
        bound_count = sum(1 for g in self.discovered_games if g.get('theme_name'))
        plat_counts = {}
        for g in self.discovered_games:
            pl = str(g.get('platform') or 'PC')
            plat_counts[pl] = plat_counts.get(pl, 0) + 1
        plat_summary = " • ".join(f"{k}: {v}" for k, v in sorted(plat_counts.items(), key=lambda x: -x[1])[:6])
        extra = f"  ({plat_summary})" if plat_summary else ""
        self.lbl_count.setText(
            f"📦 Sistemde {len(self.discovered_games)} oyun bulundu{extra}  |  🔗 Temaya Bağlı: {bound_count}"
        )

    def rebuild_game_list_ui(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.row_widgets.clear()

        self._update_game_count_banner()

        platform_colors = {
            'Steam': '#0284c7',
            'Epic Games': '#475569',
            'Riot Games': '#e11d48',
            'Xbox / PC Game Pass': '#16a34a',
            'Battle.net': '#2563eb',
            'Ubisoft': '#4f46e5',
            'EA App': '#ea580c',
            'GOG': '#7c3aed',
            'Rockstar Games': '#d97706',
            'Amazon Games': '#f59e0b',
            'Heroic': '#0891b2',
            'itch.io': '#fa5c5c',
            'HoYoPlay': '#3b82f6',
            'Wargaming': '#dc2626',
            'Özel Klasör': '#0d9488',
            'Yerel Oyun': '#6366f1',
            'PC Oyunu': '#6366f1',
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

        self._update_game_count_banner()
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
        plat_filter = "all"
        if hasattr(self, 'combo_platform_filter'):
            plat_filter = str(self.combo_platform_filter.currentData() or 'all').lower()

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

            matches_plat = True
            if plat_filter != "all":
                if plat_filter == "local":
                    matches_plat = any(tok in plat_l for tok in ("yerel", "özel", "pc", "açık"))
                else:
                    matches_plat = plat_filter in plat_l

            card.setVisible(matches_q and matches_m and matches_plat)

    def add_custom_game_scan_folder(self):
        """Allows the user to add any custom games directory (e.g., D:\\Oyunlar) to the scanner."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "📁 Taranacak Oyun Klasörünü Seçin (Örn: D:\\Oyunlar veya H:\\Games)",
            "C:\\"
        )
        if not folder or not _is_safe_local_file_path(folder) or not os.path.isdir(folder):
            return
        norm_f = os.path.abspath(folder)
        if norm_f not in self.custom_scan_dirs:
            self.custom_scan_dirs.append(norm_f)
        self.gui.app_settings['custom_game_scan_dirs'] = list(self.custom_scan_dirs)
        self.gui.save_app_settings()
        self.rescan_system_games()

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
        self.gui.app_settings['custom_game_scan_dirs'] = list(getattr(self, 'custom_scan_dirs', []))
        self.gui.app_settings['auto_game_theme_enabled'] = self.chk_enable_game_profiles.isChecked()
        self.gui.app_settings['keep_game_theme_on_alttab'] = self.chk_keep_on_alttab.isChecked()
        self.gui.app_settings['auto_game_theme_name'] = str(self.combo_fallback_theme.currentData() or '').strip()
        self.gui.save_app_settings()
        self.profiles_updated_signal.emit()
        self.accept()
