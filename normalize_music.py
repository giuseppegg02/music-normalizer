import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path
from typing import List, Tuple
import threading
import queue
import concurrent.futures
import json

class MusicNormalizer:
    def __init__(self, target_lufs: float = -16.0):
        self.target_lufs = target_lufs
        self.supported_formats = {
            # Audio
            '.mp3', '.flac', '.wav', '.m4a', '.ogg', '.opus', '.aac', '.wma',
            # Video (saranno convertiti in audio)
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'
        }
        self.video_formats = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        
    def get_ffmpeg_path(self) -> str:
        """Trova ffmpeg embedded o nel sistema"""
        # Se siamo un exe PyInstaller
        if getattr(sys, 'frozen', False):
            bundle_dir = Path(sys._MEIPASS)
            ffmpeg_embedded = bundle_dir / 'ffmpeg.exe'
            if ffmpeg_embedded.exists():
                return str(ffmpeg_embedded)
        
        # Nella stessa directory dello script/exe
        script_dir = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).parent
        ffmpeg_local = script_dir / 'ffmpeg.exe'
        if ffmpeg_local.exists():
            return str(ffmpeg_local)
        
        # Nel PATH di sistema
        return 'ffmpeg'
    
    def check_ffmpeg(self) -> Tuple[bool, str]:
        """Verifica che ffmpeg sia disponibile"""
        ffmpeg_path = self.get_ffmpeg_path()
        try:
            subprocess.run([ffmpeg_path, '-version'], 
                         capture_output=True, 
                         check=True,
                         timeout=5)
            return True, ffmpeg_path
        except Exception:
            return False, None
    
    def get_audio_files(self, folder: Path) -> List[Path]:
        """Trova tutti i file audio/video nella cartella"""
        audio_files = []
        
        for file in folder.iterdir():
            if file.is_file() and file.suffix.lower() in self.supported_formats:
                audio_files.append(file)
        
        return sorted(audio_files)
    
    def measure_loudness(self, file_path: Path, ffmpeg_path: str) -> Tuple[float, float]:
        """Misura il loudness integrato del file"""
        cmd = [
            ffmpeg_path,
            '-i', str(file_path),
            '-af', 'loudnorm=print_format=json',
            '-f', 'null',
            '-'
        ]
        
        result = subprocess.run(cmd, 
                              capture_output=True, 
                              text=True,
                              timeout=300)
        
        output = result.stderr
        
        integrated = None
        true_peak = None
        
        for line in output.split('\n'):
            if '"input_i"' in line:
                try:
                    integrated = float(line.split(':')[1].strip().rstrip(',').strip('"'))
                except ValueError:
                    pass
            elif '"input_tp"' in line:
                try:
                    true_peak = float(line.split(':')[1].strip().rstrip(',').strip('"'))
                except ValueError:
                    pass
        
        return integrated, true_peak
    
    def normalize_file(self, input_path: Path, output_path: Path, 
                      ffmpeg_path: str, log_callback=None) -> bool:
        """Normalizza un singolo file"""
        try:
            def log(msg):
                if log_callback:
                    log_callback(msg)
            
            log(f"\n{'='*60}")
            log(f"File: {input_path.name}")
            log(f"{'='*60}")
            
            # Se è un video, converti in audio
            is_video = input_path.suffix.lower() in self.video_formats
            if is_video:
                log(f"⚙️  Rilevato video, estrazione audio...")
                # Cambia estensione output in .m4a
                output_path = output_path.with_suffix('.m4a')
            
            # Misura loudness (First pass)
            log("📊 Analisi loudness (Pass 1/2)...")
            integrated, true_peak = self.measure_loudness(input_path, ffmpeg_path)
            
            if integrated is None or integrated < -70:
                log(f"⚠️  Impossibile misurare loudness (file silenzioso o corrotto?)")
                return False
            
            log(f"  Loudness attuale: {integrated:.1f} LUFS")
            log(f"  True Peak: {true_peak:.1f} dBTP")
            log(f"  Target: {self.target_lufs:.1f} LUFS")
            
            adjustment = self.target_lufs - integrated
            log(f"  Aggiustamento: {adjustment:+.1f} dB")
            
            # Se già nel range accettabile (±1 LU) e non è video, copia
            if abs(adjustment) < 1.0 and not is_video:
                log(f"✓ Già normalizzato, copiato")
                import shutil
                shutil.copy2(input_path, output_path)
                return True
            
            # Normalizza con two-pass loudnorm
            log("⚙️  Normalizzazione (Pass 2/2)...")
            
            # First pass: Get detailed loudness stats for two-pass normalization
            first_pass_cmd = [
                ffmpeg_path,
                '-i', str(input_path),
                '-af', f'loudnorm=I={self.target_lufs}:TP=-1.5:LRA=11:print_format=json',
                '-f', 'null',
                '-'
            ]
            
            first_pass_result = subprocess.run(first_pass_cmd, 
                                              capture_output=True, 
                                              text=True,
                                              timeout=600)
            
            # Parse first pass output to get measured parameters
            output = first_pass_result.stderr
            measured_i = None
            measured_tp = None
            measured_lra = None
            measured_thresh = None
            
            # Extract JSON section from output
            try:
                # Find the JSON block in stderr
                json_start = output.rfind('{')
                json_end = output.rfind('}') + 1
                if json_start != -1 and json_end > json_start:
                    json_str = output[json_start:json_end]
                    loudness_stats = json.loads(json_str)
                    measured_i = loudness_stats.get('input_i')
                    measured_tp = loudness_stats.get('input_tp')
                    measured_lra = loudness_stats.get('input_lra')
                    measured_thresh = loudness_stats.get('input_thresh')
            except (json.JSONDecodeError, ValueError) as e:
                # If parsing fails, fall back to single-pass
                log(f"  ⚠️  Two-pass parsing failed ({str(e)}), using single-pass mode")
                measured_i = None
            
            # Second pass: Apply normalization with measured parameters
            if is_video:
                # Estrai audio e normalizza
                if measured_i is not None:
                    # Two-pass normalization
                    filter_str = (f'loudnorm=I={self.target_lufs}:TP=-1.5:LRA=11:'
                                f'measured_I={measured_i}:'
                                f'measured_TP={measured_tp}:'
                                f'measured_LRA={measured_lra}:'
                                f'measured_thresh={measured_thresh}:'
                                f'linear=true')
                else:
                    # Single-pass fallback
                    filter_str = f'loudnorm=I={self.target_lufs}:TP=-1.5:LRA=11'
                
                cmd = [
                    ffmpeg_path,
                    '-i', str(input_path),
                    '-vn',  # No video
                    '-af', filter_str,
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    '-ar', '48000',
                    '-y',
                    str(output_path)
                ]
            else:
                # Normalizza audio mantenendo formato
                if measured_i is not None:
                    # Two-pass normalization
                    filter_str = (f'loudnorm=I={self.target_lufs}:TP=-1.5:LRA=11:'
                                f'measured_I={measured_i}:'
                                f'measured_TP={measured_tp}:'
                                f'measured_LRA={measured_lra}:'
                                f'measured_thresh={measured_thresh}:'
                                f'linear=true')
                else:
                    # Single-pass fallback
                    filter_str = f'loudnorm=I={self.target_lufs}:TP=-1.5:LRA=11'
                
                cmd = [
                    ffmpeg_path,
                    '-i', str(input_path),
                    '-af', filter_str,
                    '-ar', '48000',
                    '-y',
                    str(output_path)
                ]
            
            result = subprocess.run(cmd, 
                                  capture_output=True, 
                                  text=True,
                                  timeout=600)
            
            if result.returncode == 0:
                log(f"✓ Completato: {output_path.name}")
                return True
            else:
                log(f"✗ Errore normalizzazione")
                return False
                
        except subprocess.TimeoutExpired:
            log(f"✗ Timeout (file troppo grande?)")
            return False
        except Exception as e:
            log(f"✗ Errore: {str(e)}")
            return False


class NormalizerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("NORMALIZZATORE MUSICALE")
        self.root.geometry("700x600")
        self.root.resizable(True, True)
        
        # Variabili
        self.normalizer = None
        self.processing = False
        self.log_queue = queue.Queue()
        
        self.setup_ui()
        # Check ffmpeg in background to avoid blocking startup
        threading.Thread(target=self.check_ffmpeg_status, daemon=True).start()
        self.root.after(100, self.process_log_queue)
        
    def setup_ui(self):
        # Frame principale
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Titolo
        title = ttk.Label(main_frame, text="🎵 Music Normalizer", 
                         font=('Arial', 16, 'bold'))
        title.grid(row=0, column=0, pady=(0, 10))
        
        # Controlli
        control_frame = ttk.LabelFrame(main_frame, text="Impostazioni", padding="10")
        control_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        control_frame.columnconfigure(1, weight=1)
        
        # Target loudness
        ttk.Label(control_frame, text="Target Loudness:").grid(row=0, column=0, sticky=tk.W)
        
        self.target_var = tk.StringVar(value="-16 LUFS (Conservativo)")
        target_combo = ttk.Combobox(control_frame, textvariable=self.target_var, 
                                   state='readonly', width=30)
        target_combo['values'] = (
            '-16 LUFS (Conservativo)',
            '-14 LUFS (Standard Streaming)', 
            '-12 LUFS (Più Forte)'
        )
        target_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(10, 0))
        
        # Status ffmpeg
        self.ffmpeg_status = ttk.Label(control_frame, text="⏳ Verifica ffmpeg in corso...", foreground='gray')
        self.ffmpeg_status.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))
        
        # Pulsante avvio (inizialmente disabilitato fino al check ffmpeg)
        self.start_btn = ttk.Button(control_frame, text="▶ Avvia Normalizzazione", 
                                    command=self.start_processing, state='disabled')
        self.start_btn.grid(row=2, column=0, columnspan=2, pady=(15, 0))
        
        # Progress bar
        self.progress = ttk.Progressbar(control_frame, mode='indeterminate')
        self.progress.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        # Log area
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="5")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, 
                                                  font=('Consolas', 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Info iniziale
        self.log("="*60)
        self.log("MUSIC NORMALIZER")
        self.log("="*60)
        self.log("\nElabora automaticamente tutti i file audio/video")
        self.log("nella cartella dove si trova questo programma.")
        self.log("\nFormati supportati:")
        self.log("  Audio: MP3, FLAC, WAV, M4A, OGG, OPUS, AAC, WMA")
        self.log("  Video: MP4, MKV, AVI, MOV, WMV, FLV, WEBM")
        self.log("  (i video saranno convertiti in audio M4A)")
        self.log("\nI file normalizzati saranno salvati nella")
        self.log("sottocartella 'normalized'")
        self.log("="*60 + "\n")
        
    def check_ffmpeg_status(self):
        """Verifica disponibilità ffmpeg (eseguito in thread separato)"""
        # Show checking status immediately
        self.root.after(0, lambda: self.ffmpeg_status.config(
            text="⏳ Verifica ffmpeg in corso...", 
            foreground='gray'
        ))
        
        normalizer = MusicNormalizer()
        available, path = normalizer.check_ffmpeg()
        
        # Update UI from main thread using root.after()
        if available:
            self.root.after(0, lambda: self.ffmpeg_status.config(
                text=f"✓ ffmpeg disponibile", 
                foreground='green'
            ))
            self.root.after(0, lambda: self.start_btn.config(state='normal'))
        else:
            self.root.after(0, lambda: self.ffmpeg_status.config(
                text="✗ ffmpeg NON TROVATO - Metti ffmpeg.exe nella stessa cartella", 
                foreground='red'
            ))
            self.root.after(0, lambda: self.start_btn.config(state='disabled'))
            self.log("\n⚠️  ATTENZIONE: ffmpeg non trovato!")
            self.log("\nPer usare questo programma devi:")
            self.log("1. Scaricare ffmpeg da: https://ffmpeg.org/download.html")
            self.log("2. Estrarre ffmpeg.exe")
            self.log("3. Metterlo nella stessa cartella di questo programma")
            self.log("\nOppure installare ffmpeg nel sistema con 'choco install ffmpeg'\n")
    
    def log(self, message):
        """Aggiunge messaggio al log"""
        self.log_queue.put(message)
    
    def process_log_queue(self):
        """Processa messaggi dal thread worker"""
        try:
            while True:
                message = self.log_queue.get_nowait()
                # Gestisci aggiornamento progress bar
                if isinstance(message, tuple) and message[0] == '__progress__':
                    self.progress['value'] = message[1]
                else:
                    self.log_text.insert(tk.END, message + "\n")
                    self.log_text.see(tk.END)
                    self.log_text.update()
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_log_queue)
    
    def get_target_lufs(self) -> float:
        """Converte selezione in valore LUFS"""
        target_map = {
            '-16 LUFS (Conservativo)': -16.0,
            '-14 LUFS (Standard Streaming)': -14.0,
            '-12 LUFS (Più Forte)': -12.0
        }
        return target_map.get(self.target_var.get(), -16.0)
    
    def start_processing(self):
        """Avvia elaborazione in thread separato"""
        if self.processing:
            return
        
        # Conferma
        result = messagebox.askyesno(
            "Conferma",
            "Avviare la normalizzazione di tutti i file\n"
            "audio/video in questa cartella?\n\n"
            "I file normalizzati saranno salvati in 'normalized/'"
        )
        
        if not result:
            return
        
        self.processing = True
        self.start_btn.config(state='disabled')
        self.progress.start()
        
        # Avvia thread
        thread = threading.Thread(target=self.process_files, daemon=True)
        thread.start()
    
    def process_files(self):
        """Elabora tutti i file in parallelo (eseguito in thread separato)"""
        try:
            # Setup
            target_lufs = self.get_target_lufs()
            self.normalizer = MusicNormalizer(target_lufs=target_lufs)
            
            # Trova ffmpeg
            available, ffmpeg_path = self.normalizer.check_ffmpeg()
            if not available:
                self.log("\n✗ ffmpeg non disponibile!")
                return
            
            # Cartelle
            script_dir = Path(sys.executable if getattr(sys, 'frozen', False) 
                            else __file__).parent
            output_dir = script_dir / "normalized"
            output_dir.mkdir(exist_ok=True)
            
            # Trova file
            audio_files = self.normalizer.get_audio_files(script_dir)
            
            if not audio_files:
                self.log("\n✗ Nessun file audio/video trovato nella cartella!")
                self.log(f"\nCercato in: {script_dir}")
                return
            
            # Numero di worker = numero di CPU
            max_workers = os.cpu_count() or 4
            
            self.log(f"\n{'='*60}")
            self.log("AVVIO ELABORAZIONE PARALLELA")
            self.log(f"{'='*60}")
            self.log(f"Cartella: {script_dir}")
            self.log(f"Output: {output_dir}")
            self.log(f"Target: {target_lufs} LUFS")
            self.log(f"File trovati: {len(audio_files)}")
            self.log(f"🚀 Worker paralleli: {max_workers} (CPU cores)")
            self.log(f"{'='*60}")
            
            # Configura progress bar determinata
            self.progress.config(mode='determinate', maximum=len(audio_files), value=0)
            
            # Contatori thread-safe
            completed = [0]  # Lista per mutabilità in closure
            success = [0]
            failed = [0]
            lock = threading.Lock()
            
            def process_single_file(file: Path) -> Tuple[Path, bool]:
                """Processa un singolo file e ritorna risultato"""
                output_file = output_dir / file.name
                result = self.normalizer.normalize_file(
                    file, output_file, ffmpeg_path, log_callback=self.log
                )
                
                # Aggiorna contatori thread-safe
                with lock:
                    completed[0] += 1
                    if result:
                        success[0] += 1
                    else:
                        failed[0] += 1
                    # Aggiorna progress bar via queue
                    self.log_queue.put(('__progress__', completed[0]))
                
                return file, result
            
            # Elaborazione parallela con ThreadPoolExecutor
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Sottometti tutti i job
                futures = {executor.submit(process_single_file, f): f for f in audio_files}
                
                # Attendi completamento
                for future in concurrent.futures.as_completed(futures):
                    file = futures[future]
                    try:
                        _, ok = future.result()
                    except Exception as e:
                        self.log(f"✗ Errore critico per {file.name}: {e}")
                        with lock:
                            failed[0] += 1
                            completed[0] += 1
            
            # Report finale
            self.log(f"\n{'='*60}")
            self.log("✓ ELABORAZIONE COMPLETATA")
            self.log(f"{'='*60}")
            self.log(f"Successi: {success[0]}/{len(audio_files)}")
            if failed[0] > 0:
                self.log(f"Falliti: {failed[0]}/{len(audio_files)}")
            self.log(f"\nFile salvati in: {output_dir}")
            self.log(f"{'='*60}\n")
            
            messagebox.showinfo(
                "Completato",
                f"Elaborazione completata!\n\n"
                f"Successi: {success[0]}/{len(audio_files)}\n"
                f"Falliti: {failed[0]}\n\n"
                f"File salvati in:\n{output_dir}"
            )
            
        except Exception as e:
            self.log(f"\n✗ ERRORE: {str(e)}")
            messagebox.showerror("Errore", f"Errore durante elaborazione:\n{str(e)}")
        
        finally:
            self.processing = False
            self.progress.stop()
            self.start_btn.config(state='normal')


def main():
    root = tk.Tk()
    app = NormalizerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()