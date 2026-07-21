import streamlit as st
import sqlite3
import io
import os
import pytz
import random
from datetime import datetime
from docx import Document
from docx.shared import Inches

# ==============================================================================
# SİSTEM AYARLARI VE GİZLİ KASA
# ==============================================================================
st.set_page_config(page_title="Qyvam | Siber Uzay", layout="wide", initial_sidebar_state="expanded")

try:
    from openai import OpenAI
    OPENROUTER_KEY = st.secrets["OPENROUTER_KEY"]
except:
    OPENROUTER_KEY = ""

try:
    from mufredat import MUFREDAT
except ImportError:
    MUFREDAT = {}

DB_YOLU = 'qyvam_siber.db'

# Yeni Çoklu Kullanıcı Session Ayarları
if 'aktif_sayfa' not in st.session_state: st.session_state.aktif_sayfa = "Ana Sayfa"
if 'veli_kadi' not in st.session_state: st.session_state.veli_kadi = None
if 'aktif_cocuk_id' not in st.session_state: st.session_state.aktif_cocuk_id = None
if 'aktif_cocuk_isim' not in st.session_state: st.session_state.aktif_cocuk_isim = ""

# ==============================================================================
# VERİTABANI MOTORU (ÇOKLU KULLANICI DESTEKLİ)
# ==============================================================================
def init_db():
    conn = sqlite3.connect(DB_YOLU)
    c = conn.cursor()
    # Veliler Tablosu
    c.execute('''CREATE TABLE IF NOT EXISTS Veliler (kullanici_adi TEXT PRIMARY KEY, sifre TEXT)''')
    # Çocuklar Tablosu (veli_kadi eklendi)
    c.execute('''CREATE TABLE IF NOT EXISTS Cocuklar (id INTEGER PRIMARY KEY AUTOINCREMENT, isim TEXT, mevcut_adim INTEGER, veli_kadi TEXT)''')
    
    # Eski sistemden gelenler için tabloyu güvenli bir şekilde günceller
    try:
        c.execute("ALTER TABLE Cocuklar ADD COLUMN veli_kadi TEXT DEFAULT 'Kurucu'")
    except:
        pass
        
    c.execute('''CREATE TABLE IF NOT EXISTS Gorevler (id INTEGER PRIMARY KEY AUTOINCREMENT, cocuk_id INTEGER, gorev_adi TEXT, tefekkur TEXT, durum TEXT, puan INTEGER, veli_notu TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ozel_beratlar (id INTEGER PRIMARY KEY AUTOINCREMENT, cocuk_id INTEGER, berat_adi TEXT, berat_aciklama TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- Veli Kayıt ve Giriş Fonksiyonları ---
def veli_kaydol(kadi, sifre):
    conn = sqlite3.connect(DB_YOLU)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO Veliler (kullanici_adi, sifre) VALUES (?, ?)", (kadi, sifre))
        conn.commit()
        basari = True
    except:
        basari = False # Kullanıcı adı zaten sistemde var
    conn.close()
    return basari

def veli_giris_yap(kadi, sifre):
    conn = sqlite3.connect(DB_YOLU)
    c = conn.cursor()
    c.execute("SELECT * FROM Veliler WHERE kullanici_adi=? AND sifre=?", (kadi, sifre))
    kullanici = c.fetchone()
    conn.close()
    return kullanici is not None

# --- Veri Çekme Fonksiyonları (Veliye Özel Filtreli) ---
def cocuk_ekle(isim, veli_kadi):
    conn = sqlite3.connect(DB_YOLU)
    c = conn.cursor()
    c.execute("INSERT INTO Cocuklar (isim, mevcut_adim, veli_kadi) VALUES (?, ?, ?)", (isim, 1, veli_kadi))
    conn.commit()
    conn.close()

def cocuk_sil(cocuk_id):
    conn = sqlite3.connect(DB_YOLU)
    c = conn.cursor()
    c.execute("DELETE FROM Cocuklar WHERE id = ?", (cocuk_id,))
    c.execute("DELETE FROM Gorevler WHERE cocuk_id = ?", (cocuk_id,))
    c.execute("DELETE FROM ozel_beratlar WHERE cocuk_id = ?", (cocuk_id,))
    conn.commit()
    conn.close()

def cocuk_adim_guncelle(cocuk_id, yeni_adim):
    conn = sqlite3.connect(DB_YOLU)
    c = conn.cursor()
    c.execute("UPDATE Cocuklar SET mevcut_adim = ? WHERE id = ?", (yeni_adim, cocuk_id))
    conn.commit()
    conn.close()

def cocuklari_getir(veli_kadi):
    conn = sqlite3.connect(DB_YOLU)
    c = conn.cursor()
    c.execute("SELECT id, isim, mevcut_adim FROM Cocuklar WHERE veli_kadi=?", (veli_kadi,))
    data = c.fetchall()
    conn.close()
    return data

def tum_cocuklari_getir():
    conn = sqlite3.connect(DB_YOLU)
    c = conn.cursor()
    c.execute("SELECT id, isim, veli_kadi FROM Cocuklar")
    data = c.fetchall()
    conn.close()
    return data

def cocuk_bilgisi_getir(cocuk_id):
    conn = sqlite3.connect(DB_YOLU)
    imlec = conn.cursor()
    imlec.execute('SELECT isim, mevcut_adim FROM Cocuklar WHERE id = ?', (cocuk_id,))
    sonuc = imlec.fetchone()
    conn.close()
    return sonuc

def onay_bekleyenleri_getir(veli_kadi):
    conn = sqlite3.connect(DB_YOLU)
    imlec = conn.cursor()
    imlec.execute('''
        SELECT G.id, C.isim, G.gorev_adi, G.tefekkur, C.id, C.mevcut_adim 
        FROM Gorevler G 
        JOIN Cocuklar C ON G.cocuk_id = C.id 
        WHERE G.durum = 'Veli Onayı Bekliyor' AND C.veli_kadi = ?
    ''', (veli_kadi,))
    liste = imlec.fetchall()
    conn.close()
    return liste

def ozel_beratlari_getir(cocuk_id):
    conn = sqlite3.connect(DB_YOLU)
    c = conn.cursor()
    c.execute("SELECT berat_adi, berat_aciklama FROM ozel_beratlar WHERE cocuk_id=?", (cocuk_id,))
    veriler = c.fetchall()
    conn.close()
    return veriler

def ozel_berat_ekle(cocuk_id, berat_adi, berat_aciklama):
    conn = sqlite3.connect(DB_YOLU)
    c = conn.cursor()
    c.execute("INSERT INTO ozel_beratlar (cocuk_id, berat_adi, berat_aciklama) VALUES (?, ?, ?)", (cocuk_id, berat_adi, berat_aciklama))
    conn.commit()
    conn.close()

def bekleyen_gorev_kontrol(cocuk_id):
    conn = sqlite3.connect(DB_YOLU)
    imlec = conn.cursor()
    imlec.execute("SELECT id FROM Gorevler WHERE cocuk_id=? AND durum='Veli Onayı Bekliyor'", (cocuk_id,))
    sonuc = imlec.fetchone()
    conn.close()
    return sonuc is not None

def cocuk_veri_gonder(cocuk_id, gorev_adi, tefekkur_cevabi):
    conn = sqlite3.connect(DB_YOLU)
    imlec = conn.cursor()
    imlec.execute("INSERT INTO Gorevler (cocuk_id, gorev_adi, tefekkur, durum) VALUES (?, ?, ?, 'Veli Onayı Bekliyor')", (cocuk_id, gorev_adi, tefekkur_cevabi))
    conn.commit()
    conn.close()

def veri_onayla(islem_id, cocuk_id):
    conn = sqlite3.connect(DB_YOLU)
    imlec = conn.cursor()
    imlec.execute("UPDATE Gorevler SET durum = 'Onaylandı' WHERE id = ?", (islem_id,))
    imlec.execute("UPDATE Cocuklar SET mevcut_adim = mevcut_adim + 1 WHERE id = ?", (cocuk_id,))
    conn.commit()
    conn.close()

# ==============================================================================
# YARDIMCI FONKSİYONLAR
# ==============================================================================
def kazanilan_sertifikalari_hesapla(adim):
    sertifikalar = []
    if adim > 14: sertifikalar.append(("[ KÖKLER YETKİNLİK BERATI ]", "Bedenine ve mekanına gösterdiği irade ile kazanılmıştır."))
    if adim > 28: sertifikalar.append(("[ BAĞLAR YETKİNLİK BERATI ]", "Ailesine ve çevresine gösterdiği ikram bilinciyle kazanılmıştır."))
    if adim > 42: sertifikalar.append(("[ PUSULA YETKİNLİK BERATI ]", "Zaman ve dijital irade yönetimindeki kararlılığıyla kazanılmıştır."))
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
        doc.add_picture(foto_io, width=Inches(5.0))
    byte_io = io.BytesIO()
    doc.save(byte_io)
    byte_io.seek(0)
    return byte_io

# ==============================================================================
# AI MOTORU
# ==============================================================================
def ai_cevap_uret(soru, mevcut_adim, rol="veli", cocuk_isim=""):
    if not OPENROUTER_KEY:
        return "[ SİSTEM UYARISI ]: API Anahtarı bulunamadı. Yapay zeka çevrimdışı."
    faz = MUFREDAT.get(mevcut_adim, {}).get("faz", "Bilinmeyen Faz")
    if rol == "veli":
        prompt = f"Sen Qyvam adında uzman bir pedagojik asistansın. Çocuğun mevcut aşaması: {faz}. Soru: {soru}"
    else:
        prompt = f"Senin adın Qyman. Karşındaki arkadaşının adı {cocuk_isim}. Cümlelerin kısa, cesaretlendirici olsun. Gelişim aşaması: {faz}. Soru: {soru}"
    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
        response = client.chat.completions.create(model="deepseek/deepseek-v4-flash", messages=[{"role": "user", "content": prompt}])
        return response.choices[0].message.content
    except Exception as e:
        return f"[ SİSTEM HATASI ]: Bağlantı kurulamadı. Detay: {str(e)}"

# ==============================================================================
# ARAYÜZ TASARIMI (CSS)
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Baloo+2:wght@500;600;700&family=Nunito:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Nunito', sans-serif; background-color: #f0f4f8 !important; color: #334155 !important; }
    h1, h2, h3, h4, h5 { font-family: 'Baloo 2', sans-serif; font-weight: 700; color: #4f46e5 !important; }
    .glass-box { background: #ffffff; border: 2px solid #e0e7ff; border-radius: 16px; padding: 25px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(99, 102, 241, 0.05); }
    .glass-task { background: #fdf2f8; border-left: 5px solid #f472b6; border-radius: 12px; padding: 20px; margin-bottom: 15px; }
    .top-bar { background: #ffffff; border-bottom: 3px solid #e0e7ff; padding: 15px; margin-top: -50px; margin-bottom: 30px; border-radius: 0 0 20px 20px; }
    .qyman-hud { background: #eff6ff; border-left: 5px solid #3b82f6; border-radius: 12px; padding: 20px; font-family: 'Nunito', sans-serif; color: #1e3a8a; line-height: 1.6; margin-bottom: 20px; }
    .neon-text { color: #4f46e5 !important; text-shadow: none; font-weight: 700; }
    .stButton>button { border-radius: 12px; font-family: 'Baloo 2', sans-serif; font-size: 1.1rem !important; font-weight: 700; border: none; background-color: #6366f1; color: white !important; transition: all 0.3s ease; width: 100%; box-shadow: 0 4px 6px rgba(99, 102, 241, 0.25); }
    .stButton>button:hover { background-color: #4f46e5; transform: translateY(-2px); box-shadow: 0 6px 12px rgba(99, 102, 241, 0.35); }
    .hero-title { text-align: center; font-size: 4.5rem; color: #4f46e5; margin-bottom: 0; font-family: 'Baloo 2', sans-serif; font-weight: 800; }
    .hero-subtitle { text-align: center; color: #64748b; font-size: 1.2rem; font-weight: 600; margin-bottom: 25px; }
    .login-console { background: #ffffff; border: 2px solid #e0e7ff; border-radius: 20px; padding: 35px; margin-top: 15px; }
    .login-header { text-align:center; color:#4f46e5; margin-bottom:20px; font-family: 'Baloo 2', sans-serif; font-weight: 700; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# ÜST DURUM ÇUBUĞU
# ==============================================================================
def ust_komuta_merkezi():
    st.markdown('<div class="top-bar"></div>', unsafe_allow_html=True)
    col_sol, col_orta, col_sag = st.columns([3, 1, 4])
    
    with col_sol:
        durum_metni = "ANA SAYFA" if st.session_state.aktif_sayfa == "Ana Sayfa" else "REHBERLİK KÖŞESİ" if st.session_state.aktif_sayfa == "Veli_Panel" else "GELİŞİM YOLCULUĞU"
        st.markdown(f'<div style="color: #64748b; font-weight: 600;">Qyvam Eğitim Sistemi > <b style="color: #4f46e5;">{durum_metni}</b></div>', unsafe_allow_html=True)
        
    with col_orta:
        if st.session_state.aktif_sayfa == "Ana Sayfa" or st.session_state.aktif_sayfa == "Cocuk_Panel":
            if st.button("Rehber Girişi"): 
                st.session_state.aktif_sayfa = "Veli_Giris" 
                st.rerun()
        else:
            if st.button("Ana Sayfaya Dön"):
                st.session_state.aktif_sayfa = "Ana Sayfa"
                st.session_state.veli_kadi = None
                st.session_state.aktif_cocuk_id = None
                st.rerun()
                
    with col_sag:
        tz = pytz.timezone('Europe/Istanbul')
        simdi = datetime.now(tz)
        st.markdown(f'<div style="text-align: right; color: #0284c7; font-weight: 700;">{simdi.strftime("%d.%m.%Y | %H:%M")}</div>', unsafe_allow_html=True)
        st.markdown('<hr style="border-color: rgba(99, 102, 241, 0.2); margin-top: 15px;">', unsafe_allow_html=True)

# ==============================================================================
# SAYFA 1: ANA KARŞILAMA EKRANI (RASTGELE ANİMASYONLU)
# ==============================================================================
def ana_karsilama_ekrani():
    st.markdown('<div class="hero-title">Q Y V A M</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">Bilişsel İklim ve Şahsiyet İnşası Serüveni</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        # Klasördeki "qyman" kelimesiyle başlayan tüm MP4 videolarını bulur
        mevcut_videolar = [dosya for dosya in os.listdir() if dosya.startswith("qyman") and dosya.endswith(".mp4")]
        if mevcut_videolar:
            secilen_video = random.choice(mevcut_videolar)
            st.video(secilen_video, autoplay=True, loop=True, muted=True)
        elif os.path.exists("qyman.gif"):
            st.image("qyman.gif", use_container_width=True)
        elif os.path.exists("qyman.png"):
            st.image("qyman.png", use_container_width=True)
            
        st.markdown("""
            <div class="qyman-hud" style="text-align: center; margin-top: -15px; position: relative; z-index: 10;">
                <span style="font-size:1.2rem; font-weight:700; color:#8b5cf6;">✨ Sisteme Hoş Geldin! ✨</span><br><br>
                <b>Ben Qyman, senin dijital rehberinim.</b><br>
                Maceraya başlamak için aşağıdan profilini seç ve bağlantıyı kur.
            </div>
        """, unsafe_allow_html=True)
        
        cocuklar = tum_cocuklari_getir()
        if not cocuklar:
            st.warning("⚠️ Sistemde henüz kayıtlı bir profil yok. Lütfen 'Rehber Girişi' yaparak yeni bir hesap açın ve çocuğunuzu ekleyin.")
        else:
            st.markdown('<div class="login-console">', unsafe_allow_html=True)
            st.markdown('<div class="login-header">[ BAĞLANTI MODÜLÜ ]</div>', unsafe_allow_html=True)
            
            # Çocukları ve onlara ait velileri listede gösteriyoruz
            secenekler = [f"{c[1]} (Rehber: {c[2]})" for c in cocuklar]
            secilen_metin = st.selectbox("Kayıtlı Profiliniz:", secenekler, label_visibility="collapsed")
            
            st.markdown('<br>', unsafe_allow_html=True)
            if st.button("🚀 SİBER UZAYA BAĞLAN", use_container_width=True):
                secilen_index = secenekler.index(secilen_metin)
                st.session_state.aktif_cocuk_id = cocuklar[secilen_index][0]
                st.session_state.aktif_cocuk_isim = cocuklar[secilen_index][1]
                st.session_state.aktif_sayfa = "Cocuk_Panel"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

# ==============================================================================
# SAYFA 2: VELİ GÜVENLİK PROTOKOLÜ (KAYIT & GİRİŞ)
# ==============================================================================
def veli_giris_ekrani():
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown('<div class="glass-box" style="text-align:center;">', unsafe_allow_html=True)
        st.markdown('<h2 class="neon-text">[ REHBER PORTALI ]</h2>', unsafe_allow_html=True)
        st.markdown('<p style="color:#94a3b8;">Sisteme giriş yapın veya yeni bir rehber hesabı oluşturun.</p></div>', unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["🔑 Giriş Yap", "📝 Yeni Kayıt Ol"])
        
        with tab1:
            g_kadi = st.text_input("Kullanıcı Adı (Giriş):")
            g_sifre = st.text_input("Şifre (Giriş):", type="password")
            if st.button("🚀 Giriş Yap"):
                if veli_giris_yap(g_kadi, g_sifre):
                    st.session_state.veli_kadi = g_kadi
                    st.session_state.aktif_sayfa = "Veli_Panel"
                    st.rerun()
                else:
                    st.error("Hatalı kullanıcı adı veya şifre!")
                    
        with tab2:
            k_kadi = st.text_input("Yeni Kullanıcı Adı:")
            k_sifre = st.text_input("Yeni Şifre:", type="password")
            if st.button("💾 Hesabı Oluştur"):
                if k_kadi and k_sifre:
                    if veli_kaydol(k_kadi, k_sifre):
                        st.success("Hesabınız başarıyla oluşturuldu! Şimdi sol taraftaki 'Giriş Yap' sekmesinden sisteme girebilirsiniz.")
                    else:
                        st.error("Bu kullanıcı adı zaten alınmış, lütfen başka bir tane seçin.")
                else:
                    st.warning("Kullanıcı adı ve şifre boş bırakılamaz.")

# ==============================================================================
# SAYFA 3: VELİ / REHBER YÖNETİM PANELİ (FİLTRELİ)
# ==============================================================================
def veli_panel_ekrani():
    if not st.session_state.get("veli_kadi"):
        st.error("Lütfen önce giriş yapın.")
        if st.button("Geri Dön"): st.session_state.aktif_sayfa = "Ana Sayfa"; st.rerun()
        return

    st.markdown(f'<h1 class="neon-text">REHBERLİK KÖŞESİ (Hoş Geldiniz, {st.session_state.veli_kadi})</h1><hr>', unsafe_allow_html=True)
    t1, t2, t3, t4, t5, t6 = st.tabs(["Gözlem ve Onay", "Serbest Rapor", "Gelişim Matrisi", "Özel Berat Tasarla", "Sisteme Kayıt", "AI Pedagog"])

    with t1:
        st.markdown('<div class="glass-box"><h3>Bekleyen Gözlemler</h3></div>', unsafe_allow_html=True)
        bekleyenler = onay_bekleyenleri_getir(st.session_state.veli_kadi)
        if not bekleyenler: st.info("Şu an onay bekleyen bir görev bulunmamaktadır.")
        
        for kayit in bekleyenler:
            with st.expander(f"📌 {kayit[1]} - {kayit[2]}", expanded=True):
                st.write(f"**Çocuğun İfadesi:** {kayit[3]}")
                if st.button("✅ Görevi Onayla", key=f"btn_onay_{kayit[0]}"):
                    veri_onayla(kayit[0], kayit[4])
                    st.rerun()

    with t2:
        st.markdown('<div class="glass-box"><h3>Serbest Rapor Al</h3></div>', unsafe_allow_html=True)
        cocuklar = cocuklari_getir(st.session_state.veli_kadi)
        if cocuklar:
            secilen_cocuk = st.selectbox("Raporlanacak Çocuk:", [c[1] for c in cocuklar])
            serbest_gorev_adi = st.text_input("Faaliyet Adı:")
            serbest_veli_notu = st.text_area("Gözlem Notunuz:")
            serbest_foto = st.file_uploader("Görsel Kanıt:", type=['png', 'jpg', 'jpeg'], key="serbest_foto")
            if st.button("Word Olarak İndir") and serbest_gorev_adi and serbest_veli_notu:
                foto_b = serbest_foto.getvalue() if serbest_foto else None
                s_word_dosyasi = word_raporu_olustur(secilen_cocuk, serbest_gorev_adi, serbest_veli_notu, foto_b)
                st.download_button(label="📄 İndir", data=s_word_dosyasi, file_name=f"{secilen_cocuk}_Rapor.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    with t3:
        st.markdown('<div class="glass-box"><h3>Gelişim Matrisi</h3></div>', unsafe_allow_html=True)
        cocuklar = cocuklari_getir(st.session_state.veli_kadi)
        for cid, isim, adim in cocuklar:
            st.markdown(f"**{isim}** - Aşama {adim}")
            st.progress(min(int((adim / 100) * 100), 100))

    with t4:
        st.markdown('<div class="glass-box"><h3>Özel Berat Tasarla</h3></div>', unsafe_allow_html=True)
        cocuklar = cocuklari_getir(st.session_state.veli_kadi)
        if cocuklar:
            BERAT_TEMALARI = {"1. Antik Parşömen": "#fefce8", "2. Siber Uzay": "#eff6ff", "3. Doğa": "#f0fdf4"}
            secilen_isim = st.selectbox("Berat Verilecek Çocuk:", [c[1] for c in cocuklar])
            secilen_id = next(c[0] for c in cocuklar if c[1] == secilen_isim)
            veli_isim = st.text_input("İmza İçin Adınız:")
            faz_adi = st.selectbox("Faz:", ["KÖKLER FAZI", "BAĞLAR FAZI", "ÖZEL BAŞARI BERATI"])
            
            if st.button("Beratı Profiline Ekle") and veli_isim:
                ozel_berat_ekle(secilen_id, faz_adi, "Veli tarafından özel tasarım berat takdim edildi.")
                st.success(f"Berat {secilen_isim} isimli çocuğun profiline başarıyla işlendi!")

    with t5:
        st.markdown('<div class="glass-box"><h3>Sistem Kayıt Yönetimi</h3></div>', unsafe_allow_html=True)
        yeni_isim = st.text_input("Çocuğun İsmi:")
        if st.button("Sisteme Ekle"):
            if yeni_isim.strip() != "":
                cocuk_ekle(yeni_isim.strip(), st.session_state.veli_kadi)
                st.success("Profil Eklendi!")
                st.rerun()
        
        cocuklar = cocuklari_getir(st.session_state.veli_kadi)
        if cocuklar:
            silinecek_isim = st.selectbox("Silinecek Çocuğu Seçin:", [c[1] for c in cocuklar])
            if st.button("❌ Seçili Profili Tamamen Sil"):
                silinecek_id = next(c[0] for c in cocuklar if c[1] == silinecek_isim)
                cocuk_sil(silinecek_id)
                st.rerun()

    with t6:
        st.markdown('<div class="glass-box"><h3>Qyvam AI Pedagog</h3></div>', unsafe_allow_html=True)
        veli_sorusu = st.text_area("Soru Sor:")
        if st.button("🤖 Danış"):
            st.info(ai_cevap_uret(veli_sorusu, 1, rol="veli"))

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
    
    st.markdown(f'<h1 class="neon-text" style="font-size: 2.5rem;">Hoş Geldin, {isim.title()}!</h1><hr>', unsafe_allow_html=True)
    
    col_img, col_hud = st.columns([1, 4])
    with col_img:
        mevcut_videolar = [dosya for dosya in os.listdir() if dosya.startswith("qyman") and dosya.endswith(".mp4")]
        if mevcut_videolar: st.video(random.choice(mevcut_videolar), autoplay=True, loop=True, muted=True)
        elif os.path.exists("qyman.png"): st.image("qyman.png")
            
    with col_hud:
        st.markdown(f'<div class="qyman-hud"><b>🤖 Qyman Diyor ki:</b><br>Harika bir görev seni bekliyor!</div>', unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["📍 Bugünün Görevi", "🏆 Kazandığım Beratlar", "💬 Qyman'a Soru Sor"])

    with t1:
        if bekleyen_gorev_kontrol(st.session_state.aktif_cocuk_id):
            st.markdown('<div class="glass-box"><h3 class="neon-text" style="color:#fca5a5;">Görev Onay Bekliyor ⏳</h3></div>', unsafe_allow_html=True)
        else:
            cocuk_cevabi = st.text_area("Cevabını Buraya Yazabilirsin:", height=100)
            if st.button("✨ Görevimi Tamamladım, Gönder!"):
                cocuk_veri_gonder(st.session_state.aktif_cocuk_id, f"ADIM {mevcut_adim}", cocuk_cevabi)
                st.rerun()
            
    with t2:
        st.markdown('<div class="glass-box"><h3>Kazandığın Başarı Beratları</h3></div>', unsafe_allow_html=True)
        tum_sertifikalar = (kazanilan_sertifikalari_hesapla(mevcut_adim) or []) + (ozel_beratlari_getir(st.session_state.aktif_cocuk_id) or [])
        for s_adi, s_aciklama in tum_sertifikalar:
            st.markdown(f'<div class="glass-task"><h3 style="color:#db2777;">🏆 {s_adi}</h3><p>{s_aciklama}</p></div>', unsafe_allow_html=True)

    with t3:
        st.markdown('<div class="glass-box"><h3>Qyman ile Konuş</h3></div>', unsafe_allow_html=True)
        cocuk_sorusu = st.text_input("Sorunu Yaz:")
        if st.button("🤖 Gönder"):
            st.success(ai_cevap_uret(cocuk_sorusu, mevcut_adim, rol="cocuk", cocuk_isim=isim))

# ==============================================================================
# ROUTER
# ==============================================================================
ust_komuta_merkezi()

if st.session_state.aktif_sayfa == "Ana Sayfa": ana_karsilama_ekrani()
elif st.session_state.aktif_sayfa == "Veli_Giris": veli_giris_ekrani()
elif st.session_state.aktif_sayfa == "Veli_Panel": veli_panel_ekrani()
elif st.session_state.aktif_sayfa == "Cocuk_Panel": cocuk_panel_ekrani()
