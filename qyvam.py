import streamlit as st
from docx import Document
from docx.shared import Inches
import io
import pytz
import sqlite3
import os
from datetime import datetime
import locale

# ==============================================================================
# SİSTEM AYARLARI VE GİZLİ KASA (API KEY)
# ==============================================================================
st.set_page_config(page_title="Qyvam | Siber Uzay", layout="wide", initial_sidebar_state="expanded")

# API Anahtarını Streamlit'in bulut (veya yerel) gizli kasasından çekiyoruz
try:
    from openai import OpenAI
    OPENROUTER_KEY = st.secrets["OPENROUTER_KEY"]
except:
    OPENROUTER_KEY = ""

if 'aktif_sayfa' not in st.session_state: st.session_state.aktif_sayfa = "Ana Sayfa"
if 'veli_yetkili' not in st.session_state: st.session_state.veli_yetkili = False
if 'aktif_cocuk_id' not in st.session_state: st.session_state.aktif_cocuk_id = None
if 'aktif_cocuk_isim' not in st.session_state: st.session_state.aktif_cocuk_isim = ""

# ==============================================================================
# MÜFREDAT BAĞLANTISI
# ==============================================================================
try:
    from mufredat import MUFREDAT
except ImportError:
    MUFREDAT = {}
    st.error("[ SİSTEM UYARISI ]: mufredat.py dosyası bulunamadı.")

# ==============================================================================
# VERİTABANI MOTORU
# ==============================================================================
def veritabani_hazirla():
    baglanti = sqlite3.connect('qyvam_siber.db')
    imlec = baglanti.cursor()
    imlec.execute('CREATE TABLE IF NOT EXISTS Cocuklar (id INTEGER PRIMARY KEY AUTOINCREMENT, isim TEXT, mevcut_adim INTEGER)')
    imlec.execute('CREATE TABLE IF NOT EXISTS Gorevler (id INTEGER PRIMARY KEY AUTOINCREMENT, cocuk_id INTEGER, gorev_adi TEXT, tefekkur TEXT, durum TEXT, puan INTEGER, veli_notu TEXT, tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    baglanti.commit()
    baglanti.close()

veritabani_hazirla()

# ==============================================================================
# ÇOCUK EKLEME FONKSİYONU
# ==============================================================================
def cocuk_ekle(isim):
    import sqlite3
    conn = sqlite3.connect('qyvam_veritabani.db')
    c = conn.cursor()
    # Eğer cocuklar tablosu yoksa önce onu oluşturalım (Güvenlik önlemi)
    c.execute('''CREATE TABLE IF NOT EXISTS cocuklar 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  isim TEXT, 
                  mevcut_adim INTEGER)''')
    # Şimdi ismi kaydedelim
    c.execute("INSERT INTO cocuklar (isim, mevcut_adim) VALUES (?, ?)", (isim, 1))
    conn.commit()
    conn.close()

# ==============================================================================
# ÖZEL BERAT VERİTABANI İŞLEMLERİ
# ==============================================================================
def ozel_berat_ekle(cocuk_id, berat_adi, berat_aciklama):
    import sqlite3
    conn = sqlite3.connect('qyvam_veritabani.db')
    c = conn.cursor()
    # Eğer tablo yoksa otomatik oluşturur
    c.execute('''CREATE TABLE IF NOT EXISTS ozel_beratlar 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  cocuk_id INTEGER, 
                  berat_adi TEXT, 
                  berat_aciklama TEXT)''')
    c.execute("INSERT INTO ozel_beratlar (cocuk_id, berat_adi, berat_aciklama) VALUES (?, ?, ?)", 
              (cocuk_id, berat_adi, berat_aciklama))
    conn.commit()
    conn.close()
    
def cocuk_adim_guncelle(cocuk_id, yeni_adim):
    import sqlite3
    conn = sqlite3.connect('qyvam_veritabani.db')
    c = conn.cursor()
    c.execute("UPDATE cocuklar SET mevcut_adim = ? WHERE id = ?", (yeni_adim, cocuk_id))
    conn.commit()
    conn.close()

def cocuk_sil(cocuk_id):
    import sqlite3
    conn = sqlite3.connect('qyvam_veritabani.db')
    c = conn.cursor()
    
    try:
        # Önce tablonun gerçek yapısını (sütun isimlerini) öğrenelim (DEBUG İÇİN)
        c.execute("PRAGMA table_info(cocuklar)")
        columns = [info[1] for info in c.fetchall()]
        
        # Eğer tabloda 'id' yoksa hatayı hemen burada yakalayalım
        if 'id' not in columns:
            return False, f"HATA: 'cocuklar' tablosunda 'id' sütunu yok! Mevcut sütunlar: {columns}"

        # 1. Çocuğu sil
        c.execute("DELETE FROM cocuklar WHERE id = ?", (cocuk_id,))
        
        # 2. İşlemleri sil
        c.execute("DELETE FROM islemler WHERE cocuk_id = ?", (cocuk_id,))
        
        # 3. Beratları sil
        c.execute("DELETE FROM ozel_beratlar WHERE cocuk_id = ?", (cocuk_id,))
        
        conn.commit()
        return True, "Başarılı"
    except Exception as e:
        return False, f"SQL HATASI: {str(e)}"
    finally:
        conn.close()
    
def ozel_beratlari_getir(cocuk_id):
    import sqlite3
    conn = sqlite3.connect('qyvam_veritabani.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ozel_beratlar 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  cocuk_id INTEGER, 
                  berat_adi TEXT, 
                  berat_aciklama TEXT)''')
    c.execute("SELECT berat_adi, berat_aciklama FROM ozel_beratlar WHERE cocuk_id=?", (cocuk_id,))
    veriler = c.fetchall()
    conn.close()
    return veriler
              
def cocuklari_getir():
    baglanti = sqlite3.connect('qyvam_siber.db')
    imlec = baglanti.cursor()
    imlec.execute('SELECT id, isim, mevcut_adim FROM Cocuklar')
    liste = imlec.fetchall()
    baglanti.close()
    return liste

def cocuk_bilgisi_getir(cocuk_id):
    baglanti = sqlite3.connect('qyvam_siber.db')
    imlec = baglanti.cursor()
    imlec.execute('SELECT isim, mevcut_adim FROM Cocuklar WHERE id = ?', (cocuk_id,))
    sonuc = imlec.fetchone()
    baglanti.close()
    return sonuc

def onay_bekleyenleri_getir():
    baglanti = sqlite3.connect('qyvam_siber.db')
    imlec = baglanti.cursor()
    imlec.execute('''
        SELECT G.id, C.isim, G.gorev_adi, G.tefekkur, C.id, C.mevcut_adim 
        FROM Gorevler G 
        JOIN Cocuklar C ON G.cocuk_id = C.id 
        WHERE G.durum = 'Veli Onayı Bekliyor'
    ''')
    liste = imlec.fetchall()
    baglanti.close()
    return liste

def bekleyen_gorev_kontrol(cocuk_id):
    baglanti = sqlite3.connect('qyvam_siber.db')
    imlec = baglanti.cursor()
    imlec.execute("SELECT id FROM Gorevler WHERE cocuk_id=? AND durum='Veli Onayı Bekliyor'", (cocuk_id,))
    sonuc = imlec.fetchone()
    baglanti.close()
    return sonuc is not None

def cocuk_veri_gonder(cocuk_id, gorev_adi, tefekkur_cevabi):
    baglanti = sqlite3.connect('qyvam_siber.db')
    imlec = baglanti.cursor()
    imlec.execute("INSERT INTO Gorevler (cocuk_id, gorev_adi, tefekkur, durum) VALUES (?, ?, ?, 'Veli Onayı Bekliyor')", (cocuk_id, gorev_adi, tefekkur_cevabi))
    baglanti.commit()
    baglanti.close()

def veli_onayi_ver(gorev_id, puan, veli_notu, cocuk_id, basarili_mi):
    baglanti = sqlite3.connect('qyvam_siber.db')
    imlec = baglanti.cursor()
    imlec.execute("UPDATE Gorevler SET durum = 'Onaylandı', puan = ?, veli_notu = ? WHERE id = ?", (puan, veli_notu, gorev_id))
    if basarili_mi:
        imlec.execute("UPDATE Cocuklar SET mevcut_adim = mevcut_adim + 1 WHERE id = ?", (cocuk_id,))
    baglanti.commit()
    baglanti.close()

def kazanilan_sertifikalari_hesapla(adim):
    sertifikalar = []
    if adim > 14: sertifikalar.append(("[ KÖKLER YETKİNLİK BERATI ]", "Bedenine ve mekanına gösterdiği irade ile kendi şahsi gayreti ve rehberinin onayıyla kazanılmıştır."))
    if adim > 28: sertifikalar.append(("[ BAĞLAR YETKİNLİK BERATI ]", "Ailesine ve çevresine gösterdiği ikram bilinciyle kazanılmıştır."))
    if adim > 42: sertifikalar.append(("[ PUSULA YETKİNLİK BERATI ]", "Zaman ve dijital irade yönetimindeki kararlılığıyla kazanılmıştır."))
    if adim > 56: sertifikalar.append(("[ AYNALAR YETKİNLİK BERATI ]", "Öz-farkındalık ve derin empati yeteneğiyle tescillenmiştir."))
    if adim > 70: sertifikalar.append(("[ ÇARKLAR YETKİNLİK BERATI ]", "Üretim ve finansal denge konularındaki olgunluğuyla kazanılmıştır."))
    if adim > 84: sertifikalar.append(("[ KÖPRÜLER YETKİNLİK BERATI ]", "Topluma ve doğaya olan merhametli yaklaşımıyla kazanılmıştır."))
    if adim > 99: sertifikalar.append(("[ KANATLAR YETKİNLİK BERATI ]", "İhsan makamında, örnek bir şahsiyet olmaya dair üstün yetkinlik belgesidir."))
    return sertifikalar
    
def word_raporu_olustur(cocuk_ismi, gorev_adi, veli_notu, fotograf_bytes=None):
    doc = Document()
    doc.add_heading(f'Qyvam - Görev Raporu: {cocuk_ismi}', 0)
    
    doc.add_paragraph("Görev İçeriği:").bold = True
    doc.add_paragraph(gorev_adi)
    
    doc.add_paragraph("Rehber (Veli) Gözlemi:").bold = True
    doc.add_paragraph(veli_notu)
    
    if fotograf_bytes:
        doc.add_paragraph("Görevin Görsel Kanıtı:").bold = True
        foto_io = io.BytesIO(fotograf_bytes)
        doc.add_picture(foto_io, width=Inches(5.0)) # Fotoğrafı sayfaya sığdır
        
    byte_io = io.BytesIO()
    doc.save(byte_io)
    byte_io.seek(0)
    return byte_io
    
# ==============================================================================
# YAPAY ZEKA BAĞLANTISI (API MOTORU)
# ==============================================================================
# ==============================================================================
# YAPAY ZEKA BAĞLANTISI (YEDEK MOTORLU VE HATA CASUSLU API)
# ==============================================================================
def ai_cevap_uret(soru, mevcut_adim, rol="veli", cocuk_isim=""):
    if not OPENROUTER_KEY:
        return "[ SİSTEM UYARISI ]: API Anahtarı bulunamadı. Yapay zeka çevrimdışı."
        
    faz = MUFREDAT.get(mevcut_adim, {}).get("faz", "Bilinmeyen Faz")
    
    if rol == "veli":
        prompt = f"Sen Qyvam adında uzman bir pedagojik asistansın. Veliye cevap veriyorsun. Çocuğun mevcut aşaması: {faz}. Soru: {soru}"
    else:
        prompt = f"Senin adın Qyman. Zeki, siber fütüristik bir dijital ikiz rehberisin. Karşındaki arkadaşının adı {cocuk_isim}. Cümlelerin kısa, cesaretlendirici olsun. Emojileri asla kullanma. Gelişim aşaması: {faz}. Soru: {soru}"

    ucretsiz_modeller = [
        "deepseek/deepseek-v4-flash"
    ]

    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
        
        son_hata = ""
        for model_adi in ucretsiz_modeller:
            try:
                response = client.chat.completions.create(
                    model=model_adi,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content
            except Exception as e:
                son_hata = str(e) # Hatayı hafızaya al ama sistemi çökertme
                continue
                
        # Eğer hiçbiri çalışmazsa, ekrana son hatanın ne olduğunu yazdır
        return f"[ SİSTEM DETAYI ]: Ücretsiz kanallar kapalı. Rapor: {son_hata}"
    except Exception as e:
        return f"[ SİSTEM HATASI ]: Bağlantı kurulamadı. Detay: {str(e)}"

# ==============================================================================
# AYDINLIK / PASTEL EĞİTİM ARAYÜZÜ (CSS KATMANI)
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Baloo+2:wght@500;600;700&family=Nunito:wght@400;600;700&display=swap');

    /* Genel Arkaplan ve Metinler */
    html, body, [class*="css"] { font-family: 'Nunito', sans-serif; background-color: #f0f4f8 !important; color: #334155 !important; }
    
    /* Başlıklar - Daha tatlı, yuvarlak hatlı eğitim fontu */
    h1, h2, h3, h4, h5 { font-family: 'Baloo 2', sans-serif; font-weight: 700; color: #4f46e5 !important; }

    /* Kutular - Beyaz, yumuşak gölgeli, pastel köşeli */
    .glass-box { background: #ffffff; border: 2px solid #e0e7ff; border-radius: 16px; padding: 25px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(99, 102, 241, 0.05); }
    .glass-task { background: #fdf2f8; border-left: 5px solid #f472b6; border-radius: 12px; padding: 20px; margin-bottom: 15px; }
    
    /* Üst Çubuk */
    .top-bar { background: #ffffff; border-bottom: 3px solid #e0e7ff; padding: 15px; margin-top: -50px; margin-bottom: 30px; border-radius: 0 0 20px 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.02); }
    
    /* Bilgi Metinleri ve Etiketler */
    .breadcrumb { color: #64748b; font-size: 0.95rem; font-weight: 600; }
    .breadcrumb b { color: #4f46e5; }
    .sensor-data { color: #0284c7; font-size: 0.85rem; background: #e0f2fe; border: 1px solid #bae6fd; padding: 5px 12px; border-radius: 8px; margin-right: 10px; display: inline-block; font-weight: 700; }
    
    /* Qyman Mesaj Kutusu (Yumuşak Konuşma Balonu Hissi) */
    .qyman-hud { background: #eff6ff; border-left: 5px solid #3b82f6; border-radius: 12px; padding: 20px; font-family: 'Nunito', sans-serif; color: #1e3a8a; line-height: 1.6; margin-bottom: 20px; box-shadow: 0 4px 10px rgba(59, 130, 246, 0.08); }
    
    /* Eski Neon sınıflarını Pastel tonlara çevirdik */
    .neon-text { color: #4f46e5 !important; text-shadow: none; }
    .neon-green { color: #059669 !important; font-weight: 700; }
    .system-log { color: #8b5cf6; font-size: 0.95rem; font-weight: 700; }
    
    /* Sol Menü (Radar) */
    .radar-baslik { color: #ec4899; font-weight: 700; margin-top: 15px; font-family: 'Baloo 2', sans-serif; font-size: 1.2rem; }
    .radar-adim { color: #64748b; font-size: 0.95rem; margin-left: 15px; padding-top: 5px; border-left: 3px solid #e2e8f0; padding-left: 12px; font-weight: 600; }
    
    /* Butonlar - Yumuşak hatlı, renkli ve eğlenceli */
    .stButton>button { border-radius: 12px; font-family: 'Baloo 2', sans-serif; font-size: 1.1rem !important; font-weight: 700; border: none; background-color: #6366f1; color: white !important; transition: all 0.3s ease; width: 100%; box-shadow: 0 4px 6px rgba(99, 102, 241, 0.25); }
    .stButton>button:hover { background-color: #4f46e5; transform: translateY(-2px); box-shadow: 0 6px 12px rgba(99, 102, 241, 0.35); }
    
    /* Girdi Kutuları (Input/Textarea) */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea { 
        background-color: #f8fafc !important; 
        color: #334155 !important; 
        border: 2px solid #cbd5e1 !important; 
        border-radius: 12px !important; 
        font-weight: 600 !important;
        transition: all 0.2s;
    }
    .stTextInput>div>div>input::placeholder, .stTextArea>div>div>textarea::placeholder {
        color: #94a3b8 !important;
    }
    .stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.15) !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# ÜST DURUM ÇUBUĞU (TOP BAR)
# ==============================================================================
def ust_komuta_merkezi():
    st.markdown('<div class="top-bar">', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    col_sol, col_orta, col_sag = st.columns([3, 1, 4])
    with col_sol:
        if st.session_state.aktif_sayfa == "Ana Sayfa": durum_metni = "ANA SAYFA"
        elif st.session_state.aktif_sayfa == "Veli_Panel": durum_metni = "REHBERLİK KÖŞESİ"
        else: durum_metni = "GELİŞİM YOLCULUĞU"
        st.markdown(f'<div class="breadcrumb">Qyvam Eğitim Sistemi > <b>{durum_metni}</b></div>', unsafe_allow_html=True)
        
    with col_orta:
        if st.session_state.aktif_sayfa == "Ana Sayfa" or st.session_state.aktif_sayfa == "Cocuk_Panel":
            if st.button("Rehber Girişi"): 
                st.session_state.veli_yetkili = True 
                st.session_state.aktif_sayfa = "Veli_Panel" 
                st.rerun()
        else:
            if st.button("Ana Sayfaya Dön"):
                st.session_state.aktif_sayfa = "Ana Sayfa"
                st.session_state.veli_yetkili = False
                st.session_state.aktif_cocuk_id = None
                st.rerun()
                
    with col_sag:
        # Türkiye Saati Senkronizasyonu
        tz = pytz.timezone('Europe/Istanbul')
        simdi = datetime.now(tz)
        aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        tarih_str = f"{simdi.day} {aylar[simdi.month-1]} {simdi.year} | {simdi.strftime('%H:%M')}"
        
        bekleyen_sayisi = len(onay_bekleyenleri_getir())
        bildirim_kodu = f'<span class="sensor-data" style="color:#ef4444; border-color:#fca5a5;">[ ONAY BEKLEYEN: {bekleyen_sayisi} ]</span>' if bekleyen_sayisi > 0 else ''

        st.markdown(f'''
            <div style="text-align: right;">
                <span class="sensor-data" style="background:#dcfce7; border-color:#86efac; color:#166534;">🍃 Hava Kalitesi: Optimum</span>
                <span class="sensor-data" style="background:#fef9c3; border-color:#fde047; color:#854d0e;">💨 CO2: 435 ppm</span>
                <span class="sensor-data">{tarih_str}</span>
                {bildirim_kodu}
            </div>
            <hr style="border-color: rgba(99, 102, 241, 0.2); margin-top: 15px;">
        ''', unsafe_allow_html=True)

# ==============================================================================
# GELİŞİM RADARI
# ==============================================================================
def sol_radar_olustur():
    st.sidebar.markdown('<h2 class="neon-text" style="text-align:center;">GELİŞİM RADARI</h2>', unsafe_allow_html=True)
    st.sidebar.markdown('<div class="system-log" style="text-align:center; margin-bottom: 20px;">[ VERİTABANI BAĞLI ]</div>', unsafe_allow_html=True)
    if not MUFREDAT: return

    faz_gruplari = {}
    for adim_no, detay in MUFREDAT.items():
        faz_adi = detay.get("faz", "Bilinmeyen Faz")
        ust_seviye = detay.get("ust_seviye", "Genel Eylem")
        alt_seviye = detay.get("alt_seviye", "Pekiştirme")

        if faz_adi not in faz_gruplari: faz_gruplari[faz_adi] = {}
        if ust_seviye not in faz_gruplari[faz_adi]: faz_gruplari[faz_adi][ust_seviye] = []
        faz_gruplari[faz_adi][ust_seviye].append((adim_no, alt_seviye))

    for faz_adi, ust_seviyeler in faz_gruplari.items():
        with st.sidebar.expander(f"[{faz_adi.upper()}]"):
            for ust_adi, alt_liste in ust_seviyeler.items():
                st.markdown(f"<div class='radar-baslik'>{ust_adi}</div>", unsafe_allow_html=True)
                for adim_no, alt_adi in alt_liste:
                    st.markdown(f"<div class='radar-adim'>Adım {adim_no}: {alt_adi}</div>", unsafe_allow_html=True)

# ==============================================================================
# SAYFA 1: ANA KARŞILAMA EKRANI (EĞİTİM TEMALI)
# ==============================================================================
def ana_karsilama_ekrani():
    st.markdown('<h1 class="neon-text" style="text-align:center; font-size:4.5rem; margin-bottom: 0px; color:#4f46e5;">Q Y V A M</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center; color:#64748b; font-family:\'Baloo 2\'; font-size: 1.2rem; font-weight: 600;">Bilişsel İklim ve Şahsiyet İnşası Serüveni</p><br>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        qyman_gorsel_yolu = "qyman.png" # veya qyman.jpg
        if os.path.exists(qyman_gorsel_yolu):
            st.image(qyman_gorsel_yolu, use_container_width=True)
            
        st.markdown("""
            <div class="qyman-hud" style="text-align: center;">
                <span class="system-log" style="font-size:1.2rem;">✨ Serüvene Hoş Geldin! ✨</span><br><br>
                <b>Ben Qyman, senin dijital rehberinim!</b><br>
                Gelişim haritamıza sol panelden ulaşabilirsin. Maceraya başlamak için aşağıdan kendi ismini seç ve <b>Bağlantıyı Başlat</b> butonuna tıkla!
            </div>
        """, unsafe_allow_html=True)
        
        cocuklar = cocuklari_getir()
        if not cocuklar:
            st.warning("⚠️ Sistemde henüz kayıtlı bir profil yok. Lütfen Yetkili Girişi'nden yeni bir isim ekleyin.")
        else:
            st.markdown('<div class="glass-box">', unsafe_allow_html=True)
            st.markdown('<h4 class="neon-text" style="text-align:center;">İsmini Seç ve Başla</h4></div>', unsafe_allow_html=True)
            secilen = st.selectbox("Profil Seçiniz", [c[1] for c in cocuklar], label_visibility="collapsed")
            if st.button("🚀 Bağlantıyı Başlat"):
                st.session_state.aktif_cocuk_isim = secilen
                st.session_state.aktif_cocuk_id = next(c[0] for c in cocuklar if c[1] == secilen)
                st.session_state.aktif_sayfa = "Cocuk_Panel"
                st.rerun()
# ==============================================================================
# SAYFA 2: VELİ GÜVENLİK PROTOKOLÜ (PIN EKRANI)
# ==============================================================================
def veli_giris_ekrani():
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown('<div class="glass-box" style="text-align:center;">', unsafe_allow_html=True)
        st.markdown('<h2 class="neon-text">[ GÜVENLİK PROTOKOLÜ ]</h2>', unsafe_allow_html=True)
        st.markdown('<p style="color:#94a3b8;">Rehber yetkisine sahip olduğunuzu doğrulamak için PIN kodunu giriniz.</p></div>', unsafe_allow_html=True)
        
        pin_kodu = st.text_input("YETKİLİ PIN KODU:", type="password", placeholder="[ Varsayılan: 1234 ]")
        if st.button("[ BAĞLANTIYI ONAYLA ]"):
            if pin_kodu == "1234":
                st.session_state.veli_yetkili = True
                st.session_state.aktif_sayfa = "Veli_Panel"
                st.rerun()
            else:
                st.error("[ ERİŞİM REDDEDİLDİ ]: Geçersiz Kimlik Doğrulaması.")

# ==============================================================================
# SAYFA 3: VELİ / REHBER YÖNETİM PANELİ
# ==============================================================================
def veli_panel_ekrani():
    if not st.session_state.get("veli_yetkili", False):
        st.error("Bu alana erişim yetkiniz yok.")
        if st.button("Geri Dön"): st.session_state.aktif_sayfa = "Ana Sayfa"; st.rerun()
        return

    st.markdown('<h1 class="neon-text">REHBERLİK KÖŞESİ</h1><hr>', unsafe_allow_html=True)
    
    st.markdown("""
        <style>
        button[data-baseweb="tab"] { transition: all 0.3s ease !important; border-radius: 8px 8px 0 0 !important; }
        button[data-baseweb="tab"]:hover { transform: translateY(-3px); background-color: #e0e7ff; color: #4f46e5; }
        </style>
    """, unsafe_allow_html=True)

    t1, t2, t3, t4, t5, t6 = st.tabs(["Gözlem ve Onay", "Serbest Rapor (Word)", "Gelişim Matrisi", "Özel Berat Tasarla", "Sisteme Kayıt", "Qyvam AI Pedagog"])

    with t1:
        st.markdown('<div class="glass-box"><h3>Bekleyen Gözlemler</h3><p style="color:#64748b;">Çocukların gönderdiği görevleri buradan onaylayıp onlara Word raporu oluşturabilirsiniz.</p></div>', unsafe_allow_html=True)
        bekleyenler = onay_bekleyenleri_getir()
        
        if not bekleyenler:
            st.info("Şu an onay bekleyen bir görev bulunmamaktadır.")
        else:
            for kayit in bekleyenler:
                islem_id = kayit[0]
                c_id = kayit[1]
                gorev_adi = kayit[2]
                cevap = kayit[3]
                tarih = kayit[-1] if len(kayit) > 4 else "Tarih Yok"
                
                bilgi = cocuk_bilgisi_getir(c_id)
                if not bilgi: continue
                cocuk_isim, mevcut_adim = bilgi
                
                with st.expander(f"📌 {cocuk_isim} - {gorev_adi} ({tarih})", expanded=True):
                    st.write(f"**Çocuğun İfadesi:** {cevap}")
                    
                    yuklenen_foto = st.file_uploader(f"Kanıt Fotoğrafı Yükle ({cocuk_isim})", type=['png', 'jpg', 'jpeg'], key=f"foto_{islem_id}")
                    veli_degerlendirmesi = st.text_area("Rehber Notunuzu Ekleyin:", key=f"not_{islem_id}")
                    
                    col_onay, col_word = st.columns(2)
                    with col_onay:
                        if st.button("✅ Görevi Onayla", key=f"btn_onay_{islem_id}"):
                            veri_onayla(islem_id)
                            st.success(f"{cocuk_isim} için görev onaylandı!")
                            st.rerun()
                            
                    with col_word:
                        if yuklenen_foto and veli_degerlendirmesi:
                            foto_bytes = yuklenen_foto.getvalue()
                            word_dosyasi = word_raporu_olustur(cocuk_isim, gorev_adi, veli_degerlendirmesi, foto_bytes)
                            st.download_button(
                                label="📄 Fotoğraflı Word Raporunu İndir",
                                data=word_dosyasi,
                                file_name=f"{cocuk_isim}_Gorev_Raporu.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                key=f"dl_{islem_id}"
                            )
                        else:
                            st.caption("Word çıktısı almak için fotoğraf yükleyip not yazın.")

    with t2:
        st.markdown('<div class="glass-box"><h3>Serbest Fotoğraflı Rapor Al</h3><p style="color:#64748b;">Çocuğun onay göndermesini beklemeden, dilediğiniz zaman bir faaliyeti Word olarak belgeleyin.</p></div>', unsafe_allow_html=True)
        cocuklar = cocuklari_getir()
        if not cocuklar:
            st.warning("Önce 'Sisteme Kayıt' sekmesinden bir çocuk eklemelisiniz.")
        else:
            secilen_cocuk = st.selectbox("Raporlanacak Çocuğu Seçin:", [c[1] for c in cocuklar])
            serbest_gorev_adi = st.text_input("Faaliyet/Görev Adı:", placeholder="Örn: Kendi Yatağını Toplama")
            serbest_veli_notu = st.text_area("Gözlem Notunuz:", placeholder="Bugün yatağını çok güzel topladı ve odasını havalandırdı...")
            serbest_foto = st.file_uploader("Görsel Kanıt Yükle:", type=['png', 'jpg', 'jpeg'], key="serbest_foto")
            
            if serbest_foto and serbest_veli_notu and serbest_gorev_adi:
                foto_b = serbest_foto.getvalue()
                s_word_dosyasi = word_raporu_olustur(secilen_cocuk, serbest_gorev_adi, serbest_veli_notu, foto_b)
                st.download_button(
                    label="📄 Serbest Raporu Word Olarak İndir",
                    data=s_word_dosyasi,
                    file_name=f"{secilen_cocuk}_Serbest_Rapor.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="dl_serbest"
                )

    with t3:
        st.markdown('<div class="glass-box"><h3>Gelişim Matrisi ve Görev Atama</h3><p style="color:#64748b;">Çocukların ilerleyişini takip edebilir ve müfredattaki seviyeleri manuel olarak atayabilirsiniz.</p></div>', unsafe_allow_html=True)
        
        cocuklar = cocuklari_getir()
        
        # --- 1. KISIM: MEVCUT DURUM ---
        st.markdown("#### 📊 Mevcut İlerleme Durumları")
        for cid, isim, adim in cocuklar:
            ilerleme = int((adim / max(MUFREDAT.keys())) * 100) if MUFREDAT else 0
            st.markdown(f"**{isim}** - Aşama {adim} ({ilerleme}%)")
            st.progress(ilerleme)
            
        st.markdown("<hr style='border-color: #e2e8f0;'>", unsafe_allow_html=True)
        
        # --- 2. KISIM: MANUEL GÖREV ATAMA ---
        st.markdown("#### 🎯 Yeni Görev / Aşama Ata")
        if not cocuklar:
            st.warning("Önce sisteme bir çocuk eklemelisiniz.")
        else:
            col_cocuk, col_gorev = st.columns(2)
            with col_cocuk:
                secilen_cocuk_isim_g = st.selectbox("Görev Atanacak Çocuk:", [c[1] for c in cocuklar], key="g_ata_isim")
                secilen_id_g = next(c[0] for c in cocuklar if c[1] == secilen_cocuk_isim_g)
                
            with col_gorev:
                # Müfredattaki tüm faz ve seviyeleri listeleme
                mufredat_secenekleri = [f"Adım {a}: {i['faz']} ➔ {i['alt_seviye']}" for a, i in MUFREDAT.items()]
                secilen_mufredat_metin = st.selectbox("Atanacak Aşama:", mufredat_secenekleri)
                yeni_adim_no = int(secilen_mufredat_metin.split(":")[0].replace("Adım ", ""))
                
            # Seçilen görevin Veliye Önizlemesi (Ne atadığını görmesi için)
            secilen_icerik = MUFREDAT[yeni_adim_no]
            st.info(f"**📌 Çocuğa Gidecek Görev:** {secilen_icerik['varsayilan_gorev']}\n\n**🤔 Tefekkür Sorusu:** {secilen_icerik['varsayilan_tefekkur']}")
            
            if st.button("🚀 Bu Görevi Çocuğa Ata"):
                cocuk_adim_guncelle(secilen_id_g, yeni_adim_no)
                st.success(f"Harika! '{secilen_cocuk_isim_g}' artık Adım {yeni_adim_no} seviyesinde. Çocuk paneline girdiğinde bu yeni görevi görecek.")
                st.rerun()

    with t4:
        st.markdown('<div class="glass-box"><h3>Özel Berat / Sertifika Tasarla</h3><p style="color:#64748b;">Oluşturduğunuz berat doğrudan çocuğun dijital profiline kaydedilir.</p></div>', unsafe_allow_html=True)
        cocuklar = cocuklari_getir()
        if not cocuklar:
            st.warning("Önce 'Sisteme Kayıt' sekmesinden bir çocuk eklemelisiniz.")
        else:
            secilen_isim = st.selectbox("Beratı Kazanacak Çocuğu Seçin:", [c[1] for c in cocuklar])
            secilen_id = next(c[0] for c in cocuklar if c[1] == secilen_isim)
            
            berat_adi = st.text_input("Beratın Adı:", placeholder="Örn: Cesur Kaşif Beratı")
            berat_aciklamasi = st.text_area("Açıklaması / Veriliş Nedeni:", placeholder="Örn: Odanı kendi başına düzenleme sorumluluğunu aldığın için...")
            
            if st.button("🎉 Beratı Çocuğun Profiline Ekle"):
                if berat_adi and berat_aciklamasi:
                    ozel_berat_ekle(secilen_id, berat_adi, berat_aciklamasi)
                    st.success(f"Harika! '{berat_adi}' başarıyla {secilen_isim} isimli çocuğun profiline eklendi.")
                else:
                    st.error("Lütfen berat adını ve açıklamasını boş bırakmayın.")

    with t5:
        st.markdown('<div class="glass-box"><h3>Sistem Kayıt Yönetimi</h3><p style="color:#64748b;">Yeni profil ekleyebilir veya mevcut profilleri sistemden tamamen silebilirsiniz.</p></div>', unsafe_allow_html=True)
        
        col_ekle, col_cikar = st.columns(2)
        
        with col_ekle:
            st.markdown("#### ➕ Yeni Profil Ekle")
            yeni_isim = st.text_input("Çocuğun İsmi:")
            if st.button("Sisteme Ekle"):
                if yeni_isim.strip() != "":
                    cocuk_ekle(yeni_isim.strip())
                    st.success(f"{yeni_isim} başarıyla eklendi!")
                    st.rerun()
                else:
                    st.error("Lütfen geçerli bir isim girin.")
                    
        with col_cikar:
            st.markdown("#### 🗑️ Profil Sil (Çıkar)")
            cocuklar = cocuklari_getir()
            if not cocuklar:
                st.info("Sistemde silinecek kayıt yok.")
            else:
                silinecek_isim = st.selectbox("Silinecek Çocuğu Seçin:", [c[1] for c in cocuklar])
                silinecek_id = next(c[0] for c in cocuklar if c[1] == silinecek_isim)
                
                st.warning("⚠️ Dikkat: Bu işlem çocuğun tüm geçmişini ve beratlarını da silecektir.")
                if st.button("❌ Seçili Profili Tamamen Sil"):
                    cocuk_sil(silinecek_id)
                    st.success(f"'{silinecek_isim}' ve tüm verileri sistemden başarıyla silindi.")
                    
                    # Eğer silinen çocuk şu an aktif olarak seçiliyse, oturumunu temizle
                    if st.session_state.get("aktif_cocuk_id") == silinecek_id:
                        st.session_state.aktif_cocuk_id = None
                        st.session_state.aktif_cocuk_isim = ""
                        
                    st.rerun()

    with t6:
        st.markdown('<div class="glass-box"><h3>Qyvam AI Pedagog</h3><p style="color:#64748b;">Rehberlik sürecinde yapay zekaya danışın. Eğitim tavsiyeleri alın.</p></div>', unsafe_allow_html=True)
        veli_sorusu = st.text_area("Pedagojik Danışmanınıza Sorun:", placeholder="Örn: Çocuğum bu aşamada ödev yapmak istemiyor, nasıl bir dil kullanmalıyım?")
        if st.button("🤖 Danış"):
            if veli_sorusu:
                with st.spinner("Qyvam Pedagog analiz ediyor..."):
                    yanit = ai_cevap_uret(veli_sorusu, 1, rol="veli")
                st.info(yanit)

# ==============================================================================
# SAYFA 4: ÇOCUK (DİJİTAL İKİZ) VERİ GİRİŞ PANELİ
# ==============================================================================
def cocuk_panel_ekrani():
    if not st.session_state.aktif_cocuk_id:
        st.session_state.aktif_sayfa = "Ana Sayfa"
        st.rerun()
        
    bilgi = cocuk_bilgisi_getir(st.session_state.aktif_cocuk_id)
    if not bilgi: return
    isim, mevcut_adim = bilgi
    adim_bilgisi = MUFREDAT.get(mevcut_adim, {"faz": "Zirve", "ust_seviye": "Tamamlandı", "alt_seviye": "Tebrikler", "varsayilan_gorev": "Tüm adımları başarıyla tamamladın.", "varsayilan_tefekkur": "Bu yolculuk sana ne kattı?"})
    
    st.markdown(f'<h1 class="neon-text" style="font-size: 2.5rem;">Hoş Geldin, {isim.title()}!</h1><hr>', unsafe_allow_html=True)
    
    saat = datetime.now().hour
    if saat < 12: qyman_mesaj = "Günaydın! Yeni güne harika bir görevle başlamaya hazır mısın?"
    elif saat < 18: qyman_mesaj = "Merhaba! Günün görevini tamamlayıp yıldızları toplamaya ne dersin?"
    else: qyman_mesaj = "İyi akşamlar! Uyku moduna geçmeden bugünün görevini sisteme ekleyelim."

    col_img, col_hud = st.columns([1, 4])
    with col_img:
        qyman_gorsel_yolu = "qyman.png"
        if os.path.exists(qyman_gorsel_yolu): st.image(qyman_gorsel_yolu, use_container_width=True)
    with col_hud:
        st.markdown(f"""
            <div class="qyman-hud" style="margin-top:0; font-size: 1.2rem;">
                <b>🤖 Qyman Diyor ki:</b><br>{qyman_mesaj}
            </div>
        """, unsafe_allow_html=True)

    # Çocuklar için sekmeleri daha anlaşılır ikonlu ve net metinlere dönüştürdük
    t1, t2, t3 = st.tabs(["📍 Bugünün Görevi", "🏆 Kazandığım Beratlar", "💬 Qyman'a Soru Sor"])

    with t1:
        if bekleyen_gorev_kontrol(st.session_state.aktif_cocuk_id):
            st.markdown('<div class="glass-box"><h3 class="neon-text" style="color:#fca5a5;">Görev Onay Bekliyor ⏳</h3><p style="color:#94a3b8; font-size:1.1rem;">Görevini rehberine (veline) gönderdik. O onayladığında yeni görevine geçebilirsin!</p></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'''
            <div class="glass-box">
                <p style="color:#94a3b8; font-size:1.1rem; margin-bottom:5px;">Aşama {mevcut_adim} : {adim_bilgisi["alt_seviye"]}</p>
                <h2 class="neon-text" style="margin-top:0;">{adim_bilgisi["varsayilan_gorev"]}</h2>
                <hr style="border-color: rgba(56, 189, 248, 0.2);">
                <h4 style="color:#10b981;">Düşünme Vakti: {adim_bilgisi["varsayilan_tefekkur"]}</h4>
            </div>
            ''', unsafe_allow_html=True)
            
            cocuk_cevabi = st.text_area("Cevabını Buraya Yazabilirsin:", placeholder="Neler hissettin? Düşüncelerini buraya yaz...", height=100)
            if st.button("✨ Görevimi Tamamladım, Gönder!"):
                if cocuk_cevabi.strip() == "": st.error("Lütfen göndermeden önce kutuya birkaç cümle yaz.")
                else:
                    g_adi = f"[ ADIM {mevcut_adim} ]: {adim_bilgisi['alt_seviye']}"
                    cocuk_veri_gonder(st.session_state.aktif_cocuk_id, g_adi, cocuk_cevabi)
                    st.success("Tebrikler! Cevabın başarıyla gönderildi.")
                    st.rerun()
            
    with t2:
        st.markdown('<div class="glass-box"><h3>Kazandığın Başarı Beratları</h3></div>', unsafe_allow_html=True)
        sertifikalar = kazanilan_sertifikalari_hesapla(mevcut_adim)
        if not sertifikalar:
            st.info("Henüz bir berat kazanmadın. Görevleri tamamladıkça burası dolacak!")
        for s_adi, s_aciklama in sertifikalar:
            st.markdown(f'<div class="glass-task" style="border-left-color: #d946ef;"><h3 style="color: #f0abfc; margin:0;">{s_adi}</h3><p style="color: #e2e8f0;">{s_aciklama}</p></div>', unsafe_allow_html=True)

    with t3:
        st.markdown('<div class="glass-box"><h3>Qyman ile Konuş</h3><p style="color:#94a3b8;">Görevle ilgili yardıma ihtiyacın varsa Qyman\'a sorabilirsin.</p></div>', unsafe_allow_html=True)
        cocuk_sorusu = st.text_input("Sorunu Buraya Yaz:", placeholder="Örn: Bu görevi yaparken zorlandım, bana ipucu verir misin?")
        if st.button("🤖 Qyman'a Gönder"):
            if cocuk_sorusu:
                with st.spinner("Qyman düşünüyor..."):
                    yanit = ai_cevap_uret(cocuk_sorusu, mevcut_adim, rol="cocuk", cocuk_isim=isim)
                st.success(yanit)
# ==============================================================================
# ROUTER
# ==============================================================================
ust_komuta_merkezi()
sol_radar_olustur()

if st.session_state.aktif_sayfa == "Ana Sayfa": ana_karsilama_ekrani()
elif st.session_state.aktif_sayfa == "Veli_Giris": veli_giris_ekrani()
elif st.session_state.aktif_sayfa == "Veli_Panel": veli_panel_ekrani()
elif st.session_state.aktif_sayfa == "Cocuk_Panel": cocuk_panel_ekrani()
