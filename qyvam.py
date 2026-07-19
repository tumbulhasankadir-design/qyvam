import streamlit as st
import sqlite3
import io
import os
import pytz
from datetime import datetime
from docx import Document
from docx.shared import Inches

# Müfredat kontrolü
try:
    from mufredat import MUFREDAT
except ImportError:
    MUFREDAT = {}

# ==============================================================================
# 1. MERKEZİ VERİTABANI MOTORU (Tüm tablolar tek dosyada)
# ==============================================================================
DB_PATH = 'qyvam_siber.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS Cocuklar (id INTEGER PRIMARY KEY AUTOINCREMENT, isim TEXT, mevcut_adim INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS Gorevler (id INTEGER PRIMARY KEY AUTOINCREMENT, cocuk_id INTEGER, gorev_adi TEXT, tefekkur TEXT, durum TEXT, puan INTEGER, veli_notu TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ozel_beratlar (id INTEGER PRIMARY KEY AUTOINCREMENT, cocuk_id INTEGER, berat_adi TEXT, berat_aciklama TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- VERİTABANI FONKSİYONLARI ---
def cocuklari_getir():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, isim, mevcut_adim FROM Cocuklar")
    data = c.fetchall()
    conn.close()
    return data

def cocuk_ekle(isim):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO Cocuklar (isim, mevcut_adim) VALUES (?, ?)", (isim, 1))
    conn.commit()
    conn.close()

def cocuk_sil(cocuk_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM Cocuklar WHERE id = ?", (cocuk_id,))
    c.execute("DELETE FROM Gorevler WHERE cocuk_id = ?", (cocuk_id,))
    c.execute("DELETE FROM ozel_beratlar WHERE cocuk_id = ?", (cocuk_id,))
    conn.commit()
    conn.close()

def cocuk_adim_guncelle(cocuk_id, yeni_adim):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE Cocuklar SET mevcut_adim = ? WHERE id = ?", (yeni_adim, cocuk_id))
    conn.commit()
    conn.close()

def onay_bekleyenleri_getir():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT G.id, C.isim, G.gorev_adi, G.tefekkur, C.id, C.mevcut_adim 
                 FROM Gorevler G JOIN Cocuklar C ON G.cocuk_id = C.id WHERE G.durum = 'Veli Onayı Bekliyor' ''')
    liste = c.fetchall()
    conn.close()
    return liste

def veri_onayla(gorev_id, cocuk_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE Gorevler SET durum = 'Onaylandı' WHERE id = ?", (gorev_id,))
    c.execute("UPDATE Cocuklar SET mevcut_adim = mevcut_adim + 1 WHERE id = ?", (cocuk_id,))
    conn.commit()
    conn.close()

def word_raporu_olustur(cocuk_ismi, gorev_adi, veli_notu, fotograf_bytes=None):
    doc = Document()
    doc.add_heading(f'Qyvam - Görev Raporu: {cocuk_ismi}', 0)
    doc.add_paragraph("Görev İçeriği:").bold = True
    doc.add_paragraph(gorev_adi)
    doc.add_paragraph("Rehber (Veli) Gözlemi:").bold = True
    doc.add_paragraph(veli_notu)
    if fotograf_bytes:
        foto_io = io.BytesIO(fotograf_bytes)
        doc.add_picture(foto_io, width=Inches(5.0))
    byte_io = io.BytesIO()
    doc.save(byte_io)
    byte_io.seek(0)
    return byte_io

# ==============================================================================
# 2. ARAYÜZ (CSS) - TASARIMINIZ AYNEN KORUNDU
# ==============================================================================
st.set_page_config(page_title="Qyvam | Siber Uzay", layout="wide")
st.markdown("""
    <style>
    .glass-box { background: #ffffff; border: 2px solid #e0e7ff; border-radius: 16px; padding: 25px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(99, 102, 241, 0.05); }
    .neon-text { color: #4f46e5 !important; font-weight: 700; }
    .stButton>button { border-radius: 12px; background-color: #6366f1; color: white !important; }
    .radar-baslik { color: #ec4899; font-weight: 700; }
    .radar-adim { color: #64748b; margin-left: 15px; border-left: 3px solid #e2e8f0; padding-left: 12px; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 3. VELİ PANELİ (6 Sekmeli)
# ==============================================================================
def veli_panel_ekrani():
    st.markdown('<h1 class="neon-text">REHBERLİK KÖŞESİ</h1><hr>', unsafe_allow_html=True)
    t1, t2, t3, t4, t5, t6 = st.tabs(["Gözlem ve Onay", "Serbest Rapor", "Gelişim Matrisi", "Berat Tasarla", "Sisteme Kayıt", "AI Pedagog"])
    
    with t1:
        bekleyenler = onay_bekleyenleri_getir()
        if not bekleyenler: st.info("Onay bekleyen görev yok.")
        for k in bekleyenler:
            with st.expander(f"📌 {k[1]} - {k[2]}"):
                if st.button("✅ Onayla", key=f"onay_{k[0]}"):
                    veri_onayla(k[0], k[4])
                    st.rerun()
    with t5:
        st.subheader("Kayıt Yönetimi")
        isim = st.text_input("Yeni İsim:")
        if st.button("Ekle"):
            cocuk_ekle(isim)
            st.rerun()
        
        cocuklar = cocuklari_getir()
        if cocuklar:
            silinecek = st.selectbox("Sil:", [c[1] for c in cocuklar])
            if st.button("❌ Sil"):
                cid = next(c[0] for c in cocuklar if c[1] == silinecek)
                cocuk_sil(cid)
                st.rerun()

# ==============================================================================
# 4. ROUTER
# ==============================================================================
if 'aktif_sayfa' not in st.session_state: st.session_state.aktif_sayfa = "Veli_Panel"
veli_panel_ekrani()
