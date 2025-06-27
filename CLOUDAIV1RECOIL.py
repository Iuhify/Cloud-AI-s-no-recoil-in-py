import sys
import threading
import time
import random
import winsound
import json
import os
import win32api
import win32con
from typing import Optional, List, Dict

try:
    import serial
    from serial.tools import list_ports
    HAVE_PYSERIAL = True
except ImportError:
    HAVE_PYSERIAL = False

from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
                             QHBoxLayout, QSlider, QCheckBox, QColorDialog)
from PyQt5.QtCore import (Qt, QPoint, QRect, QRectF, QPropertyAnimation, QTimer,
                          QUrl, QEasingCurve, pyqtSignal, QObject, QByteArray, QSize)
from PyQt5.QtGui import (QFont, QColor, QPainter, QPainterPath, QPixmap, QIcon,
                         QDesktopServices, QPen)
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt5.QtSvg import QSvgRenderer

IMGUR_CHECK_URL = 'https://i.imgur.com/i6bI5Xn.png'
IMGUR_CLOSE_URL = 'https://i.imgur.com/cC8a7sp.png'
DISCORD_INVITE_URL = 'https://discord.gg/jEdCd7Vfqt'

DISCORD_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 127.14 96.36">
  <path fill="#5865F2" d="M107.7,8.07A105.15,105.15,0,0,0,81.47,0a72.06,72.06,0,0,0-3.36,6.83A97.68,97.68,0,0,0,49,6.83,72.37,72.37,0,0,0,45.64,0,105.89,105.89,0,0,0,19.39,8.09C2.79,32.65-1.71,56.6.54,80.21h0A105.73,105.73,0,0,0,32.71,96.36,77.7,77.7,0,0,0,39.6,85.25a68.42,68.42,0,0,1-10.85-5.18c.91-.66,1.8-1.34,2.66-2a75.57,75.57,0,0,0,64.32,0c.85.71,1.76,1.39,2.66,2a68.68,68.68,0,0,1-10.87,5.19,77,77,0,0,0,6.89,11.1A105.25,105.25,0,0,0,126.6,80.22h0C129.24,52.84,122.09,29.11,107.7,8.07ZM42.45,65.69C36.18,65.69,31,60,31,53s5-12.74,11.43-12.74S54,46,53.89,53,48.84,65.69,42.45,65.69Zm42.24,0C78.41,65.69,73.25,60,73.25,53s5-12.74,11.44-12.74S96.23,46,96.12,53,91.08,65.69,84.69,65.69Z"/>
</svg>
"""

STYLES = {
    "window_background": QColor(20, 20, 20, 240),
    "panel": "background: #1A1A1A; border-radius: 8px;",
    "title": "color: #FFFFFF; font-size: 16px; font-weight: bold;",
    "fps_label": "color: #888888; font-size: 12px;",
    "makcu_status_ok": "color: #4CAF50; font-size: 11px; font-weight: bold;",
    "makcu_status_err": "color: #F44336; font-size: 11px; font-weight: bold;",
    "makcu_status_info": "color: #2196F3; font-size: 11px; font-weight: bold;",
    "activity_on": "background-color: #4CAF50; border-radius: 4px;",
    "activity_off": "background-color: #444444; border-radius: 4px;",
    "label": "color: #888888; font-size: 12px;",
    "value_label": "color: #FFFFFF; font-size: 12px;",
    "checkbox": """
        QCheckBox { color: #FFFFFF; font-size: 13px; }
        QCheckBox::indicator {
            width: 20px; height: 20px;
            background: #252525;
            border: 1px solid #404040;
            border-radius: 4px;
        }""",
    "slider": """
        QSlider::groove:horizontal {
            height: 3px; background: #2A2A2A; border-radius: 1px;
        }
        QSlider::sub-page:horizontal {
            background: #BF40BF; border-radius: 1px;
        }
        QSlider::handle:horizontal {
            background: #FFFFFF; width: 14px; height: 14px;
            margin: -6px 0; border-radius: 7px;
        }"""
}

def svg_to_pixmap(svg_data: str, size: QSize) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg_data.encode('utf-8')))
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    return pixmap

def distribute_movement(total_pixels: int, steps: int) -> List[int]:
    if steps <= 0:
        return []
    base_move = total_pixels // steps
    remainder = total_pixels % steps
    moves = [base_move] * steps
    for i in range(remainder):
        moves[i] += 1
    return moves

class AsyncImageLoader(QObject):
    _instance = None
    
    @staticmethod
    def instance():
        if AsyncImageLoader._instance is None:
            AsyncImageLoader._instance = AsyncImageLoader()
        return AsyncImageLoader._instance

    def __init__(self):
        super().__init__()
        self.manager = QNetworkAccessManager()
        self.cache: Dict[str, QPixmap] = {}
        self.subscribers: Dict[str, List[QWidget]] = {}
        self.manager.finished.connect(self._on_finished)

    def _on_finished(self, reply):
        url = reply.url().toString()
        if reply.error():
            print(f"[Network Error] Could not load image from {url}: {reply.errorString()}")
            self.cache[url] = QPixmap()
        else:
            pixmap = QPixmap()
            pixmap.loadFromData(reply.readAll())
            self.cache[url] = pixmap
        
        if url in self.subscribers:
            for widget in self.subscribers[url]:
                if widget:
                    widget.update()
            del self.subscribers[url]
        reply.deleteLater()

    def get(self, url: str, subscriber_widget: QWidget) -> Optional[QPixmap]:
        if url in self.cache:
            return self.cache[url]
        
        if url not in self.subscribers:
            self.subscribers[url] = []
            self.manager.get(QNetworkRequest(QUrl(url)))
        
        if subscriber_widget not in self.subscribers[url]:
            self.subscribers[url].append(subscriber_widget)
            
        return None

class Config:
    CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'config.json')
    DEFAULTS = {
        'recoil_compensation': True,
        'bloom_reduction': False,
        'require_ads': True,
        'show_crosshair': False,
        'recoil_strength': 11,
        'smoothing': 3,
        'bloom_intensity': 2,
        'crosshair_color': '#BF40BF',
        'crosshair_size': 5,
        'crosshair_thickness': 2,
        'use_makcu': False
    }

    @classmethod
    def load(cls) -> dict:
        try:
            if os.path.exists(cls.CONFIG_PATH):
                with open(cls.CONFIG_PATH, 'r') as f:

                    return {**cls.DEFAULTS, **json.load(f)}
        except (json.JSONDecodeError, IOError) as e:
            print(f"[Config Error] Could not load config file: {e}")
        return cls.DEFAULTS.copy()

    @classmethod
    def save(cls, settings: dict):
        try:
            with open(cls.CONFIG_PATH, 'w') as f:
                json.dump(settings, f, indent=4)
        except IOError as e:
            print(f"[Config Error] Could not save config file: {e}")

class AppState:
    def __init__(self, initial_settings: dict):
        self.lock = threading.Lock()
        self.settings = initial_settings.copy()
        self.fps = 0
        self.running = True

    def update(self, new_settings: dict):
        with self.lock:
            self.settings.update(new_settings)

    def get_full_config(self) -> dict:
        with self.lock:
            return self.settings.copy()

class MakcuController:
    
    DEVICE_PROFILES = {
        "makcu": {
            "HANDSHAKE_COMMAND": b"km.version()\r\n",
            "HANDSHAKE_RESPONSE_KEYWORDS": ["km.makcu", "km"],
            "BAUDRATE_HIGH": 4000000,
            "INIT_SEQUENCE": bytes.fromhex("DE AD 05 00 A5 00 09 3D 00"),
            "INIT_COMMAND": b"km.buttons(1)\r\n"
        },
        "otherbox": {
            "HANDSHAKE_COMMAND": b"box.version()\r\n",
            "HANDSHAKE_RESPONSE_KEYWORDS": ["otherbox"],
            "BAUDRATE_HIGH": 115200,
            "INIT_SEQUENCE": b"",
            "INIT_COMMAND": b""
        }
    }
    BAUDRATE_DEFAULT = 115200
    MOVE_CMD_TEMPLATE = b"km.move(%d,%d)\r"

    def __init__(self):
        self.serial: Optional[serial.Serial] = None
        self.connected = False
        self.port_name: Optional[str] = None
    
    def connect(self) -> bool:
        if not HAVE_PYSERIAL:
            return False
        
        self.close()
        
        ports = list_ports.comports()
        for port in ports:
            for profile_name, profile in self.DEVICE_PROFILES.items():
                try:
                    self.serial = serial.Serial(
                        port.device, 
                        self.BAUDRATE_DEFAULT, 
                        timeout=0.5, 
                        write_timeout=0.1
                    )
                    time.sleep(0.5)
                    
                    self.serial.write(profile["HANDSHAKE_COMMAND"])
                    time.sleep(0.2)
                    response = self._read_response()
                    
                    if any(keyword in response for keyword in profile["HANDSHAKE_RESPONSE_KEYWORDS"]):
                        print(f"[MAKCU] Found {profile_name} on {port.device}. Finalizing connection...")
                        self._finalize_connection(port.device, profile)
                        return True
                    else:
                        self.serial.close()
                except (OSError, serial.SerialException):
                    if self.serial and self.serial.is_open:
                        self.serial.close()
                    continue
        
        print("[MAKCU] No supported hardware found.")
        return False

    def _finalize_connection(self, port_name: str, profile: dict):
        self.port_name = port_name
        
        if profile["INIT_SEQUENCE"]:
            self.serial.write(profile["INIT_SEQUENCE"])
        
        baud_high = profile["BAUDRATE_HIGH"]
        if baud_high != self.BAUDRATE_DEFAULT:
            self.serial.baudrate = baud_high
            
        if profile.get("INIT_COMMAND"):
            self.serial.write(profile["INIT_COMMAND"])
            
        self.serial.timeout = 0.001
        self.serial.write_timeout = 0.001
        self.connected = True
        print(f"[MAKCU] Connected to {self.port_name} at {self.serial.baudrate} baud.")

    def _read_response(self) -> str:
        lines = []
        try:
            while self.serial and self.serial.in_waiting:
                line = self.serial.readline().decode(errors="ignore").strip()
                if line:
                    lines.append(line)
        except Exception as e:
            print(f"[MAKCU Read Error] {e}")
        return " ".join(lines).lower()

    def move(self, x: int, y: int) -> bool:
        if not self.connected or not self.serial:
            return False
        
        if x == 0 and y == 0:
            return True
        
        command = self.MOVE_CMD_TEMPLATE % (int(x), int(y))
        
        try:
            self.serial.write(command)
            return True
        except (OSError, serial.SerialException) as e:
            print(f"[MAKCU Write Error] Connection lost: {e}")
            self.connected = False
            return False

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.connected = False
        self.port_name = None
        print("[MAKCU] Connection closed.")


class CrosshairWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint |  
            Qt.WindowStaysOnTopHint |  
            Qt.Tool                     
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(QApplication.desktop().screenGeometry())
        self.config = {}

    def update_crosshair(self, config: dict):
        self.config = config
        self.update()

    def paintEvent(self, event):
        if not self.config:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        center = self.rect().center()
        color = QColor(self.config['crosshair_color'])
        size = self.config['crosshair_size']
        thickness = self.config['crosshair_thickness']
        gap = 2

        pen = QPen(color, thickness, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)

        painter.drawLine(center.x() - size - gap, center.y(), center.x() - gap, center.y()) 
        painter.drawLine(center.x() + gap, center.y(), center.x() + size + gap, center.y()) 
        painter.drawLine(center.x(), center.y() - size - gap, center.x(), center.y() - gap) 
        painter.drawLine(center.x(), center.y() + gap, center.x(), center.y() + size + gap) 
        
        painter.drawPoint(center)

class ModernSlider(QSlider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet(STYLES["slider"])

class CustomCheckBox(QCheckBox):
    def __init__(self, text: str = '', parent=None):
        super().__init__(text, parent)
        self.check_pixmap = AsyncImageLoader.instance().get(IMGUR_CHECK_URL, self)

    def paintEvent(self, event):
        if self.check_pixmap is None:
            self.check_pixmap = AsyncImageLoader.instance().get(IMGUR_CHECK_URL, self)

        super().paintEvent(event)

        if self.isChecked() and self.check_pixmap and not self.check_pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            box_size = 18
            y_offset = (self.height() - box_size) / 2
            target_rect = QRect(2, int(y_offset), box_size, box_size)
            
            image = self.check_pixmap.scaled(
                target_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            painter.drawPixmap(target_rect, image)



class CloudRecoil(QWidget):
    fps_updated = pyqtSignal(float)
    makcu_status_updated = pyqtSignal(str, str)
    makcu_activity_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        
        self.config = Config.load()
        self.app_state = AppState(self.config)
        self.mouse_controller = MakcuController() if HAVE_PYSERIAL else None
        
        self.checkboxes: Dict[str, QCheckBox] = {}
        self.sliders: Dict[str, QSlider] = {}
        self.crosshair_sliders: Dict[str, QSlider] = {}

        self.activity_timer = QTimer(self)
        self.activity_timer.setSingleShot(True)
        self.animation: Optional[QPropertyAnimation] = None
        self.crosshair: Optional[CrosshairWindow] = None
        self.drag_pos = QPoint()

        self.init_ui()
        self.init_animation()
        self.init_crosshair()
        self.init_threads()

    def recoil_loop(self):

        while self.app_state.running:
            self.app_state.fps += 1
            config = self.app_state.get_full_config()

            lmb_pressed = win32api.GetAsyncKeyState(win32con.VK_LBUTTON) < 0
            ads_pressed = win32api.GetAsyncKeyState(win32con.VK_RBUTTON) < 0

            is_recoil_active = (
                lmb_pressed and 
                config['recoil_compensation'] and
                (not config['require_ads'] or ads_pressed)
            )

            if is_recoil_active:
                smoothing = max(1, config['smoothing'])
                dy_total = config['recoil_strength']
                dx_total = 0
                if config['bloom_reduction']:
                    dx_total = random.randint(-config['bloom_intensity'], config['bloom_intensity'])
                
                y_moves = distribute_movement(dy_total, smoothing)
                x_moves = distribute_movement(dx_total, smoothing)

                use_makcu = (config.get('use_makcu', False) and 
                             self.mouse_controller and self.mouse_controller.connected)
                
                for i in range(smoothing):
                    dx = x_moves[i]
                    dy = y_moves[i]
                    
                    if use_makcu:
                        if self.mouse_controller.move(dx, dy):
                            self.makcu_activity_signal.emit()
                    else:
                        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, dx, dy, 0, 0)
                    
                    time.sleep(0.001)

            time.sleep(0.002)


    def init_ui(self):
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(400, 580)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 15, 20, 20)
        main_layout.setSpacing(15)

        main_layout.addLayout(self._create_header())
        main_layout.addWidget(self._create_checkbox_panel())
        main_layout.addWidget(self._create_slider_panel())
        main_layout.addWidget(self._create_crosshair_panel())
        
        self.fps_updated.connect(lambda fps: self.fps_label.setText(f'FPS: {fps:.0f}'))
        self.makcu_status_updated.connect(self.update_makcu_status_label)
        self.makcu_activity_signal.connect(self.on_makcu_activity)
        self.activity_timer.timeout.connect(self.on_activity_timeout)
        
    def init_animation(self):
        self.animation = QPropertyAnimation(self, b'windowOpacity')
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.setDuration(500)

    def init_crosshair(self):
        self.crosshair = CrosshairWindow()
        self.crosshair.update_crosshair(self.config)
        if self.config['show_crosshair']:
            self.crosshair.show()

    def init_threads(self):
        if self.checkboxes['use_makcu'].isChecked():
            self.on_makcu_toggled(Qt.Checked)
        
        self.recoil_thread = threading.Thread(target=self.recoil_loop, daemon=True)
        self.recoil_thread.start()
        self.fps_timer = QTimer(self)
        self.fps_timer.timeout.connect(self.update_fps_label)
        self.fps_timer.start(1000)


    def _create_header(self) -> QHBoxLayout:
        header_layout = QHBoxLayout()
        
        title = QLabel('CLOUD v1')
        title.setFont(QFont('Segoe UI', 10, QFont.Bold))
        title.setStyleSheet(STYLES["title"])

        self.fps_label = QLabel('FPS: 0')
        self.fps_label.setStyleSheet(STYLES["fps_label"])

        makcu_layout = QHBoxLayout()
        makcu_layout.setSpacing(5)
        makcu_layout.setAlignment(Qt.AlignRight)
        self.activity_indicator = QLabel()
        self.activity_indicator.setFixedSize(8, 8)
        self.on_activity_timeout()
        self.makcu_status_label = QLabel("MAKCU: Disabled")
        self.update_makcu_status_label("MAKCU: Disabled", "makcu_status_err")
        makcu_layout.addWidget(self.activity_indicator)
        makcu_layout.addWidget(self.makcu_status_label)

        status_layout = QVBoxLayout()
        status_layout.setSpacing(0)
        status_layout.addWidget(self.fps_label, 0, Qt.AlignRight)
        status_layout.addLayout(makcu_layout)

        discord_pixmap = svg_to_pixmap(DISCORD_SVG, QSize(22, 22))
        discord_button = QPushButton(QIcon(discord_pixmap), '', self)
        discord_button.setToolTip('Join Discord')
        discord_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DISCORD_INVITE_URL)))
        discord_button.setFlat(True)
        discord_button.setCursor(Qt.PointingHandCursor)

        self.close_btn = QPushButton(self)
        self.close_btn.setToolTip('Close')
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setFlat(True)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.update_close_button_icon()
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addLayout(status_layout)
        header_layout.addWidget(discord_button)
        header_layout.addWidget(self.close_btn)
        return header_layout

    def _create_checkbox_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(STYLES["panel"])
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(8)

        checkbox_definitions = [
            ('Recoil Compensation', 'recoil_compensation'),
            ('Bloom Reduction', 'bloom_reduction'),
            ('Require ADS', 'require_ads'),
            ('Show Crosshair', 'show_crosshair'),
            ('Use MAKCU Hardware (not WORKIN)', 'use_makcu')
        ]

        for text, key in checkbox_definitions:
            checkbox = CustomCheckBox(text)
            checkbox.setChecked(self.config.get(key, False))
            checkbox.setStyleSheet(STYLES["checkbox"])

            if key == 'use_makcu':
                checkbox.stateChanged.connect(self.on_makcu_toggled)
                if not HAVE_PYSERIAL:
                    checkbox.setChecked(False)
                    checkbox.setEnabled(False)
                    checkbox.setToolTip("Please install 'pyserial' to use this feature.")
            else:
                checkbox.stateChanged.connect(self.update_settings)

            layout.addWidget(checkbox)
            self.checkboxes[key] = checkbox
        
        self.checkboxes['show_crosshair'].stateChanged.connect(
            lambda state: self.crosshair.show() if state == Qt.Checked else self.crosshair.hide()
        )
        return panel

    def _create_slider_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(STYLES["panel"])
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        slider_definitions = [
            ('Recoil Strength', 'recoil_strength', 1, 20),
            ('Smoothing', 'smoothing', 1, 10),
            ('Bloom Intensity', 'bloom_intensity', 0, 10)
        ]

        for text, key, min_val, max_val in slider_definitions:
            slider = ModernSlider(Qt.Horizontal)
            slider.setRange(min_val, max_val)
            slider.setValue(self.config.get(key, 0))
            slider_group = self._create_slider_group(text, slider)
            layout.addLayout(slider_group)
            self.sliders[key] = slider
            
        return panel

    def _create_crosshair_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(STYLES["panel"])
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        color_layout = QHBoxLayout()
        color_label = QLabel("Crosshair Color")
        color_label.setStyleSheet(STYLES["label"])
        self.color_button = QPushButton(self)
        self.color_button.setFixedSize(80, 24)
        self.color_button.clicked.connect(self.pick_color)
        self._update_color_button(self.config['crosshair_color'])
        
        color_layout.addWidget(color_label)
        color_layout.addStretch()
        color_layout.addWidget(self.color_button)
        layout.addLayout(color_layout)
        
        slider_definitions = [
            ('Crosshair Size', 'crosshair_size', 1, 25),
            ('Crosshair Thickness', 'crosshair_thickness', 1, 10)
        ]
        
        for text, key, min_val, max_val in slider_definitions:
            slider = ModernSlider(Qt.Horizontal)
            slider.setRange(min_val, max_val)
            slider.setValue(self.config.get(key, 0))
            slider_group = self._create_slider_group(text, slider)
            layout.addLayout(slider_group)
            self.crosshair_sliders[key] = slider

        return panel

    def _create_slider_group(self, text: str, slider: QSlider) -> QVBoxLayout:
        h_layout = QHBoxLayout()
        v_layout = QVBoxLayout()
        
        label = QLabel(text)
        label.setStyleSheet(STYLES["label"])
        
        value_label = QLabel(str(slider.value()))
        value_label.setStyleSheet(STYLES["value_label"])
        value_label.setFixedWidth(25)
        value_label.setAlignment(Qt.AlignRight)
        
        slider.valueChanged.connect(lambda value, lbl=value_label: lbl.setText(str(value)))
        slider.valueChanged.connect(self.update_settings)
        
        h_layout.addWidget(label)
        h_layout.addStretch()
        h_layout.addWidget(value_label)
        
        v_layout.addLayout(h_layout)
        v_layout.addWidget(slider)
        return v_layout

    def closeEvent(self, event):
        print("Closing application...")
        if self.mouse_controller:
            self.mouse_controller.close()
            
        Config.save(self.app_state.get_full_config())
        self.app_state.running = False
        self.crosshair.close()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        try:
            winsound.PlaySound('SystemStart', winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass
        
        screen_geometry = QApplication.desktop().screenGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)
        
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 12, 12)
        painter.fillPath(path, STYLES["window_background"])

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def update(self):
        super().update()
        self.update_close_button_icon()
            
    def update_settings(self):
        settings = {key: cb.isChecked() for key, cb in self.checkboxes.items()}
        settings.update({key: slider.value() for key, slider in self.sliders.items()})
        settings.update({key: slider.value() for key, slider in self.crosshair_sliders.items()})
        settings['crosshair_color'] = self.config['crosshair_color']
        
        self.app_state.update(settings)
        self.crosshair.update_crosshair(settings)

    def on_makcu_toggled(self, state):
        self.update_settings()
        if state == Qt.Checked and self.mouse_controller:
            threading.Thread(target=self._connect_makcu_worker, daemon=True).start()
        elif self.mouse_controller:
            self.mouse_controller.close()
            self.makcu_status_updated.emit("MAKCU: Disabled", "makcu_status_err")

    def _connect_makcu_worker(self):
        self.makcu_status_updated.emit("MAKCU: Searching...", "makcu_status_info")
        if self.mouse_controller.connect():
            self.makcu_status_updated.emit(f"MAKCU: Connected on {self.mouse_controller.port_name}", "makcu_status_ok")
        else:
            self.makcu_status_updated.emit("MAKCU: Not Found", "makcu_status_err")
            self.checkboxes['use_makcu'].setChecked(False)

    def on_makcu_activity(self):
        self.activity_indicator.setStyleSheet(STYLES["activity_on"])
        self.activity_timer.start(100)

    def on_activity_timeout(self):
        self.activity_indicator.setStyleSheet(STYLES["activity_off"])

    def update_fps_label(self):
        self.fps_updated.emit(self.app_state.fps)
        self.app_state.fps = 0

    def update_makcu_status_label(self, text: str, style_key: str):
        self.makcu_status_label.setText(text)
        self.makcu_status_label.setStyleSheet(STYLES[style_key])

    def update_close_button_icon(self):
        pixmap = AsyncImageLoader.instance().get(IMGUR_CLOSE_URL, self.close_btn)
        if pixmap and not pixmap.isNull():
            self.close_btn.setIcon(QIcon(pixmap))
            self.close_btn.setIconSize(pixmap.size())

    def pick_color(self):
        initial_color = QColor(self.config['crosshair_color'])
        new_color = QColorDialog.getColor(initial_color, self, "Choose Crosshair Color")
        if new_color.isValid():
            self.config['crosshair_color'] = new_color.name()
            self._update_color_button(new_color.name())
            self.update_settings()

    def _update_color_button(self, color_hex: str):
        self.color_button.setStyleSheet(f"background-color: {color_hex}; border-radius: 4px;")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setFont(QFont('Segoe UI', 9))

    AsyncImageLoader.instance()
    
    window = CloudRecoil()
    window.show()

    sys.exit(app.exec_())