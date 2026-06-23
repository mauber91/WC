from __future__ import annotations

import html
from pathlib import Path

from world_cup_api.pipelines.fifa_pmsr.types import ExtractionBundle


def write_audit_report(bundle: ExtractionBundle, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    root = target.parent
    issue_rows = "".join(
        "<tr>"
        f"<td>{html.escape(issue.severity)}</td>"
        f"<td>{issue.page_number or ''}</td>"
        f"<td>{html.escape(issue.code)}</td>"
        f"<td>{html.escape(issue.message)}</td>"
        "</tr>"
        for issue in bundle.issues
    ) or '<tr><td colspan="4">No issues</td></tr>'
    page_cards: list[str] = []
    for page in bundle.pages:
        counts = {name: len(elements) for name, elements in page.payloads.items()}
        render = Path(page.render_uri)
        try:
            render_uri = render.relative_to(root).as_posix()
        except ValueError:
            render_uri = render.as_uri()
        page_cards.append(
            '<section class="page">'
            f"<h2>Page {page.page_number}: {html.escape(page.classification.page_type)}</h2>"
            f'<img src="{html.escape(render_uri)}" alt="Rendered page {page.page_number}">'
            f"<p>Section: {html.escape(page.classification.section or '—')} · "
            f"Team: {html.escape(page.classification.team_scope or '—')} · "
            f"Confidence: {page.classification.confidence:.1%}</p>"
            f"<pre>{html.escape(str(counts))}</pre>"
            "</section>"
        )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>FIFA PMSR extraction audit</title>
<style>
body{{font-family:ui-sans-serif,system-ui;margin:0;background:#f4f5f7;color:#172033}}
header{{padding:24px 32px;background:#101c3a;color:white;position:sticky;top:0;z-index:2}}
main{{padding:24px 32px;max-width:1500px;margin:auto}}
.summary{{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:12px;margin-bottom:24px}}
.metric,.page{{background:white;border:1px solid #dce1e8;border-radius:10px;padding:16px}}
.metric strong{{display:block;font-size:1.5rem}} table{{width:100%;border-collapse:collapse;background:white;margin-bottom:24px}}
th,td{{border:1px solid #dce1e8;padding:8px;text-align:left;vertical-align:top}}
.pages{{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:18px}}
.page img{{width:100%;border:1px solid #cfd5df}} pre{{white-space:pre-wrap}}
</style></head><body>
<header><h1>FIFA PMSR extraction audit</h1><div>{html.escape(bundle.manifest.filename)} · {bundle.manifest.sha256}</div></header>
<main><div class="summary">
<div class="metric"><span>Status</span><strong>{bundle.status}</strong></div>
<div class="metric"><span>Quality</span><strong>{bundle.quality_score:.1%}</strong></div>
<div class="metric"><span>Coverage</span><strong>{bundle.coverage:.1%}</strong></div>
<div class="metric"><span>Pages</span><strong>{len(bundle.pages)}</strong></div>
</div>
<h2>Review queue</h2><table><thead><tr><th>Severity</th><th>Page</th><th>Code</th><th>Message</th></tr></thead><tbody>{issue_rows}</tbody></table>
<div class="pages">{''.join(page_cards)}</div></main></body></html>"""
    target.write_text(document, encoding="utf-8")
    return target
