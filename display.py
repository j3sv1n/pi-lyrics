#!/usr/bin/env python3
"""
Pi Lyrics - PDF Viewer (Vertical Monitor Edition)
- Screen is horizontal (landscape) but monitor is rotated 90° physically,
  so we render everything into a virtual vertical canvas then rotate the
  whole frame 90° clockwise before blitting to screen.
- PDF fills the top portion of the virtual canvas (no rotation applied to
  the PDF itself — the physical monitor rotation handles that).
- Big "Next: <filename>" bar sits at the bottom of the virtual canvas.
- Bottom-left: dim overall slide index (e.g. 2/5).
- Bottom-right of bar: if current PDF has >1 page, shows dim page index (e.g. p2/3).
- Navigation steps through pages within a PDF before moving to the next PDF.
"""

import sys
import json
import threading
import pygame
import fitz  # PyMuPDF
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
PDF_DIR    = BASE_DIR / "pdfs"
ORDER_FILE = BASE_DIR / "order.json"
CONTROL_FILE = BASE_DIR / "control.json"
STATE_FILE   = BASE_DIR / "state.json"

NEXT_BAR_H = 120          # height of Next bar in the virtual canvas
BG_COLOR   = (0,   0,   0)
BAR_COLOR  = (15,  15,  15)
TEXT_COLOR = (220, 220, 220)
ACCENT     = (255, 200,  60)
DIM_COLOR  = (80,  85,  95)   # dim colour for index labels
FPS        = 30

PDF_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_order():
    existing = set(p.name for p in PDF_DIR.glob("*.pdf"))
    if ORDER_FILE.exists():
        try:
            saved = json.loads(ORDER_FILE.read_text())
            ordered = [f for f in saved if f in existing]
            for f in sorted(existing):
                if f not in ordered:
                    ordered.append(f)
            return ordered
        except Exception:
            pass
    return sorted(existing)


def get_page_count(pdf_path):
    """Return the number of pages in a PDF (fast, no rendering)."""
    try:
        doc = fitz.open(str(pdf_path))
        n   = doc.page_count
        doc.close()
        return n
    except Exception:
        return 1


def render_pdf_page_to_surface(pdf_path, page_index, width, height):
    """
    Render a specific page of a PDF scaled to fit (width x height).
    Returns a pygame Surface.
    """
    doc  = fitz.open(str(pdf_path))
    page_index = min(page_index, doc.page_count - 1)
    page = doc[page_index]

    sample = page.get_pixmap(alpha=False)
    pw, ph = sample.width, sample.height

    scale = min(width / pw, height / ph)
    mat   = fitz.Matrix(scale, scale)
    pix   = page.get_pixmap(matrix=mat, alpha=False)
    doc.close()

    return pygame.image.frombuffer(pix.samples, (pix.width, pix.height), "RGB")


# ── Filesystem watcher ────────────────────────────────────────────────────────

class PDFWatcher(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback
    def on_any_event(self, event):
        p = str(event.src_path)
        if p.endswith(".pdf") or p.endswith("order.json"):
            self.callback()


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    pygame.init()
    pygame.mouse.set_visible(False)

    info    = pygame.display.Info()
    SW, SH  = info.current_w, info.current_h
    screen  = pygame.display.set_mode((SW, SH), pygame.FULLSCREEN | pygame.NOFRAME)
    pygame.display.set_caption("Pi Lyrics")
    clock   = pygame.time.Clock()

    VW, VH  = SH, SW
    canvas  = pygame.Surface((VW, VH))

    font_label = pygame.font.SysFont("dejavusans", 52, bold=True)
    font_name  = pygame.font.SysFont("dejavusans", 48)
    font_msg   = pygame.font.SysFont("dejavusans", 36)
    font_idx   = pygame.font.SysFont("dejavusans", 28)   # dim index font
    splash_font_name = "syne" if pygame.font.match_font("syne") else "dejavusans"
    font_splash_title = pygame.font.SysFont(splash_font_name, 64, bold=True)
    font_splash_sub = pygame.font.SysFont("dejavusans", 28)

    def show_splash():
        start = pygame.time.get_ticks()
        while pygame.time.get_ticks() - start < 1800:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)

            canvas.fill(BG_COLOR)
            elapsed = pygame.time.get_ticks() - start
            pulse = (pygame.math.Vector2(1, 0).rotate(elapsed * 0.18).x + 1) / 2
            title = font_splash_title.render("Pi Lyrics", True, TEXT_COLOR)
            subtitle = font_splash_sub.render("Loading display...", True, TEXT_COLOR)
            y = VH // 2 - title.get_height()
            canvas.blit(title, ((VW - title.get_width()) // 2, y))
            canvas.blit(subtitle, ((VW - subtitle.get_width()) // 2, y + title.get_height() + 18))
            line_y = y + title.get_height() + 7
            line_w = 120 + int(120 * pulse)
            pygame.draw.line(canvas, ACCENT, (VW // 2 - line_w, line_y),
                             (VW // 2 + line_w, line_y), 3)
            dot_x = VW // 2 - 110 + int((220 * elapsed / 1800) % 220)
            pygame.draw.circle(canvas, ACCENT, (dot_x, line_y), 8)

            rotated = pygame.transform.rotate(canvas, 90)
            screen.blit(rotated, (0, 0))
            pygame.display.flip()
            clock.tick(FPS)

    show_splash()

    # State
    files        = []
    current_idx  = 0       # index into files[]
    current_page = 0       # page within current PDF
    page_counts  = {}      # cache: filename -> page count
    cached_surf  = None
    cached_key   = None    # (filename, page_index)
    needs_reload = threading.Event()
    needs_reload.set()
    try:
        last_command_id = json.loads(CONTROL_FILE.read_text()).get("id")
    except Exception:
        last_command_id = None

    def request_reload():
        needs_reload.set()

    observer = Observer()
    observer.schedule(PDFWatcher(request_reload), str(PDF_DIR),  recursive=False)
    observer.schedule(PDFWatcher(request_reload), str(BASE_DIR), recursive=False)
    observer.start()

    def get_count(fname):
        if fname not in page_counts:
            page_counts[fname] = get_page_count(PDF_DIR / fname)
        return page_counts[fname]

    def write_status():
        if files:
            fname = files[current_idx]
            status = {
                "file": fname,
                "index": current_idx,
                "page": current_page,
                "pages": get_count(fname),
                "total": len(files),
            }
        else:
            status = {"file": None, "index": -1, "page": 0, "pages": 0, "total": 0}
        try:
            STATE_FILE.write_text(json.dumps(status))
        except Exception:
            pass

    def reload_list():
        nonlocal files, current_idx, current_page, cached_surf, cached_key, page_counts
        new_files = load_order()
        if new_files != files:
            cur = files[current_idx] if files else None
            files = new_files
            page_counts = {}           # invalidate cache
            if cur in files:
                current_idx = files.index(cur)
                # keep current_page if still valid
                if files:
                    current_page = min(current_page, get_count(files[current_idx]) - 1)
            else:
                current_idx  = 0
                current_page = 0
            cached_surf = cached_key = None
        write_status()

    def go_next():
        nonlocal current_idx, current_page, cached_surf, cached_key
        if not files:
            return
        fname = files[current_idx]
        pages = get_count(fname)
        if current_page < pages - 1:
            current_page += 1
        else:
            current_idx  = (current_idx + 1) % len(files)
            current_page = 0
        cached_surf = cached_key = None
        write_status()

    def go_prev():
        nonlocal current_idx, current_page, cached_surf, cached_key
        if not files:
            return
        if current_page > 0:
            current_page -= 1
        else:
            current_idx  = (current_idx - 1) % len(files)
            current_page = get_count(files[current_idx]) - 1
        cached_surf = cached_key = None
        write_status()

    def handle_web_control():
        nonlocal last_command_id
        try:
            command = json.loads(CONTROL_FILE.read_text())
        except Exception:
            return
        command_id = command.get("id")
        if not command_id or command_id == last_command_id:
            return
        last_command_id = command_id
        if command.get("action") == "next":
            go_next()
        elif command.get("action") == "prev":
            go_prev()

    def load_current():
        nonlocal cached_surf, cached_key
        if not files:
            cached_surf = cached_key = None
            return
        fname = files[current_idx]
        key   = (fname, current_page)
        if key == cached_key and cached_surf is not None:
            return
        try:
            avail_h = VH - NEXT_BAR_H
            cached_surf = render_pdf_page_to_surface(PDF_DIR / fname, current_page, VW, avail_h)
            cached_key  = key
        except Exception as e:
            print(f"Error rendering {fname} page {current_page}: {e}")
            cached_surf = None
            cached_key  = key

    running = True
    while running:

        # ── Events ────────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key in (pygame.K_RIGHT, pygame.K_DOWN, pygame.K_SPACE,
                                   pygame.K_PAGEDOWN, pygame.K_PERIOD, pygame.K_RETURN):
                    go_next()
                elif event.key in (pygame.K_LEFT, pygame.K_UP, pygame.K_PAGEUP,
                                   pygame.K_COMMA, pygame.K_BACKSPACE):
                    go_prev()

        # ── Reload ────────────────────────────────────────────────────────────
        if needs_reload.is_set():
            needs_reload.clear()
            reload_list()

        handle_web_control()
        load_current()

        # ── Draw onto virtual portrait canvas ─────────────────────────────────
        canvas.fill(BG_COLOR)
        avail_h = VH - NEXT_BAR_H

        if cached_surf:
            px = (VW - cached_surf.get_width())  // 2
            py = (avail_h - cached_surf.get_height()) // 2
            canvas.blit(cached_surf, (px, py))
        else:
            msg = font_msg.render(
                "No PDFs — upload via web interface" if not files else "Loading...",
                True, TEXT_COLOR
            )
            canvas.blit(msg, ((VW - msg.get_width()) // 2,
                              (avail_h - msg.get_height()) // 2))

        # ── Next bar ──────────────────────────────────────────────────────────
        bar_y = VH - NEXT_BAR_H
        pygame.draw.rect(canvas, BAR_COLOR, (0, bar_y, VW, NEXT_BAR_H))
        pygame.draw.line(canvas, ACCENT, (0, bar_y), (VW, bar_y), 3)

        bar_cx = VW // 2
        bar_cy = bar_y + NEXT_BAR_H // 2

        if files and len(files) > 1:
            # Determine next label: next PDF (first page)
            next_file_idx = current_idx + 1
            next_page_for_next = 0
            cur_pages = get_count(files[current_idx])
            # If we're mid-PDF, "next" is the next page of this PDF
            if current_page < cur_pages - 1:
                next_name   = files[current_idx]
                next_suffix = f"  (p{current_page + 2}/{cur_pages})"
            elif next_file_idx < len(files):
                next_name   = files[next_file_idx]
                next_suffix = ""
            else:
                next_name = None
                next_suffix = ""

            if next_name is None:
                only = font_name.render("--- end of queue ---", True, ACCENT)
                canvas.blit(only, ((VW - only.get_width()) // 2,
                                   bar_cy - only.get_height() // 2))
            else:
                display_name = next_name[:-4] if next_name.lower().endswith(".pdf") else next_name
                display_name = display_name.replace("_", " ")
                label    = font_label.render("Next:  ", True, ACCENT)
                nxt_txt  = font_name.render(display_name + next_suffix, True, TEXT_COLOR)
                total_w  = label.get_width() + nxt_txt.get_width()
                x = (VW - total_w) // 2
                y = bar_cy - label.get_height() // 2
                canvas.blit(label,   (x, y))
                canvas.blit(nxt_txt, (x + label.get_width(),
                                      y + (label.get_height() - nxt_txt.get_height()) // 2))

        elif files and len(files) == 1:
            only = font_name.render("--- end of queue ---", True, ACCENT)
            canvas.blit(only, ((VW - only.get_width()) // 2,
                               bar_cy - only.get_height() // 2))

        # ── Dim index labels in the bar ───────────────────────────────────────
        MARGIN = 20
        if files:
            # Overall slide index (left side)  e.g.  2 / 5
            overall_txt = font_idx.render(f"{current_idx + 1} / {len(files)}", True, DIM_COLOR)
            oy = bar_cy - overall_txt.get_height() // 2
            canvas.blit(overall_txt, (MARGIN, oy))

            # Per-PDF page index (right side)  e.g.  p 2 / 3  — only if >1 page
            fname   = files[current_idx]
            n_pages = get_count(fname)
            if n_pages > 1:
                page_txt = font_idx.render(f"p {current_page + 1} / {n_pages}", True, DIM_COLOR)
                px2 = VW - MARGIN - page_txt.get_width()
                canvas.blit(page_txt, (px2, oy))

        # ── Rotate canvas 90° clockwise and blit to real screen ───────────────
        rotated = pygame.transform.rotate(canvas, 90)
        screen.blit(rotated, (0, 0))

        pygame.display.flip()
        clock.tick(FPS)

    observer.stop()
    observer.join()
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
