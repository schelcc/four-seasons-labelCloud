import logging
from typing import TYPE_CHECKING, Optional

import numpy as np
from . import BaseLabelingStrategy
from ..control.config_manager import config
from ..definitions import Mode, Point3D, Point2D
from ..definitions.types import Point3D, Point2D
from ..utils import oglhelper as ogl
from ..io.labels.config import LabelConfig

if TYPE_CHECKING:
    from ..view.gui import GUI


class CorrectionStrategy(BaseLabelingStrategy):
    POINTS_NEEDED = 1
    PREVIEW = True
            
    def __init__(self, view: "GUI") -> None:
        super().__init__(view)
        logging.info("Enabled drawing mode")
        self.view.status_manager.update_status(
            "Please pick the 3D point you'd like to correct",
            mode=Mode.Drawing,
        )
        self.tmp_p3d: Optional[Point3D] = None
        self.tmp_p2d: Optional[Point2D] = None
        self.corresponding_view = None # TODO : Make type for associating 2d points to specific view
    
    def register_point_3d(self, new_point: Point3D) -> None:
        pass
    
    def register_tmp_point_3d(self, new_tmp_point: Point3D) -> None:
        pass
    