import logging
from typing import TYPE_CHECKING, Optional

from ..definitions import Point3D, Point2D
from ..definitions.types import Point2DCamera

if TYPE_CHECKING:
    from ..view.gui import GUI
    
class BaseProjCorrection:
    PREVIEW: bool = False
    IGNORE_SCROLL: bool = True

    def __init__(self, view: "GUI") -> None:
        self.view = view

    # Note - In the interest of not changing more than needed, 2d point actions will be named accordingly,
    # whereas 3d point actions will be assumed 3d

    def hold_3d(self) -> bool:
        raise NotImplementedError
    
    def register_point_2d(self, new_point: Point2D) -> None:
        pass
    
    def register_point(self, new_point: Point3D) -> None:
        pass
    
    def register_tmp_point_2d(self, tmp_pt: Point2D) -> None:
        pass

    def register_tmp_point(self, tmp_pt: Point3D) -> None:
        pass

    def register_scrolling(self, distance: float) -> None:
        pass

    def register_trans_y(self, perspective, forward: bool = False, boost: bool = False):
        pass
    
    def register_trans_x(self, perspective, left: bool = False, boost: bool = False):
        pass
    
    def register_trans_z(self, down: bool = False, boost: bool = False):
        pass
    
    def register_scale(self, distance):
        pass

    def is_finished(self) -> bool:
        pass
    
    def reset(self) -> None:
        pass
    
    def draw_preview(self) -> None:
        pass
    