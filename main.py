import os
import sys
import json
from PyQt5 import QtCore,QtWidgets,uic
from utils import Utils


QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
config_path = 'gui/config.json'
config = json.loads(open(config_path,'rb').read())
utils = Utils(config)
Ui_MainWindow, QtBaseClass = uic.loadUiType(config['ui'])


# 建立索引的后台线程类
class IndexThread(QtCore.QThread):
    update_signal = QtCore.pyqtSignal(str)
    progress_signal = QtCore.pyqtSignal(int)  # 进度信号
    completed_signal = QtCore.pyqtSignal()     # 完成信号

    def __init__(self, utils_instance):
        QtCore.QThread.__init__(self)
        self.utils = utils_instance

    def run(self):
        self.utils.remove_nonexists()
        self.progress_signal.emit(0)
        need_indexs = []
        for image_dir in config['search_dir']:
            need_index = self.utils.index_target_dir(image_dir)
            need_indexs.extend(need_index)
        if len(need_index) == 0:
            self.progress_signal.emit(100)
        for i, (idx, fpath) in enumerate(need_indexs):
            self.utils.update_ir_index(idx, fpath)
            progress = int((i + 1) / len(need_indexs) * 100)
            # 更新进度条信号发射到主线程
            self.progress_signal.emit(progress)
        self.utils.exists_index = self.utils.get_exists_index()
        self.completed_signal.emit()  # 发出完成信号
        self.requestInterruption() # 退出线程，防止内存泄漏
        return


class MainUI(QtWidgets.QMainWindow, Ui_MainWindow):

    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)
        self._bind_ui_()
        self._init_ui_()
        self.index_thread = None  # 保存线程对象的引用
        self.progress_dialog = None  # 进度条对话框的引用


    def _bind_ui_(self):
        self.selectBtn.clicked.connect(self.openfile)
        self.startSearch.clicked.connect(self.start_search)
        self.startSearchDuplicate.clicked.connect(self.start_search_duplicate)
        self.resultTable.doubleClicked.connect(self.double_click_search_table)
        self.resultTableDuplicate.doubleClicked.connect(self.double_click_duplicate_table)
        self.addSearchDir.clicked.connect(self.add_search_dir)
        self.updateIndex.clicked.connect(self.sync_index)
        self.removeInvalidIndex.clicked.connect(self.remove_invalid_index)


    def _init_ui_(self):
        if os.path.exists(utils.exists_index_path):
            self.exists_index = utils.get_exists_index()                                                        # 加载索引
        self.resultTable.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)              # 填充显示表格
        self.resultTable.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)                            # 表格设置只读
        self.resultTableDuplicate.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.resultTableDuplicate.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.resultTableDuplicate.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.resultTableDuplicate.setSortingEnabled(True)
        self.searchDirTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.searchDirTable.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.update_dir_table()
        self.progress_dialog = None  # 添加这一行，确保 self.progress_dialog 被正确初始化为 None


    def openfile(self):
        self.input_path = QtWidgets.QFileDialog.getOpenFileName(self,'选择图片','','Image files(*.*)')
        self.filePath.setText(self.input_path[0])
        self.filePath.setToolTip(f'<img width=300 src="{self.input_path[0]}">')


    def double_click_search_table(self, info):
        file_path = self.resultTable.item(info.row(), 0).text()
        os.startfile(os.path.normpath(file_path))


    def double_click_duplicate_table(self, info):
        col = info.column()
        if col > 1:
            return
        row = info.row()
        os.startfile(self.resultTableDuplicate.item(row, col).text())

    # 搜索图片
    def start_search(self):
        self.resultTable.setRowCount(0)     # 清空表格
        if not hasattr(self, 'input_path'):
            if self.filePath.text() == '':
                self.openfile()
            else:
                self.input_path = [self.filePath.text()]
        self.input_path= [self.filePath.text()]
        if self.input_path[0] == '':
            delattr(self, 'input_path')
            return
        if (config['search_dir'] == []) or (not os.path.exists(utils.exists_index_path)):
            QtWidgets.QMessageBox.information(self, '提示', '索引都没有建搜你🐎 搜')
            return
        nc = self.resultCount.value()
        nc = nc if nc <= len(self.exists_index) else len(self.exists_index)
        results = utils.checkout(self.input_path[0], self.exists_index, nc)
        for i in results:
            row = self.resultTable.rowCount()
            self.resultTable.insertRow(row)
            item_sim = QtWidgets.QTableWidgetItem(f'{i[0]:.2f} %')
            item_sim.setTextAlignment(QtCore.Qt.AlignHCenter|QtCore.Qt.AlignVCenter)
            item_path = QtWidgets.QTableWidgetItem(i[1])
            item_path.setToolTip(f'{i[1]}<br><img width=300 src="{i[1]}">')
            self.resultTable.setItem(row,0,item_path)
            self.resultTable.setItem(row,1,item_sim)

    # 检测图片是否重复
    def start_search_duplicate(self):
        if (config['search_dir'] == []) or (not os.path.exists(utils.exists_index_path)):
            QtWidgets.QMessageBox.information(self, '提示', '索引都没有建查你🐎 查')
            return
        self.resultTableDuplicate.setRowCount(0)                                                        # 清空表格
        threshold = self.similarityThreshold.value()
        same_folder = self.sameFolder.isChecked()
        for i in utils.get_duplicate(self.exists_index, threshold, same_folder):
            row = self.resultTableDuplicate.rowCount()
            self.resultTableDuplicate.insertRow(row)
            item_path_a = QtWidgets.QTableWidgetItem(i[0])
            item_path_a.setToolTip(f'{i[0]}<br><img width=300 src="{i[0]}">')
            item_path_b = QtWidgets.QTableWidgetItem(i[1])
            item_path_b.setToolTip(f'{i[1]}<br><img width=300 src="{i[1]}">')
            item_sim = QtWidgets.QTableWidgetItem(f'{i[2]:.2f} %')
            item_sim.setTextAlignment(QtCore.Qt.AlignHCenter|QtCore.Qt.AlignVCenter)
            self.resultTableDuplicate.setItem(row,0,item_path_a)
            self.resultTableDuplicate.setItem(row,1,item_path_b)
            self.resultTableDuplicate.setItem(row,2,item_sim)


    def update_dir_table(self):
        self.searchDirTable.setRowCount(0)
        for i in config['search_dir']:
            row = self.searchDirTable.rowCount()
            self.searchDirTable.insertRow(row)
            item = QtWidgets.QTableWidgetItem(i)
            self.searchDirTable.setItem(row,0,item)


    def add_search_dir(self):
        self.input_path = QtWidgets.QFileDialog.getExistingDirectory(self,'选择一个需要索引的图片目录')
        if not self.input_path:
            return
        config['search_dir'].append(self.input_path)
        self.save_settings()
        self.update_dir_table()


    def remove_invalid_index(self):
        utils.remove_nonexists()
        self.exists_index = utils.get_exists_index()
        QtWidgets.QMessageBox.information(self, '提示', '无效索引已删除')


    def sync_index(self):
        # 创建并启动索引同步的后台线程
        if self.index_thread is None or not self.index_thread.isRunning():
            self.index_thread = IndexThread(utils)
            # self.index_thread.update_signal.connect(self.update_status)
            self.progress_dialog = QtWidgets.QProgressDialog(self)  # 创建进度条对话框
            self.progress_dialog.setWindowTitle("更新索引")  # 设置窗口标题
            self.progress_dialog.setCancelButtonText("取消")
            self.progress_dialog.setWindowModality(QtCore.Qt.WindowModal)  # 将进度条对话框设置为模态
            self.progress_dialog.setAutoClose(True)  # 完成后自动关闭
            self.progress_dialog.show()  # 显示进度条对话框
            self.index_thread.progress_signal.connect(self.update_progress_bar)
            self.index_thread.completed_signal.connect(self.show_completed_message)
            self.index_thread.start()
        else:
            QtWidgets.QMessageBox.information(self, '提示', '索引更新线程已经在运行')

    def update_status(self, status):
        # 更新UI界面上的状态
        if status == "完成索引更新":
            QtWidgets.QMessageBox.information(self, '提示', '索引已完成')

    def show_completed_message(self):
        # 显示索引更新完成的提示信息
        QtWidgets.QMessageBox.information(self, '提示', '索引更新完成')
        # 退出建立索引子线程
        self.index_thread.quit()
        self.index_thread.wait()
        self.index_thread.finished.connect(self.index_thread.deleteLater)
        self.exists_index = utils.get_exists_index() # 重新获取已存在索引,解决建立索引后立即执行搜索大概率不生效的问题

    def update_progress_bar(self, progress):
        self.progress_dialog.setValue(progress)

    def closeEvent(self, event):
        # 在窗口关闭时结束后台线程
        if self.index_thread is not None and self.index_thread.isRunning():
            self.index_thread.quit()
            self.index_thread.wait()
        event.accept()


    def save_settings(self):
        with open(config_path, 'wb') as wp:
            wp.write(json.dumps(config, indent=2, ensure_ascii=False).encode('UTF-8'))


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainUI()
    window.show()
    sys.exit(app.exec_())
