"""
Additional class to handle all manual calibration behavior
"""

import logging
from functools import wraps
from typing import TYPE_CHECKING, List, Optional
import json
import yaml
import os
from os import path
import numpy as np

from logdecorator import log_on_start
from .base_element_controller import BaseElementController, has_active_element_decorator
from ..definitions import Mode, Camera, Color4f
from ..definitions.types import PointPairCamera, Point2D, Point3D
from ..utils import oglhelper
from .config_manager import config
from .pcd_manager import PointCloudManager
from ..utils.oglhelper import draw_crosshair

if TYPE_CHECKING:
    from ..view.gui import GUI


class ProjectionCorrectionController(BaseElementController):
    
    def __init__(self) -> None:
        super().__init__(PointPairCamera)
            
    def show_3d_points(self) -> None:
        for idx, point in enumerate(self.elements):
            color = (0, 1, 0, 1) if idx == self.active_element_id else (0, 0, 1, 1)
            x, y, z = point.p3d
            draw_crosshair(x, y, z, color, scale=5, thickness=2.5)
            
    def update_all(self) -> None:
        """Update all various variable displays"""
        self.update_element_list()
        self.update_p3d_readout()
        self.update_p2d_readout()
        self.update_camera_readout()
        
    def update_element_list(self) -> None:
        self.view.element_list.blockSignals(True)
        self.view.element_list.clear()
        for point in self.elements:
            self.view.element_list.addItem("Point")
        if self.has_active_element():
            self.view.element_list.setCurrentRow(self.active_element_id)
            current_item = self.view.element_list.currentItem()
            if current_item:
                current_item.setSelected(True)
        self.view.element_list.blockSignals(False) 

    def update_p3d_readout(self) -> None:
        if self.has_active_element():
            for idx, lbl in enumerate([self.view.row1_col1_edit, self.view.row1_col2_edit, self.view.row2_col3_edit]):
                lbl.setText(str(self.get_active_element().p3d[idx]))
    
    def update_p2d_readout(self) -> None:
        if self.has_active_element():
            for idx, lbl in enumerate([self.view.row2_col1_edit, self.view.row2_col2_edit]):
                lbl.setText(str(self.get_active_element().p2d[idx]))

    def update_camera_readout(self) -> None:
        if self.has_active_element():
            self.view.row3_col1_edit.setText(str(self.get_active_element().cam))     

    def translate_along_y(self, forward=False, boost=False):
        """Move active element within 2D view"""
        distance = config.getfloat("LABEL", "std_translation")
        distance*=4

        if not forward:
            distance *= -1
        
        if boost:
            distance *= config.getfloat("LABEL", "boost_multiplier")

        pt = self.get_active_element()
        pt.p2d = (pt.p2d[0], pt.p2d[1] + distance)
        self.update_element(self.active_element_id, pt)

        self.view.refresh_images(do_pixmap=False)

        
    def translate_along_x(self, left=False, boost=False):
        """Move active element within 2D view"""
        distance = config.getfloat("LABEL", "std_translation")
        distance*=4

        if left:
            distance *= -1
        
        if boost:
            distance *= config.getfloat("LABEL", "boost_multiplier")

        pt = self.get_active_element()
        pt.p2d = (pt.p2d[0] + distance, pt.p2d[1]) 
        self.update_element(self.active_element_id, pt)

        self.view.refresh_images(do_pixmap=False)

    def focus_element(self) -> Optional[Point3D]:
        if len(self.elements) > 0 and self.active_element_id >= 0:
            return self.elements[self.active_element_id].p3d
        else:
            return None
