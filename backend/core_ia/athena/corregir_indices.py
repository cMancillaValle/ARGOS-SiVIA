import os

labels_path = "dataset/labels"

for split in ["train", "val"]:
    folder = os.path.join(labels_path, split)

    for file in os.listdir(folder):
        if file.endswith(".txt"):
            path = os.path.join(folder, file)

            with open(path, "r") as f:
                lines = f.readlines()

            new_lines = []
            for line in lines:
                parts = line.strip().split()

                # Ignorar líneas vacías o corruptas
                if len(parts) < 5:
                    continue

                if parts[0] == "15":
                    parts[0] = "0"
                elif parts[0] == "16":
                    parts[0] = "1"

                new_lines.append(" ".join(parts))

            with open(path, "w") as f:
                f.write("\n".join(new_lines))

print("Clases corregidas correctamente")