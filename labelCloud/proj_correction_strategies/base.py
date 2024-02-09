from typing import TYPE_CHECKING, Optional

from ..definitions import Point3D, Point2D
from ..definitions.types import Point2DCamera

if TYPE_CHECKING:
    from ..view.gui import GUI
    
class BaseProjCorrection:
    PREVIEW: bool = False

    def __init__(self, view: "GUI") -> None:
        self.view = view

    # Note - In the interest of not changing more than needed, 2d point actions will be named accordingly,
    # whereas 3d point actions will be assumed 3d

    def register_point_2d(self, new_point: Point2D) -> None:
        pass
    
    def register_point(self, new_point: Point3D) -> None:
        pass
    
    def register_tmp_point_2d(self, tmp_pt: Point2D) -> None:
        pass

    def register_tmp_point(self, tmp_pt: Point3D) -> None:
        pass

    def is_bbox_finished(self) -> bool:
        pass
    
    def reset(self) -> None:
        pass
    
    def draw_preview(self) -> None:
        pass
    