import argparse
import csv
from pathlib import Path

import cv2


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def blur_score(image_path: Path):
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    return float(cv2.Laplacian(image, cv2.CV_64F).var())


def main():
    parser = argparse.ArgumentParser(description="Find low-sharpness avatar frames.")
    parser.add_argument("avatar_dir", nargs="?", default="data/wav2lip_avatar_wzj2cjl")
    parser.add_argument("--subdir", default="full_imgs")
    parser.add_argument("--threshold", type=float, default=80.0)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--csv", default="")
    args = parser.parse_args()

    image_dir = Path(args.avatar_dir) / args.subdir
    if not image_dir.exists():
        raise FileNotFoundError(f"Image directory not found: {image_dir}")

    image_paths = sorted(
        path for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not image_paths:
        raise FileNotFoundError(f"No images found in: {image_dir}")

    rows = []
    for image_path in image_paths:
        score = blur_score(image_path)
        if score is not None:
            rows.append((image_path, score))

    rows.sort(key=lambda item: item[1])
    scores = [score for _, score in rows]
    below_threshold = [item for item in rows if item[1] < args.threshold]

    print(f"Scanned: {len(rows)} frames")
    print(f"Score min/avg/max: {min(scores):.2f} / {sum(scores) / len(scores):.2f} / {max(scores):.2f}")
    print(f"Frames below threshold {args.threshold:.2f}: {len(below_threshold)}")
    print()
    print(f"Worst {min(args.top, len(rows))} frames:")
    for image_path, score in rows[:args.top]:
        print(f"{score:10.2f}  {image_path}")

    if args.csv:
        csv_path = Path(args.csv)
        with csv_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["path", "blur_score"])
            writer.writerows((str(path), f"{score:.4f}") for path, score in rows)
        print()
        print(f"Wrote CSV: {csv_path}")


if __name__ == "__main__":
    main()
