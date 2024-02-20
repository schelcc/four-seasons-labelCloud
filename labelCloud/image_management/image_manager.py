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
from ..utils.decorators import in_labeling_only_decorator, in_projection_only_decorator
from ..control.base_drawing_manager import BaseDrawingManager

if TYPE_CHECKING:
    from ..control.view import GUI

SUFFIXES = ["_top_left_dd.png", "_top_mid_dd.png", "_top_right_dd.png"]

class SingleImageManager:
    def __init__(self, g_view, view : "GUI") -> None:
        self.view : "GUI" = view
        self.graphics_view : ImageGraphicsView = g_view
        self.scene = QtWidgets.QGraphicsScene()
        self.camera = 0
        self.img : Optional[QGraphicsPixmapItem] = None
        self.scale = 1.0
        self.graphics_view.scale(self.scale, self.scale)
        self.graphics_view.setSceneRect(0, 0, 500, 500)
        self.is_mouse_down : bool = False

        self.prev_pos : Optional[QtCore.QPoint] = None

        self.graphics_view.wheelEvent = lambda x : self.zoom(x)
        self.graphics_view.mousePressEvent = lambda x : self.mouse_down(x)
        self.graphics_view.mouseReleaseEvent = lambda x : self.mouse_up(x)
        self.graphics_view.mouseMoveEvent = lambda x : self.refresh(x)
        self.graphics_view.setMouseTracking(True)
        
        self.last_val : Optional[float] = None

        self.graphics_view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.graphics_view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

    def mouse_down(self, event : QtGui.QKeyEvent) -> None:
        if event.button() == Keys.RightButton:
            self.is_mouse_down = True
        elif event.button() == Keys.LeftButton:
            pos_in_scene = self.graphics_view.mapToScene(event.pos())
            if self.img is not None:
                pos_in_img = self.img.mapFromScene(pos_in_scene)
                img_x = pos_in_img.x()
                img_y = pos_in_img.y()
                if (0 < img_x < 2048) and (0 < img_y < 1536):
                    self.view.controller.image_clicked((img_x, img_y), self.camera)

    def mouse_up(self, event : QEvent) -> None:
        # Don't release is_down unless specifically the right is released
        if event.button() == Keys.RightButton:
            self.is_mouse_down = False

    def set_camera(self, cam) -> None:
        self.camera = cam

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

    def render(self) -> None:
        logging.debug("SingleImageManager render")

        pixmap = self.load_image()

        self.img = self.scene.addPixmap(pixmap)

        bound = self.scene.itemsBoundingRect()
        bound.setWidth(pixmap.width())
        bound.setHeight(pixmap.height())
        self.graphics_view.setScene(self.scene)
        self.graphics_view.fitInView(bound, QtCore.Qt.KeepAspectRatio) 
        self.graphics_view.update() 

    def refresh(self, event : QtGui.QMouseEvent) -> None:
        new_pos = self.graphics_view.mapFromGlobal(event.pos())
        
        if self.is_mouse_down :
            if self.prev_pos is None:
                self.prev_pos = event.pos()
                return
            
            prev_pos = self.graphics_view.mapFromGlobal(self.prev_pos)
            
            delta = prev_pos - new_pos
            
            transform = self.graphics_view.transform()
            
            deltaX = delta.x() / transform.m11()
            deltaY = delta.y() / transform.m22()

            tr = self.img.transform()
            tr *= QTransform(1, 0, 0, 1, -deltaX, -deltaY)
            self.img.setTransform(tr)
        
        self.prev_pos = event.pos()
    
    def get_zoom_amt(self, event : QtGui.QMouseEvent) -> float:
        delta = event.angleDelta().y()
        return delta / 4000 

    def zoom(self, event : QtGui.QMouseEvent) -> None:
        amt = self.get_zoom_amt(event)
        self.graphics_view.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

        if self.img is not None:
            if 0.1 < (self.scale + amt) < 10:
                tr = self.img.transform()
                tr *= QTransform((self.scale+amt)/self.scale, 0, 0, (self.scale+amt)/self.scale, 1, 1)
                self.img.setTransform(tr)
                self.scale += amt

        self.graphics_view.update()
