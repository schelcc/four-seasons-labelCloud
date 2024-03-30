import logging
from pathlib import Path
from typing import TYPE_CHECKING, Tuple

import numpy as np
import numpy.typing as npt
from math import exp

from . import BasePointCloudHandler

from ...definitions.types import Color3f

from ...control.config_manager import config

if TYPE_CHECKING:
    from ...model import PointCloud

def sig(intensity, falloff=0.009):
    return 1.0/(1+exp(-1*falloff*intensity))

class NumpyHandler(BasePointCloudHandler):
    EXTENSIONS = {".bin",".txt"}

    def __init__(self) -> None:
        super().__init__()

    def read_point_cloud(self, path: Path) -> Tuple[npt.NDArray, None]:
        """Read point cloud file as array and drop reflection and nan values."""
        super().read_point_cloud(path)

        points = np.loadtxt(path)
        points = points.astype(np.float32)
        points = points[~np.isnan(points).any(axis=1)] # Remove NaN's
        if config.getboolean("USER_INTERFACE", "do_intensity"):
            colors = points[:, 3]

            colors = np.array(
                [Color3f(0.9, sig(c, falloff=0.005) , sig(c, falloff=0.00001)) \
                 for c in colors]).astype("float32")

            return (points[:, :3], colors)
        else:
            return (points[:, :3], None)

    def write_point_cloud(self, path: Path, pointcloud: "PointCloud") -> None:
        """Write point cloud points into binary file."""
        super().write_point_cloud(path, pointcloud)
        logging.warning(
            "Only writing point coordinates, any previous reflection values will be dropped."
        )
        pointcloud.points.tofile(path)
