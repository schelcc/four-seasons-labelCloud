from typing import List, Union

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QWidget

from ...definitions import LabelingMode
from ...definitions.label_formats.base import BaseLabelFormat
from ...io.labels.config import LabelConfig


class SelectLabelingMode(QWidget):
    changed = pyqtSignal(LabelingMode)  # class_name, was_added

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        row_buttons = QHBoxLayout()
        self.setLayout(row_buttons)

        self._add_object_detection_button(row_buttons)
        self._add_semantic_segmentation_button(row_buttons)
        self._add_projection_calibration_button(row_buttons)

        self._initialize_buttons()

        self._connect_clicked_events()

    @property
    def selected_labeling_mode(self) -> LabelingMode:
        if self.button_object_detection.isChecked():
            return LabelingMode.OBJECT_DETECTION
        if self.button_semantic_segmentation.isChecked():
            return LabelingMode.SEMANTIC_SEGMENTATION
        if self.button_projection_calibration.isChecked():
            return LabelingMode.PROJECTION_CORRECTION
        raise Exception("No labeling mode selected.")

    @property
    def available_label_formats(
        self,
    ) -> List[BaseLabelFormat]:
        return self.selected_labeling_mode.get_available_formats()

    def _add_projection_calibration_button(self, parent: QHBoxLayout) -> None:
        self.button_projection_calibration = QPushButton(
            text=LabelingMode.PROJECTION_CORRECTION.title().replace("_", " ")
        )
        self.button_projection_calibration.setCheckable(True)
        self.button_projection_calibration.setToolTip(
            "This will set the usage mode to projection correction"
        )
        parent.addWidget(self.button_projection_calibration)

    def _add_object_detection_button(self, parent: QHBoxLayout) -> None:
        self.button_object_detection = QPushButton(
            text=LabelingMode.OBJECT_DETECTION.title().replace("_", " ")
        )
        self.button_object_detection.setCheckable(True)
        self.button_object_detection.setToolTip(
            "This will result in a label file for each point cloud\n"
            "with a bounding box for each annotated object."
        )
        parent.addWidget(self.button_object_detection)

    def _add_semantic_segmentation_button(self, parent: QHBoxLayout) -> None:
        self.button_semantic_segmentation = QPushButton(
            text=LabelingMode.SEMANTIC_SEGMENTATION.title().replace("_", " ")
        )
        self.button_semantic_segmentation.setCheckable(True)
        self.button_semantic_segmentation.setToolTip(
            "This will result in a *.bin file for each point cloud\n"
            "with a label for each annotated point of an object."
        )
        parent.addWidget(self.button_semantic_segmentation)

    def _initialize_buttons(self) -> None:
        if LabelConfig().type == LabelingMode.OBJECT_DETECTION:
            self.button_object_detection.setChecked(True)
        elif LabelConfig().type == LabelingMode.SEMANTIC_SEGMENTATION:
            self.button_semantic_segmentation.setChecked(True)
        elif LabelConfig().type == LabelingMode.PROJECTION_CORRECTION:
            self.button_projection_calibration.setChecked(True)

    def _connect_clicked_events(self) -> None:
        def select_projection_correction():
            self.button_projection_calibration.setChecked(True)
            self.button_object_detection.setChecked(False)
            self.button_semantic_segmentation.setChecked(False)
            self.changed.emit(self.selected_labeling_mode)
            
        self.button_projection_calibration.clicked.connect(select_projection_correction)
        
        def select_object_detection():
            self.button_object_detection.setChecked(True)
            self.button_semantic_segmentation.setChecked(False)
            self.button_projection_calibration.setChecked(False)
            self.changed.emit(self.selected_labeling_mode)

        self.button_object_detection.clicked.connect(select_object_detection)

        def select_semantic_segmentation():
            self.button_semantic_segmentation.setChecked(True)
            self.button_object_detection.setChecked(False)
            self.button_projection_calibration.setChecked(False)
            self.changed.emit(self.selected_labeling_mode)

        self.button_semantic_segmentation.clicked.connect(select_semantic_segmentation)
