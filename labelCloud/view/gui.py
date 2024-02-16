import logging
import numpy as np
import os
import re
import sys
import copy
import shutil
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set, Union

import pkg_resources
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QPixmap, QPainter, QPen
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QColorDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMessageBox,
)

from ..control.config_manager import config
from ..definitions import Color3f, LabelingMode, Camera
from ..definitions.types import Point2D
from ..io.labels.config import LabelConfig
from ..io.pointclouds import BasePointCloudHandler
from ..labeling_strategies import PickingStrategy, SpanningStrategy
from ..proj_correction_strategies import PointMatchCorrection
from ..model.point_cloud import PointCloud
from ..utils.decorators import in_labeling_only_decorator, in_projection_only_decorator
from ..image_management.image_manager import SingleImageManager
from .settings_dialog import SettingsDialog  # type: ignore
from .startup.dialog import StartupDialog
from .status_manager import StatusManager
from .viewer import GLWidget

if TYPE_CHECKING:
    from ..control.controller import Controller


def string_is_float(string: str, recect_negative: bool = False) -> bool:
    """Returns True if string can be converted to float"""
    try:
        decimal = float(string)
    except ValueError:
        return False
    if recect_negative and decimal < 0:
        return False
    return True


def set_floor_visibility(state: bool) -> None:
    logging.info(
        "%s floor grid (SHOW_FLOOR: %s).",
        "Activated" if state else "Deactivated",
        state,
    )
    config.set("USER_INTERFACE", "show_floor", str(state))


def set_orientation_visibility(state: bool) -> None:
    config.set("USER_INTERFACE", "show_orientation", str(state))


def set_zrotation_only(state: bool) -> None:
    config.set("USER_INTERFACE", "z_rotation_only", str(state))


def set_color_with_label(state: bool) -> None:
    config.set("POINTCLOUD", "color_with_label", str(state))


def set_keep_perspective(state: bool) -> None:
    config.set("USER_INTERFACE", "keep_perspective", str(state))


def set_propagate_labels(state: bool) -> None:
    config.set("LABEL", "propagate_labels", str(state))


# CSS file paths need to be set dynamically
STYLESHEET = """
    * {{
        background-color: #FFF;
        font-family: "DejaVu Sans", Arial;
    }}

    QMenu::item:selected {{
        background-color: #0000DD;
    }}

    QListWidget#label_list::item {{
        padding-left: 22px;
        padding-top: 7px;
        padding-bottom: 7px;
        background: url("{icons_dir}/cube-outline.svg") center left no-repeat;
    }}

    QListWidget#label_list::item:selected {{
        color: #FFF;
        border: none;
        background: rgb(0, 0, 255);
        background: url("{icons_dir}/cube-outline_white.svg") center left no-repeat, #0000ff;
    }}

    QComboBox#current_class_dropdown::item:checked{{
        color: gray;
    }}

    QComboBox#current_class_dropdown::item:selected {{
        color: #FFFFFF;
    }}

    QComboBox#current_class_dropdown{{
        selection-background-color: #0000FF;
    }}
"""

""" 
UI Properties:
visible_label
visible_projection

"""

class GUI(QtWidgets.QMainWindow):
    def __init__(self, control: "Controller") -> None:
        super(GUI, self).__init__()


        uic.loadUi(
            pkg_resources.resource_filename(
                "labelCloud.resources.interfaces", f"interface-label.ui"
            ),
            self,
        )
        self.resize(1500, 900)
        self.setWindowTitle("labelCloud")
        self.setStyleSheet(
            STYLESHEET.format(
                icons_dir=str(
                    Path(__file__)
                    .resolve()
                    .parent.parent.joinpath("resources")
                    .joinpath("icons")
                )
            )
        ) 
        self.all_ui_elements = []

        self.startup_dialog = StartupDialog()
        if self.startup_dialog.exec():
            pass
        else:
            sys.exit()

        self.LABELING = LabelConfig().type == LabelingMode.OBJECT_DETECTION
        self.PROJECTION = LabelConfig().type == LabelingMode.PROJECTION_CORRECTION
        self.SEMANTIC = LabelConfig().type == LabelingMode.SEMANTIC_SEGMENTATION
        
        # Segmentation only functionalities
        if LabelConfig().type == LabelingMode.OBJECT_DETECTION:
            self.button_assign_label.setVisible(False)
            self.act_color_with_label.setVisible(False)
        # Files
        self.act_set_pcd_folder: QtWidgets.QAction
        self.act_set_element_folder: QtWidgets.QAction
    
        # MENU BAR 
        self.act_z_rotation_only: QtWidgets.QAction # In labeling only
        self.act_color_with_label: QtWidgets.QAction # In labeling only
        self.act_show_floor: QtWidgets.QAction
        self.act_show_orientation: QtWidgets.QAction
        self.act_save_perspective: QtWidgets.QAction
        self.act_align_pcd: QtWidgets.QAction
        self.act_change_settings: QtWidgets.QAction

        self.current_element_label: QtWidgets.QLabel

        self.status_bar: QtWidgets.QStatusBar
        self.status_manager = StatusManager(self.status_bar)

        self.gl_widget: GLWidget

        self.label_current_pcd: QtWidgets.QLabel
        self.button_prev_pcd: QtWidgets.QPushButton
        self.button_next_pcd: QtWidgets.QPushButton
        self.button_set_pcd: QtWidgets.QPushButton
        self.progressbar_pcds: QtWidgets.QProgressBar

        self.act_delete_all_elements: QtWidgets.QAction
        self.act_set_default_class: QtWidgets.QMenu # In labeling only
        self.actiongroup_default_class = QActionGroup(self.act_set_default_class) # In labeling only
        self.act_propagate_labels: QtWidgets.QAction # In labeling only

        self.bbox_controls : QtWidgets.QGroupBox
        self.button_bbox_up: QtWidgets.QPushButton # In labeling only
        self.button_bbox_down: QtWidgets.QPushButton # In labeling only
        self.button_bbox_left: QtWidgets.QPushButton # In labeling only
        self.button_bbox_right: QtWidgets.QPushButton # In labeling only
        self.button_bbox_forward: QtWidgets.QPushButton # In labeling only
        self.button_bbox_backward: QtWidgets.QPushButton # In labeling only
        self.dial_bbox_z_rotation: QtWidgets.QDial # In labeling only
        self.button_bbox_decrease_dimension: QtWidgets.QPushButton # In labeling only
        self.button_bbox_increase_dimension: QtWidgets.QPushButton # In labeling only

        self.button_pick_bbox: QtWidgets.QPushButton # In labeling only
        self.button_span_bbox: QtWidgets.QPushButton # In labeling only
        self.button_save: QtWidgets.QPushButton


        self.element_list: QtWidgets.QListWidget
        self.element_list.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self.current_class_dropdown: QtWidgets.QComboBox # In labeling only
        self.button_deselect_element: QtWidgets.QPushButton
        self.button_delete_element: QtWidgets.QPushButton
        self.button_assign_label: QtWidgets.QPushButton # In labeling only

        self.current_class_title: QtWidgets.QLabel

        self.act_change_class_color = QtWidgets.QAction("Change class color") # In labeling only
        self.act_delete_class = QtWidgets.QAction("Delete label") # In labeling only
        self.act_crop_pointcloud_inside = QtWidgets.QAction("Save points inside as") # In labeling only
        
        self.row1_col1_edit: QtWidgets.QLineEdit
        self.row1_col2_edit: QtWidgets.QLineEdit
        self.row1_col3_edit: QtWidgets.QLineEdit

        self.row2_col1_edit: QtWidgets.QLineEdit
        self.row2_col2_edit: QtWidgets.QLineEdit
        self.row2_col3_edit: QtWidgets.QLineEdit

        self.row3_col1_edit: QtWidgets.QLineEdit
        self.row3_col2_edit: QtWidgets.QLineEdit
        self.row3_col3_edit: QtWidgets.QLineEdit

        self.row4_col1_label: QtWidgets.QLabel
        self.row4_col2_label: QtWidgets.QLabel
        self.row4_col3_label: QtWidgets.QLabel

        self.row1_name_label: QtWidgets.QLabel
        self.row2_name_label: QtWidgets.QLabel
        self.row3_name_label: QtWidgets.QLabel
        self.row4_name_label: QtWidgets.QLabel

        self.all_line_edits = [
            self.row1_col1_edit,
            self.row1_col2_edit,
            self.row1_col3_edit,
            self.row2_col1_edit,
            self.row2_col2_edit,
            self.row2_col3_edit,
            self.row3_col1_edit,
            self.row3_col2_edit,
            self.row3_col3_edit
        ]

        self.label_volume: QtWidgets.QLabel # In labeling only

        self.button_point_match: QtWidgets.QPushButton # In projection only

        self.camera_left: QtWidgets.QLabel
        self.camera_right: QtWidgets.QLabel
        self.camera_middle: QtWidgets.QLabel

        self.manager_camera_left: SingleImageManager = SingleImageManager(self.camera_left, self)
        self.manager_camera_middle: SingleImageManager = SingleImageManager(self.camera_middle, self)
        self.manager_camera_right: SingleImageManager = SingleImageManager(self.camera_right, self)

        self.image_label_list = [
            self.camera_left,
            self.camera_middle,
            self.camera_right,
        ]
        
        self.image_manager_list = [
            self.manager_camera_left,
            self.manager_camera_middle,
            self.manager_camera_right,
        ]

        self.populate_ui_list()
        
        self.cam_list = config.getlist("FILE", "image_list")

        for idx, item in enumerate(self.image_manager_list):
            item.set_camera(idx)
        
        self.controller = control
        self.controller.pcd_manager.pcd_postfix = config.get("POINTCLOUD", "pointcloud_postfix") # LXH

        # Connect all events to functions
        self.connect_events()
        self.set_checkbox_states()  # tick in menu

        # Connect with controller
        self.controller.startup(self)

        # Start event cycle
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(20)  # period, in milliseconds
        self.timer.timeout.connect(self.controller.loop_gui)
        self.timer.start()   

    def populate_ui_list(self) -> None:
        self.all_ui_elements = [
            self.current_element_label,
            self.act_set_pcd_folder,
            self.current_class_title,
            self.act_set_element_folder,
            self.act_z_rotation_only,
            self.act_color_with_label,
            self.act_show_floor,
            self.act_show_orientation,
            self.act_save_perspective,
            self.act_align_pcd,
            self.act_change_settings,
            self.status_bar,
            self.gl_widget,
            self.label_current_pcd,
            self.button_prev_pcd,
            self.button_next_pcd,
            self.button_set_pcd,
            self.progressbar_pcds,
            self.act_delete_all_elements,
            self.act_set_default_class,
            self.actiongroup_default_class,
            self.act_propagate_labels,
            self.bbox_controls,
            self.button_bbox_up,
            self.button_bbox_down,
            self.button_bbox_left,
            self.button_bbox_right,
            self.button_bbox_forward,
            self.button_bbox_backward,
            self.dial_bbox_z_rotation,
            self.button_bbox_decrease_dimension,
            self.button_bbox_increase_dimension,
            self.button_pick_bbox,
            self.button_span_bbox,
            self.button_save,
            self.element_list,
            self.current_class_dropdown,
            self.button_deselect_element,
            self.button_delete_element,
            self.button_assign_label,
            self.act_change_class_color,
            self.act_delete_class,
            self.act_crop_pointcloud_inside,
            self.row1_col1_edit,
            self.row1_col2_edit,
            self.row1_col3_edit,
            self.row2_col1_edit,
            self.row2_col2_edit,
            self.row2_col3_edit,
            self.row3_col1_edit,
            self.row3_col2_edit,
            self.row3_col3_edit,
            self.row1_name_label,
            self.row2_name_label,
            self.row3_name_label,
            self.row4_name_label,
            self.button_point_match,
            self.camera_left,
            self.camera_right,
            self.camera_middle,
        ]

    def prop_fallback(self, ui_element, prop, fallback):
        if ui_element.property(prop) is None:
            return fallback 
        else:
            return ui_element.property(prop)
    
    def connect_events(self) -> None:
        for ui_element in self.all_ui_elements:
            
            visible_labeling = self.prop_fallback(ui_element, "visible_labeling", True) 
            visible_projection = self.prop_fallback(ui_element, "visible_projection", True)
            text_labeling = ui_element.property("text_labeling")
            text_projection = ui_element.property("text_projection")

            # Debugging            
            logging.debug(f"[UI INIT] Name: \"{ui_element.objectName()}\"")
            logging.debug(f"\t- visible_labeling: {str(visible_labeling)}")
            logging.debug(f"\t- visible_projection: {str(visible_projection)}")
            logging.debug(f"\t- text_labeling: {str(text_labeling)}")
            logging.debug(f"\t- text_projection: {str(text_projection)}")

            is_visible = (visible_labeling and self.LABELING) or (visible_projection and self.PROJECTION)
            ui_element.setVisible(is_visible)

            logging.debug(f"\t- is currently visible: {str(is_visible)}")

            if text_labeling is not None and self.LABELING:
                ui_element.setText(text_labeling)
            elif text_projection is not None and self.PROJECTION:
                ui_element.setText(text_projection)

            connections = ui_element.property("connections")
            
            if connections is None or not is_visible:
                continue
            
            connections = connections.split(';')

            conn_events = ["clicked", "pressed", "triggered", "toggled", "valueChanged", "currentTextChanged", "currentRowChanged"]
            for conn_event in conn_events:
                if ui_element.property(f"on_{conn_event}"):
                    for conn in connections:
                        logging.debug(f"\t- connecting {conn_event} w/ \"{conn}\"")
                        _globals = globals().copy()
                        _globals.update(locals())
                            
                        exec(f"ui_element.{conn_event}.connect({conn})", _globals)
        logging.debug(" ")
                      
    def set_checkbox_states(self) -> None:
        if self.LABELING:
            self.act_propagate_labels.setChecked(
            config.getboolean("LABEL", "propagate_labels")
            )
            self.act_z_rotation_only.setChecked(
                config.getboolean("USER_INTERFACE", "z_rotation_only")
            )
            self.act_color_with_label.setChecked(
                config.getboolean("POINTCLOUD", "color_with_label")
            )

        self.act_show_floor.setChecked(
            config.getboolean("USER_INTERFACE", "show_floor")
        )
        self.act_show_orientation.setChecked(
            config.getboolean("USER_INTERFACE", "show_orientation")
        )
        

    # Collect, filter and forward events to viewer
    def eventFilter(self, event_object, event) -> bool:
        if self.LABELING:
            self.bbox_previous = copy.deepcopy(self.controller.element_controller.get_active_element())

        # Keyboard Events
        if (event.type() == QEvent.KeyPress) and event_object in [
            self,
            self.element_list,
        ]:
            if self.LABELING:
                self.update_bbox_stats(self.controller.element_controller.get_active_element())
            if self.PROJECTION:
                pass
            self.controller.key_press_event(event)
            return True  # TODO: Recheck pyqt behaviour

        elif event.type() == QEvent.KeyRelease:
            self.controller.key_release_event(event)

        # Mouse Events
        if (event.type() == QEvent.MouseMove):
            if (event_object == self.gl_widget): # MOUSE MOVE
                self.controller.mouse_move_event(event)
                if self.LABELING:
                    self.update_bbox_stats(self.controller.element_controller.get_active_element())
            if (event_object in self.image_label_list):
                idx = self.image_label_list.index(event_object)
                for cam, manager in enumerate(self.image_manager_list):
                    manager.cursor_pos = (event.x(), event.y()) if cam == idx else None 
                    manager.render()
            else:
                for cam, manager in enumerate(self.image_manager_list):
                    manager.cursor_pos = None 

#            if self.PROJECTION:
#                locs = ["Left", "Middle", "Right", "Cloud", "Other"]
#                if event_object in self.image_label_list:
#                    idx = self.image_label_list.index(event_object)
#                elif event_object == self.gl_widget:
#                    idx = 3
#                else:
#                    idx = 4
#                self.cursor_pos_loc_label.setText(locs[idx])
#                self.cursor_pos_x_label.setText(str(event.x()))
#                self.cursor_pos_y_label.setText(str(event.y()))
                 
        elif (event.type() == QEvent.Wheel) and (event_object == self.gl_widget): # MOUSE SCROLL
            self.controller.mouse_scroll_event(event)
            if self.LABELING:
                self.update_bbox_stats(self.controller.element_controller.get_active_element())
        elif (event.type() == QEvent.Wheel) and (event_object in self.image_label_list):
            self.controller.image_mouse_scroll_event(event)
            self.refresh_2d_image()

        elif event.type() == QEvent.MouseButtonDblClick and ( # MOUSE DOUBLE CLICK
            event_object == self.gl_widget
        ):
            self.controller.mouse_double_clicked(event)
            return True
        
        elif (event.type() == QEvent.MouseButtonPress) and ( # MOUSE SINGLE CLICK - NOT ON IMAGE
            event_object == self.gl_widget
        ):
            self.controller.mouse_clicked(event)
            if self.LABELING:
                self.update_bbox_stats(self.controller.element_controller.get_active_element())

        elif (event.type() == QEvent.MouseButtonPress) and ( # MOUSE SINGLE CLICK - ON IMAGE
            event_object in self.image_label_list
        ):
            self.controller.image_clicked(event, event_object)

        elif (event.type() == QEvent.MouseButtonPress) and (
            self.LABELING
        ) and ( # ???
            event_object != self.current_class_dropdown
        ):
            self.current_class_dropdown.clearFocus()
            self.update_bbox_stats(self.controller.element_controller.get_active_element())
        return False

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        logging.info("Closing window after saving ...")
        self.controller.save()
        self.timer.stop()
        a0.accept()

    def show_settings_dialog(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()

    def init_2d_image(self):
        """Searches for a 2D image with the point cloud name and displays it in a new window."""
        for lbl in self.image_manager_list:
            lbl.load_image()
            lbl.render()

    def refresh_2d_image(self):
        """Re-renders images w/o refreshing pixmaps"""
        for lbl in self.image_manager_list:
            lbl.render()
            
##        P_matrix = config.getlist("FILE", "pmatrix_list")
##        P_matrix = np.array(P_matrix).reshape(-1,3,4)
##        margin = 100
#            self.image_label_list[i].show()
   

    def show_no_pointcloud_dialog(
        self, pcd_folder: Path, pcd_extensions: Set[str]
    ) -> None:
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setText(
            "<b>labelCloud could not find any valid point cloud files inside the "
            "specified folder.</b>"
        )
        msg.setInformativeText(
            f"Please copy all your point clouds into <code>{pcd_folder.resolve()}</code> or update "
            "the point cloud folder location. labelCloud supports the following point "
            f"cloud file formats:\n {', '.join(pcd_extensions)}."
        )
        msg.setWindowTitle("No Point Clouds Found")
        msg.exec_()

    # VISUALIZATION METHODS

    def set_pcd_label(self, pcd_name: str) -> None:
        self.label_current_pcd.setText("Current: <em>%s</em>" % pcd_name)

    def init_progress(self, min_value, max_value):
        self.progressbar_pcds.setMinimum(min_value)
        self.progressbar_pcds.setMaximum(max_value)

    def update_progress(self, value) -> None:
        self.progressbar_pcds.setValue(value)

    def update_current_class_dropdown(self) -> None:
        self.controller.pcd_manager.populate_class_dropdown()

#    def update_bbox_stats(self, bbox) -> None:
#        viewing_precision = config.getint("USER_INTERFACE", "viewing_precision")
#        if bbox and not self.line_edited_activated():
#            self.edit_pos_x.setText(str(round(bbox.get_center()[0], viewing_precision)))
#            self.edit_pos_y.setText(str(round(bbox.get_center()[1], viewing_precision)))
#            self.edit_pos_z.setText(str(round(bbox.get_center()[2], viewing_precision)))
#
#            self.edit_length.setText(
#                str(round(bbox.get_dimensions()[0], viewing_precision))
#            )
#            self.edit_width.setText(
#                str(round(bbox.get_dimensions()[1], viewing_precision))
#            )
#            self.edit_height.setText(
#                str(round(bbox.get_dimensions()[2], viewing_precision))
#            )
#
#            self.edit_rot_x.setText(str(round(bbox.get_x_rotation(), 1)))
#            self.edit_rot_y.setText(str(round(bbox.get_y_rotation(), 1)))
#            self.edit_rot_z.setText(str(round(bbox.get_z_rotation(), 1)))
#
#            self.label_volume.setText(str(round(bbox.get_volume(), viewing_precision)))
#        if self.bbox_previous is not None and bbox:
            # change check
#            if (self.bbox_previous.center != bbox.center 
#                or self.bbox_previous.height != bbox.height
#                or self.bbox_previous.width != bbox.width
#                or self.bbox_previous.length != bbox.length
#                or self.bbox_previous.z_rotation != bbox.z_rotation):


#    def update_bbox_parameter(self, parameter: str) -> None:
#        str_value = None
#        self.setFocus()  # Changes the focus from QLineEdit to the window
#
#        if parameter == "pos_x":
#            str_value = self.edit_pos_x.text()
#        if parameter == "pos_y":
#            str_value = self.edit_pos_y.text()
#        if parameter == "pos_z":
#            str_value = self.edit_pos_z.text()
#        if str_value and string_is_float(str_value):
#            self.controller.bbox_controller.update_position(parameter, float(str_value))
#            return
#
#        if parameter == "length":
#            str_value = self.edit_length.text()
#        if parameter == "width":
#            str_value = self.edit_width.text()
#        if parameter == "height":
#            str_value = self.edit_height.text()
#        if str_value and string_is_float(str_value, recect_negative=True):
#            self.controller.bbox_controller.update_dimension(
#                parameter, float(str_value)
#            )
#            return
#
#        if parameter == "rot_x":
#            str_value = self.edit_rot_x.text()
#        if parameter == "rot_y":
#            str_value = self.edit_rot_y.text()
#        if parameter == "rot_z":
#            str_value = self.edit_rot_z.text()
#        if str_value and string_is_float(str_value):
#            self.controller.bbox_controller.update_rotation(parameter, float(str_value))
#            return

    # Enables, disables the draw mode
    def activate_draw_modes(self, state: bool) -> None:
        if self.LABELING:
            self.button_pick_bbox.setEnabled(state)
            self.button_span_bbox.setEnabled(state)
        elif self.PROJECTION:
            self.button_point_match.setEnabled(state)

    def line_edited_activated(self) -> bool:
        for line_edit in self.all_line_edits:
            if line_edit.hasFocus():
                return True
        return False

    def change_pointcloud_folder(self) -> None:
        path_to_folder = Path(
            QFileDialog.getExistingDirectory(
                self,
                "Change Point Cloud Folder",
                directory=config.get("FILE", "pointcloud_folder"),
            )
        )
        if not path_to_folder.is_dir():
            logging.warning("Please specify a valid folder path.")
        else:
            self.controller.pcd_manager.pcd_folder = path_to_folder
            self.controller.pcd_manager.read_pointcloud_folder()
            self.controller.pcd_manager.get_next_pcd()
            logging.info("Changed point cloud folder to %s!" % path_to_folder)

    def change_element_folder(self) -> None:
        path_to_folder = Path(
            QFileDialog.getExistingDirectory(
                self,
                "Change Element Folder",
                directory=config.get("FILE", "element_folder"),
            )
        )
        if not path_to_folder.is_dir():
            logging.warning("Please specify a valid folder path.")
        else:
            # TODO
            self.controller.pcd_manager.label_manager.label_folder = path_to_folder
            self.controller.pcd_manager.label_manager.label_strategy.update_label_folder(
                path_to_folder
            )
            logging.info("Changed label folder to %s!" % path_to_folder)

    def update_default_object_class_menu(
        self, new_classes: Optional[Set[str]] = None
    ) -> None:
        object_classes = set(LabelConfig().get_classes())

        object_classes.update(new_classes or [])
        existing_classes = {
            action.text() for action in self.actiongroup_default_class.actions()
        }
        for object_class in object_classes.difference(existing_classes):
            action = self.actiongroup_default_class.addAction(
                object_class
            )  # TODO: Add limiter for number of classes
            action.setCheckable(True)
            if object_class == LabelConfig().get_default_class_name():
                action.setChecked(True)

        self.act_set_default_class.addActions(self.actiongroup_default_class.actions())

    def change_default_object_class(self, action: QAction) -> None:
        LabelConfig().set_default_class(action.text())
        logging.info("Changed default object class to %s.", action.text())

    def ask_custom_index(self):
        input_d = QInputDialog(self)
        self.input_pcd = input_d
        input_d.setInputMode(QInputDialog.IntInput)
        input_d.setWindowTitle("labelCloud")
        input_d.setLabelText("Insert Point Cloud number: ()")
        input_d.setIntMaximum(len(self.controller.pcd_manager.pcds) - 1)
        input_d.intValueChanged.connect(lambda val: self.update_dialog_pcd(val))
        input_d.intValueSelected.connect(lambda val: self.controller.custom_pcd(val))
        input_d.open()
        self.update_dialog_pcd(0)

    def update_dialog_pcd(self, value: int) -> None:
        pcd_path = self.controller.pcd_manager.pcds[value]
        self.input_pcd.setLabelText(f"Insert Point Cloud number: {pcd_path.name}")

    def change_label_color(self):
        bbox = self.controller.element_controller.get_active_element()
        LabelConfig().set_class_color(
            bbox.classname, Color3f.from_qcolor(QColorDialog.getColor())
        )

    @staticmethod
    def save_point_cloud_as(pointcloud: PointCloud) -> None:
        extensions = BasePointCloudHandler.get_supported_extensions()
        make_filter = " ".join(["*" + extension for extension in extensions])
        file_filter = f"Point Cloud File ({make_filter})"
        file_name, _ = QFileDialog.getSaveFileName(
            caption="Select a file name to save the point cloud",
            directory=str(pointcloud.path.parent),
            filter=file_filter,
            initialFilter=file_filter,
        )
        if file_name == "":
            logging.warning("No file path provided. Ignored.")
            return

        try:
            path = Path(file_name)
            handler = BasePointCloudHandler.get_handler(path.suffix)
            handler.write_point_cloud(path, pointcloud)
        except Exception as e:
            msg = QMessageBox()
            msg.setWindowTitle("Failed to save a point cloud")
            msg.setText(e.__class__.__name__)
            msg.setInformativeText(traceback.format_exc())
            msg.setIcon(QMessageBox.Critical)
            msg.setStandardButtons(QMessageBox.Cancel)
            msg.exec_()
