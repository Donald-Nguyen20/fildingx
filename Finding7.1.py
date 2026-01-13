import os
import json
import hashlib
import webbrowser
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QLabel, 
                               QLineEdit, QPushButton, QFileDialog, QTreeWidget, QTreeWidgetItem, QListWidget, 
                               QMessageBox, QTextEdit, QFrame, QDialog, QMenu)
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtGui import QPalette, QColor
import sys
import win32com.client as win32
import shutil
import base64
from PySide6.QtGui import QImage, QTextCursor
from PySide6.QtWidgets import QLCDNumber
from PySide6.QtCore import QMimeData, QBuffer, QByteArray
from PySide6.QtWidgets import QTextEdit  # Correct import for QTextEdit
from PySide6.QtWidgets import QComboBox
import re
from PySide6.QtGui import QIcon, QPixmap
from functools import partial
import sqlite3
from rapidfuzz import fuzz
from ai_chat_popup import AIChatPopup
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QProgressBar
from Funtion.percent_exclude_search import parse_percent_query, match_A_percent_B
from hud_widgets import qss_hud_metal_header_feel, qss_white_results
from hud_widgets import qss_hud_metal_header_feel, qss_white_results

import os, sys

def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)   # thư mục chứa .exe
    return os.path.dirname(os.path.abspath(__file__))  # thư mục chứa Finding7.1.py
from Funtion.learning_vector_store import VectorStoreDialog

# pyinstaller --noconfirm --clean --onefile --windowed "Finding7.1.py" --icon "icon.ico"

# Define these at the top of your script
DATA_FILE = "containers_data.json"  # Path where your data file will be stored
IMAGE_DIR = "images"  # Directory to store images

# Ensure the IMAGE_DIR exists; if not, create it
os.makedirs(IMAGE_DIR, exist_ok=True)

EXE_ADDON_FILE = "exe_addons.json"  # JSON file to store EXE add-ons
DATA_FILE = "containers_data.json"  # Path where your data file will be stored
IMAGE_DIR = "images"  # Directory to store images

# Ensure the IMAGE_DIR exists; if not, create it
os.makedirs(IMAGE_DIR, exist_ok=True)


class RichTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)

    def insertFromMimeData(self, source: QMimeData):
        # Handle image data being pasted
        if source.hasImage():
            image = source.imageData()
            buffer = QBuffer()
            buffer.open(QBuffer.ReadWrite)
            image.save(buffer, 'PNG')  # Save image data to the buffer in PNG format
            
            # Convert buffer content to base64
            base64_data = base64.b64encode(buffer.data()).decode()
            html_image = f'<img src="data:image/png;base64,{base64_data}">'
            
            # Insert the image as HTML into the text
            cursor = self.textCursor()
            cursor.insertHtml(html_image)
        else:
            # For other types of data, use the default behavior
            super().insertFromMimeData(source)

class NotesWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Notes")
        self.setGeometry(1300, 100, 800, 600)

        # ✅ Tạo layout chính (đổi tên để không đụng layout())
        self.main_layout = QVBoxLayout(self)

        self.file_name_label = QLabel("Selected File: None")
        self.main_layout.addWidget(self.file_name_label)

        self.note_text = RichTextEdit()
        self.note_text.setAcceptRichText(True)

        self.insert_image_button = QPushButton("Insert Image")
        self.insert_image_button.clicked.connect(self.insert_image)

        self.save_note_button = QPushButton("Save Note")
        self.save_note_button.clicked.connect(self.save_note)

        self.font_size_combo = QComboBox()
        self.font_size_combo.addItems([str(size) for size in range(8, 31, 2)])
        self.font_size_combo.setCurrentText("12")
        self.font_size_combo.currentTextChanged.connect(self.change_font_size)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.insert_image_button)
        button_layout.addWidget(self.save_note_button)
        button_layout.addWidget(QLabel("Font Size:"))
        button_layout.addWidget(self.font_size_combo)

        self.main_layout.addWidget(self.note_text)
        self.main_layout.addLayout(button_layout)


    def change_font_size(self, size):
        """Thay đổi kích thước chữ cho văn bản đã chọn."""
        font = self.note_text.currentFont()
        font.setPointSize(int(size))
        self.note_text.setCurrentFont(font)


    def display_note_for_file(self, container_name, file_path):
        """Display the note for the selected file within the container."""
        self.selected_container = container_name
        self.selected_file = file_path
        self.file_name_label.setText(f"{os.path.basename(file_path)}")


        # Find and display the note for the selected file
        for file, note in self.main_app.containers[container_name]:
            if file == file_path:
                # Handle case where note might be plain text instead of a dictionary
                if isinstance(note, str):
                # Convert old string format to new dictionary format
                    note = {"text": note}
            
            # Set the note content, assuming it's now a dictionary
                self.note_text.setHtml(note.get("text", ""))
                break

        self.show()



    def insert_image(self):
        """Insert an image into the notes."""
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("Images (*.png *.xpm *.jpg *.jpeg *.bmp)")
        file_path, _ = file_dialog.getOpenFileName()

        if file_path:
            # Insert image at the current cursor position in QTextEdit
            cursor = self.note_text.textCursor()
            cursor.insertImage(file_path)

    def save_note(self):
        """Save the note for the selected file within the container."""
        if self.selected_container and self.selected_file:
            # Save the content of QTextEdit as HTML to preserve text and images
            note_content = {
                "text": self.note_text.toHtml()  # Save as HTML to include images
            }
            # Find the correct file entry and update its note
            for i, (file_path, _) in enumerate(self.main_app.containers[self.selected_container]):
                if file_path == self.selected_file:
                    self.main_app.containers[self.selected_container][i] = (file_path, note_content)
                    break
            # Save the updated data back to the JSON file
            self.main_app.save_data_to_file()
            QMessageBox.information(self, "Success", "Note saved successfully!")



class FileSearchApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Search and Management")
        self.setGeometry(100, 100, 1200, 800)

        # Main layout
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_widget.setStyleSheet(qss_hud_metal_header_feel() + qss_white_results())

        # Wrapper layout (vertical)
        self.root_layout = QVBoxLayout(self.main_widget)
        self.root_layout.setContentsMargins(8, 8, 8, 8)
        self.root_layout.setSpacing(10)

        # Main content layout (giữ nguyên bố cục cũ)
        self.main_layout = QHBoxLayout()
        self.root_layout.addLayout(self.main_layout)

        from hud_widgets import HudPanel

        # ===== HUD HEADER =====
        self.hud_header = HudPanel(notch=True)
        self.hud_header.setFixedHeight(70)

        header_layout = QHBoxLayout(self.hud_header)
        header_layout.setContentsMargins(24, 0, 24, 12)

        header_layout.setSpacing(16)
        # Nút mở AI Popup (🤖) đặt trên HUD header
        self.btn_ai = QPushButton("🤖")
        self.btn_ai.setToolTip("Open AI Chat")
        self.btn_ai.setFixedSize(72, 60)
        self.btn_ai.setStyleSheet("""
        QPushButton {
            background: rgba(0, 220, 255, 18);
            border: 1px solid rgba(0, 220, 255, 150);
            border-radius: 18px;
            color: #e6ffff;
            font-weight: 900;
            font-size: 45px;
            padding-top: -2px;   /* kéo icon lên */
        }
        QPushButton:hover { background: rgba(0, 220, 255, 30); }
        QPushButton:pressed { background: rgba(0, 220, 255, 42); }
        """)
        

        self.btn_ai.clicked.connect(self.toggle_ai_popup)

        # Canh giữa trên header (giống “bộ não”)
        header_layout.addStretch(1)
        header_layout.addWidget(self.btn_ai, alignment=Qt.AlignHCenter | Qt.AlignTop)
        header_layout.addStretch(1)

        
        header_layout.addStretch()

        # Gắn header lên trên cùng
        self.root_layout.insertWidget(0, self.hud_header)

        # LEFT (bình thường)
        self.left_frame = QFrame()
        self.left_frame.setObjectName("leftFrame")
        self.left_layout = QVBoxLayout(self.left_frame)
        self.left_layout.setContentsMargins(12, 12, 12, 12)
        self.left_layout.setSpacing(10)


        # Folder selection, file search, and filename keyword section (All in one row)
        folder_layout = QHBoxLayout()
        self.folder_label = QLabel("Folder:")
        self.folder_entry = QLineEdit()
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_folder)

        # Filename keyword and search button in the same layout
        self.filename_label = QLabel("Filename Keyword:")
        self.filename_entry = QLineEdit()
        self.search_name_button = QPushButton("Search by Name")
        self.search_name_button.clicked.connect(self.search_files)

        # Add all widgets to the same row (folder_layout)
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(self.folder_entry)
        folder_layout.addWidget(self.browse_button)
        folder_layout.addWidget(self.filename_label)
        folder_layout.addWidget(self.filename_entry)
        folder_layout.addWidget(self.search_name_button)

        # TreeWidget for displaying search results
        self.tree_widget = QTreeWidget()
        self.tree_widget.setColumnCount(2)
        self.tree_widget.setHeaderLabels(["FILE NAME", "PATH"])
        self.tree_widget.setColumnWidth(0, 600)
        self.tree_widget.setColumnWidth(1, 300)
        self.tree_widget.itemDoubleClicked.connect(self.open_file)
        self.tree_widget.setSelectionMode(QTreeWidget.MultiSelection)
        # Thiết lập chế độ menu chuột phải
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_treeview_context_menu)

        # Search duplicates button
        self.search_duplicates_button = QPushButton("Search Duplicates")
        self.search_duplicates_button.clicked.connect(self.search_duplicates)

        # Adding widgets to the left layout
        self.left_layout.addLayout(folder_layout)
        self.left_layout.addWidget(self.tree_widget)

        # Right side layout (Container Management)
        self.right_frame = QFrame()
        self.right_frame.setObjectName("rightFrame")
        self.right_layout = QVBoxLayout(self.right_frame)
        self.right_layout.setContentsMargins(12, 12, 12, 12)
        self.right_layout.setSpacing(10)


        # Containers section (Put Delete button, entry, and Create button on the same row)
        container_layout = QHBoxLayout()
        self.delete_container_button = QPushButton("Delete")
        self.delete_container_button.clicked.connect(self.delete_container)

        self.container_entry = QLineEdit()
        self.create_container_button = QPushButton("Create Container")
        self.create_container_button.clicked.connect(self.create_container)

        # Add delete button, entry, and create button to the same row (container_layout)
        container_layout.addWidget(self.delete_container_button)
        container_layout.addWidget(self.container_entry)
        container_layout.addWidget(self.create_container_button)
        

        self.add_to_container_button = QPushButton("Add File")
        self.add_to_container_button.clicked.connect(self.add_to_container)

        self.containers_list = QListWidget()
        self.containers_list.itemClicked.connect(self.display_container_files)

        self.container_files_list = QListWidget()
        self.container_files_list.itemClicked.connect(self.show_note_frame)
        self.container_files_list.itemDoubleClicked.connect(self.open_file_from_container)

        # Xử lý click chuột phải để mở thư mục chứa file
        self.container_files_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.container_files_list.customContextMenuRequested.connect(self.show_context_menu_for_container)

        # Button to Open Notes.xlsm
        self.open_notes_button = QPushButton("Open Notes")
        self.open_notes_button.clicked.connect(self.open_or_create_notes)

        # Get Hyperlink Button
        self.get_hyperlink_button = QPushButton("Get Hyperlink for notes")
        self.get_hyperlink_button.clicked.connect(self.get_hyperlink_from_tree_view)

        # Adding widgets to the right layout
        self.right_layout.addLayout(container_layout)
        self.right_layout.addWidget(self.containers_list)
        self.right_layout.addWidget(self.container_files_list)

        # Add left and right frame to the main layout
        self.main_layout.addWidget(self.left_frame, 2)
        self.main_layout.addWidget(self.right_frame, 1)


        self.left_frame.setObjectName("leftFrame")
        self.right_frame.setObjectName("rightFrame")

        # Create Hidden Frame: This frame will be shown or hidden when the toggle button is pressed
        self.hidden_frame = QFrame()
        self.hidden_frame_layout = QVBoxLayout(self.hidden_frame)
        self.hidden_frame.setFrameShape(QFrame.StyledPanel)
        self.hidden_frame.setHidden(True)

        self.hidden_frame_2 = QFrame()
        self.hidden_frame_2.setFrameShape(QFrame.StyledPanel)
        self.hidden_frame_2_layout = QVBoxLayout(self.hidden_frame_2)
        self.hidden_frame_2.setHidden(True)


        # Nút cho hidden frame
        self.get_link_button = QPushButton("Get Path")
        self.get_link_button.clicked.connect(self.get_link_from_tree_view)

        self.get_name_button = QPushButton("Get Name")
        self.get_name_button.clicked.connect(self.get_name_from_tree_view)

        self.hidden_frame_layout.addWidget(self.get_link_button)
        self.hidden_frame_layout.addWidget(self.get_name_button)
        self.list_files_button = QPushButton("List Files")  # Nút List Files
        self.list_files_button.clicked.connect(self.list_files_in_folder)
        self.hidden_frame_layout.addWidget(self.list_files_button)  # Thêm nút List Files vào hidden frame


        # Toggle Button to show/hide the hidden frame
        self.toggle_button = QPushButton("🛠️")
        font = self.toggle_button.font()
        font.setPointSize(20)  # Adjust font size to fit the button size
        self.toggle_button.setFont(font)
# Set the size of the button to fit the larger font properly
        self.toggle_button.setFixedSize(50, 50)  # Adjust as needed for balance
        self.toggle_button.setStyleSheet("text-align: center;")  # Ensure centered alignment
        self.toggle_button.clicked.connect(self.toggle_hidden_frame)

        # Second Toggle Button
        self.toggle_button_2 = QPushButton("🧩")
        font = self.toggle_button_2.font()
        font.setPointSize(20)  # Adjust the size as needed
        self.toggle_button_2.setFont(font)
        self.toggle_button_2.setFixedSize(50, 50)
        self.toggle_button_2.clicked.connect(self.toggle_hidden_frame_2)

        # Third Toggle Button: Learning
        self.toggle_button_3 = QPushButton("📚")
        font = self.toggle_button_3.font()
        font.setPointSize(20)
        self.toggle_button_3.setFont(font)
        self.toggle_button_3.setFixedSize(50, 50)
        self.toggle_button_3.setStyleSheet("text-align: center;")
        self.toggle_button_3.setToolTip("Learning")
        self.toggle_button_3.clicked.connect(self.open_learning)


        # Adding Widgets to the Second Hidden Frame
        self.add_exe_button = QPushButton("ADD ON ➕")  # Button to add EXE files
        font = self.add_exe_button.font()
        font.setPointSize(14)  # Điều chỉnh kích thước chữ cho phù hợp
        self.add_exe_button.setFont(font)
        self.add_exe_button.setFixedSize(120, 50)  # Chiều rộng 120px, chiều cao 50px

#tạo ô tìm kiếm container
        # Add a search bar for filtering containers
        self.container_search_bar = QLineEdit()
        self.container_search_bar.setPlaceholderText("Search containers...")
        self.container_search_bar.textChanged.connect(self.filter_containers)

        # Add the search bar to the right layout above the containers_list
        self.right_layout.insertWidget(1, self.container_search_bar) #số 1 là vị trí hiển thị trong layout
       

        # Đặt căn chỉnh text ở giữa nút
        self.add_exe_button.setStyleSheet("""
    QPushButton {
        text-align: center;
        background-color: #4CAF50;  /* Màu nền */
        color: white;  /* Màu chữ */
        border-radius: 8px;  /* Đường viền bo tròn */
        padding: 5px;
    }
    QPushButton:hover {
        background-color: #45a049;  /* Hiệu ứng hover */
    }
""")
        self.add_exe_button.clicked.connect(self.add_exe_to_frame_2)
        # Layout to display linked EXE files inside hidden_frame_2
        self.exe_list_layout = QVBoxLayout()
        self.hidden_frame_2_layout.addWidget(self.add_exe_button)
        self.hidden_frame_2_layout.addLayout(self.exe_list_layout)
        self.hidden_frame_2_layout.addStretch()
      

        # Vertical layout to align both toggle buttons on the right edge
        self.toggle_buttons_layout = QVBoxLayout()
        self.toggle_buttons_layout.setContentsMargins(0, 50, 0, 0)
        self.toggle_buttons_layout.addWidget(self.toggle_button)
        self.toggle_buttons_layout.addWidget(self.toggle_button_2)
        self.toggle_buttons_layout.addWidget(self.toggle_button_3)
        self.toggle_buttons_layout.addStretch()  # Push the buttons to the top

        # Add the toggle buttons layout to the main layout (on the right side)
        self.main_layout.addLayout(self.toggle_buttons_layout)
        self.main_layout.addWidget(self.hidden_frame)
        self.main_layout.addWidget(self.hidden_frame_2)


         # Initialize containers and EXE add-ons
        self.containers = {}
        self.exe_addons = []  # Store EXE file paths

        # Load data from files
        self.load_data_from_file()
        self.load_exe_addons()

        # Load containers from file
        self.containers = {}
        self.load_data_from_file()

        # Create Notes Window (separate)
        self.notes_window = NotesWindow(parent=self)

        # Adjust spacing and margins
        self.hidden_frame_layout.setSpacing(2)
        self.hidden_frame_layout.setContentsMargins(0, 0, 0, 0)
        self.hidden_frame_layout.setAlignment(Qt.AlignTop)


        # Move buttons into hidden frame
        self.hidden_frame_layout.addWidget(self.search_duplicates_button)
        self.hidden_frame_layout.addWidget(self.open_notes_button)
        self.hidden_frame_layout.addWidget(self.get_hyperlink_button)
        self.hidden_frame_layout.addWidget(self.get_link_button)
        self.hidden_frame_layout.addWidget(self.get_name_button)


        # Tạo QHBoxLayout cho các nút "Add Selected File to Container" và "Delete File"
        file_buttons_layout = QHBoxLayout()

# Nút thêm file vào container
        self.add_to_container_button = QPushButton("Add File")
        self.add_to_container_button.clicked.connect(self.add_to_container)
        file_buttons_layout.addWidget(self.add_to_container_button)

# Nút xóa file khỏi container
        self.delete_file_button = QPushButton("Delete File")
        self.delete_file_button.clicked.connect(self.delete_file_from_container)
        file_buttons_layout.addWidget(self.delete_file_button)

# Thêm file_buttons_layout vào right_layout
        self.right_layout.addLayout(file_buttons_layout)

                # Create an LCDNumber widget
        self.lcd_number = QLCDNumber()
        self.lcd_number.setDigitCount(6)  # Set the number of digits displayed on the LCD
        self.lcd_number.display(0)  # Initialize with 0

                # Set the palette for QLCDNumber to ensure the digits are black
        palette = self.lcd_number.palette()
        palette.setColor(QPalette.WindowText, QColor("black"))  # Set the number color to black
        palette.setColor(QPalette.Light, QColor("#4a5d23"))  # Set light parts of the LCD display to white
        palette.setColor(QPalette.Dark, QColor("black"))  # Set the background to black
        self.lcd_number.setPalette(palette)

        # Add the LCD Number widget next to the search button
        folder_layout.addWidget(self.lcd_number)  # Add the LCDNumber to the folder layout

        self.lcd_number.setStyleSheet("""
       
        """)

        # Nút mở giao diện chỉ mục SQLite ngày 2512225
        self.open_index_interface_button = QPushButton("🔍 Contents")
        self.open_index_interface_button.setFont(font)
        self.open_index_interface_button.setFixedSize(150, 40)
        self.open_index_interface_button.clicked.connect(self.open_index_interface)

        # Thêm nút vào hidden_frame ngày 25122024
        self.hidden_frame_layout.addWidget(self.open_index_interface_button)


    def toggle_hidden_frame(self):
        """Show hidden_frame and hide hidden_frame_2."""
        if self.hidden_frame.isHidden():
            self.hidden_frame.setHidden(False)
            self.hidden_frame_2.setHidden(True)  # Hide the second frame
            self.toggle_button.setText("🛠️")
            self.toggle_button_2.setText("🧩")  # Reset the second toggle button
        else:
            self.hidden_frame.setHidden(True)
            self.toggle_button.setText("🛠️")

    def toggle_hidden_frame_2(self):
        """Show hidden_frame_2 and hide hidden_frame."""
        if self.hidden_frame_2.isHidden():
            self.hidden_frame_2.setHidden(False)
            self.hidden_frame.setHidden(True)  # Hide the first frame
            self.toggle_button_2.setText("🧩")
            self.toggle_button.setText("🛠️")  # Reset the first toggle button
        else:
            self.hidden_frame_2.setHidden(True)
            self.toggle_button_2.setText("🧩")
    def open_learning(self):
        dlg = VectorStoreDialog(self)
        dlg.exec()





# Function to add EXE files dynamically to hidden_frame_2
    def add_exe_to_frame_2(self):
        """Add and link .exe files to hidden_frame_2."""
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("Executable Files (*.exe)")
        files, _ = file_dialog.getOpenFileNames()

        if files:
            for file in files:
                # Immediately create a button for the new EXE file
                self.create_exe_button(file)

                # Avoid duplicate entries in the JSON data
                if file not in self.exe_addons:
                    self.exe_addons.append(file)
                    self.save_exe_addons()

    def create_exe_button(self, exe_path):
        """Create an EXE button with right-click release functionality."""
        exe_name = os.path.basename(exe_path)
        exe_button = QPushButton(f"Open {exe_name}")
        exe_button.setContextMenuPolicy(Qt.CustomContextMenu)

        # Use `partial` to correctly bind the button and path to the signals
        exe_button.customContextMenuRequested.connect(
            partial(self.show_exe_context_menu, exe_button, exe_path)
        )
        exe_button.clicked.connect(partial(self.open_exe_file, exe_path))

        # Add the button to the layout
        self.exe_list_layout.addWidget(exe_button)

    def show_exe_context_menu(self, button, exe_path, pos):
        """Show the right-click context menu for an EXE button."""
        menu = QMenu(self)
        release_action = menu.addAction("Release")

        # Use `partial` to bind the button and path correctly to the release function
        release_action.triggered.connect(partial(self.release_exe, button, exe_path))

        # Display the menu at the cursor's position
        menu.exec(QCursor.pos())

    def release_exe(self, button, exe_path):
        """Remove the EXE button and update the JSON file."""
        # Remove the button from the layout and delete it
        button.setParent(None)
        button.deleteLater()

        # Remove the EXE path from the saved add-ons
        if exe_path in self.exe_addons:
            self.exe_addons.remove(exe_path)
            self.save_exe_addons()

    def save_exe_addons(self):
        """Save the current EXE add-ons to the JSON file."""
        with open(EXE_ADDON_FILE, 'w') as file:
            json.dump(self.exe_addons, file)

    def load_exe_addons(self):
        """Load EXE add-ons from the JSON file."""
        if os.path.exists(EXE_ADDON_FILE):
            with open(EXE_ADDON_FILE, 'r') as file:
                self.exe_addons = json.load(file)

            # Display the loaded EXE files
            for exe_path in self.exe_addons:
                self.create_exe_button(exe_path)

    def open_exe_file(self, path):
        """Open the selected .exe file."""
        if os.path.exists(path):
            try:
                os.startfile(path)  # Open the EXE file
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open {path}: {str(e)}")
        else:
            QMessageBox.warning(self, "File Not Found", f"{path} does not exist.")


    def open_folder(self, item):
        """Mở thư mục chứa file."""
        file_path = item.text(1)
        folder = os.path.dirname(file_path)
        if os.path.exists(folder):
            webbrowser.open(f'file:///{folder}')

    def get_name_from_tree_view(self):
        """Lấy tên của các file đã chọn từ TreeView."""
        selected_items = self.tree_widget.selectedItems()
        if selected_items:
            names = [item.text(0) for item in selected_items]
            clipboard_content = "\n".join(names)
            QApplication.clipboard().setText(clipboard_content)
            QMessageBox.information(self, "Names Copied", "File names copied to clipboard.")
        else:
            QMessageBox.warning(self, "No Selection", "Please select at least one file.")

    def get_link_from_tree_view(self):
        """Lấy đường dẫn file từ TreeView và sao chép vào clipboard."""
        selected_items = self.tree_widget.selectedItems()
        if selected_items:
            links = [item.text(1) for item in selected_items]
            clipboard_content = "\n".join(links)
            QApplication.clipboard().setText(clipboard_content)
            QMessageBox.information(self, "Links Copied", "File paths copied to clipboard.")
        else:
            QMessageBox.warning(self, "No Selection", "Please select at least one file.")

    def show_note_frame(self, item):
        """Display the note window when a file is selected within a container."""
        selected_file = item.text()
        selected_container = self.containers_list.currentItem().text()
        # Get the full path of the selected file from the container
        for file_path, _ in self.containers[selected_container]:
            if os.path.basename(file_path) == selected_file:
                self.notes_window.display_note_for_file(selected_container, file_path)
                break


    def delete_container(self):
        selected_item = self.containers_list.currentItem()
        if selected_item:
            container_name = selected_item.text()
            del self.containers[container_name]
            self.containers_list.takeItem(self.containers_list.row(selected_item))
            self.container_files_list.clear()
            self.save_data_to_file()

    def create_container(self):
        container_name = self.container_entry.text()
        if container_name:
            self.containers_list.addItem(container_name)
            self.containers[container_name] = []
            self.save_data_to_file()

    def open_or_create_notes(self):
        file_path = os.path.join(os.getcwd(), "Notes.xlsm")
        excel_app = win32.Dispatch("Excel.Application")
        excel_app.Visible = True

        if not os.path.exists(file_path):
            wb = excel_app.Workbooks.Add()
            ws = wb.Worksheets(1)
            ws.Cells(1, 1).Value = "No"
            ws.Cells(1, 2).Value = "CONTENT"
            ws.Cells(1, 3).Value = "LINK"
            ws.Cells(1, 4).Value = "NOTES"
            wb.SaveAs(file_path, FileFormat=52)
        else:
            wb = excel_app.Workbooks.Open(file_path)

    def get_hyperlink_from_tree_view(self):
        """Lấy các file đã chọn từ TreeView và chèn hyperlink vào Excel."""
        file_paths = []

        selected_items = self.tree_widget.selectedItems()
        if selected_items:
            for item in selected_items:
                file_path = item.text(1)
                file_paths.append(file_path)

        if not file_paths:
            QMessageBox.warning(self, "No Selection", "Please select at least one file.")
            return

        file_path = os.path.join(os.getcwd(), "Notes.xlsm")
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "File Not Found", "Notes.xlsm file does not exist. Please create it first.")
            return

        try:
            excel_app = win32.Dispatch("Excel.Application")
            excel_app.Visible = True
            wb = excel_app.Workbooks.Open(file_path)
            ws = wb.Sheets(1)

            address = self.get_cell_address_from_user()
            if address:
                cell = ws.Range(address)
                for i, path in enumerate(file_paths):
                    target_cell = ws.Cells(cell.Row + i, cell.Column)
                    target_cell.Formula = f'=HYPERLINK("{path}", "Open File")'
                wb.Save()
                QMessageBox.information(self, "Success", "Hyperlink added to Notes sheet.")
            else:
                QMessageBox.warning(self, "No Address", "Please enter a valid cell address.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add hyperlink: {e}")

    def get_cell_address_from_user(self):
        """Lấy địa chỉ ô từ người dùng thông qua một hộp thoại."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Enter Cell Address")
        dialog.setGeometry(300, 300, 200, 100)
        layout = QVBoxLayout(dialog)

        label = QLabel("Enter the Excel cell address (e.g., A1):")
        layout.addWidget(label)

        cell_address_input = QLineEdit()
        layout.addWidget(cell_address_input)

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(dialog.accept)
        layout.addWidget(ok_button)

        if dialog.exec():
            return cell_address_input.text()
        return None

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.folder_entry.setText(folder)

    def search_files(self):
        folder_path = self.folder_entry.text()
        từ_khóa = self.filename_entry.text().strip()

        if not folder_path or not từ_khóa:
            QMessageBox.warning(self, "Input Error", "Please provide the folder path and keyword.")
            return

    # Kiểm tra cú pháp $synonym
        if từ_khóa == "$synonym":
            self.edit_synonyms()  # Mở hộp thoại chỉnh sửa từ đồng nghĩa
            return

    # Thực hiện tìm kiếm
        if từ_khóa.startswith("@"):
            từ_khóa = từ_khóa[1:]
            kết_quả = self.tìm_kiếm_tổng_hợp(folder_path, từ_khóa)  # Tìm kiếm nâng cao
        else:
            kết_quả = self.search_files_by_name(folder_path, từ_khóa)

        self.display_results(kết_quả)


#tạo từ đồng nghĩa
    def edit_synonyms(self): 
        """Open a dialog to edit synonyms."""
        synonyms = self.load_synonyms()

    # Chuyển đổi JSON thành chuỗi theo định dạng <key> == <value1>, <value2>, ...
        formatted_text = "\n".join(
            f"{key} == {', '.join(values)}" for key, values in synonyms.items()
        )

    # Tạo hộp thoại
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Synonyms")
        dialog.setGeometry(500, 300, 600, 400)
        layout = QVBoxLayout(dialog)

    # Tạo QTextEdit để hiển thị danh sách từ đồng nghĩa
        text_edit = QTextEdit()
        text_edit.setPlainText(formatted_text)  # Hiển thị theo định dạng mới
        layout.addWidget(text_edit)

    # Tạo nút Lưu
        save_button = QPushButton("Save")
        save_button.clicked.connect(lambda: self.save_synonyms_from_dialog(dialog, text_edit))
        layout.addWidget(save_button)

        dialog.exec()


    def save_synonyms_from_dialog(self, dialog, text_edit):
        """Save updated synonyms from the dialog."""
        try:
            # Đọc nội dung từ QTextEdit
            raw_text = text_edit.toPlainText().strip()
            synonyms = {}

            # Duyệt qua từng dòng để phân tích cú pháp
            for line in raw_text.splitlines():
                if "==" in line:  # Chỉ xử lý các dòng chứa '=='
                    key, values = map(str.strip, line.split("==", 1))
                    synonyms[key] = [value.strip() for value in values.split(",")]

        # Lưu dữ liệu vào file JSON
            self.save_synonyms(synonyms)
            QMessageBox.information(self, "Success", "Synonyms updated successfully!")
            dialog.accept()  # Đóng hộp thoại
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save synonyms: {e}")

#tạo từ đồng nghĩa

    def display_results(self, kết_quả):
        """Hiển thị kết quả tìm kiếm trong QTreeWidget và cập nhật QLCDNumber."""
        self.tree_widget.clear()  # Xóa kết quả cũ

        if kết_quả:
            for file_name, file_path in kết_quả:
                item = QTreeWidgetItem([file_name, file_path])
                self.tree_widget.addTopLevelItem(item)

        # Cập nhật LCDNumber và thông báo số lượng
            self.lcd_number.display(len(kết_quả))
            QMessageBox.information(self, "Kết quả", f"Tìm thấy {len(kết_quả)} tệp.")
        else:
        # Không có kết quả
            item = QTreeWidgetItem(["No matches found", ""])
            self.tree_widget.addTopLevelItem(item)
            self.lcd_number.display(0)
            QMessageBox.warning(self, "Không tìm thấy", "Không tìm thấy tệp nào phù hợp.")




    def search_files_by_name(self, folder_path, filename_keyword):
        matches = []
        # Xử lý cú pháp A%B: phải có A nhưng loại bỏ file có B
        q = parse_percent_query(filename_keyword)
        if q is not None:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    if match_A_percent_B(file, q):
                        full_path = os.path.join(root, file)
                        matches.append((file, full_path))
            return matches

    # Xử lý cụm từ tìm kiếm có dấu '*'
        if '*' in filename_keyword:
            keywords = filename_keyword.split('*')
            keywords = [kw.strip() for kw in keywords if kw.strip()]

            if len(keywords) == 2:
                pattern1 = re.escape(keywords[0]) + '.*' + re.escape(keywords[1])
                pattern2 = re.escape(keywords[1]) + '.*' + re.escape(keywords[0])
                regex_pattern = re.compile(f"({pattern1}|{pattern2})", re.IGNORECASE)
            else:
                regex_pattern = re.compile(re.escape(filename_keyword).replace(r'\*', '.*'), re.IGNORECASE)
        else:
            regex_pattern = re.compile(re.escape(filename_keyword), re.IGNORECASE)

        for root, _, files in os.walk(folder_path):
            for file in files:
                if regex_pattern.search(file):
                    full_path = os.path.join(root, file)  # Lấy đường dẫn đầy đủ của tệp
                    matches.append((file, full_path))  # Lưu tên file và đường dẫn đầy đủ

        return matches

    
    def show_treeview_context_menu(self, position):
        """Hiển thị menu chuột phải cho TreeView."""
    # Lấy item được click chuột phải
        selected_item = self.tree_widget.itemAt(position)
        if selected_item:
        # Tạo menu chuột phải
            menu = QMenu(self)
            open_folder_action = menu.addAction("Open Folder")

        # Xử lý sự kiện khi chọn Open Folder
            open_folder_action.triggered.connect(lambda: self.open_folder_from_treeview(selected_item))
        
        # Hiển thị menu tại vị trí chuột
            menu.exec(QCursor.pos())

    def open_folder_from_treeview(self, item):
        """Mở thư mục chứa file từ TreeView."""
    # Lấy đường dẫn từ cột Path
        file_path = item.text(1)
        folder = os.path.dirname(file_path)
        if os.path.exists(folder):
            # Mở thư mục chứa file
            webbrowser.open(f'file:///{folder}')
        else:
            QMessageBox.warning(self, "Error", "Folder not found.")


    def search_duplicates(self):
        folder_path = self.folder_entry.text()
        if not folder_path:
            QMessageBox.warning(self, "Input Error", "Please provide the folder path.")
            return

        results = self.find_duplicate_files(folder_path)
        self.tree_widget.clear()
        if results:
            for result in results:
                item = QTreeWidgetItem(result)
                self.tree_widget.addTopLevelItem(item)
        else:
            item = QTreeWidgetItem(["No duplicates found", ""])
            self.tree_widget.addTopLevelItem(item)

    def find_duplicate_files(self, folder_path):
        files_seen = {}
        duplicates = []
        for root, _, files in os.walk(folder_path):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                file_size = os.path.getsize(file_path)
                file_hash = self.calculate_hash(file_path)
                if file_hash:
                    if file_size in files_seen and file_hash in files_seen[file_size]:
                        duplicates.append((file_name, file_path))
                    else:
                        files_seen.setdefault(file_size, {})[file_hash] = file_path
        return duplicates

    def calculate_hash(self, file_path):
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
        except FileNotFoundError:
            print(f"File not found: {file_path}")
            return None
        return sha256_hash.hexdigest()

    def open_file(self, item):
        """Mở file được double-click trong QTreeWidget."""
        file_path = item.text(1)  # Lấy đường dẫn từ cột Path
        if os.path.exists(file_path):
            webbrowser.open(file_path)  # Mở file bằng trình duyệt mặc định
        else:
            QMessageBox.warning(self, "File Not Found", "The selected file does not exist.")


    def add_to_container(self):
        selected_item = self.tree_widget.currentItem()
        if selected_item:
            file_path = selected_item.text(1)
            selected_container = self.containers_list.currentItem().text()
            if selected_container:
                if file_path not in [f[0] for f in self.containers[selected_container]]:
                    self.containers[selected_container].append((file_path, ""))
                    self.save_data_to_file()
                    self.display_container_files(self.containers_list.currentItem())
                else:
                    QMessageBox.warning(self, "File Exists", "This file already exists in the selected container.")
            else:
                QMessageBox.warning(self, "Select Error", "Please select a container to add the file to.")
        else:
            QMessageBox.warning(self, "Select Error", "Please select a file to add.")

    def delete_file_from_container(self):
        """Xóa tệp đã chọn khỏi container."""
        selected_item = self.container_files_list.currentItem()
        selected_container = self.containers_list.currentItem()

        if not selected_item or not selected_container:
            QMessageBox.warning(self, "Selection Error", "Please select a file and a container.")
            return

        file_name = selected_item.text()
        container_name = selected_container.text()

    # Xác định vị trí tệp trong container và xóa nó
        for i, (file_path, _) in enumerate(self.containers[container_name]):
            if os.path.basename(file_path) == file_name:
                del self.containers[container_name][i]
                self.save_data_to_file()
                self.display_container_files(selected_container)
                QMessageBox.information(self, "Success", f"File '{file_name}' has been deleted from the container.")
                break
        else:
            QMessageBox.warning(self, "File Not Found", "The selected file was not found in the container.")


    def display_container_files(self, item):
        container_name = item.text()
        self.container_files_list.clear()
        if container_name in self.containers:
            for file_path, _ in self.containers[container_name]:
                file_name = os.path.basename(file_path)
                self.container_files_list.addItem(file_name)

    def open_file_from_container(self, item):
        """Mở file được double-click trong danh sách container files."""
        file_name = item.text()
        selected_container = self.containers_list.currentItem().text()
        for file_path, _ in self.containers[selected_container]:
            if os.path.basename(file_path) == file_name:
                if os.path.exists(file_path):
                    webbrowser.open(file_path)
                else:
                    QMessageBox.warning(self, "File Not Found", "The selected file does not exist.")
                break


    def save_data_to_file(self):
        with open(DATA_FILE, 'w') as file:
            json.dump(self.containers, file)

    def load_data_from_file(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as file:
                self.containers = json.load(file)

        # Initially display all containers
        self.filter_containers("")

#load và save từ đồng nghĩa
    def load_synonyms(self):
        """Load synonyms from JSON file."""
        try:
            with open("synonyms.json", "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}  # Trả về danh sách trống nếu tệp không tồn tại

    def save_synonyms(self, synonyms):
        """Save updated synonyms to JSON file."""
        with open("synonyms.json", "w") as file:
            json.dump(synonyms, file, indent=4)

    def show_context_menu_for_container(self, pos):
        item = self.container_files_list.itemAt(self.container_files_list.viewport().mapFromGlobal(QCursor.pos()))
        if item:
            menu = QMenu(self)
            open_folder_action = menu.addAction("Open Folder")
            open_folder_action.triggered.connect(lambda: self.open_folder_for_item(item))
            menu.exec(QCursor.pos())

    def open_folder_for_item(self, item):
        file_name = item.text()
        container_name = self.containers_list.currentItem().text()
        for file_path, _ in self.containers[container_name]:
            if os.path.basename(file_path) == file_name:
                folder = os.path.dirname(file_path)
                if os.path.exists(folder):
                    webbrowser.open(f'file:///{folder}')
                    break

    def filter_containers(self, text):
        """Filter containers based on the search text."""
        self.containers_list.clear()  # Clear current display

    # Filter and display containers that match the search text
        for container_name in self.containers.keys():
            if text.lower() in container_name.lower():  # Case-insensitive search
                self.containers_list.addItem(container_name)


    def list_files_in_folder(self):
        """List files in a selected folder, display them in a new window, and allow deletion of selected files."""
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")

        if not folder_path:
            QMessageBox.warning(self, "Input Error", "Please select a folder.")
            return

        # Create a new dialog window to display the list of files
        list_window = QDialog(self)
        list_window.setWindowTitle("List of Files")
        list_window.setGeometry(700, 100, 1100, 600)
        list_layout = QVBoxLayout(list_window)

    # Create an LCDNumber widget to display the count of files
        lcd_file_count = QLCDNumber()
        lcd_file_count.setDigitCount(6)  # Set the number of digits displayed on the LCD
        lcd_file_count.display(0)  # Initialize with 0

    # Set the palette for QLCDNumber to ensure the digits are black
        palette = lcd_file_count.palette()
        palette.setColor(QPalette.WindowText, QColor("black"))  # Set the number color to black
        palette.setColor(QPalette.Light, QColor("Blue"))  # Set light parts of the LCD display to white
        palette.setColor(QPalette.Dark, QColor("black"))  # Set the background to black
        lcd_file_count.setPalette(palette)

        # ComboBox to filter file formats
        format_combo = QComboBox()
        format_combo.addItem("All")  # Option to show all files

        # Size filter input fields
        min_size_input = QLineEdit()
        min_size_input.setPlaceholderText("Min size (MB)")
        max_size_input = QLineEdit()
        max_size_input.setPlaceholderText("Max size (MB)")
        size_filter_button = QPushButton("Filter by Size")

        # Tree widget to display files with checkboxes
        file_tree = QTreeWidget()
        file_tree.setColumnCount(4)  # Giữ 4 cột, không thêm cột Copy Data
        file_tree.setHeaderLabels(["Select", "Filename", "Path", "Size (MB)"])
        file_tree.setColumnWidth(0, 50)
        file_tree.setColumnWidth(1, 550)
        file_tree.setColumnWidth(2, 400)
        file_tree.setColumnWidth(3, 50)  # Set column width for file size

        # Cho phép chọn nhiều tệp cùng lúc
        file_tree.setSelectionMode(QTreeWidget.MultiSelection)

        # Add this line here to connect the itemDoubleClicked event
        file_tree.itemDoubleClicked.connect(self.open_file_from_list)

        # Store the checkbox states
        checkbox_states = []
        files = []  # Store files to filter later
        extensions_set = set()  # Set to store unique file extensions


            # Nút đổi tên hàng loạt
        batch_rename_button = QPushButton("Batch Rename")
        batch_rename_button.clicked.connect(lambda: self.open_batch_rename_dialog(file_tree))



        # Populate the tree with files from the selected folder
        for root, _, files_in_folder in os.walk(folder_path):
            for file in files_in_folder:
                file_path = os.path.join(root, file)
                extension = os.path.splitext(file)[1].lower()
                try:
                    file_size = os.path.getsize(file_path) / (1024 * 1024)  # File size in MB
                    size_str = f"{file_size:.2f}"  # Format file size to two decimal places
                except Exception as e:
                    # Handle error and continue
                    size_str = "Error"  # Indicate error size
                    print(f"Error getting size for {file_path}: {e}")

                folder_path_only = os.path.dirname(file_path)  # Get the folder path without file name
                extensions_set.add(extension)  # Collect unique extensions
                item = QTreeWidgetItem(["", file, folder_path_only, size_str])  # Hiển thị tên file, path, và size

                # Lưu trữ dữ liệu ẩn (filename và path) bằng Qt.UserRole
                item.setData(1, Qt.UserRole, {"filename": file, "path": file_path})

                item.setCheckState(0, Qt.Unchecked)  # Add a checkbox to the first column
                file_tree.addTopLevelItem(item)
                checkbox_states.append(False)  # Initialize checkbox states
                files.append((file, file_path, file_size))  # Add to the files list with size for filtering

    # Set file count on the LCD
        lcd_file_count.display(len(files))

        # Update ComboBox with file extensions
        format_combo.addItems(sorted(extensions_set))  # Add unique file extensions
        
# Add filter_row_layout and filter_layout to the main layout
        
        list_layout.addWidget(file_tree)

        # Function to filter files based on selected format
        def filter_files():
            selected_extension = format_combo.currentText()
            file_tree.clear()  # Clear existing items
            for file, path, size in files:
                if selected_extension == "All" or path.endswith(selected_extension):
                    size_str = f"{size:.2f}"
                    folder_path_only = os.path.dirname(path)  # Extract only the folder path
                    item = QTreeWidgetItem(["", file, folder_path_only, size_str])
                    item.setData(1, Qt.UserRole, {"filename": file, "path": path})  # Lưu trữ dữ liệu ẩn
                    item.setCheckState(0, Qt.Unchecked)
                    file_tree.addTopLevelItem(item)

        # Connect the filter function to ComboBox selection change
        format_combo.currentTextChanged.connect(filter_files)

        # Function to filter files based on size range
        def filter_by_size():
            try:
                min_size = float(min_size_input.text()) if min_size_input.text() else 0
                max_size = float(max_size_input.text()) if max_size_input.text() else float('inf')
            except ValueError:
                QMessageBox.warning(list_window, "Input Error", "Please enter valid numbers for size range.")
                return

            file_tree.clear()  # Clear existing items
            for file, path, size in files:
                if min_size <= size <= max_size:
                    size_str = f"{size:.2f}"
                    folder_path_only = os.path.dirname(path)  # Extract only the folder path
                    item = QTreeWidgetItem(["", file, folder_path_only, size_str])
                    item.setData(1, Qt.UserRole, {"filename": file, "path": path})  # Lưu trữ dữ liệu ẩn
                    item.setCheckState(0, Qt.Unchecked)
                    file_tree.addTopLevelItem(item)

        # Connect the filter by size button
        size_filter_button.clicked.connect(filter_by_size)

        # Function to toggle checkbox state when clicked
        def toggle_checkbox(item, column):
            if column == 0:  # Only toggle if clicking on the checkbox column
                current_state = item.checkState(0)
                item.setCheckState(0, Qt.Unchecked if current_state == Qt.Checked else Qt.Checked)

        # Connect the toggle function to the tree widget
        file_tree.itemClicked.connect(toggle_checkbox)

        # Button to delete selected files
        delete_button = QPushButton("Delete Selected Files")
        delete_button.clicked.connect(lambda: self.delete_selected_files(file_tree))

        # Button to copy filenames and paths to clipboard
        copy_button = QPushButton("Copy to Clipboard")
        copy_button.clicked.connect(lambda: self.copy_filenames_and_paths(file_tree))

        list_layout.addWidget(file_tree)

        # Create QHBoxLayout for ComboBox, Delete button, Copy button, and Size filter controls
        filter_layout = QHBoxLayout()

        # Add ComboBox, Delete button, Copy button, Min size input, Max size input, and Filter button to filter_layout
        filter_layout.addWidget(lcd_file_count)
        filter_layout.addWidget(format_combo)
        filter_layout.addWidget(delete_button)
        filter_layout.addWidget(copy_button)  # Add copy button next to delete button
        filter_layout.addWidget(min_size_input)
        filter_layout.addWidget(max_size_input)
        filter_layout.addWidget(size_filter_button)
        filter_layout.addWidget(batch_rename_button)

        # Add filter_layout to list_layout
        list_layout.addLayout(filter_layout)
        list_window.exec()




    def open_file_from_list(self, item, column):
        """Mở file được double-click trong cửa sổ List of Files."""
    # Lấy dictionary chứa filename và đường dẫn từ dữ liệu ẩn
        file_data = item.data(1, Qt.UserRole)  # Lấy dictionary từ Qt.UserRole
    
    # Lấy đường dẫn từ dictionary
        file_path = file_data.get("path", "")  # Lấy đường dẫn từ key 'path', mặc định là chuỗi rỗng nếu không có
    
        if file_path and os.path.exists(file_path):
            webbrowser.open(file_path)  # Mở file bằng trình duyệt mặc định
        else:
            QMessageBox.warning(self, "File Not Found", "The selected file does not exist or path is invalid.")



    def delete_selected_files(self, file_tree):
        """Xóa các tệp đã được chọn trong cây thư mục."""
        root = file_tree.invisibleRootItem()  # Lấy item gốc của cây
        files_to_delete = []  # Danh sách chứa các tệp cần xóa

    

    # Duyệt qua các mục trong cây và thêm các tệp đã chọn vào danh sách
        for i in reversed(range(root.childCount())):
            item = root.child(i)
        # Kiểm tra nếu checkbox ở cột đầu tiên được chọn
            if item.checkState(0) == Qt.Checked:
            # Lấy tên tệp và đường dẫn thư mục từ dữ liệu của item
                filename = item.text(1)  # Giả sử tên tệp nằm ở cột thứ hai
                folder = item.text(2)    # Giả sử đường dẫn thư mục nằm ở cột thứ ba
                file_path = os.path.join(folder, filename)  # Kết hợp để tạo đường dẫn đầy đủ của tệp
                files_to_delete.append((file_path, item))  # Thêm tệp và item vào danh sách

    # Nếu có tệp cần xóa, hiển thị hộp thoại xác nhận
        if files_to_delete:
        # Hiển thị hộp thoại xác nhận một lần
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                 f"Are you sure you want to delete the {len(files_to_delete)} selected files?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

        # Nếu người dùng chọn Yes, tiến hành xóa tất cả các tệp trong danh sách
            if reply == QMessageBox.Yes:
                for file_path, item in files_to_delete:
                    try:
                    # Cố gắng xóa tệp
                        os.remove(file_path)
                    # Xóa mục khỏi cây nếu tệp được xóa thành công
                        root.removeChild(item)
                    except Exception as e:
                    # Hiển thị thông báo lỗi nếu việc xóa thất bại
                        QMessageBox.critical(self, "Error", f"Failed to delete {os.path.basename(file_path)}: {str(e)}")

                QMessageBox.information(self, "Success", "Selected files have been deleted.")
        else:
            QMessageBox.information(self, "Notification", "No files selected for deletion.")



    def copy_filenames_and_paths(self, file_tree):
        """Copy filenames and paths from the tree widget to the clipboard."""
        root = file_tree.invisibleRootItem()  # Lấy item gốc của cây
        clipboard_content = []

        # Lặp qua các item và lấy tên file (Filename) từ cột thứ hai và đường dẫn (Path) từ cột thứ ba
        for i in range(root.childCount()):
            item = root.child(i)
            filename = item.text(1)  # Lấy tên file từ cột thứ hai (Filename)
            path = item.text(2)      # Lấy đường dẫn từ cột thứ ba (Path)
            clipboard_content.append(f"{filename}\t{path}")  # Tách file name và path bằng tab

        # Sao chép nội dung vào clipboard
        QApplication.clipboard().setText("\n".join(clipboard_content))
        QMessageBox.information(self, "Copied to Clipboard", "Filenames and paths copied to clipboard.")


    def open_batch_rename_dialog(self, file_tree):
        """Mở hộp thoại đổi tên hàng loạt cho các tệp trong danh sách."""
        selected_items = file_tree.selectedItems()

        if not selected_items:
            QMessageBox.warning(self, "No Files Selected", "Vui lòng chọn ít nhất một tệp để đổi tên.")
            return

        # Tạo hộp thoại đổi tên
        dialog = QDialog(self)
        dialog.setWindowTitle("Batch Rename")
        dialog.setGeometry(500, 300, 400, 300)

        layout = QVBoxLayout(dialog)

        # Ô nhập tiền tố, hậu tố và chuỗi thay thế
        prefix_input = QLineEdit()
        prefix_input.setPlaceholderText("Prefix")
        layout.addWidget(prefix_input)

        suffix_input = QLineEdit()
        suffix_input.setPlaceholderText("Suffix")
        layout.addWidget(suffix_input)

        replace_input = QLineEdit()
        replace_input.setPlaceholderText("Text to Replace")
        layout.addWidget(replace_input)

        # Nút thực hiện đổi tên
        rename_button = QPushButton("Rename")
        rename_button.clicked.connect(lambda: self.batch_rename_files_in_list(
            file_tree, prefix_input.text(), suffix_input.text(), replace_input.text(), dialog
        ))
        layout.addWidget(rename_button)

        dialog.exec()

    def batch_rename_files_in_list(self, file_tree, prefix, suffix, replace, dialog):
        """Thực hiện đổi tên hàng loạt cho các tệp trong danh sách."""
        selected_items = file_tree.selectedItems()

        for item in selected_items:
            old_name = item.text(1)  # Lấy tên tệp từ cột thứ hai (Filename)
            folder = item.text(2)  # Lấy thư mục chứa tệp từ cột thứ ba (Path)
            old_path = os.path.join(folder, old_name)  # Kết hợp để tạo đường dẫn đầy đủ

        # Kiểm tra xem tệp có tồn tại không
            if not os.path.exists(old_path):
                QMessageBox.critical(self, "Error", f"Tệp không tồn tại: {old_path}")
                continue

        # Tạo tên mới với tiền tố, hậu tố và thay thế chuỗi
            new_name = old_name.replace(replace, "") if replace else old_name
            new_name = f"{prefix}{new_name}{suffix}"
            new_path = os.path.join(folder, new_name)

            try:
                os.rename(old_path, new_path)  # Đổi tên tệp
                item.setText(1, new_name)  # Cập nhật tên mới trong giao diện
                item.setData(1, Qt.UserRole, {"filename": new_name, "path": new_path})  # Cập nhật dữ liệu
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Lỗi khi đổi tên tệp: {str(e)}")

        QMessageBox.information(self, "Success", "Batch rename successfully!")
        dialog.accept()



    def add_exe_to_frame_2(self):
        """Add and link .exe files to hidden_frame_2."""
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("Executable Files (*.exe)")
        files, _ = file_dialog.getOpenFileNames()

        if files:
            for file in files:
                exe_name = os.path.basename(file)
                exe_button = QPushButton(f"Open {exe_name}")
                exe_button.clicked.connect(lambda _, path=file: self.open_exe_file(path))
                self.exe_list_layout.addWidget(exe_button)

                # Save the new EXE file path
                self.exe_addons.append(file)
                self.save_exe_addons()

    def open_index_interface(self):
        """Mở giao diện tìm kiếm chỉ mục SQLite."""
        self.index_search_window = IndexSearchWindow(self)
        self.index_search_window.exec()


    def tìm_kiếm_tổng_hợp(self, folder_path, từ_khóa, ngưỡng_tương_đồng=70):
        """Tìm kiếm mờ + Đồng nghĩa + Tất cả từ khóa phải có mặt."""
        synonyms = self.load_synonyms()  # Load từ đồng nghĩa từ JSON
        từ_khóa_mở_rộng = set()
        các_từ_khóa = từ_khóa.split()

    # Mở rộng từ khóa với từ đồng nghĩa
        for kw in các_từ_khóa:
            từ_khóa_mở_rộng.add(kw)  # Thêm từ gốc
            từ_khóa_mở_rộng.update(synonyms.get(kw.lower(), []))  # Thêm từ đồng nghĩa từ JSON

        kết_quả = []
        for root, _, files in os.walk(folder_path):
            for file in files:
                # Chuyển tên file thành lowercase để so sánh không phân biệt hoa thường
                file_lower = file.lower()
                all_keywords_match = True  # Biến để kiểm tra mọi từ khóa đều khớp

            # Kiểm tra tất cả từ khóa trong từ_khóa_mở_rộng phải khớp
                for từ in từ_khóa_mở_rộng:
                    if fuzz.partial_ratio(file_lower, từ.lower()) < ngưỡng_tương_đồng:
                        all_keywords_match = False
                        break  # Nếu một từ không khớp, dừng kiểm tra

                if all_keywords_match:  # Nếu tất cả từ khóa đều khớp, thêm vào kết quả
                    kết_quả.append((file, os.path.join(root, file)))

        return kết_quả


    def toggle_ai_popup(self):
        # tạo popup lần đầu
        if not hasattr(self, "_ai_popup") or self._ai_popup is None:
            from ai_chat_popup import AIChatPopup
            self._ai_popup = AIChatPopup(main_app=self, parent=self)

        # nếu đang hiện -> tắt
        if self._ai_popup.isVisible():
            self._ai_popup.hide()
            return

        # nếu đang tắt -> bật (neo dưới nút AI)
        self._ai_popup.show_below_widget(self.btn_ai, gap=8)

    

class IndexSearchWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        # ✅ HUD theme cho cửa sổ Index Search
        self.setStyleSheet(qss_hud_metal_header_feel() + qss_white_results())

        self.setWindowTitle("Search Indexed Databases")
        self.setGeometry(800, 200, 700, 400)

        self.main_layout = QVBoxLayout(self)
        self.Hlayout = QHBoxLayout()

        self.db_paths = []

        self.import_db_button = QPushButton("Import DB")
        self.database_selector = QComboBox()
        self.database_selector.addItem("All")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter keyword...")

        self.search_button = QPushButton("Search")
        self.copy_name_button = QPushButton("Copy Name")

        # ✅ result table (bắt buộc phải có)
        self.result_table = QTreeWidget()
        self.result_table.setObjectName("resultsTree")
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setUniformRowHeights(True)
        self.result_table.setRootIsDecorated(False)

        self.result_table.setColumnCount(3)
        self.result_table.setHeaderLabels(["File Name", "Path",])
        self.result_table.setColumnWidth(0, 520)  # File Name
        self.result_table.setColumnWidth(1, 260)  # Path
        self.result_table.itemDoubleClicked.connect(self.open_file)

        # ✅ connect đúng tên hàm đang tồn tại
        self.import_db_button.clicked.connect(self.import_database)
        self.search_button.clicked.connect(self.search_database)
        self.search_input.returnPressed.connect(self.search_database)
        self.copy_name_button.clicked.connect(self.copy_selected_name)

        # layout trên
        self.Hlayout.addWidget(self.import_db_button)
        self.Hlayout.addWidget(self.database_selector)
        self.Hlayout.addWidget(self.search_input)
        self.Hlayout.addWidget(self.search_button)
        self.Hlayout.addWidget(self.copy_name_button)

        self.main_layout.addLayout(self.Hlayout)
        self.main_layout.addWidget(self.result_table)



    def import_database(self):
        """Nhập cơ sở dữ liệu SQLite."""
        db_paths, _ = QFileDialog.getOpenFileNames(self, "Select SQLite Databases", "", "SQLite Files (*.db *.sqlite)")
        if db_paths:
            self.db_paths.extend(db_paths)
            self.database_selector.clear()
            self.database_selector.addItem("All")
            self.database_selector.addItems(self.db_paths)
            QMessageBox.information(self, "Databases Imported", f"Successfully imported {len(db_paths)} databases.")

    def search_database(self):
        """Tìm kiếm từ khóa trong cơ sở dữ liệu."""
        if not self.db_paths:
            QMessageBox.warning(self, "No Database", "Please import at least one SQLite database first.")
            return

        keyword = self.search_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "Input Error", "Please enter a keyword to search.")
            return

        selected_db = self.database_selector.currentText()
        results = []

    # Kết nối và tìm kiếm trong các cơ sở dữ liệu
        if selected_db == "All":
            for db_path in self.db_paths:
                db_results = self.search_in_single_database(db_path, keyword)
            # Gắn đường dẫn cơ sở dữ liệu vào kết quả
                for result in db_results:
                    results.append((*result, db_path))  # Thêm db_path vào cuối mỗi hàng kết quả
        else:
            results = [(name, path, content, selected_db) for name, path, content in self.search_in_single_database(selected_db, keyword)]

    # Hiển thị kết quả
        self.result_table.clear()
        self.result_table.setColumnCount(2)
        self.result_table.setHeaderLabels(["File Name", "Path"])

        if results:
            for name, path, content, db_path in results:
                item = QTreeWidgetItem([name, path])

                # ✅ lưu db_path ẩn để open_file dùng (không cần cột Database nữa)
                item.setData(0, Qt.UserRole, db_path)

                self.result_table.addTopLevelItem(item)
        else:
            QMessageBox.information(self, "No Results", "No files found with the given keyword.")


    def search_in_single_database(self, db_path, keyword):
        """Tìm kiếm trong một cơ sở dữ liệu."""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            query = """
                SELECT name, path, content 
                FROM files 
                WHERE name LIKE ? OR content LIKE ?
            """
            cursor.execute(query, (f"%{keyword}%", f"%{keyword}%"))
            results = cursor.fetchall()
            conn.close()
            return results
        except Exception as e:
            QMessageBox.warning(self, "Database Error", f"Failed to search {db_path}: {e}")
            return []

    def copy_selected_name(self):
        """Copy the name of the selected file."""
        selected_item = self.result_table.currentItem()
        if selected_item:
            file_name = selected_item.text(0)  # Lấy tên file từ cột đầu tiên
            QApplication.clipboard().setText(file_name)  # Sao chép tên file vào clipboard
            QMessageBox.information(self, "Copied", f"File name copied: {file_name}")
        else:
            QMessageBox.warning(self, "No Selection", "Please select a file to copy its name.")

    def open_file(self, item, column):
        """Open the file when double-clicked in the result table."""
        try:
            # Get the relative path from the second column of the clicked item
            relative_path = item.text(1)  # Cột thứ hai chứa đường dẫn tương đối

            # Get the database path from the hidden fourth column
            db_path = item.data(0, Qt.UserRole)  # Cột thứ 4 (ẩn) chứa đường dẫn cơ sở dữ liệu

            # Kết nối tới cơ sở dữ liệu để lấy BASE_PATH
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT path FROM files WHERE name = 'BASE_PATH'")
            base_path_row = cursor.fetchone()
            conn.close()

            if base_path_row:
                base_path = base_path_row[0]
                # Kết hợp BASE_PATH với đường dẫn tương đối để tạo đường dẫn tuyệt đối
                absolute_path = os.path.join(base_path, relative_path)

                # Kiểm tra file có tồn tại và mở file
                if os.path.exists(absolute_path):
                    os.startfile(absolute_path)
                else:
                    QMessageBox.warning(self, "File Not Found", f"The file does not exist: {absolute_path}")
            else:
                QMessageBox.warning(self, "Error", "BASE_PATH not found in the database.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file: {e}")

        self.main_widget.setStyleSheet(qss_hud_metal_header_feel() + qss_white_results())

# Tạo ứng dụng PySide6 và hiển thị cửa sổ
if __name__ == "__main__":
    # Tạo ứng dụng PySide6
    app = QApplication(sys.argv)  # Khởi tạo biến app đúng cách
    
    # Thêm stylesheet cho ứng dụng để thay đổi màu sắc
    # Cập nhật stylesheet với tông màu sáng, hiện đại  8470FF
    





    window = FileSearchApp()
    window.show()
    sys.exit(app.exec())

