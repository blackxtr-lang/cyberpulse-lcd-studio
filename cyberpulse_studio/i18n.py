# -*- coding: utf-8 -*-
"""
🌐 CyberPulse Studio — Bilingual Localization Engine (🇹🇷 Türkçe / 🇬🇧 English)
Provides instant, lossless UI translation across the main studio window and all dialogs.
"""
import re
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QCheckBox, QGroupBox,
    QLineEdit, QComboBox, QTabWidget, QListWidget
)

# Exact string mapping (Turkish -> English)
TR_TO_EN_EXACT = {
    # Left Navigation Sidebar (nav_rail)
    "⊞  Tuval Stüdyosu": "⊞  Canvas Studio",
    "🎨  Tema Şablonları": "🎨  Theme Templates",
    "🖥  Ekran Kataloğu": "🖥  Screen Catalog",
    "↻  Oto Döngü Havuzu": "↻  Auto-Rotate Pool",
    "🎮  Oyun Profilleri": "🎮  Game Profiles",
    "💾  Şablona Kaydet": "💾  Save as Template",
    "✂  Medya Kırpıcı": "✂  Media Cropper",
    "BELLEK YÜKÜ": "MEMORY LOAD",
    "☕  Bana Bir Kahve Ismarla": "☕  Buy Me a Coffee",
    "Geliştiriciye destek olmak için GitHub Sponsors / Kahve Ismarla sayfasını açar":
        "Open GitHub Sponsors / Buy Me a Coffee page to support the developer",
    "⚙  Sistem Ayarları": "⚙  System Settings",
    "🌐  Dil: Türkçe (TR)": "🌐  Language: English (EN)",

    # Tooltips in Left Sidebar & Top Bar
    "Kayıtlı temaları çözünürlüğe göre gruplanmış olarak önizleyin, yükleyin, silin veya dışa/içe aktarın":
        "Preview, load, delete, or import/export saved themes grouped by resolution",
    "Bağlı USB kasa ekranlarını ve HDMI monitörleri algılayın veya katalogdan model seçin":
        "Detect connected USB case screens and HDMI monitors or select a model from the catalog",
    "Bu ekran (ve diğer ekranlar) için hangi temaların hangi sürede otomatik değişeceğini seçin":
        "Select which themes rotate automatically and at what interval for each screen",
    "Sistemde yüklü oyunları istediğiniz temalara bağlayın — oyun açıldığında otomatik o temaya geçsin":
        "Bind installed games to specific themes — automatically switch when the game launches",
    "Mevcut ekranın temasını kendi çözünürlüğünde tek dosya (.cptheme) olarak kaydeder":
        "Save the current screen's theme at its native resolution as a single (.cptheme) file",
    "Arka plan medyasını ekran oranına göre kırpın veya tam sığdırın":
        "Crop or fit background media to the screen aspect ratio",
    "Mevcut ekrandaki tüm ögeleri ve düzeni yalnızca bu ekranla aynı çözünürlükteki kayıtlı temalarınıza aktarır":
        "Apply all elements and layout on this screen to saved themes of the same resolution",

    # Top Stream & Telemetry Bar
    "HEDEF:": "TARGET:",
    "📟 Kasa LCD (USB)": "📟 Case LCD (USB)",
    "🖥 Monitör (HDMI)": "🖥 Monitor (HDMI)",
    "⚡ Çift Çıkış (USB+HDMI)": "⚡ Dual Output (USB+HDMI)",
    "PORT:": "PORT:",
    "⚡ Otomatik Algıla": "⚡ Auto Detect",
    "Kullanılabilir COM portlarını yeniden tara": "Rescan available COM ports",
    "● HAZIR": "● READY",
    "● HAZIR [BEKLEMEDE]": "● READY [STANDBY]",
    "🔴 Bağlı Değil": "🔴 Disconnected",
    "🚀 CANLI YANSIT": "🚀 GO LIVE",
    "🚀 CANLI YANSIT (USB)": "🚀 GO LIVE (USB)",
    "🚀 CANLI YANSIT (HDMI)": "🚀 GO LIVE (HDMI)",
    "🚀 CANLI YANSIT (ÇİFT)": "🚀 GO LIVE (DUAL)",
    "🚀 CANLI YANSIT (ÇİFT EKRAN)": "🚀 GO LIVE (DUAL)",
    "⏹ YAYINI DURDUR": "⏹ STOP STREAM",
    "⏹ YANSITMAYI DURDUR": "⏹ STOP STREAM",
    "● BAĞLI [60 FPS]": "● LIVE [60 FPS]",
    "📐 320×1480 (Dikey USB LCD Şerit)": "📐 320×1480 (Portrait USB LCD Strip)",
    "📐 1480×320 (Yatay USB LCD Şerit)": "📐 1480×320 (Landscape USB LCD Strip)",
    "📐 1920×1080 (Full HD Yatay Monitör)": "📐 1920×1080 (Full HD Landscape)",
    "📐 1080×1920 (Full HD Dikey Monitör)": "📐 1080×1920 (Full HD Portrait)",
    "📐 2560×1440 (2K QHD Yatay)": "📐 2560×1440 (2K QHD Landscape)",
    "📐 1440×2560 (2K QHD Dikey)": "📐 1440×2560 (2K QHD Portrait)",
    "📐 3840×2160 (4K UHD Yatay)": "📐 3840×2160 (4K UHD Landscape)",
    "📐 1920×480 (8.8\" Yatay Kasa Şerit)": "📐 1920×480 (8.8\" Landscape Strip)",
    "📐 480×1920 (8.8\" Dikey Kasa Şerit)": "📐 480×1920 (8.8\" Portrait Strip)",
    "📐 1280×400 (7.9\" Yatay Kasa Şerit)": "📐 1280×400 (7.9\" Landscape Strip)",
    "📐 1024×600 (7\" Mini HDMI Ekran)": "📐 1024×600 (7\" Mini HDMI Display)",
    "📐 800×480 (5\" Mini Kasa Ekranı)": "📐 800×480 (5\" Mini Case Display)",
    "📐 480×320 (3.5\" IPS USB Ekran)": "📐 480×320 (3.5\" IPS USB Display)",
    "⚙️ Özel Çözünürlük Gir...": "⚙️ Custom Resolution...",

    # Multi-Screen Bar
    "🖥 EKRANLAR:": "🖥 SCREENS:",
    "＋ Ekran Ekle": "＋ Add Screen",
    "Yeni bir ekran veya Kasa Ekranı Kataloğundan özel bir ekran modeli için ayrı tema oluşturucu açar":
        "Open a separate theme workspace for a new screen or catalog model",
    "Seçili özel ekran yuvasını kaldır": "Remove selected custom screen slot",
    "Yayına Dahil Et": "Include in Stream",
    "Bu ekranı çoklu ekran canlı yansıtmasına dahil eder": "Include this screen in multi-display live streaming",
    "📐 Ekran Çözünürlüğü:": "📐 Resolution:",
    "📐 Çözünürlük:": "📐 Resolution:",
    "🎨 Bu Ekranın Teması:": "🎨 Screen Theme:",
    "🎨 Tema:": "🎨 Theme:",
    "Oto Döngü": "Auto Rotate",
    "Bu ekranda seçili temaların otomatik olarak sırayla/rastgele değişmesini açar/kapatır":
        "Toggle automatic sequential/random rotation of selected themes on this screen",
    "📋 Başka Ekrandan Kopyala": "📋 Copy from Screen",
    "📋 Kopyala": "📋 Copy",
    "Başka bir ekranın özel temasını bu ekrana kopyalar ve boyuta uyarlar":
        "Copy another screen's theme to this screen and adapt to its resolution",

    # Left Column (Media & Sensors)
    "ARKA PLAN MEDYASI": "BACKGROUND MEDIA",
    "🖼 Medya Seç": "🖼 Select Media",
    "Arka plan resmi, GIF veya MP4 videosu seçin": "Select background image, GIF, or MP4 video",
    "✂ Kırp / Sığdır": "✂ Crop / Fit",
    "🎞 Varsayılan Koyu Arka Plan": "🎞 Default Dark Background",
    "YENİLEME HIZI": "REFRESH RATE",
    "EKRAN YÖNÜ": "ORIENTATION",
    "180° (Düz)": "180° (Inverted)",
    "0° (Normal)": "0° (Normal)",
    "90° (Yan)": "90° (Landscape)",
    "270° (Ters)": "270° (Landscape Inv.)",
    "SENSÖR VE BİLEŞENLER": "SENSORS & WIDGETS",
    "🔍 Sensör veya bileşen ara...": "🔍 Search sensors or widgets...",
    "➕ SEÇİLİ ÖGEYİ TUVALE EKLE": "➕ ADD SELECTED WIDGET TO CANVAS",

    # Sensor Card Titles & Subtitles
    "Canlı Çizgi Grafik (Sparkline)": "Live Line Graph (Sparkline)",
    "60s Geçmiş": "60s History",
    "Özel Resim / Logo / İkon Katmanı": "Custom Image / Logo / Icon Layer",
    "FPS Göstergesi": "FPS Counter",
    "CPU Sıcaklığı": "CPU Temperature",
    "CPU Kullanımı (%)": "CPU Usage (%)",
    "Tüm Çekirdekler": "All Cores",
    "CPU Frekansı (MHz)": "CPU Clock (MHz)",
    "Boost Saati": "Boost Clock",
    "CPU Fan Hızı (RPM)": "CPU Fan Speed (RPM)",
    "PWM Anakart": "PWM Motherboard",
    "GPU Sıcaklığı": "GPU Temperature",
    "GPU Çekirdek": "GPU Core",
    "GPU Kullanımı (%)": "GPU Usage (%)",
    "3D Motor Yükü": "3D Engine Load",
    "GPU Fan Hızı (%)": "GPU Fan Speed (%)",
    "Soğutucu Fan": "Cooler Fan",
    "RAM Kullanımı (GB)": "RAM Usage (GB)",
    "RAM Kullanımı (%)": "RAM Usage (%)",
    "Kalan / Boş RAM (GB)": "Free / Available RAM (GB)",
    "Kalan RAM": "Free RAM",
    "Boş RAM": "Free RAM",
    "💾 Kalan / Boş RAM (GB)": "💾 Free / Available RAM (GB)",
    "💾 RAM Gösterimi:": "💾 RAM Display:",
    "Kullanılan RAM (GB) — Çubuk: Kullanılan %": "Used RAM (GB) — Bar: Used %",
    "Kullanılan RAM (%) — Çubuk: Kullanılan %": "Used RAM (%) — Bar: Used %",
    "Kullanılan RAM (GB + %) — Çubuk: Kullanılan %": "Used RAM (GB + %) — Bar: Used %",
    "Kalan / Boş RAM (GB) — Çubuk: Kalan %": "Free RAM (GB) — Bar: Free %",
    "Kalan / Boş RAM (%) — Çubuk: Kalan %": "Free RAM (%) — Bar: Free %",
    "Kalan / Boş RAM (GB + %) — Çubuk: Kalan %": "Free RAM (GB + %) — Bar: Free %",
    "🔄 Her Açılışta Güncellemeleri Otomatik Denetle ve Yükle": "🔄 Automatically Check & Install Updates on Startup",
    "🔄 Güncelleme Denetle": "🔄 Check for Updates",
    "Sistem Belleği": "System Memory",
    "Disk Okuma/Yazma (MB/s)": "Disk Read/Write (MB/s)",
    "Sistem Açık Kalma Süresi": "System Uptime",
    "Çalışma Süresi": "Uptime",
    "İndirme Hızı (Download)": "Download Speed",
    "Yükleme Hızı (Upload)": "Upload Speed",
    "Canlı Ağ Akışı": "Live Network Traffic",
    "İnternet Ping (ms)": "Internet Ping (ms)",
    "Gecikme (ms)": "Latency (ms)",
    "Dijital Saat": "Digital Clock",
    "Sistem Saati": "System Time",
    "Tarih (GG.AA.YYYY)": "Date (DD.MM.YYYY)",
    "Takvim": "Calendar",
    "Türkçe Gün & Tarih": "Localized Day & Date",
    "Yerel Takvim": "Local Calendar",
    "Yatay İlerleme Çubuğu": "Horizontal Progress Bar",
    "Dikey İlerleme Çubuğu": "Vertical Progress Bar",
    "Dikey Bar": "Vertical Bar",
    "Dairesel Gösterge": "Circular Gauge",
    "Radial Kadran": "Radial Dial",
    "Canlı Döner Fan Göstergesi": "Animated Spinning Fan",
    "60 FPS Animasyon": "60 FPS Animation",
    "Kayan LED Metin (Marquee)": "Scrolling LED Text (Marquee)",
    "Granular Kayan Yazı": "Custom Scrolling Ticker",
    "YouTube Music / Medya Kartı": "YouTube Music / Media Card",
    "SMTC Medya Bilgisi": "SMTC Now Playing",
    "Canlı Hava Durumu Kartı": "Live Weather Card",
    "Otomatik Konum": "Auto Location",
    "Canlı Ping Monitörü": "Live Ping Monitor",
    "Ağ Grafiği": "Network Graph",
    "Akıllı Etkinlik Geri Sayım": "Event Countdown Timer",
    "Hedef Tarih Sayacı": "Target Date Timer",
    "Özel Düz Metin": "Custom Static Text",
    "Serbest Başlık": "Free Text Label",
    "Arka Plan Kutusu / Çizgisi": "Background Box / Divider",
    "HUD Çerçeve / Panel": "HUD Frame / Panel",

    # Center Stage Toolbar
    "↶ Geri Al": "↶ Undo",
    "Son işlemi geri al (Ctrl+Z)": "Undo last action (Ctrl+Z)",
    "↷ İleri Al": "↷ Redo",
    "Geri alınan işlemi yinele (Ctrl+Y)": "Redo last action (Ctrl+Y)",
    "⊞ MIKNATIS [AÇIK]": "⊞ SNAP [ON]",
    "⊞ Mıknatıs": "⊞ Snap",

    # Right Column (Layers & Inspector)
    "HİZALA": "ALIGN",
    "⬅ Sol": "⬅ Left",
    "↔ Orta": "↔ Center",
    "➡ Sağ": "➡ Right",
    "↕ Dikey": "↕ Middle",
    "🟰 Dağıt": "🟰 Distribute",
    "Sol kenara hizala": "Align left edge",
    "Yatay ortala": "Align horizontal center",
    "Sağ kenara hizala": "Align right edge",
    "Dikey ortala": "Align vertical center",
    "Dikey boşlukları eşit dağıt": "Distribute vertical spacing evenly",
    "Katmanı bir üste taşı (Öne getir)": "Bring layer forward",
    "Katmanı bir alta taşı (Arkaya gönder)": "Send layer backward",
    "Seçili ögeyi çoğalt (Ctrl+D)": "Duplicate selected element (Ctrl+D)",
    "Seçili ögeyi kilitle / kilidi aç": "Lock / unlock selected element",
    "Seçili ögeyi gizle / göster": "Hide / show selected element",
    "Seçili öge(ler)i sil (Delete)": "Delete selected element(s) (Delete)",
    "SEÇİLİ ÖGE AYARLARI": "SELECTED WIDGET SETTINGS",
    "ℹ️ Düzenlemek için tuvalden veya katman listesinden bir öge seçin":
        "ℹ️ Select a widget from the canvas or layer list to edit its properties",
    "Bağlı Sensör:": "Bound Sensor:",
    "🖼️ Özel Görsel / Logo Seç (PNG / WebP / JPG)": "🖼️ Select Custom Image / Logo (PNG / WebP / JPG)",
    "Etiket / Başlık:": "Label / Title:",
    "Görsel Adı:": "Image Name:",
    "Yük:": "H:",
    "G:": "W:",
    "Font Ailesi:": "Font Family:",
    "Kalın (Bold)": "Bold",
    "İtalik": "Italic",
    "Etiket:": "Label:",
    "Değer:": "Value:",
    "Hiza:": "Align:",
    "Sol (left)": "Left",
    "Orta (center)": "Center",
    "Sağ (right)": "Right",
    "🔲 Çerçeve": "🔲 Border",
    "✨ Neon Glow": "✨ Neon Glow",
    "Köşe:": "Radius:",
    "Köşe Yuvarlatma:": "Corner Radius:",
    "🎨 Yazı Renk": "🎨 Text Color",
    "🎨 Yazı": "🎨 Text",
    "🎨 Değer Renk": "🎨 Value Color",
    "🎨 Değer": "🎨 Value",
    "🎨 Çizgi/Grafik": "🎨 Line/Graph",
    "🎨 Grafik": "🎨 Graph",
    "🎨 Dinamik Renk": "🎨 Dynamic Color",
    "⚙️ Renk Eşiklerini Ayarla": "⚙️ Threshold Settings",
    "⚙️ Renk Eşikleri": "⚙️ Thresholds",
    "✨ Efekt:": "✨ Effect:",
    "Sabit (Kapalı)": "None (Static)",
    "💨 Nefes Alma (Pulse)": "💨 Breathing (Pulse)",
    "🌈 RGB Rainbow Spektrum": "🌈 RGB Rainbow Spectrum",
    "⚡ Yanıp Sönme (Flash)": "⚡ Flashing (Alert)",
    "✨ Neon Parıltı": "✨ Neon Shimmer",
    "Hız:": "Speed:",
    "🗓️ Hedef Tarih:": "🗓️ Target Date:",
    "📍 Konum/İlçe:": "📍 Location/City:",
    "Örn: Çorlu, Kadıköy": "e.g. London, New York, Istanbul",
    "🎯 Otomatik": "🎯 Auto",
    "📜 Kayan Yazı İçeriklerini Seç (Granular Marquee)": "📜 Customize Scrolling Ticker Items",
    "📜 Kayan Yazı İçeriklerini Seç": "📜 Customize Ticker Items",
    "Arka Plan:": "Background:",
    "🎨 Renk": "🎨 Color",
    "Opaklık (%):": "Opacity (%):",
    "❌ Seçimi Kaldır": "❌ Deselect Widget",

    # Dialogs: Theme Preset Manager
    "🎨 CyberPulse — Kayıtlı Temalarım & Şablon Yöneticisi": "🎨 CyberPulse — Saved Themes & Template Manager",
    "🎨 Kayıtlı Temalarım ve Şablon Yöneticisi": "🎨 Saved Themes & Template Manager",
    "Temalar ekran çözünürlüğüne göre otomatik gruplanır — tek tıkla önizleyin, yükleyin veya paylaşın.":
        "Themes are automatically grouped by screen resolution — preview, load, or share with one click.",
    "📥 Tema İçe Aktar": "📥 Import Theme",
    "📤 Seçiliyi Dışa Aktar": "📤 Export Selected",
    "🔍 Tema adı veya çözünürlük ara (Örn: Kale, 1920x1080, 320x1480)...":
        "🔍 Search theme name or resolution (e.g. Castle, 1920x1080, 320x1480)...",
    "🌐 Tüm Çözünürlükler": "🌐 All Resolutions",
    "👁️ SEÇİLİ TEMA ÖNİZLEMESİ": "👁️ SELECTED THEME PREVIEW",
    "Seçili temayı aktif ekran çalışma alanına yükle": "Load selected theme into active screen workspace",
    "✅ Seçili Temayı Ekrana Yükle": "✅ Load Selected Theme",
    "✏️ Yeniden Adlandır": "✏️ Rename",
    "🗑️ Sil": "🗑️ Delete",
    "YÜKLE": "LOAD",
    "AKTİF YÜKLÜ": "ACTIVE",
    ".cptheme Tek Dosya Paketi": ".cptheme Single-File Package",
    "JSON Tema Şablonu": "JSON Theme Template",
    "Kapat": "Close",
    "❌ Kapat": "❌ Close",
    "İptal": "Cancel",

    # Dialogs: Screen Auto-Rotate Pool
    "🎠 Ekran Bazlı Otomatik Tema Döngüsü (Seçmeli Havuz)": "🎠 Per-Screen Automatic Theme Rotation Pool",
    "🎠 Ekran Bazlı Otomatik Tema Döngüsü": "🎠 Per-Screen Automatic Theme Rotation",
    "Her ekran için hangi temaların, hangi sırayla ve sürede değişeceğini çözünürlük gruplarıyla belirleyin.":
        "Configure which themes rotate, in what order and interval, grouped by resolution for each screen.",
    "1. HEDEF EKRAN SEÇİMİ": "1. TARGET SCREEN SELECTION",
    "🖥 Düzenlenen Ekran:": "🖥 Target Screen:",
    "⚡ Bu Ekranda Otomatik Tema Döngüsünü Etkinleştir": "⚡ Enable Automatic Theme Rotation on This Screen",
    "2. DEĞİŞİM SÜRESİ VE SIRALAMA": "2. INTERVAL & ORDER",
    "⏱️ Değişim Süresi:": "⏱️ Rotation Interval:",
    "🔀 Sıralama:": "🔀 Order:",
    "Sırayla (Liste Sırası)": "Sequential (List Order)",
    "Rastgele (Shuffle)": "Random (Shuffle)",
    "3. DÖNGÜYE DAHİL EDİLECEK TEMALAR": "3. THEMES INCLUDED IN ROTATION",
    "🔍 Döngü havuzunda tema ara...": "🔍 Search themes in rotation pool...",
    "☑ Görünenleri Seç": "☑ Select Visible",
    "☐ Seçimi Temizle": "☐ Clear Selection",
    "📐 Sadece Bu Ekranın Çözünürlüğündekileri Seç": "📐 Select Matching Resolution Only",
    "💾 Tüm Ekranlara Aynı Havuzu Uygula": "💾 Apply Pool to All Screens",
    "✅ Kaydet ve Uygula": "✅ Save & Apply",

    # Dialogs: Case Screen Catalog
    "🖥️ PC Kasa Ekranı ve Cihaz Yöneticisi": "🖥️ PC Case Screen & Display Manager",
    "Bilgisayardaki kasa ekranlarını otomatik algılayın veya hazır piyasa modellerine uyarlayın.":
        "Automatically detect connected case screens or adapt to commercial display models.",
    "🔄 Ekranları Yeniden Tara": "🔄 Rescan Displays",
    "⚙️ Yansıtma ve Çıkış Ayarları": "⚙️ Streaming & Output Settings",

    # Dialogs: Game Profile Manager
    "🎮 Oyun Profili ve Otomatik Tema Bağlayıcı": "🎮 Game Profiles & Automatic Theme Switcher",
    "Sisteminizde yüklü oyunları istediğiniz temaya bağlayın — oyun açıldığında kasa ekranı otomatik olarak o temaya geçsin, kapandığında masaüstü temanıza dönsün.":
        "Bind installed games to your favorite themes — automatically switch when a game launches and restore your desktop theme on exit.",
    "⚡ OTOMATİK OYUN ALGILAMA VE GEÇİŞ AYARLARI": "⚡ AUTOMATIC GAME DETECTION & SWITCHING SETTINGS",
    "🎮 Oyun Açıldığında Otomatik Tema Değişimini Etkinleştir": "🎮 Enable Automatic Theme Switching When Game Launches",
    "🔒 Alt+Tab Yapıldığında da Oyun Kapanana Kadar Oyun Temasını Koru": "🔒 Keep Game Theme Active on Alt+Tab Until Game Exits",
    "🎯 Özel Tema Bağlanmamış Diğer 3D Oyunlar İçin Varsayılan Tema:": "🎯 Default Theme for Other Unbound 3D Games:",
    "🚫 Yok (Yalnızca Özel Bağlanan Oyunlarda Değiştir)": "🚫 None (Switch Only for Explicitly Bound Games)",
    "🔍 Yüklü oyunlarda veya .exe adlarında ara (Örn: Counter-Strike, Valorant, Cyberpunk, cs2.exe)...":
        "🔍 Search installed games or .exe names (e.g. Counter-Strike, Valorant, Cyberpunk, cs2.exe)...",
    "Tümü": "All",
    "🔗 Bağlı": "🔗 Bound",
    "⚪ Bağsız": "⚪ Unbound",
    "🔄 Yüklü Oyunları Tara": "🔄 Rescan Installed Games",
    "📂 Oyun (.exe) Seç": "📂 Select Game (.exe)",
    "⚡ Açık Uygulamalardan Ekle": "⚡ Add from Running Apps",
    "👁 BAĞLI TEMA ÖNİZLEMESİ": "👁 BOUND THEME PREVIEW",
    "Önizlemek için bir oyuna\ntema seçin": "Select a theme for a game\nto preview",
    "Henüz oyun seçilmedi": "No game selected yet",
    "💡 İpucu: İstediğiniz oyunun karşısındaki açılır menüden bir tema seçtiğinizde otomatik olarak eşleştirilir.":
        "💡 Tip: Selecting a theme from the dropdown next to any game automatically binds it.",
    "✅ Oyun Profillerini Kaydet ve Uygula": "✅ Save & Apply Game Profiles",

    # Dialogs: App Settings
    "⚙️ CyberPulse — Sistem Ayarları & Kısayollar": "⚙️ CyberPulse — System Settings & Shortcuts",
    "⚙️ Sistem Ayarları ve Donanım Yapılandırması": "⚙️ System Settings & Hardware Configuration",
    "Uygulama başlangıç davranışı, bağlantı hızı, sensör kaynakları ve global kısayolları yönetin.":
        "Configure startup behavior, serial baud rate, sensor sources, and global hotkeys.",
    "🚀 SİSTEM SERVİSİ & BAŞLANGIÇ DAVRANIŞI": "🚀 SYSTEM SERVICE & STARTUP BEHAVIOR",
    "🚀 Windows Açılışında Otomatik Çalıştır": "🚀 Launch Automatically on Windows Startup",
    "📌 Sistem Tepsisinde (System Tray) Çalıştır": "📌 Run in System Tray",
    "🔽 Başlangıçta Sistem Tepsisine Küçültülmüş Başla": "🔽 Start Minimized in System Tray",
    "⚡ Açılışta Kasa Ekranına Otomatik Yansıtmaya Başla": "⚡ Automatically Start Streaming on Launch",
    "🌐 Uygulama Dili / Language:": "🌐 App Language / Dil:",
    "🔌 DONANIM VERİ YOLU & COM PORT BAĞLANTISI": "🔌 HARDWARE BUS & COM PORT CONNECTION",
    "COM Portu:": "COM Port:",
    "⚡ Otomatik Algıla (Önerilen)": "⚡ Auto Detect (Recommended)",
    "🔌 Portu Test Et": "🔌 Test Port",
    "🌡️ TERMAL KALİBRASYON & HAVA DURUMU KONUMU": "🌡️ THERMAL CALIBRATION & WEATHER LOCATION",
    "🔥 Kritik Uyarı Sıcaklık Eşiği (°C):": "🔥 Critical Thermal Alert Limit (°C):",
    "🎯 CPU Sıcaklık Kalibrasyon Ofseti (°C):": "🎯 CPU Temp Calibration Offset (°C):",
    "📍 Hava Durumu İl/İlçe:": "📍 Weather City/District:",
    "Otomatik GPS veya şehir adı (Örn: Çorlu)": "Auto GPS or city name (e.g. London, New York)",
    "🎯 Oto GPS": "🎯 Auto GPS",
    "⌨ GLOBAL KISAYOL TUŞLARI (OYUN İÇİ & ARKA PLAN)": "⌨ GLOBAL HOTKEYS (IN-GAME & BACKGROUND)",
    "⌨️ Global Kısayol Tuşlarını Etkinleştir (Oyunlarda & Arka Planda Çalışır)":
        "⌨️ Enable Global Hotkeys (Works In-Game & in Background)",
    "⏭️ Sonraki Tema:": "⏭️ Next Theme:",
    "⏮️ Önceki Tema:": "⏮️ Previous Theme:",
    "🚀 Yansıtma Aç/Kapat:": "🚀 Toggle Live Stream:",
    "🎲 Rastgele Tema Seç:": "🎲 Random Theme:",
    "⚡ Stüdyo Göster / Gizle:": "⚡ Show / Hide Studio:",
    "🔄 Kısayolları Varsayılana Sıfırla": "🔄 Reset Hotkeys to Default",
    "🎠 OTOMATİK TEMA DÖNGÜSÜ & OYUN PROFİLLERİ": "🎠 AUTOMATIC THEME ROTATION & GAME PROFILES",
    "🎠 Kayıtlı Temaları Otomatik Değiştir (Slayt Döngüsü)": "🎠 Automatically Rotate Saved Themes (Carousel)",
    "⏱️ Süre:": "⏱️ Interval:",
    "⏱️ Saniye": "⏱️ Seconds",
    "⏱️ Dakika": "⏱️ Minutes",
    "⏱️ Saat": "⏱️ Hours",
    "📋 Sırayla": "📋 Sequential",
    "🎲 Karışık": "🎲 Random",
    "🎠 Her Ekran İçin Otomatik Değişecek Temaları Ayrı Ayrı Seç...":
        "🎠 Select Rotation Themes Separately for Each Screen...",
    "🎮 Oyun Açıldığında Otomatik Oyun Temasına Geç": "🎮 Switch to Game Theme Automatically When Game Launches",
    "🎯 Varsayılan:": "🎯 Default:",
    "🚫 Yok (Özel Bağlanan Oyunlar)": "🚫 None (Only Explicitly Bound Games)",
    "🎮 Oyun Profilleri...": "🎮 Game Profiles...",
    "✅ Ayarları Kaydet ve Uygula": "✅ Save & Apply Settings",
    "💾 Ayarları Kaydet": "💾 Save Settings",

    # Dialogs: Media Cropper
    "✂️ CyberPulse — Arka Plan Medya Kırpıcı & Boyutlandırıcı": "✂️ CyberPulse — Background Media Cropper & Resizer",
    "✂️ Arka Plan Medya Kırpıcı (Video / GIF / Resim)": "✂️ Background Media Cropper (Video / GIF / Image)",
    "✅ Kırpmayı Uygula": "✅ Apply Crop",

    # New v1.4.0 Widgets & Features
    "🎛️ Canlı Ses / Müzik Ekolayzırı": "🎛️ Live Audio / Music Visualizer",
    "🔥 GPU Hotspot Sıcaklığı": "🔥 GPU Hotspot Temp",
    "🎮 GPU VRAM Kullanımı (GB)": "🎮 GPU VRAM Used (GB)",
    "🎮 GPU Kalan / Boş VRAM (GB)": "🎮 Free GPU VRAM (GB)",
    "GPU Hotspot Sıcaklığı": "GPU Hotspot Temp",
    "GPU VRAM Kullanımı (GB)": "GPU VRAM Used (GB)",
    "GPU VRAM Yükü (%)": "GPU VRAM Load (%)",
    "GPU Kalan / Boş VRAM (GB)": "Free GPU VRAM (GB)",
    "🎬  GIF / Video Çıktı": "🎬  Export GIF / Video",
    "🌟 Hazır Tema Paketleri": "🌟 Pro Theme Packs",
    "🎛️ Ekolayzır Stili:": "🎛️ Visualizer Style:",
    "📊 Dikey LED Barlar (Bars)": "📊 Vertical LED Bars",
    "🌊 Akıcı Ses Dalgası (Wave)": "🌊 Smooth Audio Waveform",
    "🌙 Windows Kilitlendiğinde (Win+L) Kasa Ekranını Otomatik Uyku Moduna Al":
        "🌙 Auto-Standby Case LCD When Windows is Locked (Win+L)",
    "Kasa Ekranı Parlaklığı (%)": "Case Display Brightness (%)",
    "Ekran Uyku / Bekleme Modu (Ekranı Karart / Uyandır)": "Display Standby / Sleep Mode (Dim / Wake Screen)",
    "Seçili Öğeleri Grupla / Grubu Çöz (Ctrl+G)": "Group / Ungroup Selected Widgets (Ctrl+G)",
    "Başlık / Etiket:": "Title / Label:",
}

# Dynamic regex patterns (Turkish -> English)
TR_TO_EN_PATTERNS = [
    (re.compile(r"^🔄\s*Düzeni Uygula \((.+)\)$"), lambda m: f"🔄  Apply Layout ({m.group(1)})"),
    (re.compile(r"^KATMANLAR \((\d+) ÖGE\)$"), lambda m: f"LAYERS ({m.group(1)} ITEMS)"),
    (re.compile(r"^📐 (\d+×\d+) \(Dikey\)$"), lambda m: f"📐 {m.group(1)} (Portrait)"),
    (re.compile(r"^📐 (\d+×\d+) \(Yatay\)$"), lambda m: f"📐 {m.group(1)} (Landscape)"),
    (re.compile(r"^([^\d]*)(\d+)\. Ekran: USB Kasa Ekranı(.*)$"), lambda m: f"{m.group(1)}Screen {m.group(2)}: USB Case LCD{m.group(3)}"),
    (re.compile(r"^([^\d]*)Ekran (\d+):(.*)$"), lambda m: f"{m.group(1)}Screen {m.group(2)}:{m.group(3)}"),
    (re.compile(r"^🔍 Algılanan Ekranlar \((\d+)\)$"), lambda m: f"🔍 Detected Displays ({m.group(1)})"),
    (re.compile(r"^📚 Kasa Ekranları Kataloğu \((\d+)\)$"), lambda m: f"📚 Case Display Catalog ({m.group(1)})"),
    (re.compile(r"^━━ 📐 (.+) \((\d+) Tema\) ━━$"), lambda m: f"━━ 📐 {m.group(1)} ({m.group(2)} Themes) ━━"),
    (re.compile(r"^(\.cptheme Tek Dosya Paketi)\s*•\s*(.+)$"), lambda m: f".cptheme Single-File Package  •  {m.group(2)}"),
    (re.compile(r"^🟢 Bağlı \((.+)\)$"), lambda m: f"🟢 Connected ({m.group(1)})"),
    (re.compile(r"^🟢 HDMI Yayında \((.+)\)$"), lambda m: f"🟢 HDMI Live ({m.group(1)})"),
    (re.compile(r"^🟢 Çift Yayın \((.+)\)$"), lambda m: f"🟢 Dual Live ({m.group(1)})"),
]


def translate_text(text: str, lang: str = "tr") -> str:
    """Translates a Turkish UI string into the target language ('tr' or 'en')."""
    if not text or lang == "tr":
        return text
    s = str(text)
    if s in TR_TO_EN_EXACT:
        return TR_TO_EN_EXACT[s]
    stripped = s.strip()
    if stripped in TR_TO_EN_EXACT:
        return TR_TO_EN_EXACT[stripped]
    for pat, repl_fn in TR_TO_EN_PATTERNS:
        m = pat.match(stripped)
        if m:
            return repl_fn(m)
    return s


def _translate_single_widget(w: QWidget, lang: str):
    """Applies translation to a single QWidget while preserving original Turkish strings."""
    try:
        # 1. Window title (for QMainWindow / QDialog)
        if w.isWindow():
            orig_wt = w.property("_cp_orig_tr_wtitle")
            curr_wt = w.windowTitle()
            if orig_wt is None and curr_wt:
                w.setProperty("_cp_orig_tr_wtitle", curr_wt)
                orig_wt = curr_wt
            if orig_wt:
                w.setWindowTitle(orig_wt if lang == "tr" else translate_text(orig_wt, lang))

        # 2. Tooltip
        curr_tt = w.toolTip()
        orig_tt = w.property("_cp_orig_tr_tooltip")
        if orig_tt is None and curr_tt:
            w.setProperty("_cp_orig_tr_tooltip", curr_tt)
            orig_tt = curr_tt
        if orig_tt:
            w.setToolTip(orig_tt if lang == "tr" else translate_text(orig_tt, lang))

        # 3. QLabel / QPushButton / QCheckBox / QGroupBox text
        if isinstance(w, (QLabel, QPushButton, QCheckBox)):
            curr_txt = w.text()
            orig_txt = w.property("_cp_orig_tr_text")
            # Update cached Turkish text if it changed dynamically in Turkish mode
            if orig_txt is None or (lang == "tr" and curr_txt and curr_txt != translate_text(orig_txt, "en")):
                w.setProperty("_cp_orig_tr_text", curr_txt)
                orig_txt = curr_txt
            elif lang == "en" and curr_txt and curr_txt != translate_text(orig_txt, "en") and (
                curr_txt in TR_TO_EN_EXACT or any(p.match(curr_txt.strip()) for p, _ in TR_TO_EN_PATTERNS)
            ):
                w.setProperty("_cp_orig_tr_text", curr_txt)
                orig_txt = curr_txt
            if orig_txt:
                new_txt = orig_txt if lang == "tr" else translate_text(orig_txt, lang)
                if w.text() != new_txt:
                    w.setText(new_txt)

        elif isinstance(w, QGroupBox):
            curr_t = w.title()
            orig_t = w.property("_cp_orig_tr_title")
            if orig_t is None and curr_t:
                w.setProperty("_cp_orig_tr_title", curr_t)
                orig_t = curr_t
            if orig_t:
                w.setTitle(orig_t if lang == "tr" else translate_text(orig_t, lang))

        elif isinstance(w, QLineEdit):
            curr_ph = w.placeholderText()
            orig_ph = w.property("_cp_orig_tr_placeholder")
            if orig_ph is None and curr_ph:
                w.setProperty("_cp_orig_tr_placeholder", curr_ph)
                orig_ph = curr_ph
            if orig_ph:
                w.setPlaceholderText(orig_ph if lang == "tr" else translate_text(orig_ph, lang))

        elif isinstance(w, QComboBox):
            orig_items = w.property("_cp_orig_tr_combo")
            if not isinstance(orig_items, dict):
                orig_items = {}
            for i in range(w.count()):
                it_txt = w.itemText(i)
                if i not in orig_items or (lang == "tr" and it_txt != translate_text(orig_items[i], "en")):
                    orig_items[i] = it_txt
                tr_val = orig_items.get(i, it_txt)
                new_val = tr_val if lang == "tr" else translate_text(tr_val, lang)
                if it_txt != new_val:
                    w.setItemText(i, new_val)
            w.setProperty("_cp_orig_tr_combo", orig_items)

        elif isinstance(w, QTabWidget):
            orig_tabs = w.property("_cp_orig_tr_tabs")
            if not isinstance(orig_tabs, dict):
                orig_tabs = {}
            for i in range(w.count()):
                tb_txt = w.tabText(i)
                if i not in orig_tabs:
                    orig_tabs[i] = tb_txt
                tr_val = orig_tabs.get(i, tb_txt)
                new_val = tr_val if lang == "tr" else translate_text(tr_val, lang)
                if tb_txt != new_val:
                    w.setTabText(i, new_val)
            w.setProperty("_cp_orig_tr_tabs", orig_tabs)

    except Exception:
        pass


def apply_language_to_widget_tree(root_widget: QWidget, lang: str = "tr"):
    """Recursively applies 'tr' or 'en' translations to root_widget and all its descendant widgets."""
    if root_widget is None:
        return
    _translate_single_widget(root_widget, lang)
    for child in root_widget.findChildren(QWidget):
        _translate_single_widget(child, lang)
