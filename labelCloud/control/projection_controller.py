"""
Additional class to handle all projection correction behavior
"""

import logging
from functools import wraps
from typing import TYPE_CHECKING, List, Optional
import json
import yaml
import os
from os import path
import numpy as np

from ..definitions import Mode, Camera, Color4f
from ..definitions.types import PointPairCamera, Point2D, Point3D
from ..utils import oglhelper
from .config_manager import config
from .pcd_manager import PointCloudManager
from ..utils.oglhelper import draw_crosshair

if TYPE_CHECKING:
    from ..view.gui import GUI

# Decorators
def has_active_point_decorator(func):
    """
    Only execute decorated function if there is an active point
    """
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        if args[0].has_active_point():
            return func(*args, **kwargs)
        else:
            logging.warning("There is currently no active point to manipulate")
            
    return wrapper
    
class ProjectionCorrectionController(object):
    
    def __init__(self) -> None:
        self.view: GUI
        self.pcd_manger: PointCloudManager
        self.points: List[PointPairCamera] = []
        self.active_point_id = -1 # -1 means zero point pairs
        
    def has_active_point(self) -> bool:
        return 0 <= self.active_point_id < len(self.points)
    
    def get_active_point(self) -> Optional[PointPairCamera]:
        if self.has_active_point():
            return self.points[self.active_point_id]
        else:
            return None
        
    def set_view(self, view: "GUI") -> None:
        self.view = view

    def add_point(self, point_pair: PointPairCamera) -> None:
        #if isinstance(point_pair, PointPairCamera):
        self.points.append(point_pair)
        #self.set_active_point(self.points.index(point_pair))
        self.set_active_point(len(self.points)-1)
        
    def update_point(self, point_id: int, point_pair: PointPairCamera) -> None:
        if isinstance(point_pair, PointPairCamera) and (0 <= point_id < len(self.points)):
            self.points[point_id] = point_pair

    def delete_point(self, point_id: int) -> None:
        if 0 <= point_id < len(self.points):
            del self.points[point_id]
            if point_id == self.active_point_id:
                self.set_active_point(len(self.points) -1)
    
    def delete_current_point(self) -> None:
        selected_item_id = self.view.label_list.currentRow()
        self.delete_point(selected_item_id)
        
    def set_active_point(self, point_id: int) -> None:
        print(f"setting active to {point_id}")
        if 0 <= point_id < len(self.points):
            self.active_point_id = point_id
            self.update_all()
        else:
            self.deselect_point()
        print(f"active is now {self.active_point_id}")
            
    def set_points(self, points: List[PointPairCamera]):
        self.points = points
        self.deselect_point()
        self.update_point_list()
        
    def reset(self) -> None:
        self.deselect_point()
        self.set_points([])
        
    def deselect_point(self) -> None:
        self.active_point_id = -1
        self.update_all()
        self.view.status_manager.set_mode(Mode.NAVIGATION)

    @has_active_point_decorator
    def update_3d_point(self, point : Point3D) -> None:
        _, p2d_pre, cam_pre = self.get_active_point()
        self.points[self.active_point_id] = (point, p2d_pre, cam_pre)
    
    @has_active_point_decorator
    def update_2d_point(self, point : Point2D, camera : Camera) -> None:
        p3d_pre, _, _ = self.get_active_point()
        self.points[self.active_point_id] = (p3d_pre, point, camera)

    def show_3d_points(self) -> None:
        for idx, point in enumerate(self.points):
            color = (0, 1, 0, 1) if idx == self.active_point_id else (0, 0, 1, 1)
            x, y, z = point[0]
            draw_crosshair(x, y, z, color, scale=5, thickness=2.5)
            
    # HELPER
    
    def update_all(self) -> None:
        """Update all various variable displays"""
        self.update_point_list()
        self.update_p3d_readout()
        self.update_p2d_readout()
        self.update_camera_readout()
        
    def update_point_list(self) -> None:
        self.view.point_list.blockSignals(True)
        self.view.point_list.clear()
        for point in self.points:
            self.view.point_list.addItem("Point")
        if self.has_active_point():
            self.view.point_list.setCurrentRow(self.active_point_id)
            current_item = self.view.point_list.currentItem()
            if current_item:
                current_item.setSelected(True)
        self.view.point_list.blockSignals(False) 

    def update_p3d_readout(self) -> None:
        if self.has_active_point():
            for idx, lbl in enumerate([self.view.point3d_label_x, self.view.point3d_label_y, self.view.point3d_label_z]):
                lbl.setText(str(self.get_active_point()[0][idx]))
    
    def update_p2d_readout(self) -> None:
        if self.has_active_point():
            for idx, lbl in enumerate([self.view.point2d_label_x, self.view.point2d_label_y]):
                lbl.setText(str(self.get_active_point()[1][idx]))

    def update_camera_readout(self) -> None:
        cams = ["Left", "Middle", "Right"]
        if self.has_active_point():
            self.view.camera_label.setText(cams[self.get_active_point()[2]])     

    def get_points_from_file(self) -> None:
        self.points = []
        
        input_folder = config.getpath("FILE", "manual_calib_folder", fallback="manual_calib/")
        
        pcd_name = self.view.controller.pcd_manager.pcd_path.name
        pcd_name = pcd_name.replace("_oust.txt", "")
        
        in_path = path.join(input_folder, f"{pcd_name}_points.txt")
        
        try:
            with open(in_path, "r") as f:
                for line in f.readlines():
                    l = line.strip()
                    cam, p3d_x, p3d_y, p3d_z, p2d_x, p2d_y = l.split(',')

                    p3d = (float(p3d_x), float(p3d_y), float(p3d_z))
                    p2d = (float(p2d_x), float(p2d_y))
                    cam = int(cam)
                    
                    self.points.append((p3d, p2d, cam))

                    self.set_active_point(0)
        except:
            logging.info("Error loading points, file may not exist or may be formatted incorrectly")


    def save_points_to_file(self) -> None:
        if len(self.points) == 0:
            return
        
        output_folder = config.getpath("FILE", "manual_calib_folder", fallback="manual_calib/")
        
        # get sample name
        pcd_name = self.view.controller.pcd_manager.pcd_path.name
        pcd_name = pcd_name.replace("_oust.txt", "")

        out_path = path.join(output_folder, f"{pcd_name}_points.txt")
        
        out_fp = open(out_path, "w")
        
        out_str = ""
        for pt in self.points:
            p3d, p2d, cam = pt
            out_str += f"{str(cam)},{p3d[0]},{p3d[1]},{p3d[2]},{p2d[0]},{p2d[1]}\n"

        out_fp.write(out_str)
        out_fp.close()
        logging.info(f"Saved points to {out_path}")
