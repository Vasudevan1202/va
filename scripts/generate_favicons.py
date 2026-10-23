"""
Virtual Atmosphere (VA) - Favicon & Brand Asset Generator
Generates high-resolution, optimized favicon assets, web manifests,
and UI brand logos from the source logo.jpg.
"""

import os
import json
from pathlib import Path
from PIL import Image

def generate_assets(base_dir=None):
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent
    else:
        base_dir = Path(base_dir)

    static_dir = base_dir / "static"
    img_dir = static_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    logo_path = base_dir / "logo.jpg"
    if not logo_path.exists():
        raise FileNotFoundError(f"Source logo not found at {logo_path}")

    im = Image.open(logo_path).convert("RGBA")
    w, h = im.size

    # Unblend white background cleanly into alpha channel
    pixels = im.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if r >= 252 and g >= 252 and b >= 252:
                pixels[x, y] = (0, 0, 0, 0)
            else:
                diff = 255 - r
                alpha = min(255, int(diff * 1.08))
                if alpha > 0:
                    scale = 255.0 / alpha
                    new_r = max(0, min(255, int(255 - (255 - r) * scale)))
                    new_g = max(0, min(255, int(255 - (255 - g) * scale)))
                    new_b = max(0, min(255, int(255 - (255 - b) * scale)))
                    pixels[x, y] = (new_r, new_g, new_b, alpha)
                else:
                    pixels[x, y] = (0, 0, 0, 0)

    # Content bounding box calculation
    bbox = im.getbbox()
    cx = (bbox[0] + bbox[2]) // 2
    cy = (bbox[1] + bbox[3]) // 2
    cw = bbox[2] - bbox[0]
    ch = bbox[3] - bbox[1]
    max_side = max(cw, ch)

    # Square crop with balanced padding so content fills ~88-90% of the canvas
    pad = int(max_side * 0.06)
    crop_size = max_side + 2 * pad
    crop_box = (cx - crop_size // 2, cy - crop_size // 2, cx + crop_size // 2, cy + crop_size // 2)
    cropped_trans = im.crop(crop_box)

    # 1. Favicon 16x16, 32x32 transparent
    fav_16 = cropped_trans.resize((16, 16), Image.Resampling.LANCZOS)
    fav_32 = cropped_trans.resize((32, 32), Image.Resampling.LANCZOS)
    fav_48 = cropped_trans.resize((48, 48), Image.Resampling.LANCZOS)

    fav_16.save(static_dir / "favicon-16x16.png", format="PNG", optimize=True)
    fav_32.save(static_dir / "favicon-32x32.png", format="PNG", optimize=True)

    # Favicon.ico with multi-resolution directly from cropped master
    cropped_trans.save(
        static_dir / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)]
    )

    # Optimized transparent logos for UI components
    logo_512 = cropped_trans.resize((512, 512), Image.Resampling.LANCZOS)
    logo_512.save(img_dir / "va-logo.png", format="PNG", optimize=True)

    logo_64 = cropped_trans.resize((64, 64), Image.Resampling.LANCZOS)
    logo_64.save(img_dir / "va-logo-sm.png", format="PNG", optimize=True)

    # 2. Solid brand background (#07111F) for apple-touch-icon and android-chrome
    def create_brand_icon(size, icon_ratio=0.74):
        bg = Image.new("RGBA", (size, size), (7, 17, 31, 255))
        icon_size = int(size * icon_ratio)
        scaled_logo = cropped_trans.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
        offset = ((size - icon_size) // 2, (size - icon_size) // 2)
        bg.alpha_composite(scaled_logo, offset)
        return bg

    apple_icon = create_brand_icon(180, icon_ratio=0.72)
    apple_icon.save(static_dir / "apple-touch-icon.png", format="PNG", optimize=True)

    android_192 = create_brand_icon(192, icon_ratio=0.72)
    android_192.save(static_dir / "android-chrome-192x192.png", format="PNG", optimize=True)

    android_512 = create_brand_icon(512, icon_ratio=0.74)
    android_512.save(static_dir / "android-chrome-512x512.png", format="PNG", optimize=True)

    card_logo = create_brand_icon(256, icon_ratio=0.76)
    card_logo.save(img_dir / "va-logo-card.png", format="PNG", optimize=True)

    # 3. site.webmanifest with asset cache-busting query parameter
    asset_version = os.environ.get("VA_ASSET_VERSION", "1.0.1")
    manifest_data = {
        "name": "Virtual Atmosphere",
        "short_name": "VA",
        "description": "Understand Your Atmosphere. Real-time environmental monitoring platform.",
        "icons": [
            {
                "src": f"/static/android-chrome-192x192.png?v={asset_version}",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": f"/static/android-chrome-512x512.png?v={asset_version}",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ],
        "theme_color": "#07111F",
        "background_color": "#07111F",
        "display": "standalone",
        "start_url": "/dashboard",
        "orientation": "portrait-primary"
    }

    with open(static_dir / "site.webmanifest", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    print("Successfully generated all favicon and branding assets.")

if __name__ == "__main__":
    generate_assets()
