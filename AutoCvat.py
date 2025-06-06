import random
import os
import shutil
import yaml
import json

# Library for creating CLI (Command Line Interface) interfaces
import click

# Custom modules and classes
from nodes.Datagen import DataGen
from nodes.Inference import Inferencer
from nodes.AnnotMaker import COCOConverter


class LengthMismatchError(Exception):
    """Custom exception for length mismatch between class list and confidence threshold dictionary."""

    def __init__(self, message):
        super().__init__(message)


def generate_and_save_as_json_cvat_labels(original_classes, file_name="new_classes.json"):
    # Generate a random unique color for each class
    colors = ["#" + "".join(random.choices("0123456789ABCDEF", k=6)) for _ in original_classes]

    # Create a new list of dictionaries with random colors and indexes as id
    new_classes = []
    for idx, cls in enumerate(original_classes):
        cls_dict = {"name": cls, "id": idx, "color": colors[idx], "type": "any", "attributes": []}
        new_classes.append(cls_dict)

    # Save the new list to a file
    with open(file_name, "w") as file:
        json.dump(new_classes, file, indent=2)
    print(f"JSON for CVAT saved to file {file_name}")


@click.command()
@click.option(
    "--img_folder",
    default="img_folder",
    help="Folder with images (task from CVAT)",
    type=str,
)
@click.option(
    "--weights",
    default="yolov8m.pt",
    help="Path to the Yolo model weights file with .pt extension",
    type=str,
)
@click.option(
    "--annotations_zip",
    default="annotations",
    help="Name of the COCO CVAT annotation zip archive",
    type=str,
)
@click.option(
    "--yaml_pth",
    default="config.yaml",
    help="The path to configuration yaml file",
    type=str,
)
@click.option(
    "--save_images_to_annotations_zip",
    default=False,
    help="Whether to create a zip file with photos to upload to CVAT",
    type=bool,
)
@click.option(
    "--cvat_json",
    default=False,
    help="Should I create a json file with classes for CVAT",
    type=bool,
)
@click.option(
    "--all_conf",
    default=None,
    help="The confidence parameter for all classes, confidences from config don't use",
    type=float,
)
@click.option(
    "--zero_shot_segmentation",
    default=False,
    help="When set to True, it allows for zero-shot instance segmentation using SAM from any source detection network",
    type=bool,
)
def main(**kwargs):
    result_folder = kwargs["annotations_zip"]
    model_pth = kwargs["weights"]
    input_folder = kwargs["img_folder"]
    configs = kwargs["yaml_pth"]
    save_images_to_annotations_zip = bool(kwargs["save_images_to_annotations_zip"])
    cvat_json = bool(kwargs["cvat_json"])
    conf = kwargs["all_conf"]
    use_box_propt_sam = kwargs["zero_shot_segmentation"]

    # Check if the folder exists
    if not os.path.exists(input_folder):
        print(f"Folder '{input_folder}' does not exist.")
        return 

    # Check if the folder is empty
    if not os.listdir(input_folder):
        print(f"Folder '{input_folder}' is empty.")
        return  
        
    # Load data from YAML file
    with open(configs, "r") as yaml_file:
        configs = yaml.safe_load(yaml_file)
    # Get all keys and all values
    classes_cvat = list(configs["names"].values())
    classes_coco = list(configs["names"].keys())

    if conf is not None:
        dict_confs = {}
    else:
        dict_confs = configs.get("confs", {})
        if classes_coco != list(dict_confs):
            raise LengthMismatchError(
                "Class list and confidence threshold dictionary keys list do not match. "
                "Each class must correspond to a confidence threshold."
            )
        min_value_conf = min((float(value) for value in dict_confs.values()))
        conf = min_value_conf  # default conf as min conf of classes

    # If the result folder already exists, delete it and create a new one
    if os.path.exists(result_folder):
        shutil.rmtree(result_folder)

    # Create a result folder for annotations and images for uploading to cvat
    os.mkdir(result_folder)
    os.mkdir(result_folder + "/annotations")

    if save_images_to_annotations_zip:
        files = os.listdir(input_folder)
        os.mkdir(result_folder + "/images")
        for file_name in files:
            source_file = os.path.join(input_folder, file_name)
            destination_file = os.path.join(result_folder + "/images", file_name)
            shutil.copy2(source_file, destination_file)  

    # Create a JSON string in COCO format
    datagen = DataGen(input_folder)
    elements = datagen.process()

    # Inference each photo
    inferencer = Inferencer(
        elements,
        segment=configs.get("segment", False),
        model_path=model_pth,
        classes_list=classes_coco,
        conf_dict=dict_confs,
        conf=conf,
        imgsz=configs.get("imgsz", 640),
        iou=configs.get("iou", 0.8),
        minimize_points=configs.get("minimize_points", False),
        use_box_propt_sam=use_box_propt_sam,
    )
    elements = inferencer.process()

    # Create a JSON object
    converter = COCOConverter(elements, classes_cvat, classes_coco)
    results = converter.convert_to_coco()

    # Write JSON to file
    output_file_path = os.path.join(result_folder + "/annotations", "instances_default.json")

    with open(output_file_path, "w") as output_file:
        output_file.write(results)

    # Create a zip archive from the result folder
    shutil.make_archive(result_folder, "zip", result_folder)

    # Print the path to the result folder in the terminal
    print(f"Annotations are located at: {result_folder}.zip")

    # Delete the result folder
    shutil.rmtree(result_folder)

    if cvat_json:
        generate_and_save_as_json_cvat_labels(classes_cvat)


if __name__ == "__main__":
    main()
