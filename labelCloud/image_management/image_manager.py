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
    IMAGE_SCALED_WIDTH: int = 2048//4
    IMAGE_SCALED_HEIGHT: int = 1536//4
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

        self.SCALE = config.getfloat("USER_INTERFACE", "image_scale")

        # Draw action flags
        self.do_draw_cursor : bool = False
        self.do_draw_bboxes : bool = False 
        self.do_draw_calib_points : bool = False
        
    def detransform(self, point : Point2D) -> Point2D:
        """Perform pixmap transformations in reverse to match pixels properly"""
        new_x, new_y = point 
        new_x *= (4*(1/self.SCALE))
        new_y *= (4*(1/self.SCALE))
        return Point2D(new_x, new_y)

    def transform_pt(self, point: Point2D) -> Point2D:
        """Perform pixmap transformations to match true pt to scaled pt"""
        new_x, new_y = point 
        new_x *= 1/(4*(1/self.SCALE))
        new_y *= 1/(4*(1/self.SCALE))
        return Point2D(new_x, new_y)

    def set_view(self, view : "GUI") -> None:
        self.view = view
        self.do_draw_calib_points = self.view.PROJECTION
        self.do_draw_bboxes = self.view.LABELING


    def set_camera(self, camera : Camera) -> None:
        self.camera = camera

    def load_image(self) -> None:
        """Refresh "image_path" to reflect current image"""
        self.refresh_image_path()

        if self.current_path is None:
            return

        img = QtGui.QImage(QtGui.QImageReader(str(self.current_path)).read())      
        pixmap = QPixmap.fromImage(img)
        pixmap = pixmap.scaled(self.IMAGE_SCALED_WIDTH, self.IMAGE_SCALED_HEIGHT, QtCore.Qt.KeepAspectRatio)
    
        pixmap = pixmap.transformed(QtGui.QTransform().scale(self.SCALE, self.SCALE))

        self.base_image = pixmap.copy()

    def render(self) -> None:
        if self.base_image is None or self.view is None or self.drawing_mode is None:
            return
        
        pixmap = self.base_image.copy() 
        
        if self.view.PROJECTION and self.drawing_mode.is_active():
            self.draw_cursor(pixmap) 
        
        if self.view.PROJECTION:
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
        pass

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
            
    def draw_pts(self, pixmap : QPixmap, thickness : int = 1) -> None:
        all_pts = self.view.controller.element_controller.elements
        
        if len(all_pts) == 0: 
            return

        active_pt = self.view.controller.element_controller.active_element_id
        
        for idx, pt in enumerate(all_pts):
            _, p2d, cam = pt
            
            if cam != self.camera: continue        

            color = QtCore.Qt.green if idx == active_pt else QtCore.Qt.blue
           
            self.draw_crosshairs(p2d, pixmap, color=color, thickness=thickness)

    def draw_bboxes(self, pixmap : QPixmap) -> None:
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