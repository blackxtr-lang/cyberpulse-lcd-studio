<div align="center">

# ⚡ CYBERPULSE — PC Kasa Ekranı & Tema Stüdyosu

<!-- 🌐 DİL SEÇİMİ / LANGUAGE SWITCHER -->
[![Türkçe](https://img.shields.io/badge/%F0%9F%87%B9%F0%9F%87%B7%20Dil-T%C3%BCrk%C3%A7e%20(Aktif)-00a6e0?style=for-the-badge)](README.md)
[![English](https://img.shields.io/badge/%F0%9F%87%AC%F0%9F%87%A7%20Language-English%20(Click%20Here)-222a3d?style=for-the-badge)](README_EN.md)

**USB Seri (`320×1480` / Turing / XuanFang / HYTE / Lian Li / Corsair) ve HDMI/DP kasa içi IPS ekranlar için gerçek zamanlı donanım telemetrisi, çoklu ekran stüdyosu ve otomatik oyun profili yöneticisi.**

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(x64)-00a6e0?style=flat-square&logo=windows&logoColor=white)](#)
[![Dil Desteği](https://img.shields.io/badge/Aray%C3%BCz%20Dili-T%C3%BCrk%C3%A7e%20%7C%20English-8083ff?style=flat-square)](#)
[![License: MIT](https://img.shields.io/badge/Lisans-MIT-4edea3?style=flat-square)](LICENSE)

<br/>

<!-- 📥 DOĞRUDAN .EXE İNDİRME & ☕ BAĞIŞ BUTONLARI -->
<a href="https://github.com/blackxtr-lang/cyberpulse-lcd-studio/releases/latest/download/CyberPulse_Studio_Windows_x64.zip">
  <img src="https://img.shields.io/badge/%F0%9F%93%A5%20Windows%20%C4%B0%C3%A7in%20%C4%B0ndir-Haz%C4%B1r%20.EXE%20Paketi%20(ZIP)-00885d?style=for-the-badge&logo=windows&logoColor=white" alt="Windows İçin İndir (.exe)" height="42" />
</a>
&nbsp;&nbsp;
<a href="https://www.buymeacoffee.com/blackxtr" target="_blank">
  <img src="https://img.shields.io/badge/%E2%98%95%20Bana%20Bir%20Kahve%20Ismarla-Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black" alt="Bana Bir Kahve Ismarla" height="42" />
</a>

</div>

---

## 🖥️ Arayüz Önizlemesi (`🇹🇷 Türkçe` & `🇬🇧 English` Çift Dilli Arayüz)

<div align="center">
  <img src="docs/screenshots/cyberpulse_studio_preview.png" alt="CyberPulse Studio Türkçe Arayüzü" width="100%" />
</div>

---

## 📥 Kurulumsuz İndirme ve Kullanım (`.exe`)

Python veya ek kütüphane kurmanıza gerek yoktur:

1. Yukarıdaki **[📥 Windows İçin İndir (Hazır .EXE Paketi)](https://github.com/blackxtr-lang/cyberpulse-lcd-studio/releases/latest/download/CyberPulse_Studio_Windows_x64.zip)** butonuna (veya sağ taraftaki **[Releases](https://github.com/blackxtr-lang/cyberpulse-lcd-studio/releases)** bölümüne) tıklayarak `CyberPulse_Studio_Windows_x64.zip` dosyasını indirin.
2. ZIP arşivini bilgisayarınızda istediğiniz bir klasöre çıkartın.
3. Klasör içindeki **`CyberPulse_Studio.exe`** dosyasına çift tıklayarak programı doğrudan başlatın!
4. Sol menünün altındaki **`🌐 Dil: TR / EN`** butonuna tıklayarak uygulama dilini istediğiniz an **Türkçe** veya **İngilizce** yapabilirsiniz.

---

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

---

## 🛠️ Geliştiriciler İçin Kaynak Koddan Çalıştırma / Derleme

```bash
git clone https://github.com/blackxtr-lang/cyberpulse-lcd-studio.git
cd cyberpulse-lcd-studio
pip install -r requirements.txt
python cyberpulse_studio/main_gui.py
```
*Kendi `.exe` paketinizi oluşturmak için `build_exe.bat` dosyasına çift tıklayabilirsiniz.*

---

## ☕ Projeyi Destekleyin (Bana Bir Kahve Ismarla)

**CyberPulse Studio** tamamen açık kaynaklı ve ücretsiz olarak geliştirilmektedir. Projeyi beğendiyseniz ve yeni ekran protokolleri / bileşenler eklenmesine destek olmak isterseniz bir kahve ısmarlayabilirsiniz:

<div align="center">

<a href="https://www.buymeacoffee.com/blackxtr" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="54" />
</a>

</div>

---

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) altında lisanslanmıştır.
