import os
from wand.image import Image
from wand.color import Color

INPUT_DIR = r"E:\projects\python\discord_bot_manager\emojis"
OUTPUT_DIR = INPUT_DIR

def convert_svg_to_png():
    if not os.path.isdir(INPUT_DIR):
        print(f"Hiba: nincs ilyen mappa -> {INPUT_DIR}")
        return

    converted = 0
    deleted = 0

    for file in os.listdir(INPUT_DIR):
        if file.lower().endswith(".svg"):
            svg_path = os.path.join(INPUT_DIR, file)
            png_path = os.path.join(OUTPUT_DIR, file.replace(".svg", ".png"))

            try:
                with Image(filename=svg_path) as img:
                    img.format = 'png'

                    img.background_color = Color('transparent')
                    img.alpha_channel = 'activate'
                    img.save(filename=png_path)

                print(f"✔ {file} -> PNG")
                converted += 1

                os.remove(svg_path)
                print(f"🗑️ törölve: {file}")
                deleted += 1

            except Exception as e:
                print(f"✖ Hiba {file}: {e}")

    print(f"\nKész! {converted} konvertálva, {deleted} törölve.")

if __name__ == "__main__":
    convert_svg_to_png()