import json
import yaml
import logging
import numpy as np
from pathlib import Path
from typing import Any, Dict, List

from ...model import BBox
from . import BaseLabelFormat, abs2rel_rotation, rel2abs_rotation


class CentroidFormat(BaseLabelFormat):
    FILE_ENDING = ".yaml"

    def import_labels(self, pcd_path: Path) -> List[BBox]:
        labels = []
        
        label_path = self.label_folder.joinpath(pcd_path.stem[:-5]+'_label3d'+self.FILE_ENDING)
        if label_path.is_file():
            with label_path.open("r") as read_file:
                #data = json.load(read_file)
                data = yaml.safe_load(read_file) # LXH

            for label in data["labels"]:
                x,y,z = label["box3d"]["location"]["x"],label["box3d"]["location"]["y"],label["box3d"]["location"]["z"]
                l,w,h = label["box3d"]["dimension"]["length"],label["box3d"]["dimension"]["width"],label["box3d"]["dimension"]["height"]
                bbox = BBox(x,y,z,l,w,h)
                rx,ry,rz = 0.0,0.0,(label["box3d"]["orientation"]["z_rotation"]/np.pi*180.0)
                if self.relative_rotation:
                    rotations = map(rel2abs_rotation, rotations)
                bbox.set_rotations(rx,ry,rz)
                bbox.set_classname(label["category"])
                labels.append(bbox)
            logging.info(
                "Imported %s labels from %s." % (len(data["labels"]), label_path)
            )
        return labels

    def export_labels(self, bboxes: List[BBox], pcd_path: Path) -> None:
        out_dict: Dict[str, Any] = {}

        out_dict['name'] = pcd_path.name[:-9]
        out_dict['timestamp'] = 0
        out_dict['index'] = out_dict['name']
        labels_list = []

        # Labels
        for i in range(len(bboxes)):
            bbox = bboxes[i]
            label_i = {}
            label_i['id'] = i+1
            label_i['category'] = bbox.get_classname()            
            dimension = {'length':float(bbox.length), 'width':float(bbox.width), 'height':float(bbox.height)}
            location = {'x':float(bbox.center[0]), 'y':float(bbox.center[1]), 'z':float(bbox.center[2])}
            orientation = {'x_rotation':0.0,'y_rotation':0.0,'z_rotation':float(bbox.z_rotation/180.0*np.pi)}
            label_i['box3d'] = {'dimension':dimension, 'location':location, 'orientation':orientation}
            labels_list.append(label_i)
        out_dict['labels'] = labels_list

        label_path = str(self.label_folder.absolute())+'/'+out_dict['name']+'_label3d.yaml'
        with open(label_path, 'w') as f:
            yaml.safe_dump(out_dict, f)
        f.close()     

        # Save to YAML
        logging.info(
            f"Exported {len(bboxes)} labels to {label_path} "
            f"in {self.__class__.__name__} formatting!"
        )
