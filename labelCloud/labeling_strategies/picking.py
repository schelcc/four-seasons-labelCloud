import logging
from typing import TYPE_CHECKING, Optional

import numpy as np

from . import BaseLabelingStrategy
from ..control.config_manager import config
from ..definitions import Mode, Point3D
from ..definitions.types import Point3D
from ..model import BBox
from ..utils import oglhelper as ogl
from ..io.labels.config import LabelConfig

if TYPE_CHECKING:
    from ..view.gui import GUI


class PickingStrategy(BaseLabelingStrategy):
    POINTS_NEEDED = 1
    PREVIEW = True

    def __init__(self, view: "GUI") -> None:
        super().__init__(view)
        logging.info("Enabled drawing mode.")
        self.view.status_manager.update_status(
            "Please pick the location for the bounding box front center.",
            mode=Mode.DRAWING,
        )
        self.tmp_p1: Optional[Point3D] = None
        self.trans: Point3D = (0, 0, 0)
        self.scale = 0
        self.bbox_z_rotation: float = 0

    def register_point(self, new_point: Point3D) -> None:
        nx, ny, nz = new_point
        tx, ty, tz = self.trans
        
        self.point_1 = (nx + tx, ny + ty, nz + tz)
        self.points_registered += 1

    def register_tmp_point(self, new_tmp_point: Point3D) -> None:
        self.tmp_p1 = new_tmp_point

    def register_scrolling(self, distance: float) -> None:
        self.bbox_z_rotation += distance // 30
        
    def register_trans_y(self, perspective, forward: bool = False, boost: bool = False):
        distance = config.getfloat("LABEL", "std_translation")
        
        if forward:
            distance *= -1

        if boost:
            distance *= config.getfloat("LABEL", "boost_multiplier")

        cosz, sinz, bu = perspective

        tx, ty, tz = self.trans
        
        tx = tx + distance * bu * -sinz
        ty = ty + distance * bu * cosz
        
        self.trans = (tx, ty, tz)

        # self.register_tmp_point(self.tmp_p1)
        
    def register_trans_x(self, perspective, left: bool = False, boost: bool = False):
        distance = config.getfloat("LABEL", "std_translation")
        
        if left:
            distance *= -1

        if boost:
            distance *= config.getfloat("LABEL", "boost_multiplier")
        
        cosz, sinz, bu = perspective
        
        tx, ty, tz = self.trans
        
        tx = tx + distance * cosz
        ty = ty + distance * sinz
        
        self.trans = (tx, ty, tz)

        # self.register_tmp_point(self.tmp_p1)
        
    def register_trans_z(self, down: bool = False, boost: bool = False):
        distance = config.getfloat("LABEL", "std_translation")

        if down:
            distance *= -1

        if boost:
            distance *= config.getfloat("LABEL", "boost_multiplier")
            
        tx, ty, tz = self.trans
        
        tz = tz + distance
        
        self.trans = (tx, ty, tz)

        # self.register_tmp_point(self.tmp_p1)
        
    def register_scale(self, distance):
        self.scale += (distance / 300)
    
    def reset_trans(self):
        self.trans = (0, 0, 0)

    def draw_preview(self) -> None:  # TODO: Refactor
        if self.tmp_p1:
            current_label = self.view.current_class_dropdown.currentText()
            dimension = (2,2,2)
            for label_class in LabelConfig().classes:
                if current_label==label_class.name:
                    dimension = label_class.dimension
            tmp_bbox = BBox(
                self.tmp_p1[0]+self.trans[0],
                self.tmp_p1[1]+self.trans[1],
                self.tmp_p1[2]+self.trans[2],
                dimension[0] + self.scale,
                dimension[1] + self.scale,
                dimension[2] + self.scale
            ) 
            tmp_bbox.set_classname(current_label)
            tmp_bbox.set_z_rotation(self.bbox_z_rotation)
            ogl.draw_cuboid(
                tmp_bbox.get_vertices(), draw_vertices=True, vertex_color=(1, 1, 0, 1)
            )

    # Draw bbox with fixed dimensions and rotation at x,y in world space
    def get_bbox(self) -> BBox:  # TODO: Refactor
        assert self.point_1 is not None

        current_label = self.view.current_class_dropdown.currentText()
        dimension = (2,2,2)
        for label_class in LabelConfig().classes:
            if current_label==label_class.name:
                dimension = label_class.dimension
        final_bbox = BBox(
            self.tmp_p1[0]+self.trans[0],
            self.tmp_p1[1]+self.trans[1],
            self.tmp_p1[2]+self.trans[2],
            dimension[0] + self.scale,
            dimension[1] + self.scale,
            dimension[2] + self.scale
        ) 
        final_bbox.set_classname(current_label)
        final_bbox.set_z_rotation(self.bbox_z_rotation)
        return final_bbox

    def reset(self) -> None:
        super().reset()
        self.tmp_p1 = None
        self.trans = (0, 0, 0)
        self.view.button_pick_bbox.setChecked(False)
