import streamlit as st
import sqlite3
import io
import os
import pytz
from datetime import datetime
from docx import Document
from docx.shared import Inches

# ==============================================================================
# SİSTEM AYARLARI
# ==============================================================================
st.set_page_config(page_title="Qyvam | Siber Uzay", layout="wide")

# Veritabanı Tekeli (Tek Dosya: qyvam_siber.db)
DB_PATH = 'qyvam_siber.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS Cocuklar (id INTEGER PRIMARY KEY AUTOINCREMENT, isim TEXT, mevcut_adim INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS Gorevler (id INTEGER PRIMARY KEY AUTOINCREMENT, cocuk_id INTEGER, gorev_adi TEXT, tefekkur TEXT, durum TEXT, puan INTEGER, veli_notu TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ozel_beratlar (id INTEGER PRIMARY KEY AUTOINCREMENT, cocuk_id INTEGER, berat_adi TEXT, berat_aciklama TEXT)''')
    conn.commit()
    conn.close()

init_db() # Başlangıçta tabloları garantiye al

# ==============================================================================
# VERİTABANI İŞLEMLERİ (CRUD)
# ==============================================================================
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

def veri_onayla(gorev_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE Gorevler SET durum = 'Onaylandı' WHERE id = ?", (gorev_id,))
    conn.commit()
    conn.close()

# ==============================================================================
# YARDIMCI ARAÇLAR
# ==============================================================================
def word_raporu_olustur(cocuk_ismi, gorev_adi, veli_notu, fotograf_bytes=None):
    doc = Document()
    doc.add_heading(f'Qyvam - Görev Raporu: {cocuk_ismi}', 0)
    doc.add_paragraph("Görev: " + gorev_adi).bold = True
    doc.add_paragraph("Veli Gözlemi: " + veli_notu)
    if fotograf_bytes:
        foto_io = io.BytesIO(fotograf_bytes)
        doc.add_picture(foto_io, width=Inches(5.0))
    byte_io = io.BytesIO()
    doc.save(byte_io)
    byte_io.seek(0)
    return byte_io

# ==============================================================================
# ARAYÜZ TASARIMI (CSS)
# ==============================================================================
st.markdown("""
    <style>
    .glass-box { background: #ffffff; border: 2px solid #e0e7ff; border-radius: 16px; padding: 25px; margin-bottom: 20px; }
    .top-bar { background: #ffffff; padding: 15px; border-radius: 0 0 20px 20px; margin-bottom: 20px; }
    .stButton>button { border-radius: 12px; background-color: #6366f1; color: white !important; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# PANEL: VELİ / REHBER
# ==============================================================================
def veli_panel_ekrani():
    st.title("REHBERLİK KÖŞESİ")
    t1, t2, t3, t4, t5 = st.tabs(["Onay", "Rapor", "Gelişim", "Berat", "Kayıt"])

    with t1:
        bekleyenler = onay_bekleyenleri_getir()
        for k in bekleyenler:
            if st.button(f"✅ Onayla: {k[1]} - {k[2]}", key=f"onay_{k[0]}"):
                veri_onayla(k[0])
                st.rerun()

    with t2:
        cocuklar = cocuklari_getir()
        if cocuklar:
            secilen = st.selectbox("Çocuk:", [c[1] for c in cocuklar])
            notu = st.text_area("Not:")
            if st.button("Word Oluştur"):
                # Rapor oluşturma mantığı burada olacak
                st.success("Rapor hazır.")

    with t3:
        st.subheader("Gelişim Matrisi")
        for c in cocuklari_getir():
            st.write(f"{c[1]} - Adım: {c[2]}")

    with t4:
        st.subheader("Berat Tasarla")
        # Berat ekleme mantığı
        
    with t5:
        st.subheader("Kayıt Yönetimi")
        isim = st.text_input("Yeni İsim:")
        if st.button("Ekle"):
            cocuk_ekle(isim)
            st.rerun()
        
        silinecek = st.selectbox("Sil:", [c[1] for c in cocuklari_getir()])
        if st.button("Sil"):
            cid = next(c[0] for c in cocuklari_getir() if c[1] == secilen)
            cocuk_sil(cid)
            st.rerun()

# ==============================================================================
# ROUTER
# ==============================================================================
if 'aktif_sayfa' not in st.session_state: st.session_state.aktif_sayfa = "Veli_Panel"
veli_panel_ekrani()
