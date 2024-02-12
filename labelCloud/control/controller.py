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

from ..definitions import BBOX_SIDES, Colors, Context, LabelingMode, Camera
from ..io.labels.config import LabelConfig
from ..utils import oglhelper
from ..view.gui import GUI
from ..labeling_strategies import PickingStrategy
from ..image_management.image_manager import SingleImageManager
from .alignmode import AlignMode
from .bbox_controller import BoundingBoxController
from .config_manager import config
from .drawing_manager import LabelDrawingManager
from .drawing_manager import ProjectionDrawingManager
from .pcd_manager import PointCloudManager
from .projection_controller import ProjectionCorrectionController
from ..utils.decorators import in_labeling_only_decorator, in_projection_only_decorator


class Controller:
    MOVEMENT_THRESHOLD = 0.05

    def __init__(self) -> None:
        """Initializes all controllers and managers."""
        self.view: "GUI"
        self.pcd_manager = PointCloudManager()

        usage_mode = config.get("FILE", "usage_mode")

        usage_mode = usage_mode.replace("\"", "")

        self.in_labeling = (usage_mode == "label")
        self.in_projection = (usage_mode == "projection")    
        
        if self.in_labeling:
            self.bbox_controller = BoundingBoxController()
            self.drawing_mode = LabelDrawingManager(self.bbox_controller)
        elif self.in_projection:
            self.point_controller = ProjectionCorrectionController()
            self.drawing_mode = ProjectionDrawingManager(self.point_controller, self.pcd_manager)

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
        
        if self.in_labeling:
            self.bbox_controller.set_view(self.view)
            self.bbox_controller.pcd_manager = self.pcd_manager
        elif self.in_projection:
            self.point_controller.set_view(self.view)
            
        
        self.pcd_manager.set_view(self.view)
        self.drawing_mode.set_view(self.view)
        self.align_mode.set_view(self.view)
        
        if self.in_labeling:
            self.view.gl_widget.set_bbox_controller(self.bbox_controller)

        # Read labels from folders
        self.pcd_manager.read_pointcloud_folder()
        self.next_pcd(save=False)

        self.view.init_2d_image()

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
            if self.in_labeling:
                previous_bboxes = self.bbox_controller.bboxes
                self.pcd_manager.get_next_pcd()
                self.reset()
                self.bbox_controller.set_bboxes(self.pcd_manager.get_labels_from_file())   

                if not self.bbox_controller.bboxes and config.getboolean(
                    "LABEL", "propagate_labels"
                ):
                    self.bbox_controller.set_bboxes(previous_bboxes)
                self.bbox_controller.set_active_bbox(0)
            elif self.in_projection:
                previous_points = self.point_controller.points
                self.pcd_manager.get_next_pcd()
                self.reset()
                self.point_controller.set_points([]) # TODO
        else:
            self.view.update_progress(len(self.pcd_manager.pcds))
            self.view.button_next_pcd.setEnabled(False)

    def prev_pcd(self) -> None:
        self.save()
        if self.pcd_manager.current_id > 0:
            self.pcd_manager.get_prev_pcd()
            self.reset()
            if self.in_labeling:
                self.bbox_controller.set_bboxes(self.pcd_manager.get_labels_from_file())
                self.bbox_controller.set_active_bbox(0)
            elif self.in_projection:
                self.point_controller.set_points([]) # TODO
                self.point_controller.set_active_point(0)

    def custom_pcd(self, custom: int) -> None:
        self.save()
        self.pcd_manager.get_custom_pcd(custom)
        self.reset()
        if self.in_labeling:
            self.bbox_controller.set_bboxes(self.pcd_manager.get_labels_from_file())
        elif self.in_projection:
            self.point_controller.set_points([]) # TODO

    # CONTROL METHODS
    def save(self) -> None: # TODO Add save behavior for projection mode
        """Saves all bounding boxes and optionally segmentation labels in the label file."""
        self.pcd_manager.save_labels_into_file(self.bbox_controller.bboxes)

        if LabelConfig().type == LabelingMode.SEMANTIC_SEGMENTATION:
            assert self.pcd_manager.pointcloud is not None
            self.pcd_manager.pointcloud.save_segmentation_labels()

    def reset(self) -> None:
        """Resets the controllers and bounding boxes from the current screen."""
        if self.in_labeling:
            self.bbox_controller.reset()
        elif self.in_projection:
            self.point_controller.reset()
        
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
    
    def image_clicked(self, a0 : QtGui.QMouseEvent, which_image) -> None:
        camera : Camera = self.view.image_label_list.index(which_image)
        manager : SingleImageManager = self.view.image_manager_list[camera]
        
        #self.drawing_mode.register_point_2d(a0.x(), a0.y(), camera)
        manager.register_click()

    def mouse_clicked(self, a0 : QtGui.QMouseEvent) -> None:
        if self.in_labeling:
            self.mouse_clicked_labeling(a0)
        elif self.in_projection:
            self.mouse_clicked_projection(a0)
        

    @in_labeling_only_decorator
    def mouse_double_clicked(self, a0: QtGui.QMouseEvent) -> None:
        """Triggers actions when the user double clicks the mouse."""
        self.bbox_controller.select_bbox_by_ray(a0.x(), a0.y())

    def mouse_move_event(self, a0: QtGui.QMouseEvent) -> None:
        """Triggers actions when the user moves the mouse"""
        self.curr_cursor_pos = a0.pos()  # Updates the current mouse cursor position

        if self.in_projection:
            if self.drawing_mode.is_active() \
            and self.drawing_mode.drawing_strategy.can_finish():
                self.view.button_complete_selection.setDisabled(False) 
            else:
                self.view.button_complete_selection.setDisabled(True)

        # Methods that use absolute cursor position
        if self.drawing_mode.is_active() and (not self.ctrl_pressed):
            if self.in_labeling:
                self.drawing_mode.register_point(
                    a0.x(), a0.y(), correction=True, is_temporary=True
                )
            elif self.in_projection:
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
                and (self.in_labeling)
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
        ):
            self.drawing_mode.drawing_strategy.register_scale(a0.angleDelta().y())
        elif self.side_mode and self.bbox_controller.has_active_bbox():
            self.bbox_controller.get_active_bbox().change_side(  # type: ignore
                self.selected_side, -a0.angleDelta().y() / 4000  # type: ignore
            )  # ToDo implement method
        else:
            self.pcd_manager.zoom_into(a0.angleDelta().y())
            self.scroll_mode = True

    def key_press_event(self, a0: QtGui.QKeyEvent) -> None:
        """Triggers actions when the user presses a key."""

        # print(a0.key())

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

        elif a0.key() == Keys.Key_Delete:  # Delete active bbox
            self.bbox_controller.delete_current_bbox()

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
        elif a0.key() == Keys.Key_Z:
            # z rotate counterclockwise
            self.bbox_controller.rotate_around_z()
        elif a0.key() == Keys.Key_X:
            # z rotate clockwise
            self.bbox_controller.rotate_around_z(clockwise=True)
        elif a0.key() == Keys.Key_C:
            # y rotate counterclockwise
            self.bbox_controller.rotate_around_y()
        elif a0.key() == Keys.Key_V:
            # y rotate clockwise
            self.bbox_controller.rotate_around_y(clockwise=True)
        elif a0.key() == Keys.Key_B:
            # x rotate counterclockwise
            self.bbox_controller.rotate_around_x()
        elif a0.key() == Keys.Key_N:
            # x rotate clockwise
            self.bbox_controller.rotate_around_x(clockwise=True)
        #### DUAL EVENTS BASED ON PICKING
        ### IS NOT DRAWING
        elif a0.key() == Keys.Key_W and not self.drawing_mode.is_active():
            # move backward
            self.bbox_controller.translate_along_y(boost=self.shift_pressed)

        elif a0.key() == Keys.Key_S and not self.drawing_mode.is_active():
            # move forward
            self.bbox_controller.translate_along_y(forward=True, boost=self.shift_pressed)

        elif a0.key() == Keys.Key_A and not self.drawing_mode.is_active():
            # move left
            self.bbox_controller.translate_along_x(left=True, boost=self.shift_pressed)

        elif a0.key() == Keys.Key_D and not self.drawing_mode.is_active():
            # move right
            self.bbox_controller.translate_along_x(boost=self.shift_pressed)

        elif a0.key() == Keys.Key_Q and not self.drawing_mode.is_active():
            # move up
            self.bbox_controller.translate_along_z(boost=self.shift_pressed)

        elif a0.key() == Keys.Key_E and not self.drawing_mode.is_active():
            # move down
            self.bbox_controller.translate_along_z(down=True, boost=self.shift_pressed)

        ### IS DRAWING
        elif a0.key() == Keys.Key_W and self.drawing_mode.is_active():
            # move backward
            # self.drawing_mode.drawing_strategy.register_translate_y
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
            if self.bbox_controller.has_active_bbox():
                self.pcd_manager.move_focus(self.bbox_controller.get_active_bbox().center, force=True)
            # self.pcd_manager.reset_transformations()
        elif a0.key() in [Keys.Key_R, Keys.Key_Left]:
            # load previous sample
            self.prev_pcd()
        elif a0.key() in [Keys.Key_F, Keys.Key_Right]:
            # load next sample
            self.next_pcd()
        elif a0.key() in [Keys.Key_T, Keys.Key_Up]:
            # select previous bbox
            self.select_relative_bbox(-1)
        elif a0.key() in [Keys.Key_G, Keys.Key_Down]:
            # select previous bbox
            self.select_relative_bbox(1)
        elif a0.key() in [Keys.Key_Y, Keys.Key_Comma]:
            # change bbox class to previous available class
            self.select_relative_class(-1)
        elif a0.key() in [Keys.Key_H, Keys.Key_Period]:
            # change bbox class to next available class
            self.select_relative_class(1)
        elif a0.key() in list(range(49, 58)):
            # select bboxes with 1-9 digit keys
            self.bbox_controller.set_active_bbox(int(a0.key()) - 49)

    @in_labeling_only_decorator
    def select_relative_class(self, step: int):
        if step == 0:
            return
        curr_class = self.bbox_controller.get_active_bbox().get_classname()  # type: ignore
        new_class = LabelConfig().get_relative_class(curr_class, step)
        self.bbox_controller.get_active_bbox().set_classname(new_class)  # type: ignore
        self.bbox_controller.update_all()  # updates UI in SelectBox

    @in_labeling_only_decorator
    def select_relative_bbox(self, step: int):
        if step == 0:
            return
        max_id = len(self.bbox_controller.bboxes) - 1
        curr_id = self.bbox_controller.active_bbox_id
        new_id = curr_id + step
        corner_case_id = 0 if step > 0 else max_id
        new_id = new_id if new_id in range(max_id + 1) else corner_case_id
        self.bbox_controller.set_active_bbox(new_id)

    def key_release_event(self, a0: QtGui.QKeyEvent) -> None:
        """Triggers actions when the user releases a key."""
        if a0.key() == Keys.Key_Control:
            self.ctrl_pressed = False
            self.view.status_manager.clear_message(Context.CONTROL_PRESSED)
        elif a0.key() == Keys.Key_Shift:
            self.shift_pressed = False

    def crop_pointcloud_inside_active_bbox(self) -> None:
        bbox = self.bbox_controller.get_active_bbox()
        assert bbox is not None
        assert self.pcd_manager.pointcloud is not None
        points_inside = bbox.is_inside(self.pcd_manager.pointcloud.points)
        pointcloud = self.pcd_manager.pointcloud.get_filtered_pointcloud(points_inside)
        if pointcloud is None:
            logging.warning("No points found inside the box. Ignored.")
            return
        self.view.save_point_cloud_as(pointcloud)
