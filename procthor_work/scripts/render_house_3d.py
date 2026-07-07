import os

if "HOME" not in os.environ:
    os.environ["HOME"] = os.environ["USERPROFILE"]

from pathlib import Path

import matplotlib.pyplot as plt
import prior
from ai2thor.controller import Controller


def main():
    dataset = prior.load_dataset("procthor-10k")
    house = dataset["train"][0]

    controller = Controller(
        scene=house,
        width=800,
        height=600,
        quality="Low",
        renderInstanceSegmentation=False,
        renderDepthImage=False,
    )

    event = controller.last_event

    print("Last action:", event.metadata.get("lastAction"))
    print("Success:", event.metadata.get("lastActionSuccess"))
    print("Error:", event.metadata.get("errorMessage"))

    frame = event.frame

    output_path = Path("procthor_work/outputs/sample_house_0_3d.png")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    plt.imsave(output_path, frame)
    print(f"Saved image to: {output_path}")

    controller.stop()


if __name__ == "__main__":
    main()