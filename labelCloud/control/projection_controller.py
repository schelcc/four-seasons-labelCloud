"""
Additional class to handle all projection correction behavior
"""

import logging
from functools import wraps
from typing import TYPE_CHECKING, List, Optional
import json
import yaml
import os
import numpy as np

from ..definitions import Mode, Camera
from ..definitions.types import PointPairCamera, Point2D, Point3D
from ..utils import oglhelper
from .config_manager import config
from .pcd_manager import PointCloudManager

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

    # TODO : self.view gives access to gui, can use for updating lists and whatnot
        
    def add_point(self, point_pair: PointPairCamera) -> None:
        if isinstance(point_pair, PointPairCamera):
            self.points.append(point_pair)
            self.set_active_point(self.points.index(point_pair))
        
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
        if 0 <= point_id < len(self.points):
            self.active_point_id = point_id
            self.update_all()
        else:
            self.deselect_point()
            
    def set_points(self, points: List[PointPairCamera]):
        self.points = points
        self.deselect_point()
        self.update_label_list()
        
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
        
    # HELPER
    
    def update_all(self) -> None:
        """Update all various variable displays"""
        self.update_label_list()
        
    def update_label_list(self) -> None:
        # TODO
        pass
        