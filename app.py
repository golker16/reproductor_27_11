import sys
import random
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton, QHeaderView, QToolButton,
    QLineEdit, QAbstractItemView
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


# ---------------------------------------------
# Utilidades de paths (dev vs PyInstaller onedir)
# ---------------------------------------------
def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def asset_path(name: str) -> Path:
    return base_dir() / "assets" / name

def canciones_dir() -> Path:
    return base_dir() / "canciones"


# ---------------------------------------------
# Parsing de nombre de archivo -> (artista, canción)
# Espera formato: "Artista - Canción.ext"
# ---------------------------------------------
def parse_nombre_archivo(filename: str):
    name = Path(filename).stem
    if " - " in name:
        artista, cancion = name.split(" - ", 1)
        return artista.strip(), cancion.strip()
    return "(Desconocido)", name.strip()


# Archivos de audio soportados
EXTS = {".mp3", ".wav", ".m4a", ".aac", ".wma", ".ogg"}


class MusicPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Reproductor — Gabriel Golker")

        # Ícono de ventana: assets/app.png
        icon_png = asset_path("app.png")
        if icon_png.exists():
            self.setWindowIcon(QIcon(str(icon_png)))

        # Datos y estado
        self.tracks = []           # dicts: {path, artista, cancion}
        self.current_index = -1
        self.random_mode = False
        self.random_queue = []     # cola de índices para modo random
        self.search_text = ""

        # UI
        self._build_ui()

        # Player
        self.audio = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio)

        # Ir al siguiente al terminar
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

        # Cargar canciones
        self._ensure_canciones_dir()
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
        # Si quieres selección de una sola fila:
        # self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
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

        self.btn_open_folder = QToolButton()
        self.btn_open_folder.setText("📂 Abrir carpeta canciones")
        self.btn_open_folder.clicked.connect(self._on_open_folder)
        controls.addWidget(self.btn_open_folder)

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
    # Canciones
    # -------------------------
    def _ensure_canciones_dir(self):
        d = canciones_dir()
        d.mkdir(parents=True, exist_ok=True)

    def _scan_and_load(self):
        self.tracks.clear()
        d = canciones_dir()
        for entry in sorted(d.iterdir()):
            if entry.is_file() and entry.suffix.lower() in EXTS:
                artista, cancion = parse_nombre_archivo(entry.name)
                self.tracks.append({
                    "path": entry.resolve(),
                    "artista": artista,
                    "cancion": cancion
                })
        # Orden base: por artista, luego canción
        self.tracks.sort(key=lambda t: (t["artista"].lower(), t["cancion"].lower()))
        self._refresh_view()

        if not self.tracks:
            self.statusBar().showMessage(
                "No se encontraron canciones. Pon tus archivos en 'canciones' junto al .exe/.py",
                8000
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
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.btn_play.setText("▶ Play")
        else:
            if self.current_index < 0 and self.tracks:
                if self.random_mode:
                    pool = self._visible_pool_indices() or list(range(len(self.tracks)))
                    self._prepare_random_queue(pool=pool, exclude_index=None)
                    nxt = self._get_next_random_index()
                    if nxt is None:
                        nxt = pool[0]
                    self._play_index(nxt)
                else:
                    # Empieza por el primero visible (filtro + orden actual)
                    pool = self._visible_pool_indices() or list(range(len(self.tracks)))
                    self._play_index(pool[0])
            else:
                self.player.play()
                self.btn_play.setText("⏸ Pause")

    def _on_stop(self):
        self.player.stop()
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
                # fallback: siguiente secuencial dentro del pool visible
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

    def _on_open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(canciones_dir())))

    def _play_index(self, index: int):
        if not (0 <= index < len(self.tracks)):
            return
        self.current_index = index
        track = self.tracks[index]
        url = QUrl.fromLocalFile(str(track["path"]))
        self.player.setSource(url)
        self.player.play()
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

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._on_next()


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

