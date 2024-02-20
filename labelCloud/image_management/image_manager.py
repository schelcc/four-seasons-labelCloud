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
import numpy as np

import pkg_resources
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import Qt as Keys
from PyQt5.QtWidgets import QGraphicsPixmapItem
from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QPixmap, QPainter, QPen, QTransform

from ..definitions import Color3f, Camera
from ..definitions.types import Point2D
from ..utils.decorators import in_labeling_only_decorator, in_projection_only_decorator, logging_debug
from ..control.base_drawing_manager import BaseDrawingManager

if TYPE_CHECKING:
    from ..control.view import GUI

SUFFIXES = ["_top_left_dd.png", "_top_mid_dd.png", "_top_right_dd.png"]

class SingleImageManager:
    POINT_PRECISION : int = 2 # Decimal places to register for 2d
    def __init__(self, g_view, view : "GUI") -> None:
        self.view : "GUI" = view
        self.graphics_view : ImageGraphicsView = g_view
        self.scene = QtWidgets.QGraphicsScene()
        self.img : Optional[QGraphicsPixmapItem] = None
        self.base_pixmap : Optional[QPixmap] = None

        self.camera = 0
        
        self.scale = 1.0
        self.is_mouse_down : bool = False
        self.prev_pos : Optional[QtCore.QPoint] = None
        self.cursor_p2d : Optional[Point2D] = None

        # Never show scroll bars
        self.graphics_view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.graphics_view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.graphics_view.setSceneRect(0, 0, 500, 500)

        # Connect events
        self.graphics_view.wheelEvent = lambda event : self.zoom(event)
        self.graphics_view.mousePressEvent = lambda event : self.mouse_down(event)
        self.graphics_view.mouseReleaseEvent = lambda event : self.mouse_up(event)
        self.graphics_view.mouseMoveEvent = lambda event : self.mouse_move(event)
        self.graphics_view.setMouseTracking(True) # Forces Qt to register a mouseMove w/o any buttons pressed

    def set_camera(self, cam) -> None:
        self.camera = cam

    # HANDLERS
    def mouse_down(self, event : QtGui.QKeyEvent) -> None:
        """mouseDown event handler"""
        self.cursor_p2d = event.pos()

        # Translation (Dragging)
        if event.button() == Keys.RightButton:
            self.is_mouse_down = True

        # Point registering
        elif event.button() == Keys.LeftButton:
            pos_in_scene = self.graphics_view.mapToScene(event.pos())
            if self.img is not None:
                pos_in_img = self.img.mapFromScene(pos_in_scene)
                img_x = pos_in_img.x()
                img_y = pos_in_img.y()
                if (0 < img_x < 2048) and (0 < img_y < 1536):
                    self.view.controller.image_clicked((img_x, img_y), self.camera)

    def mouse_up(self, event : QEvent) -> None:
        """mouseUp event handler"""
        # Don't release is_down unless specifically the right is released
        if event.button() == Keys.RightButton:
            self.is_mouse_down = False

    def mouse_move(self, event : QtGui.QMouseEvent) -> None:
        """mouseMove event handler"""
        corr_pos = self.event_pos_to_img(event.pos())
        self.cursor_p2d = (corr_pos.x(), corr_pos.y()) if corr_pos is not None else None

        if self.is_mouse_down:
            self.drag(event.pos())

        self.prev_pos = event.pos()

        self.render()

    # ACTIONS
    def drag(self, mouse_pos : QtCore.QPoint) -> None:
        """Translate/drag the image within the GraphicsView. Updates image"""
        new_pos = self.event_pos_to_img(mouse_pos, fail_outside=False)
       
        # Do nothing if there is no prev_pos 
        if self.prev_pos is None:
            self.prev_pos = mouse_pos
            return
        
        prev_pos = self.event_pos_to_img(self.prev_pos, fail_outside=False)
        
        delta = prev_pos - new_pos
        
        transform = self.img.transform()
        
        deltaX = delta.x() * transform.m11()
        deltaY = delta.y() * transform.m22()

        tr = self.img.transform()
        tr *= QTransform(1, 0, 0, 1, -deltaX, -deltaY)
        self.img.setTransform(tr)
    
    def zoom(self, event: QtGui.QMouseEvent) -> None:
        """Scale the image element within the Graphics Scene, clipping between 0.1x and 10x. Updates the image."""
        amt = event.angleDelta().y() / 4000
        self.graphics_view.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

        if self.img is not None:
            if 0.1 < (self.scale + amt) < 10:
                tr = self.img.transform()
                tr *= QTransform((self.scale+amt)/self.scale, 0, 0, (self.scale+amt)/self.scale, 1, 1)
                self.img.setTransform(tr)
                self.scale += amt

        self.graphics_view.update()

    # UTIL
    def refresh_scene_pixmap(self, pixmap : QPixmap) -> None:
        """Refresh displayed pixmap with new pixmap"""
        prev_transform_global = self.graphics_view.transform()
        prev_transform_img = self.img.transform()

        # Remove current pixmap
        self.scene.removeItem(self.img)
        
        # Add new pixmap and reset self.img
        self.img = self.scene.addPixmap(pixmap)
       
        # Put transforms back in place 
        self.graphics_view.setTransform(prev_transform_global)
        self.img.setTransform(prev_transform_img)

    def load_image(self) -> QPixmap:
        """Refresh "image_path" to reflect current image"""
        self.refresh_image_path()

        if self.current_path is None:
            return

        img = QtGui.QImage(QtGui.QImageReader(str(self.current_path)).read())      
        pixmap = QPixmap.fromImage(img)
        return pixmap
    
    def refresh_image_path(self) -> None:
        """Set new image name by a pcd path"""
        pcd_name = self.view.controller.pcd_manager.pcd_path.stem 
        postfix_length = len(self.view.controller.pcd_manager.pcd_postfix) - 4
        file_name = pcd_name[:-postfix_length]
        self.current_path = str(self.view.controller.pcd_manager.pcd_folder.absolute())+'/'+file_name+SUFFIXES[self.camera]

    def refresh_base_pixmap(self) -> None:
        """Refresh base pixmap, should only be called when current sample changes"""
        self.base_pixmap = self.load_image()
        
    def render(self) -> None:
        if self.img is None:
            self.init_image()
            return

        if self.base_pixmap is None:
            self.refresh_base_pixmap()
        
        pixmap = self.base_pixmap.copy()

        self.draw_cursor(pixmap)

        if self.view.PROJECTION:
            self.draw_pts(pixmap)

        self.refresh_scene_pixmap(pixmap)

    def init_image(self) -> None:
        """First image draw. Subsequent draws should call to refresh_pixmap()"""

        # Set class base pixmap
        self.refresh_base_pixmap()
        pixmap = self.base_pixmap.copy()

        self.img = self.scene.addPixmap(pixmap)

        bound = self.scene.itemsBoundingRect()
        bound.setWidth(pixmap.width())
        bound.setHeight(pixmap.height())

        self.graphics_view.setScene(self.scene)
        self.graphics_view.fitInView(bound, QtCore.Qt.KeepAspectRatio) 
        self.graphics_view.update() 

    def event_pos_to_img(self, pos : QtCore.QPoint, fail_outside:bool=True) -> Optional[QtCore.QPoint]:
        """Transform the pos from an event into image coordinates.
        
        Options:
            fail_outside (bool) : Returns None if the converted pt is outside the img. Defaults True."""
        pos_in_scene = self.graphics_view.mapToScene(pos)
        if self.img is not None:
            pos_in_img = self.img.mapFromScene(pos_in_scene)
            if (0 < pos_in_img.x() < 2048) and (0 < pos_in_img.y() < 1536) and fail_outside:
                return pos_in_img
            elif not fail_outside:
                return pos_in_img
            else:
                return None

    # DRAWING
    def draw_crosshairs(self,
        point: Point2D,
        pixmap : QPixmap,
        color = QtCore.Qt.gray,
        thickness = 2,
        scale = 2,
        line_type = QtCore.Qt.DashLine ) -> None:
        
        painter = QPainter(pixmap)
        painter.setPen(QPen(color, thickness, line_type))
        
        x, y = point
        
        painter.drawLine(x-5*scale, y, x+5*scale, y)
        painter.drawLine(x, y-5*scale, x, y+5*scale) 
        painter.drawPoint(*point)
        
        painter.end() 

    def draw_cursor(self, pixmap : QPixmap) -> None:
        if self.cursor_p2d is None:
            return

        self.draw_crosshairs(
            self.cursor_p2d,
            pixmap,
            color=QtCore.Qt.red,
            thickness=2,
            scale=7,
            line_type=QtCore.Qt.DashLine
        )    
    
    def draw_pts(self, pixmap : QPixmap, thickness : int = 3, scale : int = 6) -> None:
        all_pts = self.view.controller.element_controller.elements
        
        if len(all_pts) == 0: 
            return

        active_pt = self.view.controller.element_controller.active_element_id
        
        for idx, pt in enumerate(all_pts):
            _, p2d, cam = pt
            
            if cam != self.camera: continue        

            color = QtCore.Qt.green if idx == active_pt else QtCore.Qt.blue
            
            self.draw_crosshairs(p2d, pixmap, color=color, thickness=thickness, scale=scale) 