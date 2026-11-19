"""Self-contained, escaped HTML exports for reproducible analysis."""
import json
from html import escape


def html_report(title, summary, table, metadata, figures=(), notes=(), sections=()):
    content = "".join(f"<li>{escape(str(note))}</li>" for note in notes)
    charts = "".join(fig.to_html(full_html=False, include_plotlyjs=index == 0)
                     for index, fig in enumerate(figures))
    method = escape(json.dumps(metadata, ensure_ascii=False, indent=2, default=str))
    table_html = table.to_html(index=False, escape=True)
    details = "".join(f'<section><h2>{escape(label)}</h2><div class="table">'
                      f'{data.to_html(index=False, escape=True)}</div></section>' for label, data in sections)
    return f"""<!doctype html>
<html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>body{{font:16px system-ui;background:#0D1117;color:#F0F3F6;margin:auto;max-width:76rem;padding:1rem}}
table{{border-collapse:collapse}}th,td{{border:1px solid #303A46;padding:.35rem}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.table{{overflow:auto}}</style>
<h1>{escape(title)}</h1><p>{escape(summary)}</p><ul>{content}</ul>
{charts}<div class="table">{table_html}</div>{details}<h2>Procedencia y parámetros</h2><pre>{method}</pre></html>"""
