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

if TYPE_CHECKING:
    from ..control.controller import Controller

SUFFIXES = ["_top_left_dd.png", "_top_mid_dd.png", "_top_right_dd.png"]

class SingleImageManager:
    def __init__(self, label : QtWidgets.QLabel):
        self.view : "GUI"
        self.camera : Camera
        self.current_path : Optional[str] = None
        self.draw_queue = []
        self.label = label
    
    def set_view(self, view : "GUI") -> None:
        self.view = view

    def set_camera(self, camera : Camera) -> None:
        self.camera = camera

 
    def load_image(self) -> None:
        """Refresh "image_path" to reflect current image"""
        pass
    
    def render(self) -> None:
        """Perform queued draw actions"""
        if self.current_path is None:
            return

        img = QtGui.QImage(QtGui.QImageReader(str(self.current_path)).read())      
        pixmap = QPixmap.fromImage(img)
        pixmap = pixmap.scaledToWidth(1024)
        
        pixmap = pixmap.transformed(QtGui.QTransform().scale(0.50, 0.50))
        self.label.setPixmap(pixmap)
        self.label.update()
        self.label.show()
    
    def set_new_image_by_pcd(self) -> None:
        """Set new image name by a pcd path"""
        pcd_name = self.view.controller.pcd_manager.pcd_path.stem 
        postfix_length = len(self.view.controller.pcd_manager.pcd_postfix) - 4
        file_name = pcd_name[:-postfix_length]
        self.current_path = str(self.view.controller.pcd_manager.pcd_folder.absolute())+'/'+file_name+SUFFIXES[self.camera]
    
    def register_click(self) -> None:
        print(f"Camera {self.camera} clicked") 
        