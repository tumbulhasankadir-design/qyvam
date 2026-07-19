import streamlit as st
import sqlite3
import io
import os
import pytz
from datetime import datetime
from docx import Document
from docx.shared import Inches

# ==============================================================================
# SİSTEM AYARLARI VE TEKİL VERİTABANI YOLU
# ==============================================================================
st.set_page_config(page_title="Qyvam | Siber Uzay", layout="wide")
DB_PATH = 'qyvam_siber.db'

# --- VERİTABANI MOTORU (HER ŞEY TEK DOSYADA) ---
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

# --- CSS VE ARAYÜZ (TASARIM KORUNDU) ---
st.markdown("""
    <style>
    .glass-box { background: #ffffff; border: 2px solid #e0e7ff; border-radius: 16px; padding: 25px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(99, 102, 241, 0.05); }
    .neon-text { color: #4f46e5 !important; font-weight: 700; }
    .stButton>button { border-radius: 12px; background-color: #6366f1; color: white !important; width: 100%; }
    .radar-baslik { color: #ec4899; font-weight: 700; }
    .radar-adim { color: #64748b; margin-left: 15px; border-left: 3px solid #e2e8f0; padding-left: 12px; }
    </style>
""", unsafe_allow_html=True)

# --- PANEL FONKSİYONLARI ---
def veli_panel_ekrani():
    st.markdown('<h1 class="neon-text">REHBERLİK KÖŞESİ</h1><hr>', unsafe_allow_html=True)
    t1, t2, t3, t4, t5 = st.tabs(["Onay", "Rapor", "Gelişim", "Berat", "Kayıt"])
    
    with t1:
        st.write("Bekleyen görevler burada görünecek.")
    with t2:
        st.write("Word raporu alanı.")
    with t3:
        st.subheader("Gelişim Matrisi")
        for c in cocuklari_getir():
            st.write(f"{c[1]} - Adım: {c[2]}")
    with t4:
        st.subheader("Berat Tasarla")
    with t5:
        st.subheader("Kayıt Yönetimi")
        isim = st.text_input("Yeni İsim:")
        if st.button("Ekle"):
            cocuk_ekle(isim)
            st.rerun()
        
        cocuklar = cocuklari_getir()
        if cocuklar:
            silinecek = st.selectbox("Sil:", [c[1] for c in cocuklar])
            if st.button("❌ Seçili Çocuğu Sil"):
                cid = next(c[0] for c in cocuklar if c[1] == silinecek)
                cocuk_sil(cid)
                st.rerun()

# --- ROUTER ---
if 'aktif_sayfa' not in st.session_state: st.session_state.aktif_sayfa = "Veli_Panel"
veli_panel_ekrani()
