import os
import logging
import json
import yaml
from typing import Optional
import shutil
import numpy as np
from PyQt5 import QtGui
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import Qt as Keys

from functools import wraps

from ..definitions import BBOX_SIDES, Colors, Context, LabelingMode, Camera, Point2D
from ..io.labels.config import LabelConfig
from ..utils import oglhelper
from ..view.gui import GUI
from ..labeling_strategies import PickingStrategy
from .alignmode import AlignMode
from .bbox_controller import BoundingBoxController
from .config_manager import config
from .drawing_manager import LabelDrawingManager
from .drawing_manager import ProjectionDrawingManager
from .base_drawing_manager import BaseDrawingManager         
from .pcd_manager import PointCloudManager
from .manual_calibration_controller import ProjectionCorrectionController
from .base_element_controller import BaseElementController
from ..utils.decorators import in_labeling_only_decorator, in_projection_only_decorator


class Controller:
    MOVEMENT_THRESHOLD = 0.05
    LABELING = LabelConfig().type == LabelingMode.OBJECT_DETECTION
    PROJECTION = LabelConfig().type == LabelingMode.PROJECTION_CORRECTION

    def __init__(self) -> None:
        """Initializes all controllers and managers."""
        self.view: "GUI"
        self.pcd_manager = PointCloudManager()

        usage_mode = config.get("FILE", "usage_mode")
      
        self.element_controller : Optional[BaseElementController] = None 
        self.drawing_mode : Optional[BaseDrawingManager] = None

        if self.LABELING:
            self.element_controller = BoundingBoxController()
            self.drawing_mode = LabelDrawingManager(self.element_controller)
        elif self.PROJECTION:
            self.element_controller = ProjectionCorrectionController()
            self.drawing_mode = ProjectionDrawingManager(self.element_controller, self.pcd_manager)

        # Drawing states
        self.align_mode = AlignMode(self.pcd_manager)

        # Control states
        self.curr_cursor_pos: Optional[QPoint] = None  # updated by mouse movement
        self.last_cursor_pos: Optional[QPoint] = None  # updated by mouse click
        self.ctrl_pressed = False
        self.shift_pressed = False
        self.scroll_mode = False  # to enable the side-pulling

        # Correction states
        self.side_mode = False
        self.selected_side: Optional[str] = None

    def startup(self, view: "GUI") -> None:
        """Sets the view in all controllers and dependent modules; Loads labels from file."""
        self.view = view
        
        assert self.element_controller is not None, "Element controller never got set"
        
        self.element_controller.set_view(self.view)
        self.element_controller.set_pcd_manager(self.pcd_manager)
        
        self.pcd_manager.set_view(self.view)
        self.drawing_mode.set_view(self.view)
        self.align_mode.set_view(self.view)
        
        self.view.gl_widget.set_element_controller(self.element_controller) 

        # Read labels from folders
        self.pcd_manager.read_pointcloud_folder()
        self.next_pcd(save=False)

    def loop_gui(self) -> None:
        """Function collection called during each event loop iteration."""
        self.set_crosshair()
        self.set_selected_side()
        self.view.gl_widget.updateGL()

    # POINT CLOUD METHODS
    def next_pcd(self, save: bool = True) -> None:
        if save:
            self.save()

        if self.pcd_manager.pcds_left():
            self.pcd_manager.get_next_pcd()
            self.reset()
            self.element_controller.refresh_element_list() # Handle for label propagation
            self.view.refresh_images()

        else:
            self.view.update_progress(len(self.pcd_manager.pcds))
            self.view.button_next_pcd.setEnabled(False)

    def prev_pcd(self) -> None:
        self.save()
        if self.pcd_manager.current_id > 0:
            self.pcd_manager.get_prev_pcd()
            self.reset()
            self.element_controller.refresh_element_list()
            self.view.refresh_images()
    
    def custom_pcd(self, custom: int) -> None:
        self.save()
        self.pcd_manager.get_custom_pcd(custom)
        self.reset()
        self.element_controller.refresh_element_list()
        self.view.refresh_images()
        
    # CONTROL METHODS
    def save(self) -> None: # TODO Handle for semantic mode
        """Saves all bounding boxes and optionally segmentation labels in the label file."""
        self.pcd_manager.save_labels_into_file(self.element_controller.elements)

    def reset(self) -> None:
        """Resets the controllers and bounding boxes from the current screen."""
        self.element_controller.reset()
        self.drawing_mode.reset()
        self.align_mode.reset()

    # CORRECTION METHODS
    def set_crosshair(self) -> None:
        """Sets the crosshair position in the glWidget to the current cursor position."""
        if self.curr_cursor_pos:
            self.view.gl_widget.crosshair_col = Colors.GREEN.value
            self.view.gl_widget.crosshair_pos = (
                self.curr_cursor_pos.x(),
                self.curr_cursor_pos.y(),
            )

    @in_labeling_only_decorator
    def set_selected_side(self) -> None:
        """Sets the currently hovered bounding box side in the glWidget."""
        if (
            (not self.side_mode)
            and self.curr_cursor_pos
            and self.bbox_controller.has_active_bbox()
            and (not self.scroll_mode)
        ):
            _, self.selected_side = oglhelper.get_intersected_sides(
                self.curr_cursor_pos.x(),
                self.curr_cursor_pos.y(),
                self.bbox_controller.get_active_bbox(),  # type: ignore
                self.view.gl_widget.modelview,
                self.view.gl_widget.projection,
            )
        if (
            self.selected_side
            and (not self.ctrl_pressed)
            and self.bbox_controller.has_active_bbox()
        ):
            self.view.gl_widget.crosshair_col = Colors.RED.value
            side_vertices = self.bbox_controller.get_active_bbox().get_vertices()  # type: ignore
            self.view.gl_widget.selected_side_vertices = side_vertices[
                BBOX_SIDES[self.selected_side]
            ]
            self.view.status_manager.set_message(
                "Scroll to change the bounding box dimension.",
                context=Context.SIDE_HOVERED,
            )
        else:
            self.view.gl_widget.selected_side_vertices = np.array([])
            self.view.status_manager.clear_message(Context.SIDE_HOVERED)
    
    def image_clicked(self, pos : Point2D, cam : Camera) -> None:
        logging.debug(f"controller registered camera '{cam}' clicked at ({pos[0]}, {pos[1]})")
        self.drawing_mode.register_point_2d(pos, cam) 

    # TODO
    def mouse_clicked_labeling(self, a0 : QtGui.QMouseEvent) -> None:
        """Triggers actions when the user clicks the mouse."""
        self.last_cursor_pos = a0.pos()
        if (
            self.drawing_mode.is_active()
            and (a0.buttons() & Keys.LeftButton)
            and (not self.ctrl_pressed)
        ):
            self.drawing_mode.register_point(a0.x(), a0.y(), correction=True)

        elif self.align_mode.is_active and (not self.ctrl_pressed):
            self.align_mode.register_point(
                self.view.gl_widget.get_world_coords(a0.x(), a0.y(), correction=False)
            )

        elif self.selected_side:
            self.side_mode = True
    
    def mouse_clicked_projection(self, a0 : QtGui.QMouseEvent) -> None:
        """Triggers actions when the user clicks the mouse in projection usage mode"""
        self.last_cursor_pos = a0.pos()
        if (
            self.drawing_mode.is_active()
            and (a0.buttons() & Keys.LeftButton)
            and (not self.ctrl_pressed)
        ):
            self.drawing_mode.register_point_3d(a0.x(), a0.y(), correction=True)
            
        elif self.align_mode.is_active and (not self.ctrl_pressed):
            self.align_mode.register_point(
                self.view.gl_widget.get_world_coords(a0.x(), a0.y(), correction=False)
            )
    
    def mouse_clicked(self, a0 : QtGui.QMouseEvent) -> None:
        if self.LABELING:
            self.mouse_clicked_labeling(a0)
        elif self.PROJECTION:
            self.mouse_clicked_projection(a0)

    @in_labeling_only_decorator
    def mouse_double_clicked(self, a0: QtGui.QMouseEvent) -> None:
        """Triggers actions when the user double clicks the mouse."""
        self.element_controller.select_bbox_by_ray(a0.x(), a0.y())

    def mouse_move_event(self, a0: QtGui.QMouseEvent) -> None:
        """Triggers actions when the user moves the mouse"""
        self.curr_cursor_pos = a0.pos()  # Updates the current mouse cursor position
        self.update_cursor_display()

        # Methods that use absolute cursor position
        if self.drawing_mode.is_active() and (not self.ctrl_pressed):
            if self.LABELING:
                self.drawing_mode.register_point(
                    a0.x(), a0.y(), correction=True, is_temporary=True
                )
            elif self.PROJECTION:
                self.drawing_mode.register_point_3d(
                a0.x(), a0.y(), correction=True, is_temporary=True
            )

        elif self.align_mode.is_active and (not self.ctrl_pressed):
            self.align_mode.register_tmp_point(
                self.view.gl_widget.get_world_coords(a0.x(), a0.y(), correction=False)
            )

        if self.last_cursor_pos:
            dx = (
                self.last_cursor_pos.x() - a0.x()
            ) / 5  # Calculate relative movement from last click position
            dy = (self.last_cursor_pos.y() - a0.y()) / 5

            if (
                self.ctrl_pressed
                and (not self.drawing_mode.is_active())
                and (not self.align_mode.is_active)
                and (self.LABELING)
            ):
                if a0.buttons() & Keys.LeftButton:  # bbox rotation
                    self.bbox_controller.rotate_with_mouse(-dx, -dy)
                elif a0.buttons() & Keys.RightButton:  # bbox translation
                    new_center = self.view.gl_widget.get_world_coords(
                        a0.x(), a0.y(), correction=True
                    )
                    self.bbox_controller.set_center(*new_center)  # absolute positioning
            else:
                if a0.buttons() & Keys.LeftButton:  # pcd rotation
                    self.pcd_manager.rotate_around_x(dy)
                    self.pcd_manager.rotate_around_z(dx)
                elif a0.buttons() & Keys.RightButton:  # pcd translation
                    self.pcd_manager.translate_along_x(dx)
                    self.pcd_manager.translate_along_y(dy)

            # Reset scroll locks of "side scrolling" for significant cursor movements
            if dx > Controller.MOVEMENT_THRESHOLD or dy > Controller.MOVEMENT_THRESHOLD:
                if self.side_mode:
                    self.side_mode = False
                else:
                    self.scroll_mode = False
        self.last_cursor_pos = a0.pos()
    
    def mouse_scroll_event(self, a0: QtGui.QWheelEvent) -> None:
        """Triggers actions when the user scrolls the mouse wheel."""
        if self.selected_side:
            self.side_mode = True

        if (
            self.drawing_mode.is_active()
            and (not self.ctrl_pressed)
            and (not self.shift_pressed)
            and self.drawing_mode.drawing_strategy is not None
            and (not self.drawing_mode.drawing_strategy.IGNORE_SCROLL)
        ):
            self.drawing_mode.drawing_strategy.register_scrolling(a0.angleDelta().y())
        elif (
            self.drawing_mode.is_active()
            and (not self.ctrl_pressed)
            and (self.shift_pressed)
            and self.drawing_mode.drawing_strategy is not None
            and (not self.drawing_mode.drawing_strategy.IGNORE_SCROLL)
            and (self.LABELING)
        ):
            self.drawing_mode.drawing_strategy.register_scale(a0.angleDelta().y())
        elif self.side_mode and self.element_controller.has_active_element() and self.LABELING:
            self.element_controller.get_active_element().change_side(  # type: ignore
                self.selected_side, -a0.angleDelta().y() / 4000  # type: ignore
            )  # ToDo implement method
        else:
            self.pcd_manager.zoom_into(a0.angleDelta().y())
            self.scroll_mode = True

    def key_press_event(self, a0: QtGui.QKeyEvent) -> None:
        """Triggers actions when the user presses a key."""
        # Reset position to intial value
        if a0.key() == Keys.Key_Control:
            self.ctrl_pressed = True
            self.view.status_manager.set_message(
                "Hold right mouse button to translate or left mouse button to rotate "
                "the bounding box.",
                context=Context.CONTROL_PRESSED,
            )
        elif a0.key() == Keys.Key_Shift:
            self.shift_pressed = True
        # Reset point cloud pose to intial rotation and translation
        elif a0.key() in [Keys.Key_P, Keys.Key_Home]:
            self.pcd_manager.reset_transformations()
            logging.info("Reseted position to default.")

        elif a0.key() == Keys.Key_Delete:  # Delete active element
            self.element_controller.delete_current_element()

        # Save labels to file
        elif a0.key() == Keys.Key_S and self.ctrl_pressed:
            self.save()

        elif a0.key() == Keys.Key_Escape:
            if self.drawing_mode.is_active():
                self.drawing_mode.reset()
                logging.info("Resetted drawn points!")
            elif self.align_mode.is_active:
                self.align_mode.reset()
                logging.info("Resetted selected points!")

        # BBOX MANIPULATION
        elif a0.key() == Keys.Key_Z and self.LABELING:
            # z rotate counterclockwise
            self.element_controller.rotate_around_z()
        elif a0.key() == Keys.Key_X and self.LABELING:
            # z rotate clockwise
            self.element_controller.rotate_around_z(clockwise=True)
        elif a0.key() == Keys.Key_C and self.LABELING:
            # y rotate counterclockwise
            self.element_controller.rotate_around_y()
        elif a0.key() == Keys.Key_V and self.LABELING:
            # y rotate clockwise
            self.element_controller.rotate_around_y(clockwise=True)
        elif a0.key() == Keys.Key_B and self.LABELING:
            # x rotate counterclockwise
            self.element_controller.rotate_around_x()
        elif a0.key() == Keys.Key_N and self.LABELING:
            # x rotate clockwise
            self.element_controller.rotate_around_x(clockwise=True)
        #### DUAL EVENTS BASED ON PICKING
        ### IS NOT DRAWING
        elif a0.key() == Keys.Key_W and not self.drawing_mode.is_active():
            # move backward
            self.element_controller.translate_along_y(boost=self.shift_pressed)

        elif a0.key() == Keys.Key_S and not self.drawing_mode.is_active():
            # move forward
            self.element_controller.translate_along_y(forward=True, boost=self.shift_pressed)

        elif a0.key() == Keys.Key_A and not self.drawing_mode.is_active():
            # move left
            self.element_controller.translate_along_x(left=True, boost=self.shift_pressed)

        elif a0.key() == Keys.Key_D and not self.drawing_mode.is_active():
            # move right
            self.element_controller.translate_along_x(boost=self.shift_pressed)

        elif a0.key() == Keys.Key_Q and not self.drawing_mode.is_active() and self.LABELING:
            # move up
            self.element_controller.translate_along_z(boost=self.shift_pressed)

        elif a0.key() == Keys.Key_E and not self.drawing_mode.is_active() and self.LABELING:
            # move down
            self.element_controller.translate_along_z(down=True, boost=self.shift_pressed)

        ### IS DRAWING
        elif a0.key() == Keys.Key_W and self.drawing_mode.is_active():
            # move backward
            perspective = self.pcd_manager.get_perspective()
            self.drawing_mode.drawing_strategy.register_trans_y(perspective, boost=self.shift_pressed)

        elif a0.key() == Keys.Key_S and self.drawing_mode.is_active():
            # move forward
            perspective = self.pcd_manager.get_perspective()
            self.drawing_mode.drawing_strategy.register_trans_y(perspective, forward=True, boost=self.shift_pressed)

        elif a0.key() == Keys.Key_A and self.drawing_mode.is_active():
            # move left
            perspective = self.pcd_manager.get_perspective()
            self.drawing_mode.drawing_strategy.register_trans_x(perspective, left=True, boost=self.shift_pressed)

        elif a0.key() == Keys.Key_D and self.drawing_mode.is_active():
            # move right
            perspective = self.pcd_manager.get_perspective()
            self.drawing_mode.drawing_strategy.register_trans_x(perspective, boost=self.shift_pressed)

        elif a0.key() == Keys.Key_Q and self.drawing_mode.is_active():
            # move up
            perspective = self.pcd_manager.get_perspective()
            self.drawing_mode.drawing_strategy.register_trans_z(boost=self.shift_pressed)

        elif a0.key() == Keys.Key_E and self.drawing_mode.is_active():
            # move down
            perspective = self.pcd_manager.get_perspective()
            self.drawing_mode.drawing_strategy.register_trans_z(down=True, boost=self.shift_pressed)

        elif a0.key() == Keys.Key_Space and self.drawing_mode.is_active():
            self.drawing_mode.drawing_strategy.reset()

        #### DUAL EVENTS BASED ON PICKING
        elif a0.key() == Keys.Key_Alt:
            # Unset focus
            self.pcd_manager.stop_focus()
        elif a0.key() in [Keys.Key_L, Keys.Key_Super_L, Keys.Key_Super_R]:
            # lock on to current bbox
            if self.element_controller.has_active_element():
                self.pcd_manager.move_focus(self.element_controller.focus_element(), force=True)
            # self.pcd_manager.reset_transformations()
        elif a0.key() in [Keys.Key_R, Keys.Key_Left]:
            # load previous sample
            self.prev_pcd()
        elif a0.key() in [Keys.Key_F, Keys.Key_Right]:
            # load next sample
            self.next_pcd()
        elif a0.key() in [Keys.Key_T, Keys.Key_Up] and self.LABELING:
            # select previous bbox
            self.element_controller.select_relative_element(-1)
        elif a0.key() in [Keys.Key_G, Keys.Key_Down] and self.LABELING:
            # select previous bbox
            self.element_controller.select_relative_element(1)
        elif a0.key() in [Keys.Key_Y, Keys.Key_Comma]:
            # change bbox class to previous available class
            self.select_relative_class(-1)
        elif a0.key() in [Keys.Key_H, Keys.Key_Period]:
            # change bbox class to next available class
            self.select_relative_class(1)
        elif a0.key() in list(range(49, 58)) and self.LABELING:
            # select bboxes with 1-9 digit keys
            self.bbox_controller.set_active_bbox(int(a0.key()) - 49)

    def update_cursor_display(self) -> None:
        x, y, z = self.view.gl_widget.get_world_coords(self.curr_cursor_pos.x(), self.curr_cursor_pos.y())
        self.view.row4_col1_label.setText(str(round(x, ndigits=2)))
        self.view.row4_col2_label.setText(str(round(y, ndigits=2)))
        self.view.row4_col3_label.setText(str(round(z, ndigits=2)))

    @in_labeling_only_decorator
    def select_relative_class(self, step: int):
        if step == 0:
            return
        curr_class = self.bbox_controller.get_active_bbox().get_classname()  # type: ignore
        new_class = LabelConfig().get_relative_class(curr_class, step)
        self.bbox_controller.get_active_bbox().set_classname(new_class)  # type: ignore
        self.bbox_controller.update_all()  # updates UI in SelectBox

    def key_release_event(self, a0: QtGui.QKeyEvent) -> None:
        """Triggers actions when the user releases a key."""
        if a0.key() == Keys.Key_Control:
            self.ctrl_pressed = False
            self.view.status_manager.clear_message(Context.CONTROL_PRESSED)
        elif a0.key() == Keys.Key_Shift:
            self.shift_pressed = False

    def crop_pointcloud_inside_active_bbox(self) -> None:
        bbox = self.element_controller.get_active_element()
        assert bbox is not None
        assert self.pcd_manager.pointcloud is not None
        points_inside = bbox.is_inside(self.pcd_manager.pointcloud.points)
        pointcloud = self.pcd_manager.pointcloud.get_filtered_pointcloud(points_inside)
        if pointcloud is None:
            logging.warning("No points found inside the box. Ignored.")
            return
        self.view.save_point_cloud_as(pointcloud)
