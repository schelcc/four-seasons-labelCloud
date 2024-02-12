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
from PyQt5.QtWidgets import QLabel

from ..control.config_manager import config
from ..definitions import Color3f, LabelingMode, Camera
from ..definitions.types import Point2D
from ..io.labels.config import LabelConfig
from ..io.pointclouds import BasePointCloudHandler
from ..labeling_strategies import PickingStrategy, SpanningStrategy
from ..proj_correction_strategies import PointMatchCorrection
from ..model.point_cloud import PointCloud
from ..utils.decorators import in_labeling_only_decorator, in_projection_only_decorator
from ..control.base_drawing_manager import BaseDrawingManager

if TYPE_CHECKING:
    from ..control.controller import Controller
    from ..control.view import GUI

SUFFIXES = ["_top_left_dd.png", "_top_mid_dd.png", "_top_right_dd.png"]

class SingleImageManager:
    def __init__(self, label : QtWidgets.QLabel, view : "GUI"):
        self.view : "GUI" = view
        self.drawing_mode : Optional[BaseDrawingManager] = None
        self.camera : Camera
        self.current_path : Optional[str] = None
        self.draw_queue = []
        self.label = label
        self.render_queue = []
        self.base_image : Optional[QPixmap] = None
        self.cursor_pos : Optional[Point2D] = None

        # Draw action flags
        self.do_draw_cursor : bool = False
        self.do_draw_calib_points : bool = self.view.in_projection
        self.do_draw_bboxes : bool = self.view.in_labeling
    
    def set_view(self, view : "GUI") -> None:
        self.view = view

    def set_camera(self, camera : Camera) -> None:
        self.camera = camera

    def load_image(self) -> None:
        """Refresh "image_path" to reflect current image"""
        self.refresh_image_path()

        if self.current_path is None:
            return

        img = QtGui.QImage(QtGui.QImageReader(str(self.current_path)).read())      
        pixmap = QPixmap.fromImage(img)
        pixmap = pixmap.scaledToWidth(1024)
    
        pixmap = pixmap.transformed(QtGui.QTransform().scale(0.50, 0.50))
        self.base_image = pixmap.copy()

    def render(self) -> None:
        if self.base_image is None or self.view is None or self.drawing_mode is None:
            return
        
        pixmap = self.base_image.copy() 
        
        if self.view.in_projection and self.drawing_mode.is_active():
            self.draw_cursor(pixmap) 
        
        if self.view.in_projection:
            self.draw_pts(pixmap)
         
        self.label.setPixmap(pixmap)
        self.label.update()
        self.label.show()
    
    def refresh_image_path(self) -> None:
        """Set new image name by a pcd path"""
        pcd_name = self.view.controller.pcd_manager.pcd_path.stem 
        postfix_length = len(self.view.controller.pcd_manager.pcd_postfix) - 4
        file_name = pcd_name[:-postfix_length]
        self.current_path = str(self.view.controller.pcd_manager.pcd_folder.absolute())+'/'+file_name+SUFFIXES[self.camera]
    
    def register_click(self) -> None:
        print(f"Camera {self.camera} clicked") 

    def draw_crosshairs(self,
        point: Point2D,
        pixmap : QPixmap,
        color = QtCore.Qt.gray,
        thickness = 1,
        scale = 1,
        line_type = QtCore.Qt.SolidLine ) -> None:
        
        painter = QPainter(pixmap)
        painter.setPen(QPen(color, thickness, line_type))
        
        x, y = point
        
        painter.drawLine(x-5*scale, y, x+5*scale, y)
        painter.drawLine(x, y-5*scale, x, y+5*scale) 
        
        painter.end()

    def draw_cursor(self, pixmap : QPixmap) -> None:
        if self.cursor_pos is None:
            return

        self.draw_crosshairs(
            self.cursor_pos,
            pixmap,
            color=QtCore.Qt.red,
            thickness=1,
            scale=2,
            line_type=QtCore.Qt.DashLine
        )            
            
    def draw_pts(self, pixmap : QPixmap, thickness : int = 3) -> None:
        all_pts = self.view.controller.point_controller.points
        
        if len(all_pts) == 0: 
            return

        active_pt = self.view.controller.point_controller.active_point_id
        
        for idx, pt in enumerate(all_pts):
            _, p2d, cam = pt
            
            if cam != self.camera: continue        

            color = QtCore.Qt.green if idx == active_pt else QtCore.Qt.blue
           
            self.draw_crosshairs(p2d, pixmap, color=color, thickness=thickness)