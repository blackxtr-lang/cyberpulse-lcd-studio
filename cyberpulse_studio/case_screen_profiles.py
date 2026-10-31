"""
CYBERPULSE LCD Studio - PC Kasa Ekranları ve Entegre Ekranlı Kasalar Kataloğu
Piyasadaki tüm popüler kasa ekranlarını, harici donanım panellerini,
Windows çoklu ekran / USB COM port otomatik tanıma motorunu ve
HDMI Kasa İçi Yansıtma Penceresini (Companion Window) içerir.
"""

import os
import sys
import copy
import io
import time
from PIL import Image, ImageFilter

from PyQt5.QtCore import Qt, QRect, QPoint, QSize, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush, QIcon, QFont, QCursor, QLinearGradient
from PyQt5.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QLineEdit,
    QComboBox, QCheckBox, QMessageBox, QTabWidget, QSizePolicy, QMenu, QAction, QProgressBar
)

# -------------------------------------------------------------
# 1. PİYASADAKİ TÜM KASA EKRANLARI VE MODELLERİ KATALOĞU
# -------------------------------------------------------------
CASE_SCREEN_PRESETS = [
    # ------------------ ENTEGRE EKRANLI KASALAR ------------------
    {
        "id": "soeyi_ch1_119",
        "brand": "Soeyi",
        "model": "Soeyi CH1 / U600 Vision LCD (11.9\")",
        "category": "Entegre Kasa Ekranı",
        "width": 320,
        "height": 1480,
        "diagonal": "11.9 inç",
        "aspect_desc": "8:37 (Ultra Dikey Bar)",
        "default_orientation": "portrait",
        "conn_type": "usb_serial",
        "desc": "Akvaryum tipi panoramik kasaya entegre 11.9 inç dikey IPS LCD panel. USB 9-pin veya Type-C ile COM port üzerinden veri alır."
    },
    {
        "id": "hyte_y70_touch",
        "brand": "Hyte",
        "model": "Hyte Y70 / Y70 Touch (14.1\" 4K)",
        "category": "Entegre Kasa Ekranı",
        "width": 1100,
        "height": 3840,
        "diagonal": "14.1 inç",
        "aspect_desc": "11:38 (~1:3.5 Dikey 4K)",
        "default_orientation": "portrait",
        "conn_type": "hdmi_monitor",
        "desc": "Hyte Y70 köşe paneline entegre 14.1 inç 4K 10 noktalı dokunmatik ekran. Dahili DisplayPort/HDMI ile GPU'ya ve USB ile anakarta bağlanır."
    },
    {
        "id": "hyte_y70_touch_infinite",
        "brand": "Hyte",
        "model": "Hyte Y70 Touch Infinite (14.9\" 2.5K)",
        "category": "Entegre Kasa Ekranı",
        "width": 688,
        "height": 2560,
        "diagonal": "14.9 inç",
        "aspect_desc": "43:160 (~1:3.7 Dikey 2.5K)",
        "default_orientation": "portrait",
        "conn_type": "hdmi_monitor",
        "desc": "Güncellenmiş 14.9 inç 2.5K 60Hz dokunmatik köşe ekranı. HDMI/DisplayPort üzerinden ikincil Windows ekranı olarak çalışır."
    },
    {
        "id": "hyte_y60_lcd_bar",
        "brand": "Hyte",
        "model": "Hyte Y60 LCD Mod Kit (12.6\" Yatay Bar)",
        "category": "Entegre Kasa Ekranı",
        "width": 1920,
        "height": 515,
        "diagonal": "12.6 inç",
        "aspect_desc": "32:9 (Ultrawide Bar)",
        "default_orientation": "landscape",
        "conn_type": "hdmi_monitor",
        "desc": "Hyte Y60 köşe camı yerine takılan 12.6 inç ultra geniş LCD panel. Mini-HDMI kablosuyla GPU'ya bağlanır."
    },
    {
        "id": "hyte_y60_lcd_portrait",
        "brand": "Hyte",
        "model": "Hyte Y60 LCD Mod Kit (12.6\" Dikey Bar)",
        "category": "Entegre Kasa Ekranı",
        "width": 515,
        "height": 1920,
        "diagonal": "12.6 inç",
        "aspect_desc": "9:32 (Dikey Ultrawide Bar)",
        "default_orientation": "portrait",
        "conn_type": "hdmi_monitor",
        "desc": "Hyte Y60 köşe paneli dikey yönlendirme modu."
    },
    {
        "id": "jonsbo_d31_landscape",
        "brand": "Jonsbo",
        "model": "Jonsbo D31 / D41 Screen Edition (8.0\" Yatay)",
        "category": "Entegre Kasa Ekranı",
        "width": 1280,
        "height": 800,
        "diagonal": "8.0 inç",
        "aspect_desc": "16:10 (Yatay IPS)",
        "default_orientation": "landscape",
        "conn_type": "hdmi_monitor",
        "desc": "Kasa ön paneline gömülü veya harici masaüstü standı ile kullanılan 8 inç 1280x800 IPS ekran. Mini-HDMI + Type-C."
    },
    {
        "id": "jonsbo_d31_portrait",
        "brand": "Jonsbo",
        "model": "Jonsbo D31 / D41 Screen Edition (8.0\" Dikey)",
        "category": "Entegre Kasa Ekranı",
        "width": 800,
        "height": 1280,
        "diagonal": "8.0 inç",
        "aspect_desc": "10:16 (Dikey IPS)",
        "default_orientation": "portrait",
        "conn_type": "hdmi_monitor",
        "desc": "Jonsbo D31/D41 ön panel ekranının dikey yönlendirilmiş modu."
    },
    {
        "id": "thermaltake_tower_lcd",
        "brand": "Thermaltake",
        "model": "Thermaltake Tower / Ceres LCD Panel Kit (3.9\")",
        "category": "Entegre Kasa Ekranı",
        "width": 128,
        "height": 480,
        "diagonal": "3.9 inç",
        "aspect_desc": "4:15 (Dikey Dar Bar)",
        "default_orientation": "portrait",
        "conn_type": "usb_serial",
        "desc": "Tower 500/600 ve Ceres 300/500 kasalar için 3.9 inç alt panel LCD kiti. Dahili USB bağlantısı."
    },

    # ------------------ ULTRAWIDE BAR VE HARİCİ KASA PANELLERİ ------------------
    {
        "id": "turzx_88_bar_landscape",
        "brand": "Turing / Turzx",
        "model": "Turing / Turzx 8.8\" Smart Screen (Yatay Bar)",
        "category": "Ultrawide Bar Ekran",
        "width": 1920,
        "height": 480,
        "diagonal": "8.8 inç",
        "aspect_desc": "4:1 (32:9 Ultrawide Bar)",
        "default_orientation": "landscape",
        "conn_type": "both",
        "desc": "Ekran kartı altına veya PSU kapağı üzerine monte edilen 8.8 inç IPS bar ekran. Hem Type-C USB seri port hem HDMI versiyonları vardır."
    },
    {
        "id": "turzx_88_bar_portrait",
        "brand": "Turing / Turzx",
        "model": "Turing / Turzx 8.8\" Smart Screen (Dikey Bar)",
        "category": "Ultrawide Bar Ekran",
        "width": 480,
        "height": 1920,
        "diagonal": "8.8 inç",
        "aspect_desc": "1:4 (9:32 Dikey Bar)",
        "default_orientation": "portrait",
        "conn_type": "both",
        "desc": "Kasa sütunlarına veya anakart yanına dikey konumlandırılan 8.8 inç IPS bar ekran."
    },
    {
        "id": "waveshare_88_bar",
        "brand": "Waveshare / Wisecoco",
        "model": "Waveshare / Wisecoco 8.8\" HDMI Bar Ekran",
        "category": "Ultrawide Bar Ekran",
        "width": 1920,
        "height": 480,
        "diagonal": "8.8 inç",
        "aspect_desc": "32:9 (Yatay Bar)",
        "default_orientation": "landscape",
        "conn_type": "hdmi_monitor",
        "desc": "HDMI girişli popüler 8.8 inç AIDA64 / Windows ikincil kasa içi monitörü."
    },
    {
        "id": "waveshare_119_bar",
        "brand": "Waveshare / Wisecoco",
        "model": "Waveshare 11.9\" HDMI/USB Dikey Bar Ekran",
        "category": "Ultrawide Bar Ekran",
        "width": 320,
        "height": 1480,
        "diagonal": "11.9 inç",
        "aspect_desc": "8:37 (Dikey Bar)",
        "default_orientation": "portrait",
        "conn_type": "both",
        "desc": "Standart 11.9 inç IPS kapasitif dokunmatik dikey kasa içi panel."
    },
    {
        "id": "wisecoco_140_bar_landscape",
        "brand": "Wisecoco",
        "model": "Wisecoco / Barrowch 14.0\" 4K Bar Ekran (Yatay)",
        "category": "Ultrawide Bar Ekran",
        "width": 3840,
        "height": 1100,
        "diagonal": "14.0 inç",
        "aspect_desc": "32:9 (Ultra 4K Bar)",
        "default_orientation": "landscape",
        "conn_type": "hdmi_monitor",
        "desc": "Geniş kasa tabanına monte edilen 14 inç yüksek çözünürlüklü 4K IPS panel. Mini-HDMI / Type-C."
    },
    {
        "id": "wisecoco_140_bar_portrait",
        "brand": "Wisecoco",
        "model": "Wisecoco / Barrowch 14.0\" 4K Bar Ekran (Dikey)",
        "category": "Ultrawide Bar Ekran",
        "width": 1100,
        "height": 3840,
        "diagonal": "14.0 inç",
        "aspect_desc": "9:32 (Dikey 4K Bar)",
        "default_orientation": "portrait",
        "conn_type": "hdmi_monitor",
        "desc": "Kasa dikey sütunları için 14 inç 4K yüksek PPI gösterge paneli."
    },

    # ------------------ MİNİ VE KOMPAKT SENSÖR PANELLERİ ------------------
    {
        "id": "turzx_35_portrait",
        "brand": "Turing / Turzx",
        "model": "Turing / Turzx 3.5\" Mini Panel (Dikey)",
        "category": "Sensör Paneli",
        "width": 320,
        "height": 480,
        "diagonal": "3.5 inç",
        "aspect_desc": "2:3 (Dikey Mini)",
        "default_orientation": "portrait",
        "conn_type": "usb_serial",
        "desc": "Dünyanın en yaygın USB 9-pin Type-C mini kasa sensör paneli. HDMI gerektirmez."
    },
    {
        "id": "turzx_35_landscape",
        "brand": "Turing / Turzx",
        "model": "Turing / Turzx 3.5\" Mini Panel (Yatay)",
        "category": "Sensör Paneli",
        "width": 480,
        "height": 320,
        "diagonal": "3.5 inç",
        "aspect_desc": "3:2 (Yatay Mini)",
        "default_orientation": "landscape",
        "conn_type": "usb_serial",
        "desc": "Turing 3.5 inç panelin yatay montaj modu."
    },
    {
        "id": "turzx_50_landscape",
        "brand": "Turing / Turzx",
        "model": "Turing / Turzx 5.0\" IPS Panel (Yatay)",
        "category": "Sensör Paneli",
        "width": 800,
        "height": 480,
        "diagonal": "5.0 inç",
        "aspect_desc": "5:3 (Yatay)",
        "default_orientation": "landscape",
        "conn_type": "both",
        "desc": "5 inç IPS USB/HDMI kasa sensör göstergesi."
    },
    {
        "id": "turzx_50_portrait",
        "brand": "Turing / Turzx",
        "model": "Turing / Turzx 5.0\" IPS Panel (Dikey)",
        "category": "Sensör Paneli",
        "width": 480,
        "height": 800,
        "diagonal": "5.0 inç",
        "aspect_desc": "3:5 (Dikey)",
        "default_orientation": "portrait",
        "conn_type": "both",
        "desc": "5 inç IPS panel dikey mod."
    },
    {
        "id": "waveshare_70_landscape",
        "brand": "Waveshare / Elecrow",
        "model": "Waveshare / Elecrow 7.0\" IPS Panel",
        "category": "Sensör Paneli",
        "width": 1024,
        "height": 600,
        "diagonal": "7.0 inç",
        "aspect_desc": "128:75 (~16:9)",
        "default_orientation": "landscape",
        "conn_type": "hdmi_monitor",
        "desc": "7 inç HDMI + USB dokunmatik modül. Kasa fan ızgaralarına veya PSU kapağına monte edilir."
    },

    # ------------------ AIO SIVI SOĞUTMA BLOKLARI ------------------
    {
        "id": "aio_cooler_square_round",
        "brand": "AIO Sıvı Soğutucu",
        "model": "AIO Pompa Bloğu LCD (Kraken / Corsair / Lian Li)",
        "category": "AIO Sıvı Soğutma LCD",
        "width": 480,
        "height": 480,
        "diagonal": "2.1 - 2.8 inç",
        "aspect_desc": "1:1 (Kare / Dairesel)",
        "default_orientation": "portrait",
        "conn_type": "both",
        "desc": "İşlemci soğutucu bloğu üzerine dairesel veya kare formatta canlı telemetri/GIF yayını."
    },

    # ------------------ STANDART İKİNCİL EKRANLAR ------------------
    {
        "id": "std_secondary_720p",
        "brand": "Genel Monitör",
        "model": "Standart 720p İkincil Ekran (1280×720)",
        "category": "Standart Ekran",
        "width": 1280,
        "height": 720,
        "diagonal": "Değişken",
        "aspect_desc": "16:9 Yatay",
        "default_orientation": "landscape",
        "conn_type": "hdmi_monitor",
        "desc": "HDMI veya DisplayPort üzerinden bağlı 720p ikincil monitör veya sensör paneli."
    },
    {
        "id": "std_secondary_1080p",
        "brand": "Genel Monitör",
        "model": "Standart 1080p İkincil Ekran (1920×1080)",
        "category": "Standart Ekran",
        "width": 1920,
        "height": 1080,
        "diagonal": "Değişken",
        "aspect_desc": "16:9 Yatay",
        "default_orientation": "landscape",
        "conn_type": "hdmi_monitor",
        "desc": "Standart Full HD ikincil monitör veya kasa içi geniş panel."
    },
]


def find_preset_for_resolution(width, height):
    """Verilen çözünürlükle eşleşen bilinen kasa ekranı modelini bulur."""
    w, h = int(width), int(height)
    for p in CASE_SCREEN_PRESETS:
        pw, ph = p['width'], p['height']
        if (w == pw and h == ph) or (w == ph and h == pw):
            return p
    return None


def adapt_theme_elements_to_resolution(theme_data, new_w, new_h):
    """
    Kullanıcı farklı bir kasa ekranı veya 1080p/2K/4K monitör çözünürlüğü seçtiğinde,
    mevcut temanın tüm öğelerini hedef ekranın kendi çözünürlüğüne (örn. 1920x1080)
    akıllıca uyarlar.
    - 320x1480 dikey şeritten 1920x1080 (veya geniş ekran) yatay çözünürlüğe geçildiğinde
      öğeleri ezmek yerine otomatik çok sütunlu geniş ekran (Widescreen Grid) düzenine yerleştirir.
    - 320x1480 orijinal düzeni yedekler; tekrar 320x1480'e dönüldüğünde sıfır kayıpla geri yükler.
    """
    target_w = max(64, min(4096, int(new_w)))
    target_h = max(64, min(4096, int(new_h)))
    curr_w = int(theme_data.get('width', 320))
    curr_h = int(theme_data.get('height', 1480))

    if curr_w <= 0 or curr_h <= 0 or (curr_w == target_w and curr_h == target_h):
        theme_data['width'] = target_w
        theme_data['height'] = target_h
        return theme_data

    # 1. Save lossless 320x1480 baseline before first adaptation
    if curr_w == 320 and curr_h == 1480 and '_orig_320x1480_backup' not in theme_data:
        theme_data['_orig_320x1480_backup'] = copy.deepcopy(theme_data.get('elements', []))

    # 2. If returning to 320x1480 and backup exists, restore pixel-perfect original elements!
    if target_w == 320 and target_h == 1480 and '_orig_320x1480_backup' in theme_data:
        theme_data['width'] = 320
        theme_data['height'] = 1480
        theme_data['elements'] = copy.deepcopy(theme_data['_orig_320x1480_backup'])
        return theme_data

    # Determine source elements: if current theme is already landscape and target is landscape, scale directly from current!
    curr_is_landscape = (curr_w > curr_h)
    target_is_landscape = (target_w > target_h)

    if curr_is_landscape and target_is_landscape:
        src_elements = copy.deepcopy(theme_data.get('elements', []))
        old_w, old_h = float(curr_w), float(curr_h)
    elif '_orig_320x1480_backup' in theme_data:
        src_elements = copy.deepcopy(theme_data['_orig_320x1480_backup'])
        old_w, old_h = 320.0, 1480.0
    else:
        src_elements = copy.deepcopy(theme_data.get('elements', []))
        old_w, old_h = float(curr_w), float(curr_h)

    theme_data['width'] = target_w
    theme_data['height'] = target_h

    # Smart Portrait-to-Landscape Widescreen Grid Adaptation (e.g. 320x1480 -> 1920x1080 Full HD!)
    if old_w < old_h and target_is_landscape and len(src_elements) > 0:
        pad_x = max(24, int(target_w * 0.025))
        pad_y = max(20, int(target_h * 0.03))
        gap_x = max(18, int(target_w * 0.018))
        gap_y = max(14, int(target_h * 0.022))

        ordered = sorted(src_elements, key=lambda e: (float(e.get('y', 0)), float(e.get('x', 0))))
        top_banners = [e for e in ordered if e.get('type') == 'marquee' and float(e.get('y', 0)) < old_h * 0.2]
        grid_items = [e for e in ordered if e not in top_banners]

        new_elements = []
        curr_top_y = pad_y
        f_scale = max(0.85, min(1.8, target_h / 900.0))

        for b_el in top_banners:
            bh = max(36, min(90, int(target_h * 0.065)))
            b_el['x'] = pad_x
            b_el['y'] = curr_top_y
            b_el['width'] = max(120, target_w - pad_x * 2)
            b_el['height'] = bh
            if 'fontSize' in b_el:
                b_el['fontSize'] = max(14, min(64, int(round(b_el.get('fontSize', 22) * f_scale))))
            new_elements.append(b_el)
            curr_top_y += bh + gap_y

        n_items = len(grid_items)
        if n_items > 0:
            aspect = float(target_w) / max(1.0, float(target_h))
            cols = 4 if (aspect >= 2.3 and n_items >= 4) else (3 if n_items >= 5 else max(1, min(2, n_items)))
            rows = max(1, (n_items + cols - 1) // cols)
            avail_w = max(200, target_w - pad_x * 2 - gap_x * (cols - 1))
            avail_h = max(120, target_h - curr_top_y - pad_y - gap_y * (rows - 1))
            cell_w = avail_w // cols
            cell_h = avail_h // rows

            for idx, g_el in enumerate(grid_items):
                c_i = idx % cols
                r_i = idx // cols
                cell_x = pad_x + c_i * (cell_w + gap_x)
                cell_y = curr_top_y + r_i * (cell_h + gap_y)
                el_type = g_el.get('type', 'sensor')

                if el_type in ('circle_gauge', 'animated_fan', 'custom_image'):
                    side = max(48, min(cell_w, int(cell_h * 0.92), int(target_h * 0.28)))
                    g_el['width'] = side
                    g_el['height'] = side
                    g_el['x'] = cell_x + (cell_w - side) // 2
                    g_el['y'] = cell_y + max(0, (cell_h - side) // 2)
                elif el_type == 'vertical_gauge':
                    vw = max(48, min(cell_w // 2, int(target_w * 0.08)))
                    vh = max(60, min(cell_h, int(target_h * 0.35)))
                    g_el['width'] = vw
                    g_el['height'] = vh
                    g_el['x'] = cell_x + (cell_w - vw) // 2
                    g_el['y'] = cell_y + max(0, (cell_h - vh) // 2)
                else:
                    orig_h = float(g_el.get('height', 50))
                    scaled_h = max(42, min(cell_h, int(round(orig_h * max(1.0, target_h / 720.0)))))
                    g_el['width'] = max(80, cell_w)
                    g_el['height'] = scaled_h
                    g_el['x'] = cell_x
                    g_el['y'] = cell_y + max(0, (cell_h - scaled_h) // 2)

                if 'fontSize' in g_el and el_type != 'box':
                    g_el['fontSize'] = max(12, min(72, int(round(g_el.get('fontSize', 18) * f_scale))))
                if 'valueFontSize' in g_el and el_type != 'box':
                    g_el['valueFontSize'] = max(14, min(96, int(round(g_el.get('valueFontSize', 24) * f_scale))))
                new_elements.append(g_el)

        theme_data['elements'] = new_elements
        return theme_data

    # Standard proportional scaling (same orientation or landscape -> portrait)
    scale_x = float(target_w) / old_w
    scale_y = float(target_h) / old_h
    font_scale = max(0.75, min(2.4, min(scale_x, scale_y) if scale_x > 1.0 and scale_y > 1.0 else scale_y))

    new_elements = []
    for el in src_elements:
        el_type = el.get('type', 'sensor')
        el_x = float(el.get('x', 0))
        el_y = float(el.get('y', 0))
        el_w = float(el.get('width', 100))
        el_h = float(el.get('height', 40))

        if el_type in ('circle_gauge', 'animated_fan', 'custom_image'):
            cx = (el_x + el_w * 0.5) * scale_x
            cy = (el_y + el_h * 0.5) * scale_y
            uni_scale = min(scale_x, scale_y) if scale_x < scale_y else max(0.85, scale_y)
            new_el_w = max(36, int(round(el_w * uni_scale)))
            new_el_h = max(36, int(round(el_h * uni_scale)))
            new_el_x = int(round(cx - new_el_w * 0.5))
            new_el_y = int(round(cy - new_el_h * 0.5))
        else:
            new_el_x = int(round(el_x * scale_x))
            new_el_y = int(round(el_y * scale_y))
            new_el_w = max(24, int(round(el_w * scale_x)))
            new_el_h = max(18, int(round(el_h * scale_y)))

        el['x'] = max(0, min(max(0, target_w - new_el_w), new_el_x))
        el['y'] = max(0, min(max(0, target_h - new_el_h), new_el_y))
        el['width'] = min(target_w, new_el_w)
        el['height'] = min(target_h, new_el_h)

        if 'fontSize' in el and el_type != 'box':
            el['fontSize'] = max(11, int(round(el['fontSize'] * font_scale)))
        if 'valueFontSize' in el and el_type != 'box':
            el['valueFontSize'] = max(12, int(round(el['valueFontSize'] * font_scale)))
        new_elements.append(el)

    theme_data['elements'] = new_elements
    return theme_data


def detect_all_available_screens(hardware_driver=None):
    """
    Sistemdeki tüm fiziksel bağlantıları (Windows HDMI/DP monitörleri ve USB COM port ekranları)
    otomatik tarayıp birleştirilmiş bir liste halinde döndürür.
    """
    results = {
        "screens": [],
        "monitors": [],
        "com_ports": [],
        "primary_index": 0,
        "has_case_screen": False,
        "recommended_id": None
    }

    # 1. USB Serial / COM Port Displays first so real USB LCD hardware gets priority recommendation
    usb_entries = []
    try:
        if hardware_driver and hasattr(hardware_driver, 'list_available_com_ports'):
            ports = hardware_driver.list_available_com_ports()
        else:
            from hardware_driver import HardwareDriver
            ports = HardwareDriver.list_available_com_ports()

        sorted_ports = sorted(ports, key=lambda x: not x.get('is_lcd', False))

        for p in sorted_ports:
            port_name = p.get('device', '')
            desc = p.get('description', '')
            is_lcd = p.get('is_lcd', False)
            vid = p.get('vid', '')

            default_w, default_h = 320, 1480
            if "33c3" in str(vid).lower() or is_lcd:
                matched_name = "Soeyi / DLS USB LCD (320×1480)"
                is_lcd = True
                display_label = f"📟 Kasa Ekranı: {port_name} ({matched_name})"
            else:
                matched_name = "Genel USB Seri Cihazı"
                is_lcd = False
                display_label = f"🔌 Seri Port: {port_name} - {desc} ({matched_name})"

            com_entry = {
                "unique_id": f"com_{port_name}",
                "type": "usb_serial",
                "output_mode": "usb_serial",
                "port": port_name,
                "name": port_name,
                "description": desc,
                "label": display_label,
                "width": default_w,
                "height": default_h,
                "is_primary": False,
                "is_lcd": is_lcd,
                "is_case_screen": is_lcd,
                "matched_preset": find_preset_for_resolution(default_w, default_h)
            }
            usb_entries.append(com_entry)
            if is_lcd and not results["recommended_id"]:
                results["recommended_id"] = com_entry["unique_id"]
                results["has_case_screen"] = True
    except Exception as e:
        print("USB port detection note:", e)

    # 2. Windows Display Monitors (HDMI, DisplayPort, Type-C)
    try:
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)

        if app:
            qt_screens = app.screens()
            primary_screen = app.primaryScreen()

            for i, s in enumerate(qt_screens):
                geo = s.geometry()
                sw, sh = geo.width(), geo.height()
                is_prim = (s == primary_screen)

                matched_preset = find_preset_for_resolution(sw, sh)
                screen_title = s.name()

                is_probable_case_screen = False
                if not is_prim:
                    aspect = max(sw, sh) / max(1, min(sw, sh))
                    if aspect > 2.2 or min(sw, sh) <= 900:
                        is_probable_case_screen = True

                display_label = f"Ekran {i + 1}: {screen_title} ({sw}×{sh})"
                if is_prim:
                    display_label += " [Ana Monitör]"
                else:
                    display_label += " [İkincil Monitör]"
                if matched_preset:
                    display_label += f" [{matched_preset['brand']} {matched_preset['model']}]"
                elif is_probable_case_screen:
                    display_label += " [Olası Kasa Ekranı]"

                screen_entry = {
                    "unique_id": f"mon_{i}",
                    "type": "hdmi_monitor",
                    "output_mode": "hdmi_monitor",
                    "qt_index": i,
                    "index": i,
                    "name": screen_title,
                    "label": display_label,
                    "width": sw,
                    "height": sh,
                    "x": geo.x(),
                    "y": geo.y(),
                    "is_primary": is_prim,
                    "is_case_screen": is_probable_case_screen,
                    "matched_preset": matched_preset
                }
                results["screens"].append(screen_entry)
                results["monitors"].append(screen_entry)

                if is_prim:
                    results["primary_index"] = len(results["screens"]) - 1
                elif is_probable_case_screen and not results["recommended_id"]:
                    results["recommended_id"] = screen_entry["unique_id"]
                    results["has_case_screen"] = True
    except Exception as e:
        print("Monitor detection note:", e)

    for c_ent in usb_entries:
        results["screens"].append(c_ent)
        results["com_ports"].append(c_ent)

    return results


# -------------------------------------------------------------
# 2. HDMI KASA İÇİ & İKİNCİL MONİTÖR YANSITMA PENCERESİ (COMPANION DISPLAY)
# -------------------------------------------------------------
class HDMICompanionDisplayWindow(QWidget):
    """
    HDMI / DisplayPort üzerinden bağlı kasa ekranlarına veya 1080p/2K/4K ikincil monitörlere
    tam ekran çerçevesiz görüntü yansıtan gelişmiş pencere.
    Desteklenen Görünüm Modları (hdmi_view_mode):
      - 'ambient_dashboard': 16:9 Geniş Ekran Canlı Telemetri Kanatları + Merkez Kasa Paneli + Blur Arka Plan
      - 'ambient_fit'      : Sinematik Blur Arka Plan + Merkez Kasa Paneli
      - 'letterbox'        : Klasik Siyah Arka Plan + Orijinal Oranlı Merkez Panel
      - 'stretch'          : Tam Ekran Kapla / Uzat (Stretch)
    """
    closed_signal = pyqtSignal()

    VIEW_MODES = [
        ("ambient_dashboard", "✨ Geniş Ekran Dashboard + Kasa Paneli"),
        ("ambient_fit", "🌌 Sinematik Ambiance (Yalnızca Merkez Panel)"),
        ("letterbox", "📐 Orijinal Oran (Siyah Arka Plan)"),
        ("stretch", "↔️ Tam Ekran Kapla (Stretch)")
    ]

    def __init__(self, main_gui_ref, slot_config=None):
        super().__init__()
        self.gui = main_gui_ref
        self.slot_config = slot_config  # Optional per-screen workspace dict
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #060911;")
        self.current_pixmap = None
        self.ambient_bg_pixmap = None
        self._ambient_counter = 0
        try:
            raw_mon = slot_config.get('monitor_index', 1) if isinstance(slot_config, dict) else 1
            self.target_screen_index = max(0, min(16, int(raw_mon if raw_mon is not None else 1)))
        except (ValueError, TypeError):
            self.target_screen_index = 1
        self.setWindowTitle("CYBERPULSE HDMI Case Display")

        self._toast_text = ""
        self._toast_until = 0.0

        # Auto-hide mouse cursor after 3 seconds of inactivity so mouse is never lost when moving across monitors
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.timeout.connect(lambda: self.setCursor(Qt.BlankCursor))
        self._cursor_timer.start(3000)

    def show_toast(self, msg, duration_sec=2.5):
        self._toast_text = msg
        self._toast_until = time.time() + duration_sec
        self.update()

    def get_view_mode(self):
        if isinstance(self.slot_config, dict) and self.slot_config.get('hdmi_view_mode'):
            return self.slot_config.get('hdmi_view_mode', 'ambient_dashboard')
        if hasattr(self.gui, 'app_settings'):
            return self.gui.app_settings.get('hdmi_view_mode', 'ambient_dashboard')
        return 'ambient_dashboard'

    def set_view_mode(self, mode_key):
        if isinstance(self.slot_config, dict):
            self.slot_config['hdmi_view_mode'] = mode_key
            if hasattr(self.gui, 'save_screen_workspaces_to_disk'):
                self.gui.save_screen_workspaces_to_disk()
        if hasattr(self.gui, 'app_settings'):
            self.gui.app_settings['hdmi_view_mode'] = mode_key
            if hasattr(self.gui, 'save_app_settings'):
                self.gui.save_app_settings()
        label = dict(self.VIEW_MODES).get(mode_key, mode_key)
        self.show_toast(f"🖥️ Görünüm Modu: {label}")

    def cycle_view_mode(self):
        curr = self.get_view_mode()
        keys = [k for k, _ in self.VIEW_MODES]
        idx = (keys.index(curr) + 1) % len(keys) if curr in keys else 0
        self.set_view_mode(keys[idx])

    def get_hdmi_rotation(self):
        try:
            if isinstance(self.slot_config, dict) and 'hdmi_rotation' in self.slot_config:
                raw_rot = self.slot_config.get('hdmi_rotation', 0)
                return int(raw_rot if raw_rot is not None else 0) % 360
            if hasattr(self.gui, 'app_settings'):
                raw_rot = self.gui.app_settings.get('hdmi_rotation', 0)
                return int(raw_rot if raw_rot is not None else 0) % 360
        except (ValueError, TypeError):
            pass
        return 0

    def set_hdmi_rotation(self, deg):
        try:
            deg = int(deg) % 360
        except (ValueError, TypeError):
            deg = 0
        if deg not in (0, 90, 180, 270):
            deg = 0
        if isinstance(self.slot_config, dict):
            self.slot_config['hdmi_rotation'] = deg
            if hasattr(self.gui, 'save_screen_workspaces_to_disk'):
                self.gui.save_screen_workspaces_to_disk()
        if hasattr(self.gui, 'app_settings'):
            self.gui.app_settings['hdmi_rotation'] = deg
            if hasattr(self.gui, 'save_app_settings'):
                self.gui.save_app_settings()
        self.show_toast(f"🔄 HDMI Yönü: {deg}°")

    def attach_to_screen(self, screen_index):
        app = QApplication.instance()
        if not app:
            return False

        screens = app.screens()
        if 0 <= screen_index < len(screens):
            target_screen = screens[screen_index]
        elif len(screens) > 1:
            target_screen = screens[-1]
            screen_index = len(screens) - 1
        elif len(screens) == 1:
            target_screen = screens[0]
            screen_index = 0
        else:
            return False

        self.target_screen_index = screen_index
        geo = target_screen.geometry()

        # Ensure clean screen transition across different DPI monitors
        if self.isVisible():
            self.hide()

        self.setGeometry(geo)
        self.move(geo.x(), geo.y())
        self.resize(geo.width(), geo.height())
        self.show()

        try:
            wh = self.windowHandle()
            if wh:
                wh.setScreen(target_screen)
                wh.setPosition(geo.x(), geo.y())
                wh.resize(geo.width(), geo.height())
        except Exception:
            pass

        self.setGeometry(geo)
        self.raise_()
        self.show_toast(f"🖥️ {target_screen.name()} ({geo.width()}×{geo.height()}) — [Sağ Tık: Menü | M: Görünüm | ESC: Kapat]", 3.5)
        return True

    def show_on_monitor(self, monitor_index=None):
        if monitor_index is None:
            monitor_index = getattr(self, 'target_screen_index', 1)
        return self.attach_to_screen(monitor_index)

    def update_frame(self, pil_image):
        return self.update_frame_from_pil(pil_image)

    def update_frame_from_pil(self, pil_image):
        try:
            if pil_image is None:
                return
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')

            hdmi_rot = self.get_hdmi_rotation()
            if hdmi_rot == 90:
                pil_image = pil_image.rotate(90, expand=True)
            elif hdmi_rot == 180:
                pil_image = pil_image.rotate(180)
            elif hdmi_rot == 270:
                pil_image = pil_image.rotate(270, expand=True)

            w, h = pil_image.size
            raw_data = pil_image.tobytes('raw', 'RGB')
            qimg = QImage(raw_data, w, h, w * 3, QImage.Format_RGB888).copy()
            self.current_pixmap = QPixmap.fromImage(qimg)

            # Update blurred ambient background every 4 frames (~5Hz) for near-zero CPU cost
            self._ambient_counter = (self._ambient_counter + 1) % 4
            if self.ambient_bg_pixmap is None or self._ambient_counter == 1:
                view_mode = self.get_view_mode()
                if view_mode in ('ambient_dashboard', 'ambient_fit'):
                    small = pil_image.resize((96, 54), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(radius=6))
                    sw, sh = small.size
                    s_raw = small.tobytes('raw', 'RGB')
                    s_qimg = QImage(s_raw, sw, sh, sw * 3, QImage.Format_RGB888).copy()
                    self.ambient_bg_pixmap = QPixmap.fromImage(s_qimg)

            self.update()
        except Exception:
            pass

    def _draw_telemetry_card(self, painter, x, y, w, h, title, accent_hex, rows, bar_pct=None):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Card translucent dark glass background
        painter.setBrush(QColor(11, 15, 25, 215))
        accent_col = QColor(accent_hex)
        pen = QPen(QColor(accent_col.red(), accent_col.green(), accent_col.blue(), 130), 1.5)
        painter.setPen(pen)
        painter.drawRoundedRect(QRect(int(x), int(y), int(w), int(h)), 14, 14)

        # Top accent glow bar
        painter.setPen(Qt.NoPen)
        painter.setBrush(accent_col)
        painter.drawRoundedRect(QRect(int(x + 16), int(y), int(min(90, w * 0.3)), 3), 2, 2)

        # Card Title
        f_title = QFont("Segoe UI", max(10, int(h * 0.075)), QFont.Bold)
        painter.setFont(f_title)
        painter.setPen(accent_col)
        painter.drawText(QRect(int(x + 18), int(y + 12), int(w - 36), 28), Qt.AlignLeft | Qt.AlignVCenter, title)

        # Rows
        num_rows = max(1, len(rows))
        avail_h = h - (58 if bar_pct is not None else 44)
        row_h = max(22, int(avail_h / num_rows))
        curr_y = int(y + 42)

        f_lbl = QFont("Segoe UI", max(9, int(row_h * 0.36)), QFont.DemiBold)
        f_val = QFont("Segoe UI", max(10, int(row_h * 0.44)), QFont.Bold)

        for r_lbl, r_val in rows:
            painter.setFont(f_lbl)
            painter.setPen(QColor(148, 163, 184))
            painter.drawText(QRect(int(x + 18), curr_y, int(w * 0.52), row_h), Qt.AlignLeft | Qt.AlignVCenter, str(r_lbl))

            painter.setFont(f_val)
            painter.setPen(QColor(248, 250, 252))
            painter.drawText(QRect(int(x + w * 0.42), curr_y, int(w * 0.58 - 18), row_h), Qt.AlignRight | Qt.AlignVCenter, str(r_val))
            curr_y += row_h

        # Optional Progress Bar at bottom of card
        if bar_pct is not None:
            bx = int(x + 18)
            by = int(y + h - 18)
            bw = int(w - 36)
            bh = 7
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(30, 41, 59, 220))
            painter.drawRoundedRect(QRect(bx, by, bw, bh), 3, 3)

            fill_w = int(bw * min(1.0, max(0.0, float(bar_pct) / 100.0)))
            if fill_w > 0:
                painter.setBrush(accent_col)
                painter.drawRoundedRect(QRect(bx, by, fill_w, bh), 3, 3)

        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        w, h = self.width(), self.height()
        painter.fillRect(self.rect(), QColor(6, 9, 17))

        if not self.current_pixmap:
            return

        pw, ph = self.current_pixmap.width(), self.current_pixmap.height()
        if pw <= 0 or ph <= 0:
            return

        view_mode = self.get_view_mode()
        theme_aspect = float(pw) / float(max(1, ph))
        mon_aspect = float(w) / float(max(1, h))
        is_native_aspect_match = (abs(theme_aspect - mon_aspect) <= 0.12)

        # 1. Stretch Mode or Native Resolution Match (e.g. 1920x1080 theme on a 1080p/4K 16:9 screen)
        if view_mode == 'stretch' or is_native_aspect_match:
            painter.drawPixmap(0, 0, w, h, self.current_pixmap)
        else:
            # Calculate aspect-preserving center rectangle
            margin_v = int(h * 0.025) if view_mode in ('ambient_dashboard', 'ambient_fit') else 0
            avail_h = max(100, h - margin_v * 2)
            scale = min(float(w) / pw, float(avail_h) / ph)
            dw = int(pw * scale)
            dh = int(ph * scale)
            ox = (w - dw) // 2
            oy = (h - dh) // 2

            # 2. Ambient Backdrop (for ambient_dashboard and ambient_fit)
            if view_mode in ('ambient_dashboard', 'ambient_fit'):
                if self.ambient_bg_pixmap:
                    painter.drawPixmap(0, 0, w, h, self.ambient_bg_pixmap)
                painter.fillRect(self.rect(), QColor(7, 11, 22, 175))

                # Subtle cyber grid lines on backdrop
                grid_pen = QPen(QColor(148, 163, 184, 16), 1)
                painter.setPen(grid_pen)
                for gx in range(0, w, 64):
                    painter.drawLine(gx, 0, gx, h)
                for gy in range(0, h, 64):
                    painter.drawLine(0, gy, w, gy)

            # 3. Side Telemetry Wings when displaying a portrait theme on a widescreen monitor
            side_space = ox - 48
            if view_mode == 'ambient_dashboard' and side_space >= 260 and hasattr(self.gui, 'sensor'):
                m = getattr(self.gui.sensor, 'cached_sensors', {}) or {}
                wing_w = min(560, side_space - 24)
                left_x = (ox - wing_w) // 2
                right_x = ox + dw + (ox - wing_w) // 2

                pad_y = max(24, int(h * 0.045))
                gap_y = max(16, int(h * 0.025))
                card_h = max(140, (h - pad_y * 2 - gap_y * 2) // 3)

                def _num(val_str):
                    try:
                        return float(''.join(c for c in str(val_str).split()[0] if c.isdigit() or c == '.'))
                    except Exception:
                        return 0.0

                # Left Wing Cards: CPU, GPU, RAM & Disk
                cpu_load_num = _num(m.get('cpu_load', '18%'))
                self._draw_telemetry_card(
                    painter, left_x, pad_y, wing_w, card_h,
                    f"⚡ İŞLEMCİ — {m.get('cpu_name', 'CPU')[:28]}",
                    "#38bdf8",
                    [
                        ("CPU Sıcaklığı", m.get('cpu_temp', '60°C')),
                        ("CPU Kullanımı", m.get('cpu_load', '18%')),
                        ("Çekirdek Hızı", m.get('cpu_clock', '4800 MHz')),
                        ("Soğutucu Fan", m.get('cpu_fan', '1050 RPM')),
                    ],
                    bar_pct=cpu_load_num
                )

                gpu_load_num = _num(m.get('gpu_load', '10%'))
                self._draw_telemetry_card(
                    painter, left_x, pad_y + card_h + gap_y, wing_w, card_h,
                    f"🎮 EKRAN KARTI — {m.get('gpu_name', 'GPU')[:26]}",
                    "#10b981",
                    [
                        ("GPU Sıcaklığı", m.get('gpu_temp', '50°C')),
                        ("GPU Kullanımı", m.get('gpu_load', '10%')),
                        ("GPU Fan Devri", m.get('gpu_fan', '0%')),
                        ("GPU Çekirdek", m.get('gpu_clock', '1500 MHz')),
                    ],
                    bar_pct=gpu_load_num
                )

                ram_load_num = _num(m.get('ram_load', '50%'))
                self._draw_telemetry_card(
                    painter, left_x, pad_y + (card_h + gap_y) * 2, wing_w, card_h,
                    "💾 BELLEK & DEPOLAMA",
                    "#a855f7",
                    [
                        ("Kullanılan RAM", f"{m.get('ram_used', '16 GB')} ({m.get('ram_load', '50%')})"),
                        ("Toplam Bellek", m.get('ram_spec', '32 GB DDR5')),
                        ("Disk Aktarımı", m.get('disk_io', '0.5 MB/s')),
                        ("Açık Kalma (Uptime)", m.get('system_uptime', '01s 15dk')),
                    ],
                    bar_pct=ram_load_num
                )

                # Right Wing Cards: Clock/Weather, Game FPS/Network, Media Player
                self._draw_telemetry_card(
                    painter, right_x, pad_y, wing_w, card_h,
                    "⏰ SİSTEM ZAMANI & HAVA DURUMU",
                    "#f59e0b",
                    [
                        ("Dijital Saat", m.get('time_digital', '12:00:00')),
                        ("Tarih & Gün", m.get('date_day_tr', m.get('date_full', ''))),
                        ("Konum / Şehir", m.get('weather_city', 'İstanbul')),
                        ("Hava Durumu", f"{m.get('weather_temp', '20°C')} • {m.get('weather_desc', 'Açık')}"),
                    ]
                )

                self._draw_telemetry_card(
                    painter, right_x, pad_y + card_h + gap_y, wing_w, card_h,
                    "🎯 OYUN PERFORMANSI & AĞ MONİTÖRÜ",
                    "#ec4899",
                    [
                        ("Canlı Oyun FPS", m.get('game_fps', '0 FPS')),
                        ("Sunucu Ping", str(m.get('net_ping', '14 ms')).replace('PING:', '').strip()),
                        ("İndirme Hızı (DL)", str(m.get('net_down', '0 KB/s')).replace('DL:', '').strip()),
                        ("Yükleme Hızı (UL)", str(m.get('net_up', '0 KB/s')).replace('UL:', '').strip()),
                    ]
                )

                active_t_name = (
                    self.slot_config.get('theme_data', {}).get('name')
                    if isinstance(self.slot_config, dict) and isinstance(self.slot_config.get('theme_data'), dict)
                    else getattr(self.gui, 'theme_data', {}).get('name', 'CyberPulse')
                )
                self._draw_telemetry_card(
                    painter, right_x, pad_y + (card_h + gap_y) * 2, wing_w, card_h,
                    "🎵 MEDYA & SİSTEM BİLGİSİ",
                    "#6366f1",
                    [
                        ("Medya Başlığı", str(m.get('music_title', 'Medya Bekleniyor'))[:28]),
                        ("Sanatçı / Kanal", str(m.get('music_artist', '-'))[:28]),
                        ("Anakart", str(m.get('mb_spec', 'Gaming Motherboard'))[:28]),
                        ("Aktif Tema", str(active_t_name or 'CyberPulse')[:28]),
                    ]
                )

            # 4. Draw Glowing Frame & Center Case Screen Pixmap
            if view_mode in ('ambient_dashboard', 'ambient_fit'):
                for g_off, g_alpha in ((6, 30), (3, 75), (1, 160)):
                    painter.setPen(QPen(QColor(56, 189, 248, g_alpha), 2))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRoundedRect(QRect(ox - g_off, oy - g_off, dw + g_off * 2, dh + g_off * 2), 10, 10)

            painter.drawPixmap(ox, oy, dw, dh, self.current_pixmap)

        # 5. Draw HUD Toast if active
        if self._toast_text and time.time() < self._toast_until:
            f_toast = QFont("Segoe UI", 12, QFont.Bold)
            painter.setFont(f_toast)
            tw = min(w - 80, max(360, len(self._toast_text) * 9 + 40))
            th = 42
            tx = (w - tw) // 2
            ty = h - th - 28
            painter.setPen(QPen(QColor(99, 102, 241, 200), 1.5))
            painter.setBrush(QColor(15, 23, 42, 230))
            painter.drawRoundedRect(QRect(tx, ty, tw, th), 10, 10)
            painter.setPen(QColor(248, 250, 252))
            painter.drawText(QRect(tx + 12, ty, tw - 24, th), Qt.AlignCenter, self._toast_text)

    def mouseMoveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)
        self._cursor_timer.start(3000)
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() in (Qt.Key_M, Qt.Key_Space):
            self.cycle_view_mode()
        elif event.key() == Qt.Key_R:
            self.set_hdmi_rotation((self.get_hdmi_rotation() + 90) % 360)
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        self.setCursor(Qt.ArrowCursor)
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #0f172a; color: #f8fafc; border: 1px solid #334155; border-radius: 8px; padding: 6px; font-family: 'Segoe UI'; font-size: 12px; font-weight: 600; }
            QMenu::item { padding: 7px 18px; border-radius: 4px; }
            QMenu::item:selected { background-color: #4f46e5; color: white; }
            QMenu::separator { height: 1px; background: #334155; margin: 4px 0; }
        """)

        curr_mode = self.get_view_mode()
        for m_key, m_lbl in self.VIEW_MODES:
            prefix = "✅ " if m_key == curr_mode else "    "
            act = QAction(f"{prefix}{m_lbl}", self)
            act.triggered.connect(lambda checked=False, k=m_key: self.set_view_mode(k))
            menu.addAction(act)

        menu.addSeparator()
        rot_menu = menu.addMenu("🔄 HDMI Ekran Yönü (Döndür)")
        curr_rot = self.get_hdmi_rotation()
        for r_deg in (0, 90, 180, 270):
            prefix = "✅ " if r_deg == curr_rot else "    "
            r_act = QAction(f"{prefix}{r_deg}° Yönlendirme", self)
            r_act.triggered.connect(lambda checked=False, d=r_deg: self.set_hdmi_rotation(d))
            rot_menu.addAction(r_act)

        app = QApplication.instance()
        if app and len(app.screens()) > 1:
            mon_menu = menu.addMenu("🖥️ Başka Monitöre Taşı")
            for idx, scr in enumerate(app.screens()):
                geo = scr.geometry()
                prefix = "✅ " if idx == self.target_screen_index else "    "
                m_act = QAction(f"{prefix}Ekran {idx + 1}: {scr.name()} ({geo.width()}×{geo.height()})", self)
                def _switch_mon(checked=False, target_i=idx, target_name=scr.name()):
                    if isinstance(self.slot_config, dict):
                        self.slot_config['monitor_index'] = target_i
                        if hasattr(self.gui, 'save_screen_workspaces_to_disk'):
                            self.gui.save_screen_workspaces_to_disk()
                    if hasattr(self.gui, 'app_settings'):
                        self.gui.app_settings['selected_monitor_index'] = target_i
                        self.gui.app_settings['hdmi_screen_index'] = target_i
                        self.gui.app_settings['selected_monitor_name'] = target_name
                        if hasattr(self.gui, 'save_app_settings'):
                            self.gui.save_app_settings()
                        if hasattr(self.gui, 'update_stream_status_ui'):
                            self.gui.update_stream_status_ui()
                    self.attach_to_screen(target_i)
                m_act.triggered.connect(_switch_mon)
                mon_menu.addAction(m_act)

        if hasattr(self.gui, 'apply_preset_theme_to_slot') and hasattr(self.gui, 'get_preset_theme_names'):
            theme_names = self.gui.get_preset_theme_names()
            if theme_names:
                t_menu = menu.addMenu("🎨 Bu Ekranın Temasını Değiştir")
                curr_t = (
                    str(self.slot_config.get('theme_data', {}).get('name', ''))
                    if isinstance(self.slot_config, dict)
                    else str(getattr(self.gui, 'theme_data', {}).get('name', ''))
                ).strip().lower()
                slot_id_val = self.slot_config.get('slot_id') if isinstance(self.slot_config, dict) else None
                for t_name in theme_names:
                    prefix = "✅ " if t_name.strip().lower() == curr_t else "    "
                    t_act = QAction(f"{prefix}{t_name}", self)
                    t_act.triggered.connect(
                        lambda checked=False, sid=slot_id_val, tn=t_name: self.gui.apply_preset_theme_to_slot(sid, tn)
                    )
                    t_menu.addAction(t_act)

        menu.addSeparator()
        close_act = QAction("❌ HDMI Yansıtmayı Kapat (ESC / Çift Tık)", self)
        close_act.triggered.connect(self.close)
        menu.addAction(close_act)

        menu.exec_(event.globalPos())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.close()

    def closeEvent(self, event):
        self.closed_signal.emit()
        event.accept()


# -------------------------------------------------------------
# 3. KASA EKRANI SEÇİCİ VE YÖNETİCİ DİYALOĞU
# -------------------------------------------------------------
class CaseScreenSelectorDialog(QDialog):
    """
    Kullanıcının bilgisayardaki kasa ekranlarını otomatik tespit eden,
    piyasadaki hazır modellerle temayı uyarlayan ve yansıtma hedefini belirleyen arayüz.
    """
    screen_selected_signal = pyqtSignal(dict)
    theme_adapted_signal = pyqtSignal(dict)

    def __init__(self, parent_gui, current_theme_data=None, app_settings=None):
        super().__init__(parent_gui)
        self.gui = parent_gui
        self.current_theme_data = current_theme_data if current_theme_data is not None else getattr(parent_gui, 'theme_data', {})
        self.app_settings = app_settings if app_settings is not None else getattr(parent_gui, 'app_settings', {})
        self.setWindowTitle("🖥️ Kasa Ekranı ve Yansıtma Yöneticisi")
        self.resize(1040, 700)
        self.setStyleSheet("""
            QDialog { background-color: #060e20; color: #dae2fd; font-family: 'Segoe UI', Arial, sans-serif; }
            QLabel { color: #dae2fd; font-size: 13px; font-weight: 600; }
            QTabWidget::pane { border: 1px solid rgba(68, 70, 86, 0.28); background: #0b1326; border-radius: 8px; }
            QTabBar::tab { background: #131b2e; color: #c4c5d9; font-weight: 700; font-size: 12px; padding: 9px 20px; min-width: 210px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 4px; }
            QTabBar::tab:selected { background: #8083ff; color: #07006c; font-weight: 800; }
            QPushButton { background: #171f33; border: 1px solid rgba(68, 70, 86, 0.35); border-radius: 6px; padding: 8px 14px; color: #dae2fd; font-weight: 600; font-size: 12px; }
            QPushButton:hover { background: #222a3d; border-color: #8083ff; color: #ffffff; }
            QPushButton:pressed { background: #8083ff; color: #07006c; }
            QLineEdit { background: #131b2e; border: 1px solid rgba(68, 70, 86, 0.35); border-radius: 6px; padding: 8px 12px; color: #dae2fd; font-size: 13px; }
            QLineEdit:focus { border: 1px solid #38bdf8; background: #171f33; }
            QComboBox { background: #131b2e; border: 1px solid rgba(68, 70, 86, 0.35); border-radius: 6px; padding: 6px 12px; color: #dae2fd; font-weight: 600; }
            QCheckBox { color: #dae2fd; font-weight: 600; font-size: 13px; margin: 4px 0; }
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

        self.detected_data = detect_all_available_screens(self.gui.hardware)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 16, 18, 16)

        # Başlık ve Bilgi
        hdr = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("🖥️ PC Kasa Ekranı ve Cihaz Yöneticisi")
        title.setStyleSheet("font-size: 18px; font-weight: 900; color: #dae2fd;")
        sub = QLabel("Bilgisayardaki kasa ekranlarını otomatik algılayın veya hazır piyasa modellerine uyarlayın.")
        sub.setStyleSheet("font-size: 12px; color: #c4c5d9; font-weight: 500;")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        hdr.addLayout(title_box)
        hdr.addStretch()

        btn_rescan = QPushButton("🔄 Ekranları Yeniden Tara")
        btn_rescan.setStyleSheet("background: #8083ff; color: #07006c; font-weight: 800; padding: 8px 16px; border: none; border-radius: 7px;")
        btn_rescan.clicked.connect(self.rescan_screens)
        hdr.addWidget(btn_rescan)
        layout.addLayout(hdr)

        # Tablar
        self.tabs = QTabWidget()
        self.tab_detected = QWidget()
        self.tab_catalog = QWidget()
        self.tab_settings = QWidget()

        self.build_detected_tab()
        self.build_catalog_tab()
        self.build_settings_tab()

        self.tabs.addTab(self.tab_detected, f"🔍 Algılanan Ekranlar ({len(self.detected_data['screens'])})")
        self.tabs.addTab(self.tab_catalog, f"📚 Kasa Ekranları Kataloğu ({len(CASE_SCREEN_PRESETS)})")
        self.tabs.addTab(self.tab_settings, "⚙️ Yansıtma ve Çıkış Ayarları")
        layout.addWidget(self.tabs)

        # Alt Butonlar
        bottom_box = QHBoxLayout()
        bottom_box.addStretch()

        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.accept)
        bottom_box.addWidget(btn_close)
        layout.addLayout(bottom_box)

    # ------------------ SEKME 1: ALGILANAN EKRANLAR ------------------
    def build_detected_tab(self):
        vbox = QVBoxLayout(self.tab_detected)
        vbox.setContentsMargins(14, 14, 14, 14)
        vbox.setSpacing(10)

        info_lbl = QLabel("💡 Sisteminizde tespit edilen tüm monitörler ve dahili USB LCD donanımları (2 sütunlu Stitch donanım kartları):")
        info_lbl.setStyleSheet("color: #908fa0; font-weight: 700; font-size: 11px;")
        vbox.addWidget(info_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: #0b1326; }")

        self.detected_container = QWidget()
        self.detected_container.setStyleSheet("background: #0b1326;")
        self.detected_vbox = QVBoxLayout(self.detected_container)
        self.detected_vbox.setSpacing(10)
        self.detected_vbox.setContentsMargins(0, 0, 0, 0)

        self.populate_detected_list()

        scroll.setWidget(self.detected_container)
        vbox.addWidget(scroll)

    def populate_detected_list(self):
        # Önceki kartları temizle
        while self.detected_vbox.count():
            item = self.detected_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        current_output_mode = self.gui.app_settings.get('output_mode', 'usb_serial')
        current_hdmi_idx = self.gui.app_settings.get('hdmi_screen_index', 1)
        current_com_port = self.gui.app_settings.get('selected_com_port', 'auto')

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        for idx_i, item in enumerate(self.detected_data["screens"]):
            is_active = False
            if item["type"] == "hdmi_monitor":
                if current_output_mode in ['hdmi_monitor', 'both'] and current_hdmi_idx == item.get("qt_index"):
                    is_active = True
            elif item["type"] == "usb_serial":
                if current_output_mode in ['usb_serial', 'both']:
                    active_port = getattr(self.gui.hardware, 'com_port', None)
                    if active_port and active_port == item.get("port"):
                        is_active = True
                    elif current_com_port == item.get("port") or (current_com_port == 'auto' and item.get("is_lcd")):
                        is_active = True

            card = QFrame()
            border_col = "#4edea3" if is_active else "#222a3d"
            card.setStyleSheet(f"""
                QFrame {{ background-color: #131b2e; border: 1px solid {border_col}; border-radius: 10px; }}
                QFrame:hover {{ border-color: #8083ff; background-color: #171f33; }}
            """)
            c_vbox = QVBoxLayout(card)
            c_vbox.setContentsMargins(14, 12, 14, 12)
            c_vbox.setSpacing(8)

            # Top Row: Icon Box + Title + Status Badge
            top_row = QHBoxLayout()
            icon_str = "🖥" if item["type"] == "hdmi_monitor" else "📟"
            ic_box = QLabel(icon_str)
            ic_box.setFixedSize(36, 36)
            ic_box.setAlignment(Qt.AlignCenter)
            ic_box.setStyleSheet("background: #060e20; border: 1px solid #222a3d; border-radius: 8px; font-size: 16px;")
            top_row.addWidget(ic_box)

            t_stack = QVBoxLayout()
            t_stack.setSpacing(1)
            lbl_title = QLabel(item['label'])
            lbl_title.setWordWrap(True)
            lbl_title.setStyleSheet("font-size: 12px; font-weight: 900; color: #dae2fd; border: none; background: transparent;")
            t_stack.addWidget(lbl_title)
            bus_sub = "HDMI / DisplayPort DirectX" if item["type"] == "hdmi_monitor" else f"USB Serial CDC ({item.get('port', 'COM')})"
            lbl_bus = QLabel(bus_sub)
            lbl_bus.setStyleSheet("font-size: 10px; color: #908fa0; font-family: 'Consolas', monospace; font-weight: 700; border: none; background: transparent;")
            t_stack.addWidget(lbl_bus)
            top_row.addLayout(t_stack, stretch=1)

            if is_active:
                lbl_badge = QLabel("● AKTİF YAYIN")
                lbl_badge.setStyleSheet("background: rgba(78, 222, 163, 0.16); color: #4edea3; font-weight: 900; padding: 4px 8px; border-radius: 5px; font-size: 10px; border: none;")
                top_row.addWidget(lbl_badge)
            else:
                lbl_badge = QLabel("● HAZIR")
                lbl_badge.setStyleSheet("background: #060e20; color: #7bd0ff; font-weight: 800; padding: 4px 8px; border-radius: 5px; font-size: 10px; border: none;")
                top_row.addWidget(lbl_badge)
            c_vbox.addLayout(top_row)

            # 2x2 Stitch Spec Grid (#060e20)
            spec_grid = QGridLayout()
            spec_grid.setSpacing(6)
            w_px, h_px = item.get('width', 320), item.get('height', 1480)
            orient_s = "DİKEY (PORTRAIT)" if h_px > w_px else "YATAY (LANDSCAPE)"
            proto_s = "RGB565 / SERIAL" if item["type"] == "usb_serial" else "24-BIT TRUECOLOR"
            rate_s = "115200 BAUD" if item["type"] == "usb_serial" else "60 HZ VSYNC"
            for sp_i, (sp_k, sp_v) in enumerate([
                ("ÇÖZÜNÜRLÜK", f"{w_px} × {h_px} PX"),
                ("YÖNELİM", orient_s),
                ("VERİ YOLU", proto_s),
                ("YENİLEME", rate_s),
            ]):
                sp_cell = QFrame()
                sp_cell.setStyleSheet("QFrame { background: #060e20; border: 1px solid #1e293b; border-radius: 6px; }")
                sp_lay = QVBoxLayout(sp_cell)
                sp_lay.setContentsMargins(8, 4, 8, 4)
                sp_lay.setSpacing(1)
                lk = QLabel(sp_k)
                lk.setStyleSheet("color: #908fa0; font-size: 8px; font-weight: 900; border: none; background: transparent;")
                lv = QLabel(sp_v)
                lv.setStyleSheet("color: #dae2fd; font-family: 'Consolas', monospace; font-size: 10px; font-weight: 800; border: none; background: transparent;")
                sp_lay.addWidget(lk)
                sp_lay.addWidget(lv)
                spec_grid.addWidget(sp_cell, sp_i // 2, sp_i % 2)
            c_vbox.addLayout(spec_grid)

            # Action Buttons Row
            btn_box = QHBoxLayout()
            btn_box.setSpacing(6)
            btn_select = QPushButton("🎯 Bu Ekrana Yansıt")
            btn_select.setStyleSheet("background: #8083ff; color: #07006c; font-weight: 900; padding: 6px 10px; border-radius: 6px; border: none; font-size: 11px;")
            btn_select.clicked.connect(lambda checked, it=item: self.select_target_screen(it, force_mode='single'))
            btn_box.addWidget(btn_select, stretch=1)

            btn_both = QPushButton("⚡ Çift Çıkış (USB + HDMI)")
            btn_both.setStyleSheet("background: #222a3d; color: #7bd0ff; border: 1px solid rgba(123, 208, 255, 0.35); font-weight: 800; padding: 6px 10px; border-radius: 6px; font-size: 11px;")
            btn_both.clicked.connect(lambda checked, it=item: self.select_target_screen(it, force_mode='both'))
            btn_box.addWidget(btn_both, stretch=1)

            c_vbox.addLayout(btn_box)
            grid.addWidget(card, idx_i // 2, idx_i % 2)

        self.detected_vbox.addWidget(grid_host)
        self.detected_vbox.addStretch()

    def rescan_screens(self):
        self.detected_data = detect_all_available_screens(self.gui.hardware)
        self.tabs.setTabText(0, f"🔍 Algılanan Ekranlar ({len(self.detected_data['screens'])})")
        self.populate_detected_list()
        QMessageBox.information(self, "Tarama Tamamlandı", f"{len(self.detected_data['screens'])} adet ekran/bağlantı noktası güncellendi!")

    def select_target_screen(self, item, force_mode=None):
        item_type = item["type"]
        if force_mode == 'both':
            out_mode = 'both'
        elif force_mode == 'single':
            out_mode = 'hdmi_monitor' if item_type == "hdmi_monitor" else 'usb_serial'
        else:
            out_mode = item.get("output_mode", item_type)

        self.gui.app_settings['output_mode'] = out_mode
        item['output_mode'] = out_mode

        if item_type == "hdmi_monitor":
            mon_idx = item.get("qt_index", 1)
            self.gui.app_settings['hdmi_screen_index'] = mon_idx
            self.gui.app_settings['selected_monitor_index'] = mon_idx
            self.gui.app_settings['selected_monitor_name'] = item.get('name', 'HDMI Monitör')
            target_w = item.get('width', 1920)
            target_h = item.get('height', 1080)
        else:
            port_name = item.get('port', 'auto')
            self.gui.app_settings['selected_com_port'] = port_name
            target_w = item.get('width', 320)
            target_h = item.get('height', 1480)

        self.gui.save_app_settings()

        curr_w = int(self.gui.theme_data.get('width', 320))
        curr_h = int(self.gui.theme_data.get('height', 1480))

        # When returning to USB LCD or Dual Mode (both), ensure theme is 320x1480 so USB screen is 100% native
        if (out_mode in ('usb_serial', 'both')) and (curr_w != 320 or curr_h != 1480):
            adapt_theme_elements_to_resolution(self.gui.theme_data, 320, 1480)
            if hasattr(self.gui, 'hardware'):
                self.gui.hardware.set_resolution(320, 1480)
            self.gui.save_theme_to_disk()
            if hasattr(self.gui, 'update_canvas_geometry'):
                self.gui.update_canvas_geometry()
            if hasattr(self.gui, 'refresh_elements_list'):
                self.gui.refresh_elements_list()
        elif out_mode == 'hdmi_monitor' and item.get('is_case_screen') and (curr_w != target_w or curr_h != target_h):
            # Only prompt resolution adaptation for dedicated physical case panels; standard 1080p/2K/4K monitors use Smart Widescreen Dashboard natively!
            ans = QMessageBox.question(
                self,
                "Kasa Ekranı Çözünürlük Uyarlama",
                f"Seçilen kasa ekranı çözünürlüğü ({target_w}×{target_h}), mevcut tema boyutundan ({curr_w}×{curr_h}) farklı.\n\n"
                f"Temadaki öğeler yeni ekrana göre yeniden boyutlandırılsın mı?\n"
                f"(Hayır derseniz mevcut düzen korunur ve Akıllı Geniş Ekran Dashboard modunda yansıtılır.)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if ans == QMessageBox.Yes:
                adapt_theme_elements_to_resolution(self.gui.theme_data, target_w, target_h)
                if hasattr(self.gui, 'hardware'):
                    self.gui.hardware.set_resolution(target_w, target_h)
                self.gui.save_theme_to_disk()
                if hasattr(self.gui, 'update_canvas_geometry'):
                    self.gui.update_canvas_geometry()
                if hasattr(self.gui, 'refresh_elements_list'):
                    self.gui.refresh_elements_list()

        # Sync Settings tab controls
        if hasattr(self, 'combo_output_mode'):
            idx_m = self.combo_output_mode.findData(out_mode)
            if idx_m >= 0:
                self.combo_output_mode.setCurrentIndex(idx_m)
        if hasattr(self, 'combo_hdmi_screen') and item_type == "hdmi_monitor":
            idx_s = self.combo_hdmi_screen.findData(item.get("qt_index", 1))
            if idx_s >= 0:
                self.combo_hdmi_screen.setCurrentIndex(idx_s)

        self.populate_detected_list()
        self.screen_selected_signal.emit(item)
        mode_label = "⚡ Çift Çıkış (USB Kasa Ekranı + HDMI Monitör)" if out_mode == 'both' else f"🎯 {item['label']}"
        QMessageBox.information(self, "Başarılı", f"Yansıtma hedefi '{mode_label}' olarak ayarlandı!")

    # ------------------ SEKME 2: PİYASA MODELLERİ KATALOĞU ------------------
    def build_catalog_tab(self):
        vbox = QVBoxLayout(self.tab_catalog)
        vbox.setContentsMargins(14, 14, 14, 14)
        vbox.setSpacing(10)

        # Filtreleme çubuğu
        filter_bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Marka veya Model Ara (Örn: Hyte, Jonsbo, Turing, 1920x480, Dikey)...")
        self.search_edit.textChanged.connect(self.filter_catalog)
        filter_bar.addWidget(self.search_edit)

        self.combo_category = QComboBox()
        self.combo_category.addItem("Tüm Kategoriler")
        self.combo_category.addItem("Entegre Kasa Ekranı")
        self.combo_category.addItem("Ultrawide Bar Ekran")
        self.combo_category.addItem("Sensör Paneli")
        self.combo_category.addItem("AIO Sıvı Soğutma LCD")
        self.combo_category.currentIndexChanged.connect(self.filter_catalog)
        filter_bar.addWidget(self.combo_category)

        vbox.addLayout(filter_bar)

        # Stitch Vendor Quick-Filter Pills
        vendor_bar = QHBoxLayout()
        vendor_bar.setSpacing(6)
        for v_lbl, v_q in [
            ("Tümü", ""),
            ("Hyte", "hyte"),
            ("Jonsbo", "jonsbo"),
            ("Lian Li", "lian li"),
            ("ASUS ROG", "asus"),
            ("Corsair", "corsair"),
            ("NZXT", "nzxt"),
            ("Turzx / Turing", "turing"),
        ]:
            v_btn = QPushButton(v_lbl)
            v_btn.setStyleSheet(
                "QPushButton { background: #131b2e; border: 1px solid #222a3d; color: #c0c1ff; border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 800; } "
                "QPushButton:hover { background: #8083ff; color: #07006c; }"
            )
            v_btn.clicked.connect(lambda _chk=False, q=v_q: self.search_edit.setText(q))
            vendor_bar.addWidget(v_btn)
        vendor_bar.addStretch()
        vbox.addLayout(vendor_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.catalog_container = QWidget()
        self.catalog_vbox = QVBoxLayout(self.catalog_container)
        self.catalog_vbox.setSpacing(10)
        self.catalog_vbox.setContentsMargins(0, 0, 0, 0)

        self.populate_catalog_list(CASE_SCREEN_PRESETS)

        scroll.setWidget(self.catalog_container)
        vbox.addWidget(scroll)

    def populate_catalog_list(self, preset_list):
        while self.catalog_vbox.count():
            item = self.catalog_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)

        for idx_i, p in enumerate(preset_list):
            card = QFrame()
            card.setStyleSheet("""
                QFrame { background-color: #131b2e; border: 1px solid #222a3d; border-radius: 10px; }
                QFrame:hover { border-color: #8083ff; background-color: #171f33; }
            """)
            c_vbox = QVBoxLayout(card)
            c_vbox.setContentsMargins(12, 10, 12, 10)
            c_vbox.setSpacing(6)

            top_r = QHBoxLayout()
            b_pill = QLabel(str(p.get('brand', 'PANEL')).upper())
            b_pill.setStyleSheet("background: rgba(128, 131, 255, 0.16); color: #c0c1ff; border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: 900; border: none;")
            top_r.addWidget(b_pill)
            top_r.addStretch()
            res_pill = QLabel(f"{p['width']}×{p['height']}")
            res_pill.setStyleSheet("background: #060e20; color: #7bd0ff; border: 1px solid #1e293b; border-radius: 4px; padding: 2px 6px; font-family: 'Consolas', monospace; font-size: 9px; font-weight: 800;")
            top_r.addWidget(res_pill)
            c_vbox.addLayout(top_r)

            title = QLabel(p['model'])
            title.setWordWrap(True)
            title.setStyleSheet("font-size: 12px; font-weight: 900; color: #dae2fd; border: none; background: transparent;")
            c_vbox.addWidget(title)

            spec_box = QFrame()
            spec_box.setStyleSheet("QFrame { background: #060e20; border: 1px solid #1e293b; border-radius: 6px; }")
            sb_lay = QVBoxLayout(spec_box)
            sb_lay.setContentsMargins(8, 5, 8, 5)
            sb_lay.setSpacing(2)
            lbl_det = QLabel(f"📐 {p['diagonal']}  •  {p['aspect_desc']}")
            lbl_det.setStyleSheet("font-size: 10px; color: #4edea3; font-family: 'Consolas', monospace; font-weight: 800; border: none; background: transparent;")
            lbl_cat = QLabel(f"🔌 {p['category']}")
            lbl_cat.setStyleSheet("font-size: 10px; color: #908fa0; font-weight: 700; border: none; background: transparent;")
            sb_lay.addWidget(lbl_det)
            sb_lay.addWidget(lbl_cat)
            c_vbox.addWidget(spec_box)

            desc = QLabel(p['desc'])
            desc.setStyleSheet("font-size: 10px; color: #908fa0; font-weight: 600; border: none; background: transparent;")
            desc.setWordWrap(True)
            c_vbox.addWidget(desc, stretch=1)

            btn_apply = QPushButton(f"📐 Temayı Bu Modele Uyarla ({p['width']}×{p['height']})")
            btn_apply.setStyleSheet("background: #8083ff; color: #07006c; font-weight: 900; padding: 7px 10px; border-radius: 6px; border: none; font-size: 10px;")
            btn_apply.clicked.connect(lambda checked, pr=p: self.apply_preset_to_theme(pr))
            c_vbox.addWidget(btn_apply)

            grid.addWidget(card, idx_i // 3, idx_i % 3)

        self.catalog_vbox.addWidget(grid_host)
        self.catalog_vbox.addStretch()

    def filter_catalog(self):
        query = self.search_edit.text().strip().lower()
        cat = self.combo_category.currentText()

        filtered = []
        for p in CASE_SCREEN_PRESETS:
            match_cat = (cat == "Tüm Kategoriler" or p['category'] == cat)
            match_txt = (
                not query or
                query in p['brand'].lower() or
                query in p['model'].lower() or
                query in p['desc'].lower() or
                query in f"{p['width']}x{p['height']}" or
                query in f"{p['height']}x{p['width']}"
            )
            if match_cat and match_txt:
                filtered.append(p)

        self.populate_catalog_list(filtered)

    def apply_preset_to_theme(self, preset):
        new_w = int(preset['width'])
        new_h = int(preset['height'])

        ans = QMessageBox.question(
            self,
            "Temayı Yeni Ekran Boyutuna Uyarla",
            f"Seçilen Kasa Ekranı: {preset['brand']} {preset['model']}\n"
            f"Yeni Çözünürlük: {new_w} × {new_h} px\n\n"
            f"Temadaki tüm öğeler otomatik olarak bu yeni ekrana göre ölçeklensin mi?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if ans != QMessageBox.Yes:
            return

        adapt_theme_elements_to_resolution(self.gui.theme_data, new_w, new_h)

        if hasattr(self.gui, 'hardware'):
            self.gui.hardware.set_resolution(new_w, new_h)
        self.gui.save_theme_to_disk()
        if hasattr(self.gui, 'update_canvas_geometry'):
            self.gui.update_canvas_geometry()
        if hasattr(self.gui, 'refresh_elements_list'):
            self.gui.refresh_elements_list()

        self.theme_adapted_signal.emit(self.gui.theme_data)
        QMessageBox.information(
            self,
            "Tema Güncellendi",
            f"Tema boyutu başarıyla '{preset['model']}' ({new_w}×{new_h}) çözünürlüğüne uyarlandı!"
        )

    # ------------------ SEKME 3: YANSITMA VE ÇIKIŞ AYARLARI ------------------
    def build_settings_tab(self):
        vbox = QVBoxLayout(self.tab_settings)
        vbox.setContentsMargins(20, 20, 20, 20)
        vbox.setSpacing(14)

        vbox.addWidget(QLabel("⚙️ Çoklu Ekran ve Yayım Modu Seçimi:"))

        mode_box = QHBoxLayout()
        mode_box.addWidget(QLabel("Aktif Çıkış Yöntemi:"))
        self.combo_output_mode = QComboBox()
        self.combo_output_mode.addItem("📟 Yalnızca USB LCD Donanımı (COM Portu)", "usb_serial")
        self.combo_output_mode.addItem("🖥️ Yalnızca HDMI/Windows İkincil Ekranı (Kasa Monitörü)", "hdmi_monitor")
        self.combo_output_mode.addItem("⚡ Çift Çıkış (Hem USB Ekranı Hem HDMI Kasa Ekranı)", "both")

        curr_mode = self.gui.app_settings.get('output_mode', 'usb_serial')
        for idx in range(self.combo_output_mode.count()):
            if self.combo_output_mode.itemData(idx) == curr_mode:
                self.combo_output_mode.setCurrentIndex(idx)
                break
        mode_box.addWidget(self.combo_output_mode)
        vbox.addLayout(mode_box)

        # HDMI Ekran İndeksi
        hdmi_box = QHBoxLayout()
        hdmi_box.addWidget(QLabel("HDMI Hedef Monitör:"))
        self.combo_hdmi_screen = QComboBox()
        app = QApplication.instance()
        if app:
            for i, s in enumerate(app.screens()):
                geo = s.geometry()
                lbl = f"Ekran {i + 1}: {s.name()} ({geo.width()}×{geo.height()})"
                if s == app.primaryScreen():
                    lbl += " [Ana Monitör]"
                self.combo_hdmi_screen.addItem(lbl, i)
        curr_hdmi = self.gui.app_settings.get('selected_monitor_index', self.gui.app_settings.get('hdmi_screen_index', 1))
        for idx in range(self.combo_hdmi_screen.count()):
            if self.combo_hdmi_screen.itemData(idx) == curr_hdmi:
                self.combo_hdmi_screen.setCurrentIndex(idx)
                break
        hdmi_box.addWidget(self.combo_hdmi_screen)
        vbox.addLayout(hdmi_box)

        # HDMI Görünüm Modu
        view_box = QHBoxLayout()
        view_box.addWidget(QLabel("HDMI Görünüm Modu:"))
        self.combo_hdmi_view = QComboBox()
        for m_key, m_lbl in HDMICompanionDisplayWindow.VIEW_MODES:
            self.combo_hdmi_view.addItem(m_lbl, m_key)
        curr_view = self.gui.app_settings.get('hdmi_view_mode', 'ambient_dashboard')
        for idx in range(self.combo_hdmi_view.count()):
            if self.combo_hdmi_view.itemData(idx) == curr_view:
                self.combo_hdmi_view.setCurrentIndex(idx)
                break
        view_box.addWidget(self.combo_hdmi_view)
        vbox.addLayout(view_box)

        # HDMI Yönlendirme (Döndürme)
        rot_box = QHBoxLayout()
        rot_box.addWidget(QLabel("HDMI Ekran Yönü:"))
        self.combo_hdmi_rot = QComboBox()
        self.combo_hdmi_rot.addItem("0° (Normal Düz Görünüm - Önerilen)", 0)
        self.combo_hdmi_rot.addItem("90° (Sağa Döndür)", 90)
        self.combo_hdmi_rot.addItem("180° (Ters Çevir)", 180)
        self.combo_hdmi_rot.addItem("270° (Sola Döndür)", 270)
        curr_rot = int(self.gui.app_settings.get('hdmi_rotation', 0))
        for idx in range(self.combo_hdmi_rot.count()):
            if self.combo_hdmi_rot.itemData(idx) == curr_rot:
                self.combo_hdmi_rot.setCurrentIndex(idx)
                break
        rot_box.addWidget(self.combo_hdmi_rot)
        vbox.addLayout(rot_box)

        self.chk_auto_prompt = QCheckBox("🔄 Farklı bir bilgisayarda çalıştırıldığında yeni kasa ekranını otomatik algıla ve sor")
        self.chk_auto_prompt.setChecked(self.gui.app_settings.get('auto_detect_screens', True))
        vbox.addWidget(self.chk_auto_prompt)

        tip_lbl = QLabel("💡 İpucu: HDMI yansıtma açıkken ekran üzerinde Sağ Tıklayarak veya 'M' / 'R' / 'ESC' tuşlarıyla görünümü anında değiştirebilirsiniz.")
        tip_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 500;")
        tip_lbl.setWordWrap(True)
        vbox.addWidget(tip_lbl)

        vbox.addStretch()

        btn_save_settings = QPushButton("💾 Tercihleri Kaydet ve Uygula")
        btn_save_settings.setStyleSheet("background: #10b981; color: white; font-weight: 700; padding: 9px 18px;")
        btn_save_settings.clicked.connect(self.save_settings_tab)
        vbox.addWidget(btn_save_settings, alignment=Qt.AlignRight)

    def save_settings_tab(self):
        out_mode = self.combo_output_mode.currentData()
        hdmi_idx = self.combo_hdmi_screen.currentData()
        self.gui.app_settings['output_mode'] = out_mode
        self.gui.app_settings['hdmi_screen_index'] = hdmi_idx
        self.gui.app_settings['selected_monitor_index'] = hdmi_idx
        self.gui.app_settings['hdmi_view_mode'] = self.combo_hdmi_view.currentData()
        self.gui.app_settings['hdmi_rotation'] = self.combo_hdmi_rot.currentData()
        self.gui.app_settings['auto_detect_screens'] = self.chk_auto_prompt.isChecked()

        app = QApplication.instance()
        if app and 0 <= hdmi_idx < len(app.screens()):
            self.gui.app_settings['selected_monitor_name'] = app.screens()[hdmi_idx].name()

        self.gui.save_app_settings()
        self.populate_detected_list()

        # Live apply to running GUI & stream
        if hasattr(self.gui, 'is_streaming') and self.gui.is_streaming:
            if out_mode in ('usb_serial', 'both'):
                target_port = self.gui.app_settings.get('selected_com_port', 'auto')
                self.gui.hardware.auto_connect(target_port=target_port)
            if out_mode in ('hdmi_monitor', 'both'):
                if hasattr(self.gui, 'hdmi_companion_window'):
                    self.gui.hdmi_companion_window.show_on_monitor(monitor_index=hdmi_idx)
            else:
                if hasattr(self.gui, 'hdmi_companion_window'):
                    self.gui.hdmi_companion_window.hide()

        if hasattr(self.gui, 'update_stream_status_ui'):
            self.gui.update_stream_status_ui()

        QMessageBox.information(self, "Kaydedildi", "Yansıtma tercihleri kaydedildi ve aktif akışa uygulandı!")
