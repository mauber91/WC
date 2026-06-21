from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium

from world_cup_api.pipelines.fifa_pmsr.inspect import sha256_file


def render_pages(pdf_path: str | Path, output_dir: str | Path, scale: float = 2.0) -> list[tuple[str, str]]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(pdf_path))
    rendered: list[tuple[str, str]] = []
    try:
        for index in range(len(document)):
            target = target_dir / f"page-{index + 1:03d}.png"
            page = document[index]
            bitmap = page.render(scale=scale, rotation=0)
            image = bitmap.to_pil()
            image.save(target, format="PNG", optimize=False)
            rendered.append((str(target.resolve()), sha256_file(target)))
            bitmap.close()
            page.close()
    finally:
        document.close()
    return rendered
