<div align="center">

# ⚡ CYBERPULSE — PC Kasa Ekranı & Tema Stüdyosu / PC Case Screen & Theme Studio

**🇹🇷 USB Seri (`320×1480` / Turing / XuanFang / HYTE / Lian Li / Corsair) ve HDMI/DP kasa içi IPS ekranlar için gerçek zamanlı donanım telemetrisi, çoklu ekran stüdyosu ve otomatik oyun profili yöneticisi.**

**🇬🇧 Real-time hardware telemetry, multi-display theme studio, and automatic game profile switcher for USB Serial (`320×1480` / Turing / XuanFang / HYTE / Lian Li / Corsair) and HDMI/DP in-case IPS displays.**

<br/>

<!-- 🌐 SAYFA İÇİ DİL GEÇİŞİ / IN-PAGE LANGUAGE JUMP LINKS -->
[![Türkçe Bölüm](https://img.shields.io/badge/%F0%9F%87%B9%F0%9F%87%B7%20T%C3%BCrk%C3%A7e-Tan%C4%B1t%C4%B1m%20ve%20Rehber-00a6e0?style=for-the-badge)](#-türkçe-tanıtım-ve-kullanım-rehberi)
[![English Section](https://img.shields.io/badge/%F0%9F%87%AC%F0%9F%87%A7%20English-Overview%20%26%20Guide-8083ff?style=for-the-badge)](#-english-overview--documentation)

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(x64)-00a6e0?style=flat-square&logo=windows&logoColor=white)](#)
[![UI Languages](https://img.shields.io/badge/UI%20%2F%20Aray%C3%BCz-T%C3%BCrk%C3%A7e%20%7C%20English-8083ff?style=flat-square)](#)
[![License: MIT](https://img.shields.io/badge/License%20%2F%20Lisans-MIT-4edea3?style=flat-square)](LICENSE)

<br/>

<!-- 📥 DOĞRUDAN .EXE İNDİRME & ☕ BAĞIŞ BUTONLARI / DIRECT .EXE DOWNLOAD & DONATION -->
<a href="https://github.com/blackxtr-lang/cyberpulse-lcd-studio/releases/latest/download/CyberPulse_Studio_Windows_x64.zip">
  <img src="https://img.shields.io/badge/%F0%9F%93%A5%20%C4%B0ndir%20%2F%20Download%20(.EXE)-Windows%20Portable%20ZIP-00885d?style=for-the-badge&logo=windows&logoColor=white" alt="Download Windows Portable (.exe)" height="44" />
</a>
&nbsp;&nbsp;
<a href="https://github.com/sponsors/blackxtr-lang" target="_blank">
  <img src="https://img.shields.io/badge/%E2%98%95%20Bana%20Bir%20Kahve%20Ismarla-GitHub%20Sponsors%20%E2%9D%A4%EF%B8%8F-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="GitHub Sponsors - Bana Bir Kahve Ismarla" height="44" />
</a>

</div>

---

# 🇹🇷 Türkçe Tanıtım ve Kullanım Rehberi

## 🖥️ Arayüz Önizlemesi (Türkçe Modu)

<div align="center">
  <img src="docs/screenshots/cyberpulse_studio_preview.png" alt="CyberPulse Studio Türkçe Arayüzü" width="100%" />
</div>

## 📥 Kurulumsuz İndirme ve Kullanım (`.exe`)

Python veya ek kütüphane kurmanıza gerek yoktur:

1. Yukarıdaki **[📥 İndir / Download (.EXE) — Windows Portable ZIP](https://github.com/blackxtr-lang/cyberpulse-lcd-studio/releases/latest/download/CyberPulse_Studio_Windows_x64.zip)** butonuna (veya sağ taraftaki **[Releases](https://github.com/blackxtr-lang/cyberpulse-lcd-studio/releases)** bölümüne) tıklayarak `CyberPulse_Studio_Windows_x64.zip` dosyasını indirin.
2. ZIP arşivini bilgisayarınızda istediğiniz bir klasöre çıkartın.
3. Klasör içindeki **`CyberPulse_Studio.exe`** dosyasına çift tıklayarak programı doğrudan başlatın!
4. Sol menünün altındaki **`🌐 Dil: TR 🇹🇷 / EN 🇬🇧`** butonuna tıklayarak uygulama dilini istediğiniz an **Türkçe** veya **İngilizce** yapabilirsiniz.

## ✨ Öne Çıkan Özellikler

- **🌐 Çift Dilli Arayüz (`🇹🇷 Türkçe` / `🇬🇧 English`):**
  - Sol menüdeki tek tuşla veya Sistem Ayarları üzerinden tüm stüdyo ve alt pencereleri anında Türkçe / İngilizce arasında değiştirin.
- **🖥️ Çoklu Ekran Çalışma Alanı (Multi-Screen Workspace):**
  - Aynı anda hem **USB Seri LCD (COM Port)** hem de **HDMI / DisplayPort** kasa ekranlarını bağımsız temalarla ve bağımsız çözünürlüklerle (`320×1480`, `480×1920`, `1280×400`, `1920×1080`, `2560×1440`, `3840×2160` veya özel boyut) yönetin.
- **📊 30+ Canlı Donanım ve Medya Bileşeni:**
  - **CPU & GPU:** Sıcaklık, yük (%), frekans (MHz), fan devri (RPM/%).
  - **Sistem & Ağ:** RAM kullanımı, NVMe/SATA disk okuma-yazma hızı, canlı indirme/yükleme (Download/Upload) hızı, canlı Ping monitörü ve 60 saniyelik Sparkline çizgi grafikleri.
  - **Zengin Widget'lar:** RTSS/Win32 tabanlı oyun FPS sayacı, Windows SMTC canlı medya/YouTube Music kartı, otomatik konumlu hava durumu kartı, etkinlik geri sayım sayacı, dairesel/yatay/dikey göstergeler ve özelleştirilebilir kayan LED metin (Marquee).
- **🎮 Otomatik Oyun Profili Bağlayıcı:**
  - Bilgisayarınızdaki Steam, Epic Games veya özel `.exe` oyunlarını istediğiniz temaya bağlayın. Oyun açıldığında kasa ekranınız otomatik olarak o oyunun temasına geçer, oyun kapandığında masaüstü temanıza geri döner.
- **↻ Seçmeli Otomatik Tema Döngüsü (Playlist):**
  - Her ekran için ayrı ayrı hangi temaların, hangi süreyle ve sırayla (veya rastgele) değişeceğini belirleyin.
- **📦 Tek Dosya `.cptheme` Paketleme & Akıllı Ölçeklendirme:**
  - Arka plan videoları (`.mp4`, `.gif`, `.png`), özel katman görselleri ve tüm sensör yerleşimleri tek bir taşınabilir `.cptheme` dosyasında saklanır.
  - Farklı çözünürlükteki bir ekrana geçildiğinde veya **"Düzeni Uygula"** kullanıldığında tüm bileşenler orantısal olarak hedef çözünürlüğe uyarlanır.

---

# 🇬🇧 English Overview & Documentation

## 🖥️ Studio Preview (English Mode)

<div align="center">
  <img src="docs/screenshots/cyberpulse_studio_preview_en.png" alt="CyberPulse Studio English UI" width="100%" />
</div>

## 📥 Portable Download & Quick Start (`.exe`)

No Python installation is required to run the standalone Windows build:

1. Click **[📥 İndir / Download (.EXE) — Windows Portable ZIP](https://github.com/blackxtr-lang/cyberpulse-lcd-studio/releases/latest/download/CyberPulse_Studio_Windows_x64.zip)** at the top of this page (or visit the **[Releases](https://github.com/blackxtr-lang/cyberpulse-lcd-studio/releases)** section on the right).
2. Extract `CyberPulse_Studio_Windows_x64.zip` to any folder on your PC.
3. Double-click **`CyberPulse_Studio.exe`** to launch!
4. Click **`🌐 Language: EN 🇬🇧 / TR 🇹🇷`** at the bottom of the left sidebar to switch between **English** and **Turkish** anytime.

## ✨ Key Features

- **🌐 Bilingual Studio Interface (`🇬🇧 English` / `🇹🇷 Türkçe`):**
  - Switch the entire studio and all sub-dialogs between English and Turkish with a single click from the left sidebar or System Settings.
- **🖥️ Multi-Screen Workspace Engine:**
  - Drive both **USB Serial LCDs (COM Port)** and **HDMI / DisplayPort** case monitors simultaneously with independent themes and independent resolutions (`320×1480`, `480×1920`, `1280×400`, `1920×1080`, `2560×1440`, `3840×2160`, or custom dimensions).
- **📊 30+ Live Hardware & Media Widgets:**
  - **CPU & GPU:** Temperature, load (%), clock frequency (MHz), fan speed (RPM/%).
  - **System & Network:** RAM usage, NVMe/SATA disk read/write throughput, live download/upload speed, live Ping monitor, and 60-second Sparkline history graphs.
  - **Rich Widgets:** RTSS/Win32 in-game FPS counter, Windows SMTC Now Playing / YouTube Music card, auto-location live weather card, event countdown timer, radial/horizontal/vertical gauges, and customizable scrolling LED ticker (Marquee).
- **🎮 Automatic Game Profile Switcher:**
  - Bind any installed Steam, Epic Games, or custom `.exe` game to a specific theme. When the game launches, your case screen automatically switches to that game's theme and restores your desktop theme when the game exits.
- **↻ Per-Screen Selective Auto-Rotation (Playlist):**
  - Choose which themes rotate, in what order (sequential or shuffle), and at what interval independently for each connected display.
- **📦 Single-File `.cptheme` Packaging & Smart Resolution Scaling:**
  - Background videos (`.mp4`, `.gif`, `.png`), custom overlay graphics, and widget layouts are packed into a single portable `.cptheme` file with automatic aspect-ratio scaling across different display resolutions.

---

## 🛠️ Kaynak Koddan Çalıştırma / Running from Source (Developers)

```bash
git clone https://github.com/blackxtr-lang/cyberpulse-lcd-studio.git
cd cyberpulse-lcd-studio
pip install -r requirements.txt
python cyberpulse_studio/main_gui.py
```
- **🇹🇷 Yerel `.exe` Derleme:** Klasördeki `build_exe.bat` dosyasına çift tıklayarak kendi taşınabilir `.exe` paketinizi oluşturabilirsiniz.
- **🇬🇧 Local `.exe` Build:** Double-click `build_exe.bat` to compile your own standalone portable `.exe` bundle in `dist/CyberPulse_Studio/`.

---

## ☕ Projeyi Destekleyin / Support the Project (Buy Me a Coffee)

- **🇹🇷 Türkçe:** **CyberPulse Studio** tamamen açık kaynaklı ve ücretsiz olarak geliştirilmektedir. Projeyi beğendiyseniz ve yeni ekran protokolleri / bileşenler eklenmesine destek olmak isterseniz bir kahve ısmarlayabilirsiniz.
- **🇬🇧 English:** **CyberPulse Studio** is completely free and open-source. If you enjoy using it and want to support the addition of new display protocols and widgets, consider buying me a coffee:

<div align="center">

<a href="https://github.com/sponsors/blackxtr-lang" target="_blank">
  <img src="https://img.shields.io/badge/%E2%9D%A4%EF%B8%8F%20GitHub%20Sponsors-%E2%98%95%20Bana%20Bir%20Kahve%20Ismarla%20%2F%20Buy%20Me%20A%20Coffee-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="Sponsor on GitHub" height="48" />
</a>

</div>

---

## 📄 Lisans / License

Bu proje [MIT Lisansı](LICENSE) altında lisanslanmıştır. / Licensed under the [MIT License](LICENSE).
