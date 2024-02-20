import logging 
from pathlib import Path 
from typing import Dict, List, Optional

from ...control.config_manager import config 
from ...model import Element
from ...definitions import PointPairCamera
from ...definitions import Point2D, Point3D
from . import BaseLabelFormat 

class PointMatchRaw(BaseLabelFormat):
    FILE_ENDING = ".txt"
    
    def __init__(
        self,
        label_folder: Path,
        export_precision: int,
        relative_rotation: bool = False,
        transformed: bool = True,
    ) -> None:
        super().__init__(label_folder, export_precision)
        self.transformed = transformed
        self.name_suffix = "_points" 
    
    def import_labels(self, pcd_path: Path) -> List[PointPairCamera]:
        points = []
       
        name = pcd_path.stem.split('_')[0] + self.name_suffix 
        label_path = self.label_folder.joinpath(name + self.FILE_ENDING)

        if label_path.is_file():
            with label_path.open("r") as read_file:
                lines = read_file.readlines()
            
            for line in lines[1:]:
                try:
                    cam, p3dx, p3dy, p3dz, p2dx, p2dy = line.split(',')
                    p3d = Point3D(float(p3dx), float(p3dy), float(p3dz))
                    p2d = Point2D(float(p2dx), float(p2dy))
                    point = PointPairCamera(p3d, p2d, int(cam))
                    points.append(point)
                except ValueError:
                    logging.warning(f"Error reading points from {label_path}, it likely has no points")
                    continue
        
        return points

    def export_labels(self, points: List[PointPairCamera], pcd_path: Path) -> None:
        if len(points) == 0:
            return
        output = "camera,point3d_x_y_z,point2d_x_y\n"
        output += '\n'.join([str(x) for x in points])
        output += '\n'
        path_to_file = self.save_label_to_file(pcd_path, output, suffix="_points")
        logging.info(
            f"Exported {len(points)} pairs to {path_to_file} "
            f"in {self.__class__.__name__} formatting!"
        )