import pyaudio
import numpy as np
import time
import platform
import ctypes
import subprocess

# --- AYARLAR: BU DEĞERLERİ MİKROFONUNUZA VE ORTAMINIZA GÖRE AYARLAMANIZ GEREKECEK ---

# Ses örnekleme ayarları
CHUNK = 1024 * 2         # Tek seferde okunacak ses verisi (buffer boyutu)
FORMAT = pyaudio.paInt16 # Ses formatı (16-bit)
CHANNELS = 1               # Mono (tek kanal)
RATE = 44100               # Örnekleme hızı (Hz)

# Parmak şıklatma tespiti için frekans ve enerji ayarları
# Parmak şıklatması genellikle 2500 Hz - 8000 Hz arasında güçlü bir sinyal verir
SNAP_FREQ_LOW = 1500     # Parmak şıklatması alt frekans bandı
SNAP_FREQ_HIGH = 7000      # Parmak şıklatması üst frekans bandı

# Bu eşik, "parmak şıklatma bandındaki" ses enerjisinin,
# "diğer" (konuşma/arka plan gürültüsü) bandındaki enerjiden ne kadar
# güçlü olması gerektiğini belirler.
SNAP_RATIO_THRESHOLD = 10.0  # Şıklatma enerjisi / Diğer enerji oranı

# Bu, algılama için gereken minimum toplam ses enerjisi eşiğidir.
# Çok düşük seslerin (parazit) algılanmasını engeller.
MIN_ENERGY_THRESHOLD = 500000  # Bu değeri ortam gürültünüze göre ayarlayın

# Ekran kapatıldıktan sonra tekrar algılama yapmadan önce bekleme süresi
COOLDOWN_SECONDS = 2
# ----------------------------------------------------------------------------

def lock_screen():
    """İşletim sistemine göre ekranı kilitleyen fonksiyon (Win+L görevi)"""
    system = platform.system()
    print(f"{system} işletim sistemi algılandı. Ekran kilitleniyor...")
    
    try:
        if system == "Windows":
            # Windows API kullanarak iş istasyonunu kilitle (Win + L tuşu)
            ctypes.windll.user32.LockWorkStation()
        
        elif system == "Darwin": # macOS
            # Ekranı kilitle (Giriş ekranına dön)
            # Bu komutun çalışması için "Menu Extras"ın yolunun doğru olması gerekir.
            subprocess.run([
                "/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", 
                "-suspend"
            ])
            
        elif system == "Linux":
            # Çoğu masaüstü ortamı için standart olan xdg-screensaver kullanılır.
            # Alternatif: "loginctl lock-session"
            subprocess.run(["xdg-screensaver", "lock"])
            
    except Exception as e:
        print(f"Hata: Ekran kilitlenemedi. {e}")

def main():
    """Ana ses dinleme ve analiz döngüsü"""
    
    p = pyaudio.PyAudio()

    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)

    print("Parmak şıklatması bekleniyor... (Çıkmak için Ctrl+C)")

    last_trigger_time = 0

    try:
        while True:
            # Sesi oku
            data = stream.read(CHUNK, exception_on_overflow=False)
            
            # Veriyi NumPy dizisine çevir
            audio_data = np.frombuffer(data, dtype=np.int16)

            # FFT (Hızlı Fourier Dönüşümü) uygulamak
            fft_data = np.fft.rfft(audio_data)
            # Frekansları al
            fft_freqs = np.fft.rfftfreq(len(audio_data), 1.0/RATE)
            # Enerjiyi (genlik karesi) al
            magnitudes = np.abs(fft_data)

            # Toplam enerjiyi hesapla (gürültü filtresi için)
            total_energy = np.sum(magnitudes)

            # Sadece minimum enerji eşiğini geçerse analiz yap
            if total_energy > MIN_ENERGY_THRESHOLD:
                
                # Parmak şıklatma frekans bandındaki (örn: 2500-8000 Hz) enerjiyi bul
                snap_band_energy = np.sum(magnitudes[(fft_freqs > SNAP_FREQ_LOW) & (fft_freqs < SNAP_FREQ_HIGH)])
                
                # Diğer (konuşma/gürültü) frekans bandındaki (örn: 100-2500 Hz) enerjiyi bul
                other_band_energy = np.sum(magnitudes[(fft_freqs > 100) & (fft_freqs < SNAP_FREQ_LOW)])

                if other_band_energy == 0:
                    other_band_energy = 1 # Sıfıra bölme hatasını engelle
                
                # Şıklatma bandı enerjisi, diğer bant enerjisinden belirgin şekilde yüksek mi?
                ratio = snap_band_energy / other_band_energy

                 # print(f"Enerji: {total_energy:.0f}, Oran: {ratio:.2f}") # DEBUG İÇİN KULLANABİLİRSİNİZ

                if ratio > SNAP_RATIO_THRESHOLD:
                    current_time = time.time()
                    # Cooldown süresi geçtiyse
                    if current_time - last_trigger_time > COOLDOWN_SECONDS:
                        print(f"Parmak şıklatması algılandı! (Enerji: {total_energy:.0f}, Oran: {ratio:.2f})")
                        lock_screen()      # <--- DEĞİŞTİRİLDİ
                        last_trigger_time = current_time
                        print(f"{COOLDOWN_SECONDS} saniye bekleniyor...")

    except KeyboardInterrupt:
        print("Program sonlandırılıyor.")
    
    finally:
        # Stream'i ve PyAudio'yu kapat
        stream.stop_stream()
        stream.close()
        p.terminate()

if __name__ == "__main__":
    main()