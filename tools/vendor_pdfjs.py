"""Reproduce the local reader assets after `npm ci` in tools. Never fetch a CDN at runtime."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'tools/node_modules/pdfjs-dist'
destination=ROOT/'app/static/pdfjs'
version='6.3.289'
assert json.loads((source/'package.json').read_text(encoding='utf-8'))['version']==version
lock=json.loads((ROOT/'tools/package-lock.json').read_text(encoding='utf-8'))
destination.mkdir(parents=True,exist_ok=True)
for name in ['pdf.min.mjs','pdf.worker.min.mjs']:
    shutil.copyfile(source/'build'/name,destination/name)
shutil.copyfile(source/'LICENSE',destination/'LICENSE')
for directory in ['cmaps','standard_fonts','wasm']:
    for file in (source/directory).iterdir():
        if not file.is_file() or file.name.startswith('quickjs-eval'):continue
        target=destination/directory/file.name;target.parent.mkdir(exist_ok=True)
        shutil.copyfile(file,target)
# The JavaScript-in-PDF interpreter is unused and is intentionally not distributed.
for name in ['quickjs-eval.js','quickjs-eval.wasm']:
    target=destination/'wasm'/name
    if target.exists():target.unlink()
css=(source/'web/pdf_viewer.css').read_text(encoding='utf-8')
start=css.index('.textLayer{');end=css.index('.annotationLayer{',start)
(destination/'text_layer.css').write_text('/* PDF.js '+version+' text layer. Mozilla contributors, Apache-2.0; see LICENSE. */\n'+css[start:end],encoding='utf-8')
records=[{'path':p.relative_to(destination).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in sorted(destination.rglob('*')) if p.is_file() and p.name!='vendor-manifest.json']
(destination/'vendor-manifest.json').write_text(json.dumps({'package':'pdfjs-dist','version':version,'license':'Apache-2.0',
    'npm_integrity':lock['packages']['node_modules/pdfjs-dist']['integrity'],'files':records},indent=2),encoding='utf-8')
print('Vendored',len(records),'local PDF.js assets; no PDF scripting runtime.')
