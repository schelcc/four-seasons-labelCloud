import logging
from typing import TYPE_CHECKING, Optional

import numpy as np

from . import BaseProjCorrection
from ..control.config_manager import config
from ..definitions import Mode, Point2D, Point3D, Camera
from ..definitions.types import Point2D, Point3D, Point2DCamera
from ..utils import oglhelper as ogl
from ..io.labels.config import LabelConfig

if TYPE_CHECKING:
    from ..view.gui import GUI
    

class PointMatchCorrection(BaseProjCorrection):
    PREVIEW: bool = True

    def __init__(self, view: "GUI") -> None:
        super().__init__(view)
        logging.info("Enabled projection correction mode.")
        self.view.status_manager.update_status(
            "Please pick the 3D point to match",
            mode=Mode.DRAWING,
        )
        
        self.foo = "Hell"
        self.tmp_p2d : Optional[Point2DCamera] = None
        self.tmp_p3d : Optional[Point3D] = (0., 0., 0.,)
        
        self.point_2d : Optional[Point2DCamera] = None
        self.point_3d : Optional[Point3D] = None
        
    def register_point(self, new_point: Point3D) -> None:
        self.point_3d = new_point
        
    def register_point_2d(self, new_point: Point2DCamera) -> None:
        self.point_2d = new_point
        
    def register_tmp_point(self, new_point: Point3D) -> None:
        self.tmp_p3d = new_point
        
    def register_tmp_point_2d(self, new_point: Point2DCamera) -> None:
        self.tmp_p2d = new_point

    def draw_preview(self) -> None:
        print(self.foo)
        return
        if self.tmp_p3d is not None:
            ogl.draw_points([self.tmp_p3d], color=(0, 1, 0, 1))