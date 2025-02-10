#!/usr/bin/env python3
import os
import sys
import json
import cv2
import logging
import argparse

# Configurazione di base del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Dimensioni target per ingrandire le immagini piccole
TARGET_WIDTH = 1200
TARGET_HEIGHT = 900

# Definiamo un'eccezione per uscire dalla revisione
class ExitReviewException(Exception):
    pass

def safe_destroy_window(win_name):
    """Distrugge la finestra se esiste."""
    try:
        if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) >= 1:
            cv2.destroyWindow(win_name)
    except Exception:
        pass

def manual_roi_selection(image, window_name="Select ROI", max_width=TARGET_WIDTH, max_height=TARGET_HEIGHT,
                           default_roi=None, display_img=None, scale=None):
    """
    Permette la selezione interattiva di una ROI tramite mouse.

    Se non vengono passati display_img e scale, l'immagine viene ridimensionata in modo da avere
    almeno max_width x max_height (scalando in su se l'immagine è piccola o in giù se troppo grande).

    L'utente disegna il rettangolo e poi deve premere **s** per salvare la selezione oppure **q**
    per uscire dalla revisione (in questo caso l'intero ciclo viene interrotto).

    Se il parametro default_roi è fornito, viene disegnato un reticolo di default:
      - Se default_roi è un dizionario contenente le chiavi "x", "y", "w", "h", viene trattato come ROI singolo
        e disegnato in blu, con il messaggio "Default ROI (s to accept, drag to change)".
      - Se default_roi è un dizionario senza queste chiavi, si assume che contenga default multipli (es. "internal" ed "external")
        e si disegnano rettangoli (in colori differenti) per ciascuno.
      - Altrimenti, se default_roi è una tupla/lista di 4 numeri, viene disegnato come ROI di default.

    Le coordinate restituite sono riportate nelle dimensioni originali.
    """
    # Calcola display_img e scale se non passati
    if display_img is None or scale is None:
        orig_h, orig_w = image.shape[:2]
        if orig_w > max_width or orig_h > max_height:
            scale = min(max_width / orig_w, max_height / orig_h)
            display_img = cv2.resize(image, (int(orig_w * scale), int(orig_h * scale)))
        else:
            scale = max(max_width / orig_w, max_height / orig_h)
            display_img = cv2.resize(image, (int(orig_w * scale), int(orig_h * scale)),
                                     interpolation=cv2.INTER_LINEAR)
    clone = display_img.copy()
    roi = None
    start_point = None
    selecting = False

    # Disegna il reticolo di default se presente
    if default_roi is not None:
        if isinstance(default_roi, dict):
            # Se il dizionario contiene le chiavi "x", "y", "w", "h", lo trattiamo come ROI singolo
            if all(k in default_roi for k in ("x", "y", "w", "h")):
                x = default_roi["x"]
                y = default_roi["y"]
                w = default_roi["w"]
                h = default_roi["h"]
                roi = (int(x * scale), int(y * scale), int(w * scale), int(h * scale))
                cv2.rectangle(display_img, (roi[0], roi[1]), (roi[0]+roi[2], roi[1]+roi[3]), (255, 0, 0), 2)
                cv2.putText(display_img, "Default ROI (s to accept, drag to change)", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
                clone = display_img.copy()
            else:
                # Default multipli (es. {"internal": [...], "external": [...]})
                for key, val in default_roi.items():
                    try:
                        x, y, w, h = val
                    except Exception as e:
                        logging.warning(f"Default ROI per '{key}' non valido: {val}")
                        continue
                    x_disp = int(x * scale)
                    y_disp = int(y * scale)
                    w_disp = int(w * scale)
                    h_disp = int(h * scale)
                    color = (255, 0, 0) if key.lower() == "internal" else (0, 0, 255)
                    cv2.rectangle(display_img, (x_disp, y_disp), (x_disp + w_disp, y_disp + h_disp), color, 2)
                    cv2.putText(display_img, f"{key} Default (s to accept)", (x_disp, max(y_disp - 10, 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                clone = display_img.copy()
        else:
            try:
                x, y, w, h = default_roi
                roi = (int(x * scale), int(y * scale), int(w * scale), int(h * scale))
                cv2.rectangle(display_img, (roi[0], roi[1]), (roi[0]+roi[2], roi[1]+roi[3]), (255, 0, 0), 2)
                cv2.putText(display_img, "Default ROI (s to accept, drag to change)", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
                clone = display_img.copy()
            except Exception as e:
                logging.warning("Il formato di default_roi non è corretto.")

    def mouse_callback(event, x, y, flags, param):
        nonlocal selecting, start_point, roi, clone
        if event == cv2.EVENT_LBUTTONDOWN:
            selecting = True
            start_point = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and selecting:
            if start_point is None:
                return
            temp = clone.copy()
            cv2.rectangle(temp, start_point, (x, y), (0, 255, 0), 2)
            cv2.imshow(window_name, temp)
        elif event == cv2.EVENT_LBUTTONUP:
            if start_point is None:
                return
            selecting = False
            end_point = (x, y)
            x0 = min(start_point[0], end_point[0])
            y0 = min(start_point[1], end_point[1])
            x1 = max(start_point[0], end_point[0])
            y1 = max(start_point[1], end_point[1])
            roi = (x0, y0, x1 - x0, y1 - y0)
            clone = display_img.copy()
            cv2.rectangle(clone, (x0, y0), (x1, y1), (0, 255, 0), 2)
            cv2.imshow(window_name, clone)

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(window_name, 100, 100)
    cv2.imshow(window_name, clone)
    cv2.setMouseCallback(window_name, mouse_callback)

    print(f"In the window '{window_name}', draw a rectangle then press 's' to save or 'q' to exit review.")
    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord('s'):
            safe_destroy_window(window_name)
            if roi is None:
                return (0, 0, 0, 0)
            x_disp, y_disp, w_disp, h_disp = roi
            roi_orig = (int(x_disp / scale), int(y_disp / scale),
                        int(w_disp / scale), int(h_disp / scale))
            return roi_orig
        elif key == ord('q'):
            safe_destroy_window(window_name)
            raise ExitReviewException

def review_image_pages(json_path, images_dir):
    """
    Legge il file JSON e, per ogni pagina "image-present" (di tipo "main") non ancora validata,
    permette di selezionare (o confermare) manualmente le ROI per l'immagine interna e per la caption.

    Le coordinate selezionate vengono salvate (in pixel) e il flag "manual_confirmed" viene impostato a True.
    Viene inoltre visualizzato un counter che indica quante immagini rimangono da processare.
    Se viene premuto 'q' durante la selezione, l'intera revisione termina e il JSON viene salvato.
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            pages = json.load(f)
    except Exception as e:
        logging.error(f"Errore durante il caricamento di {json_path}: {e}")
        sys.exit(1)
    
    total = sum(1 for p in pages if p.get("page_type") == "main" and 
                p.get("type") == "image-present" and not p.get("manual_confirmed", False))
    processed = 0

    try:
        for page in pages:
            if page.get("page_type") == "main" and page.get("type") == "image-present":
                if page.get("manual_confirmed", False):
                    logging.info(f"Pagina {page.get('file', 'sconosciuta')} già validata, salto.")
                    continue

                image_file = page.get("file")
                if not image_file:
                    logging.warning("Pagina senza file immagine, salto.")
                    continue

                image_path = os.path.join(images_dir, image_file)
                image = cv2.imread(image_path)
                if image is None:
                    logging.warning(f"Impossibile leggere l'immagine: {image_path}")
                    continue

                processed += 1
                remaining = total - processed
                print(f"\n--- Revisione pagina {processed}/{total}: {image_file} ---")
                print(f"Immagini rimanenti: {remaining}")

                orig_h, orig_w = image.shape[:2]
                if orig_w < TARGET_WIDTH or orig_h < TARGET_HEIGHT:
                    scale = max(TARGET_WIDTH / orig_w, TARGET_HEIGHT / orig_h)
                    display_img = cv2.resize(image, (int(orig_w * scale), int(orig_h * scale)),
                                             interpolation=cv2.INTER_LINEAR)
                elif orig_w > TARGET_WIDTH or orig_h > TARGET_HEIGHT:
                    scale = min(TARGET_WIDTH / orig_w, TARGET_HEIGHT / orig_h)
                    display_img = cv2.resize(image, (int(orig_w * scale), int(orig_h * scale)),
                                             interpolation=cv2.INTER_AREA)
                else:
                    scale = 1.0
                    display_img = image.copy()

                window_name = "Review"
                cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
                cv2.moveWindow(window_name, 100, 100)
                cv2.imshow(window_name, display_img)

                # Selezione ROI per l'immagine interna
                default_roi_image = page.get("image_coordinates")
                print("Seleziona ROI per l'immagine interna.")
                print("Premi 's' per confermare il default (se presente) oppure disegna il rettangolo.")
                roi = manual_roi_selection(image, window_name=window_name,
                                           default_roi=default_roi_image,
                                           display_img=display_img, scale=scale)
                if roi == (0, 0, 0, 0):
                    print("ROI non selezionata. Saltando questa pagina.")
                    safe_destroy_window(window_name)
                    continue
                logging.info(f"ROI immagine interna per {image_file}: {roi}")
                page["image_coordinates"] = {"x": roi[0], "y": roi[1], "w": roi[2], "h": roi[3]}

                # Selezione ROI per la caption
                default_roi_caption = page.get("internal_caption_coordinates")
                print("Seleziona ROI per la caption (o annulla per saltare) e premi 's' per confermare.")
                roi_caption = manual_roi_selection(image, window_name=window_name,
                                                   default_roi=default_roi_caption,
                                                   display_img=display_img, scale=scale)
                if roi_caption != (0, 0, 0, 0):
                    logging.info(f"ROI caption per {image_file}: {roi_caption}")
                    page["caption_coordinates"] = [roi_caption[0], roi_caption[1],
                                                   roi_caption[2], roi_caption[3]]
                else:
                    logging.info("ROI per la caption non selezionata.")
                    page["caption_coordinates"] = None

                safe_destroy_window(window_name)
                page["manual_confirmed"] = True  # Imposta il flag per indicare che le coord sono state validate
                print("Pagina validata. Procedo alla successiva...")
                cv2.waitKey(100)
    except ExitReviewException:
        print("Revisione interrotta dall'utente. Salvataggio in corso...")

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(pages, f, indent=4)
        logging.info(f"JSON aggiornato e salvato in: {json_path}")
    except Exception as e:
        logging.error(f"Errore nel salvataggio del JSON: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Strumento interattivo per validare manualmente le coordinate delle pagine 'image-present'.\n"
                    "Le pagine già validate (flag 'manual_confirmed' true) vengono saltate.\n"
                    "Premi 's' per confermare la ROI (o il reticolo di default, se presente), oppure 'q' per uscire dalla revisione."
    )
    parser.add_argument("--json", required=True, help="Percorso al file JSON (es. bookindex.json)")
    parser.add_argument("--images", required=True, help="Cartella contenente le immagini")
    args = parser.parse_args()

    review_image_pages(args.json, args.images)
