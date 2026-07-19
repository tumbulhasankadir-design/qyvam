import streamlit as st
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
    
    col_sol, col_orta, col_sag = st.columns([2, 1, 4])
    with col_sol:
        if st.session_state.aktif_sayfa == "Ana Sayfa": durum_metni = "ANA SAYFA"
        elif st.session_state.aktif_sayfa == "Veli_Panel": durum_metni = "REHBER KOMUTA MERKEZİ"
        else: durum_metni = "DİJİTAL İKİZ BAĞLANTISI"
        st.markdown(f'<div class="breadcrumb">QYVAM SİBER UZAY > <b>{durum_metni}</b></div>', unsafe_allow_html=True)
        
    with col_orta:
        if st.session_state.aktif_sayfa == "Ana Sayfa" or st.session_state.aktif_sayfa == "Cocuk_Panel":
            if st.button("Yetkili Girişi"): 
                st.session_state.veli_yetkili = True # Şifreyi atlayıp doğrudan yetki veriyoruz
                st.session_state.aktif_sayfa = "Veli_Panel" 
                st.rerun()
        else:
            if st.button("Uzay'a Dön"):
                st.session_state.aktif_sayfa = "Ana Sayfa"
                st.session_state.veli_yetkili = False
                st.session_state.aktif_cocuk_id = None
                st.rerun()
                
    with col_sag:
        try: locale.setlocale(locale.LC_TIME, 'tr_TR.UTF-8')
        except: pass
        tarih_str = datetime.now().strftime("%d %b %Y | %H:%M")
        
        bekleyen_sayisi = len(onay_bekleyenleri_getir())
        bildirim_kodu = f'<span class="sensor-data" style="color:#fca5a5; border-color:#fca5a5;">[ ONAY BEKLEYEN: {bekleyen_sayisi} ]</span>' if bekleyen_sayisi > 0 else ''

        # Kafa karıştıran AI Aktif yazısı tamamen kaldırıldı
        st.markdown(f'''
            <div style="text-align: right;">
                <span class="sensor-data">{tarih_str}</span>
                {bildirim_kodu}
            </div>
            <hr style="border-color: rgba(56, 189, 248, 0.2); margin-top: 15px;">
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
# SAYFA 3: VELİ (REHBER) KOMUTA MERKEZİ
# ==============================================================================
def veli_panel_ekrani():
    if not st.session_state.veli_yetkili:
        st.session_state.aktif_sayfa = "Veli_Giris"
        st.rerun()

    st.markdown('<h1 class="neon-text">REHBER KOMUTA MERKEZİ</h1><hr>', unsafe_allow_html=True)
    t1, t2, t3, t4, t5 = st.tabs(["[ ŞAHİTLİK VE ONAY MASASI ]", "[ GELİŞİM MATRİSİ ]", "[ YETKİNLİK BERATLARI ]", "[ SİSTEME PROFİL EKLE ]", "[ QYVAM PEDAGOG AI ]"])

    with t1:
        bekleyenler = onay_bekleyenleri_getir()
        if not bekleyenler:
            st.markdown('<div class="glass-box"><h3 class="neon-text">Bekleyen Veri Paketleri</h3>', unsafe_allow_html=True)
            st.info("[ SİSTEM BİLGİSİ ]: Şu an onay bekleyen görev bulunmamaktadır.")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            for g in bekleyenler:
                g_id, c_isim, g_adi, tefekkur, c_id, c_adim = g
                st.markdown(f'''
                    <div class="glass-task">
                        <h4 style="color:#fca5a5; margin-top:0;">[ DİJİTAL İKİZ: {c_isim.upper()} ]</h4>
                        <p style="color:#94a3b8; margin-bottom:10px;"><b>Kritik Eylem:</b> {g_adi}</p>
                        <p style="color:#6ee7b7; font-family:'Chakra Petch'; margin-bottom:5px;"><b>Tefekkür:</b> "{tefekkur}"</p>
                    </div>
                ''', unsafe_allow_html=True)
                
                puan_secim = st.radio("Şahitlik Puanınız:", ["1 - Yardımla (Tekrar)", "2 - Hatırlatmayla (Tekrar)", "3 - Kendi İradesiyle (Başarılı)", "4 - İhsanla / Kıvam (Mükemmel)"], key=f"puan_{g_id}")
                veli_notu = st.text_area("Rehber Notu:", key=f"not_{g_id}")
                
                if st.button("[ ŞAHİTLİĞİ ONAYLA ]", key=f"btn_{g_id}"):
                    puan_int = int(puan_secim.split(" ")[0])
                    basarili = True if puan_int >= 3 else False
                    veli_onayi_ver(g_id, puan_int, veli_notu, c_id, basarili)
                    st.success("[ İŞLEM BAŞARILI ]: Veri işlendi.")
                    st.rerun()

    with t2:
        st.markdown('<div class="glass-box"><h3 class="neon-text">Gelişim Radarı</h3></div>', unsafe_allow_html=True)
        cocuklar = cocuklari_getir()
        for c_id, isim, adim in cocuklar:
            yuzde = int((adim / 99) * 100)
            st.markdown(f"**Profil:** {isim} | **Mevcut Adım:** {adim}/99")
            st.progress(yuzde)

    with t3:
        st.markdown('<div class="glass-box"><h3 class="neon-text">Yetkinlik Beratları</h3></div>', unsafe_allow_html=True)
        
    with t4:
        st.markdown('<div class="glass-box"><h3 class="neon-text">Yeni Profil Tanımlama</h3></div>', unsafe_allow_html=True)
        yeni_isim = st.text_input("Dijital İkiz Adı (Çocuğun İsmi):")
        if st.button("[ MATRİSİ OLUŞTUR ]"):
            if yeni_isim:
                baglanti = sqlite3.connect('qyvam_siber.db')
                imlec = baglanti.cursor()
                imlec.execute("INSERT INTO Cocuklar (isim, mevcut_adim) VALUES (?, 1)", (yeni_isim,))
                baglanti.commit()
                baglanti.close()
                st.success(f"[ BAŞARILI ]: {yeni_isim} eklendi.")
                st.rerun()

    with t5:
        st.markdown('<div class="glass-box"><h3 class="neon-text">Qyvam Rehberlik Asistanı</h3></div>', unsafe_allow_html=True)
        veli_sorusu = st.text_input("Soru:", placeholder="[ Örn: Ekran kuralları nasıl belirlenmeli? ]", key="v_soru")
        if st.button("[ SORGULA ]", key="v_btn"):
            if veli_sorusu:
                with st.spinner("AI Çekirdeği veriyi işliyor..."):
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
