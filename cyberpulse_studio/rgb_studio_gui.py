import os
import sys
import time
import math
import ctypes
from PIL import Image

try:
    import PyQt5
    qt_plugin_dir = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins', 'platforms')
    if os.path.exists(qt_plugin_dir):
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = qt_plugin_dir
except Exception as e:
    print("Qt Plugin path note:", e)

from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QIcon
from PyQt5.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QColorDialog, QGroupBox, QComboBox,
    QMessageBox, QScrollArea, QFrame, QSizePolicy, QCheckBox
)

try:
    from rgb_controller import RGBController, ConflictProcessResolver
except ImportError:
    class ConflictProcessResolver:
        @staticmethod
        def scan_conflicts(): return []
        @staticmethod
        def terminate_conflicts(): return []
        @staticmethod
        def detect_conflicting_rgb_processes(): return []
        @staticmethod
        def terminate_conflicting_processes(): return 0

    class _FallbackHWBridge:
        def __init__(self):
            self.com_ports = []
        def scan_and_connect_com_ports(self):
            return []

    class RGBController:
        def __init__(self):
            self.is_enabled = True
            self.mode = 'rainbow'
            self.current_mode = 'rainbow'
            self.color_scheme = 'cyberpunk'
            self.color_scheme_mode = 'cyberpunk'
            self.color1 = (0, 240, 255)
            self.color2 = (255, 0, 128)
            self.color3 = (128, 0, 255)
            self.current_output_rgb = (0, 240, 255)
            self.brightness = 1.0
            self.speed = 1.0
            self.devices = []
            self.current_zone_colors = [(0, 240, 255)] * 24
            self.hw_bridge = _FallbackHWBridge()
        def set_mode(self, m):
            self.mode = m
            self.current_mode = m
        def set_color_scheme_mode(self, s):
            self.color_scheme = s
            self.color_scheme_mode = s
        def close(self): pass

class RGBVisualizerWidget(QWidget):
    """
    🖥️ Standalone Animated PC Case ARGB Visualizer Canvas
    """
    def __init__(self, rgb_controller_ref):
        super().__init__()
        self.rgb = rgb_controller_ref
        self.setFixedHeight(130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background: #090d16; border: 2px solid #334155; border-radius: 8px;")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(30)

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            w = self.width()
            h = self.height()

            rgb_tuple = getattr(self.rgb, 'current_output_rgb', (56, 189, 248))
            r, g, b = max(0, min(255, rgb_tuple[0])), max(0, min(255, rgb_tuple[1])), max(0, min(255, rgb_tuple[2]))
            main_qcolor = QColor(r, g, b)

            # Outer Chassis
            painter.setPen(QPen(QColor(51, 65, 85), 3))
            painter.setBrush(QBrush(QColor(15, 23, 42)))
            painter.drawRoundedRect(10, 10, w - 20, h - 20, 8, 8)

            # Glowing Strips
            glow_pen = QPen(main_qcolor, 4)
            painter.setPen(glow_pen)
            painter.drawLine(25, 20, w - 25, 20)
            painter.drawLine(25, h - 20, w - 25, h - 20)

            # 3 Fans evenly spaced
            anim_p = getattr(self.rgb, '_anim_phase', 0.0)
            fan_spacing = (w - 100) // 3
            for i in range(3):
                fx = 50 + (i * fan_spacing) + (fan_spacing // 2)
                fy = h // 2
                radius = 32

                painter.setPen(QPen(main_qcolor, 4))
                painter.setBrush(QBrush(QColor(r, g, b, 40)))
                painter.drawEllipse(fx - radius, fy - radius, radius * 2, radius * 2)

                painter.setBrush(QBrush(main_qcolor))
                painter.drawEllipse(fx - 8, fy - 8, 16, 16)

                angle_rad = anim_p + (i * 1.2)
                for b_idx in range(4):
                    rad = angle_rad + (b_idx * (math.pi / 2.0))
                    bx = fx + int((radius - 5) * math.cos(rad))
                    by = fy + int((radius - 5) * math.sin(rad))
                    painter.setPen(QPen(main_qcolor, 3))
                    painter.drawLine(fx, fy, bx, by)

            painter.setPen(QPen(QColor(248, 250, 252)))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(10)
            painter.setFont(font)
            txt_str = f"CANLI KASA EFEKT: RGB({r}, {g}, {b})"
            painter.drawText((w // 2) - 90, 30, txt_str)
        except Exception:
            pass

class StandaloneRGBStudioApp(QDialog):
    """
    🌈 DEDICATED DYNAMIC STANDALONE KASA RGB LED STÜDYOSU
    Auto-resizing dynamic window layout + RGB Conflict Resolver Engine!
    """
    def __init__(self):
        super().__init__()
        self.rgb = RGBController()
        self.setWindowTitle("🌈 CYBERPULSE Standalone Kasa RGB LED Stüdyosu (Dynamic Auto-Fit)")

        chk_png = os.path.join(os.path.dirname(__file__), "checkmark.png").replace('\\', '/')
        self.setStyleSheet(f"""
            QDialog {{ background-color: #090d16; color: #ffffff; }}
            QLabel {{ color: #ffffff; font-size: 13px; font-weight: 600; }}
            QGroupBox {{ border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; margin-top: 10px; font-weight: bold; font-size: 13px; color: #818cf8; }}
            QComboBox {{ background-color: #0f172a; border: 2px solid #6366f1; border-radius: 6px; padding: 8px; color: #ffffff; font-size: 13px; font-weight: bold; min-height: 28px; }}
            QComboBox QAbstractItemView {{ background-color: #0f172a; color: #ffffff; selection-background-color: #6366f1; selection-color: #ffffff; border: 1px solid #6366f1; }}
            QComboBox::item {{ color: #ffffff; background-color: #0f172a; padding: 8px; font-size: 13px; font-weight: bold; }}
            QComboBox::item:selected {{ background-color: #6366f1; color: #ffffff; }}
            QSlider::groove:horizontal {{ height: 8px; background: #1e293b; border-radius: 4px; }}
            QSlider::handle:horizontal {{ background: #6366f1; width: 18px; margin: -5px 0; border-radius: 9px; }}
            QPushButton {{ background: #1e293b; border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 9px 14px; color: #ffffff; font-weight: 600; }}
            QPushButton:hover {{ background: #334155; border-color: #6366f1; }}
            QCheckBox {{ color: #ffffff; font-weight: 600; font-size: 13px; spacing: 8px; }}
            QCheckBox::indicator {{ width: 20px; height: 20px; background-color: #0f172a; border: 2px solid #6366f1; border-radius: 5px; }}
            QCheckBox::indicator:hover {{ border-color: #818cf8; background-color: #1e293b; }}
            QCheckBox::indicator:checked {{ background-color: #10b981; border: 2px solid #10b981; image: url("{chk_png}"); }}
        """)

        self.init_ui()
        self.auto_scan_conflicts()

    def init_ui(self):
        # 🚀 DYNAMIC LAYOUT: Auto-resizes window based on content!
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSizeConstraint(QVBoxLayout.SetMinAndMaxSize)
        self.main_layout.setContentsMargins(14, 14, 14, 14)
        self.main_layout.setSpacing(10)

        title = QLabel("🌈 CYBERPULSE STANDALONE KASA ARGB KONTROLÜ")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #818cf8; margin-bottom: 2px;")
        self.main_layout.addWidget(title)

        hw_box = QHBoxLayout()
        com_list = self.rgb.hw_bridge.com_ports if (hasattr(self.rgb, 'hw_bridge') and self.rgb.hw_bridge and self.rgb.hw_bridge.com_ports) else []
        status_str = f"🔌 Donanım Kanalı: UDP Broadcast / COM ({len(com_list)} Port Aktif)"
        self.lbl_status = QLabel(status_str)
        self.lbl_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #10b981;")
        hw_box.addWidget(self.lbl_status)

        btn_rescan = QPushButton("🔄 Portları Yeniden Tara")
        btn_rescan.setStyleSheet("background: #0284c7; color: white; font-weight: bold; font-size: 11px; padding: 4px 10px;")
        btn_rescan.clicked.connect(self.rescan_ports)
        hw_box.addWidget(btn_rescan)
        self.main_layout.addLayout(hw_box)

        # 🛠️ RGB DIRECT FORCE OVERRIDE PANEL (Arka Plan Uygulamalarını Kapatmadan Canlı Kontrol)
        grp_conflict = QGroupBox("⚡ Canlı Doğrudan LED Üstüne Yazma & Donanım Yönetimi")
        conflict_layout = QVBoxLayout(grp_conflict)

        self.chk_force_override = QCheckBox("⚡ Arka Plan RGB Yazılımlarını Kapatmadan LED'leri Doğrudan Üstüne Yaz (Force LED Override)")
        self.chk_force_override.setChecked(True)
        self.chk_force_override.setToolTip("ASUS Armoury Crate, Corsair iCUE, MSI Center vb. uygulamaları KAPATMANIZA GEREK YOKTUR. Işıklar arka plan uygulamalarının üzerine canlı yansıtılır.")
        conflict_layout.addWidget(self.chk_force_override)

        self.lbl_conflict_info = QLabel("🟢 Canlı Doğrudan LED Modu Aktif: ASUS Armoury Crate, MSI Center, Corsair iCUE veya Razer Synapse açık kalsa dahi uygulamaları kapatmadan LED'lerinizi canlı kontrol eder.")
        self.lbl_conflict_info.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 600;")
        self.lbl_conflict_info.setWordWrap(True)
        conflict_layout.addWidget(self.lbl_conflict_info)

        btn_optional_close = QPushButton("🧹 İsteğe Bağlı: Arka Plan RGB Servislerini Kapat")
        btn_optional_close.setStyleSheet("background: #334155; color: #cbd5e1; font-size: 11px; font-weight: 600; padding: 5px 10px; border-radius: 4px;")
        btn_optional_close.clicked.connect(self.resolve_conflicts)
        conflict_layout.addWidget(btn_optional_close)

        self.main_layout.addWidget(grp_conflict)

        # 🖥️ Live PC Case ARGB Preview Visualizer
        grp_vis = QGroupBox("🖥️ Kasa İçi ARGB Işık Canlı Önizlemesi")
        vis_layout = QVBoxLayout(grp_vis)
        self.visualizer = RGBVisualizerWidget(self.rgb)
        vis_layout.addWidget(self.visualizer)
        self.main_layout.addWidget(grp_vis)

        grp_mode = QGroupBox("✨ RGB Işık Efekti Modu Seçimi")
        mode_layout = QVBoxLayout(grp_mode)

        self.combo_mode = QComboBox()
        effects = [
            ("🌈 1. Kasa Ekranına Uygun Işık (Screen Ambilight Dominant Sync)", "screen_ambilight"),
            ("🎵 2. Müziğe / Sese Duyarlı Ritim (Audio Spectrum Beat Reactive)", "audio_beat_reactive"),
            ("🔥 3. İşlemci & GPU Sıcaklık Uyarısı (Thermal Reactive Warning)", "thermal_reactive"),
            ("⚡ 4. İşlemci Yükü Reaktifi (CPU Load Reactive)", "cpu_load_reactive"),
            ("🎆 5. Cyberpunk Neon (Cyan & Pink Pulse)", "cyberpunk_neon"),
            ("🌊 6. Okyanus Esintisi (Deep Blue & Aqua)", "ocean_breeze"),
            ("🌋 7. Volkan Alevi (Fire Red & Gold)", "volcano_fire"),
            ("🟢 8. Matrix Kodu (Cyber Matrix Green)", "matrix_code"),
            ("🔮 9. Kuzey Işıkları (Aurora Borealis)", "aurora_borealis"),
            ("🌈 10. Gökkuşağı Spektrumu (Rainbow Wave Spectrum)", "rainbow"),
            ("🌬️ 11. Nefes Alma / Yumuşak Geçiş (Breathing / Pulse)", "breathing"),
            ("🎨 12. Sabit Özel Renk (Static Custom Color)", "static"),
            ("⚡ 13. Flaş / Çakar Işık Efekti (Strobe / Flash)", "strobe"),
            ("🖤 14. LED'leri Tamamen Kapat / Karart (Blackout / OFF)", "off")
        ]

        for lbl, key in effects:
            self.combo_mode.addItem(lbl, key)

        for i in range(self.combo_mode.count()):
            if self.combo_mode.itemData(i) == self.rgb.current_mode:
                self.combo_mode.setCurrentIndex(i)
                break

        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.combo_mode)

        btn_blackout = QPushButton("🖤 Kasa LED'lerini Tamamen Kapat / Karart (Blackout OFF)")
        btn_blackout.setStyleSheet("background: linear-gradient(135deg, #1e293b, #0f172a); color: #f8fafc; font-weight: bold; font-size: 12px; padding: 8px 12px; border: 1px solid #475569; border-radius: 6px;")
        btn_blackout.clicked.connect(self.turn_off_leds)
        mode_layout.addWidget(btn_blackout)

        self.main_layout.addWidget(grp_mode)

        # 🎨 DYNAMIC COLOR SCHEME SELECTION BOX
        grp_scheme = QGroupBox("🎨 Renk Üretim Şeması & Çoklu Renk Modları")
        scheme_layout = QVBoxLayout(grp_scheme)

        self.combo_scheme = QComboBox()
        schemes = [
            ("🌓 1. İki Renkli Geçiş (Dual Color Blend)", "dual_color"),
            ("🔺 2. Üç Renkli Özel Geçiş (Tri-Color Triad Blend)", "tri_color"),
            ("🎲 3. Rastgele Canlı Renkler (Random Dynamic Shift)", "random_dynamic"),
            ("🎆 4. Cyber Neon Paleti (Pink -> Cyan -> Purple)", "cyber_neon"),
            ("🌋 5. Volkan & Ateş Paleti (Red -> Orange -> Gold)", "volcano_fire"),
            ("🌌 6. Derin Uzay Mavi/Mor Paleti (Deep Space Palette)", "deep_space"),
            ("🎨 7. Tek Sabit Renk (Single Custom Color)", "single")
        ]

        for lbl, key in schemes:
            self.combo_scheme.addItem(lbl, key)

        for i in range(self.combo_scheme.count()):
            if self.combo_scheme.itemData(i) == self.rgb.color_scheme_mode:
                self.combo_scheme.setCurrentIndex(i)
                break

        self.combo_scheme.currentIndexChanged.connect(self.on_scheme_changed)
        scheme_layout.addWidget(self.combo_scheme)

        # 3 Color Pickers
        col_btn_box = QHBoxLayout()

        self.btn_col1 = QPushButton("🎨 1. Renk")
        r1, g1, b1 = self.rgb.color1
        self.btn_col1.setStyleSheet(f"background: rgb({r1},{g1},{b1}); color: white; font-weight: bold;")
        self.btn_col1.clicked.connect(self.pick_color1)
        col_btn_box.addWidget(self.btn_col1)

        self.btn_col2 = QPushButton("🎨 2. Renk")
        r2, g2, b2 = self.rgb.color2
        self.btn_col2.setStyleSheet(f"background: rgb({r2},{g2},{b2}); color: white; font-weight: bold;")
        self.btn_col2.clicked.connect(self.pick_color2)
        col_btn_box.addWidget(self.btn_col2)

        self.btn_col3 = QPushButton("🎨 3. Renk")
        r3, g3, b3 = self.rgb.color3
        self.btn_col3.setStyleSheet(f"background: rgb({r3},{g3},{b3}); color: white; font-weight: bold;")
        self.btn_col3.clicked.connect(self.pick_color3)
        col_btn_box.addWidget(self.btn_col3)

        scheme_layout.addLayout(col_btn_box)
        self.main_layout.addWidget(grp_scheme)

        grp_sliders = QGroupBox("⚙️ Parlaklık ve Efekt Hızı")
        sl_layout = QVBoxLayout(grp_sliders)

        sl_layout.addWidget(QLabel("💡 Parlaklık Seviyesi:"))
        self.slider_bright = QSlider(Qt.Horizontal)
        self.slider_bright.setRange(0, 100)
        self.slider_bright.setValue(int(self.rgb.brightness * 100))
        self.slider_bright.valueChanged.connect(self.on_bright_changed)
        sl_layout.addWidget(self.slider_bright)

        sl_layout.addWidget(QLabel("⚡ Efekt Değişim Hızı:"))
        self.slider_speed = QSlider(Qt.Horizontal)
        self.slider_speed.setRange(1, 50)
        self.slider_speed.setValue(int(self.rgb.speed * 10))
        self.slider_speed.valueChanged.connect(self.on_speed_changed)
        sl_layout.addWidget(self.slider_speed)

        self.main_layout.addWidget(grp_sliders)

        btn_box = QHBoxLayout()
        self.btn_toggle = QPushButton("⏹️ Kasa LED'lerini Kapat" if self.rgb.is_enabled else "▶️ Kasa LED'lerini Aç")
        self.btn_toggle.setStyleSheet("background: #ef4444; color: white; font-weight: bold;" if self.rgb.is_enabled else "background: #10b981; color: white; font-weight: bold;")
        self.btn_toggle.clicked.connect(self.toggle_rgb)
        btn_box.addWidget(self.btn_toggle)

        btn_box.addStretch()

        btn_close = QPushButton("✅ Kapat")
        btn_close.setStyleSheet("background: #10b981; color: white; font-weight: 700; padding: 9px 20px; border-radius: 6px;")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)

        self.main_layout.addLayout(btn_box)

        # Trigger dynamic geometry update
        self.adjustSize()

    def auto_scan_conflicts(self):
        conflicts = ConflictProcessResolver.scan_conflicts()
        if conflicts:
            labels = [c['label'] for c in conflicts]
            self.lbl_conflict_info.setText(
                f"🟢 Tespit Edilen Arka Plan Yazılımları: ({', '.join(labels)}).\n"
                f"⚡ Doğrudan Üstüne Yazma Aktif: Bu uygulamaları KAPATMANIZA GEREK YOKTUR! LED efekti arka plandaki uygulamalar açık kalsa dahi donanımın üstüne doğrudan yansıtılır."
            )
            self.lbl_conflict_info.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 600;")
        else:
            self.lbl_conflict_info.setText("🟢 Donanım Kanalları Açık: Arka planda donanımı kilitleyen servis bulunamadı. LED'leriniz doğrudan yönetiliyor.")
            self.lbl_conflict_info.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 600;")

    def resolve_conflicts(self):
        stopped = ConflictProcessResolver.terminate_conflicts()
        if stopped:
            QMessageBox.information(self, "Servisler Kapatıldı", f"Çakışan şu RGB servisleri kapatıldı ve donanım kilidi açıldı:\n\n- " + "\n- ".join(stopped))
        else:
            QMessageBox.information(self, "Çakışma Bulunamadı", "Çalışan herhangi bir çakışan RGB servisi tespit edilmedi.")
        self.auto_scan_conflicts()
        self.rescan_ports()

    def rescan_ports(self):
        self.rgb.hw_bridge.scan_and_connect_com_ports()
        com_list = self.rgb.hw_bridge.com_ports
        count = len(com_list)
        self.lbl_status.setText(f"🔌 Donanım Kanalı: UDP Broadcast / COM ({count} Port Aktif)")
        QMessageBox.information(self, "Port Taraması", f"{count} adet seri port ve UDP donanım kanalı tarandı!")

    def turn_off_leds(self):
        # Set RGB controller mode to 'off' - background thread safely sends (0, 0, 0)
        self.rgb.set_mode('off')
        self.rgb.current_output_rgb = (0, 0, 0)
        
        # Sync combo box selection
        idx = self.combo_mode.findData('off')
        if idx >= 0:
            self.combo_mode.blockSignals(True)
            self.combo_mode.setCurrentIndex(idx)
            self.combo_mode.blockSignals(False)

        QMessageBox.information(self, "LED'ler Karartıldı", "🖤 Tüm kasa ARGB LED'leri, RAM'ler ve soğutucu ışıkları kapatıldı (Blackout)!")

    def closeEvent(self, event):
        try:
            if self.rgb:
                self.rgb.close()
        except Exception:
            pass
        event.accept()

    def on_mode_changed(self):
        mode_key = self.combo_mode.currentData()
        self.rgb.set_mode(mode_key)

    def on_scheme_changed(self):
        scheme_key = self.combo_scheme.currentData()
        self.rgb.set_color_scheme_mode(scheme_key)

    def pick_color1(self):
        col = QColorDialog.getColor()
        if col.isValid():
            self.rgb.color1 = (col.red(), col.green(), col.blue())
            self.btn_col1.setStyleSheet(f"background: {col.name()}; color: white; font-weight: bold;")

    def pick_color2(self):
        col = QColorDialog.getColor()
        if col.isValid():
            self.rgb.color2 = (col.red(), col.green(), col.blue())
            self.btn_col2.setStyleSheet(f"background: {col.name()}; color: white; font-weight: bold;")

    def pick_color3(self):
        col = QColorDialog.getColor()
        if col.isValid():
            self.rgb.color3 = (col.red(), col.green(), col.blue())
            self.btn_col3.setStyleSheet(f"background: {col.name()}; color: white; font-weight: bold;")

    def on_bright_changed(self, val):
        self.rgb.brightness = val / 100.0

    def on_speed_changed(self, val):
        self.rgb.speed = val / 10.0

    def toggle_rgb(self):
        self.rgb.is_enabled = not self.rgb.is_enabled
        if self.rgb.is_enabled:
            self.btn_toggle.setText("⏹️ Kasa LED'lerini Kapat")
            self.btn_toggle.setStyleSheet("background: #ef4444; color: white; font-weight: bold;")
        else:
            self.btn_toggle.setText("▶️ Kasa LED'lerini Aç")
            self.btn_toggle.setStyleSheet("background: #10b981; color: white; font-weight: bold;")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = StandaloneRGBStudioApp()
    window.show()
    sys.exit(app.exec_())
