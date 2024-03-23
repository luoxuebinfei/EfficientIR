from PyQt5.QtWidgets import QLineEdit,QApplication
from PyQt5.QtCore import Qt,QEvent
from PyQt5.QtGui import QKeySequence,QClipboard


class ImageLineEdit(QLineEdit):
    """自定义QLineEdit,使其支持拖拽粘贴图片"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        """拖拽进入时的动作"""
        if e.mimeData().text():
            e.accept()
        else:
            e.ignore()

    def dropEvent(self, event): 
        """放下文件后的动作"""
        path = event.mimeData().text().replace('file:///', '') # 删除多余开头
        self.setText(path)
        self.setToolTip(f'<img width=300 src="{path}">')


    def keyPressEvent(self, key_event):
        """重写键盘事件"""
        if key_event.matches(QKeySequence.Paste):
            self.setText('')
            clipboard = QApplication.clipboard()
            mime_data = clipboard.mimeData()
            if mime_data.hasUrls():
                url = mime_data.urls()[0]
                file_path = url.toLocalFile()
                if file_path.startswith("file:///"):
                    file_path = file_path[8:]  # 去除开头的file:///
                self.setText(file_path)
                self.setToolTip(f'<img width=300 src="{file_path}">')
        else:
            super().keyPressEvent(key_event)
