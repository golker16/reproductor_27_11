import sys
import random
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton, QHeaderView, QToolButton,
    QLineEdit, QAbstractItemView
)

# YouTube invisible player (QtWebEngine)
from PySide6.QtWebEngineWidgets import QWebEngineView


# ---------------------------------------------
# Utilidades de paths (dev vs PyInstaller onedir)
# ---------------------------------------------
def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def asset_path(name: str) -> Path:
    return base_dir() / "assets" / name


def tracks_json_path() -> Path:
    return base_dir() / "tracks.json"


# ---------------------------------------------
# Reproductor
# ---------------------------------------------
class MusicPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Reproductor — Gabriel Golker")

        # Ícono de ventana: assets/app.png
        icon_png = asset_path("app.png")
        if icon_png.exists():
            self.setWindowIcon(QIcon(str(icon_png)))

        # Datos y estado
        self.tracks = []           # dicts: {artista, cancion, url}
        self.current_index = -1
        self.random_mode = False
        self.random_queue = []     # cola de índices para modo random
        self.search_text = ""

        # UI
        self._build_ui()

        # Player invisible (YouTube IFrame)
        self.web = QWebEngineView(self)
        self.web.setFixedSize(1, 1)
        self.web.hide()

        html = """
<!doctype html><html><body style="margin:0;background:black;">
<div id="player"></div>
<script>
var tag=document.createElement('script');
tag.src="https://www.youtube.com/iframe_api";
document.body.appendChild(tag);

var player=null;
var pending=null;

function onYouTubeIframeAPIReady(){
  player = new YT.Player('player', {
    height:'1', width:'1',
    videoId:'',
    playerVars:{autoplay:0,controls:0,fs:0,rel:0,iv_load_policy:3,playsinline:1},
    events:{onReady: function(){ if(pending){ playId(pending); pending=null; } }}
  });
}

function playId(id){
  if(!player){ pending=id; return; }
  player.loadVideoById(id);
  player.playVideo();
}
function pauseVid(){ if(player) player.pauseVideo(); }
function stopVid(){ if(player) player.stopVideo(); }
</script></body></html>
"""
        self.web.setHtml(html, QUrl("https://www.youtube.com"))

        # Cargar canciones desde tracks.json
        self._scan_and_load()

    # -------------------------
    # UI
    # -------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # Buscador
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar por artista o canción…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_input)
        root.addLayout(search_row)

        # Tabla Artista / Canción
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Artista", "Canción"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        root.addWidget(self.table, stretch=1)

        # Controles
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.btn_play = QPushButton("▶ Play")
        self.btn_play.clicked.connect(self._on_play_pause)
        controls.addWidget(self.btn_play)

        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.clicked.connect(self._on_stop)
        controls.addWidget(self.btn_stop)

        self.btn_next = QPushButton("⏭ Siguiente")
        self.btn_next.clicked.connect(self._on_next)
        controls.addWidget(self.btn_next)

        self.btn_random = QToolButton()
        self.btn_random.setText("🔀 Random")
        self.btn_random.setCheckable(True)
        self.btn_random.toggled.connect(self._on_toggle_random)
        controls.addWidget(self.btn_random)

        self.btn_open_file = QToolButton()
        self.btn_open_file.setText("📝 Abrir tracks.json")
        self.btn_open_file.clicked.connect(self._on_open_tracks_json)
        controls.addWidget(self.btn_open_file)

        controls.addStretch(1)
        root.addLayout(controls)

        # Footer
        footer = QLabel("© 2025 Gabriel Golker")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size: 11px; opacity: 0.8;")
        root.addWidget(footer)

        self.resize(900, 560)
        self.setMinimumSize(720, 420)

    # -------------------------
    # Cargar tracks desde JSON
    # -------------------------
    def _scan_and_load(self):
        self.tracks.clear()
        p = tracks_json_path()
        if not p.exists():
            # Plantilla para que el usuario entienda el formato
            p.write_text(
                json.dumps(
                    [
                        {
                            "artista": "Daft Punk",
                            "cancion": "One More Time",
                            "url": "https://www.youtube.com/watch?v=FGBhQbmPwH8",
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("tracks.json debe contener una lista JSON.")
        except Exception as e:
            self.statusBar().showMessage(f"Error leyendo tracks.json: {e}", 8000)
            data = []

        for t in data:
            if not isinstance(t, dict):
                continue
            self.tracks.append(
                {
                    "artista": (t.get("artista") or "(Desconocido)").strip(),
                    "cancion": (t.get("cancion") or "(Sin título)").strip(),
                    "url": (t.get("url") or "").strip(),
                }
            )

        self.tracks.sort(key=lambda x: (x["artista"].lower(), x["cancion"].lower()))
        self._refresh_view()

        if not self.tracks:
            self.statusBar().showMessage(
                "No hay tracks. Edita 'tracks.json' y pon enlaces de YouTube.",
                8000,
            )

    # -------------------------
    # Vista / filtro / tabla
    # -------------------------
    def _on_search_changed(self, text: str):
        self.search_text = text.strip()
        self._refresh_view()

    def _filtered_indices(self):
        """Índices de self.tracks que pasan el filtro actual."""
        if not self.search_text:
            return list(range(len(self.tracks)))
        q = self.search_text.lower()
        indices = []
        for i, t in enumerate(self.tracks):
            if q in t["artista"].lower() or q in t["cancion"].lower():
                indices.append(i)
        return indices

    def _visible_pool_indices(self):
        """Índices (self.tracks) en el orden visible actual de la tabla."""
        rows = self.table.rowCount()
        pool = []
        for r in range(rows):
            item = self.table.item(r, 0)  # artista
            if not item:
                continue
            idx = item.data(Qt.UserRole)
            if isinstance(idx, int):
                pool.append(idx)
        return pool

    def _refresh_view(self):
        indices = self._filtered_indices()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(indices))
        for row, idx in enumerate(indices):
            t = self.tracks[idx]
            it_artist = QTableWidgetItem(t["artista"])
            it_song = QTableWidgetItem(t["cancion"])
            # Guardamos el índice real en UserRole
            it_artist.setData(Qt.UserRole, idx)
            it_song.setData(Qt.UserRole, idx)
            self.table.setItem(row, 0, it_artist)
            self.table.setItem(row, 1, it_song)
        self.table.setSortingEnabled(True)
        # Mantener selección si la pista actual está visible
        self._select_row_for_index(self.current_index)

    # -------------------------
    # YouTube helpers
    # -------------------------
    def _youtube_id(self, url: str):
        u = urlparse(url)
        host = (u.netloc or "").lower()

        if "youtu.be" in host:
            return u.path.strip("/") or None

        if "youtube.com" in host:
            if u.path == "/watch":
                return parse_qs(u.query).get("v", [None])[0]
            if u.path.startswith("/shorts/"):
                parts = u.path.split("/")
                return parts[2] if len(parts) > 2 else None
            if u.path.startswith("/embed/"):
                parts = u.path.split("/")
                return parts[2] if len(parts) > 2 else None

        return None

    # -------------------------
    # Reproducción
    # -------------------------
    def _on_double_click(self, row, _col):
        item = self.table.item(row, 0) or self.table.item(row, 1)
        if not item:
            return
        idx = item.data(Qt.UserRole)
        if isinstance(idx, int):
            self._play_index(idx)

    def _on_play_pause(self):
        # Si no hay track seleccionado, elige uno como antes (respeta filtro + orden + random)
        if self.current_index < 0 and self.tracks:
            if self.random_mode:
                pool = self._visible_pool_indices() or list(range(len(self.tracks)))
                self._prepare_random_queue(pool=pool, exclude_index=None)
                nxt = self._get_next_random_index()
                if nxt is None:
                    nxt = pool[0]
                self._play_index(nxt)
            else:
                pool = self._visible_pool_indices() or list(range(len(self.tracks)))
                self._play_index(pool[0])
            return

        # Toggle simple basado en el texto del botón
        if self.btn_play.text().startswith("⏸"):
            self.web.page().runJavaScript("pauseVid()")
            self.btn_play.setText("▶ Play")
        else:
            if 0 <= self.current_index < len(self.tracks):
                self._play_index(self.current_index)

    def _on_stop(self):
        self.web.page().runJavaScript("stopVid()")
        self.btn_play.setText("▶ Play")

    def _on_next(self):
        if not self.tracks:
            return
        if self.random_mode:
            if not self.random_queue:
                pool = self._visible_pool_indices() or list(range(len(self.tracks)))
                self._prepare_random_queue(pool=pool, exclude_index=self.current_index)
            nxt = self._get_next_random_index()
            if nxt is None:
                pool = self._visible_pool_indices() or list(range(len(self.tracks)))
                try:
                    pos = pool.index(self.current_index)
                    nxt = pool[(pos + 1) % len(pool)]
                except ValueError:
                    nxt = pool[0]
            self._play_index(nxt)
        else:
            pool = self._visible_pool_indices() or list(range(len(self.tracks)))
            if self.current_index in pool:
                pos = pool.index(self.current_index)
                nxt = pool[(pos + 1) % len(pool)]
            else:
                nxt = pool[0]
            self._play_index(nxt)

    def _on_toggle_random(self, checked: bool):
        self.random_mode = checked
        if checked:
            pool = self._visible_pool_indices() or list(range(len(self.tracks)))
            self._prepare_random_queue(pool=pool, exclude_index=self.current_index)
        else:
            self.random_queue.clear()

    def _prepare_random_queue(self, pool, exclude_index):
        indices = list(pool)
        if exclude_index is not None and exclude_index in indices and len(indices) > 1:
            indices.remove(exclude_index)
        random.shuffle(indices)
        self.random_queue = indices

    def _get_next_random_index(self):
        if not self.random_queue:
            return None
        return self.random_queue.pop(0)

    def _play_index(self, index: int):
        if not (0 <= index < len(self.tracks)):
            return
        self.current_index = index
        track = self.tracks[index]

        vid = self._youtube_id(track["url"])
        if not vid:
            self.statusBar().showMessage("URL inválida de YouTube para esta pista.", 5000)
            return

        # Escapar comillas simples en el improbable caso de que entren en el ID (no debería)
        vid = vid.replace("'", "\\'")
        self.web.page().runJavaScript(f"playId('{vid}')")

        self.btn_play.setText("⏸ Pause")
        self._update_title()
        self._select_row_for_index(index)

    def _select_row_for_index(self, idx: int):
        if idx < 0:
            return
        rows = self.table.rowCount()
        for r in range(rows):
            item = self.table.item(r, 0) or self.table.item(r, 1)
            if not item:
                continue
            if item.data(Qt.UserRole) == idx:
                self.table.setCurrentCell(r, 0)
                return

    def _update_title(self):
        if 0 <= self.current_index < len(self.tracks):
            t = self.tracks[self.current_index]
            self.setWindowTitle(f"{t['artista']} — {t['cancion']}  |  Reproductor — Gabriel Golker")
        else:
            self.setWindowTitle("Reproductor — Gabriel Golker")

    # -------------------------
    # Utilidades
    # -------------------------
    def _on_open_tracks_json(self):
        # Abre el archivo para editarlo rápido (se crea si no existe)
        p = tracks_json_path()
        if not p.exists():
            p.write_text("[]", encoding="utf-8")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    # Para refrescar la lista si editas el JSON mientras la app está abierta:
    # podrías añadir un botón "🔄 Recargar" y llamar self._scan_and_load()


def main():
    app = QApplication(sys.argv)

    # QDarkStyle (si está instalado)
    try:
        import qdarkstyle
        app.setStyleSheet(qdarkstyle.load_stylesheet_pyside6())
    except Exception:
        pass

    w = MusicPlayer()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

