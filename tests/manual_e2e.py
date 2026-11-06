import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.argv=['x']
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtCore import QPoint, Qt, QEvent
from PySide6.QtGui import QMouseEvent, QFont
app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
from jietu import main
a=main.App(app); time.sleep(3.0)
w=QLabel('Please check the configuration file before running the application.\nUpload file to server and save the result.')
w.setFont(QFont('Microsoft YaHei UI',20)); w.setStyleSheet('background:white;color:black;padding:20px')
w.resize(1200,200); w.move(200,200); w.show()
for _ in range(60): app.processEvents(); time.sleep(0.01)
from jietu.capture import CaptureOverlay
def mk(t,x,y): return QMouseEvent(t,QPoint(x,y),QPoint(x,y),Qt.LeftButton,Qt.LeftButton,Qt.NoModifier)
lines=[]
for trial in range(3):
    ov=CaptureOverlay(); ov.selection_changed.connect(a._on_selection); a.overlay=ov; a._ocr_generation+=1; ov.show()
    t0=time.perf_counter()
    ov.mousePressEvent(mk(QEvent.MouseButtonPress,210,210))
    ov.mouseMoveEvent(mk(QEvent.MouseMove,1390,390))
    ov.mouseReleaseEvent(mk(QEvent.MouseButtonRelease,1390,390))
    for _ in range(1200):
        app.processEvents(); time.sleep(0.005)
        if ov._result_text: break
    dt=(time.perf_counter()-t0)*1000
    lines.append(f'trial{trial}: {dt:.0f}ms | {len(ov._source_text)}字')
    if trial==0:
        lines.append('原文: '+ov._source_text[:80].replace('\n',' | '))
        lines.append('译文: '+ov._result_text[:80].replace('\n',' | '))
    ov.close_all(); time.sleep(0.2)
w.hide(); a.quit(); app.quit()
print('\n'.join(lines))
