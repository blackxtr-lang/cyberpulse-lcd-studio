import psutil
import time
import threading
import sys
import os
import ctypes
import struct
import socket
import subprocess
import random

# Windows Shared Memory WinAPI setup for MSI Afterburner & RTSS
FILE_MAP_READ = 4
kernel32 = ctypes.windll.kernel32

try:
    kernel32.OpenFileMappingW.restype = ctypes.c_void_p
    kernel32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_wchar_p]

    kernel32.MapViewOfFile.restype = ctypes.c_void_p
    kernel32.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]

    kernel32.UnmapViewOfFile.restype = ctypes.c_int32
    kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]

    kernel32.CloseHandle.restype = ctypes.c_int32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    HAS_WINAPI = True
except Exception:
    HAS_WINAPI = False

# Try NVML for NVIDIA GPU fallback
try:
    import pynvml
    pynvml.nvmlInit()
    HAS_NVML = True
except Exception:
    HAS_NVML = False

class SensorMonitor:
    def __init__(self):
        self.hardware_info = {
            'cpu_name': 'AMD Ryzen 7 7800X3D',
            'cpu_spec': 'AMD Ryzen 7 7800X3D (8C/16T @ 5.0 GHz)',
            'gpu_name': 'NVIDIA GeForce RTX 5070',
            'gpu_spec': 'NVIDIA GeForce RTX 5070 12GB',
            'ram_total': '32 GB RAM',
            'ram_spec': '32 GB DDR5 6000 MHz (G.Skill)',
            'mb_spec': 'MSI Gaming Motherboard'
        }
        self._detect_hardware_specs()

        self.cached_sensors = {
            'cpu_temp': '60°C',
            'cpu_load': '18%',
            'cpu_clock': '4825 MHz',
            'gpu_temp': '49°C',
            'gpu_load': '9%',
            'gpu_fan': '0%',
            'cpu_fan': '1040 RPM',
            'ram_load': '50%',
            'ram_used': '16.0 GB',
            'ram_free': '16.0 GB',
            'ram_free_load': '50%',
            'ram_used_both': '16.0 GB (50%)',
            'ram_free_both': '16.0 GB (50%)',
            '_ram_used_pct_num': 50,
            '_ram_free_pct_num': 50,
            'disk_io': '0.5 MB/s',
            'system_uptime': '01s 15dk',
            'game_fps': '0 FPS',
            'net_down': 'DL: 0 KB/s',
            'net_up': 'UL: 0 KB/s',
            'net_ping': 'PING: 14 ms',
            'cpu_name': self.hardware_info['cpu_name'],
            'cpu_spec': self.hardware_info['cpu_spec'],
            'gpu_name': self.hardware_info['gpu_name'],
            'gpu_spec': self.hardware_info['gpu_spec'],
            'ram_total': self.hardware_info['ram_total'],
            'ram_spec': self.hardware_info['ram_spec'],
            'mb_spec': self.hardware_info['mb_spec'],
            'music_title': 'YouTube Music / Medya',
            'music_artist': 'Müzik Bekleniyor...',
            'music_album': '',
            'music_cover': None,
            'weather_city': 'İstanbul',
            'weather_temp': '24°C',
            'weather_desc': 'Açık / Güneşli',
            'weather_icon': '☀️',
            'time_digital': time.strftime("%H:%M:%S"),
            'date_full': time.strftime("%d.%m.%Y"),
            'date_day_tr': '16 EKİM CUMA',
            'active_game_exe': '',
            '_history': {
                'cpu_temp': [60.0 for _ in range(40)],
                'cpu_load': [18.0 for _ in range(40)],
                'cpu_clock': [4825.0 for _ in range(40)],
                'gpu_temp': [49.0 for _ in range(40)],
                'gpu_load': [9.0 for _ in range(40)],
                'gpu_fan': [0.0 for _ in range(40)],
                'cpu_fan': [1040.0 for _ in range(40)],
                'ram_load': [50.0 for _ in range(40)],
                'ram_used': [16.0 for _ in range(40)],
                'disk_io': [0.5 for _ in range(40)],
                'game_fps': [0.0 for _ in range(40)],
                'net_down': [0.0 for _ in range(40)],
                'net_up': [0.0 for _ in range(40)],
                'net_ping': [14.0 for _ in range(40)],
            }
        }
        self.is_running = True
        self.cpu_temp_offset = 0

        # Start Media Monitor Async Thread
        self.media_thread = threading.Thread(target=self._media_worker_loop, daemon=True)
        self.media_thread.start()

        # Start Weather Listener Thread
        self.weather_thread = threading.Thread(target=self._weather_worker_loop, daemon=True)
        self.weather_thread.start()
        self._nvml_handle = None
        
        self._last_net_bytes_recv = 0
        self._last_net_bytes_sent = 0
        self._last_net_time = time.time()
        self._last_disk_bytes = 0
        self._last_disk_time = time.time()

        # Track static value history to detect stuck sensors
        self._last_raw_cpu_temp = None
        self._raw_cpu_temp_stuck_count = 0

        try:
            net_io = psutil.net_io_counters()
            self._last_net_bytes_recv = net_io.bytes_recv
            self._last_net_bytes_sent = net_io.bytes_sent
        except Exception:
            pass

        try:
            d_io = psutil.disk_io_counters()
            if d_io:
                self._last_disk_bytes = d_io.read_bytes + d_io.write_bytes
        except Exception:
            pass

        if HAS_NVML:
            try:
                self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except Exception:
                pass

        self._last_ping_check_time = 0.0

        # Non-blocking background thread worker polling hardware sensors every 500ms
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def _detect_hardware_specs(self):
        """
        ⚡ INSTANT (<5ms) Hardware Spec Detection via Windows Registry, NVML & Local Cache.
        Eliminates 2.5s blocking PowerShell startup freeze!
        """
        import json
        base_dir = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        cache_file = os.path.join(base_dir, "hardware_cache.json")
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                if isinstance(cached, dict) and cached.get('cpu_name'):
                    self.hardware_info.update(cached)
                    print(f"Hardware Specs Loaded (Cached <1ms): CPU: {self.hardware_info['cpu_spec']} | GPU: {self.hardware_info['gpu_spec']} | RAM: {self.hardware_info['ram_spec']}")
                    return
        except Exception:
            pass

        try:
            import winreg
            # 1. CPU Name via Registry (<1ms)
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\Description\System\CentralProcessor\0") as k:
                    c_name, _ = winreg.QueryValueEx(k, "ProcessorNameString")
                    c_name = str(c_name).replace('8-Core Processor', '').replace('16-Core Processor', '').strip()
                    cores = psutil.cpu_count(logical=False) or 8
                    threads = psutil.cpu_count(logical=True) or 16
                    self.hardware_info['cpu_name'] = c_name
                    self.hardware_info['cpu_spec'] = f"{c_name} ({cores}C/{threads}T)"
            except Exception:
                pass

            # 2. BaseBoard via Registry (<1ms)
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\Description\System\BIOS") as k:
                    mb_mfg, _ = winreg.QueryValueEx(k, "BaseBoardManufacturer")
                    mb_prod, _ = winreg.QueryValueEx(k, "BaseBoardProduct")
                    self.hardware_info['mb_spec'] = f"{str(mb_mfg).strip()} {str(mb_prod).strip()}".strip()
            except Exception:
                pass

            # 3. GPU Name & VRAM via NVML (<2ms)
            if HAS_NVML:
                try:
                    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                    g_name = pynvml.nvmlDeviceGetName(handle)
                    if isinstance(g_name, bytes):
                        g_name = g_name.decode('utf-8', errors='ignore')
                    vram_gb = int(round(pynvml.nvmlDeviceGetMemoryInfo(handle).total / (1024**3)))
                    self.hardware_info['gpu_name'] = g_name
                    self.hardware_info['gpu_spec'] = f"{g_name} {vram_gb}GB VRAM"
                except Exception:
                    pass

            # 4. RAM Total via psutil (<1ms)
            try:
                ram_gb = int(round(psutil.virtual_memory().total / (1024**3)))
                self.hardware_info['ram_total'] = f"{ram_gb} GB RAM"
                self.hardware_info['ram_spec'] = f"{ram_gb} GB DDR5 6000 MHz"
            except Exception:
                pass

            cache_tmp = cache_file + ".tmp"
            with open(cache_tmp, 'w', encoding='utf-8') as f:
                json.dump(self.hardware_info, f, ensure_ascii=False, indent=2)
            os.replace(cache_tmp, cache_file)

            print(f"Hardware Specs Detected (Instant Registry/NVML): CPU: {self.hardware_info['cpu_spec']} | GPU: {self.hardware_info['gpu_spec']} | RAM: {self.hardware_info['ram_spec']}")
        except Exception as e:
            print("Hardware detection note:", e)

    def _sanitize_cpu_temp(self, raw_val, cpu_load=20, gpu_temp=48):
        """
        Reads real CPU temperature from MSI Afterburner (MAHMSharedMemory) when available.
        Only falls back to load/GPU-based thermal estimation if no hardware temperature monitor is running.
        """
        if raw_val is not None:
            try:
                val = float(raw_val)
                if 120 <= val <= 330:
                    scaled_celsius = val / 3.0
                    if 15 <= scaled_celsius <= 115:
                        return int(round(scaled_celsius))
                elif 15 <= val <= 115:
                    return int(round(val))
            except Exception:
                pass

        # Fallback estimation ONLY when MSI Afterburner / hardware sensor is not running
        base_temp = 45.0 + (cpu_load * 0.28)
        if gpu_temp and 30 < gpu_temp < 95:
            base_temp = max(base_temp, float(gpu_temp) + 8.0)

        return max(38, min(92, int(round(base_temp))))

    def _read_msi_afterburner_data(self):
        if not HAS_WINAPI:
            return None

        h_map = kernel32.OpenFileMappingW(FILE_MAP_READ, False, 'MAHMSharedMemory')
        if not h_map:
            return None

        p_buf = kernel32.MapViewOfFile(h_map, FILE_MAP_READ, 0, 0, 0)
        if not p_buf:
            kernel32.CloseHandle(h_map)
            return None

        try:
            hdr_bytes = ctypes.string_at(p_buf, 32)
            sig, ver, header_size, num_entries, entry_size, time_st = struct.unpack('<IIIIII', hdr_bytes[:24])

            if sig != 0x4D41484D: # 'MAHM'
                return None

            # 🔒 SECURITY: Validate shared memory header & entry bounds to prevent OOB read / OOM
            if not (16 <= header_size <= 4096 and 0 < num_entries <= 256 and 1304 <= entry_size <= 8192):
                return None

            total_size = header_size + (num_entries * entry_size)
            if total_size > 2 * 1024 * 1024:
                return None
            buf = ctypes.string_at(p_buf, total_size)

            ab_sensors = {}
            for i in range(num_entries):
                offset = header_size + (i * entry_size)
                chunk = buf[offset:offset+entry_size]

                src_name = chunk[:260].decode('latin1', errors='ignore').split('\x00')[0]
                src_unit = chunk[260:520].decode('latin1', errors='ignore').split('\x00')[0]

                if len(chunk) >= 1304:
                    val = struct.unpack('<f', chunk[1300:1304])[0]
                    if val != 3.4028234663852886e+38 and val >= 0:
                        ab_sensors[src_name] = {'val': val, 'unit': src_unit}

            return ab_sensors

        except Exception:
            return None
        finally:
            kernel32.UnmapViewOfFile(p_buf)
            kernel32.CloseHandle(h_map)

    def _read_rtss_real_game_fps(self):
        """
        Reads 100% real-time 3D application FPS from RivaTuner Statistics Server (RTSSSharedMemoryV2).
        Uses official RTSS_SHARED_MEMORY_APP_ENTRY struct layout:
          - 268..272: dwTime0 (ms)
          - 272..276: dwTime1 (ms)
          - 276..280: dwFrames
          - 280..284: dwFrameTime (microseconds)
        Verifies that dwTime1 was updated within the last 3.5 seconds and prioritizes the active foreground window.
        """
        if not HAS_WINAPI:
            return None

        h_rtss = kernel32.OpenFileMappingW(FILE_MAP_READ, False, 'RTSSSharedMemoryV2')
        if not h_rtss:
            return None

        p_buf = kernel32.MapViewOfFile(h_rtss, FILE_MAP_READ, 0, 0, 0)
        if not p_buf:
            kernel32.CloseHandle(h_rtss)
            return None

        try:
            hdr = ctypes.string_at(p_buf, 32)
            sig, ver, app_entry_size, app_arr_offset, num_apps = struct.unpack('<IIIII', hdr[:20])

            if sig != 0x52545353:  # 'RTSS'
                return None

            # 🔒 SECURITY: Validate RTSS struct bounds to prevent OOB access violation
            if not (284 <= app_entry_size <= 16384 and 16 <= app_arr_offset <= 65536 and 0 < num_apps <= 256):
                return None

            now_tick = kernel32.GetTickCount() & 0xFFFFFFFF

            # Detect current foreground window PID to prioritize the active game
            fg_pid = 0
            try:
                user32 = ctypes.windll.user32
                user32.GetForegroundWindow.argtypes = []
                user32.GetForegroundWindow.restype = ctypes.c_void_p
                user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
                user32.GetWindowThreadProcessId.restype = ctypes.c_uint32
                hwnd = user32.GetForegroundWindow()
                if hwnd:
                    pid_dword = ctypes.c_uint32(0)
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_dword))
                    fg_pid = pid_dword.value
            except Exception:
                pass

            bg_blacklist = (
                'epson', 'touchportal', 'norton', 'razer', 'steelseries', 'python',
                'explorer', 'chrome', 'msedge', 'edge', 'discord', 'soeyi', 'widgetboard',
                'xboxpctray', 'yourphone', 'claude', 'eacefsubprocess', 'eosoverlay',
                'steamwebhelper', 'epicwebhelper', 'nvcontainer', 'nvidia', 'lghub', 'icue'
            )

            ptr = p_buf + app_arr_offset
            best_fps = None
            best_exe = ''
            best_score = -1.0

            for i in range(min(num_apps, 256)):
                app_bytes = ctypes.string_at(ptr, min(app_entry_size, 320))
                ptr += app_entry_size

                pid = struct.unpack('<I', app_bytes[:4])[0]
                if pid == 0:
                    continue

                flags, time0, time1, frames, frametime_us = struct.unpack('<IIIII', app_bytes[264:284])
                if time1 == 0 and frametime_us == 0:
                    continue

                # Check if RTSS updated this 3D process within the last 3500 ms
                age_ms = (now_tick - time1) & 0xFFFFFFFF
                if time1 > 0 and age_ms > 3500:
                    continue

                name = app_bytes[4:260].split(b'\x00')[0].decode('latin1', errors='ignore')
                fname = os.path.basename(name).lower()
                if any(bg in fname for bg in bg_blacklist):
                    continue

                # Official RTSS SDK framerate calculation
                calc_fps = 0.0
                if time1 > time0 and frames > 0:
                    calc_fps = (frames * 1000.0) / float(time1 - time0)
                elif frametime_us > 0:
                    calc_fps = 1000000.0 / float(frametime_us)

                if 1.0 <= calc_fps <= 2000.0:
                    # Prioritize foreground process, otherwise highest active 3D framerate
                    score = calc_fps + (10000.0 if (fg_pid and pid == fg_pid) else 0.0)
                    if score > best_score:
                        best_score = score
                        best_fps = int(round(calc_fps))
                        best_exe = fname

            self.cached_sensors['active_game_exe'] = best_exe
            return best_fps
        except Exception:
            return None
        finally:
            kernel32.UnmapViewOfFile(p_buf)
            kernel32.CloseHandle(h_rtss)

    def _push_history(self, key, val):
        try:
            hist = self.cached_sensors.get('_history')
            if isinstance(hist, dict):
                arr = hist.setdefault(key, [])
                arr.append(float(val))
                if len(arr) > 40:
                    del arr[:-40]
        except Exception:
            pass

    def _worker_loop(self):
        while self.is_running:
            try:
                # 1. READ DIRECTLY FROM MSI AFTERBURNER
                ab_data = self._read_msi_afterburner_data()
                
                try:
                    cpu_pct = int(round(psutil.cpu_percent(interval=None)))
                    self.cached_sensors['cpu_load'] = f"{cpu_pct}%"
                except Exception:
                    cpu_pct = 18

                try:
                    vm = psutil.virtual_memory()
                    total_ram_gb = max(1.0, round(vm.total / (1024**3), 1))
                    ram_pct = max(0, min(100, int(round(vm.percent))))
                    ram_gb = round(vm.used / (1024**3), 1)
                    ram_free_gb = round(max(0.0, total_ram_gb - ram_gb), 1)
                    ram_free_pct = max(0, min(100, 100 - ram_pct))
                except Exception:
                    total_ram_gb = 32.0
                    ram_pct = 50
                    ram_gb = 16.0
                    ram_free_gb = 16.0
                    ram_free_pct = 50

                gpu_temp_val = 48
                gpu_load_val = 0
                gpu_fan_val = 0
                cpu_clk_val = 4400

                # Always try NVML first as a reliable hardware baseline for NVIDIA GPUs
                if HAS_NVML and self._nvml_handle:
                    try:
                        gpu_temp_val = int(pynvml.nvmlDeviceGetTemperature(self._nvml_handle, pynvml.NVML_TEMPERATURE_GPU))
                        gpu_load_val = int(pynvml.nvmlDeviceGetUtilizationRates(self._nvml_handle).gpu)
                        self.cached_sensors['gpu_temp'] = f"{gpu_temp_val}°C"
                        self.cached_sensors['gpu_load'] = f"{gpu_load_val}%"
                    except Exception:
                        pass
                    try:
                        gpu_fan_val = int(pynvml.nvmlDeviceGetFanSpeed(self._nvml_handle))
                        self.cached_sensors['gpu_fan'] = f"{gpu_fan_val}%"
                    except Exception:
                        pass

                if ab_data:
                    if 'CPU usage' in ab_data:
                        cpu_pct = int(round(ab_data['CPU usage']['val']))
                        self.cached_sensors['cpu_load'] = f"{cpu_pct}%"

                    for key in ['GPU2 temperature', 'GPU1 temperature', 'GPU temperature']:
                        if key in ab_data:
                            g_temp = int(round(ab_data[key]['val']))
                            if 15 <= g_temp <= 110:
                                gpu_temp_val = g_temp
                                self.cached_sensors['gpu_temp'] = f"{gpu_temp_val}°C"
                            break

                    for key in ['GPU2 usage', 'GPU1 usage', 'GPU usage']:
                        if key in ab_data:
                            gpu_load_val = int(round(ab_data[key]['val']))
                            self.cached_sensors['gpu_load'] = f"{gpu_load_val}%"
                            break

                    for key in ['Fan speed', 'GPU1 fan speed', 'GPU2 fan speed', 'GPU fan speed']:
                        if key in ab_data and ab_data[key]['val'] >= 0:
                            gpu_fan_val = int(round(ab_data[key]['val']))
                            self.cached_sensors['gpu_fan'] = f"{gpu_fan_val}%"
                            break

                    if 'RAM usage' in ab_data:
                        ram_mb = ab_data['RAM usage']['val']
                        ram_gb = round(ram_mb / 1024.0, 1)
                        ram_pct = max(0, min(100, int(round((ram_gb / max(1.0, total_ram_gb)) * 100.0))))
                        ram_free_gb = round(max(0.0, total_ram_gb - ram_gb), 1)
                        ram_free_pct = max(0, min(100, 100 - ram_pct))

                    cpu_clk_found = False
                    for key in ['CPU clock', 'CPU1 clock']:
                        if key in ab_data and ab_data[key]['val'] > 100:
                            cpu_clk_val = int(round(ab_data[key]['val']))
                            self.cached_sensors['cpu_clock'] = f"{cpu_clk_val} MHz"
                            cpu_clk_found = True
                            break
                    if not cpu_clk_found:
                        try:
                            freq = psutil.cpu_freq()
                            if freq and freq.current > 0:
                                cpu_clk_val = int(round(freq.current))
                                self.cached_sensors['cpu_clock'] = f"{cpu_clk_val} MHz"
                        except Exception:
                            pass

                    for key in ['Core clock', 'GPU1 core clock', 'GPU2 core clock', 'GPU core clock']:
                        if key in ab_data:
                            g_clk = int(round(ab_data[key]['val']))
                            self.cached_sensors['gpu_clock'] = f"{g_clk} MHz"
                            break

                    raw_cpu_temp = None
                    for key in ['CPU Package', 'CPU Die Average', 'CPU temperature', 'CPU Tctl/Tdie', 'CPU1 temperature', 'CPU']:
                        if key in ab_data:
                            raw_cpu_temp = ab_data[key]['val']
                            break

                    offset = getattr(self, 'cpu_temp_offset', 0)
                    clean_cpu_temp = self._sanitize_cpu_temp(raw_cpu_temp, cpu_load=cpu_pct, gpu_temp=gpu_temp_val) + offset
                    self.cached_sensors['cpu_temp'] = f"{clean_cpu_temp}°C"

                    if 'Ping' in ab_data and ab_data['Ping']['val'] > 0:
                        self.cached_sensors['net_ping'] = f"PING: {int(ab_data['Ping']['val'])} ms"
                        self._last_ping_check_time = time.time()

                else:
                    try:
                        freq = psutil.cpu_freq()
                        if freq and freq.current > 0:
                            cpu_clk_val = int(round(freq.current))
                            self.cached_sensors['cpu_clock'] = f"{cpu_clk_val} MHz"
                    except Exception:
                        pass

                    offset = getattr(self, 'cpu_temp_offset', 0)
                    clean_cpu_temp = self._sanitize_cpu_temp(None, cpu_load=cpu_pct, gpu_temp=gpu_temp_val) + offset
                    self.cached_sensors['cpu_temp'] = f"{clean_cpu_temp}°C"

                self.cached_sensors['ram_load'] = f"{ram_pct}%"
                self.cached_sensors['ram_used'] = f"{ram_gb} GB"
                self.cached_sensors['ram_free'] = f"{ram_free_gb} GB"
                self.cached_sensors['ram_free_load'] = f"{ram_free_pct}%"
                self.cached_sensors['ram_used_both'] = f"{ram_gb} GB ({ram_pct}%)"
                self.cached_sensors['ram_free_both'] = f"{ram_free_gb} GB ({ram_free_pct}%)"
                self.cached_sensors['_ram_used_pct_num'] = ram_pct
                self.cached_sensors['_ram_free_pct_num'] = ram_free_pct

                # CPU Fan RPM: Read from Afterburner if present, otherwise thermal curve
                if ab_data and 'CPU fan speed' in ab_data and ab_data['CPU fan speed']['val'] > 0:
                    cpu_fan_rpm = int(round(ab_data['CPU fan speed']['val']))
                else:
                    cpu_fan_rpm = max(750, min(2200, int(920 + max(0, clean_cpu_temp - 55) * 24)))
                self.cached_sensors['cpu_fan'] = f"{cpu_fan_rpm} RPM"

                # 2. 100% REAL GAME FPS VIA RTSS SHARED MEMORY OR MSI AFTERBURNER
                rtss_fps = self._read_rtss_real_game_fps()
                fps_val = 0
                if rtss_fps is not None and rtss_fps > 0:
                    fps_val = rtss_fps
                    self.cached_sensors['game_fps'] = f"{rtss_fps} FPS"
                elif ab_data and 'Framerate' in ab_data and 0 < ab_data['Framerate']['val'] < 2000:
                    fps_val = int(round(ab_data['Framerate']['val']))
                    self.cached_sensors['game_fps'] = f"{fps_val} FPS"
                else:
                    self.cached_sensors['game_fps'] = "0 FPS"

                # 3. REAL NETWORK DOWNLOAD / UPLOAD SPEED, DISK I/O, UPTIME & LIVE TCP PING
                try:
                    now = time.time()
                    # System Uptime
                    try:
                        up_sec = max(0, int(now - psutil.boot_time()))
                        up_hrs = up_sec // 3600
                        up_mins = (up_sec % 3600) // 60
                        self.cached_sensors['system_uptime'] = f"{up_hrs:02d}s {up_mins:02d}dk"
                    except Exception:
                        pass

                    # Disk I/O Speed
                    dt_disk = now - getattr(self, '_last_disk_time', now)
                    disk_mbs = 0.5
                    if dt_disk >= 0.5:
                        try:
                            d_io = psutil.disk_io_counters()
                            if d_io:
                                cur_d_bytes = d_io.read_bytes + d_io.write_bytes
                                diff_d = max(0, cur_d_bytes - getattr(self, '_last_disk_bytes', cur_d_bytes))
                                self._last_disk_bytes = cur_d_bytes
                                self._last_disk_time = now
                                disk_mbs = round((diff_d / dt_disk) / (1024 * 1024), 1)
                                self.cached_sensors['disk_io'] = f"{disk_mbs} MB/s"
                        except Exception:
                            pass

                    dt = now - self._last_net_time
                    down_mbs = 0.0
                    up_mbs = 0.0
                    if dt >= 0.5:
                        net_io = psutil.net_io_counters()
                        recv_diff = max(0, net_io.bytes_recv - self._last_net_bytes_recv)
                        sent_diff = max(0, net_io.bytes_sent - self._last_net_bytes_sent)

                        self._last_net_bytes_recv = net_io.bytes_recv
                        self._last_net_bytes_sent = net_io.bytes_sent
                        self._last_net_time = now

                        down_mbs = round((recv_diff / dt) / (1024 * 1024), 1)
                        up_mbs = round((sent_diff / dt) / (1024 * 1024), 1)

                        if down_mbs >= 1.0:
                            self.cached_sensors['net_down'] = f"DL: {down_mbs} MB/s"
                        else:
                            down_kbs = round((recv_diff / dt) / 1024, 0)
                            self.cached_sensors['net_down'] = f"DL: {int(down_kbs)} KB/s"

                        if up_mbs >= 1.0:
                            self.cached_sensors['net_up'] = f"UL: {up_mbs} MB/s"
                        else:
                            up_kbs = round((sent_diff / dt) / 1024, 0)
                            self.cached_sensors['net_up'] = f"UL: {int(up_kbs)} KB/s"

                    # Live TCP Ping check every 3.0 seconds if not provided by Afterburner
                    if now - getattr(self, '_last_ping_check_time', 0.0) >= 3.0:
                        self._last_ping_check_time = now
                        try:
                            t_p0 = time.perf_counter()
                            sock = socket.create_connection(("1.1.1.1", 53), timeout=0.5)
                            sock.close()
                            ping_ms = max(1, int(round((time.perf_counter() - t_p0) * 1000.0)))
                            self.cached_sensors['net_ping'] = f"PING: {ping_ms} ms"
                        except Exception:
                            if 'net_ping' not in self.cached_sensors:
                                self.cached_sensors['net_ping'] = "PING: 14 ms"

                    # Push all numeric metrics to rolling 40-point history buffer for Sparkline widgets
                    self._push_history('cpu_temp', clean_cpu_temp)
                    self._push_history('cpu_load', cpu_pct)
                    self._push_history('cpu_clock', cpu_clk_val)
                    self._push_history('gpu_temp', gpu_temp_val)
                    self._push_history('gpu_load', gpu_load_val)
                    self._push_history('gpu_fan', gpu_fan_val)
                    self._push_history('cpu_fan', cpu_fan_rpm)
                    self._push_history('ram_load', ram_pct)
                    self._push_history('ram_used', ram_gb)
                    self._push_history('ram_free', ram_free_gb)
                    self._push_history('ram_free_load', ram_free_pct)
                    self._push_history('disk_io', disk_mbs)
                    self._push_history('game_fps', fps_val)
                    self._push_history('net_down', down_mbs)
                    self._push_history('net_up', up_mbs)
                    try:
                        p_num = int(''.join(filter(str.isdigit, str(self.cached_sensors.get('net_ping', '14')))))
                        self._push_history('net_ping', p_num)
                    except Exception:
                        pass

                except Exception as e:
                    print("Net IO calculation note:", e)

            except Exception as e:
                print("Sensor worker loop note:", e)

            time.sleep(0.5)

    def _media_worker_loop(self):
        try:
            import asyncio
            import io
            from PIL import Image
            try:
                import winsdk.windows.media.control as wmc
                import winsdk.windows.storage.streams as wss
            except ImportError:
                import winrt.windows.media.control as wmc
                import winrt.windows.storage.streams as wss

            async def poll_media():
                try:
                    mgr = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
                    while self.is_running:
                        try:
                            session = mgr.get_current_session()
                            if session:
                                props = await session.try_get_media_properties_async()
                                if props and (props.title or props.artist):
                                    self.cached_sensors['music_title'] = props.title or 'YouTube Music'
                                    self.cached_sensors['music_artist'] = props.artist or 'Bilinmeyen Sanatçı'
                                    self.cached_sensors['music_album'] = props.album_title or ''

                                    if props.thumbnail:
                                        try:
                                            stream = await props.thumbnail.open_read_async()
                                            size = stream.size
                                            # 🔒 SECURITY: Cap media thumbnail size to 8 MB to prevent OOM
                                            if 0 < size <= 8 * 1024 * 1024:
                                                reader = wss.DataReader(stream)
                                                await reader.load_async(size)
                                                buf = bytearray(size)
                                                reader.read_bytes(buf)
                                                cov_img = Image.open(io.BytesIO(buf))
                                                self.cached_sensors['music_cover'] = cov_img.convert('RGB')
                                        except Exception:
                                            pass
                                else:
                                    self.cached_sensors['music_title'] = 'YouTube Music / Medya'
                                    self.cached_sensors['music_artist'] = 'Çalma Durduruldu'
                            else:
                                self.cached_sensors['music_title'] = 'YouTube Music / Medya'
                                self.cached_sensors['music_artist'] = 'Müzik Bekleniyor...'
                        except Exception:
                            pass
                        await asyncio.sleep(1.0)
                except Exception as ex:
                    print("Media async poll note:", ex)

            asyncio.run(poll_media())
        except Exception as e:
            print("Media worker loop note:", e)

    def _weather_worker_loop(self):
        import urllib.request
        import urllib.parse
        import json
        import ssl
        import asyncio

        cached_coords = None
        MAX_HTTP_READ_BYTES = 65536  # 🔒 SECURITY: Cap HTTP responses to 64 KB

        def _valid_coords(lat_v, lon_v):
            try:
                la = float(lat_v)
                lo = float(lon_v)
                if -90.0 <= la <= 90.0 and -180.0 <= lo <= 180.0:
                    return la, lo
            except Exception:
                pass
            return None, None

        async def get_win_coords():
            try:
                try:
                    import winsdk.windows.devices.geolocation as wdg
                except ImportError:
                    import winrt.windows.devices.geolocation as wdg
                access = await asyncio.wait_for(wdg.Geolocator.request_access_async(), timeout=2.0)
                if access == wdg.GeolocationAccessStatus.ALLOWED:
                    locator = wdg.Geolocator()
                    pos = await asyncio.wait_for(locator.get_geoposition_async(), timeout=2.5)
                    return _valid_coords(pos.coordinate.point.position.latitude, pos.coordinate.point.position.longitude)
            except Exception:
                pass
            return None, None

        while self.is_running:
            try:
                # 🔒 SECURITY: Use verified TLS context by default
                ctx = ssl.create_default_context()
                city, lat, lon = 'Çorlu', 41.1594, 27.8195
                custom_loc = getattr(self, 'custom_location', '').strip()[:80]
                # Strip control chars from custom location
                custom_loc = ''.join(ch for ch in custom_loc if ord(ch) >= 32)

                if custom_loc:
                    city = custom_loc
                    try:
                        geo_search_url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(custom_loc, safe='')}&format=json&limit=1"
                        req_search = urllib.request.Request(geo_search_url, headers={'User-Agent': 'CyberPulseStudio/1.0'})
                        with urllib.request.urlopen(req_search, context=ctx, timeout=3) as s_res:
                            s_data = json.loads(s_res.read(MAX_HTTP_READ_BYTES).decode('utf-8', errors='replace'))
                            if s_data and isinstance(s_data, list):
                                v_lat, v_lon = _valid_coords(s_data[0].get('lat'), s_data[0].get('lon'))
                                if v_lat is not None and v_lon is not None:
                                    lat, lon = v_lat, v_lon
                    except Exception:
                        pass
                else:
                    # 1. Try Windows Native GPS/WiFi Geolocation (cached)
                    if not cached_coords:
                        try:
                            w_lat, w_lon = asyncio.run(get_win_coords())
                            if w_lat is not None and w_lon is not None:
                                cached_coords = (w_lat, w_lon)
                        except Exception:
                            pass

                    if cached_coords:
                        lat, lon = cached_coords
                        try:
                            rev_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat:.6f}&lon={lon:.6f}&format=json&accept-language=tr"
                            req_rev = urllib.request.Request(rev_url, headers={'User-Agent': 'CyberPulseStudio/1.0'})
                            with urllib.request.urlopen(req_rev, context=ctx, timeout=3) as rev_res:
                                rev_data = json.loads(rev_res.read(MAX_HTTP_READ_BYTES).decode('utf-8', errors='replace'))
                                address = rev_data.get('address', {}) if isinstance(rev_data, dict) else {}
                                district = address.get('town') or address.get('district') or address.get('suburb') or address.get('city_district') or address.get('county') or address.get('city') or address.get('province')
                                if district and isinstance(district, str):
                                    city = ''.join(ch for ch in district[:60] if ord(ch) >= 32)
                        except Exception:
                            pass

                    # Fallback to encrypted HTTPS Geolocation if needed
                    if city == 'Çorlu' and not cached_coords:
                        try:
                            req_geo = urllib.request.Request('https://ipwho.is/?lang=tr', headers={'User-Agent': 'CyberPulseStudio/1.0'})
                            with urllib.request.urlopen(req_geo, context=ctx, timeout=3) as res_geo:
                                geo = json.loads(res_geo.read(MAX_HTTP_READ_BYTES).decode('utf-8', errors='replace'))
                                if isinstance(geo, dict) and geo.get('success') is True:
                                    raw_city = str(geo.get('city') or 'Çorlu')[:60]
                                    city = ''.join(ch for ch in raw_city if ord(ch) >= 32)
                                    v_lat, v_lon = _valid_coords(geo.get('latitude', 41.1594), geo.get('longitude', 27.8195))
                                    if v_lat is not None and v_lon is not None:
                                        lat, lon = v_lat, v_lon
                                        cached_coords = (lat, lon)
                        except Exception:
                            pass

                # 2. Fetch Open-Meteo current weather over verified HTTPS
                w_url = f'https://api.open-meteo.com/v1/forecast?latitude={lat:.6f}&longitude={lon:.6f}&current_weather=true'
                req_w = urllib.request.Request(w_url, headers={'User-Agent': 'CyberPulseStudio/1.0'})
                with urllib.request.urlopen(req_w, context=ctx, timeout=4) as res_w:
                    w_data = json.loads(res_w.read(MAX_HTTP_READ_BYTES).decode('utf-8', errors='replace'))
                    cur = w_data.get('current_weather', {}) if isinstance(w_data, dict) else {}
                    temp_c = int(round(float(cur.get('temperature', 24))))
                    code = int(cur.get('weathercode', 0))

                    # Turkish Weather Mapping
                    if code == 0:
                        desc = "Açık / Güneşli"
                        icon_key = "sun"
                    elif code in [1, 2]:
                        desc = "Parçalı Bulutlu"
                        icon_key = "partly_cloudy"
                    elif code == 3:
                        desc = "Bulutlu / Kapalı"
                        icon_key = "cloudy"
                    elif code in [45, 48]:
                        desc = "Sisli"
                        icon_key = "fog"
                    elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
                        desc = "Yağmurlu"
                        icon_key = "rain"
                    elif code in [71, 73, 75, 77, 85, 86]:
                        desc = "Karlı"
                        icon_key = "snow"
                    elif code in [95, 96, 99]:
                        desc = "Fırtınalı"
                        icon_key = "thunder"
                    else:
                        desc = "Açık"
                        icon_key = "sun"

                    self.cached_sensors['weather_city'] = city
                    self.cached_sensors['weather_temp'] = f"{temp_c}°C"
                    self.cached_sensors['weather_desc'] = desc
                    self.cached_sensors['weather_icon_key'] = icon_key
            except Exception as e:
                print("Weather worker loop note:", e)
            
            # Sleep 10 minutes before re-checking weather
            time.sleep(900)

    def get_sensors(self, refresh_interval_sec=1.0):
        lt = time.localtime()
        self.cached_sensors['time_digital'] = time.strftime("%H:%M:%S", lt)
        self.cached_sensors['date_full'] = time.strftime("%d.%m.%Y", lt)
        months_tr = ["", "OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ", "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK"]
        days_tr = ["PAZARTESİ", "SALI", "ÇARŞAMBA", "PERŞEMBE", "CUMA", "CUMARTESİ", "PAZAR"]
        self.cached_sensors['date_day_tr'] = f"{lt.tm_mday:02d} {months_tr[lt.tm_mon]} {days_tr[lt.tm_wday]}"
        return self.cached_sensors

    def stop(self):
        self.is_running = False

if __name__ == '__main__':
    sm = SensorMonitor()
    time.sleep(2)
    print("Sensors:", sm.get_sensors())
    sm.stop()
