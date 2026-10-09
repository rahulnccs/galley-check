"""The Applications chart: one row per application, columns for the stages
it can reach, grouped into bands by where it stands.

A row's dots mark the stages the application reached, joined by a solid
line. An award ends in a filled circle under Outcome; an unsuccessful one in
a cross, reached by a dashed line from where it stopped; one still under
review stops at its current stage. Applications being prepared show their
deadline instead. Clicking a row opens the application.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .fellowships_page import APPLE, SOFT

COLUMNS = ["Submitted", "Shortlisted", "Interview", "Outcome"]
BAND_LABEL = {"preparing": "Preparing", "pending": "Pending", "awarded": "Awarded",
              "unsuccessful": "Unsuccessful", "withdrawn": "Withdrawn"}
BAND_COLOR = {"preparing": SOFT["indigo"], "pending": SOFT["blue"],
              "awarded": SOFT["green"], "unsuccessful": SOFT["red"],
              "withdrawn": SOFT["grey"]}
HEADER, ROW, STRIP, LABEL_W, NOTE_W = 40, 54, 24, 300, 170


@dataclass
class ChartRow:
    key: str            # the fellowship id, emitted when the row is clicked
    title: str
    subtitle: str
    band: str
    reached: int        # -1 not submitted, 0 submitted, 1 shortlisted, 2 interview
    note: str = ""      # under Outcome, or the deadline for a row in preparation


def _font(base: QFont, scale: float = 1.0, bold: bool = False) -> QFont:
    """`base` scaled, whether its size is set in points or pixels."""
    f = QFont(base)
    if f.pointSizeF() > 0:
        f.setPointSizeF(f.pointSizeF() * scale)
    elif f.pixelSize() > 0:
        f.setPixelSize(max(8, round(f.pixelSize() * scale)))
    f.setBold(bold)
    return f


def _tint(color: str, alpha: int) -> QColor:
    c = QColor(color)
    c.setAlpha(alpha)
    return c


class PipelineChart(QWidget):
    rowClicked = Signal(str)

    def __init__(self, rows: list[ChartRow]):
        super().__init__()
        self.rows = rows
        self.hover = -1
        self.setMouseTracking(True)
        self.setMinimumSize(760, HEADER + ROW * max(1, len(rows)) + 10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

    # -- geometry -------------------------------------------------------------------
    def column_x(self, i: int) -> float:
        """Centre of stage column i (3 = Outcome)."""
        left = LABEL_W + 20
        span = self.width() - left - NOTE_W
        return left + span * (i + 0.5) / len(COLUMNS)

    def row_at(self, y: float) -> int:
        i = int((y - HEADER) // ROW)
        return i if y >= HEADER and 0 <= i < len(self.rows) else -1

    # -- events ---------------------------------------------------------------------
    def mouseMoveEvent(self, e):
        i = self.row_at(e.position().y())
        if i != self.hover:
            self.hover = i
            self.setToolTip(self.rows[i].title if i >= 0 else "")
            self.update()

    def leaveEvent(self, e):
        self.hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        i = self.row_at(e.position().y())
        if i >= 0 and e.button() == Qt.LeftButton:
            self.rowClicked.emit(self.rows[i].key)

    # -- drawing --------------------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        p.fillRect(self.rect(), QColor("white"))

        p.setFont(_font(self.font(), 0.88, bold=True))
        p.setPen(QColor(APPLE["secondary"]))
        for i, name in enumerate(COLUMNS):
            x = self.column_x(i)
            p.drawText(QRectF(x - 60, 8, 120, HEADER - 12), Qt.AlignCenter, name)
        grid = QPen(QColor(APPLE["fill"]), 1)
        p.setPen(grid)
        bottom = HEADER + ROW * len(self.rows)
        for i in range(1, len(COLUMNS)):
            x = (self.column_x(i - 1) + self.column_x(i)) / 2
            p.drawLine(QPointF(x, 6), QPointF(x, bottom))

        # Rows, with alternate shading and the hovered one highlighted.
        for i, r in enumerate(self.rows):
            y = HEADER + ROW * i
            if i == self.hover:
                p.fillRect(QRectF(STRIP, y, w - STRIP, ROW), QColor("#EAF2FF"))
            elif i % 2 == 0:
                p.fillRect(QRectF(STRIP, y, w - STRIP, ROW), QColor("#F7F7F9"))
            self._draw_row(p, r, y)

        # Bands: a tinted strip with the band's name, and a dashed rule between.
        start = 0
        for i in range(1, len(self.rows) + 1):
            if i == len(self.rows) or self.rows[i].band != self.rows[start].band:
                band = self.rows[start].band
                top, h = HEADER + ROW * start, ROW * (i - start)
                p.fillRect(QRectF(0, top, STRIP - 4, h), _tint(BAND_COLOR[band], 70))
                p.save()
                p.translate(STRIP / 2 - 2, top + h / 2)
                p.rotate(-90)
                f = _font(self.font(), 0.72, bold=True)
                f.setLetterSpacing(QFont.PercentageSpacing, 110)
                p.setFont(f)
                p.setPen(QColor(BAND_COLOR[band]).darker(135))
                text = BAND_LABEL[band].upper() if h >= 70 else BAND_LABEL[band][:4].upper()
                p.drawText(QRectF(-h / 2, -8, h, 16), Qt.AlignCenter, text)
                p.restore()
                if i < len(self.rows):
                    pen = QPen(QColor(APPLE["tertiary"]), 1, Qt.DashLine)
                    p.setPen(pen)
                    p.drawLine(QPointF(0, top + h), QPointF(w, top + h))
                start = i
        p.end()

    def _draw_row(self, p: QPainter, r: ChartRow, y: float):
        mid = y + ROW / 2
        p.setFont(_font(self.font(), bold=True))
        p.setPen(QColor(APPLE["label"]))
        fm = p.fontMetrics()
        p.drawText(QRectF(STRIP + 10, y + 7, LABEL_W - 4, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(r.title, Qt.ElideRight, LABEL_W - 4))
        p.setFont(_font(self.font(), 0.85))
        p.setPen(QColor(APPLE["secondary"]))
        p.drawText(QRectF(STRIP + 10, y + 28, LABEL_W - 4, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(r.subtitle, Qt.ElideRight, LABEL_W - 4))

        color = QColor(BAND_COLOR[r.band])
        outcome_x = self.column_x(3)
        note_rect = QRectF(outcome_x + 22, y, NOTE_W + 10, ROW)
        if r.band == "preparing":
            # Not submitted yet: an open circle where it will be, and the deadline.
            x0 = self.column_x(0)
            p.setPen(QPen(color, 1.6, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(x0, mid), 7, 7)
            p.setFont(self.font())
            p.setPen(QColor(APPLE["secondary"]))
            p.drawText(QRectF(x0 + 14, y, outcome_x - x0 + NOTE_W, ROW),
                       Qt.AlignLeft | Qt.AlignVCenter, r.note)
            return

        last = max(0, r.reached)
        xs = [self.column_x(i) for i in range(last + 1)]
        p.setPen(QPen(color, 2.5))
        if len(xs) > 1:
            p.drawLine(QPointF(xs[0], mid), QPointF(xs[-1], mid))
        if r.band == "awarded":
            p.drawLine(QPointF(xs[-1], mid), QPointF(outcome_x, mid))
        elif r.band in ("unsuccessful", "withdrawn"):
            p.setPen(QPen(_tint(color.name(), 170), 1.8, Qt.DashLine))
            p.drawLine(QPointF(xs[-1] + 8, mid), QPointF(outcome_x - 12, mid))
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        for x in xs:
            p.drawEllipse(QPointF(x, mid), 7, 7)

        p.setFont(self.font())
        if r.band == "awarded":
            p.setBrush(color.darker(115))
            p.drawEllipse(QPointF(outcome_x, mid), 11, 11)
            p.setPen(QColor(APPLE["label"]))
            p.drawText(note_rect, Qt.AlignLeft | Qt.AlignVCenter, r.note or "Awarded")
        elif r.band == "unsuccessful":
            p.setPen(QPen(color.darker(110), 3.2, Qt.SolidLine, Qt.RoundCap))
            for dx in (-1, 1):
                p.drawLine(QPointF(outcome_x - 9, mid - 9 * dx), QPointF(outcome_x + 9, mid + 9 * dx))
            p.setPen(QColor(APPLE["label"]))
            p.drawText(note_rect, Qt.AlignLeft | Qt.AlignVCenter, r.note)
        elif r.band == "withdrawn":
            p.setPen(QPen(color, 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(outcome_x - 9, mid), QPointF(outcome_x + 9, mid))
            p.setPen(QColor(APPLE["secondary"]))
            p.drawText(note_rect, Qt.AlignLeft | Qt.AlignVCenter, r.note or "Withdrawn")
        else:                                   # pending
            ring = QPen(color, 1.6, Qt.DotLine)
            p.setPen(ring)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(outcome_x, mid), 9, 9)
            p.setPen(QColor(APPLE["label"]))
            p.drawText(note_rect, Qt.AlignLeft | Qt.AlignVCenter, r.note or "Pending")
