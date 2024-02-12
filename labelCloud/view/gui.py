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

class GUI(QtWidgets.QMainWindow):
    def __init__(self, control: "Controller") -> None:
        super(GUI, self).__init__()

        usage_mode = config.get("FILE", "usage_mode")

        usage_mode = usage_mode.replace("\"", "")

        self.in_labeling = (usage_mode == "label")
        self.in_projection = (usage_mode == "projection")        
        
        logging.info(f"Usage mode is {usage_mode}")

        # TODO Add image cursor to draw crosshairs, 
        # then we can do automatic point-match completion when sufficient
        # points are selected (eliminating drawing preview for it)
         
        uic.loadUi(
            pkg_resources.resource_filename(
                "labelCloud.resources.interfaces", f"interface-{usage_mode}.ui"
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

        # Files
        self.act_set_pcd_folder: QtWidgets.QAction
        self.act_set_label_folder: QtWidgets.QAction
        
        # MENU BAR 
        self.act_z_rotation_only: QtWidgets.QAction
        self.act_color_with_label: QtWidgets.QAction
        self.act_show_floor: QtWidgets.QAction
        self.act_show_orientation: QtWidgets.QAction
        self.act_save_perspective: QtWidgets.QAction
        self.act_align_pcd: QtWidgets.QAction
        self.act_change_settings: QtWidgets.QAction

        self.status_bar: QtWidgets.QStatusBar
        self.status_manager = StatusManager(self.status_bar)

        self.gl_widget: GLWidget

        self.label_current_pcd: QtWidgets.QLabel
        self.button_prev_pcd: QtWidgets.QPushButton
        self.button_next_pcd: QtWidgets.QPushButton
        self.button_set_pcd: QtWidgets.QPushButton
        self.progressbar_pcds: QtWidgets.QProgressBar

        #if self.in_labeling:
        self.act_delete_all_labels: QtWidgets.QAction
        self.act_set_default_class: QtWidgets.QMenu
        self.actiongroup_default_class = QActionGroup(self.act_set_default_class)
        self.act_propagate_labels: QtWidgets.QAction
            # bbox control section
        self.button_bbox_up: QtWidgets.QPushButton
        self.button_bbox_down: QtWidgets.QPushButton
        self.button_bbox_left: QtWidgets.QPushButton
        self.button_bbox_right: QtWidgets.QPushButton
        self.button_bbox_forward: QtWidgets.QPushButton
        self.button_bbox_backward: QtWidgets.QPushButton
        self.dial_bbox_z_rotation: QtWidgets.QDial
        self.button_bbox_decrease_dimension: QtWidgets.QPushButton
        self.button_bbox_increase_dimension: QtWidgets.QPushButton

        self.button_pick_bbox: QtWidgets.QPushButton
        self.button_span_bbox: QtWidgets.QPushButton
        self.button_save_label: QtWidgets.QPushButton

        self.button_complete_selection: QtWidgets.QPushButton

        self.label_list: QtWidgets.QListWidget
        self.current_class_dropdown: QtWidgets.QComboBox
        self.button_deselect_label: QtWidgets.QPushButton
        self.button_delete_label: QtWidgets.QPushButton
        self.button_assign_label: QtWidgets.QPushButton

        self.act_change_class_color = QtWidgets.QAction("Change class color")
        self.act_delete_class = QtWidgets.QAction("Delete label")
        self.act_crop_pointcloud_inside = QtWidgets.QAction("Save points inside as")
        
        # BOUNDING BOX PARAMETER EDITS 
        # TODO Fix
#        self.edit_pos_x: QtWidgets.QLineEdit
#        self.edit_pos_y: QtWidgets.QLineEdit
#        self.edit_pos_z: QtWidgets.QLineEdit
#
#        self.edit_length: QtWidgets.QLineEdit
#        self.edit_width: QtWidgets.QLineEdit
#        self.edit_height: QtWidgets.QLineEdit
#
#        self.edit_rot_x: QtWidgets.QLineEdit
#        self.edit_rot_y: QtWidgets.QLineEdit
#        self.edit_rot_z: QtWidgets.QLineEdit
#
#        self.all_line_edits = [
#            self.edit_pos_x,
#            self.edit_pos_y,
#            self.edit_pos_z,
#            self.edit_length,
#            self.edit_width,
#            self.edit_height,
#            self.edit_rot_x,
#            self.edit_rot_y,
#            self.edit_rot_z,
#        ]

        self.label_volume: QtWidgets.QLabel

        #elif self.in_projection:
        self.button_point_match: QtWidgets.QPushButton

        self.camera_left: QtWidgets.QLabel
        self.camera_right: QtWidgets.QLabel
        self.camera_middle: QtWidgets.QLabel

        self.manager_camera_left: SingleImageManager = SingleImageManager(self.camera_left)
        self.manager_camera_middle: SingleImageManager = SingleImageManager(self.camera_middle)
        self.manager_camera_right: SingleImageManager = SingleImageManager(self.camera_right)

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
        
        self.current_pixmaps = []

        self.camera_label: QtWidgets.QLabel
        self.camera_title_label: QtWidgets.QLabel

        self.point2d_label_x: QtWidgets.QLabel
        self.point2d_label_y: QtWidgets.QLabel
        self.point2d_title_label: QtWidgets.QLabel

        self.point3d_label_x: QtWidgets.QLabel
        self.point3d_label_y: QtWidgets.QLabel
        self.point3d_label_z: QtWidgets.QLabel
        self.point3d_title_label: QtWidgets.QLabel

        self.point_list: QtWidgets.QListWidget
            #self.point_list.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)


        self.cam_list = config.getlist("FILE", "image_list")
        
        self.controller = control
        self.controller.pcd_manager.pcd_postfix = config.get("POINTCLOUD", "pointcloud_postfix") # LXH

        # Connect all events to functions
        self.connect_events()
        self.set_checkbox_states()  # tick in menu

        # Run startup dialog
        self.startup_dialog = StartupDialog()
        if self.startup_dialog.exec():
            pass
        else:
            sys.exit()
        # Segmentation only functionalities
        if LabelConfig().type == LabelingMode.OBJECT_DETECTION \
            and self.in_labeling:
            self.button_assign_label.setVisible(False)
            self.act_color_with_label.setVisible(False)

        if self.in_projection:
            self.button_complete_selection.setDisabled(True)
            # Init camera objects
            for idx, item in enumerate(self.image_manager_list):
                item.set_view(self)
                item.set_camera(idx)

        # Connect with controller
        self.controller.startup(self)

        # Start event cycle
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(20)  # period, in milliseconds
        self.timer.timeout.connect(self.controller.loop_gui)
        self.timer.start()   

    # Event connectors
    def connect_events(self) -> None:
        # POINTCLOUD CONTROL
        self.button_next_pcd.clicked.connect(lambda: self.controller.next_pcd(save=True))

        self.button_prev_pcd.clicked.connect(self.controller.prev_pcd)

        self.button_set_pcd.pressed.connect(lambda: self.ask_custom_index())

        self.act_change_class_color.triggered.connect(self.change_label_color)

        # open_2D_img
 
        self.act_set_pcd_folder.triggered.connect(self.change_pointcloud_folder)
        self.act_set_label_folder.triggered.connect(self.change_label_folder)
        self.actiongroup_default_class.triggered.connect(
            self.change_default_object_class
        )

        self.act_propagate_labels.toggled.connect(set_propagate_labels)
        self.act_z_rotation_only.toggled.connect(set_zrotation_only)
        self.act_color_with_label.toggled.connect(set_color_with_label)
        self.act_show_floor.toggled.connect(set_floor_visibility)
        self.act_show_orientation.toggled.connect(set_orientation_visibility)
        self.act_save_perspective.toggled.connect(set_keep_perspective)
        self.act_align_pcd.toggled.connect(self.controller.align_mode.change_activation)
        self.act_change_settings.triggered.connect(self.show_settings_dialog)
      
        self.button_save_label.clicked.connect(self.controller.save)

        if self.in_labeling: 
            
            self.button_bbox_up.pressed.connect(lambda: self.controller.bbox_controller.translate_along_z())

            self.button_bbox_down.pressed.connect(lambda: self.controller.bbox_controller.translate_along_z(down=True))

            self.button_bbox_left.pressed.connect(lambda: self.controller.bbox_controller.translate_along_x(left=True))

            self.button_bbox_right.pressed.connect(self.controller.bbox_controller.translate_along_x)

            self.button_bbox_forward.pressed.connect(lambda: self.controller.bbox_controller.translate_along_y(forward=True))

            self.button_bbox_backward.pressed.connect(lambda: self.controller.bbox_controller.translate_along_y())

            self.dial_bbox_z_rotation.valueChanged.connect(lambda x: self.controller.bbox_controller.rotate_around_z(x, absolute=True))

            self.button_bbox_decrease_dimension.clicked.connect(lambda: self.controller.bbox_controller.scale(decrease=True))

            self.button_bbox_increase_dimension.clicked.connect(lambda: self.controller.bbox_controller.scale())


            # LABELING CONTROL
            self.current_class_dropdown.currentTextChanged.connect(
                self.controller.bbox_controller.set_classname
            )

            self.button_deselect_label.clicked.connect(self.controller.bbox_controller.deselect_bbox)

            self.button_delete_label.clicked.connect(self.controller.bbox_controller.delete_current_bbox)

            self.label_list.currentRowChanged.connect(self.controller.bbox_controller.set_active_bbox)

            self.button_assign_label.clicked.connect(
                self.controller.bbox_controller.assign_point_label_in_active_box
            )

            # context menu
            self.act_delete_class.triggered.connect(self.controller.bbox_controller.delete_current_bbox)

            self.act_crop_pointcloud_inside.triggered.connect(
                self.controller.crop_pointcloud_inside_active_bbox
            )

            # LABEL CONTROL
            self.button_pick_bbox.clicked.connect(
                lambda: self.controller.drawing_mode.set_drawing_strategy(
                    PickingStrategy(self)
                )
            )
            self.button_span_bbox.clicked.connect(
                lambda: self.controller.drawing_mode.set_drawing_strategy(
                    SpanningStrategy(self)
                )
            )


            # BOUNDING BOX PARAMETER
            self.edit_pos_x.editingFinished.connect(
                lambda: self.update_bbox_parameter("pos_x")
            )
            self.edit_pos_y.editingFinished.connect(
                lambda: self.update_bbox_parameter("pos_y")
            )
            self.edit_pos_z.editingFinished.connect(
                lambda: self.update_bbox_parameter("pos_z")
            )

            self.edit_length.editingFinished.connect(
                lambda: self.update_bbox_parameter("length")
            )
            self.edit_width.editingFinished.connect(
                lambda: self.update_bbox_parameter("width")
            )
            self.edit_height.editingFinished.connect(
                lambda: self.update_bbox_parameter("height")
            )

            self.edit_rot_x.editingFinished.connect(
                lambda: self.update_bbox_parameter("rot_x")
            )
            self.edit_rot_y.editingFinished.connect(
                lambda: self.update_bbox_parameter("rot_y")
            )
            self.edit_rot_z.editingFinished.connect(
                lambda: self.update_bbox_parameter("rot_z")
            )

            self.act_delete_all_labels.triggered.connect(
                self.controller.bbox_controller.reset
            )
         
        if self.in_projection: 
            # CORRECTION CONTROL
            self.button_point_match.clicked.connect(
                lambda: self.controller.drawing_mode.set_drawing_strategy(
                    PointMatchCorrection(self)
                )
            )

            self.button_complete_selection.clicked.connect(
                lambda: self.controller.drawing_mode.finish()
            )
            
            
           
    def set_checkbox_states(self) -> None:
        self.act_propagate_labels.setChecked(
            config.getboolean("LABEL", "propagate_labels")
        )
        self.act_show_floor.setChecked(
            config.getboolean("USER_INTERFACE", "show_floor")
        )
        self.act_show_orientation.setChecked(
            config.getboolean("USER_INTERFACE", "show_orientation")
        )
        self.act_z_rotation_only.setChecked(
            config.getboolean("USER_INTERFACE", "z_rotation_only")
        )
        self.act_color_with_label.setChecked(
            config.getboolean("POINTCLOUD", "color_with_label")
        )

    # Collect, filter and forward events to viewer
    def eventFilter(self, event_object, event) -> bool:
        if self.in_labeling:
            self.bbox_previous = copy.deepcopy(self.controller.bbox_controller.get_active_bbox())

        # Keyboard Events
        if (event.type() == QEvent.KeyPress) and event_object in [
            self,
            self.label_list if self.in_labeling else self,
            self.point_list if self.in_projection else self,
        ]:
            if self.in_labeling:
                self.controller.key_press_event(event)
                self.update_bbox_stats(self.controller.bbox_controller.get_active_bbox())
            if self.in_projection:
                pass
            return True  # TODO: Recheck pyqt behaviour

        elif event.type() == QEvent.KeyRelease:
            self.controller.key_release_event(event)

        # Mouse Events
        elif (event.type() == QEvent.MouseMove):
            if (event_object == self.gl_widget): # MOUSE MOVE
                self.controller.mouse_move_event(event)
                if self.in_labeling:
                    self.update_bbox_stats(self.controller.bbox_controller.get_active_bbox())
            elif (event_object in self.image_label_list):
                self.draw_image_cursor((event.x(), event.y()), self.image_label_list.index(event_object))
                
        elif (event.type() == QEvent.Wheel) and (event_object == self.gl_widget): # MOUSE SCROLL
            self.controller.mouse_scroll_event(event)
            if self.in_labeling:
                self.update_bbox_stats(self.controller.bbox_controller.get_active_bbox())

        elif event.type() == QEvent.MouseButtonDblClick and ( # MOUSE DOUBLE CLICK
            event_object == self.gl_widget
        ):
            self.controller.mouse_double_clicked(event)
            return True
        
        elif (event.type() == QEvent.MouseButtonPress) and ( # MOUSE SINGLE CLICK - NOT ON IMAGE
            event_object == self.gl_widget
        ):
            self.controller.mouse_clicked(event)
            if self.in_labeling:
                self.update_bbox_stats(self.controller.bbox_controller.get_active_bbox())

        elif (event.type() == QEvent.MouseButtonPress) and ( # MOUSE SINGLE CLICK - ON IMAGE
            event_object in self.image_label_list
        ):
            self.controller.image_clicked(event, event_object)

        elif (event.type() == QEvent.MouseButtonPress) and (
            self.in_labeling
        ) and ( # ???
            event_object != self.current_class_dropdown
        ):
            self.current_class_dropdown.clearFocus()
            self.update_bbox_stats(self.controller.bbox_controller.get_active_bbox())
        return False

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        logging.info("Closing window after saving ...")
        self.controller.save()
        self.timer.stop()
        a0.accept()

    def show_settings_dialog(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()

    def draw_bboxes(self, width, height, P_matrix, pixelmap, cam_number : int, margin): # TODO type
        pass
#        all_bboxes = self.controller.bbox_controller.bboxes
#        active_bbox_idx = self.controller.bbox_controller.active_bbox_id
#
#        # Draw all bboxes in red
#        for idx, bbox in enumerate(all_bboxes):
#
#            corners = np.array([[-1,-1,-1],
#                [-1,1,-1],
#                [-1,1,1],
#                [-1,-1,1],
#                [1,-1,-1],
#                [1,1,-1],
#                [1,1,1],
#                [1,-1,1]]).astype(np.float64)
#            
#            thickness = 2
#            color = QtCore.Qt.blue
#            
#            # print(f"{idx} : ({bbox.center})")
#            
#            if self.controller.bbox_controller.has_active_bbox and \
#                idx == self.controller.bbox_controller.active_bbox_id:
#                    thickness = 3
#                    color = QtCore.Qt.green
#            
#            corners[:,0] *= bbox.length/2.0
#            corners[:,1] *= bbox.width/2.0
#            corners[:,2] *= bbox.height/2.0
#            angle = bbox.z_rotation/180.0*np.pi
#            Rz = np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
#            corners = np.transpose(np.matmul(Rz, np.transpose(corners, (1,0))), (1,0))   
#            corners[:,0] += bbox.center[0]
#            corners[:,1] += bbox.center[1]
#            corners[:,2] += bbox.center[2]
#            pts_homo = np.ones((corners.shape[0], 4))
#            pts_homo[:,0:3] = corners
#            P = P_matrix[cam_number]
#            pts_img = np.matmul(P, pts_homo.transpose()).transpose()
#            if np.any(pts_img[:, 2] < 0):
#                continue
#            pts_img[:,0] /= pts_img[:,2]
#            pts_img[:,1] /= pts_img[:,2]   
#            x = pts_img[:,0]
#            y = pts_img[:,1]
#            x_mean = np.mean(x)
#            y_mean = np.mean(y)
#
#            if not (x_mean<-margin or x_mean>width+margin or y_mean<-margin or y_mean>height+margin):
#                painter = QPainter(pixelmap)
#                painter.setPen(QPen(color, thickness, QtCore.Qt.DashLine))
#                for m in range(4):
#                    n = (m+1)%4
#                    painter.drawLine(x[m],y[m],x[n],y[n])
#                    painter.drawLine(x[m+4],y[m+4],x[n+4],y[n+4])
#                    painter.drawLine(x[m],y[m],x[m+4],y[m+4]) 
#                painter.end()

    def draw_points(self, cam_idx, pixmap):
        pass
#        all_pts = self.controller.point_controller.points
#        active_point_idx = self.controller.point_controller.active_point_id
#
#        thickness = 3
#        
#        for idx, point in enumerate(all_pts):
#            p3d, p2d, camera = point
#            
#            if camera != cam_idx:
#                print(f"skip, currently on {cam_idx} and the point is for {camera}")
#                continue
#            
#             
#            color = QtCore.Qt.green if idx == active_point_idx else QtCore.Qt.blue
#            
#            painter = QPainter(pixelmap)
#            painter.setPen(QPen(color, thickness, QtCore.Qt.DashDotDotLine))
#
#            x, y = p2d
#            painter.drawPoint(x, y)
#            painter.end()
#            
            

    def init_2d_image(self):
        """Searches for a 2D image with the point cloud name and displays it in a new window."""
        for lbl in self.image_manager_list:
            lbl.set_new_image_by_pcd()
            lbl.render()
#
#        self.current_pixmaps = []
#
#        # Look for image files with the name of the point cloud
#        if not len(self.controller.pcd_manager.pcds):
#            return
#            
#        pcd_name = self.controller.pcd_manager.pcd_path.stem
#        postfix_length = len(self.controller.pcd_manager.pcd_postfix)-4
#        file_name = pcd_name[:-postfix_length]
#
#        for i in range(len(self.cam_list)):
#            image_path = str(self.controller.pcd_manager.pcd_folder.absolute())+'/'+file_name+self.cam_list[i]
#            if not os.path.exists(image_path):
#                print('No Enough Image! Skip this.')
#                return
#            
##        P_matrix = config.getlist("FILE", "pmatrix_list")
##        P_matrix = np.array(P_matrix).reshape(-1,3,4)
##        margin = 100
#        
#        for i in range(len(self.cam_list)):
#            image_path = str(self.controller.pcd_manager.pcd_folder.absolute())+'/'+file_name+self.cam_list[i]
#            image = QtGui.QImage(QtGui.QImageReader(str(image_path)).read())
#            pixelmap = QPixmap.fromImage(image)
#            pixelmap = pixelmap.scaledToWidth(1024)
#                
#            width, height = 1024, 768
#
##            if self.in_labeling:            
##               self.draw_bboxes(width, height, P_matrix, pixelmap, i, margin) 
##            elif self.in_projection:
##                self.draw_points(i, pixelmap)
##            
#            # Scale down the image size
#            pixelmap = pixelmap.transformed(QtGui.QTransform().scale(0.50, 0.50))
#
#            self.current_pixmaps.append(pixelmap)
#            
#            self.image_label_list[i].setPixmap(pixelmap)
#            self.image_label_list[i].update()                     
#            self.image_label_list[i].show()
    
    def show_2d_image(self):
        pass
#        for label in self.image_label_list:
#            label.update()
#            label.show()
            
    def draw_image_cursor(self, point : Point2D, camera : Union[Camera, int],
        scale : int = 1) -> None:
        pass
#        pixmap = self.current_pixmaps[camera]
#        
#        color = QtCore.Qt.gray 
#        thickness = 1
#        
#        painter = QPainter(pixmap)
#        painter.setPen(QPen(color, thickness, QtCore.Qt.DashLine))
#
#        x, y = point
#
#        painter.drawLine(x-5*scale, y, x+5*scale, y)
#        painter.drawLine(x, y-5*scale, x, y+5*scale)
#        painter.end()
#        
#        self.image_label_list[camera].setPixmap(pixmap)
#        self.image_label_list[camera].update()
#        self.image_label_list[camera].show()
#        
#
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

    def update_bbox_stats(self, bbox) -> None:
        viewing_precision = config.getint("USER_INTERFACE", "viewing_precision")
        if bbox and not self.line_edited_activated():
            self.edit_pos_x.setText(str(round(bbox.get_center()[0], viewing_precision)))
            self.edit_pos_y.setText(str(round(bbox.get_center()[1], viewing_precision)))
            self.edit_pos_z.setText(str(round(bbox.get_center()[2], viewing_precision)))

            self.edit_length.setText(
                str(round(bbox.get_dimensions()[0], viewing_precision))
            )
            self.edit_width.setText(
                str(round(bbox.get_dimensions()[1], viewing_precision))
            )
            self.edit_height.setText(
                str(round(bbox.get_dimensions()[2], viewing_precision))
            )

            self.edit_rot_x.setText(str(round(bbox.get_x_rotation(), 1)))
            self.edit_rot_y.setText(str(round(bbox.get_y_rotation(), 1)))
            self.edit_rot_z.setText(str(round(bbox.get_z_rotation(), 1)))

            self.label_volume.setText(str(round(bbox.get_volume(), viewing_precision)))
#        if self.bbox_previous is not None and bbox:
            # change check
#            if (self.bbox_previous.center != bbox.center 
#                or self.bbox_previous.height != bbox.height
#                or self.bbox_previous.width != bbox.width
#                or self.bbox_previous.length != bbox.length
#                or self.bbox_previous.z_rotation != bbox.z_rotation):


    def update_bbox_parameter(self, parameter: str) -> None:
        str_value = None
        self.setFocus()  # Changes the focus from QLineEdit to the window

        if parameter == "pos_x":
            str_value = self.edit_pos_x.text()
        if parameter == "pos_y":
            str_value = self.edit_pos_y.text()
        if parameter == "pos_z":
            str_value = self.edit_pos_z.text()
        if str_value and string_is_float(str_value):
            self.controller.bbox_controller.update_position(parameter, float(str_value))
            return

        if parameter == "length":
            str_value = self.edit_length.text()
        if parameter == "width":
            str_value = self.edit_width.text()
        if parameter == "height":
            str_value = self.edit_height.text()
        if str_value and string_is_float(str_value, recect_negative=True):
            self.controller.bbox_controller.update_dimension(
                parameter, float(str_value)
            )
            return

        if parameter == "rot_x":
            str_value = self.edit_rot_x.text()
        if parameter == "rot_y":
            str_value = self.edit_rot_y.text()
        if parameter == "rot_z":
            str_value = self.edit_rot_z.text()
        if str_value and string_is_float(str_value):
            self.controller.bbox_controller.update_rotation(parameter, float(str_value))
            return

    # Enables, disables the draw mode
    def activate_draw_modes(self, state: bool) -> None:
        if self.in_labeling:
            self.button_pick_bbox.setEnabled(state)
            self.button_span_bbox.setEnabled(state)
        elif self.in_projection:
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

    def change_label_folder(self) -> None:
        path_to_folder = Path(
            QFileDialog.getExistingDirectory(
                self,
                "Change Label Folder",
                directory=config.get("FILE", "label_folder"),
            )
        )
        if not path_to_folder.is_dir():
            logging.warning("Please specify a valid folder path.")
        else:
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
        bbox = self.controller.bbox_controller.get_active_bbox()
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
